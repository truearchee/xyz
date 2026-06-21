---
type: adr
status: accepted
created: 2026-06-20
updated: 2026-06-20
---

# ADR-056 — Gamification day boundaries use a single configured course timezone

## Context
Stage 10 streaks count consecutive **scheduled class days** on which a student did any learning
activity. "A day" must be a real calendar day in a DST-aware timezone, never naive UTC — at 11:58 p.m.
local an activity counts for that local day, and a scheduled day is "missed" only after that local day
fully ends. The streak is **one unified streak across all of a student's assigned modules**.

The codebase has no single course-timezone configuration. `CourseModule.timezone` and `AppUser.timezone`
exist (both `Text`, default `'UTC'`), and a student can be enrolled in multiple modules. No `ZoneInfo`
usage exists anywhere in the backend yet. Per-student timezone is explicitly post-MVP (spec).

## Decision
Introduce a single **platform-level setting `COURSE_TIMEZONE`** (one IANA string, default `"UTC"`) in
`backend/app/platform/config.py`, validated at read time by constructing `zoneinfo.ZoneInfo` (a bad
zone raises `SettingsError`, matching the existing fail-loud config pattern). All gamification
day-boundary math — streak derivation and the `studied_section` per-day dedup — resolves day from a
tz-aware `occurred_at` via `occurred_at.astimezone(ZoneInfo(COURSE_TIMEZONE)).date()`.

The streak pure function takes `tz: ZoneInfo` as an explicit **parameter** (it never reads global
config), so unit tests pass arbitrary zones for DST/day-end boundary coverage.

`tzdata` is added to `backend/pyproject.toml` so `ZoneInfo` resolves in slim containers/CI.

## Alternatives considered
- **Per-module `CourseModule.timezone`.** Rejected: a unified cross-module streak has no unambiguous
  zone when two of a student's modules disagree. A single configured zone is the only thing that makes
  "one streak" well-defined for MVP.
- **A new `course_config` table.** Rejected as overkill for one global string pre-MVP, and it adds an
  authorization surface ("who edits it"). An env-var + validation is the minimum that satisfies "single
  configured course timezone, DST-aware."

## Consequences
- **Required hosted config (carry-forward to Stage 4.8):** the UTC default is fine for dev and the
  browser gate, but a hosted deploy MUST set `COURSE_TIMEZONE` to the institution's real zone in the
  Stage 4.8 deploy env list — otherwise real students' "days" roll over at UTC midnight. Recorded in
  `.env.example` and as a Stage 4.8 carry-forward (roadmap / open-questions).
- If a future product needs different day-boundaries per cohort/module, the unified-streak concept
  itself must be revisited; per-student timezone is the post-MVP escape hatch.
- Schedule `session_date` is already a calendar DATE (the local class date) and needs no conversion;
  only event `occurred_at` (a timestamptz) is converted to a local date.

## Linked documents
- Spec: [[specs/stage-10/10-gamification]]
- Plan: [[plans/stage-10/10a-foundation]]
- Companion ADR: [[decisions/adr-057-gamification-on-read-evaluation]]
- Roadmap: [[roadmap]]
