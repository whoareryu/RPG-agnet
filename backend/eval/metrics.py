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
    """한 판의 트레이스에서 지표를 뽑는다.

    결과·턴·생존자는 **마지막 미션**에서, 판단 횟수(이탈·적응·재계획)와 행동
    분포는 **런 전체**에서 온다. party_size 는 출전 명단 전체라, 미션이 여럿이고
    1판에서 사망자가 나오면 survival_rate 가 "출전한 사람 중 끝까지 살아남은
    비율" 을 뜻한다 — 마지막 미션의 파티 크기가 아니다.
    """
    start = next(e for e in events if e.kind == "run_start")
    end = next(e for e in reversed(events) if e.kind == "mission_end")
    p = end.payload
    party_size = len(start.payload["lineup"])

    # **파티의 행동만 센다.** 보스와 수하도 decision 을 내므로 전부 세면 적의
    # 행동이 섞인다 — 실측(시드 3, 균등)에서 decision 98개 중 40개(41%)가 적이었고
    # E3 의 "성향별 행동 분포" 가 그만큼 틀렸다(QA 라운드 2).
    party = set(start.payload["lineup"])
    actions: dict[str, int] = {}
    for e in events:
        if e.kind == "decision" and e.actor in party:
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


def paired(on: list[str], off: list[str]) -> dict[str, Any]:
    """같은 시드로 짝지은 비교 (McNemar).

    ON/OFF 가 같은 시드를 쓰므로 짝을 살릴 수 있다. 비율만 보면 30판에서 3판
    차이가 잡음과 구별되지 않는다 — 짝지으면 같은 판 수로도 훨씬 잘 갈린다.
    p 는 이항 정확검정(양측)이고 외부 의존성 없이 계산한다.
    """
    only_on = sum(1 for a, b in zip(on, off, strict=True) if a == "win" and b != "win")
    only_off = sum(1 for a, b in zip(on, off, strict=True) if a != "win" and b == "win")
    return {
        "games": len(on),
        "only_on_wins": only_on,
        "only_off_wins": only_off,
        "p_value": _binom_two_sided(only_on, only_on + only_off),
    }


def _binom_two_sided(k: int, n: int) -> float:
    """p=0.5 이항 양측검정. n 이 0 이면 차이가 없다는 뜻이라 1.0."""
    if n == 0:
        return 1.0
    from math import comb

    total = 2**n
    k = min(k, n - k)
    tail = sum(comb(n, i) for i in range(k + 1))
    return round(min(1.0, 2 * tail / total), 4)
