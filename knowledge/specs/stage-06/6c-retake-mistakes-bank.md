---
type: session-spec
stage: "06"
session: "6c"
slug: retake-mistakes-bank
status: done
created: 2026-06-17
updated: 2026-06-17
owner: developer
plan: knowledge/plans/stage-06/6c-retake-mistakes-bank.md
report: knowledge/steps/stage-06/6c-retake-mistakes-bank.md
---

# Session 6c — Retake reinforcement + mistakes-bank

## Linked documents
- Overview spec: [[specs/stage-06/6-complete-quiz-modes]]
- Spec: [[specs/stage-06/6c-retake-mistakes-bank]]
- Plan: [[plans/stage-06/6c-retake-mistakes-bank]]
- Report: [[steps/stage-06/6c-retake-mistakes-bank]]
- Foundation: [[steps/stage-06/6a-pool-foundation]], [[steps/stage-06/6b-recap-examprep-authorization]], [[decisions/adr-047-section-question-pool-capacity]]
- Coordination: [[steps/findings-6-shared-infra]]

## Goal
Retake reinforcement and the mistakes-bank backend work for the already-built quiz modes: retakes start
with a student's own still-active mistake prefix, correct answers to that prefix flip it off after two
cumulative source-quiz retake successes, and the per-module mistakes-bank assembles only from the current
student's mistake snapshots with 404-not-403 authorization.

## Why now
6b made recap/exam-prep attempts reachable and already pulled the event metadata + pooled mistake creation
plumbing forward. 6c completes the remaining backend behavior needed before the 6d UI/browser gate can prove
the headline flow: original quiz with mistakes → retake prefix → two correct retake answers → prefix gone
while the mistake remains available in the bank.

## Developer handoff preserved
- "6b accepted against spec v2 — verification clears the gate, and the post-class byte-identical
  preservation plus the explicitly-named reuse proof are confirmed."
- "Confirm the recap `scope_key` is derived from structural + publication eligibility (lecture/lab,
  published-for-student) and is stable regardless of summary processing state — i.e. summary-READY is the
  all-or-wait availability gate layered on top, not a component of `scope_key`."
- "The mistakes-bank's own-student-only authorization + 404 rules land in 6c — make them explicit gate
  proofs (student B never sees student A's mistakes; cross-course / unassigned → 404, session kept on
  403)."
- "Confirm the bank grouping unit. You've scoped it per module. That's almost certainly the right reading
  of the product owner's 'categorized by course' (module = the enrolled subject). Flag in the 6c spec only
  if this codebase has a course-above-module concept that would change the grouping; otherwise proceed
  per-module."
- "Event/feature names from the shared registry — already tracked; keep reading `completed_quiz` /
  `perfect_quiz_score` from the Stage 5 constants, not a local copy."
- "Proceed: write the 6c spec/plan (lighter scope as you noted — retake-prefix flip mechanics + bank
  assembly + bank authorization, since mistake-creation and event metadata already landed in 6b). Stop at
  the 6c backend-verified gate and report."

## Read first
- [[specs/stage-06/6-complete-quiz-modes]] — Retake reinforcement, mistakes-bank, Authorization & visibility
- [[steps/stage-06/6b-recap-examprep-authorization]] — 6b amendments that pulled event metadata + pooled
  mistake creation forward
- `backend/app/domains/quiz/service.py` — `answer()`, `complete()`, recap/exam-prep endpoints
- `backend/app/domains/quiz/assembly_service.py` — pooled attempt snapshot assembly
- `backend/app/domains/quiz/mistakes.py` — pooled mistake upsert identity
- `backend/app/platform/query/quiz_read.py` — unified attempt visibility and question read

## Source paths likely touched
- `backend/app/domains/quiz/service.py`
- `backend/app/domains/quiz/assembly_service.py`
- `backend/app/domains/quiz/scope_service.py`
- `backend/app/domains/quiz/schemas.py`
- `backend/app/api/routers/quiz.py`
- `backend/app/platform/query/quiz_read.py`
- `backend/tests/test_quiz_mistakes_bank.py` or focused additions to existing quiz tests
- Generated API client if route/schema contract changes

## Build
- **Retake prefix assembly:** pooled retakes for source quizzes render the current student's
  `show_in_retake_prefix=true` `MistakeRecord` rows for that same `QuizDefinition` first, from snapshots,
  as `QuizQuestion.source_type='mistake_review'` with `source_mistake_record_id` set. The fresh pool sample
  then excludes prefixed `source_pool_question_id` values and fills the normal new-question portion.
- **Flip-at-2:** in `answer()`, on the first successful `StudentAnswer` insert only, a correct answer to a
  `mistake_review` question increments `MistakeRecord.retake_correct_count` and flips
  `show_in_retake_prefix=false` once the new count reaches 2. This applies to source-quiz retakes only, not
  `mistakes_bank` practice (D2 default).
- **Mistakes-bank definition/start:** one shared `mistakes_bank` `QuizDefinition` per module with
  `scope_key=str(module_id)`. A student start assembles an attempt from that student's mistake snapshots in
  the module. No pool generation and no AI calls.
- **Mistakes-bank list:** provide a paginated current-student-only bank list for a module using the existing
  pagination envelope. Empty modules return an empty page, not an error, for assigned students.
- **Authorization gate proofs:** student B cannot see or start from student A's mistakes; unassigned or
  cross-module access returns 404. Wrong role remains 403 before resource lookup, preserving session.
- **Scope-key invariant:** leave 6b recap `scope_key` structural/publication based. Summary READY remains
  an all-or-wait availability gate layered above the key; it must not become part of the dedup key.

## Do not build
- No UI, mode selector, bank screen, or browser gate (6d).
- No post-class retrofit (6d).
- No new migration unless a code-level blocker proves one is required; Stage 6 may use 0026–0029, but 6c is
  expected to be schema-free because Stage 5/6a/6b already added the necessary fields/indexes.
- No new event type or AIRequestLog feature name. Read `COMPLETED_QUIZ` / `PERFECT_QUIZ_SCORE` from
  `app.platform.events`; do not create local copies.
- No change to recap/exam-prep authorization or canonical-key grain except tests/documentation that pin the
  existing 6b invariant.
- No cross-module or all-subject combined mistakes pile. This codebase's grouping/authz unit is
  `course_modules`; there is no separate course-above-module entity in the quiz domain.

## Data model changes
None expected. Existing fields support 6c:
- `QuizQuestion.source_type`, `source_mistake_record_id`, `source_pool_question_id`
- `QuizAttempt.new_question_count`, `mistake_review_question_count`
- `MistakeRecord.retake_correct_count`, `show_in_retake_prefix`, `source_pool_question_id`
- `QuizDefinition.quiz_mode='mistakes_bank'`, nullable section, `scope_key`

## API changes
- Student: start/list mistakes-bank endpoints under the `/student/modules/{module_id}/...` surface.
- The bank list must use `PaginatedResponse[T]`.
- Existing attempt detail/answer/complete endpoints continue to serve all modes through unified visibility.
- Regenerate the OpenAPI client if route/schema contracts change.

## Worker / job changes
None expected. Mistakes-bank assembly should be synchronous/no-AI because it snapshots existing
`MistakeRecord` rows. Source-quiz retakes continue through the existing 6a pooled assembly path.

## Authz rules
- Student role gate returns 403 before any lookup.
- Assigned active student membership in the module is required; missing membership or cross-module scope
  returns 404.
- Bank list/start reads only `MistakeRecord.student_id == current_user.user_id`; a student can never see or
  practice another student's mistakes.
- Mistake-record ids are not accepted from the client for bank assembly; the server derives the current
  student's eligible records by module.

## Verification
- `pytest -q backend/tests/test_quiz_mistakes_bank.py backend/tests/test_quiz_recap_examprep.py backend/tests/test_quiz_pool.py`
  → 6c gates pass and 6a/6b regressions remain green.
- `pytest -q` → full backend suite passes.
- `ruff check .` → clean.
- `alembic heads` → single head remains 0025 if no migration is needed, or the new single head if a justified
  6c migration is added inside 0026–0029.
- `bash scripts/generate-api-client.sh` and frontend `tsc --noEmit` if API contract changed.

## Knowledge updates required
- `knowledge/steps/stage-06/6c-retake-mistakes-bank.md`
- `knowledge/STATUS.md`
- `knowledge/log.md`
- Append change-history lines to prior reports only for prior-session files changed by 6c.

## Done means
Retakes have an exact mistake-review prefix and the cumulative two-correct source-quiz flip; mistakes-bank
starts/lists per module using only the current student's snapshots; own-student-only and 404/403 rules are
proven by backend tests; no new event/feature names are forked; backend verification is green; report is
written from `git diff` and real command output. Stage 6 remains open until the 6d browser gate.

## Amendments
_Add dated entries here if scope changes mid-flight. Do not silently edit the sections above._
- **2026-06-17 — counter implementation detail:** The spec/plan called for a guarded single-statement
  flip-at-2 update. The first full-suite run exposed that PostgreSQL evaluated the expression in a way that
  cleared the prefix after one correct answer. The implementation was changed to a row-locked read/mutate
  inside the existing answer transaction. The behavior remains exactly the accepted D2 rule: 0→1 keeps the
  prefix; 1→2 clears it; duplicate answers do not count.
