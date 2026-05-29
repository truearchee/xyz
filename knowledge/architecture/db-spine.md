---
type: architecture
stage: 02
created: 2026-05-29
updated: 2026-05-29
related-session: knowledge/specs/stage-02/2.1-db-spine.md
---

# DB Spine Architecture

## Linked documents
- Spec: [[specs/stage-02/2.1-db-spine]]
- Plan: [[plans/stage-02/2.1-db-spine]]
- Report: [[steps/stage-02/2.1-db-spine]]

## Current structure
The backend now has a SQLAlchemy declarative model package under `backend/app/platform/db/models/`. Alembic imports `app.platform.db.models` to register all model metadata before migrations run.

## Tables
- `app_users` anchors local application users and maps them to Supabase Auth through `auth_provider_id`.
- `course_modules` stores course offering containers owned by app users.
- `course_memberships` connects users to modules and preserves archived enrollment history.
- `module_sections` stores ordered module content instances and keeps scheduling fields separate.
- `section_assets` stores file metadata and stable storage references only; object storage integration is still future work.

## ID strategy
All primary keys are PostgreSQL `UUID` columns with no database-side default. Application models generate UUIDv7 values through `uuid6.uuid7`, keeping IDs time-ordered while avoiding `gen_random_uuid()` defaults.

## Local database extensions
Local Docker Postgres initializes both `vector` and `pgcrypto` from `docker/postgres/init/001-create-vector.sql`. Hosted Postgres will not run this init script, so first deployment must bootstrap required extensions explicitly for the target database.

## Intentional gaps
Role semantics that require cross-row checks remain service-layer responsibilities for later sessions: lecturer-only module ownership and no-admin memberships are not enforced by database constraints in the MVP schema.
