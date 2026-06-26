---
type: session-plan
stage: 12
session: "12f"
slug: deploy-readiness-mvp-smoke
status: approved
created: 2026-06-25
updated: 2026-06-25
owner: developer
spec: knowledge/specs/stage-12/12f-deploy-readiness-mvp-smoke.md
report: knowledge/steps/stage-12/12f-deploy-readiness-mvp-smoke.md
---

# Plan — Session 12f — Deploy-Readiness + Full-MVP Smoke

> HOW for [[specs/stage-12/12f-deploy-readiness-mvp-smoke]]. Decisions **D1=A, D2=A, D3=B, D4=A** (owner-confirmed 2026-06-25). Grounded in [[steps/findings-12]]. Run with `/careful`; one logical change per commit; branch + PR; **owner merges (agent never merges)**.

## Commit 1 — CORS finalization (F-12C-CORS + CORS-aware 500s, D1=A)
- `docker-compose.yml:91` frontend `"3001:3000"` → `"3000:3000"`.
- `.env.example:20` → `CORS_ORIGINS=http://localhost:3000,http://localhost:3001`.
- `backend/app/main.py:34` `allow_credentials=True` → `False` (pure Bearer auth; /cso LOW).
- `backend/app/platform/http/errors.py`: add `_apply_cors_headers(request, response)` — echoes the request `Origin` into `Access-Control-Allow-Origin` + `Vary: Origin` **when the origin is in `settings.CORS_ORIGINS`**; call it from `unhandled_exception_handler` only (the 500 path is the lone handler outside `CORSMiddleware` — `ServerErrorMiddleware` is outermost; 4xx/422 already get CORS headers via the inner `ExceptionMiddleware`).
- `knowledge/steps/e2e-run-procedure.md`: run command `PLAYWRIGHT_BASE_URL=...:3001` → `:3000`; annotate the gate-lesson `:3001` bullet as fixed.
- **Tests:** extend `backend/tests/test_error_envelope.py` — forced 500 with an allowed `Origin` carries `Access-Control-Allow-Origin` + `Vary: Origin`; a foreign `Origin` does not; forced 500 also carries baseline security headers via the shared `apply_security_headers` helper. New `tests/e2e/12f-cors-preflight.spec.ts` — `OPTIONS /me` preflight from the committed frontend origin echoes allow-origin; a foreign origin is not granted (joins the active suite, rule 14).

## Commit 1b — Model-id alignment (D2=A)
- `.env.example:75` `LLM_DETAILED_MODEL_ID=MBZUAI-IFM/K2-Think-v0` → `MBZUAI-IFM/K2-Think-v2` (matches `config.py:514` default + `prompts/detailed_summary/v1.yaml` + the 12e real-provider echo). Update the line-73/75 comment.

## Commit 2 — Health as real readiness
- `backend/app/api/routers/health.py`: keep `/health` (static 200 = liveness). Add `/health/ready` — DB `SELECT 1` via `get_db_session` (`backend/app/platform/db/session.py:16`) + Redis `ping` via `get_redis_connection` (`backend/app/workers/queues.py:24`); 200 only when both reachable, else **503** with the standard envelope. Reuse existing helpers; no new connection code.
- `docker-compose.yml:36-41` backend healthcheck → `/health/ready` *(flag: makes dependents wait for DB+Redis — desired; keep base on `/health` if it perturbs startup ordering — note in report).*
- **Tests:** ready=200 (deps up) / ready=503 (monkeypatched dep failure). Regen client iff the OpenAPI surface changes (rule 3).

## Commit 3 — Backend production hardening
- `backend/Dockerfile`: non-root user + `chown` `/app` + `/opt/models`, `USER` before `CMD`. Single-stage kept (model bake stays). **Do not exclude tests** — pytest runs in-container.
- New `backend/.dockerignore`: `.git`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.venv/`, local `.env*`, `*.egg-info/`.
- `backend/app/platform/http/security_headers.py` (new pure-ASGI middleware, mirroring `request_id.py`): `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`; `Strict-Transport-Security` **only when `not settings.IS_NON_PROD`** (HSTS no-op over local HTTP). Wire in `main.py:create_app`.
- **Tests:** header-presence test (HSTS absent in dev, present when `ENVIRONMENT=production`).

## Commit 4 — Frontend production build (no bump — D3=B)
- `frontend/Dockerfile`: `npm run dev` → **multi-stage production** — builder (`npm ci` + `next build`) → runner (`node:20-alpine`, non-root `node` user, `next start` / `output: 'standalone'`). `NEXT_PUBLIC_E2E_TEST_HOOKS` default **false** → `window.__xyzE2E` absent from the prod bundle.
- New `frontend/.dockerignore`: `node_modules`, `.next`, `.git`, local `.env*`, test artifacts.
- `frontend/next.config.ts`: `async headers()` — HSTS, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`, and a **pragmatic CSP** (`object-src 'none'`, `base-uri 'self'`, `frame-ancestors 'none'`, `script/style/connect/img-src` scoped to `'self'` + backend API origin + Supabase). CSP is the riskiest header — validate against the smoke; must not break the prod UI.
- **Keep `next@15.3.3`** (D3=B). **Verify:** `next build` + `tsc --noEmit` green; headers present.

## Commit 5 — Prod-candidate stack + hygiene gate wiring
- New `docker-compose.prod.yml` overlay (sibling to `docker-compose.e2e.yml`): frontend → prod target; `NEXT_PUBLIC_E2E_TEST_HOOKS=false`; no fault-injection env; backend app services replace the base `env_file: .env` with the reviewed `XYZ_PROD_ENV_FILE`; frontend resets inherited `env_file` to empty and receives only `NODE_ENV` plus `NEXT_PUBLIC_*`.
- New `scripts/build-production.sh`: pass the deploy env file to `python -m app.platform.production_hygiene --env-file` as data (never shell-source secrets) → **abort (non-zero) on any violation** → only then build, migrate, or start the stack.
- **Hygiene ⇄ deterministic seam (report it):** the script requires `LLM_PROVIDER=k2think` + forbids the frontend `NEXT_PUBLIC_*` hooks; hooks are **build-baked** (off → passes), and the prod overlay exits before app boot if `LLM_PROVIDER` is absent or not `k2think`. Prove two ways: clean prod-shaped env → hygiene exit 0; planted flag/provider → exit 1/64, build/start aborts. The deterministic smoke is split into the separate non-prod `docker-compose.qa.yml` overlay.

## Commit 6 — Full-MVP smoke + rule 14 (D4=A)
- `/qa` real-browser drive of the full path against the separate non-prod smoke overlay (`docker-compose.qa.yml`, production frontend shape, hooks off, deterministic boundary) — real UI login (hooks off; only the `window.__xyzE2E` token-bridge is unavailable, not needed). Evidence in the 12f report. **No durable `12f-full-mvp.spec.ts`** (D4=A).
- Rule 14: full active Playwright suite on the normal e2e build, serial `--workers=1`, fresh DB, `.env.e2e` sourced, base URL `:3000`. The normal E2E and fault overlays pin literal `LLM_PROVIDER=deterministic` so shell/project env cannot route tests to the real provider. All green.

## Commit 7 — Deploy docs (new `docs/`)
- `docs/deploy-procedure.md`: managed PG + Redis + backend + 3 workers + scheduler + prod frontend; **release-phase migration** (`alembic upgrade head` as an explicit phase, never on boot); extension bootstrap (`vector`,`pgcrypto`) written/unverifiable; secrets; production CORS origins; frontend public-env/secret-boundary verification; `GSTACK_*` note; backups/restore; rollback/back-out (`alembic downgrade`); the `scripts/build-production.sh` hygiene-gate step; head-from-graph guard.
- `docs/go-live-checklist.md`: every document-and-defer item (incl. F-12C-CASCADE, SSE 8.3, Next.js bump D3=B) + the locked D1/D2/D4 outcomes + final `allow_credentials`/production-CORS verification + frontend secret-boundary check.
- `README.md`: add a "Deployment" section linking both.

## Commit 8 — Knowledge / roadmap reconciliation (rule 12 — stage-closing commit)
- `knowledge/roadmap.md`: status line 62 (4.8 → DEFERRED, D-12-A); status line 73 (Stage 12 → IN PROGRESS/CLOSING, production-candidate, no live deploy); §706-722 (replace "staging→production promotion … because 4.8 exists" with D-12-A reality); §390-411 (4.8 DEFERRED, 8.3 deferred); annotate resolved carried-debt (signed-URL→ADR-062, can_publish→display-only, exception handlers→12a) + add Next.js bump to the deferred ledger (D3=B).
- `knowledge/steps/findings-12.md`: append 12f resolutions (F-12C-CORS, allow_credentials drop, CORS-aware-500, D2 model-id→v2, hygiene wired, Next.js deferred). 0082 already corrected at `:19` — add only a head-from-graph guard note.
- `knowledge/decisions/adr-064-*.md`: durable 12f decisions (deploy-ready close-out under D-12-A; D1 CORS canonical-port; CORS-aware-500 design; allow_credentials drop; hygiene-gate-at-build seam; D3 deferral).
- `STATUS.md` + `log.md` + `knowledge/open-questions.md` (close provider leak, defer seed pagination with owner); `architecture/` only if source paths changed.

## Verification (the 12f gate)
1. Backend: bring up the stack (sole-port-ownership), rebuild, `docker compose exec backend pytest` (incl. new CORS-500, readiness, security-header, build-abort tests) → full green.
2. Frontend: `next build` + `npm --prefix frontend run typecheck` green; headers present on a served response.
3. Prod-candidate stack: `./scripts/build-production.sh <prod-env> build`, `migrate`, `current`, then `up`; the script gates build/migrate/up with the reviewed env file; `/health/ready` 200 after start. The deterministic `/qa` full-MVP drive uses `docker-compose.qa.yml`, not `docker-compose.prod.yml`; rendered frontend env has no backend secrets.
4. Hygiene teeth: `scripts/build-production.sh` with a planted flag → build aborts (captured).
5. Rule 14: full suite serial `--workers=1`, fresh DB, `.env.e2e` sourced, base URL `:3000`.
6. Rule 11: owner runs the real-provider smoke → model echo `v2` match → [[steps/stage-12/12f-real-provider-smoke]].
7. `/review` + `/cso` (owner pre-merge gate).

## Findings to surface (rule 10)
F-12C-CORS resolved (committed config + cross-origin gate); CORS-aware-500 design + security headers on 500; D2 model-id reconciled; `production_hygiene` wired; frontend secret boundary closed; E2E provider leak closed by literal deterministic compose; seed pagination deferred-with-owner; Next.js bump deferred-with-owner (D3=B); F-12C-CASCADE + SSE 8.3 remain go-live. See [[steps/findings-12]].

## Linked documents
- Spec: [[specs/stage-12/12f-deploy-readiness-mvp-smoke]]
- Stage spec: [[specs/stage-12/12-release-hardening]]
- Report: [[steps/stage-12/12f-deploy-readiness-mvp-smoke]]
- Findings: [[steps/findings-12]]
