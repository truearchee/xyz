---
type: finding
stage: 08
session: "8.2"
slug: gate-image-contention
status: resolved-locally
created: 2026-06-18
updated: 2026-06-18
---

# Finding (8.2) — full-suite reds traced to mid-suite worker re-up onto non-8.2 code (image contention)

The first full-active-suite run was **15 passed / 2 failed** (`8.2-assistant-grounding`, `4.3.5e-transcript`)
— even though `8.2-assistant-grounding` PASSED standalone (26.4s) minutes earlier. Root cause is the
standing `kyiv-backend` shared-image-tag hazard from 8.1, with hard evidence this time:

## Evidence
- Container `StartedAt`: `backend`/`worker` = 15:01:58 (my bring-up), but `ai_worker` = **15:06:54** and
  `embedding_worker` = **15:07:23** — those two were RECREATED ~5 min later, mid-session.
- DB `assistant_messages`: the **15:03** turns (standalone run) had correct grounding
  (`lecture_grounded`/`general_not_from_lecture`/`educational_redirect`); the **15:10** turns (full-suite
  run) were all `status=completed` with **`grounding_status = NULL`** — the 8.1 code path, NOT the 8.2
  rewrite (which always sets a status).
- Live check on the post-restart `ai_worker`: `decide_grounding`/`v2`/`context_snapshot` all ABSENT from
  its `generation_service`, and it had **no source mounts** → it was running the BAKED image, not my tree.

So Conductor re-upped my stack with the **base** `docker-compose.yml` (no `-f override`), which dropped my
source mount → the ai_worker reverted to non-8.2 code → 8.2 turns produced NULL grounding (no basis → the
gate's `expectGrounded` failed). The same restart killed an in-flight chunk/embate job → `4.3.5e`'s
65s `waitForResponse` on the chunk-completion projection timed out.

## Why the 8.1 mount workaround was insufficient
8.1 mitigated by pinning a unique image tag in `docker-compose.yml`. This session first tried a
`docker-compose.override.yml` SOURCE MOUNT (auto-merged on a bare `docker compose up`). That works for MY
commands but **Conductor re-ups with explicit `-f docker-compose.yml`**, which does NOT auto-load the
override → no mount → baked code. A bind mount cannot survive a base-compose re-up; only baking the code
into the image the base compose references can.

## Resolution (local-only; revert before commit)
Folded the full e2e stack into the base `docker-compose.yml` so Conductor's `docker compose up -d`
reproduces it exactly:
- 4 backend services → `image: kyiv-backend-e2e-hatyai` (a UNIQUE per-workspace tag rebuilt from this
  tree, so a sibling rebuilding `kyiv-backend` can't clobber it). `build: ./backend` retained so it stays
  attributable.
- `env_file: [.env, .env.e2e]` on all services (so a base re-up keeps the e2e Supabase creds, the
  `NEXT_PUBLIC_E2E_TEST_HOOKS=true` frontend hook, and `EMBEDDING_PROVIDER=deterministic`).
- Removed the `docker-compose.override.yml` (now redundant; one config path = no my-up/Conductor-up drift).

`docker-compose.yml` is tracked, so these edits are LOCAL workarounds reverted before any commit (`.env`/
`.env.e2e` are gitignored). Verified after the fix: the post-recreate `ai_worker` imports the 8.2 grounding
code and the full suite is re-run.

## Second, DISTINCT failure: 4.3.5e timing race exposed by deterministic embeddings (NOT contention)
After the baked-image fix, the full suite went 16/17 with only `4.3.5e-transcript` red — and it failed
**in isolation too, with no worker restart in the run window**, so it is NOT the image contention. Root
cause: `4.3.5e` waits for the chunk-completed INTERMEDIATE projection state
(`CHUNK_COMPLETED_OVERALL_STATES = {'chunked','embedding','embedded'}`). With `EMBEDDING_PROVIDER=
deterministic`, embeds are instant and the deterministic LLM summaries are instant too, so the pipeline
races straight to the terminal `overall_state='summarized'` BEFORE the browser's first projection poll →
the predicate never matches → 65s `waitForResponse` timeout. The DB confirms the product is correct: the
transcript completed every step (parse/chunk/embed/brief/detailed) with no failures — only the test's
intermediate-state assumption lost the race.

**Resolution (applied):** the live E2E stack uses **real MiniLM** (leave `EMBEDDING_PROVIDER` unset →
`sentence_transformers`), the embedding behavior the whole suite was written against (8.1's 16/16). Real
MiniLM is still deterministic for identical text (distance 0 → the 8.2 grounding gate grounds on a
verbatim chunk; off-lecture distance >1.0 → general), but slow enough that the transcript lingers at the
intermediate state so `4.3.5e` (and any other fast-pipeline-sensitive spec) observes it. The
deterministic encoder remains in use for BACKEND PYTEST only (`tests/conftest.py`, in-process, no model
load). This refines review #9 (which assumed deterministic-in-E2E was free): the deterministic ENCODER +
`EMBEDDING_PROVIDER` mode ship as specified and are exercised by pytest; the live browser E2E uses real
MiniLM to preserve cross-stage pipeline-timing realism. Verified by re-running the full suite on real
MiniLM.

## Action for the env owner (permanent fix — carry to Stage 4.8/4.9)
Give each Conductor workspace a unique backend image tag by default (e.g. `image:
kyiv-backend-${COMPOSE_PROJECT_NAME}`) OR a source mount that Conductor's own re-up command includes, so
concurrent workspaces never recreate each other's backend onto the wrong code. This is the same standing
hazard tracked in open-questions since 8.1; 8.2 is the second stage to lose a suite run to it.
