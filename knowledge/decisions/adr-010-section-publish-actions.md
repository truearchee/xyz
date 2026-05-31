---
type: adr
stage: 03
status: accepted
created: 2026-05-31
updated: 2026-05-31 14:36
related-session: knowledge/specs/stage-03/3.2-publish-and-notes.md
---

# ADR-010 - Section Publish Actions

## Linked documents
- Spec: [[specs/stage-03/3.2-publish-and-notes]]
- Plan: [[plans/stage-03/3.2-publish-and-notes]]
- Report: [[steps/stage-03/3.2-publish-and-notes]]

## Decision
Section lifecycle writes use action endpoints: `POST /publish`, `POST /unpublish`, and `PATCH /notes`. Clients cannot submit arbitrary `publish_status` values.

## Rationale
The action endpoints encode intent and keep the legal transition table in the backend service layer. `draft` remains initial-only, `draft -> unpublish` returns `SECTION_TRANSITION_INVALID`, and same-state publish/unpublish returns 200 without mutating ORM fields or bumping `updatedAt`.

## Consequences
The frontend renders the canonical state returned by the backend. Future lifecycle changes must update the service transition table and tests rather than adding client-side state rules.
