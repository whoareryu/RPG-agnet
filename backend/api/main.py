"""FastAPI 앱 — 얇은 HTTP 계층 (설계 §11.1). 도메인 판단을 하지 않는다.

런은 백그라운드 스레드에서 돌고 이벤트를 큐에 넣는다. /runs/{id}/stream 이 큐를
SSE 로 흘리고, 끝나면 저장소에 남긴다. 완료된 런의 스트림은 저장된 이벤트를
한 번에 흘린다 — 새로고침해도 같은 화면이 나온다.
"""

import json
import logging
import queue
import secrets
import threading
from collections.abc import Callable, Iterator
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from adapters.harness.harness import Harness
from adapters.llm.fake import FakeModel
from adapters.llm.replay import ReplayModel
from api.schemas import CreateRunRequest, CreateRunResponse, DirectivesRequest
from api.security import 시크릿_검사
from content.classes import CLASSES, choose_build
from content.events import pool_for
from content.missions import MISSIONS_A, MISSIONS_B
from content.party import apply_direction, build_party
from content.roster import PRESET_ALLOCATIONS, PRESET_ROSTER
from core.intermission import IntermissionInput, IntermissionState, run_intermission
from core.ports import DecisionModel, RunStore
from core.rules.constants import FREE_POINTS, MAX_CALLS, STAT_BASE
from core.rules.dice import SeededDice
from core.rules.disposition import describe, mbti_label
from core.runner import RunRecord, run
from core.trace.schema import TraceEvent
from core.types import RunConfig

logger = logging.getLogger("rpg.api")

_DONE = object()


class RunSession:
    """진행 중인 런 하나. 이벤트 큐 + 완료 플래그 + 인터미션 입력 대기."""

    def __init__(self, run_id: str, config: RunConfig) -> None:
        self.run_id = run_id
        self.config = config
        self.events: list[TraceEvent] = []
        self.queue: queue.Queue[Any] = queue.Queue()
        self.done = threading.Event()
        self.error: str | None = None
        # 인터미션에서 유저 입력을 기다리는 자리. 화면이 응답하지 않아도 판은
        # 이어져야 하므로 대기에 상한을 둔다(설계 §11.1).
        self.directives: queue.Queue[DirectivesRequest] = queue.Queue()
        self.awaiting_input = threading.Event()

    def emit(self, event: TraceEvent) -> None:
        self.events.append(event)
        self.queue.put(event)


# 인터미션에서 유저 지시를 기다리는 상한(초). 넘으면 기본값(전원 훈련·분배 없음)
# 으로 간다 — 판이 멈춘 채로 남으면 스트림이 영원히 열려 있다.
DIRECTIVE_TIMEOUT = 60.0


def build_app(
    store: RunStore,
    model_factory: Callable[[], DecisionModel],
    model_name: str = "fake",
    experiments_dir: Path | None = None,
    directive_timeout: float = DIRECTIVE_TIMEOUT,
) -> FastAPI:
    app = FastAPI(title="rpg-arena", docs_url=None, redoc_url=None, openapi_url=None)
    sessions: dict[str, RunSession] = {}
    guard = [Depends(시크릿_검사)]

    @app.get("/healthz")
    def healthz() -> dict[str, Any]:
        return {
            "status": "ok",
            "model": model_name,
            "max_calls": MAX_CALLS,
            "active_runs": len(sessions),
        }

    @app.get("/roster/preset", dependencies=guard)
    def roster_preset() -> dict[str, Any]:
        out = []
        for c in PRESET_ROSTER:
            alloc = PRESET_ALLOCATIONS[c.id]
            cfg = _config(
                seed=0,
                lineup=(c.id,),
                allocations={c.id: alloc},
                classes={},
                genders={},
                orchestrator=True,
                adaptation=True,
                missions=MISSIONS_A,
            )
            directed = apply_direction(cfg, c.id)
            build = choose_build(directed)
            out.append(
                {
                    "id": c.id,
                    "name": c.name,
                    "gender": c.gender,
                    "body": asdict(c.body),
                    "weight_class": c.body.weight_class,
                    "base_stats": c.stats.as_dict(),
                    "recommended": alloc,
                    "class": c.char_class,
                    "disposition": c.disposition.as_dict(),
                    "disposition_text": describe(c.disposition),
                    "mbti": mbti_label(c.disposition),
                    "life": c.life.note,
                    "backstory": c.backstory,
                    "build_preview": {
                        "weapon": build.weapon.name,
                        "armor": build.armor.name,
                        "rationale": build.rationale,
                    },
                }
            )
        return {
            "roster": out,
            "classes": [
                {"key": k, "label": v.label, "primary": v.primary} for k, v in CLASSES.items()
            ],
            "free_points": FREE_POINTS,
            "stat_base": STAT_BASE,
            "lineup_size": MISSIONS_A[0].lineup_max,
        }

    @app.post("/runs", response_model=CreateRunResponse, dependencies=guard)
    def create_run(req: CreateRunRequest) -> CreateRunResponse:
        seed = req.seed if req.seed is not None else secrets.randbelow(1_000_000)
        cfg = _config(
            seed=seed,
            lineup=tuple(req.lineup),
            allocations=req.allocations,
            classes=req.classes,
            genders=req.genders,
            orchestrator=req.orchestrator,
            adaptation=req.adaptation,
            missions=MISSIONS_B if req.missions == 2 else MISSIONS_A,
        )
        try:
            members = build_party(cfg)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        run_id = secrets.token_hex(6)
        session = RunSession(run_id, cfg)
        sessions[run_id] = session
        _start(session, members, model_factory)
        return CreateRunResponse(run_id=run_id, seed=seed, model=model_name)

    @app.get("/runs/{run_id}/stream", dependencies=guard)
    def stream(run_id: str) -> StreamingResponse:
        session = sessions.get(run_id)
        if session is not None:
            return StreamingResponse(
                _sse_live(session),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        record = _load(run_id)
        return StreamingResponse(_sse_static(record.events), media_type="text/event-stream")

    @app.get("/runs/{run_id}", dependencies=guard)
    def get_run(run_id: str) -> dict[str, Any]:
        session = sessions.get(run_id)
        if session is not None:
            return {
                "run_id": run_id,
                "done": session.done.is_set(),
                "error": session.error,
                "events": [asdict(e) for e in session.events],
            }
        record = _load(run_id)
        return {
            "run_id": run_id,
            "done": True,
            "error": None,
            "events": [asdict(e) for e in record.events],
        }

    @app.post("/runs/{run_id}/replay", response_model=CreateRunResponse, dependencies=guard)
    def replay(run_id: str) -> CreateRunResponse:
        """녹화된 판을 Replay 모델로 다시 돌린다 — 모델 호출 0(기획서 §11.3)."""
        record = _load(run_id)
        cfg = _config_from_payload(record.config)
        members = build_party(cfg)
        new_id = secrets.token_hex(6)
        session = RunSession(new_id, cfg)
        sessions[new_id] = session
        events = list(record.events)
        _start(session, members, lambda: Harness(ReplayModel(events, FakeModel()), FakeModel()))
        return CreateRunResponse(run_id=new_id, seed=cfg.seed, model="replay")

    @app.post("/runs/{run_id}/directives", dependencies=guard)
    def directives(run_id: str, req: DirectivesRequest) -> dict[str, Any]:
        """인터미션 입력 — 육성 지시 + 성장 포인트 분배(기획서 §5·§5.1)."""
        session = sessions.get(run_id)
        if session is None:
            raise HTTPException(status_code=404, detail="진행 중인 런이 아니다")
        if not session.awaiting_input.is_set():
            raise HTTPException(status_code=409, detail="지금은 인터미션이 아니다")
        session.directives.put(req)
        return {"status": "accepted"}

    @app.get("/runs", dependencies=guard)
    def recent(limit: int = 20) -> dict[str, Any]:
        return {"runs": store.list_recent(min(limit, 50))}

    @app.get("/experiments", dependencies=guard)
    def experiments() -> dict[str, Any]:
        """돌아 있는 실험 목록. 화면이 무엇을 그릴 수 있는지 먼저 묻는다."""
        if experiments_dir is None or not experiments_dir.exists():
            return {"available": []}
        return {"available": sorted(p.stem for p in experiments_dir.glob("*.json"))}

    @app.get("/experiments/{name}", dependencies=guard)
    def experiment(name: str) -> dict[str, Any]:
        if name not in ("e1", "e2", "e3", "e4"):
            raise HTTPException(status_code=404, detail=f"모르는 실험: {name}")
        # experiments_dir 가 없으면 "실험 결과가 없다" 다. 상대 경로로 기본값을 두면
        # 테스트가 프로세스의 작업 디렉토리에 따라 결과를 주웠다 놓쳤다 한다.
        path = (experiments_dir / f"{name}.json") if experiments_dir else None
        if path is None or not path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"{name.upper()} 결과가 아직 없다. "
                f"backend 에서 `uv run python -m eval.run -e {name}` 을 돌린다",
            )
        return json.loads(path.read_text(encoding="utf-8"))

    # ─── 내부 ──────────────────────────────────────────────────────────

    def _load(run_id: str) -> RunRecord:
        try:
            record = store.load(run_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        if record is None:
            raise HTTPException(status_code=404, detail="그런 런이 없다")
        return record

    def _start(session: RunSession, members: Any, factory: Callable[[], DecisionModel]) -> None:
        def work() -> None:
            try:
                intermission = _intermission_for(session)
                record = run(
                    session.run_id,
                    session.config,
                    members,
                    factory,
                    SeededDice,
                    sink=session,
                    intermission=intermission,
                )
                try:
                    store.save(record)
                except Exception:  # noqa: BLE001 — 저장 실패가 화면을 끊으면 안 된다
                    logger.exception("런 저장 실패 %s", session.run_id)
            except Exception as e:  # noqa: BLE001
                logger.exception("런 실패 %s", session.run_id)
                session.error = f"{type(e).__name__}: {e}"
            finally:
                session.done.set()
                session.queue.put(_DONE)
                # 완료 후 잠시 세션을 남겨 스트림이 끝을 읽게 한다. 저장됐으니 지워도 된다.
                threading.Timer(60.0, lambda: sessions.pop(session.run_id, None)).start()

        threading.Thread(target=work, name=f"run-{session.run_id}", daemon=True).start()

    def _intermission_for(session: RunSession) -> Any:
        """인터미션 훅. 유저 입력을 기다렸다가 core 의 인터미션을 돌린다."""
        state = IntermissionState()

        def hook(members, result, model, dice, tracer):  # type: ignore[no-untyped-def]
            session.awaiting_input.set()
            # 화면에게 "지금 입력받는다" 를 알린다. 이 이벤트가 없으면 스트림을
            # 보는 쪽은 판이 멈춘 이유를 알 수 없다.
            tracer.emit(
                "intermission_start",
                {
                    "awaiting_input": True,
                    "after_outcome": result.outcome,
                    "party": [c.id for c, _, _ in members],
                    "timeout_s": directive_timeout,
                },
            )
            try:
                req = session.directives.get(timeout=directive_timeout)
                user = IntermissionInput(directives=dict(req.directives), growth=dict(req.growth))
            except queue.Empty:
                user = IntermissionInput()
            finally:
                session.awaiting_input.clear()
            try:
                return run_intermission(
                    members, result.outcome, user, pool_for, model, dice, tracer, state
                )
            except ValueError as e:
                # 유저 입력이 규칙을 어겼다(포인트 초과 등). 판을 죽이지 않고
                # 기본값으로 간다 — 그 사실을 트레이스에 남긴다.
                logger.warning("인터미션 입력 거부 %s: %s", session.run_id, e)
                tracer.emit("intermission_start", {"rejected": str(e), "fallback": True})
                return run_intermission(
                    members,
                    result.outcome,
                    IntermissionInput(),
                    pool_for,
                    model,
                    dice,
                    tracer,
                    state,
                )

        return hook

    return app


def _sse(event: TraceEvent) -> str:
    return f"event: {event.kind}\ndata: {json.dumps(asdict(event), ensure_ascii=False)}\n\n"


def _sse_live(session: RunSession) -> Iterator[str]:
    # 이미 지나간 이벤트부터 — 중간에 접속해도 처음부터 본다.
    sent = 0
    while True:
        while sent < len(session.events):
            yield _sse(session.events[sent])
            sent += 1
        if session.done.is_set() and sent >= len(session.events):
            break
        try:
            item = session.queue.get(timeout=15)
        except queue.Empty:
            yield ": keepalive\n\n"
            continue
        if item is _DONE:
            while sent < len(session.events):
                yield _sse(session.events[sent])
                sent += 1
            break
    if session.error:
        yield f"event: error\ndata: {json.dumps({'error': session.error}, ensure_ascii=False)}\n\n"
    yield "event: done\ndata: {}\n\n"


def _sse_static(events: list[TraceEvent]) -> Iterator[str]:
    for e in events:
        yield _sse(e)
    yield "event: done\ndata: {}\n\n"


def _config(
    seed: int,
    lineup: tuple[str, ...],
    allocations: dict,
    classes: dict,
    genders: dict,
    orchestrator: bool,
    adaptation: bool,
    missions: tuple,
) -> RunConfig:
    return RunConfig(
        seed=seed,
        lineup=lineup,
        allocations=allocations,
        classes=classes,
        genders=genders,
        orchestrator_on=orchestrator,
        adaptation_on=adaptation,
        missions=missions,
        intermission=len(missions) > 1,
    )


def _config_from_payload(p: dict[str, Any]) -> RunConfig:
    """run_start payload → RunConfig. 리플레이는 같은 설정이어야 같은 질문이 나온다.

    설정을 역산하지 않는다 — run_start 가 유저의 방향 결정을 그대로 싣는다.
    """
    return _config(
        seed=int(p["seed"]),
        lineup=tuple(p["lineup"]),
        allocations={k: dict(v) for k, v in (p.get("allocations") or {}).items()},
        classes=dict(p.get("classes") or {}),
        genders=dict(p.get("genders") or {}),
        orchestrator=bool(p["orchestrator_on"]),
        adaptation=bool(p["adaptation_on"]),
        missions=MISSIONS_B if p.get("mission_count", 1) == 2 else MISSIONS_A,
    )


def create_app() -> FastAPI:
    """uvicorn 진입점: `uv run uvicorn api.main:create_app --factory`."""
    import os

    from adapters.llm.select import build_harness, model_name_from_env
    from adapters.store.jsonl import JsonlRunStore

    runs_dir = Path(os.environ.get("RPG_RUNS_DIR", "runs"))
    return build_app(
        store=JsonlRunStore(runs_dir),
        model_factory=build_harness,
        model_name=model_name_from_env(),
        experiments_dir=Path(os.environ.get("RPG_EXPERIMENTS_DIR", "eval/out")),
    )
