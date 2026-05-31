# Status

_Last updated: 2026-05-31 19:09 — Session 3.3 final verification closeout passed_

## Current focus
Session 3.3 (Student Visibility) is accepted/done. Final verification closeout reran on 2026-05-31 19:09 and passed for migrations, targeted content tests, the full backend suite, OpenAPI client generation, frontend rebuild/restart, frontend type-checking, and `git diff --check`.

## Done recently
- Session 3.3: student published-section visibility and signed read URL authorization accepted after Docker verification; final closeout rerun passed with backend `72 passed`, content `20 passed`, frontend type-check passed, and `git diff --check` passed — completed 2026-05-31 18:45; reverified 2026-05-31 19:09
- Session 3.2: publish/unpublish and lecturer notes accepted after Docker verification; backend `69 passed`, content `17 passed`, frontend type-check passed, and ADRs 009-011 captured the locked decisions — completed 2026-05-31 14:36
- Session 3.1: file upload/list/replace accepted after Docker verification; backend `65 passed`, content `13 passed`, frontend type-check passed, and codegen now trims generated TypeScript trailing blank EOF lines — completed 2026-05-31 00:06
- Session 2.4: DB-backed module access guard, participant module endpoints, generated module API client, typed module views — completed 2026-05-30 12:24
- Session 2.3: admin flows, role guard, Supabase Admin client, generated API client — completed 2026-05-30 00:32
- Session 2.2: JWKS-backed Supabase JWT verification and identity-only `CurrentUserContext` — completed 2026-05-29; refined 2026-05-30

## In progress
- None.

## Next up
- Stage 4 spec to be provided by the developer.

## Known issues / blockers
- Hosted Postgres extension bootstrap is not covered by the local Docker init script; handle `vector` and `pgcrypto` explicitly before first hosted deployment.
- The backend test suite still reports the existing `httpx` ASGI shortcut deprecation warning.
- `canPublish` is role-derived until a future membership capability column is introduced.
- Real Supabase Storage writes and signed read URLs are behind `StorageProvider` but not live-tested; automated tests use fake storage.
- Replace cleanup failure can leave orphaned private objects until a future reconciliation job exists.
- Already-issued signed read URLs remain usable until expiry; unpublish blocks future minting, not issued bearer URLs.
