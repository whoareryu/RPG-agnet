"""미션 정의. 에피소드 길이는 파라미터다(기획서 §7.1) — 리스트 길이가 N 이다."""

from content.environments import MINE, SWAMP
from content.monsters import GHOUL_PACK, VARGAS
from core.types import MissionSpec

# A단계: 보스전 1판. 출전 3(기획서 §7.4 "로스터 5 / 출전 3").
MISSION_BOSS = MissionSpec(
    no=1,
    name="폐광의 군주",
    enemy=VARGAS,
    environment=MINE,
    lineup_min=3,
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
    lineup_min=3,
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
        lineup_min=3,
        lineup_max=3,
        adaptation_on=True,
    ),
)
