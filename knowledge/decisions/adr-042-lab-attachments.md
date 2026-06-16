# ADR-042 — Lab attachments and asset kind boundary (Stage 5.5c)

- **Status:** Accepted (2026-06-16)
- **Stage:** 5.5c
- **Related:** [[specs/stage-05/5.5-module-schedule-section-metadata]] (D5, D11, D12, Sub-scope C),
  [[steps/stage-05/5.5c-lab-attachments]]

## Context
Lab sections need to carry non-PDF teaching materials such as notebooks. Those files must be downloadable
by students, but they are not transcript sources and must not enter the parse/chunk/embed/summary
pipeline. Existing PDF section assets already behave as inert completed assets, but the schema did not
make that intent explicit.

Signed read URLs are still the right path for PDFs, but they cannot guarantee every response header the
attachment policy needs. In particular, the backend cannot attach `X-Content-Type-Options: nosniff` to a
provider-signed URL.

## Decision
1. **Add `section_assets.asset_kind`.** Values are `processable` and `attachment`. The default is
   `processable`, and migration `0021` backfills every existing row to `processable`.
2. **Keep PDFs processable-but-inert in Stage 5.5.** `processable` means eligible for a future section
   material pipeline; it does not mean transcript ingestion today.
3. **Treat notebooks as attachments.** `.ipynb` uploads are accepted only after extension,
   content-type, size, and JSON notebook-shape validation. The backend never executes or renders them.
4. **Restrict attachment uploads to lab sections.** Existing PDF uploads remain allowed through the
   section asset flow; upload-time `dueAt` uses the same lab-only rule as metadata editing.
5. **Serve attachments through the backend.** `asset_kind='attachment'` files use the backend streaming
   endpoint, which reuses the existing download authorization, reads through `StorageProvider.get_object`,
   and sets `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`, and
   `Cache-Control: no-store`.
6. **Keep signed URLs PDF-only.** The signed URL endpoint rejects attachments so clients cannot bypass
   the download-only headers.
7. **Prove no pipeline structurally.** The acceptance test uploads an attachment through the backend and
   asserts zero rows for `transcripts`, `ingestion_jobs`, `transcript_segments`, `transcript_chunks`, and
   `generated_lecture_summaries` for that section.

## Consequences
- Future work can make a new format processable, but that is a new pipeline source and needs its own
  design/ADR.
- Student UI in 5.5e must choose the download path by `assetKind`: processable PDFs keep
  `download-url`; attachments use the backend streaming endpoint.
- Stage 6 quiz scope remains insulated from lab attachments because attachments produce no transcript or
  summary rows.

## Alternatives rejected
- **Serve attachments via signed URL.** Rejected because the signed URL response cannot carry the
  required `nosniff` header.
- **Represent notebooks as transcripts.** Rejected because notebooks are lab materials, not lecture
  transcript sources, and executing/rendering them is out of scope.
- **Infer attachment behavior from MIME type alone.** Rejected because the durable boundary needs to be
  stored and testable in the database.
