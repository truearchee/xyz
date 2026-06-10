---
type: adr
stage: "4.3.5"
status: accepted
created: 2026-06-05
updated: 2026-06-05
related-session: knowledge/specs/stage-04/4.3.5c-stage2-admin-ui-backfill.md
---

# ADR-023 - Stage 2 Admin Module Membership Projection

## Linked documents
- Spec: [[specs/stage-04/4.3.5c-stage2-admin-ui-backfill]]
- Plan: [[plans/stage-04/4.3.5c-stage2-admin-ui-backfill]]
- Report: [[4.3.5c-admin-ui-final-report]]
- Findings: [[4.3.5c-admin-ui-final-report]]
- Recovery plan: [[specs/recovery/client-edge-recovery-plan]]

## Context
Session 4.3.5c must prove Stage 2 admin flows through real browser UI. The admin assign/remove workflow cannot be real or verifiable unless the UI can display current module members before offering a removal action.

The existing admin API has create user, list user, create module, list module, assign member, and remove member endpoints, but it does not expose a read projection for active members of a specific module.

## Decision
Add a narrow read-only admin endpoint:

```http
GET /admin/modules/{module_id}/members
```

The response lists active non-admin module memberships joined with user display fields:

```ts
ModuleMemberResponse {
  membershipId: string
  userId: string
  moduleId: string
  email: string
  fullName: string
  role: "lecturer" | "student"
  membershipStatus: "active"
  userIsActive: boolean
  createdAt: string
}
```

Inactive users with active memberships are included with `userIsActive=false` so admins can see and remove stale active memberships. Archived memberships and admin users are not returned. Results are sorted by role ascending, then email ascending.

## Rationale
- The projection is required for real assign/remove UI because removal must be driven from a visible current member list, not guessed local state or direct API calls.
- The endpoint is read-only because existing write endpoints already own assignment and archival behavior.
- No migration is needed because the projection reads existing `app_users`, `course_modules`, and `course_memberships` tables.
- The Client Edge Recovery plan allows required read/status projections when needed to make UI proof real. This endpoint is that projection and is approved for Option A.
- Write-path behavior remains unchanged to preserve the already-completed Session 2.3 admin-flow contract and avoid broad backend drift.

## Consequences
- The generated frontend client changes after OpenAPI regeneration.
- Admin UI can render real module members before removal.
- Backend tests must prove the projection remains admin-only, excludes archived/admin memberships, includes inactive users with active memberships, and sorts deterministically.
- Any future richer membership-management workflow should build on this read contract or supersede it through a new approved session.
