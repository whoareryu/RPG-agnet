"""환경변수로 모델을 고른다 (설계 §3.4). RPG_MODEL=fake|replay|gemini|anthropic. 기본 fake.

실모델 어댑터는 선택 의존성이라 여기서 지연 import 한다 — 설치돼 있지 않아도
fake 로는 돌아야 한다.
"""

import os

from adapters.harness.harness import Harness
from adapters.llm.fake import FakeModel
from core.ports import DecisionModel
from core.rules.constants import MAX_CALLS


def model_name_from_env() -> str:
    return os.environ.get("RPG_MODEL", "fake").lower()


def build_model(name: str | None = None) -> DecisionModel:
    name = name or model_name_from_env()
    if name == "fake":
        return FakeModel()
    if name == "gemini":
        from adapters.llm.gemini import GeminiModel

        return GeminiModel()
    if name == "anthropic":
        from adapters.llm.anthropic import AnthropicModel

        return AnthropicModel()
    raise ValueError(f"모르는 모델: {name} (fake|gemini|anthropic)")


def build_harness(name: str | None = None, max_calls: int | None = None) -> Harness:
    """모든 경로가 하네스를 거친다 — 스키마 검증·재시도·폴백·호출 계수."""
    limit = max_calls or int(os.environ.get("RPG_MAX_CALLS", MAX_CALLS))
    return Harness(build_model(name), FakeModel(), max_calls=limit)
