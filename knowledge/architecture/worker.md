---
type: architecture
stage: 04
created: 2026-06-01
updated: 2026-06-01 15:03
related-session: knowledge/specs/stage-04/4.2-transcript-parse-segments.md
---

# Worker Architecture

## Linked documents
- Spec: [[specs/stage-04/4.2-transcript-parse-segments]]
- Plan: [[plans/stage-04/4.2-transcript-parse-segments]]
- Report: [[steps/stage-04/4.2-transcript-parse-segments]]
- Architecture: [[architecture/db-spine]]
- Architecture: [[architecture/storage]]
- Decision: [[decisions/adr-017-ingestion-job-worker-spine]]
- Decision: [[decisions/adr-019-transcript-parse-strategy]]

## Current worker shape
The Docker `worker` service runs `python -m app.workers.worker`, connects to the Stage 1 Redis instance from `REDIS_URL`, and listens on the single `ingestion` RQ queue.

RQ is treated as at-least-once delivery. The queue payload contains only `transcript_id`; workers re-fetch database rows and storage objects inside the handler.

## Enqueue boundary
Transcript upload commits the `transcripts` row first, then enqueues `parse_transcript(transcript_id)`. After enqueue succeeds, the upload service conditionally updates the transcript from `uploaded` to `queued`.

If enqueue fails, the transcript remains `uploaded`. If a worker already advanced the transcript to `parsing`, the conditional update does not downgrade it.

## Parse handler structure
The parse handler uses three phases:

1. Claim a parse `ingestion_jobs` row in a short transaction using `parse:{transcript_id}:{checksum}`.
2. Read the raw object from storage and parse VTT/TXT bytes outside a database transaction.
3. Re-lock the job, verify the claimed attempt token, then persist segments and complete the job.

The claimed-attempt guard applies on both success and failure paths. If a worker no longer owns the running attempt, it aborts without changing `transcript_segments` or `transcripts.status`.

## Intentional gaps
Session 4.2 does not implement retry, backoff, stale-running recovery, replacement, or supersession. A process death after upload commit can leave `uploaded`; a mid-parse crash can leave `parsing` plus `running`. Session 4.6 owns recovery.
