"""프롬프트 조립 (설계 §6.1·§6.4).

두 부분으로 되어 있다:
1. 사람이 읽는 서술 — 실제 LLM 이 상황을 이해하는 부분.
2. `<<CONTEXT_JSON>> … <<END>>` — 같은 정보의 구조화본. Fake 모델이 규칙으로
   읽고, 실제 모델도 정확한 id 를 여기서 가져간다.

두 부분이 같은 정보를 담아야 한다. 서술에만 있고 JSON 에 없는 정보는 Fake 가
못 보고, 그 반대는 실제 모델이 놓친다.

MBTI 문자열은 절대 넣지 않는다(tests/test_prompts.py). 성향은 describe() 의
수치 서술로만 들어간다(기획서 §4.5).
"""

import json
from typing import Any

from core.battle.state import Battle, UnitState, living
from core.rules.constants import RETREAT_THRESHOLD_DEFAULT
from core.rules.disposition import describe
from core.types import Action, Plan

CTX_OPEN = "<<CONTEXT_JSON>>"
CTX_CLOSE = "<<END>>"


def _ctx(d: dict[str, Any]) -> str:
    return f"\n{CTX_OPEN}\n{json.dumps(d, ensure_ascii=False)}\n{CTX_CLOSE}\n"


def _hp_bucket(u: UnitState) -> str:
    pct = u.hp / u.hp_max
    return "건재" if pct > 0.7 else ("상처" if pct > 0.3 else "빈사")


def build_orchestrator_prompt(
    battle: Battle,
    faction: str,
    odds_value: float,
    reason: str,
    forced: bool = False,
    previous: Plan | None = None,
) -> str:
    env = battle.environment
    mine = living(battle, faction)
    other = battle.enemy if faction == battle.party else battle.party
    foes = living(battle, other)

    units_ctx = [
        {
            "id": u.id,
            "name": u.name,
            "class": u.char_class,
            "hp_pct": round(100 * u.hp / u.hp_max),
            "stamina_pct": round(100 * u.stamina / u.stamina_max),
            "agi": u.stats.agi,
            "weight_class": u.armor.weight_class,
            "ranged": u.weapon.ranged,
            "can_heal": any(s.effect == "heal" for s in u.skills),
            "position": u.position,
            "disposition": u.disposition.as_dict() if u.disposition else None,
        }
        for u in mine
    ]
    foes_ctx = [
        {
            "id": f.id,
            "name": f.name,
            "hp_bucket": _hp_bucket(f),
            "is_boss": f.is_boss,
            "position": f.position,
            "can_heal": any(s.effect == "heal" for s in f.skills),
        }
        for f in foes
    ]
    lines = [
        "당신은 용병단의 단장이다. 단주가 준 인원으로 최선을 다한다. 받은 패로 싸운다.",
        "먼저 '싸울 가치가 있는가'를 판단하고, 있다면 작전을 짠다.",
        f"환경: {env.name} — {env.description}",
        f"환경 수치: 중갑 속도 페널티 {env.speed_penalty_by_weight}, "
        f"스태미나 배수 {env.stamina_multiplier}, 피해 배수 {env.damage_modifiers}, "
        f"후열 거리 페널티 {env.range_penalty}%, 어둠 {env.darkness}",
        f"현재 승산(코드 계산): {odds_value:.2f}",
        f"재계획 사유: {reason}",
    ]
    if forced:
        lines.append("경고: 재계획이 연속 3회를 넘었다. 이번에는 포기 여부를 반드시 결정하라.")
    if previous:
        lines.append(f"직전 작전: {previous.strategy} / {previous.assessment}")
    lines.append("출전 단원:")
    for u in units_ctx:
        d = u["disposition"]
        dd = ", ".join(describe_from_dict(d).values()) if d else "-"
        lines.append(
            f"- {u['name']}({u['id']}, {u['class']}) HP {u['hp_pct']}% "
            f"스태미나 {u['stamina_pct']}% 민첩 {u['agi']} 갑옷무게 {u['weight_class']} "
            f"원거리 {u['ranged']} 치유 {u['can_heal']} / 성향: {dd}"
        )
    lines.append("적:")
    for f in foes_ctx:
        lines.append(
            f"- {f['name']}({f['id']}) {f['hp_bucket']} 위치 {f['position']} 보스 {f['is_boss']}"
        )
    lines.append(
        "JSON 으로만 답하라: assessment, worth_fighting, "
        "strategy(rush|attrition|defensive|retreat), "
        "formation{unit_id: front|back}, focus_target, per_unit_directive{unit_id: 지시}, "
        f"retreat_threshold(0.15..0.45, 기본 {RETREAT_THRESHOLD_DEFAULT}), rationale"
    )
    ctx = {
        "role": "orchestrator",
        "units": units_ctx,
        "enemies": foes_ctx,
        "odds": odds_value,
        "reason": reason,
        "forced": forced,
        "environment": {
            "name": env.name,
            "speed_penalty_by_weight": {str(k): v for k, v in env.speed_penalty_by_weight.items()},
            "range_penalty": env.range_penalty,
        },
        "retreat_threshold_default": RETREAT_THRESHOLD_DEFAULT,
    }
    return "\n".join(lines) + _ctx(ctx)


def describe_from_dict(d: dict[str, int]) -> dict[str, str]:
    from core.types import Disposition

    return describe(Disposition(**d))


def build_character_prompt(
    unit: UnitState,
    visible: dict[str, Any],
    masked: list[str],
    plan: Plan | None,
    actions: list[Action],
    verdict: str,
) -> str:
    directive = plan.per_unit_directive.get(unit.id) if plan else None
    focus = plan.focus_target if plan else None
    d = unit.disposition
    lines = [
        f"당신은 {unit.name}, {unit.char_class} 다. {unit.voice}",
        f"신체: {unit.body.height_cm}cm · {unit.body.build} · {unit.body.weight_kg}kg. "
        f"무기 {unit.weapon.name}, 갑옷 {unit.armor.name}.",
        f"능력치: 힘 {unit.stats.str_} 민첩 {unit.stats.agi} 체력 {unit.stats.con} "
        f"지능 {unit.stats.int_} 지혜 {unit.stats.wis}",
    ]
    if d:
        lines.append("성향: " + ", ".join(describe(d).values()))
    if unit.life_note:
        lines.append(f"생애: {unit.life_note}")
    if plan:
        lines.append(
            f"단장의 방침: {directive or '(개별 지시 없음)'} / 집중 목표: {focus or '없음'}"
        )
    else:
        lines.append("단장이 없다. 방침도 없다. 스스로 판단한다.")
    if verdict == "deviate":
        lines.append(
            "당신은 이번 턴 단장의 방침을 따르지 않기로 했다. 살아남는 것이 먼저다. "
            "도망(FLEE)치거나 방침 밖 행동을 고르고, 이유를 말하라."
        )
    else:
        lines.append("방침 안에서 이번 턴 행동을 고른다.")
    lines.append("보이는 것: " + json.dumps(visible, ensure_ascii=False))
    if masked:
        lines.append("보이지 않는 것(판단력 한계): " + ", ".join(masked))
    lines.append("가능한 행동: " + ", ".join(_action_text(a) for a in actions))
    lines.append(
        "JSON 으로만 답하라: action(ATTACK|DEFEND|SKILL|MOVE|FLEE|WAIT), target, skill, position, "
        "follows_plan(bool), reason(한 문장)"
    )
    ctx = {
        "role": "character",
        "self": {
            "id": unit.id,
            "class": unit.char_class,
            "hp_pct": round(100 * unit.hp / unit.hp_max),
            "stamina": unit.stamina,
            "stamina_max": unit.stamina_max,
            "position": unit.position,
            "can_heal": any(s.effect == "heal" for s in unit.skills),
        },
        "verdict": verdict,
        "directive": directive,
        "focus_target": focus,
        "strategy": plan.strategy if plan else None,
        "visible": visible,
        "masked": masked,
        "available": [_action_ctx(a) for a in actions],
    }
    return "\n".join(lines) + _ctx(ctx)


def _action_text(a: Action) -> str:
    if a.kind == "SKILL":
        return f"SKILL:{a.skill}" + (f"→{a.target}" if a.target else "")
    if a.kind == "ATTACK":
        return f"ATTACK→{a.target}"
    if a.kind == "MOVE":
        return f"MOVE→{a.position}"
    return a.kind


def _action_ctx(a: Action) -> dict[str, Any]:
    return {"kind": a.kind, "target": a.target, "skill": a.skill, "position": a.position}


def build_boss_prompt(
    battle: Battle,
    unit: UnitState,
    actions: list[Action],
    adapt_suggestion: str | None,
    focus_override: str | None,
) -> str:
    foes = [u for u in battle.units.values() if u.faction != unit.faction and u.active]
    foes_ctx = [
        {
            "id": f.id,
            "class": f.char_class,
            "hp_pct": round(100 * f.hp / f.hp_max),
            "position": f.position,
            "can_heal": any(s.effect == "heal" for s in f.skills),
        }
        for f in foes
    ]
    lines = [
        f"당신은 {unit.name}. 상대가 반복하는 것을 기억하고 대응한다.",
        f"HP {round(100 * unit.hp / unit.hp_max)}%, 스태미나 {unit.stamina}/{unit.stamina_max}.",
        "상대: " + json.dumps(foes_ctx, ensure_ascii=False),
    ]
    if adapt_suggestion:
        lines.append(f"관측된 패턴에 대한 대응 후보: {adapt_suggestion}")
    if focus_override:
        lines.append(f"우선 타격 대상: {focus_override}")
    lines.append("가능한 행동: " + ", ".join(_action_text(a) for a in actions))
    lines.append(
        "JSON 으로만 답하라: action, target, skill, "
        "adapt(focus|ward|target_healer|summon_faster|null), reason"
    )
    ctx = {
        "role": "boss",
        "self": {
            "id": unit.id,
            "hp_pct": round(100 * unit.hp / unit.hp_max),
            "stamina": unit.stamina,
        },
        "enemies": foes_ctx,
        "adapt_suggestion": adapt_suggestion,
        "focus_override": focus_override,
        "available": [_action_ctx(a) for a in actions],
        "turn": battle.turn,
    }
    return "\n".join(lines) + _ctx(ctx)


def build_narration_prompt(kind: str, facts: dict[str, Any], fallback: str) -> str:
    lines = [
        "다음 사실을 한두 문장의 중세 용병단 서사로 쓴다. 사실을 바꾸지 않는다.",
        f"종류: {kind}",
        "사실: " + json.dumps(facts, ensure_ascii=False),
        "JSON 으로만 답하라: narration",
    ]
    return "\n".join(lines) + _ctx(
        {"role": "narrator", "kind": kind, "facts": facts, "fallback": fallback}
    )
