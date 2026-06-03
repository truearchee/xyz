# Status

_Last updated: 2026-06-03 13:58 — Stage 1 FULLY VERIFIED by Session 1.1b_

## Current focus
Stage 1 is FULLY VERIFIED. Session 1.1b satisfied the browser gate: the root page calls `http://localhost:8000/health` directly through the generated client, CORS allows `http://localhost:3000`, and the browser shows live backend state.

## Done recently
- Session 1.1b: Stage 1 browser gate satisfied. Docker-backed automated checks passed (`3 passed` config tests, `4 passed` health/CORS tests, full backend `136 passed`, frontend type-check exited 0), browser polling showed `ok -> unreachable -> ok`, and human DevTools Network confirmed direct `http://localhost:8000/health` with `Access-Control-Allow-Origin: http://localhost:3000` — completed 2026-06-03 13:58.
- Session 4.3 review follow-up: added same-job and same-transcript different-key chunk concurrency coverage, version-bump and persisted parser-version tests, P1-P7 report trail, and a narrow test-cleanup retry after reproducing full-suite truncate deadlock; targeted `26 passed`, transcript `13 passed`, DB-spine `3 passed`, full backend passed twice with `130 passed`, frontend type-check and diff check passed — completed 2026-06-02 11:40.

## In progress
- None.

## Next up
- Recovery/browser-gate work for Stages 2-4.3 remains pending.

## Known issues / blockers
- Hosted Postgres extension bootstrap is not covered by the local Docker init script; handle `vector` and `pgcrypto` explicitly before first hosted deployment.
- The backend test suite still reports the existing `httpx` ASGI shortcut deprecation warning.
- `canPublish` is role-derived until a future membership capability column is introduced.
- Real Supabase Storage writes, signed read URLs, and transcript raw-object writes are behind `StorageProvider` but not live-tested against Supabase; automated tests use fake storage.
- Replace/upload cleanup failure can leave orphaned private objects until a future reconciliation job exists.
- Already-issued signed read URLs remain usable until expiry; unpublish blocks future minting, not issued bearer URLs.
- Raw transcript files are private and not exposed; future summary/transcript surfaces must continue to avoid exposing raw storage keys.
- Chunk text is not exposed through any user-facing DTO yet; future 4.7 surfaces must preserve the no-raw-key and role-aware visibility boundaries.
- Transcript parse recovery is intentionally deferred to Session 4.6: enqueue failure can leave `uploaded`, and mid-parse crash can leave `parsing` plus a `running` job.
- Transcript chunk recovery is intentionally deferred to Session 4.6: parse-to-chunk enqueue failure can leave a queued chunk job, and mid-chunk crash can leave a `running` chunk job.
