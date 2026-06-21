---
type: adr
status: accepted
created: 2026-06-20
updated: 2026-06-20
---

# ADR-057 — Gamification is derived/evaluated on read; studied_section is a read-records-an-event

## Context
Stage 10 must make streaks and badges **reproducible from `StudentActivityEvent` + schedule +
snapshots** and **never awarded by the frontend** (rule 7). It must also make "opening a section
summary" count toward the streak, which requires a new engagement event on a path that today is a pure
read.

## Decision

### 1. On-read derivation/evaluation, no worker
- **Streak (current + longest) is derived on read** from the `platform/query` primitives — there is no
  trusted stored streak counter and no separate gamification queue/worker. `current` is always
  recomputed; only the monotonic **`longest_streak`** is persisted (`student_streak_state`) so a
  milestone reached earlier survives a later break and the max-ever read stays O(1).
- **Badges are evaluated on read, persisted, sticky, idempotent.** Each read evaluates only
  not-yet-earned badges against current events/snapshots/`longest_streak`, persists newly qualified
  ones via `INSERT … ON CONFLICT (student_id, badge_key, scope_type, scope_id) DO NOTHING`, and returns
  them. Earned badges are **never re-evaluated and never revoked**, even if underlying data later
  changes. Idempotency = the unique constraint + the not-yet-earned filter; re-loading awards nothing
  new. Streak-milestone badges key off `longest_streak`, not the current streak.
- A shared **pure `evaluate_badges(metrics)`** function is used by both the on-read service and the
  reconcile tool, so "recompute == stored" is a meaningful equality.
- **`scope_id` is never NULL** (all-zeros sentinel for global scope) because Postgres treats NULLs as
  distinct in a unique constraint, which would silently allow duplicate global badges.

### 2. `studied_section` is a read that records an event (student-facing section read)
- Emitted by the **student-facing summary read** — `student_summaries.get_student_section_detail`
  (`GET /student/sections/{id}`, the endpoint the student section page actually calls) **after** the
  visibility check — via the shared **`platform/events.record_studied_section`** helper. The helper is
  platform infrastructure (it sits beside `EventRecorder`), so a content-serving domain records the
  event WITHOUT a cross-domain import (rule 8); gamification never writes the spine (rule 7), it only
  consumes. **Correction (live gate, 2026-06-20):** the browser gate caught that the emission was
  initially hooked on the content router's `get_module_section_detail`
  (`/student/modules/{id}/sections/{id}`), which the student UI does **not** call — so no event fired
  in the real flow. Moved to the real path above; the content hook was reverted.
- **Per-day dedup without a new constraint:** `source_id = uuid5(NS, f"{student}:{section}:{local_day}")`
  where `local_day = now_utc.astimezone(ZoneInfo(COURSE_TIMEZONE)).date()`. The existing
  `UNIQUE(event_type, source_id)` then collapses same-local-day re-opens (and concurrent double-opens)
  to one row. The **same `now_utc`** is used for both `occurred_at` and `local_day` so a midnight-edge
  request can't store the row under one day but key it under another.
- **Reliability:** the emit runs inside a `begin_nested()` SAVEPOINT — `IntegrityError` (same-day
  re-open) is swallowed as success; any other `SQLAlchemyError` is logged (student/section/day) and
  swallowed so the **read never breaks**, but the failure is visible and retried on the next open (not
  silently dropped). On the success path the row exists before the response returns, so E2E asserts it
  directly with **no production-leakable test flag**.

## Alternatives considered
- **A gamification worker/queue** computing streaks/badges async. Rejected: adds lag, makes the browser
  gate non-deterministic, and the candidate volumes are small (mirrors Stage 8's "exact scan until
  justified"). No ANN/index/caching layer for MVP.
- **A dedicated `studied_section` dedup table or partial-unique index on a tz-derived expression.**
  Rejected: the tz is dynamic (can't sit in an index) and the uuid5 source_id reuses the existing
  idempotency constraint with zero new schema.
- **An HTTP endpoint for recompute/reconcile.** Rejected: keeping reconcile a CLI keeps badge-grant off
  the frontend-reachable surface (security acceptance criterion).

## Discoverability + Stage 11 reconciliation (coordination note)
`studied_section` is registered in the code event vocabulary — `STUDENT_ACTIVITY_EVENT_TYPES`
(`student_activity_event.py`) and the `STUDIED_SECTION` constant (`platform/events/recorder.py`) — and
the CHECK widen is **additive** (migration `0080`, union not replace; the `test_shared_check_union` CI
test is the drift guard). Per the Stage 10/11 coordination note: Stage 11's inactivity-risk logic also
derives "activity" from `StudentActivityEvent`; whether opening a summary should *also* count toward
risk (so a summary-only student isn't "streak-alive" here yet "inactive" there) is a **merge-time /
Stage 11 decision**, not Stage 10's to implement — Stage 10's job is only to make the new event
discoverable, which the registry entry + this ADR do.

## Consequences
- Streaks/badges are always current and deterministic for tests; re-loading is a no-op.
- Editing the schedule or enrolling a student late can retroactively change a *past* streak (recomputed
  each read). Accepted for MVP (spec). Reproducibility depends on `StudentActivityEvent`s never being
  deleted.
- The content section-detail GET now commits (it was commit-free) — the only write is the dedup-guarded
  event; the read DTO is a plain dataclass unaffected by a savepoint rollback.

## Linked documents
- Spec: [[specs/stage-10/10-gamification]]
- Plan: [[plans/stage-10/10a-foundation]]
- Companion ADR: [[decisions/adr-056-gamification-course-timezone]]
- Roadmap: [[roadmap]]
