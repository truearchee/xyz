---
type: adr
stage: "4.7"
status: accepted
created: 2026-06-12
updated: 2026-06-12
related-session: knowledge/specs/stage-04/4.7-student-facing-summaries.md
---

# ADR-039 — StudentSummaryAccessPolicy owns policy; platform/query returns only visible rows (spec ADR-4.7-6)

> Spec label "ADR-4.7-6". Remapped to repo slot adr-039.

## Linked documents
- Spec: [[specs/stage-04/4.7-student-facing-summaries]]
- Report: [[steps/stage-04/4.7a-student-summary-read-policy]]
- Related: [[adr-030-summary-eligibility-domain-resolver-split]] (the same domain-owns-policy / query-reads-only split), [[adr-034-student-access-availability-table]]

## Context
The student read is inherently cross-domain (membership + publish + transcript summary). Architecture rule
8 keeps `platform/query` read-only and forbids domains importing each other; the security decision must
live somewhere explicit, not be smeared into a query's WHERE clause.

## Decision
- **`domains/student_summaries`** owns the security/business decision: `StudentSummaryAccessPolicy` (§5
  gates — role gate to 403 BEFORE lookup; missing visible section → pinned 404) and the pure §6
  `precedence`. It does not query.
- **`platform/query/student_summary_read`** owns the SCOPED reads: the §8.6 single query returns one row
  iff the section is published+active in a module the student actively belongs to (module-level join),
  else zero rows — NEVER fetch-then-branch into 403/404. It enforces the policy via its WHERE clause; it
  does not own, invent, or mutate policy.
- The §4 identity guard reuses the transcripts-domain `is_summary_eligible` predicate (single source of
  truth, adr-030/035).

## Consequences
The boundary is auditable in one place (the policy + precedence), the read layer cannot leak by branching,
and the existing eligibility predicate stays the single arbiter of "bound to the active transcript".
Verified by the policy/precedence unit tests + the integration rows in `test_student_summaries.py`.
