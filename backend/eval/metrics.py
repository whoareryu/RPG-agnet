"""트레이스 → 지표. 순수 함수 (설계 §10).

실험은 **후처리만으로** 계산되어야 한다 — 러너를 고쳐야 지표가 나오면 실험이
코어를 건드리게 되고, 그것이 기획서 §3.1 이 막으려는 것이다.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from core.trace.schema import TraceEvent


@dataclass(frozen=True)
class RunMetrics:
    outcome: str
    turns: int
    survivors: int
    party_size: int
    dead: int
    fled: int
    calls: int
    plans: int
    abandoned: bool
    deviations: int
    adaptations: int
    replans: int
    fallbacks: int
    actions: dict[str, int]

    @property
    def survival_rate(self) -> float:
        return self.survivors / self.party_size if self.party_size else 0.0


def metrics_of(events: Sequence[TraceEvent]) -> RunMetrics:
    """한 판의 트레이스에서 지표를 뽑는다. 미션이 여럿이면 마지막 미션을 본다."""
    start = next(e for e in events if e.kind == "run_start")
    end = next(e for e in reversed(events) if e.kind == "mission_end")
    p = end.payload
    party_size = len(start.payload["lineup"])
    actions: dict[str, int] = {}
    for e in events:
        if e.kind == "decision":
            label = str(e.payload["label"]).split(":")[0]
            actions[label] = actions.get(label, 0) + 1
    return RunMetrics(
        outcome=str(p["outcome"]),
        turns=int(p["turns"]),
        survivors=len(p["survivors"]),
        party_size=party_size,
        dead=len(p["dead"]),
        fled=len(p["fled"]),
        calls=int(p["calls_used"]),
        plans=int(p["plans"]),
        abandoned=bool(p["abandoned"]),
        deviations=sum(
            1 for e in events if e.kind == "compliance" and e.payload["verdict"] == "deviate"
        ),
        adaptations=sum(1 for e in events if e.kind == "boss_adapt"),
        replans=sum(1 for e in events if e.kind == "replan_trigger"),
        fallbacks=sum(
            1
            for e in events
            if e.kind in ("decision", "plan") and (e.payload.get("model") or {}).get("fallback")
        ),
        actions=actions,
    )


def aggregate(runs: Sequence[RunMetrics]) -> dict[str, Any]:
    """여러 판을 하나의 칸으로. 비율은 판 수로 나눈 값이다."""
    n = len(runs)
    if n == 0:
        return {"games": 0}

    def rate(outcome: str) -> float:
        return round(sum(1 for r in runs if r.outcome == outcome) / n, 3)

    action_total: dict[str, int] = {}
    for r in runs:
        for k, v in r.actions.items():
            action_total[k] = action_total.get(k, 0) + v
    acted = sum(action_total.values()) or 1
    return {
        "games": n,
        "win_rate": rate("win"),
        "retreat_rate": rate("retreat"),
        "loss_rate": rate("lose"),
        "draw_rate": rate("draw"),
        "survival_rate": round(sum(r.survival_rate for r in runs) / n, 3),
        "abandon_rate": round(sum(1 for r in runs if r.abandoned) / n, 3),
        "avg_turns": round(sum(r.turns for r in runs) / n, 1),
        "avg_calls": round(sum(r.calls for r in runs) / n, 1),
        "max_calls": max(r.calls for r in runs),
        "avg_plans": round(sum(r.plans for r in runs) / n, 1),
        "avg_deviations": round(sum(r.deviations for r in runs) / n, 1),
        "avg_adaptations": round(sum(r.adaptations for r in runs) / n, 1),
        "fallbacks": sum(r.fallbacks for r in runs),
        # 성향별 행동 분포(E3)의 재료. 여기서 미리 비율로 만들어 둔다.
        "action_share": {k: round(v / acted, 3) for k, v in sorted(action_total.items())},
    }
