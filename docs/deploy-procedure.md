# Deploy procedure (production-candidate)

> **Status: DRAFT (12f Commit 7) — written, not executed against real infra.** Stage 4.8 (first hosted
> deploy) is deferred-with-owner: **no hosted environment exists yet (D-12-A)**. This is the repeatable
> procedure to follow when hosting exists; the steps that can only be *verified* against real managed
> infra are flagged and tracked in [`go-live-checklist.md`](./go-live-checklist.md).

## Topology
Stand up, in order: **managed Postgres** (with `vector` + `pgcrypto`) → **Redis** → **backend** → the
**three workers** (`worker`/ingestion, `embedding_worker`, `ai_worker`) → **scheduler** → **frontend**
(production build). The backend and all workers share the one non-root `kyiv-backend` image; the
frontend is the non-root standalone image from `frontend/Dockerfile.prod`.

## 1. Secrets & environment
Provide a production env (never committed) with at least:
- `DATABASE_URL` (managed Postgres, `asyncpg`), `REDIS_URL`.
- `SUPABASE_*` (URL, secret key, JWKS URL, issuer), `SUPABASE_STORAGE_*`.
- `LLM_PROVIDER=k2think` + `LLM_API_KEY` + model ids (`LLM_DETAILED_MODEL_ID=MBZUAI-IFM/K2-Think-v2`).
- `ENVIRONMENT=production` (enables HSTS); the production overlay refuses app-service boot unless
  `LLM_PROVIDER=k2think`.
- **Production `CORS_ORIGINS`** = the real hosted frontend origin(s), comma-separated, no trailing slash.
- `COURSE_TIMEZONE` / `INSTITUTION_TIMEZONE` = the institution's real zone.
- Public frontend values only: `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_SUPABASE_URL`, and
  `NEXT_PUBLIC_SUPABASE_ANON_KEY`. All `NEXT_PUBLIC_*` test hooks and every fault-injection flag
  **unset/false** (the build gate enforces this).
- **Under Conductor:** strip any `GSTACK_*` test/override env from production shells before building.

## 2. Build (hygiene-gated)
```bash
./scripts/build-production.sh <prod-env-file> build
```
This runs the pure-stdlib `production_hygiene` assertion first and **aborts the build (non-zero) if any
E2E hook / fault-injection flag is set or `LLM_PROVIDER != k2think`**, then builds the prod images
(`docker-compose.prod.yml`). The script passes the env file to the hygiene gate as data (`--env-file`);
it does **not** shell-source the secrets file, so `$`, backticks, and other shell metacharacters in secrets
are not expanded or executed. The script exports `XYZ_PROD_ENV_FILE=<prod-env-file>` and calls `docker compose
--env-file <prod-env-file> ...`, so the same reviewed env is used for image-build interpolation and
backend/worker/scheduler runtime `env_file` resolution. The backend app services use `env_file: !override`
in the prod overlay, so the base compose `env_file: .env` is replaced instead of silently supplying missing
runtime values. The frontend explicitly resets inherited `env_file` to empty and receives only `NODE_ENV`
plus `NEXT_PUBLIC_*` values; backend secrets (`DATABASE_URL`, `REDIS_URL`, `SUPABASE_SECRET_KEY`,
`LLM_API_KEY`, etc.) must not appear in the rendered frontend environment. The forbidden `NEXT_PUBLIC_*`
hooks therefore can never be baked into the frontend bundle.

> Do **not** run bare `docker compose -f docker-compose.yml -f docker-compose.prod.yml ...` for a deploy.
> The prod overlay requires `XYZ_PROD_ENV_FILE`; the production path must go through this script or pass the
> same explicit `--env-file` + `XYZ_PROD_ENV_FILE` pair.

## 3. Managed-Postgres extension bootstrap
The local stack bootstraps extensions via `docker/postgres/init` (mounted into the pgvector image). A
**managed** Postgres can't mount init scripts — run once as a privileged user before the first migration:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```
> ⚠️ Unverifiable until real managed Postgres exists — go-live item.

## 4. Release-phase migration (NEVER on boot)
Migrations are a deliberate, explicit release phase — the image `CMD` is `uvicorn`, nothing auto-migrates:
```bash
./scripts/build-production.sh <prod-env-file> migrate
./scripts/build-production.sh <prod-env-file> current   # confirm head
```
> The current single head is **`0059`** — confirm with `alembic heads` / the migration graph, **not** a
> filename sort (`0082` is the merge node, not the head; this trap cost a stage's worth of confusion).

## 5. Start & verify
```bash
./scripts/build-production.sh <prod-env-file> up
```
- `GET /health` → 200 (liveness).
- `GET /health/ready` → 200 only when **DB and Redis** are both reachable (the prod-candidate backend
  healthcheck uses this).
- Confirm the scheduler is running (daily 06:00 local agent run) and the three queues drain.
- Confirm security headers on a frontend response (CSP, HSTS, X-Frame-Options, X-Content-Type-Options,
  Referrer-Policy) and that `window.__xyzE2E` is **absent**.
- Confirm the rendered frontend container environment contains only `NODE_ENV` and `NEXT_PUBLIC_*` keys; no
  backend secret material (`DATABASE_URL`, `REDIS_URL`, `SUPABASE_SECRET_KEY`, `LLM_API_KEY`, storage keys,
  or provider credentials).
- Confirm a misconfigured provider refuses to start: this overlay exits before boot unless runtime
  `LLM_PROVIDER=k2think`. The deterministic `/qa` smoke is separate and non-prod:
  `docker-compose.qa.yml`.

## 6. Backups & restore  (procedure written; drill is a go-live item)
- Enable managed-Postgres automated backups (point-in-time if available); confirm object-storage
  durability/versioning on the assets bucket.
- **Restore drill (execute once at go-live):** restore the latest backup into a scratch DB, run
  `alembic current`, spot-check core tables. Record the RPO/RTO observed.

## 7. Rollback / back-out
- **Application:** redeploy the previous image tag.
- **Migration:** if a release-phase migration is bad, back it out explicitly:
  ```bash
  XYZ_PROD_ENV_FILE=<prod-env-file> \
    docker compose --env-file <prod-env-file> -f docker-compose.yml -f docker-compose.prod.yml \
    run --rm backend alembic downgrade -1
  ```
  Rehearse this once against real hosted infra at go-live (the downgrade path is documented but unrehearsed).

## Local deterministic /qa smoke (non-prod only)
The owner-observed full-MVP `/qa` smoke intentionally uses the deterministic adapter at the provider boundary
for stability, but it must not use the production overlay. Run it with the separate non-prod overlay:
```bash
docker compose --env-file .env.e2e \
  -f docker-compose.yml -f docker-compose.e2e.yml -f docker-compose.qa.yml \
  up -d --build
```
This keeps the standalone production frontend image and `NEXT_PUBLIC_E2E_TEST_HOOKS=false`, while keeping
the backend non-prod (`ENVIRONMENT=development`, `LLM_PROVIDER=deterministic`).

## Deferred to go-live (see [`go-live-checklist.md`](./go-live-checklist.md))
Real promotion (`/land-and-deploy`), `/canary`, extension-bootstrap **verified** on real PG, backups
**verified** + restore-drill executed, rollback **rehearsed**, Stage 8.3 SSE, the F-12C-CASCADE deletion
mechanism, and the deferred Next.js bump.
