# Go-live checklist (product owner)

> **Status: DRAFT (12f Commit 7).** Stage 12 closes the MVP as **deploy-ready / production-candidate**,
> not live-in-production (**D-12-A: no hosted environment yet**). This is the ordered handoff for the
> product owner to execute when an external university hosting decision unblocks Stage 4.8. Follow
> [`deploy-procedure.md`](./deploy-procedure.md) for the mechanics.

## A. Provision (before first deploy)
- [ ] Managed Postgres (with `vector` + `pgcrypto`), Redis, object storage, and secrets store.
- [ ] Production env file: `LLM_PROVIDER=k2think` + `LLM_API_KEY`; `ENVIRONMENT=production`; real
      `CORS_ORIGINS` (hosted frontend origin(s)); real Supabase + storage creds; `COURSE_TIMEZONE`.
- [ ] **Extension bootstrap verified on real managed PG** (`CREATE EXTENSION vector; pgcrypto`). *(deferred — unverifiable until hosting)*
- [ ] **Rotate the K2Think `LLM_API_KEY` before go-live** — it was present in dev workspace `.env` files during development; issue a fresh key with the university / IFM and retire the old one.

## B. Build & release
- [ ] `./scripts/build-production.sh <prod-env>` passes the hygiene gate (no E2E hooks / fault flags; `LLM_PROVIDER=k2think`).
- [ ] Release-phase migration run explicitly (`alembic upgrade head`); `alembic current` == head `0059` (graph, not filename sort).
- [ ] Stack up; `/health/ready` 200 (DB+Redis); scheduler running; queues draining; security headers present; `window.__xyzE2E` absent.

## C. Promotion & watch  *(deferred-with-owner)*
- [ ] Staging → production promotion via `/land-and-deploy` executing this procedure on real infra.
- [ ] `/canary` post-deploy watch + health verification on the live environment.

## D. Resilience drills (execute once on real infra)  *(deferred-with-owner)*
- [ ] Backups confirmed enabled; **restore drill executed once** (restore → `alembic current` → spot-check); record RPO/RTO.
- [ ] **Rollback rehearsed** — the migration-downgrade path (`alembic downgrade -1`) run once against real hosted infra.

## E. Deferred features / mechanisms  *(deferred-with-owner)*
- [ ] **Stage 8.3 SSE streaming** built + validated against the real hosting proxy (buffering proxies break SSE). Assistant stays create-then-poll until then.
- [ ] **F-12C-CASCADE deletion mechanism** — the course-deletion path: either a cascade migration on the core-spine FKs (`module_sections`/`transcripts`/`section_assets`/`course_memberships` are currently `NO ACTION`; Stage 9–11 tables already cascade from `course_modules`) **or** an app-level ordered delete (the `dev_reseed` pattern) + prefix-scoped object-store cleanup (reuse 4.6 reconciliation). Owner-assigned migration block at go-live (ADR-063). **Not built in 12f.**
- [ ] **Next.js bump** (15.3.3 → current 15.x) in a small post-stage dependency pass (latent `npm audit` findings; not exploitable today — 12f decision **D3=B**).

## F. Final production-CORS verification
- [ ] On the real hosted origin: cross-origin preflight succeeds for the production origin and is rejected for a foreign origin (the `12f-cors-preflight` assertion, retargeted to the hosted origin).
- [ ] Confirm `allow_credentials` stays dropped (pure Bearer auth) and no localhost origins remain in `CORS_ORIGINS`.

## G. Security hardening before real-student data  *(deferred-with-owner)*
- [ ] **Professional third-party security pentest** before first real-student PII. The 12f `/cso` pass is an AI-assisted scan of typical issues — explicitly **not** a substitute for a professional pentest before real student data.
- [ ] **Tighten the CSP to nonce-based.** 12f shipped a pragmatic CSP (`'unsafe-inline'` for script/style; nonce-based deferred). Move to a nonce-based policy and validate in `/qa` + `/cso` before real-student launch.

## Locked 12f decisions (for the record)
- **D1=A** committed frontend port collapsed to `:3000`; `.env.example` CORS lists `:3000,:3001`.
- **D2=A** `LLM_DETAILED_MODEL_ID` = `MBZUAI-IFM/K2-Think-v2` (matches the live deployment).
- **D3=B** Next.js bump deferred-with-owner (see §E).
- **D4=A** full-MVP smoke = `/qa` evidence on the production-candidate build; per-feature assertions stay in the rule-14 suite.
