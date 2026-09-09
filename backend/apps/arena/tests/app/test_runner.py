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


def _run(config, run_id="r", horn=None, recovery=None):
    return run(
        run_id,
        config,
        build_party(config),
        model_factory=lambda: Harness(FakeModel(), FakeModel()),
        dice_factory=SeededDice,
        clock=lambda: "T",
        horn=horn,
        recovery=recovery,
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


# ─── 뿔피리 (기획서 v3 §8.2) ────────────────────────────────────────────


def _horn_at(turn: int):
    """지정한 턴에 한 번만 울리는 뿔피리. 세션의 큐를 흉내낸다."""
    state = {"blown": False}

    def horn(battle_turn: int) -> bool:
        if battle_turn >= turn and not state["blown"]:
            state["blown"] = True
            return True
        return False

    return horn


def test_뿔피리를_불면_그_자리에서_판이_끝난다():
    """기획서 v3 §8.2 — 즉시 이탈. 전멸은 피하지만 목표는 실패하고 보수는 없다."""
    rec = _run(_config(seed=3), horn=_horn_at(2))
    res = rec.results[0]
    assert res.outcome == "retreat"
    assert res.turns <= 3, "뿔피리를 불었는데 판이 계속됐다"
    assert [e.kind for e in rec.events].count("horn") == 1


def test_뿔피리로_끝난_판은_철수지_실패가_아니다():
    """「철수」가 벌점이 아닌 것이 핵심이다(기획서 v3 §7.1b)."""
    rec = _run(_config(seed=3), horn=_horn_at(2))
    assert rec.results[0].grade == "withdraw"


def test_뿔피리를_불지_않으면_판이_그대로_돈다():
    없음 = _run(_config(seed=3))
    불었다 = _run(_config(seed=3), horn=_horn_at(2))
    assert 없음.results[0].turns > 불었다.results[0].turns


def test_뿔피리는_전원을_살려_내보낸다():
    rec = _run(_config(seed=3), horn=_horn_at(2))
    res = rec.results[0]
    assert not res.dead and not res.taken, "뿔피리를 불었는데 사람을 잃었다"
    assert len(res.fled) == 3


# ─── 보스 호칭 (기획서 v3 §8.5) ─────────────────────────────────────────


def test_첫_끌려감이_보스의_이름이_된다():
    """대원들은 그것이 처음 데려간 사람의 이름으로 그것을 부른다."""
    from dataclasses import replace as _replace

    from content.missions import MISSIONS_A

    # 지원 둘만 보내면 화력이 없어 실제로 쓰러진다 — 조합은 유저의 시험 문제다.
    여름 = tuple(_replace(m, casualty_tier="summer") for m in MISSIONS_A)
    for seed in range(1, 80):
        cfg = _replace(_config(seed=seed, lineup=("aude", "agnes")), missions=여름)
        rec = _run(cfg)
        끌려간 = [t for r in rec.results for t in r.taken]
        if not 끌려간:
            continue
        named = [e for e in rec.events if e.kind == "boss_named"]
        assert len(named) == 1, "호칭은 첫 끌려감에 한 번만 붙는다"
        assert named[0].payload["after"].endswith("데려간 것")
        assert named[0].payload["member"] == 끌려간[0]
        assert rec.boss_title == named[0].payload["after"]
        return
    raise AssertionError("끌려감이 나오는 시드를 찾지 못했다 — 이 테스트가 아무것도 재지 않는다")


def test_호칭이_붙으면_보스가_그_이름으로_선다():
    """호칭이 실제로 유닛에 입혀지는지 본다.

    "1판에서 끌려가고 2판이 도는" 시드를 찾는 방식은 쓰지 않는다 — 야습이
    충분히 쉬워 그런 시드가 없고, 있더라도 밸런스가 바뀌면 테스트가 조용히
    공허해진다. 적용 자체를 직접 잰다.
    """
    from apps.arena.app.use_cases.runner import setup_battle
    from content.missions import MISSION_JUVENILE_BOSS

    members = build_party(_config())
    호칭 = "토마를 데려간 것"
    b = setup_battle(MISSION_JUVENILE_BOSS, members, seed=1, adaptation_on=True, boss_title=호칭)
    보스 = [u for u in b.units.values() if u.is_boss]
    assert len(보스) == 1 and 보스[0].name == 호칭

    # 호칭이 없으면 원래 이름 그대로다.
    b2 = setup_battle(MISSION_JUVENILE_BOSS, members, seed=1, adaptation_on=True)
    assert [u for u in b2.units.values() if u.is_boss][0].name == "굴의 그것"


# ─── 회수 결정 (기획서 v3 §6.8) ─────────────────────────────────────────


def _taken_run(decide=None, seeds=range(1, 80)):
    """끌려감이 실제로 나오는 판 하나를 찾아 돌린다."""
    from dataclasses import replace as _replace

    from content.missions import MISSIONS_A

    여름 = tuple(_replace(m, casualty_tier="summer") for m in MISSIONS_A)
    for seed in seeds:
        cfg = _replace(_config(seed=seed, lineup=("aude", "agnes")), missions=여름)
        rec = _run(cfg, recovery=decide)
        if any(r.taken for r in rec.results):
            return rec
    raise AssertionError("끌려감이 나오는 시드를 찾지 못했다 — 이 테스트가 아무것도 재지 않는다")


def test_결정하지_않으면_미지불로_영구_상실이다():
    """기한을 넘기면 자동 미지불이다(기획서 v3 §6.8)."""
    rec = _taken_run()
    res = next(r for r in rec.results if r.taken)
    assert res.recovery_unpaid == res.taken and res.recovery_paid == ()
    assert set(rec.forsaken) == set(res.taken), "미지불이 「섭식」 대상으로 남지 않았다"


def test_지불하면_섭식_대상에서_빠진다():
    """지불의 값이 여기서 생긴다 — 보스가 그 사람에게서 배우지 못한다(§8.4)."""
    rec = _taken_run(decide=lambda ids, costs: set(ids))
    res = next(r for r in rec.results if r.taken)
    assert res.recovery_paid == res.taken and res.recovery_unpaid == ()
    assert rec.forsaken == ()


def test_회수_결정이_비용과_함께_트레이스에_남는다():
    rec = _taken_run()
    ev = [e for e in rec.events if e.kind == "recovery"]
    assert ev, "회수 결정이 트레이스에 없다"
    p = ev[0].payload
    assert p["member"] and p["paid"] is False and isinstance(p["cost"], int)


# ─── 학습 카드 (기획서 v3 §8.4) ─────────────────────────────────────────


def _card_run(seed=3, **over):
    from content.cards import CARDS

    return run(
        "r",
        _config(seed=seed, **over),
        build_party(_config(seed=seed, **over)),
        model_factory=lambda: Harness(FakeModel(), FakeModel()),
        dice_factory=SeededDice,
        clock=lambda: "T",
        card_pool=CARDS,
    )


def test_보스전에서만_카드가_펼쳐진다():
    """일반전은 카드를 안 쓴다. 슬롯이 보스 형태에만 있다."""
    rec = _card_run()
    카드들 = [e for e in rec.events if e.kind == "cards"]
    assert len(카드들) == 1, "카드가 보스전 말고 다른 데서도 펼쳐졌다"
    보스_시작 = [e for e in rec.events if e.kind == "mission_start"][1]
    assert 카드들[0].seq > 보스_시작.seq


def test_카드는_출처와_관측을_들고_온다():
    """인스펙터가 출처를 가리킬 수 있어야 한다 — 그러지 않으면 그냥 표시다."""
    rec = _card_run()
    cards = [e for e in rec.events if e.kind == "cards"][0].payload["cards"]
    assert cards, "보스전인데 카드가 하나도 없다"
    for c in cards:
        assert c["source"] in ("scout", "flight", "loot", "feeding")
        assert c["observation"] and "{" not in c["observation"], c
        assert c["applied"], f"카드가 아무것도 안 했다: {c}"


def test_카드는_슬롯을_넘지_않는다():
    from apps.arena.domain.constants.balance import CARD_SLOTS

    rec = _card_run()
    cards = [e for e in rec.events if e.kind == "cards"][0].payload["cards"]
    assert len(cards) <= CARD_SLOTS["boss_juvenile"]


def test_같은_시드는_같은_카드를_낸다():
    a = [e for e in _card_run().events if e.kind == "cards"][0].payload["cards"]
    b = [e for e in _card_run().events if e.kind == "cards"][0].payload["cards"]
    assert [c["key"] for c in a] == [c["key"] for c in b]
