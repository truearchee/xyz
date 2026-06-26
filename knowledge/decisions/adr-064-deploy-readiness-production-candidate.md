---
type: adr
id: adr-064
stage: "12"
status: accepted
created: 2026-06-25
related-session: "12f"
---

# ADR-064 — Stage 12 closes as a deploy-ready production-candidate (D-12-A) + 12f deploy-hardening decisions

## Status
Accepted (Stage 12f, 2026-06-25; owner sign-off). Records the durable decisions of the 12f deploy-readiness
session. Owner decisions D1/D2/D3/D4 locked 2026-06-25.

## Context
**D-12-A (RESOLVED): no hosted environment exists**, and none arrives inside Stage 12 — Stage 4.8 (first
hosted deploy) and Stage 8.3 (SSE) are blocked on an external university hosting decision. Stage 12
therefore closes the MVP as **deploy-ready / production-candidate** — proven end-to-end on a local
production-shaped build — **not** live-in-production. The 4.8 deploy-prep deliverables are folded into 12f;
the real promotion is tracked deferred-with-owner (`docs/go-live-checklist.md`).

## Decision
1. **Close-out form.** Stage 12 is *deploy-ready*: a documented deploy procedure + a full-MVP `/qa` browser
   smoke on a local production-candidate build. No real hosted deploy is performed.
2. **Smoke timing (Option 2).** The full-MVP `/qa` smoke runs on the **deterministic adapter at the
   provider boundary only** (the full backend path still runs), but it uses the separate non-prod
   `docker-compose.qa.yml` overlay. **Rule 11** is met by a *separate* focused real-provider smoke. A flaky
   multi-minute real-AI browser run is not an acceptable final gate.
3. **F-12C-CORS → canonical `:3000` (D1).** The committed frontend port is collapsed to `:3000` (canonical
   in README/Playwright default/`config.py`/`.env.example`); `.env.example` lists both `:3000,:3001` so a
   fresh checkout works on either port; production overrides with the real origin.
4. **CORS-aware + security-header-aware 5xx.** The catch-all 500 handler runs inside Starlette's outermost
   `ServerErrorMiddleware`, bypassing `CORSMiddleware` and the normal security-header middleware path; it now
   re-attaches `Access-Control-Allow-Origin`/`Vary: Origin` for an allowed origin and reuses the same
   `apply_security_headers` helper so 500 responses carry the baseline hardening headers too.
5. **`allow_credentials` dropped.** Pure Bearer auth (no cookies) → credentialed CORS removed.
6. **Hygiene-gate-at-build + deploy-env seam.** `production_hygiene` (12b) is wired into
   `scripts/build-production.sh`, which **aborts build, migration, and runtime start** on any E2E hook /
   fault-injection flag or a non-`k2think` `LLM_PROVIDER`. The hygiene gate reads the production env file as
   data (`--env-file`) and does not shell-source secrets, so shell metacharacters in values are preserved and
   never executed. The script exports `XYZ_PROD_ENV_FILE` and runs compose with the same explicit
   `--env-file`, while `docker-compose.prod.yml` replaces backend app-service `env_file: .env` entries with
   that reviewed env file. The frontend explicitly resets inherited `env_file` to empty and receives only
   `NODE_ENV` plus `NEXT_PUBLIC_*`, so backend secrets never enter the Next.js runtime environment. The
   forbidden `NEXT_PUBLIC_*` hooks are **build-baked**, so the gate runs *before* `next build`; `LLM_PROVIDER`
   is also a **runtime/boot** boundary in the prod overlay, which exits before app boot unless it is
   `k2think`.
7. **Production-candidate images and QA split.** Backend + frontend run **non-root**; the frontend ships a multi-stage
   Next.js **standalone** image with E2E hooks off and a **pragmatic CSP** (`'unsafe-inline'` for
   script/style; nonce-based CSP is a post-MVP hardening) + HSTS/X-Frame-Options/etc. The deterministic
   provider is confined to the non-prod smoke and E2E overlays; `docker-compose.e2e.yml` and
   `docker-compose.fault.yml` pin literal `LLM_PROVIDER=deterministic`, and the production-candidate overlay
   never carries the test LLM adapter.
8. **Health readiness.** `/health/ready` is a real DB+Redis readiness probe (200/503); `/health` stays
   static liveness. The probe is excluded from the OpenAPI schema (infra endpoint).
9. **Next.js bump deferred (D3=B).** `next@15.3.3` is kept; the latent `npm audit` findings (not exploitable
   today) are deferred-with-owner to a small post-stage dependency pass.

## Consequences
- The committed config now "just works" on a fresh checkout (`cp .env.example .env` + `docker compose up`).
- Real promotion, `/canary`, extension-bootstrap-on-real-PG, backups-verify + restore-drill,
  rollback-rehearsal, SSE 8.3, and the **F-12C-CASCADE** deletion mechanism remain deferred-with-owner
  (go-live checklist). The assistant stays create-then-poll.
- The pragmatic CSP must be validated in the owner's `/qa` smoke + `/cso`; loosen any directive that blocks a
  real interaction. HSTS is emitted only outside dev.
- The Stage 12 `${LLM_PROVIDER}` E2E substitution backlog item is resolved; the `seed.mjs` 1000-user
  pagination backlog item is explicitly deferred-with-owner in `knowledge/open-questions.md`.
- Supersedes nothing; complements ADR-061 (error envelope), ADR-062 (signed-URL TTL), ADR-063 (retention).
