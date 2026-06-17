---
type: session-spec
stage: "05"
session: "5b"
slug: quiz-generation-recovery
status: done
created: 2026-06-16
updated: 2026-06-16
owner: developer
plan: "knowledge/plans/stage-05/5b-quiz-generation-recovery.md"
report: "knowledge/steps/stage-05/5b-quiz-generation-recovery.md"
---

# Session 5b — Quiz Generation Pipeline + Recovery

## Linked documents
- Stage spec: [[specs/stage-05/5-shared-quiz-engine-event-spine]] (§5b)
- Foundation: [[specs/stage-05/5a-quiz-foundation]]
- Spec: [[specs/stage-05/5b-quiz-generation-recovery]]
- Plan: [[plans/stage-05/5b-quiz-generation-recovery]]
- Report: [[steps/stage-05/5b-quiz-generation-recovery]]
- ADRs: [[decisions/adr-043-lazy-per-attempt-quiz-generation]], [[decisions/adr-044-structured-quiz-output-json-validator-authority]], [[decisions/adr-045-airequestlog-decoupled-gateway-generalized]], [[decisions/adr-046-quiz-generation-recovery]]

## Goal
Ship the lazy, per-attempt post-class quiz generation pipeline (one AI call → 10 MCQs) through the 4.5
gateway, plus stuck-`generating` recovery — proven deterministically end-to-end in CI.

## Why now
Stage 5a landed the schema + event spine (HARD GATE). 5b is the generation layer the UI (5d) and the
answer/scoring endpoints (5c) build on.

## Read first
- `knowledge/specs/stage-05/5-shared-quiz-engine-event-spine.md` §5b + locks 1/4/5/6
- `backend/app/domains/transcripts/summary_service.py` (claim/persist/mark-failed pattern mirrored)
- `backend/app/platform/llm/gateway.py`, `validation.py`, `provider.py`, `registry.py`
- `backend/app/domains/recovery/reaper.py`, `rq_liveness.py`

## Source paths touched
- `backend/alembic/versions/0020_ai_request_log_decouple_ingestion_job.py`
- `backend/app/platform/db/models/ai_request_log.py`
- `backend/app/platform/llm/{gateway,logging,validation,provider}.py`, `models/{prompt,quiz}.py`
- `backend/prompts/post_class_quiz_generation/v1.yaml` + `CHECKSUMS.json`
- `backend/app/domains/quiz/{generation_service,jobs}.py`
- `backend/app/platform/query/quiz_availability_read.py` (added `resolve_quiz_source_summary`)
- `backend/app/workers/queues.py`, `backend/app/domains/recovery/{reaper,rq_liveness}.py`
- `backend/tests/test_quiz_generation.py`

## Build
- Migration 0020: `ai_request_logs.ingestion_job_id` nullable (general decoupling) + widen `feature` CHECK (enumerated) to add `post_class_quiz`.
- Generalize the 4.5 gateway by addition: `GatewayFeature`, `ContextRefs.ingestion_job_id` optional, `output_schema`/`CompletionResult` union, `open_request_log`; summary features still require `ingestion_job_id` at the app layer.
- `PostClassQuiz` output schema + OutputValidator quiz rules (structure + size + escape-not-reject, authoritative).
- `post_class_quiz_generation/v1` prompt (reasoning route) + deterministic adapter valid/forced-invalid fixtures.
- Per-request fault injection (non-prod-gated) for inject→clear→succeed recovery tests.
- `generate_post_class_quiz` job (`quiz-generate:{attemptId}`); `start_quiz_attempt` service (get-or-create definition, resolve detailed summary→409, create generating attempt + provenance snapshot, commit, enqueue-after-commit + compensating enqueue-failure); atomic persist+provenance+flip; fencing; worker failure handler; 4.6c reaper 4th action (liveness-not-age) finalizing the orphaned AIRequestLog.

## Do not build
- Answer/feedback/scoring/retake endpoints (5c), UI (5d), HTTP routers/visibility/auth wiring.
- In-place generation retry of a *failed* attempt at the user level (Start Over = new attempt, 5c).

## Data model changes
Migration 0020 only (alter `ai_request_logs`). No new tables (all quiz tables landed in 5a).

## API changes
None (no endpoints; `start_quiz_attempt` is a service function consumed by 5c's endpoint).

## Worker / job changes
New `ai`-queue job `generate_post_class_quiz` (`quiz-generate:{attemptId}`, RQ Retry [30,120,300]).
Reaper extended with the quiz 4th action.

## Authz rules
None here (5c endpoint enforces student/visibility). `start_quiz_attempt` is the generation entry.

## Verification
```bash
docker run --rm --network test2_default --env-file <env> \
  -e DATABASE_URL=...@db:5432/<fresh> -e TEST_DATABASE_URL=...@db:5432/<fresh>_test \
  -v <ws>/backend:/app -w /app test2-backend python -m pytest -q
# Expected: 422 passed (407 post-5a + 15 new). Incl. migration round-trip (now 0013→0020) + prompt-drift guard.
```

## Done means
- One AI call per attempt through the gateway; AIRequestLog before the call (ingestion_job_id NULL for quiz); OutputValidator authoritative; persist+provenance+flip atomic; deterministic valid + forced-invalid fixtures in CI.
- Stuck `generating` recoverable: enqueue-failure compensation, worker failure handler, liveness-not-age reaper that finalizes the orphaned AIRequestLog; not reaped while legitimately queued.
- Summary features still require `ingestion_job_id` at the app layer (validated).
- Full suite green, no regression.

## Amendments
- 2026-06-16: extended the migration block to **0020** (approved) for the AIRequestLog decoupling — outside the original 0014–0019. Summary `ingestion_job_id` enforced at app layer, not the column.
