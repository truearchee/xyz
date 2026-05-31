---
type: architecture
stage: 03
created: 2026-05-30
updated: 2026-05-31 18:45
related-session: knowledge/specs/stage-03/3.1-file-upload.md
---

# Storage Architecture

## Linked documents
- Spec: [[specs/stage-03/3.1-file-upload]]
- Plan: [[plans/stage-03/3.1-file-upload]]
- Report: [[steps/stage-03/3.1-file-upload]]
- Spec: [[specs/stage-03/3.3-student-visibility]]
- Plan: [[plans/stage-03/3.3-student-visibility]]
- Report: [[steps/stage-03/3.3-student-visibility]]
- Architecture: [[architecture/db-spine]]
- Decision: [[decisions/adr-004-section-assets-owned-by-upload]]
- Decision: [[decisions/adr-005-section-assets-use-storage-key]]
- Decision: [[decisions/adr-006-section-assets-allow-multiple-files]]
- Decision: [[decisions/adr-007-section-asset-replace-in-place]]
- Decision: [[decisions/adr-008-private-section-asset-bucket]]
- Decision: [[decisions/adr-013-signed-read-url-download-authz]]

## Provider boundary
Storage access goes through `backend/app/platform/storage/base.py`. Domain code depends on the async `StorageProvider` protocol and receives a provider dependency, so upload logic does not import or construct Supabase SDK clients.

## Private bucket posture
Section assets are written to a private Supabase Storage bucket configured by `SUPABASE_STORAGE_BUCKET`. The backend stores only `section_assets.storage_key`; clients receive freshly minted signed read URLs after service-layer authorization.

## Key shape
Section asset keys use:

```text
modules/{moduleId}/sections/{sectionId}/assets/{assetId}/{randomNonce}.pdf
```

The raw filename is never embedded in the key. Display filenames live only in `section_assets.file_name`.

## Signed read URLs
Session 3.3 activates `StorageProvider.create_signed_read_url` for section asset reads. The service re-validates module access, section visibility, section status, and asset processing state on every mint request, then returns an opaque URL with an absolute `expiresAt`.

Signed read URL TTL is configured by `SIGNED_READ_URL_TTL_SECONDS` and defaults to `300`. Responses set `Cache-Control: no-store`; the backend does not persist, cache, or proxy signed URLs.

Already-issued signed URLs remain usable until provider expiry. Unpublish blocks future URL minting, not previously issued bearer URLs.

## Upload compensation
Upload endpoints authorize the current user and section access before parsing multipart form data. After authorization, upload writes to storage first with `overwrite=False`, then inserts the DB row. If DB persistence fails after storage succeeds, the backend attempts an idempotent `delete_object(storage_key)` cleanup and returns a server error.

## Replace compensation
Replace endpoints also authorize section access before parsing multipart form data. Replace validates and uploads a new object first, then locks the existing `section_assets` row for update and swaps metadata in place. If the DB update fails, the new object is cleaned up and the old row/object remain authoritative. After commit, deletion of the old object is best-effort and cleanup failures are logged as orphan risk.
