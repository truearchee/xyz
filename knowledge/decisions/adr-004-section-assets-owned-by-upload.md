---
type: adr
stage: 03
status: accepted
created: 2026-05-30
updated: 2026-05-30 19:24
related-session: knowledge/specs/stage-03/3.1-file-upload.md
---

# ADR-004 - Section Assets Are Owned By Upload

## Linked documents
- Spec: [[specs/stage-03/3.1-file-upload]]
- Plan: [[plans/stage-03/3.1-file-upload]]
- Report: [[steps/stage-03/3.1-file-upload]]
- Architecture: [[architecture/db-spine]]
- Architecture: [[architecture/storage]]

## Decision
The `section_assets` product table belongs to the file-upload feature, not the Stage 2 DB spine.

## Rationale
Stage 2 established identity, modules, memberships, and sections. Session 3.1 is the first session that proves actual object storage and asset metadata behavior, so it finalizes the storage-backed table shape.

## Consequences
The repo already had a Stage 2 placeholder table. Session 3.1 preserves migration history and uses Alembic `0003` to migrate that placeholder into the storage-backed schema instead of rewriting completed history.
