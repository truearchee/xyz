---
type: adr
stage: 03
status: accepted
created: 2026-05-30
updated: 2026-05-30 19:24
related-session: knowledge/specs/stage-03/3.1-file-upload.md
---

# ADR-006 - Section Assets Allow Multiple Files

## Linked documents
- Spec: [[specs/stage-03/3.1-file-upload]]
- Plan: [[plans/stage-03/3.1-file-upload]]
- Report: [[steps/stage-03/3.1-file-upload]]
- Architecture: [[architecture/db-spine]]

## Decision
A module section can have multiple uploaded assets.

## Rationale
The MVP allows multiple PDFs per section and does not define asset slots.

## Consequences
`section_assets.module_section_id` is indexed but not unique. Any future slot model requires an explicit new field and product decision.
