---
type: adr
stage: "5"
status: accepted
created: 2026-06-16
updated: 2026-06-16
related-session: knowledge/specs/stage-05/5a-quiz-foundation.md
---

# ADR-040 — Activity event spine: same-transaction emit, (eventType, sourceId) idempotency, no consumer

> Stage 5 spec ADR label "(B)". Remapped to repo slot adr-040 (current decisions/ max was 039).

## Linked documents
- Stage spec: [[specs/stage-05/5-shared-quiz-engine-event-spine]]
- Spec: [[specs/stage-05/5a-quiz-foundation]]
- Report: [[steps/stage-05/5a-quiz-foundation]]
- Related: [[adr-041-pagination-envelope]], [[adr-042-quiz-availability-computed-read-only]]

## Context
Stage 5 must record platform activity (quiz completions) such that later stages (gamification, streaks,
badges in Stage 10) can reconstruct state purely from events. Rule 7: gamification CONSUMES events, never
OWNS them — Stage 5 builds the spine, not the consumer. The event must land atomically with the score it
accompanies, must be replay-safe, and must carry an unambiguous UTC instant for tz-aware streak logic.

## Decision
- `StudentActivityEvent` (`student_activity_events`): `id`, `student_id` (FK), `module_id` (FK),
  `event_type`, `source_id` (the action instance = quiz attempt id; deliberately NOT a FK), `occurred_at`
  (`timestamptz`, server-default `now()`), `metadata` (JSONB), `created_at`.
- **Idempotency** via `UNIQUE(event_type, source_id)`. A re-emit raises `IntegrityError` to the caller.
- **`EventRecorder.record(session, ...)`** inserts via `session.flush()` WITHIN the caller's transaction
  and NEVER commits — the domain owns the commit, so the event and its score commit/rollback together.
- **`event_type` CHECK encodes only the Stage-5-emitted values** (`completed_quiz`, `perfect_quiz_score`)
  plus the app-layer `QUIZ_EVENT_TYPES` guard (single source of truth, pinned to the CHECK by a test).
  Widened per consuming slice — the same widen-later pattern 0011 used for `failure_category`. (This is
  the documented D1 deviation from the spec's literal "full Slice 8 set"; flip = list more values in the
  CHECK. Chosen to avoid inventing event names a later Slice-8 spec might rename.)
- **No consumer is built in Stage 5.**

## Consequences
Events are atomic with their domain write, replay-safe, and queryable for badge reproduction. The
widen-later CHECK keeps Stage 5 honest (typo protection) while leaving the spine extensible by a one-line
migration. Verified by `test_event_recorder.py` (same-transaction insert, no-commit, idempotency, and the
`QUIZ_EVENT_TYPES`↔CHECK equality pin) and `test_quiz_schema.py` (idempotency + event_type CHECK).
