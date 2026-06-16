---
type: session-report
stage: "05"
session: "5b"
slug: quiz-generation-recovery
status: complete
created: 2026-06-16
updated: 2026-06-16
spec: knowledge/specs/stage-05/5b-quiz-generation-recovery.md
plan: knowledge/plans/stage-05/5b-quiz-generation-recovery.md
---

# Session 5b — Report — Quiz Generation Pipeline + Recovery

## Linked documents
- Stage spec: [[specs/stage-05/5-shared-quiz-engine-event-spine]]
- Spec: [[specs/stage-05/5b-quiz-generation-recovery]]
- Plan: [[plans/stage-05/5b-quiz-generation-recovery]]
- Report: [[steps/stage-05/5b-quiz-generation-recovery]]
- ADRs: [[decisions/adr-043-lazy-per-attempt-quiz-generation]], [[decisions/adr-044-structured-quiz-output-json-validator-authority]], [[decisions/adr-045-airequestlog-decoupled-gateway-generalized]], [[decisions/adr-046-quiz-generation-recovery]]

## What shipped (from `git diff` + new files)
Migration:
- `0020_ai_request_log_decouple_ingestion_job.py` — `ai_request_logs.ingestion_job_id` → nullable (general "AI calls aren't always ingestion jobs" decoupling, documented in a column COMMENT for Stage 8); `ck_ai_request_logs_feature` widened (enumerated) to add `post_class_quiz`. Downgrade reverses both.

Modified (shared 4.5 infra — by addition):
- `models/ai_request_log.py` — `ingestion_job_id` nullable + decoupling comment; feature CHECK widened.
- `models/prompt.py` — `GatewayFeature` (adds `post_class_quiz`), `SummaryFeature` alias kept; `FEATURES_REQUIRING_INGESTION_JOB`.
- `gateway.py` — `ContextRefs.ingestion_job_id` optional; `output_schema`/`CompletionResult` union gains `PostClassQuiz`; `feature: GatewayFeature`; **app-layer guard**: summary features with `ingestion_job_id=None` raise before any log row opens.
- `logging.py` — `open_request_log(ingestion_job_id: UUID | None)`.
- `validation.py` — `OutputValidator.validate` dispatches `PostClassQuiz` → `_validate_quiz_object` (exactly 10 questions; 4 options; one correct; no empty/dup option/question; explanation present; size caps; escape-not-reject).
- `provider.py` — per-request fault injection (`set_request_faults`/`clear_request_faults`, non-prod-gated, popped once per `send()` before the constructor fault, `invalid_input` excluded) + `_quiz_fixture` (valid 10-Q with known-correct option A; forced-invalid drops a question).
- `prompts/post_class_quiz_generation/v1.yaml` + `CHECKSUMS.json` entry.
- `query/quiz_availability_read.py` — added `resolve_quiz_source_summary` (platform-only readiness resolution so the quiz domain imports no other domain).
- `workers/queues.py` — `enqueue_generate_post_class_quiz` (`quiz-generate:{id}`, Retry [30,120,300]).
- `recovery/rq_liveness.py` — `"quiz_generate"` stable-id builder.
- `recovery/reaper.py` — 4th action `_reap_lost_quiz_generation` (LIVENESS not age: reap only `live is False`) + `_mark_quiz_attempt_crashed_fenced` (marks failed/crashed + finalizes the linked AIRequestLog → `failed`/`abandoned_crashed`).

New (quiz domain):
- `domains/quiz/generation_service.py` — `start_quiz_attempt` (get-or-create definition, resolve detailed summary→`QuizUnavailableError`, create generating attempt + provenance snapshot, COMMIT, enqueue-after-commit + compensating `enqueue_failed`; concurrent-Start race → resume) + `generate_post_class_quiz_async` (claim/fence → gateway → stamp log id → atomic persist+provenance+flip → mark failed; RQ-retryable re-activation).
- `domains/quiz/jobs.py` — the sync RQ wrapper.

New tests: `tests/test_quiz_generation.py` (15).

## Verification (real output)
Run with this workspace's code mounted, against a fresh isolated DB (NOT the shared `xyz_lms`):
```
$ docker run --rm --network test2_default --env-file <env> \
    -e DATABASE_URL=...@db:5432/xyz_lms_5bfull -e TEST_DATABASE_URL=...@db:5432/xyz_lms_5bfull_test \
    -v <ws>/backend:/app -w /app test2-backend python -m pytest -q
422 passed, 111 warnings in 48.87s
```
- `422` = 407 (post-5a) + 15 new. No failures, no regressions in the summary path despite the shared-gateway/AIRequestLog changes.
- Includes `test_migration_round_trip` (now `0013→…→0020` up→down→up) and the prompt-drift guard (the new prompt's CHECKSUMS entry validated).
- 15 new tests cover: start (create/resume/unavailable/enqueue-failure compensation); atomic persist+flip; `generating ⟺ no questions`; idempotent re-run (fence); invalid_output → failed/invalid_output; provider_transient → failed/provider_error; per-request inject→clear→succeed; reaper reaps lost job + finalizes AIRequestLog; reaper does NOT reap live/unknown; summary app-layer ingestion_job_id guard; validator structure/size/escape.

Throwaway DBs dropped after the run; `xyz_lms`/`xyz_lms_test` untouched.

## Decisions (→ ADRs)
- D-A/D-B confirmed by the developer: extend the block to **0020**; generalize the shared gateway (not a parallel path). → ADR-045.
- Structured output = the existing JSON-mode path (code wins; not function-calling). → ADR-044.
- Lazy per-attempt generation. → ADR-043. Recovery (enqueue-after-commit + worker handler + liveness reaper + AIRequestLog finalize). → ADR-046.

## Deviations / residuals (honest accounting)
1. **AIRequestLog finalize on a mid-CALL crash is best-effort.** The attempt's `ai_request_log_id` is
   stamped right AFTER `complete()` returns (a dedicated txn before the atomic question-persist), so the
   reaper finalizes the log for the common crash window (between the AI call returning and the DB write).
   A crash DURING the HTTP call (before `complete()` returns) leaves a `running` log with no attempt
   linkage — the SAME pre-existing behavior as summaries — because the linkage only exists once the
   gateway returns. Fully closing it needs an AIRequestLog→source reference (the same Stage-8 decoupling).
   Logged in open-questions.
2. **RQ-retry re-activation interpretation.** "RQ retry → exhausted → failed" + "no in-place retry of a
   failed attempt" reconciled as: the bounded RQ retry re-activates a transiently-`failed` attempt
   (categories `provider_error`/`invalid_output`) back to `generating` and re-runs (mirrors the 4.5
   summary claim); `crashed`/`enqueue_failed` are terminal; "no in-place retry" holds at the USER level
   (no manual retry endpoint — Start Over makes a new attempt, 5c). A brief `failed`→`generating`
   flicker during retry backoff is the same as the summary path.
3. **RESOLVED by Session 5e:** `generation_job_id` is now stored after successful enqueue, using the same
   canonical `quiz-generate:{attemptId}` helper as RQ liveness.
4. **Per-request `invalid_input` unsupported** — it is a pre-transport gateway fault, not a provider-
   boundary outcome; the setter rejects it. Constructor-fault still covers the over-context path.

## Modified prior sessions
- Session 4.5 (`app/platform/llm/{gateway,logging,validation,provider}.py`, `models/prompt.py`,
  `db/models/ai_request_log.py`) — generalized the gateway by addition for quiz; summary behavior
  unchanged (byte-for-byte feature values; `ingestion_job_id` still required for summaries at the app
  layer, proven by `test_summary_feature_still_requires_ingestion_job_id`). 4.5 reports remain
  `status: complete` historical records; this is the change-history note.
- Session 4.6c (`app/domains/recovery/{reaper,rq_liveness}.py`) — added the quiz 4th action + liveness
  builder; existing actions untouched.

## Close-the-loop checklist
- [x] Spec `status: done`; plan `status: executed`
- [x] Plan approved before source edits (developer's D-A/D-B/D-C calls)
- [x] Stayed in scope; residuals recorded above
- [x] Verification run; real output recorded (422 passed)
- [x] Report from `git diff` + command output
- [x] spec ↔ plan ↔ report links resolve
- [x] `STATUS.md` overwritten; `log.md` appended
- [ ] `architecture/` — not updated (defer to 5c/5d when the quiz domain gets endpoints/UI; no architecture doc covers it yet)
- [x] ADRs 043–046 added
- [x] `open-questions.md` updated (AIRequestLog mid-call-crash residual; per-request-fault now landed)

## Change history
- 2026-06-16 — [Session 5b] initial report. Generation pipeline + recovery landed + verified (422 passed) on an isolated DB.
- 2026-06-16 22:46 — [Session 5e] stamped `QuizAttempt.generation_job_id` after enqueue, changed the uncommitted 0016 column/model to text, and aligned enqueue + RQ liveness on `quiz-generate:{attemptId}`; full backend passed (442).
