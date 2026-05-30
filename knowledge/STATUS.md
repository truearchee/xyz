# Status

_Last updated: 2026-05-30 12:24 — Session 2.4 complete_

## Current focus
Session 2.4 (Module Base Views) complete. The backend exposes participant-facing `/modules` and `/modules/{module_id}` endpoints gated by DB-backed `require_module_access`, and the frontend has typed presentational module list/detail components using the regenerated API DTOs.

## Done recently
- Session 2.4: DB-backed module access guard, participant module endpoints, generated module API client, typed module views — completed 2026-05-30 12:24
- Session 2.3: admin flows, role guard, Supabase Admin client, generated API client — completed 2026-05-30 00:32
- Session 2.2: JWKS-backed Supabase JWT verification and identity-only `CurrentUserContext` — completed 2026-05-29; refined 2026-05-30
- Session 2.1: DB spine schema with UUIDv7 app-generated primary keys and isolated migration tests — completed 2026-05-29

## In progress
- (none)

## Next up
- Session 2.5 (developer to provide spec)

## Known issues / blockers
- Hosted Postgres extension bootstrap is not covered by the local Docker init script; handle `vector` and `pgcrypto` explicitly before first hosted deployment.
- The backend test suite still reports the existing `httpx` ASGI shortcut deprecation warning.
- `canPublish` is role-derived until a future membership capability column is introduced.
