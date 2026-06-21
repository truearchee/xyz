---
type: session-spec
stage: 10
session: "10"
slug: gamification
status: approved        # draft → approved → in-progress → done → superseded
created: 2026-06-20
updated: 2026-06-20
owner: developer
plan: "knowledge/plans/stage-10/10a-foundation.md"
report: "knowledge/steps/stage-10/10a-foundation.md"
---

# Stage 10 — Gamification (streaks, badges, progress)

> Developer-authored spec, filed verbatim in substance and reformatted to the session-spec
> template (AGENTS.md rule 1). Three implementation choices were confirmed by the owner as
> **A / A / A** (see **Decisions** below) and recorded as ADRs.

## Linked documents
- Spec: [[specs/stage-10/10-gamification]]
- Plan: [[plans/stage-10/10a-foundation]]
- Report: [[steps/stage-10/10a-foundation]]
- ADR (timezone): [[decisions/adr-056-gamification-course-timezone]]
- ADR (on-read evaluation): [[decisions/adr-057-gamification-on-read-evaluation]]
- Roadmap: [[roadmap]] · Design seed: [[design-plan]] §2.8

## Goal
One unified **Learning streak** plus four families of **badges**, fully derivable from
`StudentActivityEvent` + the Stage 5.5 schedule + Stage 9 snapshots, evaluated **on read**,
idempotent and sticky, **never awarded by the frontend** — filling Stage 9's placeholder
gamification section so a completed quiz on a scheduled day visibly bumps the streak and earns a
badge through the event path, verified in a real browser.

## Why now
Stage 9 shipped the My Progress dashboard with a placeholder gamification section. The event spine
(Stage 5), the module schedule (Stage 5.5), and the topic-mastery snapshots (Stage 9) now all exist
— the substrate gamification consumes. Builds on ADR-052 (single-tenant MVP); no new tenancy work.

## Decisions (CONFIRMED by owner — A / A / A)
- **D1 — Flashcard volume = count distinct, never sum repeats; tightened farm-proofing.** No per-card
  review *event* exists (only `glossary_practice_completed` per session; metadata `{mode, totalCount,
  …}`, no deck id). → Use a **distinct, bounded unit reproducible from the event spine: distinct local
  days with a completed flashcard-mode session** ("Practiced flashcards on N days"). Plus the spec's
  `first_flashcard` milestone (≥1 flashcard session). Honest labels; Effort/volume family.
- **D2 — Course timezone = new platform setting `COURSE_TIMEZONE`** (single IANA, DST-aware via
  `ZoneInfo`, default `UTC`). **Required hosted config** (Stage 4.8 deploy env list carry-forward) or
  real students' days roll over at UTC midnight. → [[decisions/adr-056-gamification-course-timezone]].
- **D3 — Panel styling = Tailwind + shared `ui/` components.** No new inline-style debt, no lint
  exemption. Temporary visual mismatch with Stage 9's inline-styled siblings is absorbed by Stage 12.

---

## Product decisions locked by the founder (encode exactly)
- **ONE primary "Learning streak" — not separate Attendance / Quiz / Glossary streaks.** A streak
  counts consecutive **scheduled class days** on which the student did **any qualifying learning
  activity** (opened a section summary, reviewed a flashcard, completed a quiz, …). Secondary
  per-activity counts may appear as badge progress, never as independent streaks.
- A streak **resets to zero** the moment a scheduled class day is missed. **No freezes, no grace days,
  no make-ups.**
- **Badges** span four families: **Milestones**, **Consistency (streaks)**, **Mastery**, **Effort /
  volume**.
- Day boundaries are computed in a single **configured course timezone** (IANA, DST-aware), never
  naive UTC. Per-student timezone is post-MVP.

## Streak semantics (exact)
- A scheduled class day is **"missed" only after that local calendar day has fully ended** in the
  configured timezone. **Today's scheduled day does NOT break the streak until the next local day
  begins.** At 3 p.m. on a scheduled day with no activity yet → `needs_activity_today`, not `broken`.
- **Multiple scheduled sections on the same local date count as one scheduled day.**
- **No-class days are neutral** — they neither extend nor break a streak.
- **Future scheduled days are ignored.**
- An **engagement day** is derived from `StudentActivityEvent.occurred_at` (when the activity
  happened), **not** processing time.
- `streakStatus` ∈ **`active`** (today satisfied) · **`needs_activity_today`** (today scheduled, not
  yet satisfied) · **`broken`** (a prior scheduled day was missed; show the true current value) ·
  **`no_scheduled_day`** (no class today; streak is safe).

## Governing rules this stage must obey (from the roadmap)
- **Rule 7** — Gamification consumes events; never owns/writes them. The one new event (`studied_section`)
  is owned by the **content domain**.
- **Rule 8** — cross-domain reads go through `platform/query`; gamification and the Stage 11 analytics
  domain must not import each other.
- **"Reproducible from events, never awarded by the frontend."** Re-evaluating the same data never
  double-awards.
- **Rule 11 (real-provider AI smoke): N/A — Stage 10 makes ZERO AI / model calls.**
- **Rule 14** — full active Playwright suite re-runs at stage close.

## How streaks and badges are computed (on read, no extra worker)
Both computed **on read** (the same evaluation may also run right after a qualifying activity). **No
separate gamification queue/worker.**
- **Streak (current + longest): derived on read** from the shared `platform/query` primitives. Walk
  the student's scheduled class days up to "now" in the configured tz; the trailing run of scheduled
  days that are also engagement days is the current streak; the first missed scheduled day (fully
  ended, no engagement) breaks it. `longestStreak` is the maximum run ever — monotonic.
- **Badges: evaluated on read, persisted, sticky, idempotent.** On each read, evaluate only the badges
  the student has **not yet earned**; persist newly qualified; return them. Earned badges are **never
  re-evaluated and never revoked**. Idempotency = unique constraint + not-yet-earned filter.
  - **Streak-milestone badges key off `longestStreak` (max ever), not the current streak.**
  - **No separate product backfill** — first read after deploy awards the historical set. The
    recompute path is a verification/dev tool, not the product award path.

`StudentBadge` schema (nullable-scope fixed — Postgres `NULL` is not "equal" in a unique constraint):
```
StudentBadge: student_id; badge_key; scope_type (global|module|topic|section);
  scope_id (normalized, NEVER NULL — '' / all-zeros for global); earned_at;
  triggering_event_id (nullable); rule_version; qualified_value / qualified_threshold (debug);
  unique(student_id, badge_key, scope_type, scope_id)
```

**Reconcile / recompute (dev + verification tool, NOT a product path).** A deterministic recompute
rebuilds a student's badges from the full event log and verifies it matches stored state (Stage 4.6
reconciliation ethos) — this proves "reproducible from events."

## Read first
- knowledge/specs/stage-10/10-gamification.md (this file)
- knowledge/plans/stage-10/10a-foundation.md
- knowledge/roadmap.md (rules 7, 8, 11, 14; Stage 10 entry)
- backend/app/platform/db/models/student_activity_event.py + platform/events/recorder.py
- backend/app/platform/query/section_week_resolver.py + progress_read.py

## Source paths likely touched
- backend/app/platform/config.py, platform/query/gamification_read.py,
  domains/gamification/*, platform/db/models/{student_badge,student_streak_state}.py,
  api/routers/gamification.py, domains/content/service.py + api/routers/content.py,
  platform/db/models/student_activity_event.py, platform/events/recorder.py + __init__.py,
  alembic/versions/0080_*, 0081_*, scripts/reconcile_gamification.py
- frontend/src/features/gamification/GamificationPanel.tsx,
  features/progress/ProgressDashboard.tsx, lib/api/wrapper.ts (+ regenerated lib/api/*)

## Build
**Shared read primitives in `platform/query` (built here, reused by Stage 11):**
- `scheduled_class_days(studentId, range, tz)` → calendar days with ≥1 scheduled section across the
  student's assigned modules (Stage 5.5 `session_date`).
- `engagement_days(studentId, range, tz)` → calendar days with ≥1 qualifying `StudentActivityEvent`
  (`occurred_at`, configured tz; allowlist). Reads only (rule 8). Streak *rules* live in the domain.

**Content domain — `studied_section` engagement event:**
- Emitted when a student opens a published section's summary, **deduped by (student, section,
  local-calendar-day in the configured tz)** so re-opening that day is one event.
- **Reliability:** the summary read must **never fail** because engagement recording failed, but
  failures must be **logged and retryable** — not silently dropped. Record synchronously on the
  serving path, wrapped so a failure can't break the read. **In the success path the event exists by
  the time the response returns** → E2E asserts it directly, **no production-leakable test flag**.

**Gamification domain (owns its own tables; never imports other domains):** streak derivation +
on-read badge evaluation + `StudentBadge` + recompute tool.

**Badge catalog — code-defined global catalog for MVP** (stable `badge_key`s; UI metadata returned by
the API). **Defer** a `BadgeDefinition` table and lecturer-customized names/icons (post-MVP). Starter
set: *Milestones* (first quiz; first section summary studied; first flashcard reviewed; first glossary
term saved; first scheduled week with activity); *Consistency* (3/7/30-day streak keyed off
`longestStreak`); *Mastery* (topic mastered = Stage 9 `status_label='strong'`; module completed;
perfect quiz at 100%); *Effort/volume* (10 quizzes; flashcard days per D1; N section summaries).

**10a counting-rules table (mandatory deliverable, covers EVERY catalog entry).** Bind each badge to a
real event/snapshot + an exact count rule. **Retake / volume rule:** volume badges count **distinct
source items** so retaking or re-reading cannot farm a badge; a retake still counts as activity for
the streak.

## Do not build
- No separate attendance / quiz / glossary streaks (one Learning streak). No leaderboards, rankings,
  or student-to-student comparison. No freezes / grace / make-ups. No proactive streak-about-to-break
  notifications (needs the Stage 11 scheduler). No frontend-awarded or frontend-stored state. No
  lecturer-customized `BadgeDefinition`s, no per-student timezone UI, no XP / levels / currency. No new
  event types owned by gamification (only the content-domain `studied_section`). **Do not touch the
  assistant (8.6) or analytics (11) domains.**

## Data model changes
- New `student_badges` table (unique(student_id, badge_key, scope_type, scope_id); scope_id non-null).
- New `student_streak_state` table (student_id PK; longest_streak; last_seen_gamification_at).
- `student_activity_events` CHECK widened to add `studied_section` (union with any parallel-stage value).

## API changes
- `GET /student/gamification` (student-only; `Cache-Control: private, no-store`). Read shape:
  `currentStreak, longestStreak, todayIsScheduled, todaySatisfied, nextScheduledDay, streakStatus,
  earnedBadges[], lockedBadges[] (progress current/target), progressItems[], newBadgeIds[], lastSeenAt`.
- `studied_section` is emitted server-side on the EXISTING content section-detail GET — no new event API.

## Worker / job changes
None. On-read computation only (no queue/worker). `backend/scripts/reconcile_gamification.py` is a
dev/verification CLI, not a product path.

## Authz rules
- `GET /student/gamification` is student-role-gated (403 lecturer/admin), token-derived student only,
  no `student_id` param. No endpoint grants a badge, sets a streak, or creates a `StudentActivityEvent`
  arbitrarily; quiz scores are read from server-emitted events, never trusted from the client.

## Verification
- `docker compose exec backend pytest` → new gamification suites + `test_shared_check_union` pass.
- `alembic upgrade head → downgrade base → upgrade head` round-trips; `alembic heads` = 1.
- `python backend/scripts/reconcile_gamification.py …` exits 0 (recompute == stored).
- `docker compose exec frontend npx tsc --noEmit` → exit 0; new frontend files add **zero** new
  `check:inline-styles` / `check:design-tokens` violations.
- `scripts/generate-api-client.sh` → committed client matches the live OpenAPI.
- `tests/e2e/10-gamification.spec.ts` Scenarios A/B/C green; **full active Playwright suite green**
  (rule 14, serial `--workers=1`).

## Browser gate
```
A — earn + extend (the roadmap's core gate):
  Seed: 2-day streak, 9 DISTINCT quizzes completed, today scheduled.
  Complete a (10th, distinct) quiz in-browser → completed_quiz event (same txn as score)
    → My Progress on-read → streak = 3, "3-day streak" + "10 quizzes" badges shown
    → reload awards nothing new (idempotency).
B — reset after a missed scheduled day (dates RELATIVE to today, no time-travel):
  Seed: active through 3 days ago, scheduled days 2-days-ago & yesterday with NO activity, today
  scheduled. Any activity today → current streak shows 1 (reset by the gap), NOT 4.
C — studied_section (the fragile new path):
  Open a published section summary → content records studied_section once per student/section/local-day
    → reopening that day creates NO second event → engagement_days includes that local date.
```
Seed data uses **relative dates computed at run time** and **deterministic seeded records** — never
random failure, never manual DB edits, never a prod-leakable hook (rule 9 + Stage 4.8 discipline).

**Security acceptance criteria (verified by `/cso` + targeted tests, NOT the happy-path gate):** no
frontend-reachable endpoint can create a `StudentActivityEvent` directly, grant a `StudentBadge` or set
current/longest streak, spoof another student's source action, or spoof perfect-score / quiz-score
metadata.

## Sub-sessions
```
10a  Foundation: event inventory + counting-rules table; qualifying-activity allowlist + badge catalog
     + thresholds; content-domain studied_section (unique-per-day, reliable); timezone ADR;
     platform/query primitives; streak derivation (pure fn) + deterministic backend tests.
10b  Badges: code catalog + on-read evaluation + StudentBadge + recompute/reconcile tool + tests
     (no-double-award, sticky, recompute reproduces, longest-streak milestone after a later break).
10c  My Progress UI + browser gate (A, B, C) + security assertions + full active Playwright suite
     (rule 14) + roadmap status update (rule 12).
```

## Known and accepted MVP behaviors
- **Editing the schedule or enrolling a student late can retroactively change a past streak** (streak
  recomputed from current schedule + enrollment on each read). Acceptable for MVP.
- **`StudentActivityEvent`s are never deleted.** Reproducibility depends on this.

## Parallel development with Stage 11
- **Migrations.** Read the current head yourself; expect Stage 11 adding migrations in parallel;
  rebase/renumber before merge; keep **a single Alembic head**. (Block **0080+** per the Stage 10/11
  coordination note — Stage 11 climbs from 0056 and owns 0057–0079; Stage 8.6 took 0042. Migrations are
  `0080` event-type widen + `0081` gamification tables, chained off this tree's head `0041`.)
- **One shared definition of "showing up."** The `platform/query` primitives and `studied_section` are
  the single source of truth — Stage 10 builds them first; Stage 11 reuses them.
- **Both are event consumers only** — read-only on the spine, no cross-domain imports (rule 8).

## Knowledge updates required
- knowledge/steps/stage-10/{10a,10b,10c}-*.md (reports — always)
- knowledge/decisions/adr-056-*, adr-057-* (timezone; on-read evaluation)
- knowledge/roadmap.md status table + STATUS.md + log.md (rule 12)
- knowledge/architecture/* if source-path topology changes
- Stage 4.8 carry-forward: COURSE_TIMEZONE required in hosted env list

## Done means
One Learning streak and badges fully derivable from events + schedule + snapshots, never awarded by the
frontend; on-read evaluation idempotent and sticky; recompute reproduces stored state; browser
Scenarios A/B/C pass against the real backend; security acceptance criteria verified; full active
Playwright suite green (rule 14); knowledge files + roadmap status table updated in the same commit
(rule 12). Zero AI calls → rule 11 N/A.

## Amendments
_Add dated entries here if scope changes mid-flight._
