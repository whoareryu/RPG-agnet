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
        names = ctx.get("names", {})
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
        # 실측 보정(30시드, 전사 몰빵): 승산이 0.15~0.20 으로 읽힐 때 그대로 싸운
        # 판의 28% 가 이겼다. 임계 0.20 은 이길 판을 버리는 값이라 속공은 0.15 로
        # 내린다. 오래 끄는 작전일수록 일찍 접는다.
        threshold = {"rush": 0.15, "attrition": 0.25, "defensive": 0.30}[strategy]

        # 도주 성공률이 낮으면 후퇴가 더 비싸다 — 실패한 유닛은 턴을 잃고 그대로 맞는다.
        # 실측(30시드, 전사 몰빵): 느린 전사 파티에 후퇴를 명령하니 사망이 22→40 으로
        # 늘고 승률은 10/30 → 1/30 이 됐다. 도망칠 수 없다면 싸우는 편이 낫다.
        escape = float(ctx.get("escape_chance", 1.0))
        can_escape = escape >= 0.5

        # 승산은 휴리스틱이라 한 턴 크게 흔들린다. 한 번 낮게 찍혔다고 판을 접으면
        # 이길 판을 버린다 — 추세가 나빠지는 중일 때만 접는다. 강제 결정(연속
        # 재계획 상한 초과)일 때는 추세를 묻지 않는다(설계 §6.3).
        prev = ctx.get("previous_odds")
        worsening = prev is None or odds <= float(prev)

        # 후퇴는 이르게 하거나 하지 않는다.
        #
        # 사람이 쓰러진 뒤에 빼면 값이 두 배다: 이미 잃은 것은 못 돌리고, 남은
        # 이들은 등을 보이며 맞는다. 실측(30시드, 전사 몰빵)에서 늦은 후퇴는
        # 승률을 33%→13% 로 깎으면서 생존율은 76%→74% 로 그대로였다 — 아무것도
        # 사지 못하고 판만 버린 셈이다. 그래서 이미 잃은 뒤에는 승산이 임계의
        # 절반 아래로 무너졌을 때만 접는다.
        losses = int(ctx.get("losses", 0))
        bar = threshold if losses == 0 else threshold * 0.5
        give_up = can_escape and ((odds < bar and worsening) or (forced and odds < bar + 0.1))
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
                "rationale": (
                    f"싸울 가치가 없다. 도주 성공률 {escape:.0%} 면 뺄 수 있다. 생존 우선 철수."
                ),
            }

        # 편성: 버틸 수 있는 만큼만 앞에 세운다.
        #
        # 근접 적은 전열이 살아 있는 한 후열에 닿지 못한다(core/battle/resolve.py).
        # 그래서 "전사는 전부 전열" 은 맞을 자리를 늘리기만 한다 — 실측(30시드,
        # 전사 몰빵)에서 감독 ON 의 승률이 3%, 고정 편성인 OFF 가 33% 였다.
        # 방패를 든 하나가 앞에 서고 나머지는 뒤에서 친다.
        def durability(u: dict[str, Any]) -> tuple[int, int]:
            return (u["weight_class"], u["hp_pct"])

        formation = {u["id"]: "back" for u in units}
        melee = [u for u in units if not u["ranged"]]
        if units:
            tank = max(melee or units, key=durability)
            formation[tank["id"]] = "front"
        # 근접이 여럿이고 인원이 넉넉하면 둘째 근접도 앞에 세워 전열이 무너지는
        # 순간을 늦춘다. 치유자는 앞에 세우지 않는다.
        if len(units) >= 3 and len(melee) >= 2:
            second = sorted(
                (u for u in melee if formation[u["id"]] == "back" and not u["can_heal"]),
                key=durability,
                reverse=True,
            )
            if second and durability(second[0])[0] >= 2:
                formation[second[0]["id"]] = "front"

        # 집중 목표: 치유자 → 곧 죽일 수 있는 잡졸 → 보스.
        #
        # 예전에는 "가장 약한 적"(HP 버킷)이었고, 그래서 보스가 상처를 입는 순간
        # 계속 보스만 물고 늘어졌다. 그 사이 소환된 수하가 살아남아 매 턴 파티를
        # 갉아먹었다 — 실측(20시드, 전사 몰빵)에서 감독 ON 이 OFF 보다 나빴다.
        # 잡졸은 HP 가 낮아 먼저 치우는 편이 받는 피해를 줄인다.
        focus = None
        if enemies:
            healers = [e for e in enemies if e["can_heal"]]
            adds = sorted([e for e in enemies if not e["is_boss"]], key=lambda e: e.get("hp", 0))
            bosses = [e for e in enemies if e["is_boss"]]
            if healers and any(u["ranged"] for u in units):
                focus = healers[0]["id"]
            elif adds:
                focus = adds[0]["id"]
            elif bosses:
                focus = bosses[0]["id"]
            else:
                focus = enemies[0]["id"]

        focus_name = names.get(focus, focus) if focus else "적"
        directive = {}
        for u in units:
            if u["can_heal"]:
                directive[u["id"]] = "후열에서 다친 아군을 치유하고, 여유가 있으면 축복."
            elif formation[u["id"]] == "front":
                directive[u["id"]] = f"전열에서 {focus_name}을(를) 집중 공격. 빈사면 방어."
            else:
                directive[u["id"]] = f"후열에서 {focus_name}을(를) 노린다. 근접당하면 물러선다."

        stuck = "" if can_escape else f" 도주 성공률이 {escape:.0%}라 물러설 수도 없다."
        text = {
            "rush": "힐러가 없으니 오래 못 버틴다. 속공으로 짧게 끝낸다.",
            "attrition": "힐러가 있다. 전열이 버티고 후열이 갉아먹는다.",
            "defensive": "승산이 반반 아래다. 방어하며 기회를 본다.",
        }[strategy] + stuck
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
        names = ctx.get("names", {})
        skills = {s["name"]: s for s in ctx.get("skills", [])}
        hp = me.get("hp_pct", 100)
        stamina_ratio = me.get("stamina", 0) / max(1, me.get("stamina_max", 1))
        my_statuses = set((visible.get("self") or {}).get("statuses") or [])

        def nm(uid: str | None) -> str:
            return names.get(uid, uid) if uid else "적"

        def find(kind: str, **match: Any) -> dict[str, Any] | None:
            for a in available:
                if a["kind"] != kind:
                    continue
                if all(a.get(k) == v for k, v in match.items()):
                    return a
            return None

        def skill_actions(pred) -> list[dict[str, Any]]:
            out = []
            for a in available:
                if a["kind"] != "SKILL":
                    continue
                meta = skills.get(a.get("skill") or "")
                if meta and pred(meta):
                    out.append(a)
            return out

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
            return answer(find("FLEE"), True, "단장의 후퇴 명령이다. 물러난다.")

        if verdict == "deviate":
            life = (me.get("life") or "").strip()
            worry = f" {life}" if life else ""
            if hp < 40 and find("FLEE"):
                return answer(find("FLEE"), False, f"여기서 죽을 수는 없다.{worry}")
            if find("DEFEND"):
                return answer(find("DEFEND"), False, f"방침은 알지만 지금은 몸을 지킨다.{worry}")
            return answer(find("WAIT"), False, f"발이 떨어지지 않는다.{worry}")

        # 순응 — 치유자가 먼저 본다. 사람이 죽으면 작전이 없다.
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
                    return answer(a, True, f"{h['name']}이(가) 위험하다. 상처를 덮는다.")
            bless = skill_actions(lambda m: m["effect"] == "bless")
            if bless and stamina_ratio > 0.6 and "bless" not in my_statuses:
                return answer(bless[0], True, "다친 사람이 없다. 축복으로 아군의 손을 돕는다.")

        # 순응 — 빈사면 방어
        if hp < 30 and find("DEFEND"):
            return answer(find("DEFEND"), True, "빈사다. 방침대로 몸을 지킨다.")

        # 순응 — 방어 기술은 아직 안 걸려 있을 때 한 번만.
        #
        # 예전에는 "스킬 목록의 첫 번째" 를 골랐고, 전사 스킬 순서가
        # (방패 밀치기, 강타) 라 가렛이 40판 동안 자기 방어만 하고 총 피해가 0 이었다
        # (QA 라운드 1 P0-4). 기술이 무엇을 하는지는 ctx["skills"] 가 말해준다.
        guards = skill_actions(lambda m: m["effect"] == "guard")
        if (
            guards
            and "guard" not in my_statuses
            and stamina_ratio > 0.5
            and me.get("position") == "front"
        ):
            return answer(guards[0], True, "전열이다. 방패를 들어 뒤를 막는다.")

        # 순응 — 피해 기술. 집중 목표가 있으면 그쪽으로.
        offensive = skill_actions(lambda m: m["offensive"])
        if offensive and stamina_ratio >= 0.5:
            picked = next((a for a in offensive if a.get("target") == focus), None)
            picked = picked or next((a for a in offensive if a.get("target") is None), None)
            picked = picked or offensive[0]
            where = nm(picked.get("target")) if picked.get("target") else "적 전체"
            return answer(picked, True, f"{picked['skill']}으로 {where}을(를) 노린다.")

        # 순응 — 집중 목표 공격
        if focus and find("ATTACK", target=focus):
            return answer(find("ATTACK", target=focus), True, f"방침대로 {nm(focus)}을(를) 친다.")
        any_attack = find("ATTACK")
        if any_attack:
            return answer(any_attack, focus is None, f"{nm(any_attack['target'])}을(를) 친다.")
        if find("DEFEND"):
            return answer(find("DEFEND"), True, "칠 수 없다. 방어한다.")
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
        names = ctx.get("names", {})
        target_name = names.get(target, target) if target else "적"
        adapt_ko = {
            "focus": " 저 자가 계속 나를 노렸다.",
            "ward": " 마법이 성가시다. 결계를 두른다.",
            "target_healer": " 상처를 덮는 자를 먼저 부순다.",
            "summon_faster": " 잔해를 더 자주 불러 모은다.",
        }
        return {
            "action": chosen["kind"],
            "target": chosen.get("target"),
            "skill": chosen.get("skill"),
            "adapt": adapt,
            "reason": f"{target_name}을(를) 노린다." + adapt_ko.get(adapt or "", ""),
        }
