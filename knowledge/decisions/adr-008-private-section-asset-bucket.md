---
type: adr
stage: 03
status: accepted
created: 2026-05-30
updated: 2026-05-30 19:24
related-session: knowledge/specs/stage-03/3.1-file-upload.md
---

# ADR-008 - Section Asset Bucket Is Private

## Linked documents
- Spec: [[specs/stage-03/3.1-file-upload]]
- Plan: [[plans/stage-03/3.1-file-upload]]
- Report: [[steps/stage-03/3.1-file-upload]]
- Architecture: [[architecture/storage]]

## Decision
Section asset objects are written to a private storage bucket.

## Rationale
Student visibility and signed URL authorization are Stage 3 concerns that depend on backend authorization, not public object URLs.

## Consequences
Session 3.1 shapes `StorageProvider.create_signed_read_url` for later use, but no student-facing signed URL endpoint is exposed until Session 3.3.
