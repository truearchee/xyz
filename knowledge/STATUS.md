# Status

_Last updated: 2026-05-31 14:36 — Session 3.2 accepted after Docker verification_

## Current focus
Session 3.2 (Publish / Unpublish + Lecturer Notes) is accepted/done. Docker verification passed for migrations, targeted content tests, the full backend suite, OpenAPI client generation, frontend type-checking, and `git diff --check`.

## Done recently
- Session 3.2: publish/unpublish and lecturer notes accepted after Docker verification; backend `69 passed`, content `17 passed`, frontend type-check passed, and ADRs 009-011 captured the locked decisions — completed 2026-05-31 14:36
- Session 3.1: file upload/list/replace accepted after Docker verification; backend `65 passed`, content `13 passed`, frontend type-check passed, and codegen now trims generated TypeScript trailing blank EOF lines — completed 2026-05-31 00:06
- Session 3.1 completion patch: implemented targeted review fixes; local frontend type-check and Python syntax checks passed, Docker backend verification pending — 2026-05-30 23:42
- Session 2.4: DB-backed module access guard, participant module endpoints, generated module API client, typed module views — completed 2026-05-30 12:24
- Session 2.3: admin flows, role guard, Supabase Admin client, generated API client — completed 2026-05-30 00:32
- Session 2.2: JWKS-backed Supabase JWT verification and identity-only `CurrentUserContext` — completed 2026-05-29; refined 2026-05-30

## In progress
- None.

## Next up
- Session 3.3 (student read visibility and signed read URL authorization; developer to provide spec).

## Known issues / blockers
- Hosted Postgres extension bootstrap is not covered by the local Docker init script; handle `vector` and `pgcrypto` explicitly before first hosted deployment.
- The backend test suite still reports the existing `httpx` ASGI shortcut deprecation warning.
- `canPublish` is role-derived until a future membership capability column is introduced.
- Real Supabase Storage writes are behind `StorageProvider` but not live-tested; automated tests use fake storage.
- Replace cleanup failure can leave orphaned private objects until a future reconciliation job exists.
- Published sections are not student-readable until Session 3.3 adds the student visibility path.
