import pytest

from apps.arena.adapter.outbound.strategies.dice import SeededDice
from apps.arena.adapter.outbound.strategies.harness.harness import Harness
from apps.arena.adapter.outbound.strategies.llm.fake import FakeModel
from apps.arena.app.use_cases.runner import run
from apps.arena.domain.entities.trace_event import judgment_view
from apps.arena.domain.entities.types import RunConfig
from content.missions import MISSIONS_A
from content.party import build_party


def _config(
    seed=1, lineup=("martin", "aude", "thoma"), orchestrator=True, adaptation=True, classes=None
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
    return [judgment_view(e) for e in events]


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
    rec = _run(_config(seed=seed, lineup=("martin", "gilles", "agnes")))
    assert rec.results[0].outcome in ("win", "lose", "retreat", "draw")


def test_후퇴가_실제로_발생하는_시드가_있다():
    """기획서 §5 — 무조건 싸우는 게임이 아니다. 포기 판단이 트레이스에 남아야 한다."""
    found = None
    for seed in range(1, 120):
        # 지원 둘만 보내면 화력이 없어 승산이 무너진다 — 조합은 유저의 시험 문제다(§8.1).
        rec = _run(_config(seed=seed, lineup=("aude", "agnes")))
        if any(r.abandoned for r in rec.results):
            found = rec
            break
    assert found is not None, (
        "120개 시드에서 후퇴가 한 번도 없다 — 승산 붕괴가 감독에게 닿지 않는다"
    )
    kinds = [e.kind for e in found.events]
    assert "abandon" in kinds and "replan_trigger" in kinds
    assert all(r.outcome in ("retreat", "lose", "draw", "win") for r in found.results)


def test_출전_인원_상한을_넘으면_거부한다():
    """하한은 1 이다 — 혼자 가는 것도 단주의 선택(기획서 §7.2·§8.1)."""
    build_party(_config(lineup=("martin",)))
    build_party(_config(lineup=("martin", "aude")))
    with pytest.raises(ValueError, match="1~3명"):
        build_party(_config(lineup=("martin", "aude", "thoma", "agnes")))


def test_같은_캐릭터_중복_출전은_거부한다():
    with pytest.raises(ValueError):
        build_party(_config(lineup=("martin", "martin", "thoma")))


def test_트롤픽_전사_셋도_돈다():
    cfg = _config(
        lineup=("gilles", "aude", "agnes"),
        classes={"gilles": "warrior", "aude": "warrior", "agnes": "warrior"},
    )
    rec = _run(cfg)
    assert rec.results[0].outcome in ("win", "lose", "retreat", "draw")
    start = rec.events[0].payload
    assert all(r["class"] == "warrior" for r in start["roster"])


# ─── QA 라운드 1 회귀 ──────────────────────────────────────────────────


def test_이탈과_적응이_실제로_재계획을_부른다():
    """기획서 §8.3 의 트리거 4종 중 둘이 죽어 있었다(QA 라운드 1 P0-1).

    신호는 턴 안에서 쌓이고 다음 턴 시작에 읽힌다 — 읽기 전에 비우면 안 된다.
    """
    kinds = set()
    for seed in range(1, 12):
        rec = _run(_config(seed=seed))
        kinds |= {e.payload["trigger"] for e in rec.events if e.kind == "replan_trigger"}
    assert "deviation" in kinds, "이탈이 재계획을 부르지 않는다"
    assert "adaptation" in kinds, "보스 적응이 재계획을 부르지 않는다"


def test_30턴까지_모든_유닛이_행동한다():
    """QA 라운드 1 P1-4 — 턴 상한을 유닛 루프 안에서 보면 마지막 턴이 잘린다."""
    for seed in range(1, 200):
        rec = _run(_config(seed=seed))
        if rec.results[0].outcome != "draw":
            continue
        last = max(e.turn for e in rec.events)
        order = [e for e in rec.events if e.kind == "turn_start" and e.turn == last][0]
        차례 = [o["unit"] for o in order.payload["order"]]
        acted = {e.actor for e in rec.events if e.kind == "resolution" and e.turn == last}
        # 자기 차례 전에 쓰러지거나 빠져나간 유닛은 행동하지 못한다 — 그건 정상이다.
        사라짐: set[str] = set()
        for e in rec.events:
            if e.turn != last:
                continue
            if e.kind == "resolution":
                for st in e.payload["strikes"]:
                    if st["killed"]:
                        사라짐.add(st["target"])
                if e.payload.get("flee_success"):
                    사라짐.add(e.actor)
        기대 = [u for u in 차례 if u not in 사라짐 - acted]
        assert acted >= set(기대) - 사라짐, f"seed {seed}: 마지막 턴이 잘렸다"
        assert len(acted) >= len(차례) - len(사라짐), f"seed {seed}: 마지막 턴이 잘렸다"
        return
    raise AssertionError("무승부 시드를 찾지 못했다 — 이 테스트가 아무것도 재지 않는다")


def test_전사는_실제로_적을_친다():
    """QA 라운드 1 P0-4 — Fake 가 스킬 목록 첫 번째를 골라 자기 방어만 했다."""
    total = 0
    for seed in range(1, 6):
        rec = _run(_config(seed=seed))
        total += sum(
            s["damage"]
            for e in rec.events
            if e.kind == "resolution" and e.actor == "martin"
            for s in e.payload["strikes"]
        )
    assert total > 0, "전사가 다섯 판 동안 아무에게도 피해를 주지 못했다"


def test_봄에는_아무도_죽지_않는다():
    """기획서 v3 §6.0 — 1~4 출동 사망 0%. 고블린은 죽이기보다 끌고 간다.

    A단계 미션은 6·5회차라 봄이 아니다(2026-09-08 팀 결정 ①). 봄 구간을
    직접 만들어 확률표의 0% 가 실제로 지켜지는지 잰다.
    """
    from dataclasses import replace as _replace

    from content.environments import SWAMP
    from content.missions import MISSION_NIGHT_RAID
    from content.monsters import GOBLIN_BAND

    봄 = (
        _replace(
            MISSION_NIGHT_RAID,
            no=1,
            name="마을 방어",
            enemy=GOBLIN_BAND,
            environment=SWAMP,
            casualty_tier="spring",
        ),
    )
    쓰러진_적_있다 = False
    for seed in range(1, 40):
        cfg = _replace(_config(seed=seed, lineup=("thoma", "aude")), missions=봄)
        rec = _run(cfg)
        for res in rec.results:
            assert not res.dead, f"seed {seed}: 봄인데 {res.dead} 가 죽었다"
            쓰러진_적_있다 = 쓰러진_적_있다 or bool(res.injured or res.taken)
    assert 쓰러진_적_있다, "아무도 쓰러지지 않아 이 테스트가 아무것도 재지 않는다"


def test_사망하거나_끌려간_단원은_다음_판에_나오지_않는다():
    """사망은 소멸이고(기획서 §6.6), 끌려간 사람은 굴에 있다(v3 §6.8)."""
    from dataclasses import replace as _replace

    from content.missions import MISSIONS_B

    # 가을 구간(사망 20%)으로 바꿔 실제로 잃는 판을 만든다.
    가을 = tuple(_replace(m, casualty_tier="autumn") for m in MISSIONS_B)
    for seed in range(1, 60):
        cfg = _replace(_config(seed=seed, lineup=("thoma", "aude")), missions=가을)
        rec = _run(cfg)
        빠진_사람 = set(rec.results[0].dead) | set(rec.results[0].taken)
        if len(rec.results) < 2 or not 빠진_사람:
            continue
        second = [e for e in rec.events if e.kind == "mission_start"][1]
        나온_사람 = {p["id"] for p in second.payload["party"]}
        assert not (빠진_사람 & 나온_사람), (
            f"seed {seed}: {빠진_사람 & 나온_사람} 이(가) 2판에 섰다"
        )
        return
    raise AssertionError(
        "1판에 사망·끌려감이 나오는 시드를 찾지 못했다 — 이 테스트가 아무것도 재지 않는다"
    )
