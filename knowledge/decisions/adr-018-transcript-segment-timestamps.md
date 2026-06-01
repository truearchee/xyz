---
type: adr
stage: 04
status: accepted
created: 2026-06-01
updated: 2026-06-01 15:03
related-session: knowledge/specs/stage-04/4.2-transcript-parse-segments.md
---

# ADR-018 - Transcript Segment Timestamp Representation

## Linked documents
- Spec: [[specs/stage-04/4.2-transcript-parse-segments]]
- Plan: [[plans/stage-04/4.2-transcript-parse-segments]]
- Report: [[steps/stage-04/4.2-transcript-parse-segments]]
- Architecture: [[architecture/db-spine]]
- Decision: [[decisions/adr-017-ingestion-job-worker-spine]]
- Decision: [[decisions/adr-019-transcript-parse-strategy]]

## Decision
Store parsed segment timing as integer milliseconds in nullable `start_ms` and `end_ms` columns.

VTT segments have both timestamps; TXT fallback segments have neither. The database enforces paired nullability, non-negative starts, `end_ms > start_ms`, nonblank text, and unique `(transcript_id, sequence_number)`.

`sequence_number` is 0-based, contiguous, and assigned only after empty parser output is filtered.

## Rationale
Integer milliseconds avoid string timestamp ambiguity and floating-point rounding. Paired nullable columns represent the VTT/TXT boundary directly without forcing fake TXT timings.

## Consequences
Later chunking can consume ordered parse output without reparsing timestamp strings. The service owns sequence contiguity because the database cannot enforce gap-free sequences.
