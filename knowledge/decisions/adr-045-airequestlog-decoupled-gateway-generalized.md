---
type: adr
stage: "5"
status: accepted
created: 2026-06-16
updated: 2026-06-16
related-session: knowledge/specs/stage-05/5b-quiz-generation-recovery.md
---

# ADR-045 — AIRequestLog decoupled from IngestionJob; the 4.5 gateway generalized by addition

> New decision surfaced in 5b (not in the original A–F list). Repo slot adr-045. Resolves the long-open
> question "AIRequestLog.ingestion_job_id NOT NULL … Stage 8 will need it nullable."

## Linked documents
- Stage spec: [[specs/stage-05/5-shared-quiz-engine-event-spine]]
- Spec: [[specs/stage-05/5b-quiz-generation-recovery]]
- Report: [[steps/stage-05/5b-quiz-generation-recovery]]
- Related: [[adr-044-structured-quiz-output-json-validator-authority]]

## Context
Rule 6 requires an AIRequestLog row BEFORE every gateway call. But `ai_request_logs.ingestion_job_id`
was NOT NULL (every 4.5 caller was a transcript-summary job), and quiz generation (Stage 5) — like the
assistant (Stage 8) — makes gateway calls with NO IngestionJob. The gateway's `complete()`,
`ContextRefs`, `open_request_log`, `feature` enum, and `output_schema` union were all summary-specific.
A parallel quiz gateway path would duplicate the limiter, the AIRequestLog write, provenance stamping,
and validation — reintroducing exactly the bypass the single gateway exists to prevent.

## Decision
- **Migration 0020:** `ai_request_logs.ingestion_job_id` → NULLABLE (a general "AI calls aren't always
  transcript-ingestion jobs" decoupling, documented in a column COMMENT so Stage 8 doesn't re-litigate
  it). The `feature` CHECK is widened but stays an EXPLICIT enumerated set (`summary_brief`,
  `summary_detailed`, `post_class_quiz`) — each consuming feature adds its value deliberately.
- **Generalize the shared gateway by ADDITION, not mutation:** `GatewayFeature` adds `post_class_quiz`
  (summary members byte-for-byte unchanged; `SummaryFeature` kept as an alias); `ContextRefs.
  ingestion_job_id` and `open_request_log` become optional; `output_schema`/`CompletionResult` gain
  `PostClassQuiz`. One gateway, all calls inside the chain.
- **The summary contract is preserved at the application layer.** The column is nullable platform-wide,
  but `complete()` raises before opening a log if a feature in `FEATURES_REQUIRING_INGESTION_JOB`
  (the two summary features) is called with `ingestion_job_id=None`. Optionality is a property of the
  quiz/assistant features, NOT a hole in the summary contract — and it is VALIDATED
  (`test_summary_feature_still_requires_ingestion_job_id`), not assumed.

## Consequences
Quiz and (later) assistant calls log through the same rule-6/rule-15 chain; no second code path can
bypass the limiter/log/validator. The summary path is unchanged and proven (full suite 422 green, no
regression). Stage 8 inherits the nullable column. Migration 0020 extends this branch's block to
0013→0020 (collision-reconciled at merge — see open-questions #5a).
