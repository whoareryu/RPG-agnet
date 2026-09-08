"""하네스 — 스키마 강제 · 검증 · 재시도 · 폴백 · 호출 계수 (기획서 §9, 설계 §3.5).

모델 포트를 감싼다. 검증에 실패하면 오류 문장을 프롬프트 끝에 붙여 다시 묻고,
그래도 실패하면 폴백(Fake)으로 답하고 `_meta.fallback=true` 를 남긴다.
호출 상한을 넘으면 모델을 부르지 않고 폴백으로 간다 — 전투 1판 = 100~300 호출
(기획서 §7.1)의 비용 통제.
"""

import time
from typing import Any

from adapters.harness.validate import validate
from core.ports import DecisionModel, JsonSchema, Role
from core.rules.constants import HARNESS_RETRIES, MAX_CALLS


class Harness:
    def __init__(
        self,
        model: DecisionModel,
        fallback: DecisionModel,
        max_calls: int = MAX_CALLS,
        retries: int = HARNESS_RETRIES,
    ) -> None:
        self._model = model
        self._fallback = fallback
        self._max_calls = max_calls
        self._retries = retries
        self.calls_used = 0
        self.fallbacks = 0

    @property
    def name(self) -> str:
        return self._model.name

    def decide(self, role: Role, prompt: str, schema: JsonSchema) -> dict[str, Any]:
        t0 = time.perf_counter()
        attempts = 0
        errors: list[str] = []
        if self.calls_used >= self._max_calls:
            return self._use_fallback(role, prompt, schema, attempts, "budget", t0)

        current = prompt
        for _ in range(self._retries + 1):
            attempts += 1
            self.calls_used += 1
            try:
                data = self._model.decide(role, current, schema)
            except Exception as e:  # noqa: BLE001 — 모델 장애는 폴백으로 흡수한다
                errors = [f"모델 오류: {type(e).__name__}: {e}"]
            else:
                errors = (
                    validate(data, schema) if isinstance(data, dict) else ["응답이 객체가 아니다"]
                )
                if not errors:
                    self._stamp(data, self._model.name, False, attempts, None, t0)
                    return data
            current = (
                prompt
                + "\n\n직전 응답이 형식에 맞지 않았다:\n- "
                + "\n- ".join(errors)
                + "\n다시 JSON 으로만 답하라."
            )
        return self._use_fallback(role, prompt, schema, attempts, "; ".join(errors), t0)

    def _use_fallback(
        self, role: Role, prompt: str, schema: JsonSchema, attempts: int, reason: str, t0: float
    ) -> dict[str, Any]:
        self.fallbacks += 1
        data = self._fallback.decide(role, prompt, schema)
        # 폴백 응답도 검증한다. 폴백이 스키마를 깨면 코어가 KeyError 로 죽는데,
        # 그때 원인이 "모델이 이상했다" 로 보이면 안 된다 — 폴백이 깨진 건 우리 버그다.
        errors = validate(data, schema) if isinstance(data, dict) else ["폴백 응답이 객체가 아니다"]
        if errors:
            raise RuntimeError(f"폴백({self._fallback.name})이 {role} 스키마를 어겼다: {errors}")
        self._stamp(data, self._fallback.name, True, attempts, reason, t0)
        return data

    @staticmethod
    def _stamp(
        data: dict[str, Any],
        model: str,
        fallback: bool,
        attempts: int,
        reason: str | None,
        t0: float,
    ) -> None:
        """판정 메타와 시간 메타를 **나눠서** 붙인다.

        latency_ms 가 _meta 안에 있으면 그 값이 트레이스 payload 에 실려
        "같은 시드 = 같은 트레이스" 비교가 매번 깨진다(측정한 시간은 매번 다르다).
        결정론 비교의 정본은 payload 에서 `timing` 을 뺀 것이다.
        """
        data["_meta"] = {
            "model": model,
            "fallback": fallback,
            "fallback_reason": reason,
            "attempts": attempts,
        }
        data["_timing"] = {"latency_ms": round((time.perf_counter() - t0) * 1000, 1)}
