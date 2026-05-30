---
type: architecture
stage: 02
created: 2026-05-29
updated: 2026-05-30
related-session: knowledge/specs/stage-02/2.2-supabase-auth-current-user-context.md
---

# Auth Current User Context Architecture

## Linked documents
- Spec: [[specs/stage-02/2.2-supabase-auth-current-user-context]]
- Plan: [[plans/stage-02/2.2-supabase-auth-current-user-context]]
- Report: [[steps/stage-02/2.2-supabase-auth-current-user-context]]
- Spec: [[specs/stage-02/2.3-admin-flows]]
- Plan: [[plans/stage-02/2.3-admin-flows]]
- Report: [[steps/stage-02/2.3-admin-flows]]
- Architecture: [[architecture/db-spine]]

## Current structure
The backend auth boundary is `backend/app/platform/auth/`. JWT parsing and verification live in `jwt.py`, request identity resolution lives in `dependencies.py`, role guards live in `guards.py`, and immutable request identity types live in `context.py`.

## JWT verification
Supabase Auth is trusted only for provider identity. The backend verifies asymmetric Supabase JWTs locally with `PyJWT[crypto]` and `jwt.PyJWKClient`, using `SUPABASE_JWKS_URL` to fetch and cache public signing keys. Tokens must validate signature, expiry, audience, issuer, and required `sub`, `exp`, and `role` claims.

The legacy shared-secret HS256 path is intentionally not implemented because the project has migrated to Supabase asymmetric signing keys.

## Request identity
`get_current_user` is the FastAPI dependency for authenticated routes. It validates an exact `Authorization: Bearer <token>` header, decodes the token, loads `app_users` by `auth_provider_id = sub`, rejects inactive users, and loads only active `course_memberships` joined to `course_modules`.

`CurrentUserContext` is frozen and database-authoritative. App role, email, full name, timezone, active state, membership roles, ownership, and publish capability come from the app database, not JWT metadata.

## Route boundary
Authenticated routes consume `Depends(get_current_user)` and do not parse JWTs or query app users directly. Role-gated routes consume `Depends(require_role(...))`; this wraps `get_current_user`, returns the same `CurrentUserContext`, and raises `403 "Insufficient permissions"` when the app-owned role is not allowed.

`GET /health/authed` remains an auth smoke endpoint using `get_current_user`. Admin routes use `require_role("admin")` as their only identity dependency, so handlers do not double-resolve identity or inline role checks.
