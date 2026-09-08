from dataclasses import replace

from content.classes import choose_build
from content.environments import MINE, SWAMP
from content.monsters import VARGAS
from content.roster import PRESET_ALLOCATIONS, ROSTER_BY_ID
from core.battle.state import Battle, unit_from_character, unit_from_enemy
from core.judgment.compliance import deviation_probability, judge_compliance
from core.judgment.odds import odds
from core.judgment.replan import (
    ReplanState,
    mark_quiet_turn,
    mark_replanned,
    replan_triggers,
)
from core.judgment.visibility import visible_context, wis_tier
from core.rules.dice import FixedDice
from core.rules.stats import allocate
from core.types import Plan


def _char(cid: str, **stat_override):
    c = ROSTER_BY_ID[cid]
    c = replace(c, stats=allocate(c.stats, PRESET_ALLOCATIONS[cid]))
    if stat_override:
        c = replace(c, stats=replace(c.stats, **stat_override))
    return c


def _battle(env=SWAMP, party=("garret", "elaine", "kyle"), **overrides):
    units = {}
    for cid in party:
        c = _char(cid, **overrides.get(cid, {}))
        units[cid] = unit_from_character(c, choose_build(c), "party", "front")
    for e in VARGAS.units:
        units[e.id] = unit_from_enemy(e, "enemy")
    return Battle(seed=1, environment=env, units=units, enemy_def=VARGAS)


PLAN = Plan("평가", True, "rush", {}, "vargas", {}, 0.30, "이유")


# ─── 지혜 마스킹 ──────────────────────────────────────────────────────


def test_지혜_단계는_설계_표와_같다():
    assert [wis_tier(w, SWAMP) for w in (7, 8, 12, 13, 16, 17, 20)] == [0, 1, 1, 2, 2, 3, 3]


def test_어둠은_한_단계_내린다():
    assert wis_tier(13, MINE) == 1 and wis_tier(5, MINE) == 0


def test_지혜가_낮으면_아군_상태가_가려진다():
    b = _battle(kyle={"wis": 5})
    visible, masked, tier = visible_context(b, "kyle", PLAN, 0.6)
    assert tier == 0
    assert "allies" not in visible and "allies" in masked
    assert "enemy_pattern" in masked and "plan_intent" in masked and "odds" in masked
    assert visible["self"]["hp"] and visible["enemies_basic"][0]["id"] == "vargas"
    assert "hp" not in visible["enemies_basic"][0]


def test_지혜가_높으면_전부_보인다():
    b = _battle(seraphine={"wis": 18}, party=("garret", "elaine", "seraphine"))
    visible, masked, tier = visible_context(b, "seraphine", PLAN, 0.6)
    assert tier == 3 and masked == []
    assert visible["plan_intent"]["strategy"] == "rush" and visible["odds"] == 0.6
    assert {a["id"] for a in visible["allies"]} == {"garret", "elaine"}


def test_같은_상황_두_캐릭터의_입력이_다르다():
    """기획서 §15 "지혜 높으면 뭐가 달라져요" — 입력 컨텍스트 비교."""
    b = _battle(garret={"wis": 5}, elaine={"wis": 15})
    _, m1, _ = visible_context(b, "garret", PLAN, 0.5)
    _, m2, _ = visible_context(b, "elaine", PLAN, 0.5)
    assert len(m1) > len(m2)


# ─── 승산 ─────────────────────────────────────────────────────────────


def test_승산은_범위_안이고_대칭이다():
    b = _battle()
    a, _ = odds(b, "party")
    e, _ = odds(b, "enemy")
    assert 0.05 <= a <= 0.95 and abs(a + e - 1) < 0.01


def test_전력이_없는_진영의_승산은_바닥이다():
    b = _battle()
    for cid in ("garret", "elaine", "kyle"):
        b.units[cid].alive = False
    v, _ = odds(b, "party")
    assert v == 0.05


def test_힐러가_있으면_시너지가_붙는다():
    with_healer = _battle(party=("garret", "elaine", "kyle"))
    without = _battle(party=("garret", "seraphine", "kyle"))
    _, bd1 = odds(with_healer, "party")
    _, bd2 = odds(without, "party")
    assert bd1["mine"]["synergy"] == 1.15 and bd2["mine"]["synergy"] == 1.0


def test_HP_가_줄면_승산이_내려간다():
    b = _battle()
    full, _ = odds(b, "party")
    b.units["garret"].hp = 10
    hurt, _ = odds(b, "party")
    assert hurt < full


# ─── 순응 ─────────────────────────────────────────────────────────────


def test_HP_가_낮을수록_이탈_확률이_오른다():
    b = _battle()
    k = b.units["kyle"]
    ps = []
    for hp in (k.hp_max, k.hp_max // 2, k.hp_max // 5):
        k.hp = hp
        ps.append(deviation_probability(k, b)[0])
    assert ps[0] < ps[1] < ps[2]


def test_희생_수용도가_높을수록_이탈_확률이_내린다():
    b = _battle()
    g, e = b.units["garret"], b.units["elaine"]
    g.hp = e.hp = 20
    assert deviation_probability(e, b)[0] < deviation_probability(g, b)[0]


def test_가장형은_같은_HP_에서_이탈_압력이_높다():
    """카일: 딸 2세(기획서 §9 예시). 생애 가중이 압력에 이름으로 남는다."""
    b = _battle()
    _, bd = deviation_probability(b.units["kyle"], b)
    assert bd["pressure_breakdown"]["life"] == 0.2
    _, bd2 = deviation_probability(b.units["garret"], b)
    assert bd2["pressure_breakdown"]["life"] == 0.0


def test_기획서_9장_시나리오():
    """HP 32%, 힐러 사망, 딸 2세 → 이탈 확률 ~70%."""
    b = _battle()
    k = b.units["kyle"]
    k.hp = round(k.hp_max * 0.32)
    b.units["elaine"].alive = False
    p, _ = deviation_probability(k, b)
    assert 0.6 <= p <= 0.8


def test_판정은_시드_주사위로_결정된다():
    b = _battle()
    k = b.units["kyle"]
    k.hp = 5
    rec = judge_compliance(k, b, FixedDice([1], uniforms=[0.01]))
    assert rec.verdict == "deviate" and rec.roll == 0.01
    rec2 = judge_compliance(k, b, FixedDice([1], uniforms=[0.99]))
    assert rec2.verdict == "comply"


def test_적_유닛은_항상_순응한다():
    b = _battle()
    assert (
        judge_compliance(b.units["vargas"], b, FixedDice([1], uniforms=[0.0])).verdict == "comply"
    )


# ─── 재계획 ───────────────────────────────────────────────────────────


def test_이탈은_재계획을_부른다():
    s = ReplanState()
    s.deviations.append("kyle")
    ts = replan_triggers(s, 0.6, PLAN)
    assert [t.kind for t in ts] == ["deviation"]


def test_승산_붕괴는_첫_진입과_계단마다_한_번씩():
    s = ReplanState()
    assert [t.kind for t in replan_triggers(s, 0.28, PLAN)] == ["odds_collapse"]
    mark_replanned(s, 0.28, PLAN)
    s.begin_turn()
    s.consume_signals()
    assert replan_triggers(s, 0.25, PLAN) == []  # 같은 계단(0.2)
    s.begin_turn()
    s.consume_signals()
    assert [t.kind for t in replan_triggers(s, 0.19, PLAN)] == ["odds_collapse"]  # 0.1 계단


def test_한_턴에_재계획은_한_번이다():
    s = ReplanState()
    mark_replanned(s, 0.6, PLAN)
    s.deviations.append("kyle")
    assert replan_triggers(s, 0.6, PLAN) == []


def test_감독_OFF_면_트리거가_없다():
    s = ReplanState()
    s.deviations.append("kyle")
    assert replan_triggers(s, 0.1, None) == []


def test_연속_재계획_상한을_넘으면_강제_결정():
    s = ReplanState()
    forced = [mark_replanned(s, 0.6, PLAN) for _ in range(4)]
    assert forced == [False, False, False, True]
    mark_quiet_turn(s)
    assert s.consecutive == 0
