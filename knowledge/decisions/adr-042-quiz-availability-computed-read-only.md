---
type: adr
stage: "5"
status: accepted
created: 2026-06-16
updated: 2026-06-16
related-session: knowledge/specs/stage-05/5a-quiz-foundation.md
---

# ADR-042 — Quiz availability is computed and read-only; QuizDefinition has no persisted status, no summary pointer

> Stage 5 spec ADR label "(E)". Remapped to repo slot adr-042.

## Linked documents
- Stage spec: [[specs/stage-05/5-shared-quiz-engine-event-spine]]
- Spec: [[specs/stage-05/5a-quiz-foundation]]
- Report: [[steps/stage-05/5a-quiz-foundation]]
- Related: [[adr-039-student-summary-policy-query-split]] (reused visibility + readiness), [[adr-034-student-access-availability-table]], [[adr-040-activity-event-spine]]

## Context
A post-class quiz is "available" iff the section's active transcript has a usable detailed summary. That
readiness drifts (supersession, regeneration). A stored readiness flag on `QuizDefinition` would be a
drift magnet, and a stored summary pointer would break under supersession. Reads must never create rows.

## Decision
- **Availability is a pure read.** `app/platform/query/quiz_availability_read.get_quiz_availability`
  returns `None` when the section is not visible (caller → pinned 404), else
  `QuizAvailabilityView(available, reason_code)`. It reuses the 4.7 scoped visibility query
  (`get_visible_student_section`) and the 4.7 readiness predicate (`derive_slot_state` / READY) on the
  `detailed_study` slot, so quiz availability is NEVER more permissive than summary visibility. It
  creates no rows and never raises HTTP.
- **`QuizDefinition` has NO persisted readiness `status`** (a stored-but-untrusted status is a drift
  magnet; readiness is computed every time) and **NO summary pointer** (the active summary is resolved
  live at Start and snapshotted onto the attempt — supersession-safe). The row is materialized
  get-or-create on `POST start` only (5b), never on a read; `module_id` is derived from the section's
  `course_module_id` by the writer.
- `reasonCode` ∈ { `summary_processing` (GENERATING), `summary_unavailable` (UNAVAILABLE/NOT_APPLICABLE) }
  per the HTTP contract; `available` only when the detailed slot is READY.

## Consequences
No GET-side writes; availability cannot diverge from the proven summary-visibility truth; supersession
never strands a stale pointer. The read model is testable without HTTP and reused by 5b's start endpoint.
Endpoints (and the 403 student gate via `StudentSummaryAccessPolicy.require_student`) land in 5b/5c.
