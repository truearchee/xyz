---
type: session-plan
stage: 07
session: "7e"
slug: review-fixes
status: executed
created: 2026-06-18
updated: 2026-06-18
spec: knowledge/specs/stage-07/7e-review-fixes.md
report: knowledge/steps/stage-07/7e-review-fixes.md
---

# Session 7e — Implementation Plan — Stage 7 Review Fixes

## Linked documents
- Spec: [[specs/stage-07/7e-review-fixes]]
- Plan: [[plans/stage-07/7e-review-fixes]]
- Report: [[steps/stage-07/7e-review-fixes]]

## Scope confirmation
This delivers only the two requested runtime fixes plus the requested spec/documentation cleanup. It does not implement 7d, add vocabulary, redesign the detail UI, harden prompt-echo validation, repair historical Stage 7 knowledge trios, expand Playwright coverage, rerun the real-provider smoke, commit, or update the roadmap row.

## Approach
Mirror the existing quiz generation compensation pattern: keep enqueue after commit, catch queue errors, mark the glossary cache row and pending entries failed, and return the saved entry in that failed state. For retry, reuse the existing duplicate-save branch but teach it to reactivate and enqueue a failed cache row so the single cache row can still fan out to the existing entry after the worker succeeds.

For `entry_type`, reject update payloads that include it. This keeps create-time type selection intact and avoids cache-key/provenance desynchronization without adding a reclassification feature.

## Changes, file by file
- `backend/app/domains/glossary/save_service.py` — add enqueue compensation helper; reuse failed-cache requeue from duplicate save path.
- `backend/app/domains/glossary/service.py` — reject `entry_type` updates before mutating the row.
- `backend/app/domains/glossary/policy.py` — add a stable validation error code for immutable entry type.
- `backend/tests/test_glossary_save.py` — add enqueue-failure/retry-to-generated regression and immutable-entry-type regression.
- `knowledge/specs/stage-07/7-glossary.md` — remove `vocabulary` from the entry-type enumeration and clarify D3 prompt validation acceptance.
- `knowledge/steps/findings-stage-07.md` — record deferred review findings and accepted rationale.
- `knowledge/open-questions.md` — add deferred follow-ups for Stage 12 design, docs cleanup, and Playwright assertion expansion.
- `knowledge/steps/stage-07/7e-review-fixes.md` — write after verification from actual diff/output.
- `knowledge/STATUS.md` / `knowledge/log.md` — close-loop session status/log only; do not update roadmap row.

## Order of operations
1. File this spec/plan and keep scope fenced.
2. Patch glossary save retry/compensation and entry-type rejection.
3. Add the regression tests.
4. Apply the locked-spec correction and deferred finding notes.
5. Run targeted backend tests; fix issues if any.
6. Run full backend tests.
7. Run full active E2E suite with `--workers=1`.
8. Write the 7e report from `git diff` and command output.
9. Report and hold uncommitted for developer review.

## Test strategy
- Enqueue failure test monkeypatches `enqueue_generate_glossary_definition` to throw on first save, asserts cache and entry become `failed`, then retries with enqueue capture and drives `generate_glossary_definition_async` to prove completion.
- Entry-type update test calls `update_entry` with an `entry_type` payload and asserts the clear validation error while the original type remains unchanged.
- Full backend and full active E2E suite provide regression coverage for existing Stage 7 and inherited active workflows.

## Risks & mitigations
- Risk: compensating after commit with the same session can leave session state stale. Mitigation: commit the compensation in its own helper and return via the existing read path, which refreshes from the DB.
- Risk: duplicate retry could enqueue repeatedly. Mitigation: only failed cache rows are reactivated; pending rows still mean an active job is assumed.
- Risk: API client becomes stale if schema is changed. Mitigation: service-level rejection avoids a schema-generation requirement for this follow-up.

## Open questions
- The Stage 4.6 stuck-row reaper does not currently cover glossary definition cache rows; this session will note whether that should become a later recovery follow-up after compensation/retry is in place.
