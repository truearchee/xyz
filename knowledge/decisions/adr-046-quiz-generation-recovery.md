---
type: adr
stage: "5"
status: accepted
created: 2026-06-16
updated: 2026-06-16
related-session: knowledge/specs/stage-05/5b-quiz-generation-recovery.md
---

# ADR-046 — Quiz generation recovery: enqueue-after-commit, worker handler, liveness-not-age reaper

> Stage 5 spec ADR label "(F)" recovery half (the one-active/attempt-number lifecycle invariants are the
> 5a schema, ADR-040-adjacent). Repo slot adr-046.

## Linked documents
- Stage spec: [[specs/stage-05/5-shared-quiz-engine-event-spine]]
- Spec: [[specs/stage-05/5b-quiz-generation-recovery]]
- Report: [[steps/stage-05/5b-quiz-generation-recovery]]
- Related: [[adr-043-lazy-per-attempt-quiz-generation]], [[adr-032-stuck-row-reaper-singleton]]

## Context
A `generating` QuizAttempt must never strand. Failures arrive three ways: the enqueue throws after the
creating commit; the worker's generation fails (provider/validator); or the worker (and its job) is
lost entirely. The QuizAttempt is its OWN status tracker (no IngestionJob), so it is the recovery
target. Because persist+provenance+flip is one transaction (5a/lock 5), `status == 'generating'`
provably means "no questions persisted" — the fence and reaper are unambiguous.

## Decision
Three recovery paths, no in-place retry of a terminally-failed attempt (Start Over makes a new one):
- **Enqueue-after-commit + compensation.** `start_quiz_attempt` commits the `generating` attempt, THEN
  enqueues `quiz-generate:{attemptId}` (a rollback can never leave a phantom job) and stamps that stable
  job id onto `QuizAttempt.generation_job_id`. If the enqueue throws, a compensating transaction marks
  the attempt `failed`/`enqueue_failed`.
- **Worker failure handler.** The job maps a GatewayError to `failed`/`invalid_output` or
  `failed`/`provider_error` and (for the RQ-retryable transient categories) re-raises so RQ retries; the
  claim re-activates a transiently-`failed` attempt back to `generating` and re-runs. Non-retryable →
  terminal. `crashed`/`enqueue_failed` are never re-activated.
- **Liveness-not-age reaper (4.6c extension).** A 4th singleton-locked action reaps `generating`
  attempts whose RQ job (`quiz-generate:{id}`) is `live is False` (absent from every registry) →
  `failed`/`crashed`. A job still queued/running behind a backed-up AI queue (`True`) or unknown (a
  Redis hiccup, `None`) is NEVER reaped — only LOST jobs, never age. On `crashed` it ALSO finalizes the
  linked AIRequestLog (`failed`/`abandoned_crashed`) so the cost dashboard (rule 6) leaks no dangling
  `running` row.

## Consequences
No stuck `generating`; the cohort-burst queue is respected (not reaped); the cost log is finalized.
Verified: enqueue-failure compensation, worker-handler failure (invalid_output + provider_error),
per-request inject→clear→succeed re-activation, reaper-reaps-lost + finalizes-log, reaper-skips-live/
unknown. **Residual (logged):** a crash DURING the gateway HTTP call (before `complete()` returns)
leaves a `running` AIRequestLog with no attempt linkage — the same pre-existing summary behavior; fully
closing it needs an AIRequestLog→source reference. **Owner: Stage 8** (the assistant gateway calls have
no IngestionJob either and will drive the AIRequestLog→source linkage that closes this for both quiz and
assistant). Do NOT patch it in 5c — that would be scope creep into infrastructure Stage 8 redesigns.
Tracked in open-questions (#5b).
