---
type: adr
stage: "4.7"
status: accepted
created: 2026-06-12
updated: 2026-06-12
related-session: knowledge/specs/stage-04/4.7-student-facing-summaries.md
---

# ADR-036 — Student summary per-slot state precedence (spec ADR-4.7-3)

> Spec label "ADR-4.7-3". Remapped to repo slot adr-036.

## Linked documents
- Spec: [[specs/stage-04/4.7-student-facing-summaries]]
- Report: [[steps/stage-04/4.7a-student-summary-read-policy]]
- Related: [[adr-035-active-transcript-identity-guard-transcriptid-primary]], [[architecture/transcript-lifecycle]]

## Context
"Being generated" is a real, common state (brief lands before detailed). A naive read shows a forever
spinner when the pipeline has actually failed, or shows nothing while it is genuinely working.
`GeneratedLectureSummary` is success-only (no `status` column) — so failure/in-progress must be derived
from the 4.5 `overallState`/`steps` projection, not from a summary-row status.

## Decision
`derive_slot_state(...)` is a PURE function, first-match-wins (spec §6), per slot:
0. non-lecture/lab → `not_applicable`; 1. no active transcript → `unavailable`;
2. a generated row for the active transcript → `ready` (2a checksum tripwire / 2b blank-content → both
   `unavailable` **+ log**); 3. the summary STEP is `failed` → `unavailable`;
4. no row yet → derive from the projection: queued/running → `generating`; step `completed` but no row →
   `unavailable` **+ lecturer-inconsistency flag** (completed-but-missing); upstream terminally failed
   (`overallState == failed`) → `unavailable`; otherwise still progressing → `generating`.

`GENERATING` is shown ONLY when generation is still actually possible — so a terminally-failed pipeline
resolves to `unavailable`, never a forever-spinner. The completed-but-missing anomaly surfaces a
lecturer-side inconsistency (4.6 retry/debug), never to the student.

## Consequences
Deterministic, projection-aware, never order-of-insertion dependent (latest by `generatedAt`). Pinned by
exhaustive unit tests (`test_precedence_*`) covering every branch incl. the corruption/supersession split
(adr-035) and completed-but-missing. Browser-verified: G1 (ready), G2 (brief-first generating), G7
(unavailable).
