---
type: architecture
stage: 04
created: 2026-06-01
updated: 2026-06-01 19:58
related-session: knowledge/specs/stage-04/4.2-transcript-parse-segments.md
---

# Worker Architecture

## Linked documents
- Spec: [[specs/stage-04/4.2-transcript-parse-segments]]
- Plan: [[plans/stage-04/4.2-transcript-parse-segments]]
- Report: [[steps/stage-04/4.2-transcript-parse-segments]]
- Spec: [[specs/stage-04/4.3-transcript-chunking]]
- Plan: [[plans/stage-04/4.3-transcript-chunking]]
- Report: [[steps/stage-04/4.3-transcript-chunking]]
- Architecture: [[architecture/db-spine]]
- Architecture: [[architecture/storage]]
- Decision: [[decisions/adr-017-ingestion-job-worker-spine]]
- Decision: [[decisions/adr-019-transcript-parse-strategy]]
- Decision: [[decisions/adr-020-transcript-chunk-normalization-versioning]]
- Decision: [[decisions/adr-021-transcript-chunk-transactional-handoff]]

## Current worker shape
The Docker `worker` service runs `python -m app.workers.worker`, connects to the Stage 1 Redis instance from `REDIS_URL`, and listens on the single `ingestion` RQ queue.

RQ is treated as at-least-once delivery. Parse queue payloads contain only `transcript_id`; chunk queue payloads contain only `ingestion_job.id`. Workers re-fetch database rows and storage objects inside the handler.

## Enqueue boundary
Transcript upload commits the `transcripts` row first, then enqueues `parse_transcript(transcript_id)`. After enqueue succeeds, the upload service conditionally updates the transcript from `uploaded` to `queued`.

If enqueue fails, the transcript remains `uploaded`. If a worker already advanced the transcript to `parsing`, the conditional update does not downgrade it.

## Parse handler structure
The parse handler uses three phases:

1. Claim a parse `ingestion_jobs` row in a short transaction using `parse:{transcript_id}:{checksum}`.
2. Read the raw object from storage and parse VTT/TXT bytes outside a database transaction.
3. Re-lock the job, verify the claimed attempt token, then persist segments and complete the job.

The claimed-attempt guard applies on both success and failure paths. If a worker no longer owns the running attempt, it aborts without changing `transcript_segments` or `transcripts.status`.

Successful parse completion now creates a queued `chunk` ingestion job in the same transaction that marks parse complete. After that commit, the handler enqueues the chunk worker by job id. If RQ enqueue fails, the queued DB row remains recoverable for Session 4.6.

## Chunk handler structure
The chunk handler locks the `chunk` `ingestion_jobs` row, marks it running, then locks the owning `transcripts` row before replacing any chunk rows. It verifies that a completed parse job exists and uses the parse job's persisted `processor_version` in the chunk idempotency key.

Chunk replacement is atomic: one transaction deletes old chunks, inserts the fresh chunk set, advances the transcript to `completed`, and completes the job with `result_metadata.chunk_count` and `result_metadata.oversized_segment_count`. If insertion fails, that transaction rolls back and preserves the prior committed chunk set. A separate cleanup transaction then marks the job and transcript failed with a sanitized error.

## Embedding + AI queues (Stage 4.4 / 4.5)
Worker isolation extends by queue: `python -m app.workers.worker <queue>` selects `ingestion`
(default), `embedding`, or `ai`. Each runs as its own Docker service (`worker`, `embedding_worker`,
`ai_worker`) on the shared `test2-backend` image. The `embedding` worker validates the pinned model
snapshot at startup; the `ai` worker validates the PromptRegistry (a malformed/missing prompt is a
boot failure) and the provider config.

Successful **parse** completion creates two queued summary `ingestion_jobs` (`generate_brief_summary`,
`generate_detailed_summary`) and enqueues them onto the `ai` queue after commit, alongside the chunk
job — summaries fork from parse (the normalized text comes from segments), NOT from embed, so an embed
failure cannot block summaries (4.6b / adr-031; was after-embed in 4.5, moved in 4.6b). The summary
handlers call `LLMGateway.complete` (see [[architecture/llm]]); on success they store a
`GeneratedLectureSummary` with full provenance, on failure they set `IngestionJob.failure_category` and
write no artifact — the transcript itself is not failed, so the status projection shows per-step failure.
Every step's destructive write is **fenced** (aborts if the transcript was superseded or the job is no
longer the running attempt). See [[architecture/transcript-lifecycle]] for retry + fencing.

## Recovery status (updated 4.6b)
Replacement/supersession landed in **4.6a**; lecturer-driven **retry** (resume-from-earliest-failed-step
over the DAG, fenced) landed in **4.6b** (adr-031). Still open: a process death after a commit can leave
a job `queued` that was never enqueued to RQ, or `running` after a crash — the **step-aware stuck-row
reaper + storage reconciliation (4.6c)** owns that (it produces the `crashed` failure category). The
after-commit enqueue-failure path still leaves rows `queued` precisely so that reaper can re-drive them.
RQ-scheduler-driven retry stays disabled (F-4.5-47); the retry endpoint is the product retry surface.
