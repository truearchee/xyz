---
type: session-spec
stage: "05"
session: "5e"
slug: review-finding-fixes
status: done
created: 2026-06-16
updated: 2026-06-16
owner: developer
plan: "knowledge/plans/stage-05/5e-review-finding-fixes.md"
report: "knowledge/steps/stage-05/5e-review-finding-fixes.md"
---

# Session 5e — Review Finding Fixes

## Linked documents
- Stage spec: [[specs/stage-05/5-shared-quiz-engine-event-spine]]
- Spec: [[specs/stage-05/5e-review-finding-fixes]]
- Plan: [[plans/stage-05/5e-review-finding-fixes]]
- Report: [[steps/stage-05/5e-review-finding-fixes]]
- Prior reports: [[steps/stage-05/5a-quiz-foundation]], [[steps/stage-05/5b-quiz-generation-recovery]], [[steps/stage-05/5c-answer-feedback-scoring-retake]], [[steps/stage-05/5d-student-ui-browser-gate]]

## Goal
Close the review findings raised against Stage 5 on `spec-5`: make current verification green, record quiz generation job provenance, align docs with the accepted pagination amendment, add missing 5a CHECK negative tests, and commit the Stage 5 work.

## Build
- Fix health CORS tests so they verify the configured allowed origin instead of hard-coding `localhost:3000`.
- Stamp `QuizAttempt.generation_job_id` when the post-class quiz job is enqueued, and use one canonical job-id helper for enqueue + recovery liveness.
- Add negative tests for the 5a CHECK constraints that were previously only asserted by name.
- Update Stage 5 docs/ADRs/reports to reflect the pagination amendment and the provenance repair.
- Commit the Stage 5 working tree when verification is green.

## Do not build
- No new Stage 5 product surface, no new quiz endpoint behavior, no generation algorithm changes, no new migration beyond repairing uncommitted Stage 5 migration content.
- No changes to ignored `.env` / `.env.e2e` secrets.

## Verification
```bash
docker compose exec -T backend pytest -q tests/test_health.py
docker compose exec -T backend pytest -q tests/test_db_spine.py tests/test_quiz_schema.py tests/test_event_recorder.py tests/test_quiz_schemas_dto.py tests/test_quiz_generation.py tests/test_quiz_endpoints.py
docker compose exec -T backend pytest -q
docker compose exec -T frontend npx tsc --noEmit
git status --short --untracked-files=all
```

## Done means
- All review findings are either fixed in code or explicitly reconciled in the stage docs.
- Current backend and frontend verification commands pass.
- A commit exists on `spec-5` containing the Stage 5 work and these review fixes.

## Amendments
- None.
