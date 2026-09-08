"""러너 — 미션 N개 + 인터미션 (기획서 §7.1, 설계 §9). N 은 미션 리스트 길이다.

한 판의 루프(설계 §5.2):
  턴 시작 → 소환 → 승산 → 재계획 트리거 → (재계획) → 행동 순서 → 유닛별
  [컨텍스트 → 순응 → 판단 → 해석] → 턴 종료 → 승리 조건

같은 러너를 API 가 SSE 로 흘리고(run_stream), eval 이 시드만 바꿔 수백 번 돌린다.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

from apps.arena.app.use_cases.agents.boss import boss_act, minion_act
from apps.arena.app.use_cases.agents.character import character_act
from apps.arena.app.use_cases.agents.orchestrator import make_plan
from apps.arena.domain.entities.trace_event import TraceEvent, Tracer
from apps.arena.domain.entities.types import (
    Action,
    BuildChoice,
    Character,
    MissionSpec,
    Plan,
    RunConfig,
)
from apps.arena.domain.ports.ports import DecisionModel, Dice, TraceSink
from apps.arena.domain.services.battle.order import turn_order
from apps.arena.domain.services.battle.resolve import end_turn, resolve
from apps.arena.domain.services.battle.state import (
    Battle,
    display_names,
    living,
    outcome,
    unit_from_character,
    unit_from_enemy,
)
from apps.arena.domain.services.judgment.odds import odds
from apps.arena.domain.services.judgment.replan import (
    ReplanState,
    mark_quiet_turn,
    mark_replanned,
    replan_triggers,
)

PartyMember = tuple[Character, BuildChoice, str]  # (캐릭터, 빌드, 말투)


@dataclass(frozen=True)
class MissionResult:
    no: int
    outcome: str
    turns: int
    survivors: tuple[str, ...]
    fled: tuple[str, ...]
    dead: tuple[str, ...]
    calls_used: int
    plans: int
    abandoned: bool


@dataclass
class RunRecord:
    run_id: str
    config: dict[str, Any]
    events: list[TraceEvent] = field(default_factory=list)
    results: list[MissionResult] = field(default_factory=list)


class _Collect:
    """싱크를 감싸 이벤트를 모으고 바깥 싱크에도 흘린다."""

    def __init__(self, inner: TraceSink | None) -> None:
        self.inner = inner
        self.events: list[TraceEvent] = []

    def emit(self, event: TraceEvent) -> None:
        self.events.append(event)
        if self.inner is not None:
            self.inner.emit(event)


def _default_positions(members: list[PartyMember]) -> dict[str, str]:
    """감독 OFF 의 고정 편성(설계 §6.1): AGI 최고 1명 후열, 나머지 전열.

    혼자 나가면 뒤에 설 수 없다 — 앞을 막아 줄 사람이 없다.
    """
    if not members:
        return {}
    if len(members) == 1:
        return {members[0][0].id: "front"}
    fastest = max(members, key=lambda m: m[0].stats.agi)[0].id
    return {m[0].id: ("back" if m[0].id == fastest else "front") for m in members}


def setup_battle(
    mission: MissionSpec, members: list[PartyMember], seed: int, adaptation_on: bool
) -> Battle:
    positions = _default_positions(members)
    units = {}
    for c, build, voice in members:
        units[c.id] = unit_from_character(c, build, "party", positions[c.id], voice=voice)  # type: ignore[arg-type]
    for e in mission.enemy.units:
        units[e.id] = unit_from_enemy(e, "enemy")
    return Battle(
        seed=seed,
        environment=mission.environment,
        units=units,
        adaptation_on=adaptation_on and mission.adaptation_on,
        enemy_def=mission.enemy,
        summon_every=mission.enemy.summon_every,
    )


def _maybe_summon(battle: Battle, tracer: Tracer) -> None:
    e = battle.enemy_def
    if e is None or not battle.summon_every or e.summon_template is None:
        return
    if battle.summoned >= e.summon_max or battle.turn % battle.summon_every != 0:
        return
    boss_alive = any(u.is_boss and u.active for u in battle.units.values())
    if not boss_alive:
        return
    battle.summoned += 1
    unit = unit_from_enemy(e.summon_template, "enemy", suffix=f"_{battle.summoned}")
    battle.units[unit.id] = unit
    tracer.emit(
        "summon", {"unit": unit.id, "name": unit.name, "count": battle.summoned}, actor=unit.id
    )


def _order_retreat(battle: Battle, plan: Plan, odds_value: float, tracer: Tracer) -> None:
    """감독의 포기 — 진영 전체 후퇴(설계 §5.3). 유닛별 FLEE 는 턴 루프가 굴린다."""
    battle.retreat_ordered = True
    tracer.emit(
        "abandon",
        {
            "odds": odds_value,
            "strategy": plan.strategy,
            "rationale": plan.rationale,
            "assessment": plan.assessment,
        },
    )


def _emit_resolution(tracer: Tracer, rec: Any, action: Action, actor: str) -> None:
    tracer.emit("resolution", rec, actor=actor)
    if action.kind == "FLEE":
        tracer.emit(
            "flee",
            {"roll": rec.flee_roll, "needed": rec.flee_needed, "success": rec.flee_success},
            actor=actor,
        )


def play_mission(
    mission: MissionSpec,
    members: list[PartyMember],
    model: DecisionModel,
    dice: Dice,
    tracer: Tracer,
    orchestrator_on: bool,
    adaptation_on: bool,
    seed: int,
) -> MissionResult:
    battle = setup_battle(mission, members, seed, adaptation_on)
    tracer.mission = mission.no
    tracer.turn = 0
    calls_before = getattr(model, "calls_used", 0)
    tracer.emit(
        "mission_start",
        {
            "no": mission.no,
            "name": mission.name,
            "enemy": {
                "name": mission.enemy.name,
                "description": mission.enemy.description,
                "units": [
                    {"id": u.id, "name": u.name, "position": u.position, "is_boss": u.is_boss}
                    for u in mission.enemy.units
                ],
            },
            "environment": battle.environment,
            "party": [
                {
                    "id": u.id,
                    "name": u.name,
                    "class": u.char_class,
                    "hp_max": u.hp_max,
                    "weapon": u.weapon.name,
                    "armor": u.armor.name,
                    "position": u.position,
                }
                for u in living(battle, battle.party)
            ],
            "orchestrator_on": orchestrator_on,
            "adaptation_on": battle.adaptation_on,
        },
    )

    plan: Plan | None = None
    plans = 0
    abandoned = False
    replan = ReplanState()

    if orchestrator_on:
        plan = make_plan(battle, battle.party, model, tracer, reason="initial")
        plans += 1
        if not plan.worth_fighting or plan.strategy == "retreat":
            odds_value, _ = odds(battle, battle.party)
            _order_retreat(battle, plan, odds_value, tracer)
            abandoned = True

    result = None
    while result is None:
        battle.turn += 1
        tracer.turn = battle.turn
        replan.begin_turn(battle.turn)
        _maybe_summon(battle, tracer)

        odds_value, odds_bd = odds(battle, battle.party)
        tracer.emit(
            "odds",
            {
                "value": odds_value,
                "breakdown": odds_bd,
                "threshold": plan.retreat_threshold if plan else None,
            },
        )

        if plan is not None and not battle.retreat_ordered:
            triggers = replan_triggers(replan, odds_value, plan, display_names(battle))
            if triggers:
                for t in triggers:
                    tracer.emit("replan_trigger", {"trigger": t.kind, "detail": t.detail})
                forced = mark_replanned(replan, odds_value, plan, triggers)
                reason = "replan:" + "+".join(t.kind for t in triggers)
                plan = make_plan(battle, battle.party, model, tracer, reason=reason, forced=forced)
                plans += 1
                if not plan.worth_fighting or plan.strategy == "retreat":
                    _order_retreat(battle, plan, odds_value, tracer)
                    abandoned = True
            else:
                mark_quiet_turn(replan)
            # 읽었으니 비운다. 이번 턴이 새 신호를 쌓는다.
            replan.consume_signals()

        order = turn_order(battle, dice)
        tracer.emit(
            "turn_start",
            {"order": [{"unit": uid, "speed": v, "breakdown": bd} for uid, v, bd in order]},
        )

        for uid, _, _ in order:
            unit = battle.units[uid]
            if not unit.active:
                continue
            if unit.faction == battle.party:
                decision = character_act(battle, uid, plan, model, dice, tracer, odds_value)
                if decision.compliance.verdict == "deviate":
                    replan.deviations.append(uid)
                action = decision.action
            elif unit.is_boss:
                action, pattern = boss_act(battle, uid, model, tracer)
                if pattern:
                    replan.adaptations.append(pattern)
            else:
                action = minion_act(battle, uid, tracer)
            rec = resolve(battle, uid, action, dice)
            _emit_resolution(tracer, rec, action, uid)
            result = outcome(battle)
            if result is not None:
                break

        end_turn(battle)
        if result is None:
            result = outcome(battle, end_of_turn=True)

    units = battle.units.values()
    party_units = [u for u in units if u.faction == battle.party]
    res = MissionResult(
        no=mission.no,
        outcome=result,
        turns=battle.turn,
        survivors=tuple(u.id for u in party_units if u.alive),
        fled=tuple(u.id for u in party_units if u.fled),
        dead=tuple(u.id for u in party_units if not u.alive),
        calls_used=getattr(model, "calls_used", 0) - calls_before,
        plans=plans,
        abandoned=abandoned,
    )
    tracer.emit("mission_end", res)
    return res


ModelFactory = Callable[[], DecisionModel]
DiceFactory = Callable[[int], Dice]
# (멤버, 직전 결과, 모델, 주사위, tracer) → 다음 판에 나갈 멤버.
# core 는 인터미션의 내용을 모른다 — 호출자가 content 와 유저 입력을 묶어 준다.
IntermissionFn = Callable[
    [list[PartyMember], MissionResult, DecisionModel, Dice, Tracer], list[PartyMember]
]


def run(
    run_id: str,
    config: RunConfig,
    members: list[PartyMember],
    model_factory: ModelFactory,
    dice_factory: DiceFactory,
    sink: TraceSink | None = None,
    intermission: IntermissionFn | None = None,
    clock: Callable[[], str] | None = None,
) -> RunRecord:
    collect = _Collect(sink)
    tracer = Tracer(run_id, collect, **({"clock": clock} if clock else {}))
    model = model_factory()
    dice = dice_factory(config.seed)
    record = RunRecord(run_id=run_id, config=_config_payload(config, members))

    tracer.emit("run_start", record.config)
    for i, mission in enumerate(config.missions):
        res = play_mission(
            mission,
            members,
            model,
            dice,
            tracer,
            orchestrator_on=config.orchestrator_on,
            adaptation_on=config.adaptation_on,
            seed=config.seed,
        )
        record.results.append(res)
        # 죽은 사람은 다음 판에 나오지 않는다. 사망은 소멸이다(기획서 §6.6).
        # 인터미션이 없어도 러너가 책임진다 — 예전에는 1판에서 죽은 단원이
        # 2판에 만피로 서 있었다(QA 라운드 1 P0-5).
        members = [m for m in members if m[0].id not in res.dead]
        if not members:
            break
        if i < len(config.missions) - 1 and config.intermission and intermission is not None:
            tracer.mission = mission.no
            tracer.turn = 0
            members = intermission(members, res, model, dice, tracer)
    tracer.mission = 0
    tracer.turn = 0
    tracer.emit(
        "run_end",
        {
            "outcomes": [r.outcome for r in record.results],
            "results": record.results,
            "calls_used": getattr(model, "calls_used", 0),
            "fallbacks": getattr(model, "fallbacks", 0),
        },
    )
    record.events = collect.events
    return record


def run_stream(
    run_id: str,
    config: RunConfig,
    members: list[PartyMember],
    model_factory: ModelFactory,
    dice_factory: DiceFactory,
    intermission: IntermissionFn | None = None,
) -> Iterator[TraceEvent]:
    """이벤트를 발생 순서대로 흘린다. 스레드 없이 제너레이터로 — 호출자가 소비 속도를 정한다."""
    buffer: list[TraceEvent] = []

    class _Buf:
        def emit(self, e: TraceEvent) -> None:
            buffer.append(e)

    # 제너레이터 안에서 run() 을 한 번에 돌리면 스트림이 아니다. 대신 미션 단위로 끊는다:
    # run() 이 끝난 뒤 버퍼를 비우면 되지만 실시간성이 사라진다. 그래서 여기서는
    # run() 을 그대로 쓰고 버퍼를 즉시 흘린다 — 실시간 스트림은 api 가 스레드 + 큐로 만든다.
    record = run(run_id, config, members, model_factory, dice_factory, _Buf(), intermission)
    yield from record.events


def _config_payload(config: RunConfig, members: list[PartyMember]) -> dict[str, Any]:
    return {
        "seed": config.seed,
        # 유저의 방향 결정을 그대로 싣는다. 예전에는 리플레이가 stats 에서
        # 배분을 역산하고 성별은 버렸다 — 성별이 조용히 되돌아갔고, 기본
        # 능력치가 갈라지는 순간(충원·다른 프리셋) 배분도 틀리게 복원된다.
        "allocations": {k: dict(v) for k, v in config.allocations.items()},
        "classes": dict(config.classes),
        "genders": dict(config.genders),
        "model": config.model_name,
        "lineup": list(config.lineup),
        "orchestrator_on": config.orchestrator_on,
        "adaptation_on": config.adaptation_on,
        "mission_count": len(config.missions),
        "missions": [m.name for m in config.missions],
        "intermission": config.intermission,
        "roster": [
            {
                "id": c.id,
                "name": c.name,
                "class": c.char_class,
                "gender": c.gender,
                "body": c.body,
                "stats": c.stats.as_dict(),
                "disposition": c.disposition.as_dict(),
                "life": c.life.note,
                "weapon": b.weapon.name,
                "armor": b.armor.name,
                "build_rationale": b.rationale,
            }
            for c, b, _ in members
        ],
    }
