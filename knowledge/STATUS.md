# Status

_Last updated: 2026-06-05 15:42 - Session 4.3.5b app shell + role routing complete_

## Current focus
Stage 1 is FULLY VERIFIED. Session 1.1b satisfied the browser gate: the root page called `http://localhost:8000/health` directly through the generated client, CORS allowed `http://localhost:3000`, and the browser showed live backend state.

Session 4.3.5a is committed at `5f92698` and proved the client-edge tracer spine. Docs-only cleanup is committed at `7f06f471`; Session 4.3.5b used `7f06f471` as its clean preflight baseline.

Session 4.3.5b is complete. The frontend now has a minimal app shell, role routing, route guards, wrapper 401/403 behavior, E2E hook bridge, `/tracer` env gate, and browser proof for token refresh/recovery behavior. This is still recovery shell work, not product UI.

## Client edge - 4.3.5b result
- App shell + role routing (GET /me-driven, role-prefix guard): PROVEN
- Token refresh with rotated-token Authorization header: PROVEN
- 401 recovery (signOut + redirect to /login): PROVEN
- Client route guard cross-role (/unauthorized, session kept): PROVEN
- Server-side 403 cross-role defense in depth (session kept): PROVEN
- Logout from AppShell (session cleared + /login): PROVEN
- /tracer gated by NEXT_PUBLIC_TRACER_ENABLED: PROVEN
- Stage 2/3/4 product UI: still UI PENDING (backfilled in 4.3.5c/d/e)

## Done recently
- Session 4.3.5b: app shell and role routing completed. Rebuilt E2E stack passed; fixture seed produced four Auth users, four app users, one module, two active memberships, and two sections; Playwright `tests/e2e/4.3.5b-shell-routing.spec.ts` passed `1 passed (13.7s)`; frontend type-check passed; static fetch/JWT scans returned no matches; full backend `pytest` passed with `144 passed, 71 warnings` - completed 2026-06-05 15:42.
- Session 4.3.5a: browser tracer proof passed with real Supabase login, real backend, real app DB rows, local private Supabase Storage, and separate lecturer/student browser contexts - committed at `5f92698`.
- Session 1.1b: Stage 1 browser gate satisfied. Docker-backed automated checks passed (`3 passed` config tests, `4 passed` health/CORS tests, full backend `136 passed`, frontend type-check exited 0), browser polling showed `ok -> unreachable -> ok`, and human DevTools Network confirmed direct `http://localhost:8000/health` with `Access-Control-Allow-Origin: http://localhost:3000` - completed 2026-06-03 13:58.

## In progress
- None.

## Next up
- Session 4.3.5c - Stage 2 Admin UI backfill.
- Session 4.3.5d - Stage 3 Content UI backfill.
- Session 4.3.5e - Stage 4.1-4.3 Transcript UI backfill and `/tracer` deletion.

## Known issues / blockers
- Stage 2/3/4 product UI remains pending; current admin/lecturer/student routes are placeholders only.
- Hosted Postgres extension bootstrap is not covered by the local Docker init script; handle `vector` and `pgcrypto` explicitly before first hosted deployment.
- The backend test suite still reports the existing `httpx` ASGI shortcut deprecation warning.
- `canPublish` is role-derived until a future membership capability column is introduced.
- Transcript raw-object writes remain behind `StorageProvider` and are still not live-tested against Supabase.
- Existing storage-key generation does not support run-scoped `e2e/{runId}` prefixes; E2E browser upload tests must clean exact returned keys only unless a future test-infrastructure change is approved.
- Replace/upload cleanup failure can leave orphaned private objects until a future reconciliation job exists.
- Already-issued signed read URLs remain usable until expiry; unpublish blocks future minting, not issued bearer URLs.
- Raw transcript files are private and not exposed; future summary/transcript surfaces must continue to avoid exposing raw storage keys.
- Chunk text is not exposed through any user-facing DTO yet; future 4.7 surfaces must preserve the no-raw-key and role-aware visibility boundaries.
- Transcript parse recovery is intentionally deferred to Session 4.6: enqueue failure can leave `uploaded`, and mid-parse crash can leave `parsing` plus a `running` job.
- Transcript chunk recovery is intentionally deferred to Session 4.6: parse-to-chunk enqueue failure can leave a queued chunk job, and mid-chunk crash can leave a `running` chunk job.
