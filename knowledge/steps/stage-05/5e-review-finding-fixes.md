---
type: session-report
stage: "05"
session: "5e"
slug: review-finding-fixes
status: complete
created: 2026-06-16
updated: 2026-06-16
spec: knowledge/specs/stage-05/5e-review-finding-fixes.md
plan: knowledge/plans/stage-05/5e-review-finding-fixes.md
---

# Session 5e — Report — Review Finding Fixes

## Linked documents
- Stage spec: [[specs/stage-05/5-shared-quiz-engine-event-spine]]
- Spec: [[specs/stage-05/5e-review-finding-fixes]]
- Plan: [[plans/stage-05/5e-review-finding-fixes]]
- Report: [[steps/stage-05/5e-review-finding-fixes]]
- Prior reports: [[steps/stage-05/5a-quiz-foundation]], [[steps/stage-05/5b-quiz-generation-recovery]], [[steps/stage-05/5d-student-ui-browser-gate]]
- ADRs: [[decisions/adr-041-pagination-envelope]], [[decisions/adr-046-quiz-generation-recovery]]

## What changed
- `tests/test_health.py` now checks the configured first CORS origin (`settings.CORS_ORIGINS[0]`) instead
  of hard-coding `http://localhost:3000`; this closes the full-suite failure in the current `kyiv` stack
  where the frontend is on `localhost:3001`.
- `workers/queues.py` now has one canonical `quiz_generation_job_id(attempt_id)` helper returning
  `quiz-generate:{attemptId}`. Enqueue returns that id; RQ liveness uses the same helper.
- `QuizAttempt.generation_job_id` is stored after successful enqueue. The uncommitted 0016 migration and
  ORM model use text, because RQ job ids are string identities, not UUID rows.
- `test_quiz_generation.py` proves successful enqueue stamps `generation_job_id`.
- `test_quiz_schema.py` now has negative CHECK tests for `quiz_mode`, `failure_category`,
  `question_type`, and `source_type`.
- Stage 5 pagination docs now explicitly reflect ADR-041: the envelope is defined in 5a, while the first
  genuine paginated list consumer is deferred to Stage 6 mistakes-bank or Stage 7 glossary.
- Stale 5d report/open-question wording was reconciled: Gate 1 and Gate 3 both passed; F-5d-1 re-confirmed
  at `finish_reason='stop'`.

## Verification
Rebuilt the backend image before running tests so `docker compose exec` used the current source:
```bash
docker compose build backend
docker compose up -d --no-deps --force-recreate backend worker embedding_worker ai_worker
```

Targeted health regression:
```bash
$ docker compose exec -T backend pytest -q tests/test_health.py
4 passed, 4 warnings in 0.02s
```

Focused Stage 5 and migration spine set:
```bash
$ docker compose exec -T backend pytest -q tests/test_db_spine.py tests/test_quiz_schema.py tests/test_event_recorder.py tests/test_quiz_schemas_dto.py tests/test_quiz_generation.py tests/test_quiz_endpoints.py
61 passed, 15 warnings in 16.57s
```

Full backend suite:
```bash
$ docker compose exec -T backend pytest -q
442 passed, 126 warnings in 55.20s
```

Frontend type-check:
```bash
$ docker compose exec -T frontend npx tsc --noEmit
# exit 0
```

## Modified prior sessions
- Session 1.1 — `backend/tests/test_health.py`: made CORS assertions configuration-driven so local port
  remaps do not break the suite.
- Session 5a — `backend/tests/test_quiz_schema.py`, `knowledge/specs/stage-05/5-shared-quiz-engine-event-spine.md`,
  `knowledge/decisions/adr-041-pagination-envelope.md`, `knowledge/steps/stage-05/5a-quiz-foundation.md`:
  added missing CHECK negative tests and reconciled the pagination-envelope done item with ADR-041.
- Session 5b — `backend/alembic/versions/0016_quiz_attempts.py`,
  `backend/app/platform/db/models/quiz_attempt.py`, `backend/app/workers/queues.py`,
  `backend/app/domains/recovery/rq_liveness.py`, `backend/app/domains/quiz/generation_service.py`,
  `backend/tests/test_quiz_generation.py`, `knowledge/decisions/adr-046-quiz-generation-recovery.md`,
  `knowledge/steps/stage-05/5b-quiz-generation-recovery.md`: stored generation job provenance and aligned
  job-id formatting.
- Session 5d — `knowledge/steps/stage-05/5d-student-ui-browser-gate.md`,
  `knowledge/steps/stage-05/5d-real-provider-smoke.md`, `knowledge/findings-5d.md`: removed stale residual
  wording after Gate 1 and the 16000-token re-confirm were already green.

## Remaining risks
- The migration-number collision with sibling branches' 0014-0016 remains a merge-time blocker. 5e did
  not renumber Stage 5 migrations.
- AIRequestLog finalize on a mid-call crash remains the accepted 5b residual; 5e did not change the
  broader logging linkage model.

## Change history
- 2026-06-16 22:46 — [Session 5e] review findings fixed and verified; backend 442 passed, frontend tsc exit 0.
