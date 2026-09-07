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
from content.missions import MISSIONS_A, MISSIONS_B
from content.party import apply_direction, build_party
from content.roster import PRESET_ALLOCATIONS, PRESET_ROSTER
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
        self.directives: queue.Queue[DirectivesRequest] = queue.Queue()

    def emit(self, event: TraceEvent) -> None:
        self.events.append(event)
        self.queue.put(event)


def build_app(
    store: RunStore,
    model_factory: Callable[[], DecisionModel],
    model_name: str = "fake",
    intermission_factory: Callable[[RunSession], Any] | None = None,
    e1_path: Path | None = None,
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
    def directives(run_id: str, req: DirectivesRequest) -> dict[str, str]:
        session = sessions.get(run_id)
        if session is None:
            raise HTTPException(status_code=404, detail="진행 중인 런이 아니다")
        session.directives.put(req)
        return {"status": "accepted"}

    @app.get("/runs", dependencies=guard)
    def recent(limit: int = 20) -> dict[str, Any]:
        return {"runs": store.list_recent(min(limit, 50))}

    @app.get("/experiments/e1", dependencies=guard)
    def e1() -> dict[str, Any]:
        if e1_path is None or not e1_path.exists():
            raise HTTPException(
                status_code=404, detail="E1 결과가 아직 없다. eval.run --experiment e1 을 돌린다"
            )
        return json.loads(e1_path.read_text(encoding="utf-8"))

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
                intermission = intermission_factory(session) if intermission_factory else None
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
    """run_start payload → RunConfig. 리플레이는 같은 설정이어야 같은 질문이 나온다."""
    roster = {r["id"]: r for r in p.get("roster", [])}
    classes = {cid: r["class"] for cid, r in roster.items()}
    allocations = {
        cid: {k: v - STAT_BASE for k, v in r["stats"].items() if v - STAT_BASE > 0}
        for cid, r in roster.items()
    }
    return _config(
        seed=int(p["seed"]),
        lineup=tuple(p["lineup"]),
        allocations=allocations,
        classes=classes,
        genders={},
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
    e1 = Path(os.environ.get("RPG_E1_PATH", "eval/out/e1.json"))
    return build_app(
        store=JsonlRunStore(runs_dir),
        model_factory=build_harness,
        model_name=model_name_from_env(),
        e1_path=e1,
    )
