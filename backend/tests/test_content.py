from dataclasses import replace

from content.classes import CLASSES, SKILLS, choose_build
from content.environments import MINE, SWAMP
from content.monsters import VARGAS
from content.roster import PRESET_ALLOCATIONS, PRESET_ROSTER, ROSTER_BY_ID
from core.rules.constants import FREE_POINTS
from core.rules.stats import allocate
from core.types import Body, Disposition


def test_프리셋_다섯은_id_가_유일하고_능력치는_전부_8이다():
    ids = [c.id for c in PRESET_ROSTER]
    assert len(ids) == 5 and len(set(ids)) == 5
    for c in PRESET_ROSTER:
        assert set(c.stats.as_dict().values()) == {8}


def test_프리셋_성향은_설계_표와_같다():
    assert ROSTER_BY_ID["kyle"].disposition == Disposition(-30, 20, 20, -40)
    assert ROSTER_BY_ID["elaine"].disposition == Disposition(10, 70, -10, 80)
    assert ROSTER_BY_ID["kyle"].life.dependents == 1


def test_추천_배분은_전원_18점이다():
    for cid, alloc in PRESET_ALLOCATIONS.items():
        assert sum(alloc.values()) == FREE_POINTS, cid
        allocate(ROSTER_BY_ID[cid].stats, alloc)  # 예외 없이 통과해야 한다


def test_클래스는_다섯이고_스킬은_둘씩이다():
    assert set(CLASSES) == {"warrior", "mage", "archer", "rogue", "cleric"}
    for cls in CLASSES.values():
        assert len(cls.skills) == 2
        for k in cls.skills:
            assert k in SKILLS
    assert CLASSES["cleric"].can_heal


def test_건장하고_큰_전사는_방패를_든다():
    garret = ROSTER_BY_ID["garret"]
    garret = replace(garret, stats=allocate(garret.stats, PRESET_ALLOCATIONS["garret"]))
    assert choose_build(garret).weapon.name == "방패와 검"


def test_키_작고_힘_센_전사는_워해머다():
    """기획서 §5 "키 작고 힘 센 전사 → 긴 창 비효율, 워해머"."""
    c = replace(
        ROSTER_BY_ID["garret"],
        body=Body(165, "normal", 66),
        stats=allocate(ROSTER_BY_ID["garret"].stats, {"str_": 8}),
    )
    assert choose_build(c).weapon.name == "워해머"


def test_마른_캐릭터를_전사로_키워도_막지_않는다():
    """트롤픽 허용(기획서 §4.1). 빌드가 나오고 이유가 붙는다."""
    c = replace(ROSTER_BY_ID["seraphine"], char_class="warrior")
    b = choose_build(c)
    assert b.weapon and b.rationale


def test_환경_수치는_설계와_같다():
    assert SWAMP.speed_penalty_by_weight == {3: -2}
    assert SWAMP.stamina_multiplier == 1.5
    assert SWAMP.damage_modifiers["magic"] == 0.8
    assert MINE.darkness and MINE.range_penalty == 10 and MINE.damage_modifiers["magic"] == 1.1


def test_보스는_유닛_하나와_소환_규칙이다():
    assert len(VARGAS.units) == 1 and VARGAS.units[0].is_boss
    assert VARGAS.summon_every == 3 and VARGAS.summon_max == 2


def test_출전은_1명부터_3명까지다():
    """기획서 §7.2 — A·B 단계 출전 1~3. 혼자 가는 것도 단주의 선택이다."""
    from content.missions import MISSIONS_A, MISSIONS_B

    for m in (*MISSIONS_A, *MISSIONS_B):
        assert (m.lineup_min, m.lineup_max) == (1, 3), m.name


def test_도적_무기는_행운이_아니라_민첩이_고른다():
    """기획서 §4.2 — 행운은 판단에 개입하지 않는다. 투척/단검은 사거리를 바꾼다."""
    from dataclasses import replace

    base = ROSTER_BY_ID["thomas"]
    빠름 = replace(base, stats=replace(base.stats, agi=14, luck=1))
    느림 = replace(base, stats=replace(base.stats, agi=8, luck=20))
    assert choose_build(빠름).weapon.ranged is True
    assert choose_build(느림).weapon.ranged is False
