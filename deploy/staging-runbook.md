# Staging deploy runbook (Stage 4.8b)

Operator-facing procedure for the Fly.io staging deploy. "You provision, I build": this repo carries
the scripts + configs; you hold the flyctl auth, the two pre-created apps, and the secrets.

## Apps & artifacts
- Two Fly apps (adr-040/042): **backend** (`backend/fly.toml` — api + 3 worker process groups) and
  **frontend** (`frontend/fly.toml`). The backend app's hostname is `NEXT_PUBLIC_API_BASE_URL`; the
  frontend app's hostname goes in the backend's `CORS_ORIGINS`.
- **Immutable artifact (MF5):** `deploy-staging.sh` builds+pushes once, captures the image **digest**,
  and deploys that digest (`fly deploy --image …@sha256:…`) — never a bare rebuild / re-resolved tag.
  Record both digests + the git SHA in the 4.8d artifact-identity block.

## One-time provisioning (operator)
1. Create the two Fly apps; set `primary_region` in each `fly.toml`.
2. Staging Supabase project: confirm `vector` is creatable (see Extensions); ES256 signing.
3. Hosted protocol-Redis with `noeviction`.
4. `fly secrets set` on the **backend** app: `DATABASE_URL` (pooler, `?ssl=require`),
   `DIRECT_DATABASE_URL` (session), `REDIS_URL`, `SUPABASE_URL`, `SUPABASE_SECRET_KEY`,
   `SUPABASE_JWKS_URL`, `SUPABASE_JWT_ISSUER`, `LLM_API_KEY`, `CORS_ORIGINS`, and the
   `BOOTSTRAP_*_PASSWORD` secrets. Non-secret config (`ENVIRONMENT`, `DATABASE_POOLER`,
   pool sizes, `BOOTSTRAP_SEED_IDENTITIES`, emails) is in `backend/fly.toml [env]`.

## Deploy
```
set -a; . ./.env.staging; set +a        # load env for check-staging-env + frontend build args
scripts/deploy-staging.sh --dry-run      # env gate only
scripts/deploy-staging.sh                # full deploy
```
**Start-ordering:** the backend `release_command` (`sh scripts/release.sh`) runs FIRST — `alembic
upgrade head` over `DIRECT_DATABASE_URL`, then the idempotent identity bootstrap. Fly starts api + the
three worker groups **only after** the release succeeds (workers crashloop against a schema-less DB if
they precede it). A **non-zero release aborts the deploy** (MF1).

**O2 coupling (accepted):** migrate runs before bootstrap in one `release_command`. A transient
Supabase blip during bootstrap therefore aborts an otherwise-fine *migration* deploy. This is
acceptable under **expand-only** migrations (a migrated DB is compatible with the still-running old app
version), and the deploy is simply retried. Keep migrations backward-compatible one version.

## First ready boot — pass/fail
- `/health` → 200 (liveness, DB-free).
- `/health/ready` → **200** with `alembic_version == head` (the first time readiness goes green).
- **Workers (MF4):** all three Fly process groups `Up` AND registered in the RQ worker registry —
  `fly ssh console -a <backend> -C 'python scripts/check_workers.py'` prints ingestion/embedding/ai.
  (`/health/ready` proves only the API; a functional pipeline round-trip is 4.8d.)

## Pooler verifications — run the moment the staging DB is up (MF2)
A real transaction pooler exists for the first time, so these are now discoverable here, not at 4.8d:
- **(a) Advisory lock survives a handback cycle:** trigger the admin reaper twice (or restart a
  worker so startup recovery runs) — it must acquire the singleton lock over the **direct** engine and
  complete; no "could not obtain lock" / silent double-run. (adr-041; the lock is routed to
  `DIRECT_DATABASE_URL`.)
- **(b) Prepared statements off on the pooler:** exercise a pgvector insert/select via the app
  (upload → embed) — no asyncpg `prepared statement "__asyncpg_…" does not exist` error
  (`DATABASE_POOLER=true` → `statement_cache_size=0`). If either fails it surfaces at provisioning.

## Extensions (closes F006)
`alembic upgrade head` runs `CREATE EXTENSION IF NOT EXISTS vector` (migrations 0006/0007). The
Supabase `postgres` role over the **direct** connection can normally create `vector`. If it cannot
(privilege), run once in the Supabase SQL console: `CREATE EXTENSION IF NOT EXISTS vector;` then
re-deploy (the migration `IF NOT EXISTS` no-ops). No `pgcrypto` (no consumer — F-4.8a-4).

## Connection budget (MF3)
App + workers connect to the **pooler** (which multiplexes to Postgres); only the release migrator and
the reaper advisory lock open **direct** Postgres sessions. Fill `<max_connections>` from the plan.

| Source | Endpoint | Connections | Notes |
|---|---|---|---|
| api (`DATABASE_POOL_SIZE=5`, overflow 0) | pooler | ≤5 | tune down if the pooler's Postgres-side pool is small |
| worker / embedding_worker / ai_worker | pooler | ≤2 each (set per group) | RQ forks a child per job — connections established post-fork |
| release migrator | **direct** | 1, transient | only during `release_command` |
| reaper advisory lock | **direct** | 1, transient, singleton | one worker at a time (cross-process lock) |
| **Direct total (steady state)** | direct | ~0–1 | must stay well under `<max_connections>` − reserved |

Wrong sizing → failure-catalog #4 ("remaining connection slots reserved") on warm-up.

## Poison-migration abort rehearsal (MF1, hosted — both directions)
Prove the contract on staging once (the local proof is `backend/tests/test_release_abort.py`):
1. On a throwaway branch, add a revision whose `upgrade()` raises; deploy.
2. **Assert:** the release phase exits non-zero, the deploy is **aborted**, the **new version never
   serves** (the prior version stays up, or nothing is promoted), and `/health/ready` never goes green
   on the new release. Capture the `fly` output.
3. Revert the poison; redeploy; assert a clean deploy completes + `/health/ready` 200.
A deploy that *succeeds* against a broken migration means the gate is theater — this rehearsal is the
proof it is real.

## Rollback
- **App:** redeploy the previous immutable digest — `fly deploy -a <app> --image <prior ref@sha256:…>`.
- **DB:** **forward-fix** (no automated down-migrations in staging). Keep migrations
  backward-compatible one version where feasible so the prior app version tolerates the new schema.
