---
type: session-spec
stage: "05"
session: "5c"
slug: answer-feedback-scoring-retake
status: done
created: 2026-06-16
updated: 2026-06-16
owner: developer
plan: "knowledge/plans/stage-05/5c-answer-feedback-scoring-retake.md"
report: "knowledge/steps/stage-05/5c-answer-feedback-scoring-retake.md"
---

# Session 5c — Answer / Feedback / Scoring / Retake (HTTP surface)

## Linked documents
- Stage spec: [[specs/stage-05/5-shared-quiz-engine-event-spine]] (§5c, HTTP contract, endpoint behaviour, S2/S4/S5/S7)
- Prior: [[specs/stage-05/5a-quiz-foundation]], [[specs/stage-05/5b-quiz-generation-recovery]]
- Spec: [[specs/stage-05/5c-answer-feedback-scoring-retake]]
- Plan: [[plans/stage-05/5c-answer-feedback-scoring-retake]]
- Report: [[steps/stage-05/5c-answer-feedback-scoring-retake]]

## Goal
Wire the student-facing quiz HTTP endpoints (availability, start, attempt detail, answer, complete) with
visibility on EVERY endpoint, option-identity correctness, DB-idempotent re-answer, MistakeRecord on
incorrect, atomic completion with `completed_quiz`/`perfect_quiz_score` events, Start Over, and an
attempts aggregate. No UI (5d), no new migrations.

## Read first
- Stage spec §"HTTP contract" + §"Endpoint behaviour" + §"Cross-stage seams" (S2/S4/S5/S7)
- `app/domains/student_summaries/{policy,service}.py`, `app/api/routers/student_summaries.py` (gate/router pattern)
- `app/domains/quiz/generation_service.py` (5b start service) + `app/platform/query/quiz_availability_read.py`
- `app/platform/events/recorder.py`, `app/platform/query/student_summary_read.py` (`get_visible_student_section`)

## Source paths likely touched
- `app/domains/quiz/service.py` (new), `app/domains/quiz/schemas.py` (extend)
- `app/api/routers/quiz.py` (new) + `app/main.py` (include router)
- `app/platform/query/quiz_read.py` (new — scoped attempt/question reads + attempts aggregate) OR inline in service
- `tests/test_quiz_endpoints.py` (new)

## Build (endpoint behaviour — the ordering is load-bearing)
- **Non-student → 403 uniformly** on every quiz endpoint (`StudentSummaryAccessPolicy.require_student` before any lookup).
- **Visibility re-checked on EVERY student endpoint** (availability, start, detail, answer, complete): caller owns the attempt AND still assigned AND section still published AND section ∈ {lecture,lab} → else 404. (S7 seam: unpublish hides an in-flight attempt → all endpoints 404; re-publish → resume; no event fires while hidden.)
- **GET availability**: 200 `{availability, reasonCode?}` (read-only, no rows); 404 unpublished/unassigned; 403 non-student.
- **POST start**: visibility+student; resolve active detailed summary (none → 409 `quiz_unavailable`); get-or-create definition; non-terminal exists → resume; terminal → new generating attempt (`attemptNumber+1`); commit; enqueue-after-commit. (Reuses 5b `start_quiz_attempt`.) Start Over = POST start from a terminal attempt (the one-active invariant makes this safe — mid-attempt resumes, never double-creates).
- **GET attempt detail/status**: 200 attempt DTO (no `isCorrect` pre-answer; answered questions embed the `answer` block); 404 not-owner OR section not visible; 403 non-student.
- **POST answer** `{questionId, selectedAnswerOptionId}` — ONE at a time, in this order:
  1. visibility (404 if not) → 2. `attempt.status == in_progress` (else 409); ownership cross-student → 404 →
  3. three-way integrity: `question.quizAttemptId == attemptId` (404); `selectedAnswerOption.quizQuestionId == questionId` (422) →
  4. insert StudentAnswer; on `UNIQUE(quizAttemptId,quizQuestionId)` IntegrityError → return the ORIGINAL AnswerFeedback, `alreadyAnswered=true` (re-submitted option irrelevant) →
  5. `isCorrect` from OPTION IDENTITY only (never position) →
  6. if incorrect → create MistakeRecord (idempotent via its own UNIQUE; `questionSnapshot`/`answerOptionsSnapshot` capture DISPLAY-TIME state, not a live re-query) →
  7. return AnswerFeedback. NO score, NO event.
- **POST complete** `{attemptId}` — the atomic unit: visibility BEFORE the lock (so we don't lock a row we're about to 404); `SELECT ... FOR UPDATE`; strict `status == in_progress` (a `generating`/terminal attempt → 409, never silent complete); all questions answered (always reachable, no skip); if already completed → return cached result; ONE TRANSACTION: counts from StudentAnswer rows inside the lock; `scorePercentage = round(correct/total*100, 2)`; status=completed + counts + completedAt; `EventRecorder(completed_quiz)`; if `correctCount == totalQuestions` → `EventRecorder(perfect_quiz_score)`; commit once. `(eventType,sourceId)` UNIQUE is the duplicate-event backstop; `FOR UPDATE` makes the score deterministic.
- **GET attempts (aggregate)**: visibility+student; `{attemptCount, bestScorePercentage}` for the section's definition (single aggregate query — NOT a paginated list; ADR-041 amended, the envelope's real-consumer proof is deferred to Stage 6/7). null/zero when no definition/attempts.

## Do not build
- UI (5d), real-provider smoke (5d), browser gate (5d).
- Paginated attempts list (aggregate only — no pagination theatre; ADR-041 amendment).
- Any Stage 6 (mistakes-bank read/practice, recap/exam-prep, retake-reinforcement, concept dedup).
- New migrations.

## Data model changes
None.

## API changes
New `quiz` router: `GET /student/sections/{section_id}/quiz/availability`, `POST .../quiz/start`,
`GET /student/quiz/attempts/{attempt_id}`, `POST /student/quiz/attempts/{attempt_id}/answer`,
`POST /student/quiz/attempts/{attempt_id}/complete`, `GET /student/sections/{section_id}/quiz/attempts`.
(Exact paths finalized in the plan; section-scoped entry, no by-question IDOR routes.) `Cache-Control:
private, no-store` on student responses. OpenAPI client regenerated.

## Worker / job changes
None.

## Authz rules
Non-student → 403 (uniform). Visibility (owner + assigned + published + lecture/lab) → 404 on every endpoint.

## Verification
```bash
docker run ... test2-backend python -m pytest -q   # full suite, no regression + new endpoint tests
# tsc + client regen are part of close-out (a router lands → OpenAPI changes).
```

## Done means
- Every endpoint: 403 non-student, 404 hidden/not-owner, visibility re-checked.
- Answer: option-identity correctness; three-way integrity; DB-idempotent re-answer returns ORIGINAL; mistake on incorrect (idempotent snapshot).
- Complete: FOR UPDATE; strict in_progress; atomic score + completed_quiz (+ perfect_quiz_score); idempotent re-complete; visibility before lock; no event while hidden.
- Start Over from terminal; resume on reload.
- Attempts aggregate (count + best).
- Full suite green; OpenAPI client regenerated.

## Amendments
_Add dated entries here if scope changes mid-flight._
