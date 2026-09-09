"""환경변수로 모델을 고른다 (설계 §3.4). RPG_MODEL=fake|replay|gemini|anthropic. 기본 fake.

실모델 어댑터는 선택 의존성이라 여기서 지연 import 한다 — 설치돼 있지 않아도
fake 로는 돌아야 한다.
"""

import os

from apps.arena.adapter.outbound.strategies.harness.harness import Harness
from apps.arena.adapter.outbound.strategies.llm.fake import FakeModel
from apps.arena.adapter.outbound.strategies.llm.paced import PacedModel
from apps.arena.domain.constants.balance import MAX_CALLS
from apps.arena.domain.ports.ports import DecisionModel


def model_name_from_env() -> str:
    return os.environ.get("RPG_MODEL", "fake").lower()


def build_model(name: str | None = None) -> DecisionModel:
    name = name or model_name_from_env()
    if name == "fake":
        return FakeModel()
    if name == "gemini":
        from apps.arena.adapter.outbound.strategies.llm.gemini import GeminiModel

        return GeminiModel()
    if name == "anthropic":
        from apps.arena.adapter.outbound.strategies.llm.anthropic import AnthropicModel

        return AnthropicModel()
    raise ValueError(f"모르는 모델: {name} (fake|gemini|anthropic)")


def pace_seconds() -> float:
    """RPG_PACE_S — decide() 한 번마다 쉬는 시간(초). 기본 0.

    Fake 는 한 판을 수백 ms 에 끝낸다. 그러면 뿔피리를 누를 시간이 없다
    (기획서 v3 §8.2). 배포 데모에서는 0.2~0.3 을 준다. 실모델은 이미
    느리므로 0 이다.
    """
    try:
        return float(os.environ.get("RPG_PACE_S", "0"))
    except ValueError:
        return 0.0


def build_harness(name: str | None = None, max_calls: int | None = None) -> Harness:
    """모든 경로가 하네스를 거친다 — 스키마 검증·재시도·폴백·호출 계수."""
    limit = max_calls or int(os.environ.get("RPG_MAX_CALLS", MAX_CALLS))
    model = build_model(name)
    pace = pace_seconds()
    if pace:
        model = PacedModel(model, pace)
    return Harness(model, FakeModel(), max_calls=limit)
