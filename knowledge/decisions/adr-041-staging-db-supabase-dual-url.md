---
type: adr
stage: "4.8"
status: accepted
created: 2026-06-12
updated: 2026-06-12
related-session: knowledge/specs/stage-04/4.8-first-hosted-deploy-staging.md
---

# ADR-041 — Staging app DB = dedicated Supabase project, addressed via TWO URLs (spec Decision B)

> Spec label "Decision B". Locked in spec §4/§7.B; recorded BEFORE code.

## Linked documents
- Spec: [[specs/stage-04/4.8-first-hosted-deploy-staging]]
- Related: [[adr-040-compute-topology-flyio]] (compute is on Fly; DB is NOT), [[adr-042-browser-backend-transport-direct]]
- Carry-forward: closes debt F006 (hosted Postgres extension bootstrap) on the `vector` bootstrap.

## Context
A fresh hosted Postgres has no `vector` extension and no schema. The app currently uses a **single**
`DATABASE_URL` with a default SQLAlchemy async engine (`backend/app/platform/db/session.py:6–8`) and
runs Alembic against the same URL. Managed Postgres is reached through a **transaction pooler**
(pgBouncer-style) for app connections — and a transaction pooler is incompatible with two things the
codebase relies on:
1. **asyncpg prepared statements** — the driver caches server-side prepared statements; a transaction
   pooler rebinds server connections per transaction, so the cache breaks ("prepared statement does
   not exist").
2. **session-scoped `pg_advisory_lock`** — the reaper's singleton lock (`app/domains/recovery/locks.py`)
   holds a session-level advisory lock on a pinned connection; through a transaction pooler the
   session identity is not stable, so the lock is unreliable.
Migrations (DDL, multi-statement, advisory locks) also need a real session, not a transaction pooler.

## Decision
- **One dedicated STAGING Supabase project** provides Postgres + auth + storage (one vendor, isolated
  from local and any future prod; ships the `vector` extension).
- **Two URLs:**
  - `DATABASE_URL` → the Supabase **transaction pooler**, with `ssl=require`, asyncpg
    `statement_cache_size=0`, and a unique `prepared_statement_name_func` (or `NullPool`). Used by the
    **app API + all three workers**.
  - `DIRECT_DATABASE_URL` → the Supabase **direct/session** endpoint. Used by **Alembic** and by the
    **reaper's advisory-lock connection** (the one place app code needs session semantics).
- **Connection budget:** small per-process pools (api + 3 workers) + migrator + reaper sized under the
  managed PG `max_connections`; app/workers route through the pooler; only the migrator and the
  reaper lock use direct connections.
- **Extension bootstrap:** an idempotent migration runs `CREATE EXTENSION IF NOT EXISTS vector`. Per
  spec §5, **`pgcrypto` is NOT bootstrapped** — no consumer exists in the tree (record, don't add). If
  the migration role lacks `CREATE EXTENSION`, enable `vector` once via the Supabase SQL console and
  document it; prefer the migration path.

## Consequences
- `session.py` engine creation is parametrized (connect args + pool sizing); a separate direct engine
  is introduced for migrations and the reaper lock.
- `scripts/check-staging-env` asserts `DATABASE_URL != DIRECT_DATABASE_URL`, that `DATABASE_URL` is the
  pooler endpoint, and `ssl=require` (the A2 VPS fallback documents the no-pooler exception).
- pgvector inserts/selects must be confirmed to round-trip over the pooler with prepared statements
  off (a 4.8a verification item; relates to the 4.4 `UserDefinedType`→pgvector carry-forward).
- F006 closes on the `vector` bootstrap alone.
