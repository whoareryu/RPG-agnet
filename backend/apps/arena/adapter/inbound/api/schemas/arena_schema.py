"""HTTP 요청/응답 스키마. 도메인 검증(포인트 총량·출전 인원)은 core/content 가 한다 —
여기는 모양만 본다."""

from typing import Literal

from pydantic import BaseModel, Field


class CreateRunRequest(BaseModel):
    lineup: list[str] = Field(min_length=1, max_length=5)
    allocations: dict[str, dict[str, int]] = Field(default_factory=dict)
    classes: dict[str, str] = Field(default_factory=dict)
    genders: dict[str, Literal["female", "male"]] = Field(default_factory=dict)
    orchestrator: bool = True
    adaptation: bool = True
    seed: int | None = None
    missions: Literal[1, 2] = 1


class CreateRunResponse(BaseModel):
    run_id: str
    seed: int
    model: str


class DirectivesRequest(BaseModel):
    """인터미션 입력(B단계). 지시 카테고리 + 성장 포인트 분배."""

    directives: dict[str, Literal["train", "rest", "study", "leisure"]] = Field(
        default_factory=dict
    )
    growth: dict[str, dict[str, int]] = Field(default_factory=dict)
