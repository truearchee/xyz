---
type: session-spec
stage: "06"
session: "6e"
slug: corrective-closure
status: approved
created: 2026-06-17
updated: 2026-06-17
owner: developer
plan: knowledge/plans/stage-06/6e-corrective-closure.md
report: knowledge/steps/stage-06/6e-corrective-closure.md
---

# Session 6e — Corrective Closure

## Linked documents
- Overview spec: [[specs/stage-06/6-complete-quiz-modes]]
- Spec: [[specs/stage-06/6e-corrective-closure]]
- Plan: [[plans/stage-06/6e-corrective-closure]]
- Report: [[steps/stage-06/6e-corrective-closure]]
- Prior 6d report: [[steps/stage-06/6d-ui-browser-gate-postclass-retrofit]]
- Prior real-provider smoke: [[steps/stage-06/6d-real-provider-smoke]]
- Stage 7 coordination: [[steps/findings-6-shared-infra]]

## Goal
Reopen and re-close Stage 6 correctly by fixing the 6d browser-gate hole, wiring failed-pool retry, finishing the missing gate assertions, aligning ORM metadata with migration 0023, and rerunning the required closeout gates.

## Why now
An independent review found that Stage 6 closure did not hold. The 6d gate went green while skipping core assertions from the Stage 6 UI proof obligation, and a real failed-pool retry path remained unwired. Stage 6 must move back to IN PROGRESS until 6e proves the full obligation in-browser and reruns the closeout evidence.

## Developer handoff preserved
- "An independent review found the Stage 6 closure doesn't hold. Reopen Stage 6 — unflip the roadmap row back to IN PROGRESS with a note pointing at a corrective session (call it 6e), and address these. Don't argue them away; the review traced source and I agree."
- "P1 — gate hole (most important). The 6d browser gate does not prove the Stage 6 UI proof obligation. 6d-quiz-modes-browser-gate.spec.ts asserts the retake prefix banner appears and opens the bank, but never answers a prefixed mistake correctly twice, never asserts it leaves the retake prefix, and never asserts it remains in the bank after. Backend unit coverage of the atomic flip is necessary but not sufficient (rule 9 — the browser must prove it). Extend the gate to walk the full obligation end-to-end in the browser."
- "P1 — real defect, pool retry not wired. retry_section_pool() exists but no normal start/retry path calls it. ensure_section_pool() returns an existing failed pool, start_pooled_attempt() proceeds, assembly then marks the attempt failed, and the frontend \"Try again\" only re-hits start-over — so a terminal pool failure is sticky. Wire retry to re-enqueue once under the existing one-active lock, surface the failure+retry state in QuizAttemptPanel, and prove it in the gate (force a pool failure -> retry -> reaches completed). This compounds with the live-latency timeout finding from closeout — failed pools will happen in production."
- "P2 — finish the gate's remaining required assertions. Exam-prep completion must insert completed_quiz (+ perfect_quiz_score on 100%) with mode/scope metadata — the gate starts exam-prep and checks scope only, never completes or queries the event rows. And the retake reuse/no-new-AIRequestLog assertion is missing (second-student recap reuse is proven; retake reuse is not). Add both."
- "P2 — ORM/migration drift. Migration 0023 widened the ai_request_logs.feature CHECK for quiz_pool, but the SQLAlchemy model still lists only summary_brief/summary_detailed/post_class_quiz. Align the model so metadata-created schemas and autogenerate don't drift. (Coordinate with the Stage 7 shared-registry reconcile already on the findings note — this is the same constraint; don't fork it.)"
- "Re-close 6e only when: the full retake obligation is browser-proven, pool-retry works and is gate-proven, the exam-prep event + retake-reuse assertions are in, the ORM matches, and the full active suite + rule-11 smoke are re-run green (rule 14). Then re-flip the row. Same rule-12 single-commit discipline."
- "One process note for the report: capture how the original gate passed while skipping its core assertions, so the gate-authoring step gets a check that asserts against the spec's obligation, not just \"a test exists and is green.\" A green test that doesn't test the requirement is the failure mode here."

## Read first
- [[specs/stage-06/6-complete-quiz-modes]]
- [[specs/stage-06/6d-ui-browser-gate-postclass-retrofit]]
- [[plans/stage-06/6d-ui-browser-gate-postclass-retrofit]]
- [[steps/stage-06/6d-ui-browser-gate-postclass-retrofit]]
- `backend/app/domains/quiz/pool_service.py`
- `backend/app/domains/quiz/assembly_service.py`
- `backend/app/domains/quiz/service.py`
- `frontend/src/features/quiz/QuizAttemptPanel.tsx`
- `tests/e2e/6d-quiz-modes-browser-gate.spec.ts`

## Source paths likely touched
- `backend/app/domains/quiz/pool_service.py`
- `backend/app/domains/quiz/assembly_service.py`
- `backend/app/domains/quiz/service.py`
- `backend/app/api/routers/quiz.py`
- `backend/app/platform/db/models/ai_request_log.py`
- `backend/tests/test_quiz_pool.py`
- `frontend/src/features/quiz/QuizAttemptPanel.tsx`
- `frontend/src/features/quiz/StudentQuizModesPanel.tsx`
- `frontend/src/lib/api/wrapper.ts`
- `tests/e2e/6d-quiz-modes-browser-gate.spec.ts`
- Stage 6 knowledge files

## Build
- Reopen Stage 6 in roadmap/status/log before source edits and point the corrective work at 6e.
- Wire failed-pool retry into a normal, explicit retry path that re-enqueues the failed pool once under the existing one-active/generating lock.
- Surface terminal pool failure plus retry in `QuizAttemptPanel` so the user action reaches the new retry path instead of repeating the sticky failed start path.
- Extend the browser gate to force a pool failure, retry it, and prove the attempt reaches completion.
- Extend the browser gate to complete two retakes correctly, prove the source mistake leaves the retake prefix, and prove the same mistake remains playable in the mistakes bank.
- Extend the browser gate to complete exam prep and query `completed_quiz` plus `perfect_quiz_score` with mode/scope metadata.
- Extend the browser gate to assert retake reuse/no-new-`AIRequestLog` at section granularity.
- Align `AIRequestLog` ORM metadata with migration 0023's `quiz_pool` CHECK value, without forking the Stage 7 shared-registry reconcile.
- Write an evidence-based 6e report that explains how the original green gate skipped its core obligations.

## Do not build
- Do not change the Stage 6 product scope beyond the corrective findings above.
- Do not add new event types or AIRequestLog feature names.
- Do not start the Stage 7 shared-registry reconcile; only align the existing ORM constraint with the existing migration value.
- Do not weaken the browser gate to satisfy timing; the assertions must match the Stage 6 obligation.
- Do not re-flip Stage 6 to FULLY VERIFIED until the full active suite and rule-11 smoke rerun green.

## Data model changes
No migration is expected. ORM metadata for the existing `ai_request_logs.feature` CHECK must include `quiz_pool` to match migration 0023.

## API changes
Add or adapt only the endpoint surface needed for explicit failed-pool retry. Preserve 401/403/404 semantics and existing generated-client behavior.

## Worker / job changes
Retrying a terminal failed pool must enqueue one pool generation job under the existing section/model/prompt lock and avoid duplicate generation when multiple waiters retry.

## Authz rules
No relaxation. Retry must be available only through the same student visibility/ownership checks that govern the failed attempt or quiz mode.

## Verification
- `docker compose build backend frontend` -> build succeeds.
- `docker compose run --rm --no-deps backend sh -c "alembic upgrade head && alembic downgrade base && alembic upgrade head && alembic heads"` -> single head.
- `docker compose run --rm --no-deps backend pytest -q` -> full backend green.
- `docker compose run --rm --no-deps backend ruff check .` -> clean.
- `bash scripts/generate-api-client.sh` -> no unexpected client drift.
- `cd frontend && npx tsc --noEmit` -> clean.
- `npx playwright test tests/e2e/5d-post-class-quiz.spec.ts --workers=1` -> green.
- `npx playwright test tests/e2e/6d-quiz-modes-browser-gate.spec.ts --workers=1` -> green with the new assertions.
- `npx playwright test --workers=1` -> full active suite green.
- `docker compose run --rm --no-deps backend python scripts/gate3_quiz_pool_smoke.py` -> rule-11 smoke green with model echo and valid quiz-pool payload.

## Knowledge updates required
- Create `knowledge/steps/stage-06/6e-corrective-closure.md` from `git diff` and real command output.
- Update this spec and the plan linked-doc sections to include the report once it exists.
- Update `knowledge/STATUS.md`, append `knowledge/log.md`, and update `knowledge/roadmap.md` twice as evidence requires: first to reopen, then to re-close only after all gates pass.
- Append change-history lines to prior Stage 6 reports for prior-session files modified by 6e.

## Done means
Stage 6 is re-closed only after the full retake obligation is browser-proven, failed-pool retry is wired and gate-proven, exam-prep completion events and retake reuse/no-new-generation are asserted, ORM metadata matches migration 0023, full active E2E and rule-11 smoke rerun green, and the report captures the original green-but-insufficient gate failure mode.

## Amendments
_Add dated entries here if scope changes mid-flight. Do not silently edit the sections above._
