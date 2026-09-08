"""미션 정의. 에피소드 길이는 파라미터다(기획서 §7.1) — 리스트 길이가 N 이다."""

from apps.arena.domain.entities.types import MissionSpec
from content.environments import MINE, SWAMP
from content.monsters import GHOUL_PACK, VARGAS

# A단계: 보스전 1판. 로스터 5 / 출전 최대 3(기획서 §7.4).
# 하한이 1 인 이유: 기획서 §7.2 가 "A·B 단계 출전 1~3" 이라 못박았고, §8.1 이
# "게임은 막지 않는다" 이다. 혼자 보스에게 가는 것도 단주의 선택이다.
MISSION_BOSS = MissionSpec(
    no=1,
    name="폐광의 군주",
    enemy=VARGAS,
    environment=MINE,
    lineup_min=1,
    lineup_max=3,
    adaptation_on=True,
)
MISSIONS_A: tuple[MissionSpec, ...] = (MISSION_BOSS,)

# B단계: 일반 전투(적응 OFF) → 인터미션 → 보스전(적응 ON).
MISSION_GHOULS = MissionSpec(
    no=1,
    name="늪지의 구울",
    enemy=GHOUL_PACK,
    environment=SWAMP,
    lineup_min=1,
    lineup_max=3,
    adaptation_on=False,
)
MISSIONS_B: tuple[MissionSpec, ...] = (
    MISSION_GHOULS,
    MissionSpec(
        no=2,
        name="폐광의 군주",
        enemy=VARGAS,
        environment=MINE,
        lineup_min=1,
        lineup_max=3,
        adaptation_on=True,
    ),
)
