"""클래스 5종 · 무기 · 갑옷 · 스킬 · AI 세부 층의 빌드 선택 (설계 §2.3).

성직자를 더한 이유: E1 의 "힐러 없음" 조합이 성립하려면 힐러가 있어야 한다.

choose_build 는 기획서 §5 "세부" 층이다 — 무기·스킬은 유저가 정하지 않고
캐릭터의 신체·능력치·클래스를 보고 정해진다. A단계는 코드 휴리스틱이고
그 이유가 rationale 로 인스펙터에 남는다.
"""

from dataclasses import dataclass

from apps.arena.domain.entities.types import BuildChoice, Character, Equipment, SkillDef

# ─── 무기 ─────────────────────────────────────────────────────────────
WEAPONS: dict[str, Equipment] = {
    "방패와 검": Equipment("방패와 검", 3, 0, 10, 10, "physical", armor=10),
    "워해머": Equipment("워해머", 2, 0, 14, 16, "physical"),
    "쌍검": Equipment("쌍검", 1, 0, 8, 9, "physical"),
    "지팡이": Equipment("지팡이", 1, 0, 4, 6, "magic", ranged=True),
    "마도서": Equipment("마도서", 1, 0, 4, 8, "magic", ranged=True),
    "장궁": Equipment("장궁", 2, 170, 9, 11, "physical", is_long=True, ranged=True),
    "단궁": Equipment("단궁", 1, 0, 6, 8, "physical", ranged=True),
    "석궁": Equipment("석궁", 2, 0, 12, 13, "physical", ranged=True),
    "단검": Equipment("단검", 1, 0, 4, 7, "physical"),
    "투척 나이프": Equipment("투척 나이프", 1, 0, 5, 6, "physical", ranged=True),
    "철퇴": Equipment("철퇴", 2, 0, 10, 11, "physical"),
    "성표": Equipment("성표", 1, 0, 3, 5, "magic", ranged=True),
}

ARMORS: dict[str, Equipment] = {
    "판금 갑옷": Equipment("판금 갑옷", 3, 0, 11, 0, "physical", armor=30),
    "사슬 갑옷": Equipment("사슬 갑옷", 2, 0, 8, 0, "physical", armor=18),
    "가죽 갑옷": Equipment("가죽 갑옷", 1, 0, 4, 0, "physical", armor=8),
    "로브": Equipment("로브", 1, 0, 1, 0, "physical", armor=3),
}

# ─── 스킬 ─────────────────────────────────────────────────────────────
SKILLS: dict[str, SkillDef] = {
    "방패 밀치기": SkillDef("방패 밀치기", 8, "physical", 6, "self", "guard", 2),
    "강타": SkillDef("강타", 10, "physical", 14, "enemy", "damage"),
    "화염구": SkillDef("화염구", 12, "magic", 10, "all_enemies", "damage"),
    "서리 결계": SkillDef("서리 결계", 10, "magic", 0, "all_enemies", "slow", 2),
    "조준 사격": SkillDef("조준 사격", 9, "physical", 12, "enemy", "snipe"),
    "연사": SkillDef("연사", 10, "physical", 6, "enemy", "double"),
    "급소 찌르기": SkillDef("급소 찌르기", 9, "physical", 9, "enemy", "crit", 30),
    "연막": SkillDef("연막", 8, "physical", 0, "all_enemies", "blind", 2),
    "치유": SkillDef("치유", 10, "magic", 0, "ally", "heal", 25),
    "축복": SkillDef("축복", 8, "magic", 0, "all_allies", "bless", 2),
}


@dataclass(frozen=True)
class ClassDef:
    key: str
    label: str
    primary: tuple[str, ...]
    ideal_build: tuple[str, ...]
    ideal_min_height: int
    weapons: tuple[str, ...]
    skills: tuple[str, ...]
    can_heal: bool = False


CLASSES: dict[str, ClassDef] = {
    "warrior": ClassDef(
        "warrior",
        "전사",
        ("str_", "con"),
        ("sturdy",),
        175,
        ("방패와 검", "워해머", "쌍검"),
        ("방패 밀치기", "강타"),
    ),
    "mage": ClassDef(
        "mage",
        "마법사",
        ("int_",),
        ("slim", "normal"),
        0,
        ("지팡이", "마도서"),
        ("화염구", "서리 결계"),
    ),
    "archer": ClassDef(
        "archer",
        "궁수",
        ("agi",),
        ("slim", "normal"),
        165,
        ("장궁", "단궁", "석궁"),
        ("조준 사격", "연사"),
    ),
    "rogue": ClassDef(
        "rogue",
        "도적",
        ("agi", "luck"),
        ("slim",),
        0,
        ("단검", "투척 나이프"),
        ("급소 찌르기", "연막"),
    ),
    "cleric": ClassDef(
        "cleric",
        "성직자",
        ("wis", "int_"),
        ("slim", "normal", "sturdy"),
        0,
        ("철퇴", "성표"),
        ("치유", "축복"),
        can_heal=True,
    ),
}


def choose_build(c: Character) -> BuildChoice:
    """신체·능력치를 보고 무기·갑옷을 고른다. 이유를 문장으로 남긴다."""
    cls = CLASSES[c.char_class]
    b, s = c.body, c.stats
    skills = tuple(SKILLS[k] for k in cls.skills)

    if cls.key == "warrior":
        if b.build == "sturdy" and b.height_cm >= 175:
            return BuildChoice(
                WEAPONS["방패와 검"],
                ARMORS["판금 갑옷"],
                skills,
                "건장하고 키가 크다. 방패를 들고 전열을 막는다.",
            )
        if s.str_ >= 14 and b.height_cm < 175:
            return BuildChoice(
                WEAPONS["워해머"],
                ARMORS["사슬 갑옷"],
                skills,
                "키가 작고 힘이 세다. 긴 무기는 비효율 — 워해머로 짧게 세게 친다.",
            )
        if b.build == "slim" and s.agi >= 12:
            return BuildChoice(
                WEAPONS["쌍검"],
                ARMORS["가죽 갑옷"],
                skills,
                "마르고 빠르다. 무거운 갑옷 대신 쌍검으로 딜을 낸다.",
            )
        return BuildChoice(
            WEAPONS["방패와 검"],
            ARMORS["사슬 갑옷"],
            skills,
            "특별한 강점이 없다. 방패와 사슬로 무난하게 버틴다.",
        )
    if cls.key == "mage":
        w = WEAPONS["마도서"] if s.int_ >= 12 else WEAPONS["지팡이"]
        return BuildChoice(
            w,
            ARMORS["로브"],
            skills,
            "지능이 높으면 마도서, 아니면 지팡이. 갑옷은 마법을 방해한다.",
        )
    if cls.key == "archer":
        if b.height_cm >= 170:
            return BuildChoice(
                WEAPONS["장궁"], ARMORS["가죽 갑옷"], skills, "키가 커서 장궁을 제대로 당긴다."
            )
        if s.str_ >= 12:
            return BuildChoice(
                WEAPONS["석궁"],
                ARMORS["가죽 갑옷"],
                skills,
                "키는 작지만 힘이 있다. 석궁이 맞는다.",
            )
        return BuildChoice(
            WEAPONS["단궁"],
            ARMORS["가죽 갑옷"],
            skills,
            "키가 작아 장궁은 비효율. 단궁으로 빠르게 쏜다.",
        )
    if cls.key == "rogue":
        # 행운으로 무기를 고르면 안 된다 — 투척은 원거리라 사거리·편성·거리
        # 페널티가 함께 바뀌고, 그것이 곧 판단이다(기획서 §4.2 "행운은 판단에
        # 개입하지 않는다"). 민첩으로 고른다.
        w = WEAPONS["투척 나이프"] if s.agi >= 12 else WEAPONS["단검"]
        return BuildChoice(
            w, ARMORS["가죽 갑옷"], skills, "가볍게 움직여야 한다. 손이 빠르면 투척, 아니면 단검."
        )
    # cleric
    w = WEAPONS["철퇴"] if s.str_ >= 10 else WEAPONS["성표"]
    a = ARMORS["사슬 갑옷"] if b.build == "sturdy" else ARMORS["가죽 갑옷"]
    return BuildChoice(w, a, skills, "치유가 본분이다. 몸이 버티는 만큼만 갑옷을 입는다.")
