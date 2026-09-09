"""미션 정의. 에피소드 길이는 파라미터다(기획서 §7.1) — 리스트 길이가 N 이다.

A단계(9/20)는 두 판이다(2026-09-08 팀 결정 ①):
  6회차 야습 대응 — 놀 등장. 뿔피리 순간과 끌려감이 여기서 나온다
  5회차 성장기 미노타우루스 — 첫 보스 대치

회차 번호가 순서와 어긋나는 것은 의도다. 15출동 중 **어느 판을 잘라 냈는지**가
보이는 편이 낫다(기획서 v3 §7.1 "A·B 는 N 만 낮춘다").
"""

from apps.arena.domain.entities.types import MissionSpec
from content.environments import MINE, SWAMP
from content.monsters import GNOLL_PACK, JUVENILE_MINOTAUR

# 6회차 — 여름. 놀이 처음 나온다. 밤·시야 제한.
# "누굴 뒤에 두는가" 가 처음 문제가 되는 자리다(통합시나리오 §5).
MISSION_NIGHT_RAID = MissionSpec(
    no=6,
    name="야습 대응",
    enemy=GNOLL_PACK,
    environment=SWAMP,
    lineup_min=1,
    lineup_max=3,
    adaptation_on=False,
    casualty_tier="summer",
)

# 5회차 — 굴 입구. 그것이 처음 온다. 이 판은 이긴다. 그것은 물러난다.
MISSION_JUVENILE_BOSS = MissionSpec(
    no=5,
    name="굴 입구",
    enemy=JUVENILE_MINOTAUR,
    environment=MINE,
    lineup_min=1,
    lineup_max=3,
    adaptation_on=True,
    casualty_tier="boss_juvenile",
)

# A단계 제출본: 야습 → 보스전 두 판.
MISSIONS_A: tuple[MissionSpec, ...] = (MISSION_NIGHT_RAID, MISSION_JUVENILE_BOSS)

# B단계: 같은 두 판 사이에 인터미션이 들어간다(러너가 intermission 플래그로 켠다).
MISSIONS_B: tuple[MissionSpec, ...] = MISSIONS_A

# 한 판만 도는 경로. 인터미션 없이 보스전만 본다 — 투표 유저의 첫 접속용이고,
# 실험 러너도 이걸 쓴다. 판 수는 파라미터라는 원칙이 여기서 지켜진다(기획서 §7.1).
MISSIONS_SINGLE: tuple[MissionSpec, ...] = (MISSION_JUVENILE_BOSS,)
