---
type: adr
stage: 03
status: accepted
created: 2026-05-31
updated: 2026-05-31 14:36
related-session: knowledge/specs/stage-03/3.2-publish-and-notes.md
---

# ADR-009 - Publish Without Content Gate

## Linked documents
- Spec: [[specs/stage-03/3.2-publish-and-notes]]
- Plan: [[plans/stage-03/3.2-publish-and-notes]]
- Report: [[steps/stage-03/3.2-publish-and-notes]]

## Decision
Publishing a section is a visibility-state transition and does not require uploaded assets or lecturer notes. Session 3.2 does not add `published_at` or publish-history fields.

## Rationale
Stage 3 separates lecturer content lifecycle from student read visibility. An empty published section is harmless until Session 3.3 renders student-facing content, and adding audit fields now would imply lifecycle history the MVP does not yet model.

## Consequences
The system cannot answer "when was this first published?" until a future content lifecycle or audit feature exists. The Stage 5 student-activity event spine does not backfill lecturer publish history.
