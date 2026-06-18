---
type: finding
stage: 08
session: "8.1"
slug: gate-run-blocked
status: resolved
created: 2026-06-18
updated: 2026-06-18
---

# Finding (8.1) — live gate run: two environmental blockers (RESOLVED) + a standing env hazard

The Stage 8.1 live gate (browser gate + full suite + real-provider smoke) eventually ran fully GREEN, but
only after working around **two environmental problems**. Both fixes were applied locally and **NOT
committed** (they are environment-specific). Recorded per roadmap rule 10.

## Blocker 1 — local Supabase test stack `edge_runtime` 502 (RESOLVED)
`npx supabase start` (project `test2`, repo `supabase/config.toml`) failed consistently with
`Error status 502` during health checks; the surfaced unhealthy container was `supabase_edge_runtime_test2`
(it had been exited for ~2 weeks). The assistant gate uses Supabase **auth/storage**, not edge functions.
**Fix (least-destructive, authorized):** set `[edge_runtime] enabled = false` in `supabase/config.toml`,
`supabase stop && supabase start` → `auth/v1/health` 200. The config edit was **reverted** afterward (the
running instance is unaffected; a future `supabase start` will 502 again unless edge_runtime is disabled or
repaired). **Action for the env owner:** repair or permanently disable `edge_runtime` in the local test
Supabase.

## Blocker 2 — shared `kyiv-backend` image tag contention (RESOLVED for this run; standing hazard)
The backend services share the image tag `kyiv-backend` across ALL Conductor workspaces. Sibling
workspaces (observed: `tokyo` actively running, plus a prior `stage-9` build) rebuild that tag, and
Conductor's stack management re-`up`s my `hat-yai` stack using the **base** `docker-compose.yml`
(`image: kyiv-backend`), so my `ai_worker`/`embedding_worker` were repeatedly recreated **mid-suite**
(~every 1.5–3 min) onto a sibling image **without my `app.domains.assistant`** → RQ `import_attribute`
failed → assistant turns never completed → 8.1 (last spec) failed while passing standalone.
**Fix:** point MY workspace's `docker-compose.yml` backend services at a unique tag
`kyiv-backend-e2e-hatyai` (built from my tree) + recreate. Conductor's recreates then use my image even
mid-suite (verified: the worker was recreated at 12:03 during the green run but onto my tag). This does
**not** touch other workspaces (a new tag, not a re-tag of the shared one). The `docker-compose.yml` edit
was **reverted** afterward (local workaround only).
**Action for the env owner / Stage 4.8–4.9:** give each workspace a unique backend image tag (or a source
mount) so concurrent workspaces don't clobber each other's `kyiv-backend`. Tracked in open-questions.

## A third (non-blocking) env note — host-side Supabase admin in specs
Specs that create run-scoped users host-side (e.g. `7-glossary`) read `process.env.SUPABASE_SERVICE_ROLE_KEY`
(default `''`). The Playwright run must **source `.env.e2e`** (`set -a; . ./.env.e2e; set +a`) or those
admin calls 401. `8.1` is unaffected (browser login only). Folded into [[steps/e2e-run-procedure]] mentally;
the run command used: `COMPOSE_PROJECT_NAME=hat-yai`, seed, source `.env.e2e`,
`PLAYWRIGHT_BASE_URL=http://localhost:3001 npx playwright test --workers=1`.

## Outcome
8.1 browser gate GREEN; full active suite **16/16** (rule 14); real-provider smoke **PASS** (model echo
`MBZUAI-IFM/K2-Think-v2`). Stage 8.1 flipped to FULLY VERIFIED. The migration-chain verification (the
requested checkpoint) was GREEN: single head `0032`, round-trip `0025→0030→0031→0032`.
