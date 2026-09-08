#!/usr/bin/env python3
"""docs/trace-samples/one-run.jsonl 을 만든다 — 파이썬과 프론트가 같이 읽는 계약 샘플.

backend/ 에서: uv run python ../scripts/make_trace_sample.py
시드·조합을 고정해 두어 다시 만들어도 같은 파일이 나온다(ts 제외).
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from adapters.harness.harness import Harness  # noqa: E402
from adapters.llm.fake import FakeModel  # noqa: E402
from content.missions import MISSIONS_A  # noqa: E402
from content.party import build_party  # noqa: E402
from core.rules.dice import SeededDice  # noqa: E402
from core.runner import run  # noqa: E402
from core.trace.schema import to_json  # noqa: E402
from core.types import RunConfig  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "docs" / "trace-samples" / "one-run.jsonl"


def main() -> None:
    # 시드 3 · 가렛/일레인/카일: 22턴 동안 이탈 11회 · 보스 적응 · 재계획 · 포기가
    # 전부 나오고, **카일이 딸을 이유로 전장을 벗어나는 장면**이 들어 있다.
    # 데모 시나리오(기획서 §11.3)와 진입 화면 3장면 카드의 재료가 이 한 판에 있다.
    cfg = RunConfig(
        seed=3,
        lineup=("garret", "elaine", "kyle"),
        allocations={},
        classes={},
        genders={},
        orchestrator_on=True,
        adaptation_on=True,
        missions=MISSIONS_A,
        intermission=False,
    )
    rec = run(
        "sample-one-run",
        cfg,
        build_party(cfg),
        model_factory=lambda: Harness(FakeModel(), FakeModel()),
        dice_factory=SeededDice,
        clock=lambda: "2026-09-07T00:00:00.000+00:00",
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(to_json(e) + "\n" for e in rec.events), encoding="utf-8")
    kinds = sorted({e.kind for e in rec.events})
    print(f"{OUT}: {len(rec.events)} events, outcome={rec.results[0].outcome}, kinds={kinds}")


if __name__ == "__main__":
    main()
