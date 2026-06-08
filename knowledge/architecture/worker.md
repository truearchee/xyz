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

## Intentional gaps
Session 4.3 does not implement retry, backoff, stale-running recovery, replacement, or supersession. A process death after parse commit can leave a queued chunk job that has not been enqueued to RQ; Session 4.6 owns recovery.
