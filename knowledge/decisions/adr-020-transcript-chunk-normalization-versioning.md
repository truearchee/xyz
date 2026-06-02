---
type: adr
stage: 04
status: accepted
created: 2026-06-01
updated: 2026-06-01 19:58
related-session: knowledge/specs/stage-04/4.3-transcript-chunking.md
---

# ADR-020 - Transcript Chunk Normalization and Versioning

## Linked documents
- Spec: [[specs/stage-04/4.3-transcript-chunking]]
- Plan: [[plans/stage-04/4.3-transcript-chunking]]
- Report: [[steps/stage-04/4.3-transcript-chunking]]
- Architecture: [[architecture/db-spine]]
- Architecture: [[architecture/worker]]
- Decision: [[decisions/adr-018-transcript-segment-timestamps]]
- Decision: [[decisions/adr-019-transcript-parse-strategy]]

## Decision
Chunk text uses deterministic structural normalization only. Session 4.3 collapses whitespace, removes residual VTT structural artifacts, skips empty normalized segments, and drops adjacent duplicate normalized segments.

Normalization and chunking are versioned independently with code constants: `NORMALIZATION_VERSION="norm-v1-structural"` and `CHUNKING_VERSION="chunk-v1-no-overlap-180w"`. Token counts use `TOKEN_COUNT_METHOD="heuristic_word_count_v1"`.

Chunking is non-overlapping and never splits a segment. Segments above the target but below the hard cap become normal singleton chunks; segments at or above the hard cap become oversized singleton chunks.

## Rationale
Parsed `transcript_segments` are immutable source records. Cleanup for embedding and summarization belongs to the chunk layer, where versioned re-chunking can be tracked without mutating parse output.

Semantic or AI-based filtering is deferred because it can remove instructional content and would require a separate product decision.

## Consequences
Future changes to structural cleanup or token policy require version bumps. Re-chunking can be driven from the job idempotency key without pretending old segments were produced by a newer parser or normalizer.
