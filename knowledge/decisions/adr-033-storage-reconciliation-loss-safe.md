---
type: adr
stage: "4.6"
status: accepted
created: 2026-06-11
updated: 2026-06-11
related-session: knowledge/specs/stage-04/4.6c-recovery-reaper-reconciliation.md
---

# ADR-033 — Storage reconciliation: loss-safe by construction (spec ADR-46-D)

> Spec label "ADR-46-D". Remapped to repo slot adr-033. Completes the 4.6 ADR set (A–E → adr-029..033).

## Linked documents
- Spec: [[specs/stage-04/4.6c-recovery-reaper-reconciliation]]
- Report: [[steps/stage-04/4.6c-recovery-reaper-reconciliation]]
- Related: [[adr-029-transcript-replacement-atomic-swap]] (supersession retains files), [[architecture/transcript-lifecycle]]

## Context
Replacement multiplies the ways a raw object can be orphaned (a failed cleanup after an
IntegrityError/replacement leaves an object with no DB row). Conversely a DB row can lose its object. A
reconciliation job must find both — but storage deletion is irreversible and an in-flight upload looks
identical to an orphan, so the job must be loss-safe by construction, not by careful operation.

## Decision
`run_storage_reconciliation(...)` — singleton-locked (its own advisory lock), MaintenanceRun-logged:
1. **REPORT-ONLY by default.** Cleanup is a separate, explicitly-enabled action: it deletes only when
   `mode='cleanup'` AND `RECONCILIATION_CLEANUP_ENABLED`, capped at `RECONCILIATION_DELETION_CAP_PER_RUN`,
   logging + recording every deletion.
2. **Orphan = object with no transcript row referencing it AND older than the grace window** (default 24h).
   A younger object is indistinguishable from an in-flight upload, so it is never an orphan.
3. **Scope = the transcript-managed prefix only** (`…/transcripts/…`, excluding `…/assets/…` and unknown
   prefixes). A new `list_objects` recurses the bucket (Supabase `.list()` is non-recursive), capped at
   `RECONCILIATION_MAX_OBJECTS`.
4. **Superseded transcripts are RETAINED** (4.6a keeps the row) → their `storage_key` is in the DB set →
   referenced, never an orphan.
5. **Missing case (DB ref, no object) = potential data loss → reported loudly, NEVER auto-fixed.** Missing
   detection is computed only when the listing is COMPLETE (cap not hit) and the scope is the full managed
   prefix — a partial/narrowed listing would raise false alarms (`summary_json.capped=True` records this).

## Consequences
- The default mode cannot delete anything; turning on cleanup is a deliberate, double-gated, capped action.
- A data-loss condition is surfaced (logged + in `MaintenanceRun.summary_json.missing_ref_keys`) but never
  acted on automatically — a human decides.
- Stage 12 verifies reconciliation from `MaintenanceRun` rows, not log-scraping.
- Superseded-transcript files accumulate by design (retained); the retention/hard-delete policy stays on the
  post-MVP watchlist (roadmap §12).

## Alternatives rejected
- **Auto-delete orphans by default** — irreversible; an in-flight upload would be destroyed.
- **Auto-restore/auto-fix missing refs** — there is nothing to restore; data loss must be reported, not hidden.
- **Per-transcript existence checks instead of a listing** — reliable for the missing case but cannot find
  orphans (object-with-no-row); the capped recursive listing covers both.
