"""실험 CLI.

    uv run python -m eval.run --experiment e1 --seeds 30
    uv run python -m eval.run --experiment e1 --seeds 30 --out eval/out/e1.json

결과를 표로 찍고 JSON 으로도 남긴다. 프론트 /experiments 가 그 JSON 을 읽는다.
"""

import argparse
import json
from pathlib import Path
from typing import Any

from eval.experiments import EXPERIMENTS


def main() -> int:
    ap = argparse.ArgumentParser(description="실험 러너")
    ap.add_argument("--experiment", "-e", default="e1", choices=sorted(EXPERIMENTS))
    ap.add_argument("--seeds", "-n", type=int, default=30)
    ap.add_argument("--out", "-o", type=Path, default=None)
    ap.add_argument("--quiet", "-q", action="store_true")
    args = ap.parse_args()

    progress = None if args.quiet else (lambda line: print(f"  {line}"))
    print(f"{args.experiment} · 시드 {args.seeds}개 · Fake 모델")
    result = EXPERIMENTS[args.experiment](args.seeds, progress)

    print()
    _print_table(result)

    out = args.out or Path("eval/out") / f"{args.experiment}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n→ {out}")
    return 0


def _print_table(result: dict[str, Any]) -> None:
    if result["experiment"] in ("e1", "e2"):
        flag = "감독" if result["experiment"] == "e1" else "적응"
        head = f"{'조합':<12} {flag:<5} {'승률':>5} {'후퇴':>5} {'패배':>5} "
        print(head + f"{'생존':>5} {'평균턴':>6} {'최대호출':>7}")
        print("-" * 60)
        for c in result["compositions"]:
            for side in ("on", "off"):
                a = c[side]
                print(
                    f"{c['label']:<12} {side.upper():<5} {a['win_rate']:>5.0%} "
                    f"{a['retreat_rate']:>5.0%} {a['loss_rate']:>5.0%} "
                    f"{a['survival_rate']:>5.0%} {a['avg_turns']:>6.1f} {a['max_calls']:>7}"
                )
    else:
        for axis in result["axes"]:
            print(f"[{axis['axis']}]")
            for row in axis["levels"]:
                share = row["action_share"]
                print(
                    f"  {row['level']:+4} → 이탈 {row['avg_deviations']:>4.1f}회/판 "
                    f"FLEE {share.get('FLEE', 0):>5.0%} DEFEND {share.get('DEFEND', 0):>5.0%} "
                    f"ATTACK {share.get('ATTACK', 0):>5.0%} 승률 {row['win_rate']:>4.0%}"
                )


if __name__ == "__main__":
    raise SystemExit(main())
