---
stage: "8.6a"
title: "Gate handoff — live browser gate + full active suite + rule-11 smoke pending a dedicated env"
status: resolved
created: 2026-06-20
updated: 2026-06-20
---

> **RESOLVED (2026-06-20):** the owner directed the live gate run on a non-disruptive alt-port stack
> (:8005/:3005 via `.context/8.6a-gate.override.yml`, kyiv `.env`+`.env.e2e` disk-to-disk, clean DB,
> backend image content-hash-verified to HEAD). **All gates GREEN:** the 8.6a homework gate PASSED, the
> **full active Playwright suite 22/22** (rule 14, run id `e2e-86a-final`, 7.2m), and the **rule-11 homework
> smoke PASSED** on the cerebras route. The gate caught two issues, both fixed in place: the homework route
> (Think/Nvidia `not_json` → cerebras, ADR-057 amend) and a test-wiring fragility (unique module title vs
> same-runId reruns). Two environment-only blockers were also fixed (CORS origin for :3005; cold-`next dev`
> route pre-warm). 8.6a is **FULLY VERIFIED**. The recipe below stands for 8.6b/8.6c. → [[steps/stage-08/8.6a-mode-coordinator-homework]]

# Findings — Stage 8.6a live-gate handoff (rule 10, not faked)

8.6a (mode coordinator + Homework) is implemented and verified at the **backend, type, and
frontend-wiring** levels. The **live browser gate + the rule-14 full active Playwright suite + the rule-11
homework smoke were NOT run in this session** — and are not faked. Mirrors the Stage 8.5 precedent
([[findings-8.5-gate-handoff]]): a fresh workspace lacks the local e2e harness, and here the live run would
also collide with the parallel Stage 10/11 stack.

## Why the live gate did not run here
1. **Port contention with the parallel stack.** `docker-compose.yml` maps the backend to host `:8000`, which
   is held by the running sibling `test2-backend-1` (a parallel Stage 10/11 workspace). My instructions
   forbid disrupting that stack, so the dallas backend cannot bind `:8000` as-is — a non-disruptive alt-port
   override is required (the prior gate used `.context/8.5-gate.override.yml` on :8005/:3005).
2. **`.env.e2e` absent.** `tests/e2e/fixtures/seed.mjs` needs `.env.e2e` (local Supabase URL + service-role
   key + JWKS/JWT config) to seed the standing users (`admin_e2e`/`lecturer_e2e`/`student_e2e`/…). This
   workspace has no `.env.e2e` and the standing users are not in the dallas `xyz_lms` DB.
3. **Shared Supabase-local.** Supabase-local (`:54321`) is healthy but shared with the sibling stack; re-seeding
   mid-session could race a running sibling gate. Standing-user upsert is idempotent, but the safe path is a
   dedicated gate run when the sibling is idle.

## What IS verified (this session)
- Backend: full `pytest` suite GREEN (see the report for the exact count); **24 new mode tests**
  (`tests/test_assistant_modes.py`) + the **53 existing assistant tests** GREEN (lecture path unregressed);
  migration **0042** single-head + fresh-DB round-trip (`0041↔0042`); prompt-drift guard OK.
- Frontend: `tsc --noEmit` clean; **vitest 9** (HomeworkStarters 2 + ConversationView 7) GREEN; OpenAPI client
  regenerated (new `createStudentAssistantConversation` op).
- Gate spec authored + **Playwright-discoverable**: `npx playwright test --list` lists
  `8.6a-assistant-homework.spec.ts` (and the full active suite = 22 tests / 19 files, rule 14 ready).

## Exact run recipe (when the dedicated env is available)
```
# 0) prerequisites: free :800x/:300x ports (sibling idle or alt-port override); .env + .env.e2e present
#    (copy disk-to-disk from a sibling per the 8.5 precedent — auth identical across siblings).
npm install && npx playwright install chromium            # done in this session

# 1) clean DB + standing users (alt-port override so the sibling is untouched)
docker compose -f docker-compose.yml -f .context/8.6a-gate.override.yml up -d --build
docker compose exec backend alembic upgrade head           # → single head 0042
node tests/e2e/fixtures/seed.mjs seed                       # seeds users + prints E2E_RUN_ID + manifest

# 2) run the 8.6a gate, then the FULL active suite (rule 14), serial
export E2E_RUN_ID=<printed>
export PLAYWRIGHT_BASE_URL=http://localhost:<frontend-port>
export NEXT_PUBLIC_API_BASE_URL=http://localhost:<backend-port>
npx playwright test tests/e2e/8.6a-assistant-homework.spec.ts
npx playwright test --workers=1                             # all 22 tests incl. 8.1/8.2/8.4/8.5/9 + 8.6a

# 3) rule-11 homework smoke (Think/Nvidia route) — see 8.6-real-provider-smoke.md
#    real K2Think creds via the workspace env channel; assert model-ID echo + L4 behavioral check.
```

## Resolution
Deferred to a dedicated gate run (rule 13 — deferred to a named step). 8.6a is **BACKEND + FRONTEND
VERIFIED, not FULLY VERIFIED**. The browser gate, the full active suite, and the rule-11 smoke are the
explicit remaining acceptance steps.

## Linked documents
- Report: [[steps/stage-08/8.6a-mode-coordinator-homework]]
- Smoke: [[steps/stage-08/8.6-real-provider-smoke]]
- Precedent: [[steps/stage-08/findings-8.5-gate-handoff]]
