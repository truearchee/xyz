---
type: architecture
stage: 02
created: 2026-05-29
updated: 2026-06-07 11:31
related-session: knowledge/specs/stage-02/2.1-db-spine.md
---

# DB Spine Architecture

## Linked documents
- Spec: [[specs/stage-02/2.1-db-spine]]
- Plan: [[plans/stage-02/2.1-db-spine]]
- Report: [[steps/stage-02/2.1-db-spine]]
- Spec: [[specs/stage-03/3.1-file-upload]]
- Report: [[steps/stage-03/3.1-file-upload]]
- Spec: [[specs/stage-03/3.2-publish-and-notes]]
- Report: [[steps/stage-03/3.2-publish-and-notes]]
- Spec: [[specs/stage-04/4.3.5d-B1-stage3-module-section-auto-generation-repair]]
- Plan: [[plans/stage-04/4.3.5d-B1-stage3-module-section-auto-generation-repair]]
- Report: [[archive/stage-04/4.3.5d/4.3.5d-B1-section-generation-repair]]
- Spec: [[specs/stage-04/4.1-transcript-upload]]
- Plan: [[plans/stage-04/4.1-transcript-upload]]
- Report: [[steps/stage-04/4.1-transcript-upload]]
- Spec: [[specs/stage-04/4.2-transcript-parse-segments]]
- Plan: [[plans/stage-04/4.2-transcript-parse-segments]]
- Report: [[steps/stage-04/4.2-transcript-parse-segments]]
- Spec: [[specs/stage-04/4.3-transcript-chunking]]
- Plan: [[plans/stage-04/4.3-transcript-chunking]]
- Report: [[steps/stage-04/4.3-transcript-chunking]]
- Architecture: [[architecture/storage]]
- Architecture: [[architecture/worker]]
- Decision: [[decisions/adr-015-transcript-upload-boundary-active-invariant]]
- Decision: [[decisions/adr-016-transcript-file-validation-storage-metadata]]
- Decision: [[decisions/adr-017-ingestion-job-worker-spine]]
- Decision: [[decisions/adr-018-transcript-segment-timestamps]]
- Decision: [[decisions/adr-019-transcript-parse-strategy]]
- Decision: [[decisions/adr-020-transcript-chunk-normalization-versioning]]
- Decision: [[decisions/adr-021-transcript-chunk-transactional-handoff]]

## Current structure
The backend now has a SQLAlchemy declarative model package under `backend/app/platform/db/models/`. Alembic imports `app.platform.db.models` to register all model metadata before migrations run.

## Tables
- `app_users` anchors local application users and maps them to Supabase Auth through `auth_provider_id`.
- `course_modules` stores course offering containers owned by app users.
- `course_memberships` connects users to modules and preserves archived enrollment history.
- `module_sections` stores ordered module content instances and keeps scheduling fields separate.
- `section_assets` stores private storage keys and file metadata for uploaded section PDFs. Session 3.1 migrated the Stage 2 placeholder from `file_url` to `storage_key`, added `checksum_sha256`, and records `uploaded_by_user_id` for the current stored object.
- `transcripts` stores raw transcript upload metadata for lecture/lab sections. Session 4.1 adds the table with full lifecycle status values but only writes `status='uploaded'` and `source_type='manual_upload'`.
- `transcript_segments` stores immutable parsed VTT/TXT output for transcripts. VTT segments use integer millisecond timestamps; TXT fallback segments have null timestamps.
- `transcript_chunks` stores normalized, ordered chunk text derived from immutable segments. Chunks carry segment ids, sequence bounds, millisecond time bounds or null TXT bounds, version strings, token counts, nullable `vector(384)` embedding placeholders, and `updated_at` for future embedding writes.
- `ingestion_jobs` tracks idempotent background ingestion work. Session 4.3 wires `job_type='chunk'` after parse and adds `result_metadata jsonb` for structured worker output counts.

## Section asset schema notes
- `section_assets.storage_key` is a private object-storage path and is unique.
- `section_assets.module_section_id` is indexed for section asset listing, but it is not unique; a section may have multiple PDF assets.
- `section_assets.uploaded_by_user_id` points at `app_users(id)` and is updated on replace.
- `section_assets.processing_status` is technical file state and remains separate from `module_sections.publish_status`, which controls student visibility in later Stage 3 work.
- Section asset list responses are read through `platform/query/content_read.py` projection rows; write behavior remains in the content domain service.

## Section publish and notes behavior
- `module_sections.publish_status` is a service-managed visibility state with values `draft`, `published`, and `unpublished`; `draft` is initial-only.
- `module_sections.lecturer_notes` stores shared plain-text lecturer notes for the section and uses `NULL` as the canonical empty value.
- Session 3.2 implements behavior only; no schema change or `published_at` field was added.

## Module section generation
- Session 4.3.5d-B1 adds a backend/product section-generation path to admin module creation. `POST /admin/modules` now creates the `course_modules` row, owner membership, and four default `module_sections` in the same route transaction.
- The temporary MVP default policy creates `Lecture 1`, `Lecture 2`, `Lab 1`, and `Assignment 1` with `order_index` values 1 through 4.
- Generated sections use existing schema fields only: `publish_status='draft'`, `status='active'`, and `lecturer_notes=NULL`.
- No section-template table, schedule builder, schema migration, or public admin DTO change was added in 4.3.5d-B1.

## Transcript schema notes
- `transcripts.module_section_id` points at `module_sections(id)` and has a partial unique index, `uq_active_transcript_per_section`, for `is_active = true`.
- `transcripts.storage_key` is a private object-storage path and is unique.
- `transcripts.uploaded_by_user_id` is nullable and points at `app_users(id)`, matching the P6-confirmed target of `section_assets.uploaded_by_user_id`.
- `transcripts.status` and `transcripts.source_type` use `text + CHECK`, matching the existing status column convention.
- `transcripts.checksum` stores lowercase SHA-256 over raw uploaded bytes; it is not exposed in public `TranscriptMeta`.
- `ix_transcripts_status_created_at` supports future recovery sweeps over low-cardinality transcript states.
- `transcript_segments.sequence_number` is assigned after empty parse output is filtered and is unique per transcript. The database enforces nonblank text, paired timestamp nullability, non-negative starts, and `end_ms > start_ms`.
- `ingestion_jobs.idempotency_key` is unique. Parse uses `parse:{transcript_id}:{checksum}`; `processor_version` is stored as metadata and is not part of the key.
- `transcript_chunks.chunk_index` is unique per transcript. The unique btree on `(transcript_id, chunk_index)` is the transcript lookup path; no separate `transcript_id` index is present.
- `transcript_chunks.embedding` is nullable until Session 4.4. `embedding_generated_at` records embedding time, while `updated_at` records the row's latest mutation.
- `transcripts.status='completed'` means the Stage 4.1-4.3 transcript pipeline has completed upload, parse, and chunk persistence. Successful chunk jobs set the transcript to `completed` while also completing the `chunk` row in `ingestion_jobs`; there is intentionally no `chunked` transcript status.

## ID strategy
All primary keys are PostgreSQL `UUID` columns with no database-side default. Application models generate UUIDv7 values through `uuid6.uuid7`, keeping IDs time-ordered while avoiding `gen_random_uuid()` defaults.

## Local database extensions
Local Docker Postgres initializes both `vector` and `pgcrypto` from `docker/postgres/init/001-create-vector.sql`. Migration `0006` also runs `CREATE EXTENSION IF NOT EXISTS vector` before creating `transcript_chunks.embedding`. Hosted Postgres still needs required extensions available to the migration role before first deployment.

## Intentional gaps
Role semantics that require cross-row checks remain service-layer responsibilities for later sessions: lecturer-only module ownership and no-admin memberships are not enforced by database constraints in the MVP schema.
