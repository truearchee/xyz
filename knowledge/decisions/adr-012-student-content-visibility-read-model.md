---
type: adr
stage: 03
status: accepted
created: 2026-05-31
updated: 2026-05-31 18:45
related-session: knowledge/specs/stage-03/3.3-student-visibility.md
---

# ADR-012 - Student Content Visibility Read Model

## Linked documents
- Spec: [[specs/stage-03/3.3-student-visibility]]
- Plan: [[plans/stage-03/3.3-student-visibility]]
- Report: [[steps/stage-03/3.3-student-visibility]]
- Decision: [[decisions/adr-009-publish-without-content-gate]]

## Decision
Student section reads use a dedicated read model that returns only sections where `publish_status = 'published'` and `status = 'active'`. Student asset metadata is returned only for assets where `processing_status = 'completed'`.

Non-visible student content is reported as `404`, not `403`.

## Rationale
The read projection encodes the visibility filter before rows reach the service boundary, which prevents accidental serialization of draft, unpublished, archived, or non-completed content. Returning `404` keeps the existing no-existence-leak discipline for cross-role and cross-module access.

## Consequences
`publish_status` and `processing_status` remain independent axes. Empty published sections remain valid and render as zero-asset sections. `hasAssets` and `hasNotes` are caller-relative list hints, so the student list only claims assets when student detail would return at least one completed asset.
