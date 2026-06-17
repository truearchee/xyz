---
type: session-spec
stage: "05"
session: "5a"
slug: quiz-foundation
status: done
created: 2026-06-16
updated: 2026-06-16
owner: developer
plan: "knowledge/plans/stage-05/5a-quiz-foundation.md"
report: "knowledge/steps/stage-05/5a-quiz-foundation.md"
---

# Session 5a — Quiz Engine + Event Spine Foundation (NO AI)

## Linked documents
- Stage spec: [[specs/stage-05/5-shared-quiz-engine-event-spine]]
- Spec: [[specs/stage-05/5a-quiz-foundation]]
- Plan: [[plans/stage-05/5a-quiz-foundation]]
- Report: [[steps/stage-05/5a-quiz-foundation]]

## Goal
Land the Stage 5 schema + event spine (migrations 0014–0019, 7 tables + 7 models) plus the pagination
envelope, the read-only quiz-availability model, the `EventRecorder`, and student-safe quiz DTOs —
the HARD GATE that must exist before any generation code (5b–5d).

## Why now
Stage 5 (shared quiz engine + event spine) is the next roadmap stage. The stage spec's HARD GATE is
"schema + event spine land before any generation code exists." Migration block 0014–0019 maps exactly
to 5a's seven tables. 5b–5d are later sessions and are designed to need no further migrations (all
forward-looking columns land now).

## Read first
- `knowledge/specs/stage-05/5-shared-quiz-engine-event-spine.md` (the stage spec — authoritative)
- `backend/alembic/versions/0012_maintenance_run.py` (migration pattern)
- `backend/app/platform/query/student_summary_read.py` (`get_section_summary_inputs`, `get_visible_student_section` — reused by the availability model)
- `backend/app/domains/student_summaries/precedence.py` (`derive_slot_state`, READY — reused for availability)

## Source paths likely touched
- `backend/alembic/versions/0014..0019_*.py`
- `backend/app/platform/db/models/{student_activity_event,quiz_definition,quiz_attempt,quiz_question,answer_option,student_answer,mistake_record}.py` + `__init__.py`
- `backend/app/platform/events/` (new)
- `backend/app/platform/query/{pagination,quiz_availability_read}.py` (new)
- `backend/app/domains/quiz/schemas.py` (new)
- `backend/tests/{conftest,test_db_spine,test_quiz_schema,test_event_recorder,test_quiz_schemas_dto}.py`

## Build
- 7 tables via migrations 0014–0019 (event spine, quiz_definitions, quiz_attempts, quiz_questions+answer_options, student_answers, mistake_records) + 7 ORM models.
- `EventRecorder.record` — same-transaction insert, never commits; `(event_type, source_id)` idempotency.
- `PaginatedResponse[T]` envelope (defined once).
- Read-only availability model (computes availability; creates no rows; reuses 4.7 visibility + readiness).
- Student-safe quiz DTOs (structurally cannot leak `isCorrect` pre-answer).
- Tests: schema round-trip, every UNIQUE/partial-unique/CHECK, event same-txn + idempotency, DTO no-leak.

## Do not build
- Any AI/generation (5b), answer/feedback/scoring/retake endpoints (5c), UI (5d).
- Any HTTP router/endpoint wiring (availability *read model* + DTOs only; endpoints land with 5b/5c).
- Any Stage 6 logic (mistake-review prefix, retake-correct flips, question pools).
- Migrations beyond 0019.

## Data model changes
7 new tables: `student_activity_events`, `quiz_definitions`, `quiz_attempts`, `quiz_questions`,
`answer_options`, `student_answers`, `mistake_records`. See the plan for full column specs.

## API changes
None (no endpoints wired in 5a).

## Worker / job changes
None.

## Authz rules
None enforced here. The availability read model returns `None` when the section is not visible (caller
maps to the pinned 404 in 5b/5c); the 403 student gate stays in the future endpoint.

## Verification
```bash
# Full suite incl. test_migration_round_trip (up→down→up) + test_expected_tables_exist_after_upgrade_head,
# run against an ISOLATED fresh DB with this workspace's code mounted (the test2-* container runs a
# different branch — see report's Deviations).
docker run --rm --network test2_default --env-file <container-env> \
  -e DATABASE_URL=...@db:5432/xyz_lms_5a -e TEST_DATABASE_URL=...@db:5432/xyz_lms_5a_test \
  -v <workspace>/backend:/app -w /app test2-backend python -m pytest -q
# Expected: 407 passed (389 baseline + 18 new), 0 failures.
```

## Knowledge updates required
- `knowledge/steps/stage-05/5a-quiz-foundation.md` (report)
- `knowledge/STATUS.md`, `knowledge/log.md`
- `knowledge/decisions/adr-040..042` (event spine; pagination envelope; computed availability)
- `knowledge/open-questions.md` (migration-number collision with sibling branch)

## Done means
- `alembic upgrade head` / `downgrade base` / `upgrade head` round-trips clean on a fresh DB.
- 7 tables + 7 models present and registered; all CHECK/UNIQUE/partial-unique guards enforced.
- `EventRecorder` proven same-transaction + idempotent; DTOs proven no-leak.
- Full suite green, no regression.

## Amendments
- 2026-06-16: `answer_option.py` import collision (`text` column shadowed `sqlalchemy.text`) — fixed
  by aliasing the import to `sa_text` in that file. No scope change.
