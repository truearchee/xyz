---
type: session-plan
stage: "06"
session: "6e"
slug: corrective-closure
status: approved
created: 2026-06-17
updated: 2026-06-17
spec: knowledge/specs/stage-06/6e-corrective-closure.md
report: knowledge/steps/stage-06/6e-corrective-closure.md
---

# Session 6e — Implementation Plan — Corrective Closure

## Linked documents
- Overview spec: [[specs/stage-06/6-complete-quiz-modes]]
- Spec: [[specs/stage-06/6e-corrective-closure]]
- Plan: [[plans/stage-06/6e-corrective-closure]]
- Report: [[steps/stage-06/6e-corrective-closure]]
- Prior 6d report: [[steps/stage-06/6d-ui-browser-gate-postclass-retrofit]]
- Prior real-provider smoke: [[steps/stage-06/6d-real-provider-smoke]]
- Stage 7 coordination: [[steps/findings-6-shared-infra]]

## Scope confirmation
This plan implements only the accepted 6e corrective findings: reopen Stage 6, fix failed-pool retry, strengthen the 6d browser gate to prove the full retake obligation, add the missing exam-prep event and retake-reuse assertions, align the `AIRequestLog` ORM CHECK metadata with migration 0023, and re-close only after the full gate set reruns green.

Out of scope: Stage 7 shared-registry reconcile, new event or AIRequestLog feature names, new quiz modes, broader UI redesign, or any weakening of the browser obligations.

## Approach
Use the existing pool state machine instead of adding a parallel retry mechanism. Failed-pool retry should be an explicit user action on a failed attempt, checked through the same visibility rules as attempt reads, then routed to `retry_section_pool()` for the failed section(s). The browser gate should assert against DB state and user-visible state at each obligation boundary so it cannot pass merely because a banner or a test exists.

## Changes, file by file
- `knowledge/roadmap.md` — move Stage 6 back to IN PROGRESS and point to corrective session 6e; later re-close only with new evidence.
- `knowledge/STATUS.md` — overwrite current state to Stage 6 reopened for 6e.
- `knowledge/log.md` — append the reopening line and, at closeout, the evidence line.
- `backend/app/platform/db/models/ai_request_log.py` — add `quiz_pool` to the ORM `feature` CHECK.
- `backend/app/domains/quiz/service.py` / `assembly_service.py` / `pool_service.py` — expose a visibility-checked retry path that re-enqueues terminal failed pools once under the existing generating lock.
- `backend/app/api/routers/quiz.py` and generated client/wrapper files — add the retry endpoint only if no existing endpoint can safely express explicit retry.
- `frontend/src/features/quiz/QuizAttemptPanel.tsx` — route terminal failed-state retry to the explicit retry API and keep honest failed/generating states.
- `tests/e2e/6d-quiz-modes-browser-gate.spec.ts` — add full retake-prefix drop and bank persistence proof, forced failed-pool retry proof, exam-prep completion event proof, and retake no-new-generation proof.
- `backend/tests/test_quiz_pool.py` and related focused tests — cover failed pool retry through the public service/API path, not just the low-level helper.
- `knowledge/steps/stage-06/6e-corrective-closure.md` — evidence report from real diff and command output.

## Order of operations
1. File 6e spec/plan and reopen roadmap/status/log.
2. Inspect the current failed-attempt DTO/API and decide the narrowest retry endpoint shape.
3. Implement backend retry with row-locking and visibility checks; add focused tests.
4. Align the ORM CHECK metadata and run focused backend checks.
5. Regenerate client if API changed; wire frontend failed-state retry.
6. Extend the browser gate assertions for retake, bank persistence, forced retry, exam-prep events, and retake reuse.
7. Run focused verification, then full backend/static/browser gates, then rule-11 smoke.
8. Write the 6e report, append prior-session change-history lines, update status/log/roadmap, and commit once.

## Test strategy
- Backend focused tests prove failed pool retry through the service/API path re-enqueues a failed pool once, preserves waiter behavior, and does not duplicate generation.
- Browser gate proves the exact Stage 6 UI obligation: two correct retakes drop the prefix while bank practice remains available.
- Browser gate uses DB assertions for `AIRequestLog` count, `StudentActivityEvent` metadata, source-section scope, mistake bank rows, and failed-pool status transitions.
- Full backend, frontend type-check, 5d preservation gate, 6d gate, full active Playwright suite, and rule-11 smoke are required before re-closing.

## Risks & mitigations
- **Retry endpoint could bypass authz:** base it on visible attempt/module checks already used by quiz read/start paths.
- **Retry can race multiple users:** call the existing lock-aware `retry_section_pool()` and add a duplicate-retry assertion.
- **Browser test could again become superficial:** every new obligation must have a concrete assertion against the final state, not just an intermediate banner.
- **Live-provider latency remains high:** keep the rule-11 smoke evidence and do not treat retry as a timeout fix; retry only handles terminal failed pools.

## Open questions
- None. The developer explicitly accepted the review findings and requested implementation.
