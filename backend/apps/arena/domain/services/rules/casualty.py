"""쓰러짐 3분기 판정 (기획서 v3 §6.0).

HP 가 0 이 된 대원은 그 자리에서 죽지 않는다. 전투가 끝난 뒤에야
부상 · 끌려감 · 사망으로 갈린다. 굴림은 Dice 포트를 지난다 — 같은 시드가
같은 사상자 명부를 만들어야 리플레이와 실험이 성립한다.
"""

from typing import Literal

from apps.arena.domain.constants.balance import CASUALTY_TABLE
from apps.arena.domain.ports.ports import Dice

Casualty = Literal["injured", "taken", "dead"]


def resolve_casualty(dice: Dice, tier: str) -> Casualty:
    """1..100 굴림을 표의 누적 경계에 대본다.

    경계를 포함으로 읽는다 — 부상 97 이면 97 까지가 부상이다. 사망이 0% 인
    구간에서는 100 을 굴려도 끌려감에서 멈춘다.
    """
    injured, taken, _dead = CASUALTY_TABLE[tier]
    roll = dice.roll(100)
    if roll <= injured:
        return "injured"
    if roll <= injured + taken:
        return "taken"
    return "dead"
