---
type: adr
stage: 03
status: accepted
created: 2026-05-31
updated: 2026-05-31 18:45
related-session: knowledge/specs/stage-03/3.3-student-visibility.md
---

# ADR-014 - Shared Role-Aware Content Endpoints

## Linked documents
- Spec: [[specs/stage-03/3.3-student-visibility]]
- Plan: [[plans/stage-03/3.3-student-visibility]]
- Report: [[steps/stage-03/3.3-student-visibility]]
- Architecture: [[architecture/auth-current-user-context]]

## Decision
Content read and download routes stay under the shared `/modules/{moduleId}/sections...` route family. The router consumes `require_module_access(moduleId)`, and the service selects lecturer or student projections from `ModuleAccessContext.global_role`.

The section list endpoint returns one shared `SectionListItem` DTO for both roles, without `publishStatus`.

## Rationale
Shared endpoints keep module access behavior consistent and avoid route forks that would duplicate authorization semantics. A single list DTO also keeps the generated frontend client simple while allowing richer lecturer-only state to remain on detail and write responses.

## Consequences
There are no `/student/...` or `/lecturer/...` content route prefixes. Student and lecturer list rows may differ by visibility, but they share the same response shape.
