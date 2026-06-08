---
type: adr
stage: "4.3.5"
status: accepted
created: 2026-06-08
updated: 2026-06-08
related-session: knowledge/specs/stage-04/4.3.5e-stage4-transcript-ui-backfill.md
---

# ADR-024 - Stage 4.3 Post-Chunk Terminal Status

## Linked documents
- Spec: [[specs/stage-04/4.3.5e-stage4-transcript-ui-backfill]]
- Plan: [[plans/stage-04/4.3.5e-stage4-transcript-ui-plan]]
- Findings: [[findings-4.3.5e]]
- Recovery plan: [[specs/recovery/client-edge-recovery-plan]]

## Context
Session 4.3.5e must let the browser observe a real worker-driven terminal state for the already-implemented Stage 4.1-4.3 transcript pipeline.

Before this decision, the backend completed parse and chunk jobs, persisted transcript segments and chunks, and recorded chunk job metadata, but left `Transcript.status` at `chunking`. A browser gate cannot treat `chunking` as terminal because the name describes an in-progress worker state.

Stage 4.4 embeddings and Stage 4.5 summaries are not implemented in this repair.

## Decision
For Stage 4.1-4.3, successful chunk completion sets `Transcript.status` to `completed`.

No new `chunked` status is added.

No embedding jobs, summary jobs, AI infrastructure, retry behavior, replacement behavior, product endpoints, or raw transcript/chunk exposure are added by this decision.

## Rationale
- `chunking` is non-terminal.
- `completed` already exists in the transcript status contract and database constraint.
- Adding a new `chunked` status would create unnecessary enum/API churn.
- Stage 4.4 can later extend the pipeline by transitioning to embedding/generating states when those stages are implemented.
- The client recovery browser gate needs a clear status to poll without pretending an in-progress label is success.

## Consequences
- 4.3.5e UI can poll until `completed`.
- Backend worker tests must prove chunk job completion sets transcript status to `completed`.
- Stage 4.4 must revisit the downstream transition when embedding jobs are introduced.
- `completed` currently means Stage 4.1-4.3 transcript upload, parse, and chunk completion, not embedding or summary completion.
