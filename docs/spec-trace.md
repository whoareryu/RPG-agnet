# 기획서 조항 ↔ 코드 대조표

- 기준: `docs/기획/기획서_v2_2026-09-06.md` · 설계 `docs/superpowers/specs/2026-09-07-rpg-autonomous-party-design.md`
- 갱신: 2026-09-08 (마일스톤 1~6 + QA 라운드 1 반영, 커밋 `21341b5`)
- 상태: ● 구현 / ○ 부분 / – 타입·스키마만(C단계) / ✗ 없음

## §4 캐릭터 시스템

| 조항 | 설계 | 구현 | 테스트 | 상태 |
|---|---|---|---|---|
| §4.1 지급 → 관찰 → 방향 결정(능력치·클래스·성별) | §4.1 | `content/roster.py`, `content/party.py`, `frontend/app/roster/` | `test_content.py`, `test_api.py` | ● |
| §4.1 신체 주사위 탄생 1회, 불변 | §4.1 | `core/rules/body.py`, `Body` frozen | `test_body.py` | ● |
| §4.1 "육각형이 좋은 게 아니다" / 트롤픽 허용 | §4.3 | `content/classes.py:choose_build`, `core/rules/equipment.py` | `test_content.py::test_마른_캐릭터를_전사로_키워도_막지_않는다` | ● |
| §4.2 능력치 6종이 각각 판단 분기를 만든다 | §4.2 | `core/rules/{stats,combat}.py` | `test_stats.py`, `test_combat.py` | ● |
| §4.2 지혜 = 정보 해상도(프롬프트 마스킹) | §4.6 | `core/judgment/visibility.py` (4단계) | `test_judgment.py::test_지혜가_낮으면_아군_상태가_가려진다` | ● |
| §4.2 행운은 굴림에만, 판단 미개입 | §3.3 | `core/rules/combat.py` (`include_luck`) | `test_boundaries.py::test_행운은_판단에_개입하지_않는다` (AST) | ● |
| §4.3 신체 vs 능력치 경계 · 효율 스펙트럼 | §4.3 | `core/rules/equipment.py` | `test_equipment.py` | ● |
| §4.4 성별은 엔진 영향 0, 표현 레이어만 | §3.3 | `core/agents/narration.py` | `test_boundaries.py::test_성별은_엔진에_닿지_않는다` (AST) | ○ ¹ |
| §4.5 성향 4축 수치, 시드 결정, 유저 불가 | §4.5 | `core/types.Disposition`, `content/roster.py` | `test_disposition.py` | ● |
| §4.5 MBTI 는 표기만, 프롬프트에 금지 | §4.5 | `core/rules/disposition.py:mbti_label` | `test_prompts.py::test_캐릭터_프롬프트에_MBTI_가_없다` | ● |

¹ 성별이 실제로 바꾸는 것이 아직 없다 — `narration.voice()` 의 두 분기가 같은 문자열이다(QA P2-9). 로스터 화면에 셀렉트를 노출 중이라 B단계에서 말투를 가르거나 셀렉트를 감춘다.

## §5 성장 시스템 세 층

| 조항 | 설계 | 구현 | 테스트 | 상태 |
|---|---|---|---|---|
| 방향(능력치) = 유저 | §13 | `core/rules/stats.py:allocate`, `frontend/lib/allocation.ts` | `test_stats.py`, `allocation.test.ts` | ● |
| 세부(무기·스킬) = AI | §2.3 | `content/classes.py:choose_build` (+ `rationale`) | `test_content.py` | ● |
| 통제 밖(컨디션·성격) = 캐릭터 | §6.4 | `core/judgment/compliance.py` | `test_judgment.py` | ● |
| 유저 포인트는 시스템이 뺏지 않는다 | §4.2 | `Stats.with_added` (감소 경로 없음) | `test_types.py` | ● |
| §5.1 육성 턴 · 순응 · 거부 서사("술집") | §7.1 | `core/intermission/` 비어 있음 | — | ✗ **B단계 다음 작업** |

## §6 로스터 생애 주기 (C단계)

| 조항 | 구현 | 상태 |
|---|---|---|
| §6.1 슬롯 상태 모델 | `core/types.Slot` | – |
| §6.2 이탈은 이벤트가 아니라 판단 | — | – |
| §6.3 충원 주사위 · 리롤 없음 | — | – |
| §6.4 대체자 · 포인트 소멸 | `SlotOccupantKind` | – |
| §6.5 복귀 · 관계 감쇄 | — | – |
| §6.6 사망 = 소멸 | `core/runner.py` (다음 판에 제외) | ○ ² |
| §6.7 이벤트 effect 타입 | `core/types.EventEffectKind` | – |

² 죽은 단원이 다음 미션에 나오지 않는 것까지 구현. 사기·트라우마·파급은 C단계.

## §7 미션·캠페인

| 조항 | 설계 | 구현 | 테스트 | 상태 |
|---|---|---|---|---|
| §7.1 에피소드 길이는 파라미터 (A=1, B=2) | §9 | `content/missions.py`, `core/runner.py` | `test_runner.py` | ● |
| §7.1 인터미션이 두 판 사이에 | §7 | `run()` 이 콜백 자리를 갖고 있음, 구현 없음 | — | ✗ **B단계** |
| §7.2 출전 인원 미션별 가변 (A·B: 1~3) | §11.1 | `content/missions.py`, `content/party.py:build_party` | `test_content.py`, `test_api.py` | ● |
| §7.3 진영 대칭 엔진 (보스 = 유닛 1 진영) | §5.1 | `core/battle/state.py` | `test_battle_state.py` | ● |
| §7.3 자동 대전(평가 도구) | §10 | `eval/` 비어 있음 | — | ✗ **A단계 남은 작업** |
| §7.4 로스터 5 / 출전 3 | §2.2 | `content/roster.py` | `test_content.py` | ● |

## §8 오케스트레이터

| 조항 | 설계 | 구현 | 테스트 | 상태 |
|---|---|---|---|---|
| §8.1 받은 패로 최선 · 트롤픽 허용 | §6.1 | `core/agents/orchestrator.py`, `adapters/llm/fake.py` | `test_agents.py`, `test_runner.py::test_트롤픽_전사_셋도_돈다` | ● |
| §8.2 조언은 희소하게 | §6.5 | 상수만(`ADVICE_*`), 발동 코드 없음 | — | ✗ B단계 ○ |
| §8.3 2층 판단(전략/전술) | §6.1·§6.4 | `orchestrator.py` + `character.py` | `test_agents.py` | ● |
| §8.3 재계획 트리거 4종 | §6.3 | `core/judgment/replan.py` | `test_runner.py::test_이탈과_적응이_실제로_재계획을_부른다` | ○ ³ |
| §8.3 포기 판단("싸울 가치가 있는가") | §6.1 | `_order_retreat`, `abandon` 이벤트 | `test_runner.py::test_후퇴가_실제로_발생하는_시드가_있다` | ● |
| §8.3 승산은 계산이 코드, 판단이 LLM | §6.2 | `core/judgment/odds.py` (time-to-kill) | `test_judgment.py` | ● |
| §8.3 환경 시스템 | §5.5 | `content/environments.py`, `core/rules/combat.py` | `test_combat.py` | ● |
| §8.3 보스 in-context 적응 | §5.6 | `core/agents/boss.py` (4규칙) | `test_agents.py` | ● |

³ 환경 변화 트리거는 자리만 있고 발동 조건이 없다(B단계에 환경 이벤트가 없어서). 나머지 3종은 실측으로 발동을 확인했다.

## §9 아키텍처

| 조항 | 구현 | 테스트 | 상태 |
|---|---|---|---|
| 하네스: 스키마 강제 · 검증 · 재시도 | `adapters/harness/` | `test_harness.py` | ● |
| model-agnostic (로컬↔API 교체) | `adapters/llm/select.py` | `test_store_replay.py` | ○ ⁴ |
| 추가① Fake/Replay 어댑터 | `adapters/llm/{fake,replay}.py` | `test_store_replay.py` | ● |
| 추가② 진영 대칭 엔진 | `core/battle/` | `test_battle_state.py` | ● |
| 헥사고날 절충 · 아키텍처 테스트 CI | `core/ports.py`, `tests/test_boundaries.py` | AST 검사 5종 | ● |

⁴ Gemini·Anthropic 어댑터가 아직 없다(마일스톤 9). `select.py` 가 자리를 잡아 두었다.

## §10 평가

| 조항 | 구현 | 상태 |
|---|---|---|
| E1 조합별 감독 ON/OFF | `eval/` 없음 — 수동 측정만 했다 | ✗ **A단계 남은 작업** |
| E2 보스 적응 ON/OFF | 플래그는 있음(`adaptation_on`), 러너 없음 | ✗ B단계 |
| E3 성향별 행동 분포 | — | ✗ B단계 |
| E4 모델 벤치마크 | — | ✗ B단계 |

## §11 데모 / UI

| 조항 | 구현 | 테스트 | 상태 |
|---|---|---|---|
| §11.1 그래픽 없음, 대사+흐름+판정값 | `frontend/app/_ds/parchment.css` 외 | — | ● |
| §11.2 서사 스트림 + 판정 인스펙터 2패널 | `components/{NarrativeStream,Inspector}.tsx` | `trace.test.ts` | ● |
| §11.2 상태 대시보드(B) | — | — | ✗ B단계 |
| §11.2 투표 사용자 진입 화면 | `frontend/app/page.tsx` | — | ● |
| §11.3 Replay 로 빨리감기 | `adapters/llm/replay.py`, `POST /runs/{id}/replay` | `test_api.py` | ● |
| 배포 (9/12 전) | — | — | ✗ **A단계 남은 작업** |

## 지금 남은 A단계(9/20) 작업

1. **E1 실험 러너** (`eval/`) — 기획서 §10.1 이 A단계 ● 로 표시한 유일한 실험이다.
2. **배포** — 제출물이 "배포된 서비스" 다(§1.2). 9/12 전에 실도메인.
3. 실모델 어댑터(Gemini) — A단계에 필수는 아니다(Fake 로 완주한다). §9 "model-agnostic" 의 증거로는 필요하다.

## B단계(10/17) 남은 작업

인터미션(육성 턴·순응·거부 장면·생애 이벤트·성장 포인트) · 대시보드 패널 · 조언 · E2·E3·E4 · MBTI 표현 레이어(이미 있음).
