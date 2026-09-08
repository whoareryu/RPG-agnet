#!/usr/bin/env python3
"""docs/trace-samples/one-run.jsonl 을 만든다 — 파이썬과 프론트가 같이 읽는 계약 샘플.

backend/ 에서: uv run python ../scripts/make_trace_sample.py
시드·조합을 고정해 두어 다시 만들어도 같은 파일이 나온다(ts 제외).
"""

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from apps.arena.adapter.outbound.strategies.harness.harness import Harness  # noqa: E402
from apps.arena.adapter.outbound.strategies.llm.fake import FakeModel  # noqa: E402
from content.missions import MISSIONS_A  # noqa: E402
from content.party import build_party  # noqa: E402
from apps.arena.adapter.outbound.strategies.dice import SeededDice  # noqa: E402
from apps.arena.app.use_cases.runner import run  # noqa: E402
from apps.arena.domain.entities.trace_event import judgment_view  # noqa: E402
from apps.arena.domain.entities.types import RunConfig  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "docs" / "trace-samples" / "one-run.jsonl"


def main() -> None:
    ap = argparse.ArgumentParser(description="트레이스 계약 샘플 생성")
    # CI 가 프로세스 간 결정론을 재는 데 쓴다 — 파일을 건드리지 않고 표준출력으로.
    ap.add_argument(
        "--stdout",
        action="store_true",
        help="파일 대신 표준출력으로 판정 뷰를 낸다 (CI 의 프로세스 간 결정론 비교용)",
    )
    args = ap.parse_args()

    # 시드 1 · 가렛/카일/세라핀: 16턴 동안 이탈 8회 · 보스 적응 · 재계획 · 포기가
    # 전부 나오고, **카일이 딸을 이유로 전장을 벗어나는 장면**과 지혜 마스킹이
    # 걸린 판단이 함께 들어 있다. 데모 시나리오(기획서 §11.3)와 진입 화면
    # 3장면 카드의 재료가 이 한 판에 있다.
    # 시드 9: 클래스 개편(2026-09-08) 뒤로 시드 1 은 승리로 끝나 이탈 장면이
    # 사라졌다. flee·abandon 이 함께 나오는 판으로 다시 골랐다.
    cfg = RunConfig(
        seed=9,
        lineup=("garret", "kyle", "bern"),
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
    if args.stdout:
        # 판정 뷰만 낸다 — ts 와 timing 은 매번 다르고 판단이 아니다(설계 §3.4).
        for e in rec.events:
            view = json.dumps(judgment_view(e), ensure_ascii=False, sort_keys=True)
            sys.stdout.write(view + "\n")
        return

    # 파일은 픽스처다. 측정한 시간을 0 으로 눕혀 다시 만들어도 같은 바이트가
    # 나오게 한다 — 그러지 않으면 재생성할 때마다 git diff 가 소음으로 찬다.
    body = ""
    for e in rec.events:
        d = asdict(e)
        if isinstance(d["payload"].get("timing"), dict):
            d["payload"]["timing"] = {"latency_ms": 0.0}
        body += json.dumps(d, ensure_ascii=False) + "\n"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(body, encoding="utf-8")
    kinds = sorted({e.kind for e in rec.events})
    print(f"{OUT}: {len(rec.events)} events, outcome={rec.results[0].outcome}, kinds={kinds}")


if __name__ == "__main__":
    main()
