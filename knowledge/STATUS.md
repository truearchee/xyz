# Status

_Last updated: 2026-06-01 00:21 — Session 4.1 transcript upload accepted_

## Current focus
Session 4.1 (Transcript Upload + DB Status Only) is accepted/done. Verification passed for Docker build/start, Alembic `0004`, targeted transcript tests, full backend tests, OpenAPI client generation, frontend rebuild/restart, frontend type-checking, and `git diff --check`.

## Done recently
- Session 4.1: assigned lecturer VTT/TXT transcript upload and active transcript read accepted after Docker verification; backend `83 passed`, transcript `11 passed`, frontend type-check passed, and `git diff --check` passed — completed 2026-06-01 00:21
- Session 3.3: student published-section visibility and signed read URL authorization accepted after Docker verification; final closeout rerun passed with backend `72 passed`, content `20 passed`, frontend type-check passed, and `git diff --check` passed — completed 2026-05-31 18:45; reverified 2026-05-31 19:09
- Session 3.2: publish/unpublish and lecturer notes accepted after Docker verification; backend `69 passed`, content `17 passed`, frontend type-check passed, and ADRs 009-011 captured the locked decisions — completed 2026-05-31 14:36
- Session 3.1: file upload/list/replace accepted after Docker verification; backend `65 passed`, content `13 passed`, frontend type-check passed, and codegen now trims generated TypeScript trailing blank EOF lines — completed 2026-05-31 00:06
- Session 2.4: DB-backed module access guard, participant module endpoints, generated module API client, typed module views — completed 2026-05-30 12:24
- Session 2.3: admin flows, role guard, Supabase Admin client, generated API client — completed 2026-05-30 00:32

## In progress
- None.

## Next up
- Session 4.2 spec to be provided by the developer.

## Known issues / blockers
- Hosted Postgres extension bootstrap is not covered by the local Docker init script; handle `vector` and `pgcrypto` explicitly before first hosted deployment.
- The backend test suite still reports the existing `httpx` ASGI shortcut deprecation warning.
- `canPublish` is role-derived until a future membership capability column is introduced.
- Real Supabase Storage writes, signed read URLs, and transcript raw-object writes are behind `StorageProvider` but not live-tested against Supabase; automated tests use fake storage.
- Replace/upload cleanup failure can leave orphaned private objects until a future reconciliation job exists.
- Already-issued signed read URLs remain usable until expiry; unpublish blocks future minting, not issued bearer URLs.
- Raw transcript files are private and not exposed; future summary/transcript surfaces must continue to avoid exposing raw storage keys.
