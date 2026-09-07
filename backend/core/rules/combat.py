"""판정 함수 — 순수 (설계 §5.4). 주사위를 굴리지 않는다. "필요한 값"과 그 내역을 돌려준다.

내역(breakdown)이 항상 붙는 이유: 인스펙터가 "명중 62% = 기본 60 + 민첩차 +6
- 무게 미달 -10 + 축복 +10 - 어둠 -4" 를 보여줘야 한다(기획서 §9).
"""

from core.battle.state import UnitState
from core.rules.constants import (
    ARMOR_SCALE,
    CRIT_BASE,
    CRIT_MULT,
    DEFEND_MULT,
    FLEE_BASE,
    FLEE_PER_AGI_DIFF,
    HIT_BASE,
    HIT_MAX,
    HIT_MIN,
    HIT_PER_AGI_DIFF,
    INT_DAMAGE_COEF,
    LUCK_NEUTRAL,
    LUCK_ROLL_BONUS,
    STR_DAMAGE_COEF,
)
from core.types import Environment, SkillDef

Breakdown = list[tuple[str, float]]


def _luck_bonus(u: UnitState) -> int:
    """행운은 굴림에만 소폭(기획서 §4.2). (LCK-10)×0.5% 를 내림."""
    return int((u.stats.luck - LUCK_NEUTRAL) * LUCK_ROLL_BONUS)


def speed(u: UnitState, env: Environment) -> tuple[int, Breakdown]:
    bd: Breakdown = [("민첩", u.stats.agi)]
    v = u.stats.agi
    for label, m in (("무기", u.weapon_mods), ("갑옷", u.armor_mods)):
        if m.speed:
            bd.append((f"{label} 무게 미달", m.speed))
            v += m.speed
    env_pen = env.speed_penalty_by_weight.get(u.armor.weight_class, 0)
    if env_pen:
        bd.append((f"환경 {env.name}", env_pen))
        v += env_pen
    slow = u.status("slow")
    if slow:
        bd.append(("둔화", -slow.value))
        v -= int(slow.value)
    return v, bd


def hit_chance(
    attacker: UnitState, defender: UnitState, env: Environment, skill: SkillDef | None = None
) -> tuple[int, Breakdown]:
    bd: Breakdown = [("기본", HIT_BASE)]
    v = HIT_BASE
    diff = (attacker.stats.agi - defender.stats.agi) * HIT_PER_AGI_DIFF
    bd.append(("민첩 차", diff))
    v += diff
    for label, m in (("무기", attacker.weapon_mods), ("갑옷", attacker.armor_mods)):
        if m.hit:
            bd.append((f"{label} 효율", m.hit))
            v += m.hit
    if (
        attacker.position == "back"
        and env.range_penalty
        and not (skill and skill.effect == "snipe")
    ):
        bd.append((f"환경 {env.name} 거리", -env.range_penalty))
        v -= env.range_penalty
    blind = attacker.status("blind")
    if blind:
        bd.append(("연막", -blind.value))
        v -= int(blind.value)
    bless = attacker.status("bless")
    if bless:
        bd.append(("축복", bless.value))
        v += int(bless.value)
    luck = _luck_bonus(attacker)
    if luck:
        bd.append(("행운", luck))
        v += luck
    v = max(HIT_MIN, min(HIT_MAX, v))
    return v, bd


def crit_chance(attacker: UnitState, skill: SkillDef | None = None) -> tuple[int, Breakdown]:
    bd: Breakdown = [("기본", CRIT_BASE)]
    v = CRIT_BASE
    if skill and skill.effect == "crit":
        bd.append((skill.name, skill.magnitude))
        v += skill.magnitude
    luck = _luck_bonus(attacker)
    if luck:
        bd.append(("행운", luck))
        v += luck
    return max(1, min(95, v)), bd


def damage(
    attacker: UnitState,
    defender: UnitState,
    env: Environment,
    skill: SkillDef | None,
    crit: bool,
) -> tuple[int, Breakdown]:
    kind = skill.kind if skill else attacker.weapon.kind
    if kind == "physical":
        stat_part = attacker.stats.str_ * STR_DAMAGE_COEF
        stat_label = "힘"
    else:
        stat_part = attacker.stats.int_ * INT_DAMAGE_COEF
        stat_label = "지능"
    base = skill.base if (skill and skill.base) else attacker.weapon.base_damage
    bd: Breakdown = [("기본", base), (stat_label, round(stat_part, 1))]
    raw = base + stat_part

    armor = defender.armor.armor + defender.weapon.armor
    guard = defender.status("guard")
    if guard:
        armor += int(guard.value)
        bd.append(("방패 밀치기 방어", guard.value))
    reduction = ARMOR_SCALE / (ARMOR_SCALE + armor)
    bd.append((f"방어력 {armor}", round(reduction, 2)))
    raw *= reduction

    env_mult = env.damage_modifiers.get(kind, 1.0)
    if env_mult != 1.0:
        bd.append((f"환경 {env.name} {kind}", env_mult))
        raw *= env_mult
    ward = defender.status("ward")
    if ward and kind == "magic":
        bd.append(("마법 저항", -ward.value))
        raw *= 1 - ward.value
    if defender.defending:
        bd.append(("방어 태세", DEFEND_MULT))
        raw *= DEFEND_MULT
    if crit:
        bd.append(("치명타", CRIT_MULT))
        raw *= CRIT_MULT
    return max(1, round(raw)), bd


def flee_chance(unit: UnitState, enemies: list[UnitState]) -> tuple[int, Breakdown]:
    """개인 이탈 성공률. 실패하면 그 턴을 잃는다 — 후퇴에도 비용이 있다(설계 §5.3)."""
    fastest = max((e.stats.agi for e in enemies), default=unit.stats.agi)
    diff = (unit.stats.agi - fastest) * FLEE_PER_AGI_DIFF
    v = max(HIT_MIN, min(HIT_MAX, FLEE_BASE + diff))
    return v, [("기본", FLEE_BASE), ("민첩 차", diff)]
