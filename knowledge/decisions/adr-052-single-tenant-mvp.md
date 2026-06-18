---
type: adr
status: accepted
created: 2026-06-18
updated: 2026-06-18
---

# ADR-052 — Single-Tenant MVP

## Context
Stage 9 introduces progress and grade tables. Stage 8, running in parallel, introduces assistant tables. The roadmap requires an institution/organization-model decision before these table waves land.

## Decision
The MVP is single-tenant. New Stage 9 tables do not carry `organization_id`.

Access is scoped by existing user, membership, module, section, and current-student boundaries. If multi-institution support becomes a product requirement, it will be a post-MVP schema and authorization project with its own ADR and migrations.

## Consequences
- Stage 9 tables use existing `app_users`, `course_modules`, `course_memberships`, and `module_sections` relationships.
- Stage 9 progress APIs remain current-user-only and never expose cross-tenant abstractions.
- Parallel Stage 8 tables should match the same single-tenant assumption.
- Retrofitting tenancy later is acknowledged as a real migration project, not an accidental omission.

## Linked documents
- Stage 9 spec: [[specs/stage-09/9-my-progress-dashboard]]
- Stage 9 plan: [[plans/stage-09/9-my-progress-dashboard]]
- Roadmap: [[roadmap]]
