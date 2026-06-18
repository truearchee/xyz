---
type: session-spec
stage: 07
session: "7e"
slug: review-fixes
status: in-progress
created: 2026-06-18
updated: 2026-06-18
owner: developer
plan: knowledge/plans/stage-07/7e-review-fixes.md
report: knowledge/steps/stage-07/7e-review-fixes.md
---

# Session 7e — Stage 7 Review Fixes

## Linked documents
- Spec: [[specs/stage-07/7e-review-fixes]]
- Plan: [[plans/stage-07/7e-review-fixes]]
- Report: [[steps/stage-07/7e-review-fixes]]

## Goal
Fix the two real Stage 7 code-review defects, correct the entry-type spec drift, and log the deferred findings without implementing them.

## Why now
The Stage 7 implementation review found two runtime correctness issues in otherwise verified 7a-7c glossary core work. Both affect retryability and data consistency and should be resolved before Stage 7 is reviewed for landing.

## Read first
- [[specs/stage-07/7-glossary]]
- [[steps/stage-07/7a-glossary-foundation]]
- [[steps/stage-07/7bc-glossary-practice]]
- [[steps/findings-stage-07]]
- `.context/plans/stage-7-interactive-glossary-practice-implementati.md`

## Source paths likely touched
- `backend/app/domains/glossary/save_service.py`
- `backend/app/domains/glossary/service.py`
- `backend/app/domains/glossary/policy.py`
- `backend/tests/test_glossary_save.py`
- `knowledge/specs/stage-07/7-glossary.md`
- `knowledge/steps/findings-stage-07.md`
- `knowledge/open-questions.md`

## Build
- Fix enqueue-after-commit failure handling for glossary definitions:
  - Keep enqueue after commit.
  - If enqueue throws, compensate the just-committed definition cache row and matching pending entries to a failed/retryable state.
  - Make duplicate retry recover a failed definition by re-enqueueing it so generation can complete.
  - Add a regression test that simulates enqueue throwing and proves failed/retryable state plus retry-to-completion.
  - Note whether the Stage 4.6 stuck-row reaper covers glossary definition rows.
- Fix `entry_type` update drift:
  - Disallow `entry_type` changes on glossary entry update with a clear validation error.
  - Add a regression test for the rejected update.
- Correct the locked Stage 7 spec entry-type enumeration to `term | formula | concept`.
- Log deferred findings so they stop resurfacing:
  - Detail-sheet tabs flattened to an aside: log for the Stage 12 design pass.
  - Prompt-echo hard rejection softened: record D3 rationale as accepted, not drift.
  - Per-sub-session knowledge trios incomplete: log as docs-cleanup follow-up.
  - Browser gate missing `<4 terms` fallback and MCQ wrong-pick assertions: log as low-priority follow-up that can fold into 7d gate.
  - 7d remains already tracked; no action.

## Do not build
- Do not implement 7d quiz-highlight.
- Do not add a `vocabulary` entry type.
- Do not redesign the entry detail UI or add tabs now.
- Do not change prompt validation behavior beyond documenting the accepted D3 rationale.
- Do not repair the historical per-sub-session knowledge trios now.
- Do not expand the Playwright gate assertions now except by logging the follow-up.
- Do not rerun the real-provider smoke; the AI call path is unchanged.
- Do not commit or update the roadmap row before developer review.

## Data model changes
None.

## API changes
The update-entry API must reject `entry_type` changes. Create-entry APIs still accept the current entry type set: `term`, `formula`, `concept`.

## Worker / job changes
Glossary definition enqueue compensation is added on the request path. No new queue, worker, or scheduler is added.

## Authz rules
No authz changes.

## Verification
- `docker compose run --rm -v "$PWD/backend:/app" -T backend pytest -q` -> backend tests green, including the two new regression tests.
- `PLAYWRIGHT_BASE_URL=http://localhost:3001 E2E_RUN_ID=<run-id> npx playwright test --workers=1` -> full active E2E suite green.
- Real-provider smoke is intentionally not rerun.

## Knowledge updates required
- Update [[specs/stage-07/7-glossary]] to remove `vocabulary` from the entry-type enumeration and record D3 validation rationale.
- Update [[steps/findings-stage-07]] and/or [[open-questions]] with the deferred findings.
- Write [[steps/stage-07/7e-review-fixes]] from `git diff` and actual verification output.
- Do not update the roadmap row before developer review.

## Done means
- Enqueue failure leaves the glossary definition cache row and matching entry state in `failed`, not unowned `pending`.
- Retrying the same save re-enqueues the failed definition and the definition can reach `generated`.
- `entry_type` update is rejected with a clear validation error.
- The locked spec says the entry type set is `term | formula | concept`.
- Deferred findings are logged, not fixed.
- Backend tests and the full active E2E suite pass.
- Changes remain uncommitted for developer review.

## Amendments
_Add dated entries here if scope changes mid-flight. Do not silently edit the sections above._
