---
stage: "8.5"
title: 8.5 browser-gate handoff — run recipe + what is already verified
status: resolved
updated: 2026-06-20
---

> **RESOLVED 2026-06-20 — the gate RAN GREEN.** The owner delivered the local creds (`.env` + `.env.e2e`
> copied disk-to-disk from the `kyiv` sibling; auth identical across all siblings, proven-current from the
> 8.4 gate). The recipe below was followed (alt-port stack `:8005`/`:3005` via
> `.context/8.5-gate.override.yml`, `kyiv-frontend` node:20 container + worcester source, local Supabase
> `:54321`, deterministic LLM adapter, clean DB). Result: 8.5 browser gate PASSED + **full active suite
> 21/21** (run id `e2e-mqlw0xei-9d1e2ebc`) + `/qa` clean. As predicted, the only finding was thin UI
> wiring (selector scoping, commit `011a635`); product code unchanged. 8.5 is FULLY VERIFIED. See
> [[steps/stage-08/8.5-save-to-glossary]] "Live gate — GREEN".

# Findings — Stage 8.5 browser-gate handoff (rule 10)

## Why this exists
The live browser gate + the rule-14 full active Playwright suite were **not run** in the implementation
session. This is recorded, not papered over (rule 10). Every prior Stage 8 gate (8.1/8.2/8.4) "ran
LOCALLY" in the engineer's e2e harness (see `log.md` `#8.4-GATE`); this fresh `worcester` workspace does
not contain that harness (`.env.e2e` and the gate compose override lived in the 8.4 workspace, and
`.env.e2e.example` ships blank Supabase URLs/JWKS). Standing it up requires the running local Supabase's
specific URLs/keys + the alt-port serve recipe — owner-environment territory.

## Already verified (does NOT need the browser to trust)
- Backend seam — 16 new real-DB pytest negatives (`test_glossary_conversation_save.py`): user-message
  rejected, pending/failed rejected, message-not-in-conversation 404, selectedText-not-in-message 422
  (+ markdown-straddle positive), unbound 404, not-owned 404 (no leak), unpublished/unassigned 404,
  double-submit idempotent (1 entry/source/event/enqueue), and the empty-context cache-collapse proofs.
- Frontend affordance gating — 5 new vitest component tests (`ConversationView.test.tsx`): affordance
  present on a completed assistant reply in a bound conversation; absent on the user's own message
  (exactly one for the assistant reply, none in the user row), in an unbound conversation, with no
  conversationId, and on pending/failed replies. This is exactly what the browser gate's two visible
  negative assertions check.
- Migration 0041 single-head round-trip; `tsc` green; client regenerated.

## Run recipe (adapt the documented 8.4 recipe — `log.md` `#8.4-GATE`)
1. `cp .env.e2e.example .env.e2e` and fill the local-Supabase values: browser-facing
   `NEXT_PUBLIC_SUPABASE_URL=http://127.0.0.1:54321`; container-facing
   `SUPABASE_URL=http://host.docker.internal:54321`, `SUPABASE_JWKS_URL=.../auth/v1/.well-known/jwks.json`,
   `SUPABASE_JWT_ISSUER=.../auth/v1`; keep the standard local anon/service-role keys + `E2E_TEST_PASSWORD`;
   set `E2E_SUPABASE_ALLOWED_URL` to the local URL. Local Supabase confirmed up on :54321.
2. Recreate the gate compose override (`.context/8.5-gate.override.yml`, mirroring 8.4): backend + workers
   on **:8005** bind-mounting `./backend` (live code, no rebake); frontend in a **node:20** container on
   **:3005** (the host runs node 25, whose localStorage shim breaks Next SSR — 8.4 gotcha);
   `env_file: [.env, .env.e2e]`; backend `CORS_ORIGINS` must include `http://localhost:3005`;
   `NEXT_PUBLIC_API_BASE_URL=http://localhost:8005`, `NEXT_PUBLIC_E2E_TEST_HOOKS=true`.
3. **Clean DB** + seed standing users (`node tests/e2e/fixtures/seed.mjs` — includes `student2_e2e`).
   Migrate to head (0041).
4. Set `PLAYWRIGHT_BASE_URL=http://localhost:3005`, `NEXT_PUBLIC_API_BASE_URL=http://localhost:8005`, a
   fresh `E2E_RUN_ID` + run-manifest; Playwright chromium is already installed locally.
5. Run the **full active suite serially** on the clean DB (rule 14):
   `npx playwright test --workers=1` (the 18 specs incl. `8.5-assistant-save-to-glossary.spec.ts`).
   Repeated same-run-id runs pollute quiz state (8.4 gotcha) → reset the DB between runs.
6. On GREEN: flip 8.5 to FULLY VERIFIED in `roadmap.md` + `STATUS.md`, append a `[gate]` line to `log.md`,
   and update this note's status to `resolved`. Then run `/cso`, `/review`, `/qa` per the spec.

## Risk if the gate surfaces something
The likeliest browser-only surprises are selection-capture quirks over rendered markdown (the gate uses
the same `selectTextIn` helper as Stage 7) or a testid mismatch. The backend rejections and the
affordance gating are already covered by the pytest + vitest above, so any gate failure should be a thin
UI-wiring fix, not a seam-logic redesign.
