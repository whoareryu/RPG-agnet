// 이벤트 → 서사 문장 (설계 §11.2). 순수 함수. 모델이 쓰는 문장은 decision.reason 뿐이고
// 나머지는 전부 여기서 만든다 — 그래야 Fake 모드에서도 화면이 비지 않는다.
//
// 원칙: 왼쪽(서사)에서 일어나는 모든 일이 가운데(인스펙터)에서 설명 가능해야 한다.
// 그러니 서사는 사실만 말하고, 수치는 인스펙터에 맡긴다.

import type { MissionResult, Resolution, TraceEvent } from "./trace.ts";
import { OUTCOME_KO } from "./trace.ts";

type Names = Record<string, string>;

const ACTION_KO: Record<string, string> = {
  ATTACK: "공격한다",
  DEFEND: "방어 태세를 취한다",
  FLEE: "전장에서 빠져나가려 한다",
  WAIT: "숨을 고른다",
};

const TRIGGER_KO: Record<string, string> = {
  deviation: "단원의 이탈",
  odds_collapse: "승산 붕괴",
  adaptation: "적의 적응",
  environment: "환경 변화",
};

const ADAPT_KO: Record<string, string> = {
  repeat_attacker: "같은 자가 세 턴 연속 자신을 노린 것",
  magic_heavy: "마법 피해가 대부분인 것",
  healing: "치유가 반복되는 것",
  turtle: "상대가 방어만 하는 것",
};
const COUNTER_KO: Record<string, string> = {
  focus: "그를 우선 노리기로 한다",
  ward: "마법 저항 결계를 두른다",
  target_healer: "치유자를 먼저 노린다",
  summon_faster: "잔해를 더 자주 불러 모은다",
};

const STRATEGY_KO: Record<string, string> = {
  rush: "속공",
  attrition: "지구전",
  defensive: "방어전",
  retreat: "후퇴",
};

export function nameOf(id: string | null | undefined, names: Names): string {
  if (!id) return "누군가";
  return names[id] ?? id;
}

export function narrate(e: TraceEvent, names: Names): string {
  const p = e.payload;
  const who = nameOf(e.actor, names);
  switch (e.kind) {
    case "run_start": {
      const lineup = (p.lineup as string[]).map((id) => nameOf(id, names)).join(", ");
      return `단주가 출전 명단을 확정했다 — ${lineup}. ${p.orchestrator_on ? "단장이 지휘한다." : "단장 없이 각자 판단한다."}`;
    }
    case "mission_start": {
      const enemy = p.enemy as { name: string; description: string };
      const env = p.environment as { name: string; description: string };
      return `${env.name}. ${env.description} 상대는 ${enemy.name}. ${enemy.description}`;
    }
    case "plan": {
      const plan = p.plan as { assessment: string; strategy: string; worth_fighting: boolean; focus_target: string | null };
      const reason = String(p.reason);
      const lead = reason === "initial" ? "단장이 전장을 읽는다" : "단장이 작전을 다시 짠다";
      if (!plan.worth_fighting) return `${lead}: "${plan.assessment}" — 싸울 가치가 없다고 판단했다.`;
      const focus = plan.focus_target ? ` 목표는 ${nameOf(plan.focus_target, names)}.` : "";
      return `${lead}: "${plan.assessment}" 작전은 ${STRATEGY_KO[plan.strategy] ?? plan.strategy}.${focus}`;
    }
    case "odds": {
      const v = Math.round(Number(p.value) * 100);
      return `승산 ${v}%.`;
    }
    case "turn_start": {
      const order = (p.order as { unit: string }[]).map((o) => nameOf(o.unit, names));
      return `${e.turn}턴. 움직이는 순서: ${order.join(" → ")}.`;
    }
    case "context": {
      const masked = (p.masked as string[]) ?? [];
      if (masked.length === 0) return `${who}는 전장을 전부 본다.`;
      return `${who}는 전장의 일부만 본다 (판단력 ${p.wis_tier}단계).`;
    }
    case "compliance": {
      const pct = Math.round(Number(p.probability) * 100);
      if (p.verdict === "deviate") return `${who}의 마음이 방침에서 떠난다 (이탈 확률 ${pct}%).`;
      return `${who}는 방침을 따르기로 한다 (이탈 확률 ${pct}%).`;
    }
    case "decision": {
      const label = String(p.label);
      const target = p.target ? nameOf(String(p.target), names) : null;
      const reason = p.reason ? ` "${p.reason}"` : "";
      const note = p.note ? ` (${p.note})` : "";
      if (label.startsWith("SKILL:")) {
        const skill = label.slice(6);
        return `${who}가 ${skill}${target ? `을(를) ${target}에게` : "을(를)"} 쓴다.${reason}${note}`;
      }
      if (label.startsWith("MOVE:")) return `${who}가 ${label.endsWith("back") ? "후열로" : "전열로"} 움직인다.${reason}`;
      if (label === "ATTACK") return `${who}가 ${target}을(를) ${ACTION_KO.ATTACK}.${reason}${note}`;
      return `${who}가 ${ACTION_KO[label] ?? label}.${reason}`;
    }
    case "resolution": {
      const r = p as unknown as Resolution;
      return narrateResolution(r, names);
    }
    case "boss_adapt": {
      return `${who}가 ${ADAPT_KO[String(p.pattern)] ?? String(p.pattern)}을 읽었다 — ${COUNTER_KO[String(p.counter)] ?? String(p.counter)}.`;
    }
    case "replan_trigger":
      return `${TRIGGER_KO[String(p.trigger)] ?? String(p.trigger)} — ${p.detail}. 단장이 판을 다시 본다.`;
    case "abandon": {
      const v = Math.round(Number(p.odds) * 100);
      return `단장이 결정한다: "${p.rationale}" (승산 ${v}%). 전원 철수.`;
    }
    case "flee":
      return p.success ? `${who}가 전장을 벗어났다.` : `${who}가 빠져나가지 못했다.`;
    case "summon":
      return `갱도가 흔들리고 ${p.name}이(가) 일어선다.`;
    case "mission_end": {
      const r = p as unknown as MissionResult;
      const outcome = OUTCOME_KO[r.outcome] ?? r.outcome;
      const dead = r.dead.length ? ` 쓰러진 자: ${r.dead.map((d) => nameOf(d, names)).join(", ")}.` : "";
      const fled = r.fled.length ? ` 빠져나온 자: ${r.fled.map((d) => nameOf(d, names)).join(", ")}.` : "";
      return `${r.turns}턴 만에 ${outcome}.${dead}${fled}`;
    }
    case "intermission_start":
      return "전투가 끝났다. 용병단은 야영지로 돌아온다.";
    case "directive":
      return `단주가 ${who}에게 지시한다: ${p.category}.`;
    case "train_compliance": {
      const pct = Math.round(Number(p.probability) * 100);
      return p.verdict === "refuse"
        ? `${who}는 지시를 따르지 않는다 (순응 확률 ${pct}%).`
        : `${who}는 지시를 ${p.verdict === "partial" ? "절반만 " : ""}따른다 (순응 확률 ${pct}%).`;
    }
    case "train_result":
      return String(p.narration ?? `${who}의 하루가 지났다.`);
    case "life_event":
      return String(p.narration ?? `${who}에게 일이 생겼다.`);
    case "param_diff": {
      const delta = p.delta as Record<string, number>;
      const parts = Object.entries(delta).map(([k, v]) => `${k} ${v > 0 ? "+" : ""}${v}`);
      return `${who}가 변했다: ${parts.join(", ")}.`;
    }
    case "growth_points":
      return `단주가 성장 포인트 ${p.granted}점을 받았다.`;
    case "advice":
      return `단장의 경고: "${p.message}"`;
    case "run_end": {
      const outcomes = (p.outcomes as string[]).map((o) => OUTCOME_KO[o as MissionResult["outcome"]] ?? o);
      return `계약이 끝났다. 결과: ${outcomes.join(" · ")}.`;
    }
    default:
      return `${e.kind}`;
  }
}

function narrateResolution(r: Resolution, names: Names): string {
  const who = nameOf(r.actor, names);
  if (r.action === "FLEE") return r.flee_success ? `${who}가 몸을 돌려 달아났다.` : `${who}의 발이 잡혔다.`;
  if (r.action === "DEFEND") return `${who}가 몸을 낮춘다.`;
  if (r.action === "WAIT") return `${who}가 숨을 고른다.`;
  if (r.action.startsWith("MOVE")) return `${who}가 자리를 옮긴다.`;
  if (r.healed > 0) return `${who}의 손길에 ${nameOf(r.target, names)}의 상처가 ${r.healed}만큼 아문다.`;
  if (r.strikes.length === 0) {
    const skill = r.action.startsWith("SKILL:") ? r.action.slice(6) : r.action;
    return `${who}의 ${skill}이(가) 전장에 퍼진다.`;
  }
  const parts = r.strikes.map((s) => {
    const t = nameOf(s.target, names);
    if (!s.hit) return `${t}에게는 빗나갔다`;
    const crit = s.crit ? " 급소를 찔러" : "";
    const killed = s.killed ? ` — ${t}이(가) 쓰러진다` : "";
    return `${t}에게${crit} ${s.damage}의 피해${killed}`;
  });
  const note = r.notes.length ? ` (${r.notes[0]})` : "";
  return `${who}: ${parts.join(", ")}.${note}`;
}
