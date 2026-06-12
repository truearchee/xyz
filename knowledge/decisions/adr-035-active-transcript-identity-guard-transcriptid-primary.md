---
type: adr
stage: "4.7"
status: accepted
created: 2026-06-12
updated: 2026-06-12
related-session: knowledge/specs/stage-04/4.7-student-facing-summaries.md
---

# ADR-035 — Active-transcript identity guard: transcriptId primary, checksum tripwire (spec ADR-4.7-2)

> Spec label "ADR-4.7-2". Remapped to repo slot adr-035. **Reverses the v0.2 "checksum authoritative"
> decision.**

## Linked documents
- Spec: [[specs/stage-04/4.7-student-facing-summaries]]
- Report: [[steps/stage-04/4.7a-student-summary-read-policy]]
- Related: [[adr-030-summary-eligibility-domain-resolver-split]] (the reused predicate), [[adr-029-transcript-replacement-atomic-swap]] (what "active" means), [[adr-036-student-summary-state-precedence]]

## Context
A summary must reach a student only if it belongs to the section's currently ACTIVE transcript (4.6's
"never mix old and new"). Checksum-alone mishandles the identical-file re-upload collision (same checksum,
different record). Transcripts are immutable, so a `transcriptId` has a fixed checksum.

## Decision
Content is eligible iff `summary.transcriptId == active.id` (PRIMARY selector) AND
`summary.sourceTranscriptChecksum == active.checksum` (TRIPWIRE) — reusing the existing
`is_summary_eligible` predicate (adr-030, single source of truth). Because id-match already implies
checksum-match, an id-match-with-checksum-mismatch can only be corruption → the projection **fails safe
to `unavailable` and logs**. Defense-in-depth: >1 active transcript for a section → fail-safe fallback +
log (never guess); multiple generated rows → latest by `generatedAt`.

## Consequences
- The "but it passed the checksum" bug class and the re-upload collision are closed.
- **Corruption (id-match + checksum-mismatch) is kept DISTINCT from supersession (no row for the active
  transcript → GENERATING).** `is_summary_eligible` returns False for both, so the precedence inspects
  identity and checksum separately and never collapses onto `is_summary_eligible == False` — pinned by two
  dedicated unit tests (`test_precedence_corruption_*` / `test_precedence_supersession_*`).
