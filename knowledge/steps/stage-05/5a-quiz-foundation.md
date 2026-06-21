---
type: session-report
stage: "05"
session: "5a"
slug: quiz-foundation
status: complete
created: 2026-06-16
updated: 2026-06-20
spec: knowledge/specs/stage-05/5a-quiz-foundation.md
plan: knowledge/plans/stage-05/5a-quiz-foundation.md
---

# Session 5a — Report — Quiz Engine + Event Spine Foundation

## Linked documents
- Stage spec: [[specs/stage-05/5-shared-quiz-engine-event-spine]]
- Spec: [[specs/stage-05/5a-quiz-foundation]]
- Plan: [[plans/stage-05/5a-quiz-foundation]]
- Report: [[steps/stage-05/5a-quiz-foundation]]
- ADRs: [[decisions/adr-040-activity-event-spine]], [[decisions/adr-041-pagination-envelope]], [[decisions/adr-042-quiz-availability-computed-read-only]]

## What shipped (from `git diff` + new files)
Modified:
- `backend/app/platform/db/models/__init__.py` — registered 7 new models (import + `__all__`).
- `backend/tests/conftest.py` — `TRUNCATE_TABLES` gained the 7 tables (children first).
- `backend/tests/test_db_spine.py` — `EXPECTED_TABLES` +7, `EXPECTED_CHECKS` +6, `EXPECTED_INDEXES` +11.

New (migrations 0014–0019):
- `0014_student_activity_events.py`, `0015_quiz_definitions.py`, `0016_quiz_attempts.py`,
  `0017_quiz_questions_answer_options.py`, `0018_student_answers.py`, `0019_mistake_records.py`.

New (models): `student_activity_event.py`, `quiz_definition.py`, `quiz_attempt.py`, `quiz_question.py`,
`answer_option.py`, `student_answer.py`, `mistake_record.py`.

New (platform/domain):
- `app/platform/events/{__init__,recorder}.py` — `EventRecorder` + `QUIZ_EVENT_TYPES` constants.
- `app/platform/query/pagination.py` — `PaginatedResponse[T]` + `PaginationMeta`.
- `app/platform/query/quiz_availability_read.py` — `get_quiz_availability` (read-only).
- `app/domains/quiz/{__init__,schemas.py}` — student-safe DTOs.

New (tests): `test_quiz_schema.py` (10), `test_event_recorder.py` (5), `test_quiz_schemas_dto.py` (3).

## Verification (real output)
Run with this workspace's code mounted over `/app` in the `test2-backend` image, against an ISOLATED
fresh DB (`xyz_lms_5a` / `xyz_lms_5a_test`) on the shared Postgres — NOT the shared `xyz_lms` (which is
on a different branch's migration lineage; see Deviations):

```
$ docker run --rm --network test2_default --env-file <container-env> \
    -e DATABASE_URL=...@db:5432/xyz_lms_5a -e TEST_DATABASE_URL=...@db:5432/xyz_lms_5a_test \
    -v <workspace>/backend:/app -w /app test2-backend python -m pytest -q
407 passed, 111 warnings in 37.23s
```

- `407 passed` = 389 baseline (spec-5 / 4.7 main) + 18 new tests. No failures, no regressions.
- The suite includes `test_migration_round_trip` (alembic upgrade head → downgrade base → upgrade head)
  and `test_expected_tables_exist_after_upgrade_head` (asserts the 7 tables, 6 CHECKs, 11 indexes are
  present and that every new table's `id` has no server default) — both green.
- `alembic heads` from the mounted code = `0019 (head)`; `app` resolves to `/app/app/__init__.py`
  (mount confirmed running this workspace's code).

Throwaway DBs `xyz_lms_5a` / `xyz_lms_5a_test` were dropped after the run. `xyz_lms` / `xyz_lms_test`
were never touched.

## Deviations / findings
1. **The `test2-*` containers run a DIFFERENT branch.** `test2-backend-1` has migrations
   `0014_summary_truncation_flag`, `0015_map_reduce_summaries`, `0016_brief_from_detailed` (summary
   work, not Stage 5), and the shared `xyz_lms` dev DB is stamped at that lineage's `0016`. The plan's
   `docker exec test2-backend-1 alembic upgrade head` would have failed/corrupted, so verification was
   done against an isolated DB with this workspace's code mounted. **This is a migration-number
   collision** with the assigned block 0014–0019 — clean on `spec-5` (0001→0019 is a linear chain) but
   conflicting at merge. Logged in open-questions.md as a coordination item.
2. **`answer_option.py` import shadowing.** The column named `text` shadowed the imported
   `sqlalchemy.text` within the class body (`server_default=text("now()")` → "MappedColumn not
   callable"). Fixed by importing `text as sa_text` in that file. Caught by the first suite run.
3. **D1 (event_type CHECK)** resolved as recommended: CHECK encodes the 2 emitted values + app-layer
   `QUIZ_EVENT_TYPES`; widened per consuming slice. ADR-040.

## Modified prior sessions
- None of the prior sessions' source files were changed in their behavior. `conftest.py` and
  `test_db_spine.py` (originally from earlier stages) were extended additively (new tables only).

## Close-the-loop checklist
- [x] Spec exists and is `status: done`
- [x] Plan existed and was approved before any source edits (plan-mode approval)
- [x] Stayed in scope; one in-scope fix recorded (answer_option import)
- [x] Verification run; real output recorded (407 passed)
- [x] Report written from `git diff` + command output, not memory
- [x] spec ↔ plan ↔ report links resolve (frontmatter + wikilinks)
- [x] `STATUS.md` overwritten
- [x] `log.md` appended
- [ ] `architecture/` — not updated (no architecture doc covers the new quiz domain yet; defer to 5b when endpoints/services land)
- [x] ADRs added: 040 (event spine), 041 (pagination envelope), 042 (computed availability)
- [x] `open-questions.md` updated (migration collision)

## Change history
- 2026-06-16 — [Session 5a] initial report. Stage 5a foundation landed + verified (407 passed) on an isolated DB.
- 2026-06-16 22:46 — [Session 5e] added missing negative CHECK tests for quiz_mode, failure_category, question_type, and source_type; focused Stage 5 set passed (61), full backend passed (442).
- 2026-06-20 23:12 — [Session 10] extended `backend/tests/conftest.py` truncation with
  `student_badges` and `student_streak_state` so Stage 10 gamification tables are cleaned in backend tests.
