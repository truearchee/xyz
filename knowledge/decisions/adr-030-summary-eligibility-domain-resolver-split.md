---
type: adr
stage: "4.6"
status: accepted
created: 2026-06-11
updated: 2026-06-11
related-session: knowledge/specs/stage-04/4.6a-lifecycle-supersession-foundation.md
---

# ADR-030 — Summary eligibility: domain predicate + read-only resolver (spec ADR-46-E)

> Spec label "ADR-46-E". Remapped to repo slot adr-030. Builds on the read-model boundary in
> [[adr-012-student-content-visibility-read-model]].

## Linked documents
- Spec: [[specs/stage-04/4.6a-lifecycle-supersession-foundation]]
- Report: [[steps/stage-04/4.6a-lifecycle-supersession-foundation]]
- Related: [[adr-029-transcript-replacement-atomic-swap]], [[architecture/transcript-lifecycle]]

## Context
With replacement (adr-029), "which summary may stand for the active transcript?" becomes a real
decision. Checksum alone is insufficient: an identical re-upload (same bytes) yields a matching
checksum against the **wrong** transcript record, so identity must be checked too. This decision is
**business logic** — it must not live in `platform/query`, whose standing rule is read models only.
But the lecturer active-summary preview (4.6d) and the student endpoint (4.7) also need to *read*
eligibility, and they must use the *same* rule the activation write-side uses — not a drifting copy.

A complication: `GeneratedLectureSummary` is a **success-only** table (no `status` column); a row's
existence IS "generated". So the spec's `summary.status == generated` maps to row existence, and
multiple rows per `(transcript, summary_type)` accumulate across prompt versions.

## Decision
1. **The predicate and write-side decisions live in the transcript domain** —
   `backend/app/domains/transcripts/summary_eligibility.py`:
   - `is_summary_eligible(summary, active_transcript)` = `summary.transcript_id == active.id` (identity)
     AND `summary.source_transcript_checksum == active.checksum` (provenance); "generated" = the row
     exists (caller only passes existing rows).
   - `get_activation_ready_summaries(transcript, require_detailed)` — write-side readiness used by
     activation; "exactly one" is satisfied structurally (latest row per type) + predicate-bound + at
     the expected prompt version.
2. **The read projection lives in `platform/query`** — `ActiveTranscriptSummaryResolver` wraps the
   **same** `is_summary_eligible` predicate for reads only and makes **no** activation/authz decision.
3. **`try_activate_pending_transcript` uses the domain service, never the resolver.** The resolver is
   consumed in 4.6 only by the thin lecturer-scoped preview (4.6d); the student-authz wrapper is 4.7.
4. To avoid an import cycle (`summary_service` → `activation` → `summary_eligibility` →
   `summary_service`), the spec constants (`BRIEF`/`DETAILED` + expected prompt versions) were
   extracted to a dependency-free `summary_specs.py` imported by both.

## Consequences
- Single source of truth for eligibility: the write-side gate and every read projection share one
  predicate; a stale-identity or stale-checksum row is reported ineligible rather than silently
  combining v1 identity with v2 content.
- `platform/query` keeps its "read models only / no business decisions" invariant intact.
- The 4.6/4.7 boundary is resolved: resolver now (lecturer preview in 4.6d), student authz wrapper
  later (4.7) — both over the same predicate.

## Alternatives rejected
- **Predicate in `platform/query`** — violates the read-model boundary; the write-side would then
  depend on the read layer for a business rule.
- **Checksum-only eligibility** — a same-bytes re-upload matches the wrong record.
