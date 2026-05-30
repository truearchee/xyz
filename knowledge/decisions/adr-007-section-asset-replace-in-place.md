---
type: adr
stage: 03
status: accepted
created: 2026-05-30
updated: 2026-05-30 19:24
related-session: knowledge/specs/stage-03/3.1-file-upload.md
---

# ADR-007 - Section Asset Replace In Place

## Linked documents
- Spec: [[specs/stage-03/3.1-file-upload]]
- Plan: [[plans/stage-03/3.1-file-upload]]
- Report: [[steps/stage-03/3.1-file-upload]]
- Architecture: [[architecture/storage]]

## Decision
Replacing an uploaded PDF updates the same `section_assets` row and preserves the asset ID.

## Rationale
MVP replacement needs stable identity and simple current-object provenance, not version history or lineage.

## Consequences
Replace updates `storage_key`, file metadata, checksum, `uploaded_by_user_id`, and `updated_at`. It does not create `replaced_at`, `replaced_by_asset_id`, status flags, or historical rows.
