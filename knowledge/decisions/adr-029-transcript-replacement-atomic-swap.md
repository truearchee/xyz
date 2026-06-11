---
type: adr
stage: "4.6"
status: accepted
created: 2026-06-11
updated: 2026-06-11
related-session: knowledge/specs/stage-04/4.6a-lifecycle-supersession-foundation.md
---

# ADR-029 — Transcript replacement = atomic swap on completion (spec ADR-46-A)

> Spec label "ADR-46-A". Remapped to repo slot adr-029 (same convention 4.5 used for ADR-015..018 →
> adr-025..028). Supersedes the one-active-only boundary in [[adr-015-transcript-upload-boundary-active-invariant]].

## Linked documents
- Spec: [[specs/stage-04/4.6a-lifecycle-supersession-foundation]]
- Plan: [[plans/stage-04/4.6a-lifecycle-supersession-foundation]]
- Report: [[steps/stage-04/4.6a-lifecycle-supersession-foundation]]
- Related: [[adr-030-summary-eligibility-domain-resolver-split]], [[architecture/transcript-lifecycle]]

## Context
Before 4.6, a section had exactly one transcript and a second upload was rejected with
`409 TRANSCRIPT_ALREADY_EXISTS` (adr-015). Stage 4.6 must allow a lecturer to *replace* a transcript
without a content gap, a blackout, or a mix of old-text/new-summary — and a broken replacement must
never degrade working content. A naive "delete + re-upload" or "flip active in place" violates all of
those.

## Decision
A replacement transcript processes **alongside** the still-active old one and only becomes visible
once it has **fully completed**.

1. **`lifecycle_state ∈ (active | pending | superseded)`** replaces the boolean `is_active`
   (clean pre-MVP cut; `is_active` removed). Partial-unique indexes enforce **one active** AND **one
   pending** per `module_section_id`.
2. **First-ever upload** (no prior active) → `active` immediately (unchanged student-facing behavior).
   **Replacement** (a prior active exists) → `pending`; the old stays `active`.
3. **Section-scoped lock.** Creation, pending-discard, and activation acquire a `module_sections`
   `SELECT … FOR UPDATE` so ordinary races (double-click, client retry, two co-lecturers) surface as
   ordered state transitions, not constraint-violation 500s. Lock order is **section → transcript**
   in every path to avoid deadlock.
4. **Double replacement** discards the prior pending (`supersession_reason='discarded_pending'`)
   before inserting the new pending — the one-pending index is the backstop.
5. **Activation is the only active-promotion path** — `try_activate_pending_transcript(transcriptId)`,
   under the section lock: verify still `pending` + no newer pending + `overall_state=='summarized'`
   + (via the domain eligibility service, adr-030) exactly one eligible brief AND one eligible
   detailed summary, then swap old active → `superseded` and pending → `active` atomically. It is a
   **no-op** for anything that is not a ready pending, so it is safe to trigger opportunistically from
   the summary-completion path.
6. **Lineage** (audit/debug, no UI): `replacement_of_transcript_id`, `superseded_by_transcript_id`,
   `supersession_reason` (`replaced_active`|`discarded_pending`), `superseded_at`.

## Consequences
- A failed/incomplete replacement stays `pending`+failed and retryable; the old transcript stays
  `active`. Working content can never be degraded by a broken replacement.
- The swap is atomic under the one-active partial-unique index **only if** the old-active demotion is
  flushed before the pending promotion (the unit of work does not preserve assignment order). Same for
  the pending-discard insert. Both are enforced explicitly and covered by tests (real bugs the tests
  caught).
- Superseded transcripts and their raw files are **retained** (source of truth, retry, audit). Their
  storage objects are referenced, not orphaned; indefinite retention of identifiable recordings is a
  product-owner policy decision flagged on the post-MVP watchlist (roadmap §12).
- No student HTTP surface here; the visibility restoration is 4.7. The fencing-guarded destructive
  deletes that retry needs are 4.6b.

## Alternatives rejected
- **Flip active in place / delete-then-reupload** — content gap + data loss + mixed state.
- **Keep the 409** — replacement impossible; the carried stuck-row debt cannot be addressed.
