---
type: adr
stage: "4.7"
status: accepted
created: 2026-06-12
updated: 2026-06-12
related-session: knowledge/specs/stage-04/4.7-student-facing-summaries.md
---

# ADR-034 — Student access × availability table (spec ADR-4.7-1)

> Spec label "ADR-4.7-1". Remapped to repo slot adr-034.

## Linked documents
- Spec: [[specs/stage-04/4.7-student-facing-summaries]]
- Report: [[steps/stage-04/4.7a-student-summary-read-policy]]
- Related: [[adr-035-active-transcript-identity-guard-transcriptid-primary]], [[adr-036-student-summary-state-precedence]], [[adr-039-student-summary-policy-query-split]]

## Context
The student summary surface is the first point where Stage 3 visibility, the 4.5 brief-before-detailed
split, and 4.6 supersession are enforced together on a student read. The status/availability semantics
must be decided once, not improvised per endpoint, or it ships an existence leak or a stale-content bug.

## Decision
The §5 access × availability table is the contract (`StudentSummaryAccessPolicy` + precedence):
- **200** for rows 1–6 and T — including "visible but not ready/failed" (rows 4/5 → `unavailable`) and
  assignment/supplementary (row T → both slots `not_applicable`, NOT 404). Availability ≠ denial.
- **404, ONE pinned byte-identical body** for rows D (unpublished), P (other module), I (inactive
  membership). Unpublished/not-member/inactive are indistinguishable (asserted on the body, S2).
- **403** for row R (a non-student on the student surface) — the role gate fires BEFORE any resource
  lookup, so it leaks nothing. Supersedes v0.2's uniform-404; there is no "preview as student" (D3).
- **401** for row A (unauthenticated) — handled by the auth dependency.
- Student failure vocabulary is binary: `generating` vs `unavailable`. The lecturer-only taxonomy
  (failed/rate_limited/invalid_output) never reaches a student.

## Consequences
A wrong-surface caller cannot probe resource existence; visibility states are honest without leaking
denial vs absence. Verified by `test_student_summaries.py` (every row incl. byte-identical D/P/I) + the
4.7 browser gate (G4/G5/G6).
