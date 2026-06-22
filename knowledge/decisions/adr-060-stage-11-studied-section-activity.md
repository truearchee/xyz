# ADR-060 — `studied_section` counts as qualifying activity for the `inactive_recently` risk reason

Date: 2026-06-22

## Status
Accepted (owner decision at the three-branch landing — rule 13 "resolved by owner decision").

## Context
Stage 11.1's deterministic risk engine includes an `inactive_recently` reason: a student with upcoming
work but no recorded activity for a configured number of days is surfaced as `watch` / `needs_support`.
"Activity" is read off the shared `StudentActivityEvent` spine.

When Stage 11 was built (branch base at Alembic `0041`), the only activity event types were the quiz
events (`completed_quiz`, `perfect_quiz_score`) and the glossary events (`glossary_term_saved`,
`glossary_practice_completed`), and `latest_activity_at` read **every** event with no `event_type`
filter. In parallel, Stage 10 (gamification) widened the shared `ck_student_activity_events_event_type`
CHECK via migration `0080` to add **`studied_section`** — the CONTENT-domain "opened a section summary"
engagement signal — which is now on `main`. At the three-branch landing (Stage 10 and Stage 8.6 already
merged), Stage 11 reconciles against it.

Reading every event implicitly counted `studied_section`, but the set was a magic implicit "all", not an
explicit, reviewable, reproducible policy. Two things needed deciding: (1) does opening a section summary
count as activity that should reset the inactivity clock, and (2) how is the qualifying set expressed.

## Decision
1. **`studied_section` COUNTS AS qualifying activity** in the `inactive_recently` computation. Opening a
   section summary is genuine engagement with the course; a student doing so should not be nudged as
   inactive.
2. **The qualifying set is explicit and config-backed**, not an implicit "all events" or an inline list:
   `settings.RISK_ACTIVITY_EVENT_TYPES` (default
   `completed_quiz, perfect_quiz_score, glossary_term_saved, glossary_practice_completed, studied_section`,
   comma-separated env override) is threaded through `RiskConfig.activity_event_types` and consumed by
   `analytics_read.latest_activity_at(..., event_types=...)`. This is the same pattern as the numeric risk
   thresholds, and because the set is part of `RiskConfig` it is captured in the risk `input_hash` — a
   change is an `algorithmVersion`-level change, not a silent code edit. Making the set explicit also
   closes the latent risk that a future, non-engagement event type added to the spine would silently
   reset the inactivity clock.
3. **Isolation holds (rule 8).** This reads a content-owned event off the shared `StudentActivityEvent`
   spine by `event_type` string only. The risk/analytics path imports nothing from the Stage 10
   gamification domain (no gamification tables, no `gamification_read`, no badge/streak logic). Confirmed
   by grep: no `gamification` import in `app/domains/analytics/**`, `analytics_read.py`, or
   `app/platform/scheduler/**`.
4. **`algorithmVersion` is amended in place (`risk-v1`), not bumped.** `risk-v1` was never released —
   nothing was on `main` before this landing, so there is no persisted `risk-v1` snapshot data to
   preserve. Adding `activity_event_types` to `RiskConfig` changes the `input_hash` of newly computed
   snapshots, which is acceptable because there is no prior data to reconcile against. (Per the landing
   brief: bump only if persisted `risk-v1` data must be preserved — none exists; rule 10 flag not
   triggered.)

## Consequences
- A student whose only recent activity is `studied_section` is NOT flagged inactive; a student with no
  *recent* qualifying activity IS flagged once past the threshold. Both are covered by
  `backend/tests/test_analytics_inactivity_activity.py`, which also asserts the filter is honored (drop
  `studied_section` from the set → the event is excluded).
- The risk DISPLAY remains live-on-read (Stage 11.1), so a student who studies a section sees the
  inactivity nudge clear immediately, not only at the next scheduled `AgentRun`.
- Section-visibility leak (rule 10): `studied_section` is an event-derived count, which the shared
  visibility gate (`section_visibility.py`, Stage 10.x) deliberately leaves ungated by design — those
  events record only activity the student already performed behind the published gate. So counting
  `studied_section` introduces no unpublished-content leak.

## Alternatives considered
- *Keep the implicit "read all events" behavior.* Rejected: not explicit, not reproducible (not in the
  `input_hash`), and would silently count any future event type regardless of whether it is engagement.
- *Bump to `risk-v2`.* Unnecessary — `risk-v1` was never released, so amend in place and document here.
