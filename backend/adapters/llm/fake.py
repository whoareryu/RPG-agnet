"""Fake 모델 — 휴리스틱 정책 (기획서 §9 추가①, 설계 §3.4).

프롬프트의 `<<CONTEXT_JSON>>` 블록을 읽어 규칙으로 답한다. 판단이 LLM 보다
단순할 뿐, 규칙·로그·인스펙터는 동일하다. 테스트·자동 대전(수백 판)·LLM 장애
폴백·API 키 없는 로컬 플레이가 전부 이것으로 돈다.

"너무 똑똑하지도 너무 멍청하지도" 않아야 실험이 의미 있다: 감독은 힐러 유무와
승산을 보고, 단원은 HP·스태미나·방침을 보고, 보스는 코드가 제안한 적응을 따른다.
"""

import json
from typing import Any

from core.agents.prompts import CTX_CLOSE, CTX_OPEN
from core.ports import JsonSchema, Role

RANGED_CLASSES = {"archer", "mage", "cleric"}


def parse_context(prompt: str) -> dict[str, Any]:
    start = prompt.rfind(CTX_OPEN)
    end = prompt.rfind(CTX_CLOSE)
    if start < 0 or end < 0:
        return {}
    return json.loads(prompt[start + len(CTX_OPEN) : end])


class FakeModel:
    name = "fake"

    def decide(self, role: Role, prompt: str, schema: JsonSchema) -> dict[str, Any]:
        ctx = parse_context(prompt)
        if role == "orchestrator":
            return self._orchestrate(ctx)
        if role == "character":
            return self._act(ctx)
        if role == "boss":
            return self._boss(ctx)
        return {"narration": ctx.get("fallback", "")}

    # ─── 단장 ───────────────────────────────────────────────────────────
    def _orchestrate(self, ctx: dict[str, Any]) -> dict[str, Any]:
        units = ctx.get("units", [])
        enemies = ctx.get("enemies", [])
        odds = float(ctx.get("odds", 0.5))
        forced = bool(ctx.get("forced"))
        has_healer = any(u["can_heal"] for u in units)
        if not has_healer:
            strategy = "rush"
        elif odds >= 0.5:
            strategy = "attrition"
        else:
            strategy = "defensive"
        # 임계는 전략이 정한다. 속공은 "짧게 끝내자"는 약속이라 낮은 승산을 견디고,
        # 방어전은 오래 끄는 만큼 일찍 접는다. 힐러 없음에 +0.05 를 얹는 안은 실측
        # (30시드)에서 이길 판의 절반을 포기하게 만들어 버렸다.
        threshold = {"rush": 0.20, "attrition": 0.30, "defensive": 0.35}[strategy]

        give_up = odds < threshold or (forced and odds < threshold + 0.1)
        if give_up:
            return {
                "assessment": (
                    f"승산 {odds:.2f}. 힐러 {'있음' if has_healer else '없음'}. "
                    "더 싸우면 사람을 잃는다."
                ),
                "worth_fighting": False,
                "strategy": "retreat",
                "formation": {u["id"]: u["position"] for u in units},
                "focus_target": None,
                "per_unit_directive": {u["id"]: "후퇴한다. 생존 우선." for u in units},
                "retreat_threshold": round(threshold, 2),
                "rationale": "싸울 가치가 없다. 포기, 생존 우선 철수.",
            }

        formation = {}
        for u in units:
            front = u["class"] in ("warrior", "rogue") or u["weight_class"] == 3 or not u["ranged"]
            formation[u["id"]] = "front" if front else "back"
        if all(p == "back" for p in formation.values()) and units:
            # 누군가는 앞에 서야 한다. 체력이 가장 많은 사람.
            tank = max(units, key=lambda u: u["hp_pct"])
            formation[tank["id"]] = "front"

        focus = None
        if enemies:
            healers = [e for e in enemies if e["can_heal"]]
            bosses = [e for e in enemies if e["is_boss"]]
            weak = sorted(enemies, key=lambda e: {"빈사": 0, "상처": 1, "건재": 2}[e["hp_bucket"]])
            if healers and any(u["ranged"] for u in units):
                focus = healers[0]["id"]
            elif weak and weak[0]["hp_bucket"] != "건재":
                focus = weak[0]["id"]
            elif bosses:
                focus = bosses[0]["id"]
            else:
                focus = weak[0]["id"]

        directive = {}
        for u in units:
            if u["can_heal"]:
                directive[u["id"]] = "후열에서 다친 아군을 치유하고, 여유가 있으면 축복."
            elif formation[u["id"]] == "front":
                directive[u["id"]] = f"전열에서 {focus} 를 집중 공격. 빈사면 방어."
            else:
                directive[u["id"]] = f"후열에서 {focus} 를 노린다. 근접당하면 물러선다."

        text = {
            "rush": "힐러가 없으니 오래 못 버틴다. 속공으로 짧게 끝낸다.",
            "attrition": "힐러가 있다. 전열이 버티고 후열이 갉아먹는다.",
            "defensive": "승산이 반반 아래다. 방어하며 기회를 본다.",
        }[strategy]
        return {
            "assessment": f"승산 {odds:.2f}. 힐러 {'있음' if has_healer else '없음'}. {text}",
            "worth_fighting": True,
            "strategy": strategy,
            "formation": formation,
            "focus_target": focus,
            "per_unit_directive": directive,
            "retreat_threshold": round(threshold, 2),
            "rationale": text,
        }

    # ─── 단원 ───────────────────────────────────────────────────────────
    def _act(self, ctx: dict[str, Any]) -> dict[str, Any]:
        me = ctx.get("self", {})
        available = ctx.get("available", [])
        verdict = ctx.get("verdict", "comply")
        focus = ctx.get("focus_target")
        visible = ctx.get("visible", {})
        hp = me.get("hp_pct", 100)

        def find(kind: str, **match: Any) -> dict[str, Any] | None:
            for a in available:
                if a["kind"] != kind:
                    continue
                if all(a.get(k) == v for k, v in match.items()):
                    return a
            return None

        def answer(a: dict[str, Any] | None, follows: bool, reason: str) -> dict[str, Any]:
            if a is None:
                a = {"kind": "WAIT", "target": None, "skill": None, "position": None}
            return {
                "action": a["kind"],
                "target": a.get("target"),
                "skill": a.get("skill"),
                "position": a.get("position"),
                "follows_plan": follows,
                "reason": reason,
            }

        if ctx.get("strategy") == "retreat" and find("FLEE"):
            return answer(find("FLEE"), True, "단장의 후퇴 명령. 빠진다.")

        if verdict == "deviate":
            if hp < 40 and find("FLEE"):
                return answer(find("FLEE"), False, "생존이 먼저다. 여기서 죽을 수는 없다.")
            if find("DEFEND"):
                return answer(find("DEFEND"), False, "방침은 알지만 지금은 몸을 지킨다.")
            return answer(find("WAIT"), False, "움직이지 않는다.")

        # 순응 — 치유자
        if me.get("can_heal"):
            allies = visible.get("allies") or []
            hurt = sorted(
                [a for a in allies if a.get("hp_pct", 100) < 55], key=lambda a: a["hp_pct"]
            )
            if hp < 45:
                heal_self = find("SKILL", skill="치유", target=me["id"])
                if heal_self:
                    return answer(heal_self, True, "내가 쓰러지면 아무도 못 살린다.")
            for h in hurt:
                a = find("SKILL", skill="치유", target=h["id"])
                if a:
                    return answer(a, True, f"{h['name']} 이(가) 위험하다. 치유한다.")
            bless = find("SKILL", skill="축복")
            if bless and me.get("stamina", 0) > me.get("stamina_max", 1) * 0.6:
                return answer(bless, True, "다친 사람이 없다. 축복으로 아군의 손을 돕는다.")

        # 순응 — 빈사면 방어
        if hp < 30 and find("DEFEND"):
            return answer(find("DEFEND"), True, "빈사다. 방침대로 방어한다.")

        # 순응 — 스킬 여유가 있으면 스킬
        stamina_ok = me.get("stamina", 0) >= me.get("stamina_max", 1) * 0.5
        if stamina_ok:
            for a in available:
                if a["kind"] == "SKILL" and a.get("skill") not in ("치유", "축복"):
                    if a.get("target") in (None, focus) or focus is None:
                        return answer(
                            a, True, f"{a['skill']} 로 {a.get('target') or '적 전체'} 를 친다."
                        )
        # 순응 — 집중 목표 공격
        if focus and find("ATTACK", target=focus):
            return answer(find("ATTACK", target=focus), True, f"방침대로 {focus} 를 공격한다.")
        any_attack = find("ATTACK")
        if any_attack:
            return answer(any_attack, focus is None, f"{any_attack['target']} 를 공격한다.")
        if find("DEFEND"):
            return answer(find("DEFEND"), True, "공격할 수 없다. 방어한다.")
        return answer(find("WAIT"), True, "지쳤다. 숨을 고른다.")

    # ─── 보스 ───────────────────────────────────────────────────────────
    def _boss(self, ctx: dict[str, Any]) -> dict[str, Any]:
        available = ctx.get("available", [])
        enemies = ctx.get("enemies", [])
        focus = ctx.get("focus_override")
        adapt = ctx.get("adapt_suggestion")
        turn = int(ctx.get("turn", 0))

        target = focus
        if target is None and enemies:
            front = [e for e in enemies if e["position"] == "front"]
            pool = front or enemies
            target = min(pool, key=lambda e: e["hp_pct"])["id"]

        def find(kind: str, **match: Any) -> dict[str, Any] | None:
            for a in available:
                if a["kind"] == kind and all(a.get(k) == v for k, v in match.items()):
                    return a
            return None

        chosen = None
        if turn % 2 == 0:
            chosen = find("SKILL", skill="분쇄", target=target) or find("SKILL", skill="갱도 진동")
        if chosen is None:
            chosen = (
                find("ATTACK", target=target) or find("ATTACK") or find("DEFEND") or find("WAIT")
            )
        if chosen is None:
            chosen = {"kind": "WAIT", "target": None, "skill": None}
        return {
            "action": chosen["kind"],
            "target": chosen.get("target"),
            "skill": chosen.get("skill"),
            "adapt": adapt,
            "reason": f"{target} 를 노린다." + (f" 적응: {adapt}." if adapt else ""),
        }
