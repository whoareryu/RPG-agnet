"""학습 카드 — 집계와 매칭 (기획서 v3 §8.4).

```
[집계 · 코드]  전투 기록 → 패턴 지표 → 상위 N
[매칭 · 코드]  카드 풀에서 결정론적 선택
[전술 · LLM]   보유 카드를 언제 어떻게 쓸지 (B단계)
```

**집계도 매칭도 결정론이다.** 같은 기록이면 같은 카드가 나온다 — 그러지
않으면 "보스가 배웠다" 가 아니라 "보스가 굴렸다" 가 되고, 인스펙터가 출처를
가리킬 수 없다.

카드 풀은 콘텐츠라 여기서 모른다. 호출자가 넘긴다.
"""

from collections import Counter
from typing import Any

from apps.arena.domain.entities.types import CardDef
from apps.arena.domain.services.battle.state import ActionRecord

Chosen = tuple[CardDef, dict[str, Any]]


def pattern_metrics(history: list[ActionRecord], ranged_ids: set[str]) -> dict[str, Any]:
    """전투 기록에서 지표를 뽑는다. 순수 함수다.

    지표 7종 전량은 B단계다(기획서 v3 §14). 지금은 카드 셋을 고를 만큼만 센다.
    """
    dealt: Counter[str] = Counter()
    for h in history:
        if h.faction == "party" and h.damage > 0:
            dealt[h.actor] += h.damage
    total = sum(dealt.values())
    # 동률이면 먼저 친 쪽 — set 순회는 프로세스마다 순서가 달라 판이 갈린다.
    top = max(dealt, key=lambda a: (dealt[a], -list(dealt).index(a)), default=None)
    return {
        "top_contributor": top,
        "top_ratio": round(dealt[top] / total, 2) if top and total else 0.0,
        "ranged_count": len(ranged_ids),
        "dealt": dict(dealt),
    }


def choose_cards(
    history: list[ActionRecord],
    ranged_ids: set[str],
    forsaken: tuple[str, ...],
    slots: int,
    pool: tuple[CardDef, ...] = (),
) -> list[Chosen]:
    """(카드, 근거) 를 슬롯 수만큼. 근거는 인스펙터가 출처를 가리키는 재료다.

    「섭식」이 먼저 온다. 유저가 **안 한 것**(회수)이 카드가 되어 눈앞에 있는
    것이 이 장치의 심장이다 — 기술 차트가 아니라 죄책감으로 전달된다.
    """
    by_key = {c.key: c for c in pool}
    m = pattern_metrics(history, ranged_ids)
    out: list[Chosen] = []

    if forsaken and "devoured" in by_key:
        card = by_key["devoured"]
        out.append((card, {"member": forsaken[0], "source": card.source}))

    if m["top_contributor"] and "pillar" in by_key:
        card = by_key["pillar"]
        out.append(
            (
                card,
                {
                    "member": m["top_contributor"],
                    "ratio": int(m["top_ratio"] * 100),
                    "source": card.source,
                },
            )
        )

    if m["ranged_count"] and "range" in by_key:
        card = by_key["range"]
        out.append((card, {"count": m["ranged_count"], "source": card.source}))

    return out[:slots]
