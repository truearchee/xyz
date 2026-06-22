# ADR-056 — Stage 11 Scheduler + Deterministic Risk Contract

Date: 2026-06-20

## Status
Accepted

## Context
Stage 11 needs scheduled daily and pre-deadline computation, but existing RQ workers only execute queued jobs.
The stage also introduces risk visibility for lecturers and students while preserving the hard rule that AI
explains deterministic output only and never calculates risk or grades.

## Decision
- Add a shared `platform/scheduler` Python service/container rather than adding `rq-scheduler`.
- The scheduler is single-instance through a Postgres advisory lock and only enqueues jobs onto existing RQ
  queues. Heavy work runs in workers.
- Every scheduler/manual execution is recorded as an `AgentRun` with an idempotency key:
  `triggerType + scopeType + scopeId + scheduledFor + algorithmVersion`.
- Stage 11.1 risk uses `algorithmVersion="risk-v1"` with config-backed thresholds. A threshold change requires
  an algorithm-version bump.
- UI reads compute current risk live. `StudentRiskSnapshot` rows are retained as run history/proactive-layer
  evidence with `algorithmVersion`, `inputHash`, and `sourceCutoffAt`.
- Risk inputs are restricted to already-shipped domains: quiz attempts/answers, `StudentActivityEvent`, schedule
  metadata, and Stage 9 progress/forecast data. Stage 10 gamification data is not read.
- AI is not involved in 11.1. Later recommendation/advice phrasing layers may explain the deterministic output
  through the LLM gateway, but they may not calculate or override the risk tier.

## Consequences
- Deployments must run exactly one scheduler service instance or rely on the advisory lock to skip duplicates.
- The manual trigger is safe for E2E proof because duplicate keys do not create duplicate runs or snapshots.
- Historical risk explanations remain auditable even after live risk changes, because each snapshot pins its
  input hash and cutoff time.

## Linked documents
- Spec: [[specs/stage-11/11.1-roster-risk-scheduler]]
- Plan: [[plans/stage-11/11.1-roster-risk-scheduler]]
- Report: [[steps/stage-11/11.1-roster-risk-scheduler]]
- Master spec: [[specs/stage-11/11-proactive-ai-agent-analytics]]
