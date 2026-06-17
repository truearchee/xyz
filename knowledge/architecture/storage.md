---
type: architecture
stage: 03
created: 2026-05-30
updated: 2026-06-17
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
- Spec: [[specs/stage-04/4.1-transcript-upload]]
- Plan: [[plans/stage-04/4.1-transcript-upload]]
- Report: [[steps/stage-04/4.1-transcript-upload]]
- Spec: [[specs/stage-04/4.2-transcript-parse-segments]]
- Plan: [[plans/stage-04/4.2-transcript-parse-segments]]
- Report: [[steps/stage-04/4.2-transcript-parse-segments]]
- Architecture: [[architecture/db-spine]]
- Architecture: [[architecture/worker]]
- Decision: [[decisions/adr-004-section-assets-owned-by-upload]]
- Decision: [[decisions/adr-005-section-assets-use-storage-key]]
- Decision: [[decisions/adr-006-section-assets-allow-multiple-files]]
- Decision: [[decisions/adr-007-section-asset-replace-in-place]]
- Decision: [[decisions/adr-008-private-section-asset-bucket]]
- Decision: [[decisions/adr-013-signed-read-url-download-authz]]
- Decision: [[decisions/adr-042-lab-attachments]]
- Decision: [[decisions/adr-043-dev-reseed]]
- Decision: [[decisions/adr-015-transcript-upload-boundary-active-invariant]]
- Decision: [[decisions/adr-016-transcript-file-validation-storage-metadata]]
- Decision: [[decisions/adr-019-transcript-parse-strategy]]
- Decision: [[decisions/adr-022-supabase-public-url-for-signed-urls]]

## Provider boundary
Storage access goes through `backend/app/platform/storage/base.py`. Domain code depends on the async `StorageProvider` protocol and receives a provider dependency, so upload logic does not import or construct Supabase SDK clients.

Session 4.2 adds `get_object(key) -> bytes` to the same provider boundary. Workers read raw transcript bytes through this method; parse jobs do not receive raw bytes in queue payloads and do not call Supabase directly.

## Private bucket posture
Section assets and raw transcript uploads are written to a private Supabase Storage bucket configured by `SUPABASE_STORAGE_BUCKET`. The backend stores private storage keys in database rows. Clients receive freshly minted signed read URLs for authorized processable section PDFs; download-only attachments are streamed by the backend so the response can set attachment headers.

## Key shape
Section asset keys use:

```text
modules/{moduleId}/sections/{sectionId}/assets/{assetId}/{randomNonce}.pdf
```

Stage 5.5c keeps the same shape but uses the validated upload extension, so lab notebook attachments end
in `.ipynb`:

```text
modules/{moduleId}/sections/{sectionId}/assets/{assetId}/{randomNonce}.ipynb
```

The raw filename is never embedded in the key. Display filenames live only in `section_assets.file_name`.

Transcript keys use:

```text
modules/{moduleId}/sections/{sectionId}/transcripts/{transcriptId}/{safeFileName}
```

`transcriptId` provides uniqueness, so no extra nonce is added. The filename segment is sanitized for storage-key safety and does not trust browser path data. Display filenames live in `transcripts.original_file_name`.

## Signed read URLs
Session 3.3 activates `StorageProvider.create_signed_read_url` for section asset reads. The service re-validates module access, section visibility, section status, asset processing state, and `asset_kind` on every mint request, then returns an opaque URL with an absolute `expiresAt`. Stage 5.5c keeps this path PDF-only (`asset_kind='processable'`).

Signed read URL TTL is configured by `SIGNED_READ_URL_TTL_SECONDS` and defaults to `300`. Responses set `Cache-Control: no-store`; the backend does not persist, cache, or proxy signed URLs.

Already-issued signed URLs remain usable until provider expiry. Unpublish blocks future URL minting, not previously issued bearer URLs.

Backend services call Supabase through `SUPABASE_URL`. When local Docker needs an internal URL that browsers cannot open, `SUPABASE_PUBLIC_URL` can be set to a browser-facing origin. The Supabase storage provider rewrites only the signed URL origin from `SUPABASE_URL` to `SUPABASE_PUBLIC_URL`; path, query string, token, and fragment are preserved exactly. If `SUPABASE_PUBLIC_URL` is unset, it defaults to `SUPABASE_URL`.

## Attachment streaming
Stage 5.5c adds `GET /modules/{moduleId}/sections/{sectionId}/assets/{assetId}/download` for
`asset_kind='attachment'`. It reuses the same role/resource checks as signed URL minting, reads bytes
through `StorageProvider.get_object`, and returns `Content-Disposition: attachment`,
`X-Content-Type-Options: nosniff`, and `Cache-Control: no-store`. Attachments are rejected on the
signed-URL endpoint because Supabase signed URLs cannot attach the `nosniff` header.

Stage 5.5d's dev reseed creates one published lab fixture with both paths represented: a processable
PDF for signed URL reads and an attachment `.ipynb` for backend streaming. The fixture is dev data only
and exists to make the 5.5e browser gate deterministic.

## Upload compensation
Upload endpoints authorize the current user and section access before parsing multipart form data. After authorization, upload writes to storage first with `overwrite=False`, then inserts the DB row. If DB persistence fails after storage succeeds, the backend attempts an idempotent `delete_object(storage_key)` cleanup and returns a server error.

Transcript upload also checks for an existing active transcript before multipart parsing. The database partial unique index remains the race guard; if a concurrent upload wins after storage succeeds, the loser object is deleted and the API returns `409`.

## Replace compensation
Replace endpoints also authorize section access before parsing multipart form data. Replace validates and uploads a new object first, then locks the existing `section_assets` row for update and swaps metadata in place. If the DB update fails, the new object is cleaned up and the old row/object remain authoritative. After commit, deletion of the old object is best-effort and cleanup failures are logged as orphan risk.
