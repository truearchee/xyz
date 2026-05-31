---
type: adr
stage: 03
status: accepted
created: 2026-05-31
updated: 2026-05-31 18:45
related-session: knowledge/specs/stage-03/3.3-student-visibility.md
---

# ADR-013 - Signed Read URL Download Authz

## Linked documents
- Spec: [[specs/stage-03/3.3-student-visibility]]
- Plan: [[plans/stage-03/3.3-student-visibility]]
- Report: [[steps/stage-03/3.3-student-visibility]]
- Architecture: [[architecture/storage]]
- Decision: [[decisions/adr-008-private-section-asset-bucket]]

## Decision
Asset downloads are authorized through a role-aware download URL endpoint that re-validates the section/module/asset state at mint time and then calls `StorageProvider.create_signed_read_url`.

Signed read URLs use `SIGNED_READ_URL_TTL_SECONDS`, defaulting to `300`, are minted fresh per request, are never persisted, and are returned with `Cache-Control: no-store`.

## Rationale
The private bucket posture remains intact while allowing students and lecturers to open files without proxying bytes through the API. Re-validation at mint time means publishing changes affect future URL creation immediately.

## Consequences
Already-issued signed URLs remain bearer capabilities until their provider TTL expires. Unpublishing a section blocks future minting but does not revoke URLs that have already been handed out. Instant revocation would require download proxying, object rotation, or provider-specific revocation controls, all out of scope for the MVP.
