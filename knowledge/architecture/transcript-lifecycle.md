---
type: architecture
updated: 2026-06-11
since: "4.6a"
---

# Transcript lifecycle, supersession & eligibility

Map of the Stage 4.6a foundation. See [[architecture/db-spine]] (tables), [[architecture/worker]]
(pipeline), [[decisions/adr-029-transcript-replacement-atomic-swap]], and
[[decisions/adr-030-summary-eligibility-domain-resolver-split]].

## State model
`transcripts.lifecycle_state ∈ (active | pending | superseded)` — replaces the old boolean
`is_active` (removed in migration `0010`). Orthogonal to `transcripts.status` (the pipeline status:
uploaded→…→completed/failed).

```
one ACTIVE  per module_section_id   — partial-unique uq_active_transcript_per_section  (WHERE lifecycle_state='active')
one PENDING per module_section_id   — partial-unique uq_pending_transcript_per_section (WHERE lifecycle_state='pending')
```

Lineage columns (audit, no UI): `replacement_of_transcript_id`, `superseded_by_transcript_id`,
`supersession_reason` (`replaced_active`|`discarded_pending`), `superseded_at`.

```
first upload (no active)      → active
replacement (active exists)   → pending      (old stays active)
pending completes + eligible  → swap: old active→superseded, pending→active   (atomic, under section lock)
second replacement upload     → prior pending → superseded (discarded_pending), new pending created
```

## Key modules (backend)
- `app/domains/transcripts/service.py` — `_create_transcript_under_section_lock`: section
  `FOR UPDATE` lock → decide active vs pending → discard prior pending (demote NULL-pointer → insert →
  back-fill lineage) → enqueue parse after commit. Read paths filter `lifecycle_state == 'active'`.
- `app/domains/transcripts/activation.py` — `try_activate_pending_transcript`: the ONLY
  active-promotion path. Lock order **section → transcript**. Gate = `overall_state=='summarized'`
  (projection) + `get_activation_ready_summaries(...).is_ready` (domain). Demotion is flushed before
  promotion (one-active index). No-op for anything that is not a ready pending; triggered post-commit
  from the summary-completion path.
- `app/domains/transcripts/summary_eligibility.py` — `is_summary_eligible` (identity + checksum;
  "generated" = row exists) + `get_activation_ready_summaries` (write-side). **Owns the business rule.**
- `app/domains/transcripts/summary_specs.py` — `SummarySpec`/`BRIEF`/`DETAILED` + expected prompt
  versions, extracted to break the `summary_service ⇄ activation` import cycle.
- `app/platform/query/active_transcript_summary_resolver.py` — `ActiveTranscriptSummaryResolver`:
  read-only wrapper over the SAME predicate (lecturer preview in 4.6d; student authz in 4.7). No
  write/authz decision.

## Provenance (4.6 fencing/audit)
Each artifact records the job that produced it (FK → `ingestion_jobs.id`, ON DELETE SET NULL):
- `transcript_segments.created_by_ingestion_job_id` (parse)
- `transcript_chunks.created_by_ingestion_job_id` (chunk) **and**
  `transcript_chunks.embedding_created_by_ingestion_job_id` (embed) — **separate**: embed updates the
  vector in place and must never overwrite the chunk creator.
- `generated_lecture_summaries.created_by_ingestion_job_id` (summary)

## Fault-injection harness (test infra)
`app/platform/faults/pipeline_faults.py`, gated by `PIPELINE_FAULT_INJECTION_ENABLED` (+
`PIPELINE_FAULT_INJECTION=<step>`). No-op when off; refuses outside non-prod. `maybe_fail_step(step)`
is called once at the top of each of the five step bodies; `seed_failed_ingestion_job(...)` pre-creates
a failed record. Distinct from the LLM-transport `LLM_FAULT_INJECTION` (summary jobs only).
`docker-compose.fault.yml` wires the env onto all three workers.

## Retry, fencing & the DAG (4.6b — adr-031)
- **Retry endpoint:** `POST /modules/{m}/sections/{s}/transcript/{transcriptId}/retry` (lecturer-only,
  assigned; superseded → 409; nothing failed → 409). `app/domains/transcripts/retry.py`:
  `resolve_retry_scope` (earliest failed step over the DAG: parse failed → just parse; else earliest of
  chunk/embed + independent failed summaries), `apply_retry` (reset failed jobs → queued, enqueue after
  commit). Service: `service.retry_transcript_processing`.
- **DAG decouple:** summary jobs fork from **parse** (`parse._persist_success` calls `insert_summary_jobs`
  + enqueues brief/detailed), NOT embed — an embed failure no longer blocks summaries; a summary retry
  never touches chunks/embeddings.
- **Per-step delete-and-regenerate:** parse deletes summaries → chunks → segments (FK order) then
  regenerates; chunk deletes chunks; embed rewrites embedding fields in place; summary is success-only.
- **Fencing** (`app/domains/transcripts/fencing.py` `can_commit_step`): before any destructive write,
  the worker re-reads job + transcript FOR UPDATE and aborts if `superseded` or the job is no longer
  running. Wired into parse/chunk/embed (incl. each embed batch)/summary persist paths. Parse gained a
  one-active index (its current-job pointer); chunk keeps the completed-key dedup (coexistence).
- **Failure taxonomy:** each step sets a sanitized `IngestionJob.failure_category`; the projection
  surfaces `failureCategory` (one of 9) + `retryable`. Missing raw file → `storage_missing`
  (`StorageObjectNotFoundError`).

## Boundaries / deferred
- one-active "current job" indexes: **embed/summary (0007/0008) + parse (0011)**. **chunk** stays
  WITHOUT one (a one-active-chunk index breaks the tested two-chunk-jobs-coexist replacement path).
- `crashed` failure category is mapped in the projection but only **produced** by the 4.6c reaper.
- Reaper/reconciliation/`MaintenanceRun`/heartbeat → 4.6c. Lecturer UI + preview endpoint + browser gate
  → 4.6d. Student surface → 4.7. Targeted `?jobType=` retry + RQ scheduler (F-4.5-47) → not 4.6.
