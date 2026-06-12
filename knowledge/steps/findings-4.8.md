---
type: findings
stage: "04"
relates_to: ["4.8", "4.8a"]
status: open
created: 2026-06-12
---

# Stage 4.8 findings

Resolution vocabulary (rule 13 / spec §15): **fixed in this block** / **deferred to a named session** /
**accepted with written rationale** / **rejected as invalid**. Unresolved findings block FULLY VERIFIED.

## F-4.8a-1 — Upload path: FastAPI multipart passthrough (NOT signed-URL PUT) → body-size fork

**Status:** RESOLVED (confirmed) · **Resolution:** fixed-classification in 4.8a.
`frontend/src/lib/api/upload.ts:201-216` (`uploadTranscript`) → `uploadMultipart` (`:112-164`) →
`fetch(POST, body: FormData)` to `/modules/{id}/sections/{id}/transcript`; explicit `413` handler at
`:151`. ⇒ Failure-catalog #1 **fork #1 (API body-size) activates**; storage-bucket-CORS fork is dormant.
**Action:** ensure the staging platform ingress permits bodies ≥ the app caps
(`MAX_TRANSCRIPT_UPLOAD_BYTES`=10 MB, `MAX_SECTION_ASSET_UPLOAD_BYTES`=25 MB) so the **app** is the
binding 413. Fly imposes no nginx-style ~1 MB cap, so the binding limit is uvicorn/Starlette + the app
caps — confirm at provisioning (4.8a human handoff); no app code change needed (caps already exist).

## F-4.8a-2 — pgBouncer/transaction-pooler prepared-statement incompatibility

**Status:** FIXED in 4.8a · `backend/app/platform/db/session.py`.
asyncpg caches server-side prepared statements; a transaction pooler rebinds backends per txn → "prepared
statement does not exist". Fixed by an **explicit** `DATABASE_POOLER` flag (MF3 — never a port sniff;
Supabase direct + pooler can both be :5432) that drives `connect_args={statement_cache_size:0,
prepared_statement_name_func: unique-per-call}` + small bounded pool. Off-pooler (local) returns `{}` →
engine construction is byte-identical to before (proven: full backend suite 409 + active browser suite
9/9 green with the change in place). Exact `connect_args` combo against the live pooler finalized in 4.8b.

## F-4.8a-3 — Advisory lock unreliable over a transaction pooler (per-connection session lock)

**Status:** FIXED in 4.8a · `session.py::create_direct_engine` + `worker.py` + `admin.py`.
`pg_try_advisory_lock` is session-level; held across the reaper's multiple commits on a pinned
connection (`recovery/locks.py:36`). Over a transaction pooler that connection is handed back → the lock
is lost. Fixed by routing BOTH lock call sites to the **direct/session** endpoint via a NullPool
`create_direct_engine()`: worker startup reads `DIRECT_DATABASE_URL or DATABASE_URL`; the admin-trigger
path (`admin.py`, previously `engine=db.bind` = pooler) uses a per-call direct engine when
`DIRECT_DATABASE_URL` is set (else `db.bind`, unchanged local/test). Concurrency proven:
`test_two_concurrent_reapers_exactly_one_proceeds` (two racing reapers → exactly one runs). **Caveat
(stated, not overclaimed):** the unit test runs on a DIRECT connection, so it proves singleton-under-
concurrency, not the pooler-handback mode. **MF2 (4.8b):** that handback mode is now **4.8b-discoverable**
(the first real pooler exists) — a developer-run pass/fail the moment the staging DB is up; see
`deploy/staging-runbook.md` §"Pooler verifications".

## F-4.8a-4 — pgcrypto has no consumer → vector-only extension bootstrap

**Status:** REJECTED as unneeded (pgcrypto) · vector bootstrap RESOLVED.
`rg` finds only `CREATE EXTENSION IF NOT EXISTS vector` (`alembic/versions/0006:30`, `0007:115`); no
`pgcrypto`, no `gen_random_uuid`/`uuid_generate`/`uuid-ossp` (UUIDs are app-side `uuid7()`). So pgcrypto
is dropped from the migration scope AND from `check-staging-env`. The `vector` `CREATE` **already exists**
in migrations → F006's residual gap is only the migration-role `CREATE EXTENSION` **privilege**, verified
in 4.8b. F006 closes on the vector bootstrap alone.

## F-4.8a-5 — Fault-injection fail-loud predicate (O1)

**Status:** FIXED in 4.8a (developer-ruled) · `backend/app/platform/faults/boot.py`.
Refuse-to-boot when a fault flag is active AND `not IS_NON_PROD` (ENVIRONMENT ∈ {production, staging}) —
the SAME predicate as the retained step-level guard. NOT narrowed to {test, e2e}: the local fault harness
(`docker-compose.fault.yml`) runs under `ENVIRONMENT=development`, which is not hosted, so a {test,e2e}
predicate would crash-loop local fault testing for zero security gain. **Gap-closer:** `check-staging-env`
asserts `ENVIRONMENT=staging` *explicitly* (the boot check permits development; the script guards the env
value). Both directions unit-tested (`test_fault_boot_check.py`) and live-validated under the fault overlay
(ai_worker boots with `LLM_FAULT_INJECTION` set + development).

## F-4.8a-6 — Connection budget under a small managed PG

**Status:** DEFERRED to 4.8b (sizing against the provisioned plan).
4.8a ships conservative small pool defaults (`DATABASE_POOL_SIZE=5`, `DATABASE_MAX_OVERFLOW=0`, pooler
only); the exact per-process integers (api + 3 workers + migrator + reaper vs `max_connections`) are
finalized against the real Supabase plan and recorded in the deploy runbook. `check-staging-env` cannot
read `max_connections`; it is documented, not script-enforced.

## F-4.8a-7 — ECC P-256 / ES256 already supported

**Status:** RESOLVED (already satisfied) · config task DROPPED.
`backend/app/platform/auth/jwt.py` decodes with `algorithms=["RS256","ES256"]`; the backend test harness
already mints + validates ES256 over SECP256R1 (`conftest.py:141,198`). So no "confirm asymmetric signing"
config work; the runtime assertion that a *staging-minted* token validates is carried to the **4.8d** smoke.

## F-4.8a-8 — Redis eviction (noeviction) is a provisioning-time setting

**Status:** DEFERRED to provisioning (4.8a human handoff) · documented.
Managed Redis often defaults to `allkeys-lru` → silent RQ job-hash eviction. Set `noeviction` on the
hosted instance. Not an in-repo code change; documented in `.env.staging.example` + the fly notes.

## F-4.8a-9 — Frontend prod image cannot also serve the e2e hooks (build-time vs runtime inlining)

**Status:** ACCEPTED-with-rationale · deviation from spec B5 ("rewrite frontend/Dockerfile").
`output:'standalone'` inlines `NEXT_PUBLIC_*` at BUILD; the local e2e suite injects
`NEXT_PUBLIC_E2E_TEST_HOOKS=true` at RUNTIME (only the dev `next dev` image honors that). A single image
cannot serve both. Resolution: keep `frontend/Dockerfile` (dev, for local + e2e) and add a SEPARATE
`frontend/Dockerfile.prod` (staging) — two Dockerfiles, two purposes, mirroring the umbrella "two suites"
reframe. This IS the §8 hygiene boundary (the prod build never receives the hook arg).

## F-4.8a-10 — Node base pinned by version, not yet by digest (offline build)

**Status:** ACCEPTED-with-rationale (digest captured at provisioning).
`Dockerfile.prod` pins `node:20.18.1-alpine` (exact patch) via `ARG NODE_IMAGE`; an offline build cannot
resolve a live `sha256:` digest. The immutable digest is captured at first build and recorded in the
deploy runbook + the 4.8d artifact-identity block.

## F-4.8c-1 — SSE probe shipped (C1); hosted progressive-delivery check is developer-run

**Status:** FIXED in 4.8c (probe) · hosted check DEFERRED to the deploy run.
`/internal/sse-probe` (`sse_probe.py`): gated by `ENABLE_INTERNAL_SSE_PROBE` (404 when off), admin-only,
`text/event-stream`, 3–5 chunks, no compression, anti-buffering headers. Unit-verified
(`test_sse_probe`, 3/3). The §7.C2 "streams PROGRESSIVELY, not buffered" property is only assertable
from the staging browser over D1 (not from an in-process client) → developer-run at deploy.

## F-4.8c-2 — Runtime hook gate is NOT byte-clean; O1 exclusion required; regex gotcha

**Status:** FIXED in 4.8c (binds to Dockerfile.prod, F-4.8a-9).
A prod build with `NEXT_PUBLIC_E2E_TEST_HOOKS` unset still left `__xyzE2E` in **5** `.next/static`
files — Next's minifier did NOT dead-code-eliminate the runtime-gated hook. So O1 (exclude the e2e
modules from the prod build via a `!dev` `NormalModuleReplacementPlugin` → no-op stub) is genuinely
required; the deployed bundle (`.next/standalone`+`static`+`server`) is then byte-clean of `__xyzE2E`
and `registerE2ETestHooks`. **Gotcha:** the replacement regex must match the **resolved `.ts` path**
(`/(^|[\\/])e2e[\\/](testHooks|e2eAuthOverride)(\.tsx?)?$/`), not just the bare `../e2e/testHooks`
request, or it only partially fires (server/some chunks retain the hook).

## F-4.8c-3 — §8 backend proof reframed (no fault HTTP route exists)

**Status:** ACCEPTED-with-rationale (reframe).
`rg` finds no fault/test HTTP route — fault injection is env-flag + worker-side only. So the umbrella
§8 "fault route returns 404/403" has nothing to 404. The real backend proof: fault flags ABSENT in
staging (`check-staging-env`) + fail-loud boot (`assert_fault_injection_safe`, `test_fault_boot_check`)
+ no HTTP surface that can trigger fault injection.

## F-4.8c-4 — check-staging-env is a HARD deploy gate

**Status:** FIXED in 4.8c (proven, not asserted).
`deploy-staging.sh --dry-run` rehearsal: GOOD env → exit 0; a stale renamed name (`K2THINK_API_KEY`)
→ exit 1; a dev-Supabase env (`SUPABASE_URL == DEV`) → exit 1. The gate FAILS the deploy (the env
script runs under `set -e` before any `fly deploy`), not warns.

## F-4.8c-5 — CORS staging origin

**Status:** FIXED in 4.8c (config) · `allow_credentials` DEFERRED to 4.9.
The staging frontend origin is a `CORS_ORIGINS` value (the middleware already reads it; no code
change). Preflight allows `OPTIONS` + `Authorization`/`Content-Type`/`Idempotency-Key` (`allow_headers
=["*"]`). `allow_credentials=True` removal stays 4.9.

## F-4.8d-1 — 4.3.5c deterministically flakes on accumulated DB state (admin-list pagination)

**Status:** DEFERRED (test isolation / Stage 5 pagination envelope; candidate for the 4.9 hygiene batch).
On repeated active-suite runs, `4.3.5c-stage2-admin` fails at `getByTestId('admin-module-row-…')`
toBeVisible — the test creates a module and expects its row, but **58 accumulated `course_modules`** in
the dev DB (`xyz_lms`) overflow the admin-list page so the new row is off-page. **Not a 4.8a–d
regression:** 4.3.5c PASSED in the first clean run with the same injected code; subsequent runs added
the accumulation. **NOT papering over it:** truncating `course_modules` would buy a convenient green
while burying the real defect — the active suite is **not isolated from accumulated DB state**. The
finding is logged, not reset. Real fixes: (a) per-spec DB isolation/teardown so runs don't accumulate,
and/or (b) a deterministic admin-list pagination envelope (Stage 5) the test asserts against rather than
"the row is on page 1". Revisit in the **4.9 hygiene batch** (alongside the 4.7-R2 `--workers=1`
fragility). The authoritative rule-14 result is the first clean run's 9/9 + fault 2/2 = 11/11.
