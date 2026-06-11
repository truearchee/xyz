---
type: adr
stage: "4.6"
status: accepted
created: 2026-06-11
updated: 2026-06-11
related-session: knowledge/specs/stage-04/4.6b-retry-fencing-failure-taxonomy.md
---

# ADR-031 — Retry = resume from the earliest failed step over the DAG, fenced (spec ADR-46-B)

> Spec label "ADR-46-B". Remapped to repo slot adr-031 (same convention as adr-029/030). Builds on
> [[adr-029-transcript-replacement-atomic-swap]] (supersession is what fencing guards against).

## Linked documents
- Spec: [[specs/stage-04/4.6b-retry-fencing-failure-taxonomy]]
- Report: [[steps/stage-04/4.6b-retry-fencing-failure-taxonomy]]
- Related: [[architecture/transcript-lifecycle]]

## Context
4.6 is the first stage where the pipeline may be re-run by a human. Retry must be safe (no duplicates, no
data loss, correct under concurrency) and must respect the **true** dependency DAG, not enqueue order:

```
parse ──► chunk ──► embed          (retrieval branch)
parse ──► brief                    (summary branch — uses normalized text, NOT chunks/embeddings)
parse ──► detailed                 (summary branch)
```

Two correctness hazards: (1) a stale worker — its job marked failed by the reaper, or its transcript
superseded by an activated replacement — is still a live OS process and could delete/overwrite rows that
now belong to a newer valid attempt; (2) the 4.5 implementation created summary jobs in the **embed**
success path, so an embed failure blocked summaries — contradicting the DAG.

## Decision
1. **Single retry surface.** `POST /modules/{m}/sections/{s}/transcript/{transcriptId}/retry`
   (section-scoped namespace + transcriptId target so a failed **pending** replacement can be retried, not
   just the active transcript). Resolves the **earliest failed step** over the DAG: parse failed → retry
   parse (its success cascade re-enqueues chunk + brief + detailed); else the earliest failed retrieval
   step (chunk before embed) PLUS each failed summary (independent). Resets those jobs to `queued`,
   enqueues after commit, returns the projection. Targeted `?jobType=` retry is deferred (YAGNI).
2. **Step ownership / delete-and-regenerate.** Each step, on (re-)run, first deletes the rows it owns,
   then regenerates: parse → summaries → chunks → segments (FK order); chunk → chunks; embed → rewrite
   embedding fields in place; summary → success-only artifact (idempotent on provenance).
3. **Summaries fork from parse, not embed** — an embed failure cannot block summaries; a summary retry
   never touches chunks/embeddings. `insert_summary_jobs` moves from the embed success path to the parse
   success path (logic unchanged; call site moved).
4. **Fencing.** Before ANY destructive write, in the same transaction with the rows locked `FOR UPDATE`,
   verify the transcript is not `superseded` and the job is still the running attempt
   (`can_commit_step`); otherwise abort — write/delete/enqueue nothing. Parse gains a one-active index as
   its "current job" pointer; chunk keeps the completed-key dedup (it legitimately coexists two jobs).
5. **Sanitized failure taxonomy.** Every step records an internal `failure_category`; the status
   projection rolls it up to one of 9 sanitized categories (parse_failed, chunk_failed, embedding_failed,
   summary_generation_failed, invalid_output, crashed, provider_error, storage_missing, unsupported_file)
   + a `retryable` flag. The full internal reason stays on `error_message`. A missing raw object is
   `storage_missing` (new `StorageObjectNotFoundError`), distinct from a generic parse failure.

## Consequences
- Retry is idempotent: a double-retry resets once (jobs locked + reset-only-if-failed), and a re-run
  produces no duplicate segments/chunks/summaries.
- A superseded/stale worker aborts cleanly — proven by the fencing tests.
- The lecturer UI (4.6d) drives its retry control off `retryable`/`failureCategory`.
- `crashed` is mapped in the projection now but only produced by the 4.6c reaper. `unsupported_file` has
  no parse-job producer (file type is gated at upload, 422). The RQ scheduler stays disabled (F-4.5-47) —
  the endpoint is the product retry surface.

## Alternatives rejected
- **Linear-chain retry** — would re-run summaries on an embed retry and vice versa; the DAG forks.
- **Endpoint-side delete-and-regenerate** — the worker owns its rows; deletes belong in the fenced worker
  transaction, not the request handler.
- **Keep summaries after embed** — violates "embed failure does not block summaries".
