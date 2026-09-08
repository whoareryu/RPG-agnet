from dataclasses import replace

from apps.arena.adapter.outbound.strategies.dice import FixedDice
from apps.arena.domain.services.battle.order import turn_order
from apps.arena.domain.services.battle.state import Battle, unit_from_character, unit_from_enemy
from apps.arena.domain.services.rules.combat import damage, flee_chance, hit_chance, speed
from apps.arena.domain.services.rules.stats import allocate
from content.classes import choose_build
from content.environments import MINE, SWAMP
from content.monsters import VARGAS
from content.roster import PRESET_ALLOCATIONS, ROSTER_BY_ID


def _char(cid: str, **stat_override):
    c = ROSTER_BY_ID[cid]
    c = replace(c, stats=allocate(c.stats, PRESET_ALLOCATIONS[cid]))
    if stat_override:
        c = replace(c, stats=replace(c.stats, **stat_override))
    return c


def _battle(env=MINE, party=("garret", "bern", "kyle"), **overrides):
    units = {}
    for cid in party:
        c = _char(cid, **overrides.get(cid, {}))
        units[cid] = unit_from_character(c, choose_build(c), "party", "front")
    for e in VARGAS.units:
        units[e.id] = unit_from_enemy(e, "enemy")
    return Battle(seed=1, environment=env, units=units, enemy_def=VARGAS)


def test_명중은_기본_60에_민첩차를_더한다():
    b = _battle()
    needed, bd = hit_chance(b.units["kyle"], b.units["vargas"], MINE)
    # 카일 AGI 16 vs 바르가스 9 → +14. 카일 LCK 10 → 0. 전열이라 거리 페널티 없음.
    assert needed == 74
    assert ("민첩 차", 14) in bd


def test_후열_원거리는_폐광에서_거리_페널티를_받는다():
    b = _battle()
    b.units["kyle"].position = "back"
    needed, bd = hit_chance(b.units["kyle"], b.units["vargas"], MINE)
    assert needed == 64
    assert ("환경 폐광 거리", -10) in bd


def test_행운은_굴림에만_소폭_걸린다():
    """기획서 §4.2 — LCK 20 과 1 의 차는 (20-1)×0.5 ≈ 9~10%."""
    hi = _battle(kyle={"luck": 20})
    lo = _battle(kyle={"luck": 1})
    a, _ = hit_chance(hi.units["kyle"], hi.units["vargas"], MINE)
    c, _ = hit_chance(lo.units["kyle"], lo.units["vargas"], MINE)
    assert 9 <= a - c <= 10


def test_명중은_5와_95_사이로_잘린다():
    b = _battle(kyle={"agi": 20})
    b.units["vargas"].stats = replace(b.units["vargas"].stats, agi=1)
    needed, _ = hit_chance(b.units["kyle"], b.units["vargas"], MINE)  # 60 + 38 = 98 → 95
    assert needed == 95
    lo = _battle(kyle={"agi": 1})
    lo.units["vargas"].stats = replace(lo.units["vargas"].stats, agi=20)
    from apps.arena.domain.services.battle.state import Status

    lo.units["kyle"].statuses.append(Status("blind", 2, 15))
    needed, _ = hit_chance(lo.units["kyle"], lo.units["vargas"], MINE)  # 60 - 38 - 15 = 7
    assert needed == 7


def test_방어_태세는_피해를_절반으로():
    b = _battle()
    full, _ = damage(b.units["vargas"], b.units["garret"], MINE, None, crit=False)
    b.units["garret"].defending = True
    half, bd = damage(b.units["vargas"], b.units["garret"], MINE, None, crit=False)
    assert half == round(full * 0.5) or abs(half * 2 - full) <= 1
    assert ("방어 태세", 0.5) in bd


def test_늪지는_마법_피해를_줄인다():
    """마법 피해원은 음유시인의 북·류트다 — 마법사가 사라진 뒤로(설계 2026-09-08)."""
    b = _battle(env=SWAMP, party=("garret", "elaine", "kyle"))
    d_swamp, bd = damage(b.units["elaine"], b.units["vargas"], SWAMP, None, crit=False)
    d_mine, _ = damage(b.units["elaine"], b.units["vargas"], MINE, None, crit=False)
    assert d_swamp < d_mine
    assert ("환경 늪지 magic", 0.8) in bd


def test_치명타는_1_5배():
    b = _battle()
    n, _ = damage(b.units["garret"], b.units["vargas"], MINE, None, crit=False)
    c, _ = damage(b.units["garret"], b.units["vargas"], MINE, None, crit=True)
    assert abs(c - n * 1.5) <= 1


def test_늪지에서_중갑은_느려진다():
    b = _battle(env=SWAMP)
    v, bd = speed(b.units["garret"], SWAMP)
    assert ("환경 늪지", -2) in bd
    v2, _ = speed(b.units["garret"], MINE)
    assert v == v2 - 2


def test_행동_순서는_속도_내림차순이고_시드에_결정된다():
    b = _battle()
    o1 = [r[0] for r in turn_order(b, FixedDice([1]))]
    o2 = [r[0] for r in turn_order(b, FixedDice([1]))]
    assert o1 == o2
    assert o1[0] == "kyle"  # AGI 16


def test_도망_성공률은_적_최고_민첩과의_차다():
    b = _battle()
    needed, _ = flee_chance(b.units["kyle"], [b.units["vargas"]])
    assert needed == 50 + (16 - 9) * 3
