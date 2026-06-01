---
type: adr
stage: 04
status: accepted
created: 2026-06-01
updated: 2026-06-01 00:18
related-session: knowledge/specs/stage-04/4.1-transcript-upload.md
---

# ADR-015 - Transcript Upload Boundary and Active Invariant

## Linked documents
- Spec: [[specs/stage-04/4.1-transcript-upload]]
- Plan: [[plans/stage-04/4.1-transcript-upload]]
- Report: [[steps/stage-04/4.1-transcript-upload]]
- Architecture: [[architecture/db-spine]]
- Architecture: [[architecture/storage]]
- Decision: [[decisions/adr-016-transcript-file-validation-storage-metadata]]

## Decision
Transcripts are a separate backend domain that consumes an authorized section context from `platform/query`. The transcript domain does not import the content domain and does not perform direct object-store calls.

Session 4.1 creates the full `transcripts` table needed for the transcript lifecycle, but it only writes `source_type='manual_upload'`, `status='uploaded'`, and `is_active=true`.

One active transcript per section is enforced by the partial unique index `uq_active_transcript_per_section`. The service performs a courtesy duplicate pre-check before reading multipart data, but the partial unique index is the correctness guard for races. Duplicate active uploads return `409`; the lost-race path deletes the uploaded loser object before returning `409`.

`uploaded_by_user_id` is nullable so future `zoom_import` rows do not need fake uploaders. P6 confirmed the existing `section_assets.uploaded_by_user_id` FK target is `app_users(id)`, so transcripts use the same target.

Status and source type use `text + CHECK`, matching the existing `section_assets.processing_status` and `module_sections.publish_status/status` convention.

## Rationale
The raw transcript upload boundary is the foundation for later parsing, chunking, embeddings, and summary generation. Keeping it separate from content assets avoids treating transcripts as downloadable section PDFs and preserves the Stage 4 rule that students never see raw transcript files.

The database invariant must own active-transcript uniqueness because two upload requests can pass a pre-check concurrently. The service still performs the pre-check to avoid streaming large files when a duplicate is already visible.

## Consequences
Supersession, replacement, retry, and checksum deduplication remain deferred to later Stage 4 work. Future sessions can add status transitions and worker polling without changing the 4.1 upload API contract.
