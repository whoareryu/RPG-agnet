# QA 라운드 2 — 마일스톤 5~7: API · 프론트 2패널 · 실험 러너

- 검사 대상 커밋: `7fdfd92` (브랜치 stage-a)
- 범위: `backend/api/**`, `backend/eval/**`, `frontend/**`, 그리고 라운드 1 수정분(`core`·`adapters`) 재검
- 아직 없는 것: 인터미션(마일스톤 8) · 실모델 어댑터 · 배포(마일스톤 9). 부재는 발견이 아니다.
- 검증: `cd backend && uv run ruff check . && uv run pytest -q` → 306 passed / `cd frontend && npm test && npx tsc --noEmit` → 12 passed, tsc OK
- 실동작 확인: uvicorn + next start 로 `/` `/roster` `/experiments` `/battle/[run]` `/result/[run]` 200, SSE 376 이벤트 done 까지

## 발견
