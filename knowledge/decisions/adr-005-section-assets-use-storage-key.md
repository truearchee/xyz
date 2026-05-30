---
type: adr
stage: 03
status: accepted
created: 2026-05-30
updated: 2026-05-30 19:24
related-session: knowledge/specs/stage-03/3.1-file-upload.md
---

# ADR-005 - Section Assets Use Storage Key

## Linked documents
- Spec: [[specs/stage-03/3.1-file-upload]]
- Plan: [[plans/stage-03/3.1-file-upload]]
- Report: [[steps/stage-03/3.1-file-upload]]
- Architecture: [[architecture/db-spine]]
- Architecture: [[architecture/storage]]

## Decision
The asset table uses `storage_key`, not `file_url`.

## Rationale
Section assets live in a private bucket. The stored value is a private object path, not a public URL and not a signed read URL.

## Consequences
The API never exposes `storage_key`. Session 3.3 will add authorized signed-read behavior without changing the stored reference shape.
