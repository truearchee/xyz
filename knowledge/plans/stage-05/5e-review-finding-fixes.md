---
type: session-plan
stage: "05"
session: "5e"
slug: review-finding-fixes
status: executed
created: 2026-06-16
updated: 2026-06-16
spec: knowledge/specs/stage-05/5e-review-finding-fixes.md
report: knowledge/steps/stage-05/5e-review-finding-fixes.md
---

# Session 5e — Implementation Plan — Review Finding Fixes

## Linked documents
- Stage spec: [[specs/stage-05/5-shared-quiz-engine-event-spine]]
- Spec: [[specs/stage-05/5e-review-finding-fixes]]
- Plan: [[plans/stage-05/5e-review-finding-fixes]]
- Report: [[steps/stage-05/5e-review-finding-fixes]]

## Scope confirmation
Fix only the review findings from the Stage 5 audit. This is a repair session over completed Stage 5 work, not a new feature slice.

## Steps
1. Make `tests/test_health.py` use `settings.CORS_ORIGINS[0]` as the allowed origin so local port remaps do not break the backend suite.
2. Add `quiz_generation_job_id(attempt_id)` in `workers/queues.py`; use it in enqueue and RQ liveness; return the job id from enqueue.
3. Change `quiz_attempts.generation_job_id` from UUID to Text in the uncommitted 0016 migration/model, then stamp it after successful enqueue.
4. Add regression tests for generation-job provenance and the missing 5a CHECK negative cases.
5. Update Stage 5 documentation and prior reports' change histories.
6. Run the targeted tests, full backend suite, frontend type-check, then commit all intended Stage 5 files.

## Risks
- The running local DB may still have the previous uncommitted UUID shape for `generation_job_id`. The migration round-trip test recreates the test DB schema from source; if runtime DB state matters, rebuild from migrations rather than relying on the old volume.
- `docker-compose.yml` contains local port-remap changes from the 5d gate standup. Verification should not depend on ignored `.env` values being committed.
