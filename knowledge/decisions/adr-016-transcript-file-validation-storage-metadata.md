---
type: adr
stage: 04
status: accepted
created: 2026-06-01
updated: 2026-06-01 00:18
related-session: knowledge/specs/stage-04/4.1-transcript-upload.md
---

# ADR-016 - Transcript File Validation and Storage Metadata

## Linked documents
- Spec: [[specs/stage-04/4.1-transcript-upload]]
- Plan: [[plans/stage-04/4.1-transcript-upload]]
- Report: [[steps/stage-04/4.1-transcript-upload]]
- Architecture: [[architecture/storage]]
- Architecture: [[architecture/db-spine]]
- Decision: [[decisions/adr-015-transcript-upload-boundary-active-invariant]]

## Decision
Session 4.1 accepts only `.vtt` and `.txt` uploads. VTT files must decode as UTF-8 and begin with `WEBVTT` after optional BOM and leading whitespace. TXT files must decode as UTF-8 and be non-empty after trimming.

Client MIME is advisory only. The backend derives `text/vtt` for `.vtt` and `text/plain` for `.txt`, computes SHA-256 over the raw uploaded bytes, and stores those raw bytes unchanged through `StorageProvider.put_object`.

Transcript objects use the existing private bucket configured by `SUPABASE_STORAGE_BUCKET`. Their storage keys follow the Stage 3 module/section convention:

```text
modules/{moduleId}/sections/{sectionId}/transcripts/{transcriptId}/{safeFileName}
```

No optional nonce is added because `transcriptId` already gives object-key uniqueness. The storage key uses a sanitized filename; `original_file_name` is also sanitized for display but remains user-facing metadata. Public `TranscriptMeta` never exposes `storageKey`, `checksum`, `isActive`, or `supersededAt`.

## Rationale
The upload boundary must preserve the raw file so later transcript parsing has an immutable source. MIME sniffing by extension and lightweight content validation are enough for 4.1 because no parser or student-facing rendering exists yet.

Using the existing private bucket keeps Stage 4 aligned with the established storage provider contract while separating transcript keys from section asset keys.

## Consequences
Future bucket-per-content-type separation remains possible, but it would be a deployment/storage decision rather than a 4.1 API change. Future student-facing transcript or summary endpoints must continue to avoid exposing raw transcript storage keys.
