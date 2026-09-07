"""승산 휴리스틱 — 계산은 코드, 판단은 모델 (기획서 §8.3, 설계 §6.2).

행운을 읽지 않는다(hit_chance 에 include_luck=False). 행운이 승산에 들어가면
"그냥 랜덤 아니에요?"의 근거가 되고 성향 실험을 오염시킨다(기획서 §4.2).
"""

from typing import Any

from core.battle.state import Battle, UnitState, living
from core.rules.combat import damage, hit_chance
from core.rules.constants import HEAL_SYNERGY, ODDS_MAX, ODDS_MIN
from core.types import Environment


def unit_power(
    u: UnitState, foes: list[UnitState], env: Environment
) -> tuple[float, dict[str, Any]]:
    if not foes:
        return 0.0, {"reason": "적 없음"}
    exp = 0.0
    for f in foes:
        needed, _ = hit_chance(u, f, env, None, include_luck=False)
        dmg, _ = damage(u, f, env, None, crit=False)
        exp += dmg * needed / 100
    exp /= len(foes)
    hp_ratio = u.hp / u.hp_max
    # 스태미나가 바닥이면 행동을 못 한다. 그래도 0 은 아니다 — 회복이 있다.
    survival = max(0.3, u.stamina / u.stamina_max)
    power = hp_ratio * exp * survival
    return power, {
        "hp_ratio": round(hp_ratio, 2),
        "expected_damage": round(exp, 1),
        "survival": round(survival, 2),
        "power": round(power, 1),
    }


def faction_power(battle: Battle, faction: str) -> tuple[float, dict[str, Any]]:
    mine = living(battle, faction)
    other = battle.enemy if faction == battle.party else battle.party
    foes = living(battle, other)
    total = 0.0
    per_unit: dict[str, Any] = {}
    for u in mine:
        p, bd = unit_power(u, foes, battle.environment)
        total += p
        per_unit[u.id] = bd
    synergy = 1.0
    if any(s.effect == "heal" for u in mine for s in u.skills):
        synergy = HEAL_SYNERGY
        total *= synergy
    return total, {"units": per_unit, "synergy": synergy, "total": round(total, 1)}


def odds(battle: Battle, faction: str) -> tuple[float, dict[str, Any]]:
    """faction 의 승산 0.05..0.95."""
    other = battle.enemy if faction == battle.party else battle.party
    # 한쪽이 비어 있으면 전력 계산이 양쪽 다 0 이 된다(때릴 상대가 없다).
    # 그 경우는 승부가 이미 났다 — 비어 있는 쪽이 바닥이다.
    if not living(battle, faction):
        return ODDS_MIN, {"reason": "생존 유닛 없음"}
    if not living(battle, other):
        return ODDS_MAX, {"reason": "적 생존 유닛 없음"}
    a, bd_a = faction_power(battle, faction)
    b, bd_b = faction_power(battle, other)
    value = 0.5 if a + b == 0 else a / (a + b)
    value = max(ODDS_MIN, min(ODDS_MAX, value))
    return round(value, 3), {"mine": bd_a, "theirs": bd_b}
