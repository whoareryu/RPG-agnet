from dataclasses import asdict

import pytest

from adapters.harness.harness import Harness
from adapters.llm.fake import FakeModel
from content.missions import MISSIONS_A
from content.party import build_party
from core.rules.dice import SeededDice
from core.runner import run
from core.types import RunConfig


def _config(
    seed=1, lineup=("garret", "elaine", "kyle"), orchestrator=True, adaptation=True, classes=None
):
    return RunConfig(
        seed=seed,
        lineup=tuple(lineup),
        allocations={},
        classes=classes or {},
        genders={},
        orchestrator_on=orchestrator,
        adaptation_on=adaptation,
        missions=MISSIONS_A,
        intermission=False,
    )


def _run(config, run_id="r"):
    return run(
        run_id,
        config,
        build_party(config),
        model_factory=lambda: Harness(FakeModel(), FakeModel()),
        dice_factory=SeededDice,
        clock=lambda: "T",
    )


def _strip_ts(events):
    return [{k: v for k, v in asdict(e).items() if k != "ts"} for e in events]


def test_A단계_한_판이_30턴_안에_끝난다():
    rec = _run(_config())
    res = rec.results[0]
    assert res.outcome in ("win", "lose", "retreat", "draw") and res.turns <= 30
    kinds = [e.kind for e in rec.events]
    assert kinds[0] == "run_start" and kinds[-1] == "run_end"
    assert "mission_start" in kinds and "mission_end" in kinds and "plan" in kinds


def test_같은_시드는_같은_트레이스를_만든다():
    """리플레이·실험의 전제(설계 §3.4). ts 만 빼고 바이트 단위로 같다."""
    a = _run(_config(seed=7))
    b = _run(_config(seed=7))
    assert _strip_ts(a.events) == _strip_ts(b.events)


def test_다른_시드는_다른_판을_만든다():
    outcomes = {(_run(_config(seed=s)).results[0].turns) for s in range(1, 8)}
    assert len(outcomes) > 1


def test_감독_OFF_면_plan_이벤트가_없다():
    rec = _run(_config(orchestrator=False))
    assert not [e for e in rec.events if e.kind == "plan"]
    assert rec.results[0].plans == 0


def test_호출_수는_상한_안이고_mission_end_에_남는다():
    rec = _run(_config())
    end = [e for e in rec.events if e.kind == "mission_end"][0]
    assert 0 < end.payload["calls_used"] <= 300


@pytest.mark.parametrize("seed", range(1, 41))
def test_어느_시드든_예외_없이_끝난다(seed):
    rec = _run(_config(seed=seed, lineup=("garret", "seraphine", "thomas")))
    assert rec.results[0].outcome in ("win", "lose", "retreat", "draw")


def test_후퇴가_실제로_발생하는_시드가_있다():
    """기획서 §5 — 무조건 싸우는 게임이 아니다. 포기 판단이 트레이스에 남아야 한다."""
    found = None
    for seed in range(1, 60):
        rec = _run(_config(seed=seed, lineup=("thomas", "kyle", "seraphine")))
        if rec.results[0].abandoned:
            found = rec
            break
    assert found is not None, "60개 시드에서 후퇴가 한 번도 없다 — 승산 붕괴가 감독에게 닿지 않는다"
    kinds = [e.kind for e in found.events]
    assert "abandon" in kinds and "replan_trigger" in kinds
    assert found.results[0].outcome in ("retreat", "lose", "draw", "win")


def test_출전_인원이_맞지_않으면_거부한다():
    with pytest.raises(ValueError, match="3~3명"):
        build_party(_config(lineup=("garret", "elaine")))


def test_같은_캐릭터_중복_출전은_거부한다():
    with pytest.raises(ValueError):
        build_party(_config(lineup=("garret", "garret", "kyle")))


def test_트롤픽_전사_셋도_돈다():
    cfg = _config(
        lineup=("seraphine", "elaine", "thomas"),
        classes={"seraphine": "warrior", "elaine": "warrior", "thomas": "warrior"},
    )
    rec = _run(cfg)
    assert rec.results[0].outcome in ("win", "lose", "retreat", "draw")
    start = rec.events[0].payload
    assert all(r["class"] == "warrior" for r in start["roster"])
