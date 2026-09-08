"""프리셋 로스터 5명 (설계 §2.2). 신체·성향은 지급 시 이미 굴려진 상태다.

데모 장면별 요구 성향(희생형·가장형·수읽기형·보수 기준선·중갑 전사)에
한 명씩 대응한다(기획서 §7.4). 능력치는 전부 기본 8 이고 PRESET_ALLOCATIONS
가 "추천 배분" 이다 — 유저가 재분배한다(A단계: 프리셋 5 + 재분배).
"""

from apps.arena.domain.entities.types import Body, Character, Disposition, LifeContext
from apps.arena.domain.services.rules.stats import base_stats

PRESET_ROSTER: tuple[Character, ...] = (
    Character(
        id="garret",
        name="가렛 발렌",
        gender="male",
        body=Body(188, "sturdy", 96),
        stats=base_stats(),
        disposition=Disposition(risk=20, cooperation=30, planning=40, sacrifice=30),
        char_class="warrior",
        life=LifeContext(0, "폐광 경비대 출신. 가족 없음."),
        backstory="폐광 경비대 출신. 지키는 일에 질려 먼저 치고 들어가는 쪽을 택했다.",
    ),
    Character(
        id="elaine",
        name="일레인 모어",
        gender="female",
        body=Body(166, "normal", 58),
        stats=base_stats(),
        disposition=Disposition(risk=10, cooperation=70, planning=-10, sacrifice=80),
        char_class="bard",
        life=LifeContext(0, "무너진 수도원의 마지막 수련 수녀."),
        backstory="무너진 수도원의 마지막 수련 수녀. 남을 위해 서는 것이 습관이다.",
    ),
    Character(
        id="kyle",
        name="카일 브란트",
        gender="male",
        body=Body(175, "normal", 72),
        stats=base_stats(),
        disposition=Disposition(risk=-30, cooperation=20, planning=20, sacrifice=-40),
        char_class="archer",
        life=LifeContext(1, "두 살 딸이 집에 있다."),
        backstory="두 살 딸이 있다. 위험이 오면 먼저 집을 생각한다.",
    ),
    Character(
        id="bern",
        name="베른 하이트",
        gender="male",
        body=Body(183, "sturdy", 92),
        stats=base_stats(),
        # 세라핀이 갖고 있던 수읽기형(계획 +80) 데모 슬롯을 승계한다(기획서 §7.4).
        disposition=Disposition(risk=-20, cooperation=40, planning=80, sacrifice=20),
        char_class="defender",
        life=LifeContext(0, "성문 수비대에서 십 년."),
        backstory="성문 수비대에서 십 년. 어디가 먼저 뚫릴지 보고 그 자리에 선다.",
    ),
    Character(
        id="thomas",
        name="토마스 헤일",
        gender="male",
        body=Body(169, "slim", 60),
        stats=base_stats(),
        disposition=Disposition(risk=-10, cooperation=10, planning=50, sacrifice=10),
        char_class="rogue",
        life=LifeContext(0, "세금 징수관 출신의 자물쇠 전문가."),
        backstory="세금 징수관 출신의 자물쇠 전문가. 규칙대로 하되 규칙이 위험하면 멈춘다.",
    ),
)

# 추천 배분(합 18). "추천 배분 수락" 버튼의 값이다(기획서 §5) — 조언 시스템과 무관.
PRESET_ALLOCATIONS: dict[str, dict[str, int]] = {
    "garret": {"str_": 6, "con": 8, "wis": 4},
    "elaine": {"wis": 8, "int_": 6, "con": 4},
    "kyle": {"agi": 8, "wis": 4, "con": 4, "luck": 2},
    "bern": {"con": 8, "str_": 5, "wis": 5},
    "thomas": {"agi": 8, "luck": 5, "wis": 5},
}

ROSTER_BY_ID: dict[str, Character] = {c.id: c for c in PRESET_ROSTER}
