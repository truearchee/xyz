---
type: adr
stage: 04
status: accepted
created: 2026-06-01
updated: 2026-06-01 15:03
related-session: knowledge/specs/stage-04/4.2-transcript-parse-segments.md
---

# ADR-017 - Ingestion Job Worker Spine

## Linked documents
- Spec: [[specs/stage-04/4.2-transcript-parse-segments]]
- Plan: [[plans/stage-04/4.2-transcript-parse-segments]]
- Report: [[steps/stage-04/4.2-transcript-parse-segments]]
- Architecture: [[architecture/worker]]
- Architecture: [[architecture/db-spine]]
- Decision: [[decisions/adr-018-transcript-segment-timestamps]]
- Decision: [[decisions/adr-019-transcript-parse-strategy]]

## Decision
Introduce `ingestion_jobs` in Session 4.2, the first worker session, and use it as the correctness surface for at-least-once RQ delivery.

Only the `parse` handler is wired now, but the table accepts the future `chunk`, `embed`, `generate_brief_summary`, and `generate_detailed_summary` job types so later sessions do not need another ledger migration.

Successful parse leaves `transcripts.status='parsing'`. Parse completion is represented by the `ingestion_jobs` row where `job_type='parse'` and `status='completed'`.

## Rationale
The job ledger belongs with the first worker, not with a later retry session, because parse already needs idempotency, attempts, sanitized failure recording, and future stale-running recovery anchors.

RQ's delivery model is not the source of truth. The database idempotency key, row lock, and claimed-attempt guard decide whether work may proceed.

## Consequences
Session 4.6 can add recovery and retry behavior without changing parse output semantics. Until then, stuck `uploaded` and `running` states are accepted known gaps.
