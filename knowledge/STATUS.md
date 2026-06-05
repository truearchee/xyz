# Status

_Last updated: 2026-06-03 20:38 — Session 4.3.5a browser tracer proof complete_

## Current focus
Stage 1 is FULLY VERIFIED. Session 1.1b satisfied the browser gate: the root page calls `http://localhost:8000/health` directly through the generated client, CORS allows `http://localhost:3000`, and the browser shows live backend state.

4.3.5a tracer preparation is approved. Original tracer code baseline: `8144529ece104c4f870c546438ba0e5d7bf25e83`; approved preflight cleanup baseline: `2f323b9b92b47b9fd7429b8c5dd65511c7d8f2bd`.

Session 4.3.5a is complete pending final commit. Checkpoints A, B, C, C.5, D, and E are complete. Local Supabase is initialized and running via `npx supabase`; `.env.e2e` is ignored and points browser/seed usage at `http://127.0.0.1:54321`, while Dockerized backend services use `host.docker.internal` for Supabase/JWKS/storage reachability. Deterministic E2E Auth users and app DB fixtures were seeded twice with stable counts.

4.3.5a browser tracer proof passed. Playwright used real Supabase login, real backend, real DB rows, real local private Supabase Storage, and separate lecturer/student browser contexts.

Client edge proof status:
- JWT acquire: PROVEN
- CORS cross-origin Authorization request: PROVEN
- Multipart upload from real browser: PROVEN
- `GET /me` role resolution: PROVEN
- Signed-URL consumption without auth header: PROVEN
- `Cache-Control: no-store` on `/download-url`: PROVEN
- Token refresh on expiry: DEFERRED to 4.3.5b
- Stage 2/3/4 product UI: still UI PENDING

## Done recently
- Session 1.1b: Stage 1 browser gate satisfied. Docker-backed automated checks passed (`3 passed` config tests, `4 passed` health/CORS tests, full backend `136 passed`, frontend type-check exited 0), browser polling showed `ok -> unreachable -> ok`, and human DevTools Network confirmed direct `http://localhost:8000/health` with `Access-Control-Allow-Origin: http://localhost:3000` — completed 2026-06-03 13:58.
- Session 4.3.5a Checkpoint C: local Supabase E2E target initialized; `.env.e2e.example`, `docker-compose.e2e.yml`, and `tests/e2e/fixtures/seed.mjs` added; seed ran twice and verified four Auth users, four app users, one module, two active memberships, and draft/published sections — completed 2026-06-03 19:19.
- Session 4.3.5a Checkpoint C.5: local private storage bucket `section-assets` ready; `SUPABASE_PUBLIC_URL` added for browser-openable signed URL origins; provider tests, full backend suite, frontend type-check, diff check, and exact-key storage smoke passed — completed 2026-06-03 20:00.
- Session 4.3.5a Checkpoint D: throwaway `/tracer` page added with raw controls for session, `/me`, modules, sections, upload, publish, signed URL, and 403 display; rebuilt-container frontend type-check, static fetch scan, and diff check passed — completed 2026-06-03 20:13.
- Session 4.3.5a Checkpoint E: Playwright tracer spec passed all 15 browser/API/storage assertions with separate lecturer/student contexts; fixture seed idempotency, frontend type-check, static fetch scan, diff check, and exact-key cleanup verification passed — completed 2026-06-03 20:38.
- Session 4.3 review follow-up: added same-job and same-transcript different-key chunk concurrency coverage, version-bump and persisted parser-version tests, P1-P7 report trail, and a narrow test-cleanup retry after reproducing full-suite truncate deadlock; targeted `26 passed`, transcript `13 passed`, DB-spine `3 passed`, full backend passed twice with `130 passed`, frontend type-check and diff check passed — completed 2026-06-02 11:40.

## In progress
- None.

## Next up
- Final review/commit for Session 4.3.5a.
- Session 4.3.5b token-refresh/expiry proof after 4.3.5a is committed.

## Known issues / blockers
- Hosted Postgres extension bootstrap is not covered by the local Docker init script; handle `vector` and `pgcrypto` explicitly before first hosted deployment.
- The backend test suite still reports the existing `httpx` ASGI shortcut deprecation warning.
- `canPublish` is role-derived until a future membership capability column is introduced.
- 4.3.5a proved real browser section-asset upload and signed URL consumption against local Supabase Storage. Transcript raw-object writes remain behind `StorageProvider` and are still not live-tested against Supabase.
- Existing storage-key generation does not support run-scoped `e2e/{runId}` prefixes; E2E browser upload tests must clean exact returned keys only unless a future test-infrastructure change is approved.
- Replace/upload cleanup failure can leave orphaned private objects until a future reconciliation job exists.
- Already-issued signed read URLs remain usable until expiry; unpublish blocks future minting, not issued bearer URLs.
- Raw transcript files are private and not exposed; future summary/transcript surfaces must continue to avoid exposing raw storage keys.
- Chunk text is not exposed through any user-facing DTO yet; future 4.7 surfaces must preserve the no-raw-key and role-aware visibility boundaries.
- Transcript parse recovery is intentionally deferred to Session 4.6: enqueue failure can leave `uploaded`, and mid-parse crash can leave `parsing` plus a `running` job.
- Transcript chunk recovery is intentionally deferred to Session 4.6: parse-to-chunk enqueue failure can leave a queued chunk job, and mid-chunk crash can leave a `running` chunk job.
