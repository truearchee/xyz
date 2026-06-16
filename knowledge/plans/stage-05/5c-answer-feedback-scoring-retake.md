---
type: session-plan
stage: "05"
session: "5c"
slug: answer-feedback-scoring-retake
status: executed
created: 2026-06-16
updated: 2026-06-16
spec: knowledge/specs/stage-05/5c-answer-feedback-scoring-retake.md
report: knowledge/steps/stage-05/5c-answer-feedback-scoring-retake.md
---

# Session 5c — Implementation Plan — Answer / Feedback / Scoring / Retake

## Linked documents
- Spec: [[specs/stage-05/5c-answer-feedback-scoring-retake]]
- Stage spec: [[specs/stage-05/5-shared-quiz-engine-event-spine]]
- Plan: [[plans/stage-05/5c-answer-feedback-scoring-retake]]
- Report: [[steps/stage-05/5c-answer-feedback-scoring-retake]]
- Prior: [[steps/stage-05/5b-quiz-generation-recovery]]

## Scope confirmation
The student HTTP surface for quizzes: availability, start (= Start Over), attempt detail, answer,
complete, attempts-aggregate — with visibility on every endpoint, option-identity correctness,
DB-idempotent re-answer, MistakeRecord on incorrect, atomic completion + events. NO UI (5d), NO new
migrations (heads stays 0020), NO paginated attempts list (aggregate only — ADR-041 amended).

## Decisions locked (developer, this session)
- Attempts surface = **aggregate** (`COUNT(*)` + `MAX(score_percentage)`), not a paginated list. ADR-041 amended; envelope's real-consumer proof deferred to Stage 6/7.
- Complete validates `status == in_progress` STRICTLY; `generating` (even with questions) or terminal → 409.
- AIRequestLog mid-call-crash residual is Stage-8-owned — NOT touched here (ADR-046).

## Approach
Mirror the 4.7 student surface: a `quiz` router whose endpoints are thin, delegating to
`app/domains/quiz/service.py`; the role gate (`StudentSummaryAccessPolicy.require_student` → 403) and
the visibility gate (scoped read → pinned 404) fire in the service before any resource work; scoped
reads live in `app/platform/query/quiz_read.py`. `Cache-Control: private, no-store` on every response.
Reuse 5b `start_quiz_attempt` (build a factory from `db.bind` for its commit + enqueue-after-commit).
Reuse 5a `get_quiz_availability`. Reuse the `EventRecorder` (same-transaction emit).

## Changes, file by file
- `app/platform/query/quiz_read.py` (new): `get_visible_attempt(db, student_id, attempt_id) -> VisibleAttempt | None` (JOIN attempt→definition→section→module→membership enforcing owner + published + active + member + section.type ∈ {lecture,lab}; None → 404). `get_attempt_questions_for_student(db, attempt_id)` (questions ordered by display_order + options ordered by display_order + the student's StudentAnswer per question). `get_attempts_aggregate(db, student_id, definition_id) -> {count, best}`. All read-only, no row creation.
- `app/domains/quiz/schemas.py` (extend): add `AnswerSubmission` (request: question_id, selected_answer_option_id), `QuizAttemptsSummary` (attempt_count, best_score_percentage|None). Confirm `QuizAttemptForStudent` embeds `answer` per question; `AnswerFeedback`, `QuizAttemptResult`, `QuizAvailabilityResponse` already drafted in 5a.
- `app/domains/quiz/service.py` (new): the six service functions (below). Custom HTTPException mapping (403/404/409/422). Reuses `start_quiz_attempt`, `get_quiz_availability`, `get_visible_attempt`, `EventRecorder`.
- `app/api/routers/quiz.py` (new): thin endpoints, `DbSession`/`CurrentUser` aliases, `Cache-Control: private, no-store`. Section-scoped + attempt-scoped routes; NO by-question route (IDOR closure).
- `app/main.py`: `include_router(quiz_router)`.
- `tests/test_quiz_endpoints.py` (new).
- Close-out: regenerate OpenAPI client (`scripts/generate-api-client.sh`) since a router lands.

## Service functions (the ordering is the spec)
- `availability(db, current_user, section_id)`: require_student; `get_quiz_availability` → None → 404 pinned; else `QuizAvailabilityResponse{availability: 'available'|'unavailable', reasonCode?}`.
- `start(db, current_user, section_id)`: require_student; `get_visible_student_section` → None → 404; `start_quiz_attempt(sessionmaker(db.bind), student_id, section_id, enqueue=True)`; map `QuizUnavailableError`→409 `quiz_unavailable`, `SectionNotFoundError`→404; return the attempt detail DTO (resumed or created).
- `get_attempt(db, current_user, attempt_id)`: require_student; `get_visible_attempt` → None → 404; build `QuizAttemptForStudent` (no isCorrect on unanswered options; answered → embed `answer`).
- `answer(db, current_user, attempt_id, payload)`: require_student; visibility (404); `attempt.status==in_progress` else 409; three-way integrity (question→attempt 404; option→question 422); insert StudentAnswer, on UNIQUE IntegrityError → return ORIGINAL AnswerFeedback `alreadyAnswered=true`; `is_correct` from the selected option's `is_correct`; if incorrect → idempotent MistakeRecord (snapshot question+options as serialized at read time); return AnswerFeedback (no score/event). One transaction for the answer+mistake insert; the IntegrityError path rolls back to a savepoint and re-reads.
- `complete(db, current_user, attempt_id)`: require_student; visibility (404) BEFORE the lock; `SELECT attempt FOR UPDATE`; if completed → return cached `QuizAttemptResult`; strict `status==in_progress` else 409; assert all questions answered (else 409 — shouldn't happen, no skip); ONE TRANSACTION: count correct/total from StudentAnswer; `score=round(correct/total*100,2)`; set status=completed+counts+completedAt; `EventRecorder.record(completed_quiz, source_id=attempt.id, module_id=definition.module_id, metadata=...)`; if correct==total → `record(perfect_quiz_score, ...)`; commit once; return result.
- `attempts_summary(db, current_user, section_id)`: require_student; visibility; `get_attempts_aggregate` → `QuizAttemptsSummary`.

## Visibility seam (S7)
`get_visible_attempt` is the single gate: it JOINs through to the live publish/membership state, so an
unpublished-mid-attempt section yields None → 404 on detail/answer/complete; re-publish → visible again
→ resume. Complete checks visibility BEFORE `FOR UPDATE` (never lock a row we'll 404). No event fires
while hidden because complete 404s before the EventRecorder call.

## Test strategy (tests/test_quiz_endpoints.py, auth_client + jwt)
Seed (committed): student+lecturer+admin, module, membership, published lecture section, active
transcript + eligible detailed summary; start + generate (deterministic) to reach `in_progress` with 10
questions. Then:
- non-student (lecturer/admin) → 403 on every endpoint; unassigned student → 404.
- answer: correct→feedback isCorrect true, no mistake; incorrect→isCorrect false + MistakeRecord created; re-answer (different option) → ORIGINAL feedback, alreadyAnswered, no 2nd StudentAnswer, no 2nd mistake; cross-attempt question → 404; option from another question → 422; answer when not in_progress → 409.
- complete: all-answered → score, status completed, `completed_quiz` event row in same txn; all-correct → `perfect_quiz_score` too; re-complete → cached, no duplicate event; complete a `generating` attempt → 409.
- S7: start (published) → unpublish section → detail/answer/complete all 404 → re-publish → resume + complete works; assert NO event row while hidden.
- availability: 200 available; summary-not-ready → unavailable+reasonCode; unpublished → 404; non-student → 403.
- start/resume: second start mid-attempt resumes; Start Over after completion → new attempt (attemptNumber+1).
- attempts aggregate: count + best score.

## Risks & mitigations
- IntegrityError handling inside a request transaction → use `begin_nested()` savepoints around the StudentAnswer + MistakeRecord inserts; on conflict re-read the original. (Mirror 5b's start race.)
- Event-while-hidden → visibility before the lock + before any EventRecorder call.
- Score float-eq → counts only (`correct == total`), never float compare (5a `score_percentage` is Numeric).
- OpenAPI drift → regenerate the client in close-out; `tsc` clean.

## Open questions
- None blocking. (Attempts-aggregate vs paginated resolved → aggregate; ADR-041 amended.)
