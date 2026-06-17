# ADR-040 — Schedule-driven section generation (Stage 5.5a)

- **Status:** Accepted (2026-06-16)
- **Stage:** 5.5a
- **Related:** [[specs/stage-05/5.5-module-schedule-section-metadata]] (D1, D2, D9, D10, D14),
  [[steps/stage-05/5.5a-schedule-generation]]

## Context
Module creation emitted a fixed 4-section template (`Lecture 1/2`, `Lab 1`, `Assignment 1`) with no
`week_number`/`session_date`. Stage 6 quiz scope resolves entirely through `week_number`, so the
template had to be replaced with schedule-driven generation. The `module_sections` metadata columns
already existed (migration 0002); `course_modules` had `starts_on`/`ends_on` but no
weekday-pattern/quiz-day config.

## Decision
1. **Generation is weekday × date-range driven (D1).** Input = course start/end + a
   `sessionPattern` of `{weekday, sectionType}` (lecture|lab only) + optional `quizDay`. Output count
   (e.g. "28 sections") is emergent, never an input. The quiz day is recorded but generates nothing.
2. **Pure generator in the domain (D8).** `generate_sections(...)` is a pure, unit-testable function;
   an adapter builds `ModuleSection` rows. Week math: `anchor` = most recent `weekStartDay` on-or-before
   start; `week_number = (D - anchor).days // 7 + 1`; order = global ascending by
   `(session_date, lecture<lab)`; default title `"{Type} — Week {n} ({Abbr} DD Mon)"`. Weekdays are
   lowercase day-names (avoids integer off-by-one).
3. **Synchronous + atomic (D14).** Generation runs inside the module-creation transaction — no worker,
   no partial "module with zero sections," no double-generation.
4. **No silent fallback.** A creation request without a `schedule` returns **422**; the fixed-template
   path is removed entirely.
5. **Schedule config is creation-time provenance (D10), stored NULLABLE.** `week_start_day` (text),
   `session_pattern` (jsonb), `quiz_day` (text) on `course_modules` are nullable. NULL means "no
   schedule configured"; the 422 + validation live in the **service/schema layer**, not a DB NOT NULL
   constraint — so ORM-direct test/fixture inserts that bypass the API keep working (minimal call-site
   blast radius). Course dates reuse the existing `starts_on`/`ends_on` columns.

## Consequences
- Stage 6 `coveredWeeks` scope resolution is unblocked (`week_number` now populated).
- Every API-path module-creation call site must supply a schedule (suite-breaking) — handled in 5.5a
  for backend tests + E2E payloads; E2E section-selection rework + reseed are 5.5d/5.5e.
- Migration 0021 (`down_revision='0020'`) adds the three columns idempotently after the Stage 5 main
  chain. Session 5.5g rebased the original development seam so `alembic heads` stays singular.

## Alternatives rejected
- **NOT NULL schedule columns** — would force every ORM-direct fixture/factory to supply a schedule, a
  large cross-branch blast radius for no benefit (validation belongs in the service).
- **Async generation via a worker** — needless for ~28 trivial rows; introduces partial-module and
  double-generation failure modes that D14 avoids.
- **Keep the fixed template behind an optional branch** — a silent fallback that would let
  un-scheduled modules exist; rejected in favour of a hard 422.
