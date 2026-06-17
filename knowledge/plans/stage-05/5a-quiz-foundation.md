---
type: session-plan
stage: "05"
session: "5a"
slug: quiz-foundation
status: executed
created: 2026-06-16
updated: 2026-06-16
spec: knowledge/specs/stage-05/5a-quiz-foundation.md
report: knowledge/steps/stage-05/5a-quiz-foundation.md
---

# Session 5a — Implementation Plan — Quiz Engine + Event Spine Foundation

## Linked documents
- Spec: [[specs/stage-05/5a-quiz-foundation]]
- Plan: [[plans/stage-05/5a-quiz-foundation]]
- Report: [[steps/stage-05/5a-quiz-foundation]]

## Scope confirmation
Delivers Stage 5a foundation only: 7 tables (migrations 0014–0019) + 7 ORM models, `EventRecorder`,
`PaginatedResponse`, the read-only availability model, and student-safe DTOs, with full schema/event
tests. Does NOT build generation (5b), answer/scoring endpoints (5c), UI (5d), or any HTTP routing.

## Approach
Mirror the established platform conventions exactly: flat models in `app/platform/db/models/`
registered in `__init__.py`; hand-written idempotent migrations (existence-checked guards, downgrade
mirrors, partial-unique via `postgresql_where`); reuse the 4.7 visibility scoped query
(`get_visible_student_section`) and the 4.7 readiness predicate (`derive_slot_state`/READY) for the
availability model so quiz availability is never more permissive than summary visibility; `EventRecorder`
inserts via `session.flush()` inside the caller's transaction and never commits.

## Migration grouping (0014–0019)
| Rev | Table(s) |
|-----|----------|
| 0014 | `student_activity_events` (UNIQUE(event_type,source_id); CHECK event_type) |
| 0015 | `quiz_definitions` (partial-UNIQUE post_class per section; CHECK quiz_mode) |
| 0016 | `quiz_attempts` (one-active partial-UNIQUE; UNIQUE(student,def,attempt#); CHECK status + failure_category) |
| 0017 | `quiz_questions` + `answer_options` (CHECK question_type, source_type) |
| 0018 | `student_answers` (UNIQUE(attempt,question)) |
| 0019 | `mistake_records` (UNIQUE(attempt,question)) + deferred FK quiz_questions.source_mistake_record_id→mistake_records |

Full column specs are in the approved plan file (system plan) and the migrations themselves.

## Key decisions
- **D1 (event_type CHECK):** encoded only the 2 Stage-5-emitted values (`completed_quiz`,
  `perfect_quiz_score`) + the app-layer `QUIZ_EVENT_TYPES` guard; widened per consuming slice (same
  pattern 0011 used to widen `failure_category`). → ADR-040.
- **failure_category CHECK:** the spec Lock 4 set (`generation_timeout`, `provider_error`,
  `invalid_output`, `enqueue_failed`, `crashed`) encoded now so 5b needs no migration.
- **source_mistake_record_id FK:** column created bare in 0017, FK added in 0019 (after
  `mistake_records` exists) to keep the natural definitions→attempts→questions order while still wiring
  the FK within Stage 5's block. The ORM model leaves the column FK-less (DB enforces integrity).
- **Pagination envelope** offset-based, defined once. → ADR-041.
- **Availability computed/read-only**, no GET-side writes, reuses 4.7 predicates. → ADR-042.

## Test strategy
`test_db_spine` extended (EXPECTED_TABLES/CHECKS/INDEXES) — `test_migration_round_trip` proves the
fresh-DB up→down→up gate; `test_expected_tables_exist_after_upgrade_head` proves all objects exist.
`test_quiz_schema` proves every UNIQUE/partial-unique/CHECK via IntegrityError. `test_event_recorder`
proves same-transaction insert, no-commit, idempotency, and pins `QUIZ_EVENT_TYPES` to the DB CHECK.
`test_quiz_schemas_dto` proves the student option/question DTOs cannot serialize `isCorrect`/explanation
pre-answer (with a positive control on `AnswerFeedback`).

## Risks & mitigations
- **Migration-number collision (realized):** a sibling workspace/branch already uses 0014–0016 for
  summary work (visible in the running `test2-*` stack). On `spec-5` the 0001→0019 chain is clean, but
  this collides at merge. → logged in open-questions; verified my work on an isolated DB instead of the
  shared `xyz_lms`.
- **`text` column vs `sqlalchemy.text` shadowing** in `answer_option.py` → fixed by aliasing import.

## Open questions
- Migration block 0014–0019 vs the sibling branch's 0014–0016 summary migrations — reconcile at merge
  (renumber one side). See open-questions.md.
