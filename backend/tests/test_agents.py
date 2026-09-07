from dataclasses import replace

from adapters.llm.fake import FakeModel
from content.classes import choose_build
from content.environments import MINE
from content.monsters import VARGAS
from content.roster import PRESET_ALLOCATIONS, ROSTER_BY_ID
from core.agents.boss import boss_act, detect_adaptation, minion_act
from core.agents.character import action_from, character_act
from core.agents.orchestrator import make_plan
from core.battle.state import ActionRecord, Battle, unit_from_character, unit_from_enemy
from core.rules.dice import FixedDice
from core.rules.stats import allocate
from core.trace.schema import Tracer
from core.trace.sink import ListSink
from core.types import Action


def _char(cid):
    c = ROSTER_BY_ID[cid]
    return replace(c, stats=allocate(c.stats, PRESET_ALLOCATIONS[cid]))


def _battle(party=("garret", "elaine", "kyle"), adaptation=True):
    units = {}
    for cid in party:
        c = _char(cid)
        units[cid] = unit_from_character(c, choose_build(c), "party", "front")
    for e in VARGAS.units:
        units[e.id] = unit_from_enemy(e, "enemy")
    return Battle(seed=1, environment=MINE, units=units, enemy_def=VARGAS, adaptation_on=adaptation)


def _tracer():
    sink = ListSink()
    return Tracer("t", sink, clock=lambda: "T"), sink


class 고정모델:
    name = "fixed"

    def __init__(self, data):
        self.data = data

    def decide(self, role, prompt, schema):
        return dict(self.data)


# ─── 단장 ─────────────────────────────────────────────────────────────


def test_감독은_힐러가_없으면_속공을_고르고_편성을_반영한다():
    b = _battle(party=("garret", "seraphine", "kyle"))
    tracer, sink = _tracer()
    plan = make_plan(b, "party", FakeModel(), tracer, "initial")
    assert plan.strategy == "rush" and plan.worth_fighting
    assert b.units["kyle"].position == "back" and b.units["garret"].position == "front"
    assert sink.of_kind("plan")[0].payload["reason"] == "initial"


def test_싸울_가치가_없다면서_다른_전략을_내면_후퇴로_고정한다():
    b = _battle()
    tracer, sink = _tracer()
    m = 고정모델(
        {
            "assessment": "x",
            "worth_fighting": False,
            "strategy": "rush",
            "formation": {"nobody": "front"},
            "focus_target": "ghost",
            "per_unit_directive": {},
            "retreat_threshold": 0.9,
            "rationale": "r",
        }
    )
    plan = make_plan(b, "party", m, tracer, "initial")
    assert (
        plan.strategy == "retreat" and plan.retreat_threshold == 0.45 and plan.focus_target is None
    )
    notes = sink.of_kind("plan")[0].payload["notes"]
    assert len(notes) == 3


# ─── 단원 ─────────────────────────────────────────────────────────────


def test_이탈_판정이면_모델이_따랐다고_해도_이탈이다():
    """설계 §6.4 — 모델이 순응 여부를 뒤집을 수 없다."""
    b = _battle()
    tracer, sink = _tracer()
    b.units["kyle"].hp = 3
    m = 고정모델({"action": "ATTACK", "target": "vargas", "follows_plan": True, "reason": "싸운다"})
    d = character_act(b, "kyle", None, m, FixedDice([1], uniforms=[0.0]), tracer, 0.5)
    assert d.compliance.verdict == "deviate" and d.follows_plan is False
    kinds = [e.kind for e in sink.events]
    assert kinds == ["context", "compliance", "decision"]


def test_모델이_불가능한_행동을_고르면_가장_가까운_것으로_바꾸고_기록한다():
    actions = [Action("ATTACK", "vargas"), Action("DEFEND"), Action("WAIT")]
    a, note = action_from({"action": "ATTACK", "target": "ghost"}, actions)
    assert a == Action("ATTACK", "vargas") and note
    a, note = action_from({"action": "SKILL", "skill": "화염구"}, actions)
    assert a == Action("WAIT") and note


def test_감독_OFF_에서도_단원은_행동한다():
    b = _battle()
    tracer, _ = _tracer()
    d = character_act(b, "garret", None, FakeModel(), FixedDice([1], uniforms=[0.99]), tracer, None)
    assert d.action.kind in ("ATTACK", "SKILL")
    assert d.follows_plan is False  # 방침이 없으니 "따랐다"도 없다


def test_Fake_단원은_방침의_집중_목표를_친다():
    b = _battle()
    tracer, _ = _tracer()
    plan = make_plan(b, "party", FakeModel(), tracer, "initial")
    d = character_act(b, "garret", plan, FakeModel(), FixedDice([1], uniforms=[0.99]), tracer, 0.5)
    assert d.action.target == plan.focus_target or d.action.kind == "SKILL"
    assert d.follows_plan


# ─── 보스 ─────────────────────────────────────────────────────────────


def _history(b, actor, turns, target="vargas", kind="physical", dmg=10, action="ATTACK", healed=0):
    for t in turns:
        b.history.append(
            ActionRecord(t, actor, "party", action, target, kind if dmg else None, dmg, healed)
        )


def test_같은_아군이_3턴_연속_공격하면_집중_타격_적응():
    b = _battle()
    b.turn = 4
    _history(b, "garret", [1, 2, 3])
    _history(b, "kyle", [1, 2, 3], dmg=0, action="DEFEND")
    pattern, ev = detect_adaptation(b, "vargas")
    assert pattern == "repeat_attacker" and ev["actor"] == "garret"


def test_마법_위주면_결계_적응():
    b = _battle()
    b.turn = 4
    _history(b, "seraphine", [1, 2], kind="magic", dmg=30, action="SKILL:화염구")
    _history(b, "garret", [3], dmg=5)
    _history(b, "kyle", [1, 2, 3], dmg=0, action="DEFEND")
    pattern, _ = detect_adaptation(b, "vargas")
    # 가렛은 1턴만 쳤으니 repeat 아님. magic 60/65 ≥ 0.6.
    assert pattern == "magic_heavy"


def test_치유_2회면_치유자_타격_적응():
    b = _battle()
    b.turn = 4
    _history(b, "elaine", [1, 2], target="garret", dmg=0, action="SKILL:치유", healed=20)
    _history(b, "garret", [3], dmg=5)
    _history(b, "kyle", [1, 2, 3], dmg=0, action="DEFEND")
    assert detect_adaptation(b, "vargas")[0] == "healing"


def test_방어_위주면_소환_가속_적응():
    b = _battle()
    b.turn = 4
    _history(b, "garret", [1, 2, 3], dmg=0, action="DEFEND")
    _history(b, "kyle", [1, 2, 3], dmg=0, action="DEFEND")
    assert detect_adaptation(b, "vargas")[0] == "turtle"


def test_적응_OFF_면_적응하지_않고_ON_이면_boss_adapt_가_남는다():
    for on in (False, True):
        b = _battle(adaptation=on)
        b.turn = 4
        b.summon_every = 3
        _history(b, "garret", [1, 2, 3])
        tracer, sink = _tracer()
        action, pattern = boss_act(b, "vargas", FakeModel(), tracer)
        assert (pattern is not None) == on
        assert (len(sink.of_kind("boss_adapt")) == 1) == on
        if on:
            assert b.boss_focus == "garret" and action.target == "garret"


def test_같은_패턴은_창_안에서_한_번만():
    b = _battle()
    b.turn = 4
    _history(b, "garret", [1, 2, 3])
    b.boss_adaptations.append((3, "repeat_attacker"))
    assert detect_adaptation(b, "vargas")[0] is None


def test_수하는_모델_없이_가장_약한_적을_친다():
    b = _battle()
    b.units["kyle"].hp = 5
    tracer, sink = _tracer()
    a = minion_act(b, "vargas", tracer)  # 보스를 수하 정책으로 돌려도 동작한다
    assert a.target == "kyle" and a.kind in ("ATTACK", "SKILL")
    assert sink.of_kind("decision")[0].payload["model"]["model"] == "policy"
