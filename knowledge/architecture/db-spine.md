---
type: architecture
stage: 02
created: 2026-05-29
updated: 2026-06-01 00:18
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
- Spec: [[specs/stage-04/4.1-transcript-upload]]
- Plan: [[plans/stage-04/4.1-transcript-upload]]
- Report: [[steps/stage-04/4.1-transcript-upload]]
- Architecture: [[architecture/storage]]
- Decision: [[decisions/adr-015-transcript-upload-boundary-active-invariant]]
- Decision: [[decisions/adr-016-transcript-file-validation-storage-metadata]]

## Current structure
The backend now has a SQLAlchemy declarative model package under `backend/app/platform/db/models/`. Alembic imports `app.platform.db.models` to register all model metadata before migrations run.

## Tables
- `app_users` anchors local application users and maps them to Supabase Auth through `auth_provider_id`.
- `course_modules` stores course offering containers owned by app users.
- `course_memberships` connects users to modules and preserves archived enrollment history.
- `module_sections` stores ordered module content instances and keeps scheduling fields separate.
- `section_assets` stores private storage keys and file metadata for uploaded section PDFs. Session 3.1 migrated the Stage 2 placeholder from `file_url` to `storage_key`, added `checksum_sha256`, and records `uploaded_by_user_id` for the current stored object.
- `transcripts` stores raw transcript upload metadata for lecture/lab sections. Session 4.1 adds the table with full lifecycle status values but only writes `status='uploaded'` and `source_type='manual_upload'`.

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

## Transcript schema notes
- `transcripts.module_section_id` points at `module_sections(id)` and has a partial unique index, `uq_active_transcript_per_section`, for `is_active = true`.
- `transcripts.storage_key` is a private object-storage path and is unique.
- `transcripts.uploaded_by_user_id` is nullable and points at `app_users(id)`, matching the P6-confirmed target of `section_assets.uploaded_by_user_id`.
- `transcripts.status` and `transcripts.source_type` use `text + CHECK`, matching the existing status column convention.
- `transcripts.checksum` stores lowercase SHA-256 over raw uploaded bytes; it is not exposed in public `TranscriptMeta`.

## ID strategy
All primary keys are PostgreSQL `UUID` columns with no database-side default. Application models generate UUIDv7 values through `uuid6.uuid7`, keeping IDs time-ordered while avoiding `gen_random_uuid()` defaults.

## Local database extensions
Local Docker Postgres initializes both `vector` and `pgcrypto` from `docker/postgres/init/001-create-vector.sql`. Hosted Postgres will not run this init script, so first deployment must bootstrap required extensions explicitly for the target database.

## Intentional gaps
Role semantics that require cross-row checks remain service-layer responsibilities for later sessions: lecturer-only module ownership and no-admin memberships are not enforced by database constraints in the MVP schema.
