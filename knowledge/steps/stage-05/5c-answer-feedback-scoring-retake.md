---
type: session-report
stage: "05"
session: "5c"
slug: answer-feedback-scoring-retake
status: complete
created: 2026-06-16
updated: 2026-06-16
spec: knowledge/specs/stage-05/5c-answer-feedback-scoring-retake.md
plan: knowledge/plans/stage-05/5c-answer-feedback-scoring-retake.md
---

# Session 5c — Report — Answer / Feedback / Scoring / Retake (HTTP surface)

## Linked documents
- Stage spec: [[specs/stage-05/5-shared-quiz-engine-event-spine]]
- Spec: [[specs/stage-05/5c-answer-feedback-scoring-retake]]
- Plan: [[plans/stage-05/5c-answer-feedback-scoring-retake]]
- Report: [[steps/stage-05/5c-answer-feedback-scoring-retake]]
- Prior: [[steps/stage-05/5b-quiz-generation-recovery]]
- Related: [[decisions/adr-041-pagination-envelope]] (amended this session)

## What shipped (from `git diff` + new files)
New:
- `app/platform/query/quiz_read.py` — `get_visible_attempt` (the single S7 visibility gate: owner + published + active + assigned + lecture/lab → None ⇒ 404), `get_attempt_questions_for_student`, `get_attempts_aggregate` (COUNT + MAX score). Read-only.
- `app/domains/quiz/service.py` — the six endpoint services with the spec ordering (availability/start/get_attempt/answer/complete/attempts_summary). Role gate (403) + visibility gate (pinned 404) before any business work.
- `app/api/routers/quiz.py` — 6 thin endpoints; `Cache-Control: private, no-store`; section/attempt-scoped (no by-question IDOR route).
- `tests/test_quiz_endpoints.py` (15).
Modified:
- `app/domains/quiz/schemas.py` — `AnswerSubmission`, `QuizAttemptsSummary`.
- `app/main.py` — include `quiz_router`.
- `frontend/src/lib/api/*` — regenerated OpenAPI client (additive).

## Verification (real output)
Full suite, fresh isolated DB, this workspace's code:
```
437 passed, 126 warnings in 55.16s
```
- `437` = 422 (post-5b) + 15 new endpoint tests. No failures, no regressions; migration round-trip (0013→0020) still green.
- 15 endpoint tests: non-student 403 on every endpoint; unassigned student 404 + assigned availability 200; attempt detail hides correctness pre-answer (no `isCorrect` on options, `answer=null`) + `Cache-Control` asserted; answer correct (no mistake) / incorrect (mistake created, `mistakeSaved`) / idempotent re-answer returns ORIGINAL (`alreadyAnswered`, no 2nd StudentAnswer, no 2nd mistake) / cross-attempt question 404 / option-from-other-question 422; complete scores + emits `completed_quiz` (same txn) / all-correct emits `perfect_quiz_score` / idempotent re-complete (no duplicate event) / strict `in_progress` (a generating attempt → 409); **S7 unpublish-mid-attempt → all endpoints 404 + zero events while hidden → re-publish → complete works**; start resume + Start-Over (new attempt, attemptNumber 2); attempts aggregate (count + best).

**OpenAPI client regenerated + verified (not deferred to 5d):**
- Generated `app.openapi()` from this workspace's backend → ran `openapi-typescript-codegen@0.29.0` (matches `frontend/package.json`) → `frontend/src/lib/api`.
- Diff is **purely additive**: `index.ts` +10 exports; 10 new files (`QuizService.ts` + 9 quiz models); **zero existing client files modified** → no breaking change to existing frontend surface.
- `tsc --noEmit` on the frontend (borrowing the frontend image's node_modules — deps unchanged) → **exit 0**.
- Note: not committed (no commit instruction this session); the regenerated client sits in the working tree to be committed when the branch is committed. The running `test2-*` stack is a sibling branch, so the regen used a spec dumped from this workspace's code, not `localhost:8000`.

Throwaway DBs dropped; `xyz_lms`/`xyz_lms_test` untouched.

## Decisions (recorded)
- Attempts surface = **aggregate** (count + best score), not a paginated list — no pagination theatre. **ADR-041 amended** (envelope defined + unit-tested in 5a; real-consumer proof deferred to Stage 6 mistakes-bank / Stage 7 glossary). No new ADR for 5c (the endpoint ordering + atomicity are spec implementations, not new durable decisions).
- Complete validates `status == in_progress` strictly (a `generating` attempt → 409, never silent complete) — proven by `test_complete_strict_in_progress_409`.
- AIRequestLog mid-call-crash residual NOT touched (Stage-8-owned, ADR-046).

## Deviations / residuals
- None new. The S7 seam, answer ordering, and complete atomicity are implemented as specified. tsc was run by borrowing the frontend image's node_modules (this workspace has none provisioned); a native frontend build belongs to 5d where the UI is actually run.

## Modified prior sessions
- Session 1.x (`app/main.py`) — added the quiz router include (additive). No behavior change to existing routers.

## Close-the-loop checklist
- [x] Spec `status: done`; plan `status: executed`
- [x] Plan approved before code (developer's detailed 5c guidance + go)
- [x] Stayed in scope (no UI, no migrations — heads stayed 0020)
- [x] Verification run; real output (437 passed)
- [x] Report from `git diff` + command output
- [x] spec ↔ plan ↔ report links resolve
- [x] `STATUS.md` overwritten; `log.md` appended
- [x] **OpenAPI client regenerated + tsc-clean** (the contract changed; not deferred to 5d)
- [ ] `architecture/` — not updated (no architecture doc covers the quiz domain yet; a single quiz-domain architecture note across 5a–5c could be added at stage close — deferred to 5d/stage-close)
- [x] No new ADR needed (ADR-041 amended)
- [x] `open-questions.md` — no new items

## Change history
- 2026-06-16 — [Session 5c] initial report. Student quiz HTTP surface landed + verified (437 passed); OpenAPI client regenerated (additive, tsc-clean).
