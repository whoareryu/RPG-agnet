"""보스 정책 + in-context 적응 (기획서 §8.3, 설계 §5.6). 수하는 고정 정책(모델 호출 0).

적응 규칙은 코드로 고정한다 — 인스펙터가 "관측 → 대응"을 설명할 수 있어야
하고, 자유 텍스트 적응은 재현이 안 된다. 모델은 4개 enum 안에서만 고른다.
"""

from typing import Any

from core.agents.josa import with_josa
from core.agents.prompts import build_boss_prompt
from core.agents.schemas import ADAPTATIONS, BOSS_SCHEMA
from core.battle.state import Battle, Status, available_actions, enemies_of
from core.ports import DecisionModel
from core.rules.constants import (
    ADAPT_DEFEND_RATIO,
    ADAPT_HEAL_COUNT,
    ADAPT_MAGIC_RATIO,
    ADAPT_WARD_MAGIC_RESIST,
    ADAPT_WARD_TURNS,
    ADAPT_WINDOW,
)
from core.trace.schema import Tracer
from core.types import Action

PATTERN_TO_COUNTER = {
    "repeat_attacker": "focus",
    "magic_heavy": "ward",
    "healing": "target_healer",
    "turtle": "summon_faster",
}


def detect_adaptation(battle: Battle, boss_id: str) -> tuple[str | None, dict[str, Any]]:
    """최근 ADAPT_WINDOW 턴(완료된 턴)의 파티 행동에서 패턴 하나. 같은 패턴은 창 안에서 한 번만."""
    boss = battle.units[boss_id]
    window_start = battle.turn - ADAPT_WINDOW
    recent = [
        h
        for h in battle.history
        if h.faction != boss.faction and window_start <= h.turn < battle.turn
    ]
    turns_seen = {h.turn for h in recent}
    if len(turns_seen) < ADAPT_WINDOW:
        return None, {}
    already = {p for t, p in battle.boss_adaptations if t > window_start}

    # ① 같은 아군이 3턴 연속 보스를 공격.
    #
    # 후보를 set 으로 돌면 파이썬 문자열 해시 순서가 PYTHONHASHSEED 에 따라 달라져
    # 같은 시드가 프로세스마다 다른 판을 만든다(160판 중 6판이 승패까지 갈렸다).
    # 등장 순서(dict.fromkeys)로 돌고, 동률이면 먼저 친 쪽을 고른다.
    if "repeat_attacker" not in already:
        for actor in dict.fromkeys(h.actor for h in recent):
            hits = {
                h.turn for h in recent if h.actor == actor and h.target == boss_id and h.damage > 0
            }
            if len(hits) >= ADAPT_WINDOW:
                return "repeat_attacker", {
                    "actor": actor,
                    "turns": sorted(hits),
                    "tie_rule": "먼저 공격을 시작한 쪽",
                }
    # ② 피해의 60% 이상이 마법
    total = sum(h.damage for h in recent)
    magic = sum(h.damage for h in recent if h.damage_kind == "magic")
    if "magic_heavy" not in already and total > 0 and magic / total >= ADAPT_MAGIC_RATIO:
        return "magic_heavy", {"magic": magic, "total": total, "ratio": round(magic / total, 2)}
    # ③ 치유 2회 이상
    heals = [h for h in recent if h.healed > 0]
    if "healing" not in already and len(heals) >= ADAPT_HEAL_COUNT:
        return "healing", {"healer": heals[0].actor, "count": len(heals)}
    # ④ 방어 위주
    defends = [h for h in recent if h.action == "DEFEND"]
    if "turtle" not in already and recent and len(defends) / len(recent) >= ADAPT_DEFEND_RATIO:
        return "turtle", {"defends": len(defends), "actions": len(recent)}
    return None, {}


def apply_adaptation(
    battle: Battle, boss_id: str, pattern: str, evidence: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """(대응 이름, 실제로 바뀐 것). 바뀐 게 없으면 effect 가 그것을 말한다.

    변화를 기록하는 이유: 인스펙터가 "보스가 치유자를 노리기로 했다" 를 세 번
    보여주는데 상태가 한 번도 안 바뀌면 로그가 거짓말한다(QA 라운드 1 P1-9).
    """
    counter = PATTERN_TO_COUNTER[pattern]
    boss = battle.units[boss_id]
    effect: dict[str, Any] = {}
    if counter in ("focus", "target_healer"):
        before = battle.boss_focus
        after = evidence["actor"] if counter == "focus" else evidence["healer"]
        battle.boss_focus = after
        effect = {"field": "boss_focus", "before": before, "after": after}
    elif counter == "ward":
        existing = boss.status("ward")
        effect = {
            "field": "ward",
            "before": existing.value if existing else 0,
            "after": ADAPT_WARD_MAGIC_RESIST,
            "turns": ADAPT_WARD_TURNS,
        }
        if existing:
            existing.turns = max(existing.turns, ADAPT_WARD_TURNS)
        else:
            boss.statuses.append(Status("ward", ADAPT_WARD_TURNS, ADAPT_WARD_MAGIC_RESIST))
    elif counter == "summon_faster":
        before = battle.summon_every
        # 바닥을 2 로 둔다. 설계 §5.6 은 "3→2턴" 이고, 창이 지날 때마다 다시
        # 발동해 1턴까지 내려가면 소환이 매 턴이 된다.
        battle.summon_every = max(2, before - 1)
        effect = {
            "field": "summon_every",
            "before": before,
            "after": battle.summon_every,
            "summoned": battle.summoned,
            "summon_max": battle.enemy_def.summon_max if battle.enemy_def else 0,
        }
    effect["no_change"] = effect.get("before") == effect.get("after")
    battle.boss_adaptations.append((battle.turn, pattern))
    return counter, effect


def boss_act(
    battle: Battle, boss_id: str, model: DecisionModel, tracer: Tracer
) -> tuple[Action, str | None]:
    """(행동, 이번 턴 발생한 적응 패턴 또는 None)."""
    boss = battle.units[boss_id]
    pattern: str | None = None
    counter: str | None = None
    if battle.adaptation_on:
        pattern, evidence = detect_adaptation(battle, boss_id)
        if pattern:
            counter, effect = apply_adaptation(battle, boss_id, pattern, evidence)
            tracer.emit(
                "boss_adapt",
                {
                    "pattern": pattern,
                    "counter": counter,
                    "evidence": evidence,
                    "effect": effect,
                    "turn_window": [battle.turn - ADAPT_WINDOW, battle.turn - 1],
                },
                actor=boss_id,
            )
    focus = battle.boss_focus
    if focus and not battle.units[focus].active:
        battle.boss_focus = focus = None

    actions = available_actions(battle, boss_id)
    prompt = build_boss_prompt(battle, boss, actions, counter, focus)
    data = model.decide("boss", prompt, BOSS_SCHEMA)
    from core.agents.character import action_from

    action, note = action_from(data, actions)
    adapt = data.get("adapt")
    if adapt not in ADAPTATIONS:
        adapt = None
    tracer.emit(
        "decision",
        {
            "action": action,
            "label": action.label(),
            "target": action.target,
            "follows_plan": True,
            "verdict": "policy",
            "reason": str(data.get("reason", "")),
            "note": note,
            "adapt": adapt,
            "model": data.get("_meta", {}),
            "timing": data.get("_timing", {}),
            "prompt": prompt,
            "raw": {k: v for k, v in data.items() if not k.startswith("_")},
        },
        actor=boss_id,
    )
    return action, pattern


def minion_act(battle: Battle, unit_id: str, tracer: Tracer) -> Action:
    """수하·일반 적의 고정 정책. 모델을 부르지 않는다 — 비용 통제(기획서 §7.2)."""
    u = battle.units[unit_id]
    actions = available_actions(battle, unit_id)
    foes = enemies_of(battle, unit_id)
    allies = [
        a for a in battle.units.values() if a.faction == u.faction and a.active and a.id != unit_id
    ]
    chosen: Action | None = None
    reason = ""
    heal = u.has_skill("치유")
    if heal:
        hurt = sorted([a for a in allies if a.hp / a.hp_max < 0.5], key=lambda a: a.hp / a.hp_max)
        for h in hurt:
            cand = Action("SKILL", target=h.id, skill="치유")
            if cand in actions:
                chosen, reason = cand, f"{with_josa(h.name, '을')} 치유한다"
                break
    target: str | None = None
    if foes:
        focus = battle.boss_focus if battle.boss_focus in {f.id for f in foes} else None
        target = focus or min(foes, key=lambda f: f.hp).id
    if chosen is None and target and u.stamina >= u.stamina_max * 0.5:
        for a in actions:
            if a.kind == "SKILL" and a.skill not in ("치유", "축복") and a.target in (target, None):
                who = battle.units[a.target].name if a.target else "전원"
                chosen, reason = a, f"{with_josa(a.skill, '으로')} {with_josa(who, '을')} 친다"
                break
    if chosen is None and target:
        cand = Action("ATTACK", target=target)
        chosen = cand if cand in actions else next((a for a in actions if a.kind == "ATTACK"), None)
        reason = f"{with_josa(battle.units[target].name, '을')} 노린다"
    if chosen is None:
        chosen = Action("DEFEND") if Action("DEFEND") in actions else Action("WAIT")
        reason = "버틴다"
    tracer.emit(
        "decision",
        {
            "action": chosen,
            "label": chosen.label(),
            "target": chosen.target,
            "follows_plan": True,
            "verdict": "policy",
            "reason": reason,
            "note": None,
            "model": {"model": "policy", "fallback": False, "attempts": 0, "latency_ms": 0},
        },
        actor=unit_id,
    )
    return chosen
