---
type: session-plan
stage: "06"
session: "6c"
slug: retake-mistakes-bank
status: executed
created: 2026-06-17
updated: 2026-06-17
spec: knowledge/specs/stage-06/6c-retake-mistakes-bank.md
report: knowledge/steps/stage-06/6c-retake-mistakes-bank.md
---

# Session 6c — Implementation Plan — Retake reinforcement + mistakes-bank

## Linked documents
- Spec: [[specs/stage-06/6c-retake-mistakes-bank]]
- Plan: [[plans/stage-06/6c-retake-mistakes-bank]]
- Report: [[steps/stage-06/6c-retake-mistakes-bank]]
- Foundation: [[steps/stage-06/6a-pool-foundation]], [[steps/stage-06/6b-recap-examprep-authorization]]
- Coordination: [[steps/findings-6-shared-infra]]

## Scope confirmation
This delivers the backend-only 6c slice: source-quiz retake prefix, flip-at-2 mechanics, per-module
mistakes-bank list/start, and own-student-only/404 authorization proofs. It does not build UI, browser
gates, post-class retrofit, or any new shared event/feature names. The plan treats the current prompt as
explicit approval to proceed through the backend gate after filing these artifacts.

Confirmed 6b invariant: recap `scope_key` is derived from the sorted eligible section ids after structural
and publication/student filters; summary READY is the D3 all-or-wait gate layered on top and is not a key
component. Confirmed grouping: this codebase's enrollment/authz unit is `course_modules`, and there is no
course-above-module quiz entity; mistakes-bank is therefore per module.

## Approach
Keep all bank and prefix materialization server-derived. Retake prefix questions are generated from
`MistakeRecord` snapshots before pool sampling, and pool sampling excludes those prefixed pool questions.
Correct answers to prefix questions update the linked `MistakeRecord` with one guarded `UPDATE` after the
first successful `StudentAnswer` insert. The bank is a separate `mistakes_bank` definition per module, but
attempt questions are all `mistake_review` snapshots and never invoke pool generation.

## Changes, file by file
- `backend/app/domains/quiz/assembly_service.py` — load prefix `MistakeRecord` rows for non-bank pooled
  source-quiz attempts; snapshot them as `mistake_review` questions with `source_mistake_record_id`; exclude
  their `source_pool_question_id` values from the fresh pool sample; set `mistake_review_question_count`
  and `new_question_count`. Add a separate synchronous helper to assemble a bank attempt from a student's
  module mistakes.
- `backend/app/domains/quiz/service.py` — add `mistakes_bank` list/start service functions; in `answer()`,
  after successful insert and only for correct source-quiz `mistake_review` answers, increment
  `retake_correct_count` and flip `show_in_retake_prefix` false at 2. Gate out `quiz_mode='mistakes_bank'`.
- `backend/app/domains/quiz/scope_service.py` — add `MISTAKES_BANK_MODE` and a get-or-create helper for the
  shared per-module `mistakes_bank` definition (`scope_key=str(module_id)`, empty or module source scope).
- `backend/app/platform/query/quiz_read.py` — add current-student paginated mistake-bank query for a module
  using `PaginatedResponse` metadata; preserve existing visibility behavior.
- `backend/app/domains/quiz/schemas.py` — add mistake-bank DTO(s) and start/list response schema only if the
  existing attempt DTO and generic pagination envelope are insufficient.
- `backend/app/api/routers/quiz.py` — add student bank list/start routes with `Cache-Control:
  private, no-store`.
- `backend/tests/test_quiz_mistakes_bank.py` — new focused 6c gate tests for prefix ordering/counts,
  flip-at-2 idempotency, bank assembly, and own-student/404/403 authorization.
- Generated frontend client — regenerate if routes/schemas changed.
- Knowledge files — report, `STATUS.md`, `log.md`, and prior-report change history if source edits touch
  completed-session files.

## Order of operations
1. Add 6c tests first around existing helpers: retake prefix from snapshots, flip counter, bank list/start,
   student-B isolation, unassigned 404, wrong-role 403.
2. Implement prefix assembly in `assembly_service`; keep post-class and recap/exam-prep existing paths
   otherwise intact.
3. Implement flip-at-2 in `service.answer()` with the existing answer idempotency boundary.
4. Implement bank list/start routes and schemas; derive all mistake ids from current user + module.
5. Regenerate client if the API contract changed.
6. Run focused tests, full backend, ruff, Alembic head check, and frontend type-check if client changed.
7. Write the evidence-based 6c report and close knowledge links/status/log.

## Test strategy
- Prefix: create a pooled source quiz with two active mistakes; next retake starts with those exact
  snapshots first, records `source_type='mistake_review'`, sets `source_mistake_record_id`, excludes their
  pool ids from new generated questions, and records the split counts.
- Flip: a correct answer to the same prefix mistake across two source-quiz retakes increments
  `retake_correct_count` from 0→1→2 and flips `show_in_retake_prefix=false`; a duplicate answer does not
  double-count; a wrong answer does not count; bank practice does not count.
- Bank: assigned student lists a paginated module bank and starts a bank attempt assembled only from their
  module mistakes, with no pool/AI enqueue. Empty assigned module returns an empty page.
- Authorization: student B cannot list/start from student A's mistakes; unassigned/cross-module returns
  404; non-student gets 403 before lookup.
- Regression: 6a/6b focused tests still pass, especially recap/exam-prep visibility and pool reuse.

## Risks & mitigations
- Prefix assembly can accidentally starve fresh questions if the prefix is large. Mitigation: fill remaining
  new-question slots from pools after prefix; if prefix exceeds the normal target, keep the exact active
  prefix and record split counts honestly.
- Retake counting can double-count on duplicate submits. Mitigation: run the update only after the
  successful `StudentAnswer` insert path, never the `IntegrityError` reread path.
- Bank practice could mutate prefix state if it reuses `mistake_review`. Mitigation: gate the counter update
  by `visible.quiz_mode != 'mistakes_bank'`.
- Authorization can leak by accepting mistake ids from the client. Mitigation: no client-supplied mistake ids
  for assembly; every query filters `MistakeRecord.student_id == current_user.user_id`.

## Open questions
- None blocking. Bank grouping is per module after checking the codebase model boundary.
