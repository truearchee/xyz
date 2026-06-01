---
type: adr
stage: 04
status: accepted
created: 2026-06-01
updated: 2026-06-01 15:03
related-session: knowledge/specs/stage-04/4.2-transcript-parse-segments.md
---

# ADR-019 - Transcript Parse Strategy

## Linked documents
- Spec: [[specs/stage-04/4.2-transcript-parse-segments]]
- Plan: [[plans/stage-04/4.2-transcript-parse-segments]]
- Report: [[steps/stage-04/4.2-transcript-parse-segments]]
- Architecture: [[architecture/worker]]
- Architecture: [[architecture/storage]]
- Decision: [[decisions/adr-017-ingestion-job-worker-spine]]
- Decision: [[decisions/adr-018-transcript-segment-timestamps]]

## Decision
Route by content sniff before strict decoding. `WEBVTT` content is decoded with strict `utf-8-sig` and parsed with `webvtt-py`; TXT fallback uses `utf-8-sig` with replacement.

Speaker extraction is conservative: VTT voice spans are accepted, Zoom-style leading speaker prefixes are accepted only when they pass the educational-label stoplist and capitalization heuristic, and doubtful cases preserve text with `speaker_name=NULL`.

Parsing does not normalize transcript text. Greeting removal, mic-check cleanup, and other normalization belong to chunk text in a later session.

`processor_version` is stored as metadata on `ingestion_jobs` but is not part of the idempotency key.

## Rationale
VTT needs strict decoding because malformed caption files are not recoverable parse input. TXT is the fallback format and should tolerate isolated bad bytes.

The preferred speaker-extraction failure mode is under-attribution, not text corruption. Segment text is parsed-from-raw and must not be silently mutated.

## Consequences
Parser bug-fix reprocessing before Session 4.6 is manual: clear or fail the relevant completed parse job, then re-enqueue. No coordinated processor-version requeue policy is required for MVP.
