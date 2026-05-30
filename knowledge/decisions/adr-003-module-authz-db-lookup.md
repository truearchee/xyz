---
type: adr
stage: 02
status: accepted
created: 2026-05-30
updated: 2026-05-30 12:24
related-session: knowledge/specs/stage-02/2.4-module-base-views.md
---

# ADR-003 - Module Authorization Uses DB Lookup

## Linked documents
- Spec: [[specs/stage-02/2.4-module-base-views]]
- Plan: [[plans/stage-02/2.4-module-base-views]]
- Report: [[steps/stage-02/2.4-module-base-views]]
- Architecture: [[architecture/auth-current-user-context]]
- Architecture: [[architecture/db-spine]]

## Decision
Module-scoped authorization is resolved from the application database per request through `require_module_access`, not from JWT claims and not from an eager membership list on `CurrentUserContext`.

## Rationale
The application database is the source of truth for module access. A DB lookup gives real-time revocation: archived memberships and inactive modules stop authorizing the next request without token refresh.

## Current schema behavior
- `course_modules.is_active` is the module active flag.
- `course_memberships.status` and `course_memberships.archived_at` track membership archival.
- `course_memberships` enforces partial active uniqueness for `(user_id, module_id)`, allowing historical archived rows plus one active row.
- Reassignment after removal inserts a new active row and preserves archived history.
- There is no membership-level publish capability column in the current schema. For 2.4, `canPublish` is derived from the caller's global role: lecturers can publish; students cannot.

## Authorization conventions
- Identity and user active state stay in `get_current_user`.
- Per-module access is resolved on demand into `ModuleAccessContext`.
- Active access requires an active membership and `course_modules.is_active = true`.
- Non-member, archived membership, inactive module, and cross-tenant requests return `404`.
- `403` is reserved for a known valid member attempting a role-forbidden action.
- `/modules` is participant-facing only. Admin module management remains under `/admin`; any future UI reuse must be presentational reuse, not a backend authorization bypass.

## Deferred options
- A membership-level publish capability column is the preferred long-term shape if read-only lecturer, TA, or guest lecturer roles appear.
- A Redis membership cache is deferred until scale requires it.
