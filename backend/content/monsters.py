"""에르덴 변경의 적 (설계 §2.4). 진영 대칭 엔진의 B 진영 정의."""

from content.classes import ARMORS, SKILLS, WEAPONS
from core.types import Body, EnemyDef, EnemyUnitDef, Equipment, SkillDef, Stats

발톱 = Equipment("썩은 발톱", 1, 0, 1, 8, "physical")
주먹 = Equipment("강철 주먹", 3, 0, 1, 18, "physical")
잔해 = Equipment("잔해 덩어리", 2, 0, 1, 9, "physical")
부패의_손길 = SkillDef("부패의 손길", 8, "magic", 9, "enemy", "damage")
분쇄 = SkillDef("분쇄", 12, "physical", 22, "enemy", "damage")
진동 = SkillDef("갱도 진동", 14, "physical", 8, "all_enemies", "damage")

GHOUL_PACK = EnemyDef(
    name="늪지 구울 무리",
    description="늪에 버려진 시체들이 일어섰다. 셋이 함께 움직이고, 뒤의 것은 주문을 웅얼거린다.",
    units=(
        EnemyUnitDef(
            "ghoul_a",
            "구울 A",
            Stats(10, 7, 9, 4, 3, 5),
            Body(170, "normal", 60),
            발톱,
            ARMORS["가죽 갑옷"],
            (),
            "front",
        ),
        EnemyUnitDef(
            "ghoul_b",
            "구울 B",
            Stats(10, 8, 9, 4, 3, 5),
            Body(165, "slim", 50),
            발톱,
            ARMORS["가죽 갑옷"],
            (),
            "front",
        ),
        EnemyUnitDef(
            "rotten_priest",
            "썩은 사제",
            Stats(6, 6, 8, 11, 6, 5),
            Body(172, "slim", 52),
            WEAPONS["성표"],
            ARMORS["로브"],
            (부패의_손길, SKILLS["치유"]),
            "back",
        ),
    ),
)

VARGAS = EnemyDef(
    name='폐광의 군주 "바르가스"',
    description=(
        "옛 광산 감독관의 사체에 깃든 강철 골렘. 갱도의 잔해를 불러 모으고, "
        "상대가 반복하는 것을 기억한다."
    ),
    units=(
        EnemyUnitDef(
            "vargas",
            "바르가스",
            Stats(16, 9, 18, 8, 10, 8),
            Body(210, "sturdy", 180),
            주먹,
            ARMORS["판금 갑옷"],
            (분쇄, 진동),
            "front",
            is_boss=True,
        ),
    ),
    summon_every=3,
    summon_max=2,
    summon_template=EnemyUnitDef(
        "debris",
        "잔해 수하",
        Stats(9, 5, 8, 2, 2, 5),
        Body(160, "sturdy", 120),
        잔해,
        ARMORS["사슬 갑옷"],
        (),
        "front",
    ),
)
