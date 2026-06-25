---
type: session-spec
stage: 12
session: "12f"
slug: deploy-readiness-mvp-smoke
status: approved
created: 2026-06-25
updated: 2026-06-25
owner: developer
plan: knowledge/plans/stage-12/12f-deploy-readiness-mvp-smoke.md
report: knowledge/steps/stage-12/12f-deploy-readiness-mvp-smoke.md
---

# Session 12f — Deploy-Readiness + Full-MVP Smoke

> Filed from the approved Stage 12 master spec ([[specs/stage-12/12-release-hardening]] §5 12f + §7 deferred-with-owner). The Stage 12 **capstone**: produce a *deploy-ready, production-candidate* MVP and prove it end-to-end in a real browser — **without any real hosted deploy** (D-12-A: no hosted environment). Owner decisions locked 2026-06-25 (D1=A, D2=A, D3=B, D4=A). Run with `/careful`; one logical change per commit; branch + PR; **owner merges**. Kickoff + reconciliations: [[steps/findings-12]].

## Why
**D-12-A (RESOLVED):** no hosted environment exists; Stage 4.8 (first hosted deploy) and Stage 8.3 (SSE) are blocked on an external university hosting decision. Stage 12 therefore closes the MVP as **deploy-ready / production-candidate**, folding 4.8's deploy-prep deliverables into 12f. 12f absorbs the inherited items: **F-12C-CORS** (committed frontend-port ⇄ CORS-default mismatch), the **5 LOW `/cso`** hardening items, the **orphaned `production_hygiene`** script (built in 12b, never wired), **CORS-aware-500s**, and the **`LLM_DETAILED_MODEL_ID`** mismatch.

## Smoke-timing (LOCKED — Option 2)
Full-MVP `/qa` browser path runs on the **deterministic adapter at the provider boundary only** (full backend code path still runs) → a stable, fast gate. **Rule 11** is satisfied by a **separate** focused real-provider smoke in [[steps/stage-12/12f-real-provider-smoke]] asserting the echoed model id == the configured identifier. Same split proven in 12e (B1 DB-path + B2 real provider).

## Owner decisions (LOCKED — 2026-06-25)
- **D1=A** — F-12C-CORS → collapse onto `:3000` (canonical in README, `playwright.config.ts`, `config.py` default, `.env.example`); ship `.env.example` CORS as `http://localhost:3000,http://localhost:3001` (fresh checkout works either way; production overrides with the real origin); add a cross-origin Playwright assertion.
- **D2=A** — align `.env.example` `LLM_DETAILED_MODEL_ID` → `MBZUAI-IFM/K2-Think-v2` (the live deployment 12e's smoke echoed; `config.py` default is already `v2`). Cache-pool invalidation harmless on seed-only data.
- **D3=B** — **defer** the Next.js bump (deferred-with-owner; owner = product owner). Keep `next@15.3.3`; minimal/predictable 12f diff. Audit findings latent / not exploitable.
- **D4=A** — full-MVP smoke = `/qa` evidence only; no durable hook-free full-path Playwright clone (the active suite covers each feature per rule 14).

## What (scope) — BUILD / PROVE now
1. **Production-candidate build** — non-root Docker (both images); `.dockerignore` (both); production frontend (`next build`/`next start`, multi-stage, hooks off); CSP/HSTS + security headers; **`production_hygiene` wired so the build aborts on any hook/flag**; E2E hooks/fault-injection verifiably absent.
2. **Full-MVP `/qa` browser smoke** on that build (deterministic boundary) — admin → module → content → transcript → pipeline → summaries → student studies → quiz → wrong-answer mistake → glossary → assistant Q&A → progress/forecast → gamification → analytics.
3. **Health endpoints as real readiness checks** — `/health/ready` checks DB + Redis reachability.
4. **F-12C-CORS (D1)** — collapse onto `:3000` + cross-origin Playwright assertion; **CORS-aware 500s**; **drop `allow_credentials=True`**.
5. **Documented deploy procedure** — release-phase migration, managed-PG extension bootstrap (`vector`/`pgcrypto`), backups/restore, rollback/back-out — **written, not executed against real infra**.
6. **`docs/go-live-checklist.md`** — ordered owner handoff.
7. **Rule-11 real-provider smoke** (owner-run with the real key, like 12e).
8. **Rule-12 knowledge reconciliation** (stage-closing commit) — reconcile `roadmap.md` to D-12-A + flip the Stage 12 status table; README pointer; confirm the 0082 cleanup.

## Done means
- Prod-candidate build builds **non-root** with E2E hooks **absent**; `scripts/build-production.sh` **aborts the build on any planted hook/flag** (proven two ways).
- `/health/ready` returns 200 only when DB **and** Redis are reachable, 503 otherwise.
- Committed frontend port == CORS default (`:3000`); fresh `cp .env.example .env` + `docker compose up` passes the `:3000` preflight; cross-origin Playwright assertion green (allowed origin echoed, foreign origin not granted); `allow_credentials` dropped; a forced cross-origin 500 carries `Access-Control-Allow-Origin`.
- `.env.example` `LLM_DETAILED_MODEL_ID == MBZUAI-IFM/K2-Think-v2`.
- Full-MVP `/qa` smoke green on the prod-candidate build (evidence captured); **full active Playwright suite green (rule 14)**; **real-provider smoke recorded + model echo `v2` (rule 11)**.
- `docs/deploy-procedure.md` + `docs/go-live-checklist.md` written; README points to them.
- `roadmap.md` reconciled to D-12-A + Stage 12 status flipped, **in the stage-closing commit (rule 12)**; Next.js bump recorded deferred-with-owner.
- Backend pytest green; frontend `tsc` green; `git diff backend/openapi.json` empty unless `/health/ready` is added to the schema (then regen + commit). `/review` + `/cso` attached (owner pre-merge gate). Branch + PR; **owner merges.**

## Do NOT build (document-and-defer)
- **Go-live (owner = product owner):** real promotion (`/land-and-deploy`); `/canary`; extension-bootstrap-verified-on-real-PG; backups-verified + restore-drill; rollback-rehearsal; **Stage 8.3 SSE**; the **F-12C-CASCADE deletion mechanism** (and its cascade migration). Assistant stays **create-then-poll**.
- **Post-stage dependency pass:** the **Next.js bump** (D3=B).
- **No migration** (Alembic head stays `0059` — verified via the migration graph, not a filename sort; `0082` is the merge node). F-12C-CASCADE cascade migration is **not written now**. Any task that surfaces a schema change → **STOP and ask the owner for a block**.

## Linked documents
- Stage spec: [[specs/stage-12/12-release-hardening]]
- Plan: [[plans/stage-12/12f-deploy-readiness-mvp-smoke]]
- Report: [[steps/stage-12/12f-deploy-readiness-mvp-smoke]]
- Real-provider smoke: [[steps/stage-12/12f-real-provider-smoke]]
- Findings: [[steps/findings-12]]
- Runbook: [[steps/e2e-run-procedure]]
