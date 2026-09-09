from pathlib import Path

from apps.arena.adapter.outbound.repositories.jsonl_run_repository import JsonlRunStore
from apps.arena.adapter.outbound.strategies.dice import SeededDice
from apps.arena.adapter.outbound.strategies.harness.harness import Harness
from apps.arena.adapter.outbound.strategies.llm.fake import FakeModel
from apps.arena.adapter.outbound.strategies.llm.replay import ReplayModel
from apps.arena.adapter.outbound.strategies.llm.select import build_harness, build_model
from apps.arena.app.use_cases.runner import run
from apps.arena.domain.entities.trace_event import KINDS, from_json, judgment_view
from apps.arena.domain.entities.types import RunConfig
from content.missions import MISSIONS_A
from content.party import build_party

# apps/arena/tests/adapter/ → 저장소 루트까지 다섯 단계다.
SAMPLE = Path(__file__).resolve().parents[5] / "docs" / "trace-samples" / "one-run.jsonl"


def _cfg(seed=3):
    return RunConfig(
        seed=seed,
        lineup=("agnes", "thoma", "gilles"),
        allocations={},
        classes={},
        genders={},
        orchestrator_on=True,
        adaptation_on=True,
        missions=MISSIONS_A,
        intermission=False,
    )


def _run(cfg, model_factory=lambda: Harness(FakeModel(), FakeModel())):
    return run("r1", cfg, build_party(cfg), model_factory, SeededDice, clock=lambda: "T")


def _strip(events):
    return [judgment_view(e) for e in events]


def _strip_model(events):
    """판단 내용만 본다 — 누가 답했는지(fake vs replay)는 뺀다.

    결정론 비교(_strip)와 다른 질문이다: "리플레이가 같은 판단을 냈는가".
    """
    out = []
    for d in _strip(events):
        d["payload"] = {k: v for k, v in d["payload"].items() if k != "model"}
        out.append(d)
    return out


def test_저장_후_불러오면_같다(tmp_path):
    store = JsonlRunStore(tmp_path)
    rec = _run(_cfg())
    store.save(rec)
    loaded = store.load("r1")
    assert loaded is not None
    assert _strip(loaded.events) == _strip(rec.events)
    assert loaded.results[0].outcome == rec.results[0].outcome
    assert loaded.config["seed"] == 3


def test_없는_런은_None_이고_이상한_id_는_거부한다(tmp_path):
    store = JsonlRunStore(tmp_path)
    assert store.load("nope") is None
    import pytest

    with pytest.raises(ValueError):
        store.load("../etc/passwd")


def test_최근_목록은_요약만_읽는다(tmp_path):
    store = JsonlRunStore(tmp_path)
    store.save(_run(_cfg(1)))
    rows = store.list_recent(5)
    assert rows[0]["run_id"] == "r1" and rows[0]["lineup"] == ["agnes", "thoma", "gilles"]


def test_리플레이는_모델_호출_없이_같은_판을_재생한다():
    """기획서 §11.3 — 데모에서 AI 를 안 부르고 안정적으로 보여준다."""
    original = _run(_cfg())

    class 부르면안됨:
        name = "boom"

        def decide(self, *a):
            raise AssertionError("리플레이 중에 모델을 불렀다")

    replay = ReplayModel(original.events, fallback=부르면안됨())
    again = _run(_cfg(), model_factory=lambda: Harness(replay, 부르면안됨()))
    assert _strip_model(again.events) == _strip_model(original.events)
    assert replay.exhausted == 0


def test_녹화가_바닥나면_폴백으로_간다():
    original = _run(_cfg())
    replay = ReplayModel(original.events, fallback=FakeModel())
    other = _run(_cfg(seed=9), model_factory=lambda: Harness(replay, FakeModel()))
    assert other.results[0].outcome in ("win", "lose", "retreat", "draw")


def test_기본_모델은_fake_이고_하네스를_거친다(monkeypatch):
    monkeypatch.delenv("RPG_MODEL", raising=False)
    assert build_model().name == "fake"
    h = build_harness()
    assert h.name == "fake" and h.calls_used == 0


def test_샘플_트레이스는_계약을_지킨다():
    """docs/trace-samples/one-run.jsonl — 프론트 lib/trace.test.ts 가 같은 파일을 읽는다."""
    assert SAMPLE.exists(), "scripts/make_trace_sample.py 를 돌려 샘플을 만든다"
    lines = SAMPLE.read_text(encoding="utf-8").splitlines()
    events = [from_json(line) for line in lines]
    assert events[0].kind == "run_start" and events[-1].kind == "run_end"
    assert {e.kind for e in events} <= KINDS
    assert [e.seq for e in events] == list(range(1, len(events) + 1))
    # 데모 하이라이트가 샘플에 있어야 화면 개발이 된다
    kinds = {e.kind for e in events}
    assert {"plan", "context", "compliance", "decision", "resolution", "odds"} <= kinds
    assert {"abandon", "replan_trigger", "boss_adapt", "flee"} <= kinds
    assert any(e.kind == "compliance" and e.payload["verdict"] == "deviate" for e in events)
