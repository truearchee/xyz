# Status

_Last updated: 2026-05-29 — Session 2.1 complete_

## Current focus
Session 2.1 (DB spine) complete. The five core database tables, SQLAlchemy models, Alembic migration, and isolated migration tests are in place.

## Done recently
- Session 2.1: DB spine schema with UUIDv7 app-generated primary keys and isolated migration tests — completed 2026-05-29
- Session 1.1: full local dev environment with Docker (backend, frontend, database, Redis, worker) — completed 2026-05-29 16:40

## In progress
- (none)

## Next up
- Session 2.2 (developer to provide spec)

## Known issues / blockers
- Hosted Postgres extension bootstrap is not covered by the local Docker init script; handle `vector` and `pgcrypto` explicitly before first hosted deployment.
