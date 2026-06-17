---
type: runbook
title: E2E (Playwright) suite — how to run it
created: 2026-06-16
updated: 2026-06-16
---

# E2E run procedure (active Playwright suite)

The active browser-gate suite needs a real stack + Supabase + a fixed run id. This was rediscovered
the hard way during Stage 5.5b; capture it so next time is one page, not an archaeology dig.

## Hard preconditions
- **`.env.e2e`** present at repo root (real Supabase creds — local `supabase` stack or a hosted test
  project). `seed.mjs` throws without it. Only `.env.e2e.example` is committed.
- **Sole port ownership.** The stack binds `:3000` (frontend), `:8000` (backend), `:5432` (db),
  `:6379` (redis). Multiple Conductor workspaces (stage-55 / kyiv / stage-5) **cannot** run their e2e
  stacks at once — they collide on these ports. **Stop the other workspaces' stacks first**, bring up
  exactly one, run, then stop it. (A sibling backend on `:8000` is the classic "service backend is not
  running" / port-already-allocated failure.)
- **`COMPOSE_PROJECT_NAME`** must match the running stack's compose project. The harness
  (`seed.mjs`, `fixtures/db.mjs`) calls **bare** `docker compose exec -T db|backend …` with no `-p`/`-f`,
  so it targets `COMPOSE_PROJECT_NAME` (or the dir name). Export it for seed AND the playwright run.

## Steps
```bash
# 0. Ensure no other workspace's stack holds the ports (stop them first).

# 1. Bring up THIS workspace's stack on the e2e overlay, built from the commit under test.
export COMPOSE_PROJECT_NAME=<project>   # e.g. stage-55 — must match the running containers
docker compose --env-file .env.e2e -f docker-compose.yml -f docker-compose.e2e.yml up -d --build

# 2. Confirm migrations are at head.
docker compose exec -T backend alembic upgrade head      # expect → current head; `alembic heads` singular

# 3. Seed Supabase users + fixtures + run manifest under a FIXED run id.
#    Run id MUST match /^e2e-[a-z0-9][a-z0-9-]{5,80}$/  (lowercase, starts "e2e-", hyphens; NO dots).
export E2E_RUN_ID="e2e-$(echo $RANDOM | md5 2>/dev/null | head -c8 || date +%s)"
node tests/e2e/fixtures/seed.mjs

# 4. Run the suite with the SAME run id, SERIAL.
npx playwright test --workers=1        # --workers=1 is required (run-manifest race-safety, 4.7-R2)

# 5. (optional) teardown — removes only this run's manifest-owned artifacts.
node tests/e2e/fixtures/teardown.mjs
```

## Gotchas
- **`--workers=1` is mandatory**, not a preference: parallel runs race the run manifest and saturate the
  single `embedding_worker` (see open-questions 4.7-R2 / the 4.9 follow-up).
- **Run id parity**: seed and the playwright run must share `E2E_RUN_ID` (seed writes
  `tests/e2e/.runs/<id>.json`; specs `requireRunId()` + load that manifest).
- **`E2E_RUN_ID` unset → every gate throws in `beforeAll`** ("E2E_RUN_ID must be exported…").
- **Frontend env is baked at build**: `NEXT_PUBLIC_E2E_TEST_HOOKS=true` (in `.env.e2e`) must be present
  at `up -d --build` time or `window.__xyzE2E` hooks are absent and auth-recovery specs hang.
- **Attribution**: build from the exact commit under test so reds are attributable; verify
  `alembic current` matches the expected head before trusting a result.
