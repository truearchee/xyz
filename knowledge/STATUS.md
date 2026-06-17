# Status

_Last updated: 2026-06-17 — Stage 5 knowledge graph repaired on branch `spec-5`._

## Current state

Stage 5 is **FULLY VERIFIED** on this branch and now has a follow-up review-fix session:

- 5a foundation: quiz/event schema, EventRecorder, pagination envelope, availability read model, DTOs.
- 5b generation/recovery: lazy post-class quiz generation through the shared LLM gateway, stable RQ job id
  `quiz-generate:{attemptId}`, `generation_job_id` stamped after enqueue, reaper liveness wired.
- 5c HTTP surface: availability/start/detail/answer/complete/attempts aggregate.
- 5d UI/gates: student quiz panel, browser gate green, real-provider smoke green and re-confirmed at
  `finish_reason='stop'` after `max_tokens` was raised to 16000.
- 5e review fixes: dynamic CORS health test, generation-job provenance repair, missing CHECK negative
  tests, pagination-doc reconciliation, stale report cleanup.

Current verification from 5e:

```bash
docker compose exec -T backend pytest -q tests/test_health.py
# 4 passed, 4 warnings in 0.02s

docker compose exec -T backend pytest -q tests/test_db_spine.py tests/test_quiz_schema.py tests/test_event_recorder.py tests/test_quiz_schemas_dto.py tests/test_quiz_generation.py tests/test_quiz_endpoints.py
# 61 passed, 15 warnings in 16.57s

docker compose exec -T backend pytest -q
# 442 passed, 126 warnings in 55.20s

docker compose exec -T frontend npx tsc --noEmit
# exit 0
```

## Stage 5 documents

- Stage spec: [[specs/stage-05/5-shared-quiz-engine-event-spine]]
- 5a report: [[steps/stage-05/5a-quiz-foundation]]
- 5a spec: [[specs/stage-05/5a-quiz-foundation]]
- 5a plan: [[plans/stage-05/5a-quiz-foundation]]
- 5b report: [[steps/stage-05/5b-quiz-generation-recovery]]
- 5b spec: [[specs/stage-05/5b-quiz-generation-recovery]]
- 5b plan: [[plans/stage-05/5b-quiz-generation-recovery]]
- 5c report: [[steps/stage-05/5c-answer-feedback-scoring-retake]]
- 5c spec: [[specs/stage-05/5c-answer-feedback-scoring-retake]]
- 5c plan: [[plans/stage-05/5c-answer-feedback-scoring-retake]]
- 5d report: [[steps/stage-05/5d-student-ui-browser-gate]]
- 5d spec: [[specs/stage-05/5d-student-ui-browser-gate]]
- 5d plan: [[plans/stage-05/5d-student-ui-browser-gate]]
- 5d real-provider smoke: [[steps/stage-05/5d-real-provider-smoke]]
- 5e report: [[steps/stage-05/5e-review-finding-fixes]]
- ADRs: [[decisions/adr-040-activity-event-spine]], [[decisions/adr-041-pagination-envelope]],
  [[decisions/adr-042-quiz-availability-computed-read-only]], [[decisions/adr-043-lazy-per-attempt-quiz-generation]],
  [[decisions/adr-044-structured-quiz-output-json-validator-authority]],
  [[decisions/adr-045-airequestlog-decoupled-gateway-generalized]], [[decisions/adr-046-quiz-generation-recovery]]

## Open risks

- **Merge-time migration collision:** Stage 5 uses 0014-0020 while sibling work also used 0014-0016.
  Renumber/rebase one side before landing on `main`.
- **AIRequestLog mid-call crash residual:** still accepted and logged in [[open-questions]]; fixing it
  needs a broader AIRequestLog-to-source linkage, not a 5e repair.

## Environment note

The local `kyiv` Docker stack used for 5e has db/redis internal-only, backend on `localhost:8000`, and
frontend on `localhost:3001`; tests no longer assume the frontend origin is `localhost:3000`.
