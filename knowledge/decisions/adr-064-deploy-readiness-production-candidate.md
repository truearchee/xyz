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
   provider boundary only** (the full backend path still runs); **rule 11** is met by a *separate* focused
   real-provider smoke. A flaky multi-minute real-AI browser run is not an acceptable final gate.
3. **F-12C-CORS → canonical `:3000` (D1).** The committed frontend port is collapsed to `:3000` (canonical
   in README/Playwright default/`config.py`/`.env.example`); `.env.example` lists both `:3000,:3001` so a
   fresh checkout works on either port; production overrides with the real origin.
4. **CORS-aware 5xx.** The catch-all 500 handler runs inside Starlette's outermost `ServerErrorMiddleware`,
   bypassing `CORSMiddleware`; it now re-attaches `Access-Control-Allow-Origin`/`Vary: Origin` for an
   allowed origin so a cross-origin SPA can read the 5xx envelope/`request_id`.
5. **`allow_credentials` dropped.** Pure Bearer auth (no cookies) → credentialed CORS removed.
6. **Hygiene-gate-at-build seam.** `production_hygiene` (12b) is wired into `scripts/build-production.sh`,
   which **aborts the build** on any E2E hook / fault-injection flag or a non-`k2think` `LLM_PROVIDER`. The
   forbidden `NEXT_PUBLIC_*` hooks are **build-baked**, so the gate runs *before* `next build`; `LLM_PROVIDER`
   is a **runtime/boot** boundary, so the local smoke may run `deterministic` while a real deploy must set
   `k2think` (enforced by the gate + the existing boot refusal of deterministic providers in prod/staging).
7. **Production-candidate images.** Backend + frontend run **non-root**; the frontend ships a multi-stage
   Next.js **standalone** image with E2E hooks off and a **pragmatic CSP** (`'unsafe-inline'` for
   script/style; nonce-based CSP is a post-MVP hardening) + HSTS/X-Frame-Options/etc.
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
- Supersedes nothing; complements ADR-061 (error envelope), ADR-062 (signed-URL TTL), ADR-063 (retention).
