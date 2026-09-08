"""실험 러너 — 같은 러너를 시드만 바꿔 돌린다 (기획서 §10, 설계 §10).

E1: 조합별 감독 ON/OFF. "감독의 가치는 좋은 조합에서의 승률이 아니라
    나쁜 조합에서의 회복력" (기획서 §8.1).
E2: 보스 적응 ON/OFF.
E3: 성향별 행동 분포 — 같은 전투, 성향 수치만 교체.

전부 Fake 모델로 돈다. 사람도 API 키도 없이 돌아가는 것이 자동 대전의 요점이다
(기획서 §7.3 "평가 도구로는 A단계부터").
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from typing import Any

from adapters.harness.harness import Harness
from adapters.llm.fake import FakeModel
from content.missions import MISSIONS_A
from content.party import build_party
from content.roster import ROSTER_BY_ID
from core.rules.dice import SeededDice
from core.runner import run
from core.trace.sink import ListSink
from core.types import Disposition, MissionSpec, RunConfig
from eval.metrics import aggregate, metrics_of


@dataclass(frozen=True)
class Composition:
    key: str
    label: str
    lineup: tuple[str, ...]
    classes: dict[str, str]


# 기획서 §10.1 의 조합 4종.
COMPOSITIONS: tuple[Composition, ...] = (
    Composition(
        "warriors",
        "전사 몰빵",
        ("garret", "kyle", "thomas"),
        {"kyle": "warrior", "thomas": "warrior"},
    ),
    Composition("balanced", "균등", ("garret", "elaine", "seraphine"), {}),
    Composition(
        "mages", "마법사 몰빵", ("seraphine", "kyle", "thomas"), {"kyle": "mage", "thomas": "mage"}
    ),
    Composition("no_healer", "힐러 없음", ("garret", "seraphine", "thomas"), {}),
)


def _run_once(
    seed: int,
    lineup: tuple[str, ...],
    classes: dict[str, str],
    orchestrator: bool,
    adaptation: bool,
    missions: tuple[MissionSpec, ...] = MISSIONS_A,
    dispositions: dict[str, Disposition] | None = None,
) -> Any:
    cfg = RunConfig(
        seed=seed,
        lineup=lineup,
        allocations={},
        classes=classes,
        genders={},
        orchestrator_on=orchestrator,
        adaptation_on=adaptation,
        missions=missions,
        intermission=False,
    )
    members = build_party(cfg)
    if dispositions:
        members = [
            (replace(c, disposition=dispositions.get(c.id, c.disposition)), b, v)
            for c, b, v in members
        ]
    sink = ListSink()
    run(
        f"eval-{seed}",
        cfg,
        members,
        model_factory=lambda: Harness(FakeModel(), FakeModel()),
        dice_factory=SeededDice,
        sink=sink,
        clock=lambda: "T",
    )
    return metrics_of(sink.events)


Progress = Callable[[str], None]


def e1(seeds: int, progress: Progress | None = None) -> dict[str, Any]:
    """조합 4종 × 감독 ON/OFF × 시드 N."""
    out = []
    for comp in COMPOSITIONS:
        cell = {}
        for side, on in (("on", True), ("off", False)):
            runs = [
                _run_once(s, comp.lineup, comp.classes, orchestrator=on, adaptation=True)
                for s in range(1, seeds + 1)
            ]
            cell[side] = aggregate(runs)
            if progress:
                progress(f"E1 {comp.label} 감독 {side.upper()}: 승률 {cell[side]['win_rate']:.0%}")
        out.append(
            {
                "key": comp.key,
                "label": comp.label,
                "lineup": [ROSTER_BY_ID[i].name for i in comp.lineup],
                **cell,
            }
        )
    return {"experiment": "e1", "seeds": seeds, "model": "fake", "compositions": out}


def e2(seeds: int, progress: Progress | None = None) -> dict[str, Any]:
    """보스 적응 ON/OFF. 같은 시드·같은 조합이라 차이는 적응 하나에서 온다."""
    out = []
    for comp in COMPOSITIONS:
        cell = {}
        for side, on in (("on", True), ("off", False)):
            runs = [
                _run_once(s, comp.lineup, comp.classes, orchestrator=True, adaptation=on)
                for s in range(1, seeds + 1)
            ]
            cell[side] = aggregate(runs)
            if progress:
                progress(f"E2 {comp.label} 적응 {side.upper()}: 승률 {cell[side]['win_rate']:.0%}")
        out.append({"key": comp.key, "label": comp.label, **cell})
    return {"experiment": "e2", "seeds": seeds, "model": "fake", "compositions": out}


# 성향 축 하나만 극단으로 바꾼다. 나머지 축은 0 으로 고정해 축의 효과를 분리한다.
E3_LEVELS = (-80, 0, 80)


def e3(seeds: int, progress: Progress | None = None) -> dict[str, Any]:
    """성향별 행동 분포 — 같은 전투, 성향 수치만 교체(기획서 §10.1 E3)."""
    comp = COMPOSITIONS[1]  # 균등
    out = []
    for axis in ("risk", "sacrifice", "cooperation"):
        rows = []
        for level in E3_LEVELS:
            disp = {
                cid: Disposition(
                    **{
                        **dict.fromkeys(("risk", "cooperation", "planning", "sacrifice"), 0),
                        axis: level,
                    }
                )
                for cid in comp.lineup
            }
            runs = [
                _run_once(
                    s,
                    comp.lineup,
                    comp.classes,
                    orchestrator=True,
                    adaptation=True,
                    dispositions=disp,
                )
                for s in range(1, seeds + 1)
            ]
            agg = aggregate(runs)
            rows.append({"level": level, **agg})
            if progress:
                progress(
                    f"E3 {axis}={level:+}: 이탈 {agg['avg_deviations']}회/판 "
                    f"FLEE {agg['action_share'].get('FLEE', 0):.0%}"
                )
        out.append({"axis": axis, "levels": rows})
    return {"experiment": "e3", "seeds": seeds, "model": "fake", "axes": out}


EXPERIMENTS: dict[str, Callable[..., dict[str, Any]]] = {"e1": e1, "e2": e2, "e3": e3}


def available() -> Iterable[str]:
    return EXPERIMENTS.keys()
