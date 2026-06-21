---
type: session-plan
stage: 10
session: "10a"
slug: foundation
status: approved     # proposed → approved → executed
created: 2026-06-20
updated: 2026-06-20
spec: knowledge/specs/stage-10/10-gamification.md
report: "knowledge/steps/stage-10/10a-foundation.md"
---

# Session 10a — Implementation Plan — Gamification Foundation

## Linked documents
- Spec: [[specs/stage-10/10-gamification]]
- Plan: [[plans/stage-10/10a-foundation]]
- Report: [[steps/stage-10/10a-foundation]]
- ADRs: [[decisions/adr-056-gamification-course-timezone]] · [[decisions/adr-057-gamification-on-read-evaluation]]

## Scope confirmation
**Delivers (10a):** the configured-timezone setting; the content-domain `studied_section` engagement
event (unique-per-day, reliable) + its CHECK-widen migration; the read-only `platform/query` primitives
`scheduled_class_days` / `engagement_days`; the pure `derive_streak` function with full edge handling;
the `student_streak_state` table (monotonic longest); deterministic backend tests for the streak math
and the `studied_section` dedup. **Does NOT (10a):** badges (10b), the gamification API/UI (10c),
leaderboards, freezes/grace, frontend-awarded state, any AI call, or any change to the assistant (8.6)
or analytics (11) domains.

## Approach
Mirror the existing event-spine / read-model / pure-function idioms (EventRecorder, `platform/query`
resolvers, `progress/forecast.py`). Compute everything on read; persist only the monotonic
`longest_streak`. The `studied_section` event is owned by the content domain and deduped via a
deterministic `uuid5` source_id keyed by the configured-tz local day, reusing the existing
`UNIQUE(event_type, source_id)` constraint (no new dedup schema). Day boundaries come from
`COURSE_TIMEZONE` via `ZoneInfo`; the streak fn takes `tz` as a parameter for deterministic tests.

## Changes, file by file
- `backend/app/platform/config.py` — add `COURSE_TIMEZONE` property (default `"UTC"`, `ZoneInfo`-validated → `SettingsError`).
- `backend/pyproject.toml` — add `tzdata` dependency. `.env.example` — add `COURSE_TIMEZONE=UTC` (+ hosted note).
- `backend/app/platform/db/models/student_activity_event.py` — add `"studied_section"` to `STUDENT_ACTIVITY_EVENT_TYPES`.
- `backend/app/platform/events/recorder.py` + `events/__init__.py` — `STUDIED_SECTION = "studied_section"` constant + export.
- `backend/app/domains/content/service.py` — emit `studied_section` in `get_module_section_detail` student branch (after visibility); thread `current_user`. `begin_nested()` + `IntegrityError`/`SQLAlchemyError` handling + commit; `uuid5` dedup; same `now_utc` for occurred_at + local day.
- `backend/app/api/routers/content.py` — pass `current_user` into `get_module_section_detail` on the section-detail GET.
- `backend/alembic/versions/0080_gamification_event_type.py` — drop+recreate `ck_student_activity_events_event_type` with the union (0030 pattern).
- `backend/tests/test_shared_check_union.py` — add `studied_section` to the expected union.
- `backend/app/platform/query/gamification_read.py` — `scheduled_class_days()` + `engagement_days()` (read-only; no domain imports).
- `backend/app/domains/gamification/__init__.py`, `streak.py` — `StreakInputs`/`StreakResult` + pure `derive_streak`.
- `backend/app/platform/db/models/student_streak_state.py` (+ register in `models/__init__.py`) — `student_id` PK, `longest_streak`, `last_seen_gamification_at`, `updated_at`. Table created in migration `0081` (shared with 10b's `student_badges`).
- `backend/tests/test_gamification_streak.py` — pure-fn edge tests. `backend/tests/test_gamification_studied_section.py` — emit + dedup on the content GET.

## Order of operations
1. `COURSE_TIMEZONE` config + `tzdata` + `.env.example`.
2. Event-type vocab (`studied_section`) in model tuple + recorder constant; migration 0080 + union test.
3. `studied_section` emission in the content service/router (savepoint-wrapped, uuid5 dedup).
4. `platform/query/gamification_read.py` primitives.
5. `derive_streak` pure fn + `student_streak_state` model.
6. Backend tests; bring up docker (unique-tag image + clean DB); `alembic upgrade head` (0080 chained off current head 0041 locally) + round-trip; `pytest` green.

## Test strategy
- `derive_streak` (no DB, time as param): reset-after-ended-miss; neutral no-class days; today
  scheduled+unsatisfied → `needs_activity_today` (not broken); future ignored; tz/day-end boundary
  (same UTC instant → different local date under two zones); `occurred_at` vs processing time; longest
  survives a break.
- `studied_section`: a student GET on a published section inserts exactly one event for
  (student, section, today); a same-day re-GET inserts none; a different section adds one; the read
  still returns 200 if emission raises (savepoint swallow).
- `test_shared_check_union` passes with the widened CHECK; migration round-trips on a fresh DB.

## Risks & mitigations
- **`ModuleAccessContext` lacks `user_id`** → thread `current_user` as a local param (avoid editing the
  shared dataclass that Stage 11 also touches).
- **Section GET was commit-free** → emit inside `begin_nested()` so a dedup `IntegrityError` can't
  poison the session; commit only the event.
- **Midnight edge** → one `now_utc` read feeds both `occurred_at` and the dedup local day.
- **Migration collision with Stage 11** (event-type CHECK) → keep `studied_section` in the model tuple;
  the union CI guard + single-head rebase converge it at merge. Local `0080.down_revision='0041'`;
  repoint to main's head at rebase, numbering stays in the 0080+ block (Stage 11 owns 0057–0079).
- **`tzdata` missing in slim image** → added to pyproject so `ZoneInfo` resolves in CI/containers.

## Open questions
- None blocking. D1 flashcard unit confirmed (distinct local days with a completed flashcard session;
  no deck id on the event) — affects 10b catalog, recorded in the spec's Decisions.
