---
type: architecture
stage: 02
created: 2026-05-29
updated: 2026-05-30 23:42
related-session: knowledge/specs/stage-02/2.1-db-spine.md
---

# DB Spine Architecture

## Linked documents
- Spec: [[specs/stage-02/2.1-db-spine]]
- Plan: [[plans/stage-02/2.1-db-spine]]
- Report: [[steps/stage-02/2.1-db-spine]]
- Spec: [[specs/stage-03/3.1-file-upload]]
- Report: [[steps/stage-03/3.1-file-upload]]
- Architecture: [[architecture/storage]]

## Current structure
The backend now has a SQLAlchemy declarative model package under `backend/app/platform/db/models/`. Alembic imports `app.platform.db.models` to register all model metadata before migrations run.

## Tables
- `app_users` anchors local application users and maps them to Supabase Auth through `auth_provider_id`.
- `course_modules` stores course offering containers owned by app users.
- `course_memberships` connects users to modules and preserves archived enrollment history.
- `module_sections` stores ordered module content instances and keeps scheduling fields separate.
- `section_assets` stores private storage keys and file metadata for uploaded section PDFs. Session 3.1 migrated the Stage 2 placeholder from `file_url` to `storage_key`, added `checksum_sha256`, and records `uploaded_by_user_id` for the current stored object.

## Section asset schema notes
- `section_assets.storage_key` is a private object-storage path and is unique.
- `section_assets.module_section_id` is indexed for section asset listing, but it is not unique; a section may have multiple PDF assets.
- `section_assets.uploaded_by_user_id` points at `app_users(id)` and is updated on replace.
- `section_assets.processing_status` is technical file state and remains separate from `module_sections.publish_status`, which controls student visibility in later Stage 3 work.
- Section asset list responses are read through `platform/query/content_read.py` projection rows; write behavior remains in the content domain service.

## ID strategy
All primary keys are PostgreSQL `UUID` columns with no database-side default. Application models generate UUIDv7 values through `uuid6.uuid7`, keeping IDs time-ordered while avoiding `gen_random_uuid()` defaults.

## Local database extensions
Local Docker Postgres initializes both `vector` and `pgcrypto` from `docker/postgres/init/001-create-vector.sql`. Hosted Postgres will not run this init script, so first deployment must bootstrap required extensions explicitly for the target database.

## Intentional gaps
Role semantics that require cross-row checks remain service-layer responsibilities for later sessions: lecturer-only module ownership and no-admin memberships are not enforced by database constraints in the MVP schema.
