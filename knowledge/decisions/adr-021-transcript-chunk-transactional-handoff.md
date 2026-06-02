---
type: adr
stage: 04
status: accepted
created: 2026-06-01
updated: 2026-06-01 19:58
related-session: knowledge/specs/stage-04/4.3-transcript-chunking.md
---

# ADR-021 - Transcript Chunk Transactional Handoff

## Linked documents
- Spec: [[specs/stage-04/4.3-transcript-chunking]]
- Plan: [[plans/stage-04/4.3-transcript-chunking]]
- Report: [[steps/stage-04/4.3-transcript-chunking]]
- Architecture: [[architecture/worker]]
- Architecture: [[architecture/db-spine]]
- Decision: [[decisions/adr-017-ingestion-job-worker-spine]]
- Decision: [[decisions/adr-020-transcript-chunk-normalization-versioning]]

## Decision
Successful parse creates the queued chunk `ingestion_jobs` row in the same transaction that records parse completion. RQ enqueue happens only after that commit and carries the chunk job id.

Chunk processing locks the chunk job row and the owning transcript row before replacing chunks. Replacement happens in one transaction. Failure status and sanitized error recording happen in a separate cleanup transaction after rollback.

Chunk job idempotency includes the transcript id, stored checksum, completed parse job `processor_version`, normalization version, and chunking version. The parser version is read from the completed parse job that produced the current segments, not from the current parser code constant.

## Rationale
The database is the recovery surface. If enqueue fails after parse commits, Session 4.6 can find the queued chunk job. If replacement fails, rollback preserves any prior committed chunks.

Dual row locks serialize chunk writes per transcript and avoid corrupting the chunk set when two chunk jobs with different version keys are present.

## Consequences
Chunk completion is represented by the completed chunk job and its `result_metadata`, while `transcripts.status='chunking'` means the transcript has reached the chunking stage. There is no `chunked` transcript status.
