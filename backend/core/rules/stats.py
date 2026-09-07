"""능력치 분배와 파생치 (기획서 §4.2 · 설계 §13)."""

from core.rules.constants import (
    FREE_POINTS,
    HP_BASE,
    HP_PER_CON,
    STAMINA_BASE,
    STAMINA_PER_CON,
    STAT_BASE,
)
from core.types import STAT_LABELS, STAT_NAMES, Stats


def base_stats() -> Stats:
    return Stats(*([STAT_BASE] * 6))


def allocate(base: Stats, points: dict[str, int]) -> Stats:
    """유저의 자유 포인트 분배. 총량 ≤ FREE_POINTS, 음수 금지, 상한은 Stats 가 본다."""
    for name, p in points.items():
        if name not in STAT_NAMES:
            raise ValueError(f"모르는 능력치: {name}")
        if p < 0:
            raise ValueError(f"{STAT_LABELS[name]} 에 음수 포인트({p})를 줄 수 없다")
    total = sum(points.values())
    if total > FREE_POINTS:
        raise ValueError(f"포인트 총량 {total} 이 상한 {FREE_POINTS} 을 넘는다")
    return base.with_added(**points)


def hp_max(stats: Stats) -> int:
    return HP_BASE + stats.con * HP_PER_CON


def stamina_max(stats: Stats) -> int:
    return STAMINA_BASE + stats.con * STAMINA_PER_CON
