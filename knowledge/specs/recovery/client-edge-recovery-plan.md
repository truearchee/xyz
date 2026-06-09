# XYZ LMS — Client Edge Recovery Plan

**Status:** complete through 4.3.5e
**Sessions:** 4.3.5.0 → 4.3.5a → 4.3.5b → 4.3.5c → 4.3.5d → 4.3.5e
**Slots between:** Stage 4.3 and Stage 4.4
**Purpose:** Restore the walking skeleton by proving the browser → API → storage/DB/worker → browser path before backend AI work resumes.

## Governing principle

Keepable infrastructure, throwaway UI.

Keepable:
- Supabase browser client
- Session provider
- API wrapper that retrieves the current access token per request
- GET /me bootstrap contract
- E2E fixture/reset scripts
- OpenAPI client freshness checks
- Environment wiring

Throwaway:
- /login layout
- styling/copy/polish
- temporary tracer controls

The tracer proved the early spine and was deleted in 4.3.5e after real product UI replaced it for the recovery gate.

## Backend changes allowed during recovery

Allowed:
- GET /me
- read-only status projections over already implemented backend state, only if needed
- bug fixes discovered by tracer, documented before proceeding

Not allowed:
- new feature domains
- embeddings
- AI calls
- summary generation
- retry/recovery engines
- new auth architecture
- new storage paths
- domain behavior not already committed in the Stage 4.3 baseline

## Auth rule

Supabase proves identity.
The backend provides application context.

The frontend must not infer product role or memberships from JWT claims.
Role and active memberships come from GET /me.

GET /me returns active memberships only.
Archived memberships do not reach app bootstrap.

## 401 / 403 rule

401 means unauthenticated or expired token:
- clear session
- redirect to /login

403 means authenticated but not permitted:
- keep session
- render unauthorized state
- never redirect to /login for 403

## Session 4.3.5.0 — Baseline Freeze

Goal:
Freeze a known-good baseline before tracer work.

Done means:
- working tree clean
- committed backend baseline recorded
- Stage 1 FULLY VERIFIED
- Docker stack healthy
- OpenAPI client fresh or differences committed intentionally
- recovery plan exists at this path

## Session 4.3.5a — Client Edge Tracer Bullet

Goal:
Prove real browser auth, protected API access, multipart upload, publish flow, student visibility, and signed URL consumption.

Build:
- GET /me
- Supabase browser client
- SessionProvider
- API wrapper token-per-request
- /login
- /tracer
- E2E fixture setup
- Playwright tracer test

Do not build:
- dashboards
- app shell
- admin UI
- lecturer/student product pages
- transcript summaries
- AI
- new storage behavior

Required assertions:
- lecturer logs in through real Supabase
- GET /me returns lecturer context
- GET /modules returns only assigned module
- cross-origin Authorization request succeeds without CORS errors
- lecturer uploads PDF
- non-PDF upload rejected
- lecturer publishes section
- student logs in in a separate browser context
- GET /me returns student context
- student sees published section
- student cannot access draft section
- student requests signed URL
- /download-url response has Cache-Control: no-store
- browser opens signed URL without Authorization header
- student direct upload attempt returns 403 and keeps session

Still unproven after this gate:
- token refresh
- DTO ergonomics for real screens
- Stage 2/3/4 product UI

## Session 4.3.5b — App Shell + Role Routing

Goal:
Promote auth infrastructure into a real app shell.

Build:
- app shell
- route guards
- role routing from GET /me
- token refresh proof
- 401 recovery
- /tracer behind development-only flag

Do not build:
- admin feature screens
- content UI
- transcript UI

## Session 4.3.5c — Stage 2 Admin UI Backfill

Goal:
Make Stage 2 human-verifiable through the browser.

Build:
- admin user create/list/deactivate/reset password
- admin module create/list
- assign/remove lecturer and student memberships

No new backend endpoints unless approved after a finding.

## Session 4.3.5d — Stage 3 Content UI Backfill

Goal:
Make Stage 3 human-verifiable through the browser.

Build:
- lecturer section list
- upload/replace PDF
- notes edit
- publish/unpublish
- student published section view
- signed URL open/download

Must show processingStatus and publishStatus as distinct states.

## Session 4.3.5e — Stage 4.1–4.3 Transcript UI Backfill

Goal:
Make implemented transcript upload/parse/chunk pipeline observable from browser.

Build:
- lecturer VTT/TXT upload
- transcript processing status
- student cannot see raw transcript

Do not build:
- summaries
- embeddings
- AI status
- retry UI unless already implemented

Result:
- 4.3.5e Part 5 Playwright gate passed.
- Lecturer uploaded VTT/TXT through the real UI.
- Worker-driven transcript status reached `completed`.
- Test-level DB proof showed parse jobs completed, chunk jobs completed, transcript segments persisted, and transcript chunks persisted.
- Assignment upload, duplicate active transcript upload, and student transcript upload/read were rejected by backend contract.
- Student session remained active after 403.
- No raw transcript text/segments/chunks were exposed through product UI or DTOs.
- `/tracer` was deleted and `NEXT_PUBLIC_TRACER_ENABLED` removed.

## After recovery

Stage 4.4 may resume. Client Edge Recovery Block 4.3.5 is complete through Stage 4.1-4.3 browser verification.

From Stage 4.4 onward:
- every backend slice ships with a thin UI slice
- every stage has a browser-verifiable gate
- AIRequestLog still lands before the first K2Think call
