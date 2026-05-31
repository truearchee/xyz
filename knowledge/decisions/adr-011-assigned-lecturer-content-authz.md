---
type: adr
stage: 03
status: accepted
created: 2026-05-31
updated: 2026-05-31 14:36
related-session: knowledge/specs/stage-03/3.2-publish-and-notes.md
---

# ADR-011 - Assigned Lecturer Content Authz

## Linked documents
- Spec: [[specs/stage-03/3.2-publish-and-notes]]
- Plan: [[plans/stage-03/3.2-publish-and-notes]]
- Report: [[steps/stage-03/3.2-publish-and-notes]]
- Architecture: [[architecture/auth-current-user-context]]

## Decision
Any active lecturer assigned to the section's module may publish, unpublish, and edit shared lecturer notes in the MVP.

## Rationale
The current membership model does not distinguish co-teachers, assistants, upload-only lecturers, or note-only lecturers. Adding a capability gate now would be speculative and could contradict the locked MVP contract.

## Consequences
Authorization remains active app user, global role `lecturer`, active lecturer membership, active module, and section/module coherence. Future capability differentiation should add explicit membership capability fields and update both publish and notes authz separately.
