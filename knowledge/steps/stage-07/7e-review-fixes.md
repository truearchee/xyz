---
type: session-report
stage: 07
session: "7e"
slug: review-fixes
status: complete
created: 2026-06-18
updated: 2026-06-18
spec: knowledge/specs/stage-07/7e-review-fixes.md
plan: knowledge/plans/stage-07/7e-review-fixes.md
commit: ""
---

# Session 7e — Report — Stage 7 Review Fixes

## Linked documents
- Spec: [[specs/stage-07/7e-review-fixes]]
- Plan: [[plans/stage-07/7e-review-fixes]]
- Report: [[steps/stage-07/7e-review-fixes]]
- Stage spec: [[specs/stage-07/7-glossary]]
- Findings: [[steps/findings-stage-07]]

## Summary
Implemented the two requested Stage 7 review fixes and the requested spec correction. The changes are
uncommitted and held for review.

- Glossary definition enqueue failures after commit now compensate the cache row and matching pending
  entries to `failed` instead of leaving an unowned `pending` row.
- Duplicate-save retry now reactivates a failed glossary definition cache row, re-enqueues it, and lets
  the existing entry reach `generated` through the normal worker fan-out.
- `entry_type` updates now return a clear 422 validation error instead of mutating a cache-key component.
- The locked Stage 7 spec now uses `term | formula | concept`; `vocabulary` is explicitly not a product
  type.
- Deferred review findings were logged, not fixed.

## Files changed
Backend:
- `backend/app/domains/glossary/save_service.py`
- `backend/app/domains/glossary/service.py`
- `backend/app/domains/glossary/policy.py`
- `backend/tests/test_glossary_save.py`

Knowledge:
- `knowledge/specs/stage-07/7e-review-fixes.md`
- `knowledge/plans/stage-07/7e-review-fixes.md`
- `knowledge/steps/stage-07/7e-review-fixes.md`
- `knowledge/specs/stage-07/7-glossary.md`
- `knowledge/steps/findings-stage-07.md`
- `knowledge/open-questions.md`
- `knowledge/STATUS.md`
- `knowledge/log.md`
- `knowledge/steps/stage-07/7a-glossary-foundation.md`

Local verification environment:
- `.env.e2e` was updated locally with `CORS_ORIGINS=http://localhost:3000,http://localhost:3001` so the
  Bucharest frontend on `:3001` can pass browser auth preflights. This file is gitignored.

## Verification
| Command | Result | Notes |
|---|---|---|
| `docker compose run --rm -v "$PWD/backend:/app" -T backend pytest -q tests/test_glossary_save.py tests/test_glossary_practice.py tests/test_glossary_unit.py` | passed | `20 passed in 3.37s` |
| `docker compose run --rm -v "$PWD/backend:/app" -T backend pytest -q` | passed | `500 passed, 138 warnings in 62.31s` |
| `PLAYWRIGHT_BASE_URL=http://localhost:3001 E2E_RUN_ID=e2e-1781765063-stage7e2 npx playwright test --workers=1` after seeding | failed | First proper run: `13 passed / 1 failed`; only failure was `5d-post-class-quiz.spec.ts` waiting for `quiz-question-card`. Investigation showed stale `ai_worker` image using Stage 6 fields (`quiz_definitions.scope_key`) against Stage 7 DB head `0031`. |
| Rebuilt/recreated app containers from current checkout | passed | `ai_worker` then reported `QuizDefinition` columns without stale Stage 6 fields. |
| `PLAYWRIGHT_BASE_URL=http://localhost:3001 E2E_RUN_ID=e2e-1781765745-stage7e4 npx playwright test --workers=1` after seeding | failed | `12 passed / 2 failed`; failures were `4.3.5c-stage2-admin.spec.ts` and `5.5e-ui-browser-gate.spec.ts`, both timing out waiting for newly created `admin-module-row-*`. Stage 5 quiz and Stage 7 glossary passed. |
| `PLAYWRIGHT_BASE_URL=http://localhost:3001 E2E_RUN_ID=e2e-1781766005-stage7e5 npx playwright test --workers=1` after seeding | failed | Repeat confirmed same two unrelated admin row-refresh failures: `12 passed / 2 failed`; Stage 5 quiz and Stage 7 glossary passed again. |

The requested full active E2E suite is **not green** yet. The residual failures are outside this Stage 7
follow-up scope and are not caused by the glossary enqueue/type changes. In both failed runs, the failed
module rows existed in the database after creation; the UI assertion did not observe the row within 10s.

## Deviations from spec
- Full active E2E did not pass. I did not broaden into admin module UI fixes because this session is
  scoped to Stage 7 review fixes and the failure is in inherited admin/schedule browser gates.
- The real-provider smoke was not rerun, per developer instruction.
- The roadmap row was not updated, per developer instruction.

## Decisions made
No ADR added.

Implementation decisions:
- Enqueue compensation mirrors the existing quiz enqueue-after-commit pattern: catch queue errors after
  commit, mark the committed generation state failed, and let the user retry from a clean failed state.
- `entry_type` is immutable after entry creation; reclassification is not a Stage 7 feature.

## Risks introduced
- The Stage 4.6 stuck-row reaper does not cover `glossary_definition_cache`; this is logged in
  [[open-questions]] as a future recovery-scope decision. The required compensation + duplicate retry
  recovery is implemented now.
- Full-suite acceptance is still blocked by unrelated admin module-row refresh failures.

## Follow-ups
- Resolve the inherited admin module-row refresh failures before using rule-14 full-suite green as final
  acceptance evidence for this follow-up.
- Stage 12 design pass: revisit glossary detail panel tabs vs inline aside.
- Docs cleanup: repair historical Stage 7 per-sub-session knowledge trios.
- 7d gate: add Playwright assertions for `<4 terms` MCQ fallback and deterministic MCQ wrong-pick.
- Later recovery pass: decide whether `glossary_definition_cache` needs scheduled stuck-row reaper coverage.

## Modified prior sessions
- **Session 7a** — `backend/app/domains/glossary/save_service.py`, `backend/app/domains/glossary/service.py`,
  `backend/app/domains/glossary/policy.py`, `backend/tests/test_glossary_save.py`: added enqueue-failure
  compensation/retry recovery and entry-type immutability.

## Knowledge updates
- Added this 7e spec/plan/report trio.
- Corrected [[specs/stage-07/7-glossary]] entry-type enumeration to remove `vocabulary`.
- Recorded D3 prompt-validation rationale as accepted, not drift.
- Logged deferred review findings in [[steps/findings-stage-07]] and [[open-questions]].
- Updated [[STATUS]] and appended [[log]].

## Close-the-loop checklist
- [x] Spec exists and approved
- [x] Plan existed before coding
- [x] Stayed in scope; full E2E deviation noted above
- [x] Verification commands run; real output recorded
- [x] Report written from git diff + output, not memory
- [x] spec ↔ plan ↔ report links all resolve
- [x] STATUS.md overwritten; log.md appended
- [x] architecture/ not updated; no source-path topology changed
- [x] ADR not added; no durable cross-cutting decision needed
- [x] open-questions.md updated for unresolved follow-ups

## Change history
- 2026-06-18 — initial report written; code remains uncommitted pending developer review.
