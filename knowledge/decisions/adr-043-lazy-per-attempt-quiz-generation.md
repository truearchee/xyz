---
type: adr
stage: "5"
status: accepted
created: 2026-06-16
updated: 2026-06-16
related-session: knowledge/specs/stage-05/5b-quiz-generation-recovery.md
---

# ADR-043 — Lazy, per-attempt quiz generation (one AI call per attempt)

> Stage 5 spec ADR label "(A)". Remapped to repo slot adr-043.

## Linked documents
- Stage spec: [[specs/stage-05/5-shared-quiz-engine-event-spine]]
- Spec: [[specs/stage-05/5b-quiz-generation-recovery]]
- Report: [[steps/stage-05/5b-quiz-generation-recovery]]
- Related: [[adr-042-quiz-availability-computed-read-only]], [[adr-046-quiz-generation-recovery]]

## Context
A post-class quiz could be pre-generated (a marker quiz materialized when the summary completes) or
generated lazily at Start. Pre-generation spends Nvidia-route calls on quizzes nobody takes and creates
a stored artifact to keep in sync with supersession. The reasoning route is the platform's tightest
budget (10 RPM) and post-class is the burstiest trigger (a cohort hitting one lecture).

## Decision
Questions are generated **at Start, per attempt** — never ahead of time. `start_quiz_attempt` creates a
`generating` QuizAttempt and enqueues `quiz-generate:{attemptId}`; the job makes ONE gateway call (rule
15) producing all 10 questions. A brief "generating" poll precedes Q1. The limiter queue + the
"generating" state absorb the cohort burst; the reaper does not kill queued jobs (ADR-046). The route
is a config knob (the gateway abstracts it); re-routing is an ADR, not a code change. The heavier
recap/exam-prep burst math is Stage 6's capacity ADR.

## Consequences
No wasted calls on untaken quizzes; no stored-quiz↔supersession sync problem (the attempt snapshots the
summary it was built from). The cost is a visible generating state — accepted for MVP. Verified by the
deterministic end-to-end generation tests.
