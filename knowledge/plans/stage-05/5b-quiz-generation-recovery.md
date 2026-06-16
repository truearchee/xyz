---
type: session-plan
stage: "05"
session: "5b"
slug: quiz-generation-recovery
status: executed
created: 2026-06-16
updated: 2026-06-16
spec: knowledge/specs/stage-05/5b-quiz-generation-recovery.md
report: knowledge/steps/stage-05/5b-quiz-generation-recovery.md
---

# Session 5b — Implementation Plan — Quiz Generation Pipeline + Recovery

## Linked documents
- Stage spec: [[specs/stage-05/5-shared-quiz-engine-event-spine]] (§5b)
- Foundation: [[specs/stage-05/5a-quiz-foundation]], [[steps/stage-05/5a-quiz-foundation]]
- Spec: [[specs/stage-05/5b-quiz-generation-recovery]]
- Plan: [[plans/stage-05/5b-quiz-generation-recovery]]
- Report: [[steps/stage-05/5b-quiz-generation-recovery]]

## Scope confirmation
Delivers the LAZY per-attempt quiz-generation pipeline (one AI call → 10 MCQs) on the existing `ai`
RQ queue through the 4.5 gateway, plus stuck-`generating` recovery. Does NOT build answer/feedback/
scoring/retake (5c) or UI (5d). Builds: `post_class_quiz_generation` prompt; the `PostClassQuiz`
output schema; OutputValidator quiz rules (structure + size + escape-not-reject); the
`generate_post_class_quiz` job (job_id `quiz-generate:{attemptId}`); the ATOMIC persist+provenance+flip
transaction; fencing; enqueue-after-commit + compensating enqueue-failure; the worker failure handler;
the 4.6c reaper 4th action (liveness-not-age) that also finalizes the orphaned AIRequestLog; and the
deterministic adapter's valid + forced-invalid quiz fixtures.

## Verified integration points (code-accurate, from exploration)
- **Gateway**: `LLMGateway.complete(*, prompt_key, output_schema, context_refs, priority, feature, attempt_number)` → `CompletionResult{parsed, model_id_echoed, usage, backend_used, reasoning_level, ai_request_log_id}` (`app/platform/llm/gateway.py:112`). Structured output = **JSON-mode** (`response_format={"type":"json_object"}`) + tolerant parse + Pydantic + `OutputValidator`, NOT function-calling (`provider.py:120-137`, `validation.py:124`). **Code wins → use the JSON path** (ADR-C).
- **Prompt registry**: flat YAML in `backend/prompts/<name>/<version>.yaml`; required fields `name,version,content,max_tokens,model,backend`; `{{transcript}}` placeholder is mandatory, `{{section_type}}` optional; content-hash drift guard; `render(key, transcript=, section_type=)` (`registry.py:132`). Model/backend declared per-prompt YAML; reasoning route = `backend: nvidia`, model from `settings.LLM_DETAILED_MODEL_ID` (K2-Think-v2 named deviation). A new input placeholder (`{{detailed_summary_text}}`) requires extending `render()`.
- **Deterministic adapter**: `DeterministicTestProvider._render_output()` branches on `rendered.prompt_key.name`; `fault="invalid_output"` forces a wrong-shaped body (`provider.py:322`). Add a `post_class_quiz_generation` branch (valid 10-Q fixture with known correct options + a forced-invalid variant).
- **Job/queue**: `ai` queue, `AI_RQ_RETRY_MAX=3`, intervals `[30,120,300]` (`queues.py`); enqueue-after-commit pattern in `parse_service.py:97`; worker selects queue by argv, runs startup reaper (`worker.py`).
- **Reaper**: `run_stuck_row_reaper` singleton-locked (`reaper.py:62`), liveness via `is_job_live_in_rq(job_type, id)` returning True/False/None (`rq_liveness.py:29`); add `"quiz_generate": lambda i: f"quiz-generate-{i}"` to `_STABLE_JOB_ID`; add a 4th action `_reap_lost_quiz_generation` (only `live is False` → reap; `None`/`True` → skip — liveness-not-age) that marks the attempt `failed/crashed` AND finalizes `attempt.ai_request_log_id` to terminal.

## Approach (mirror the summary pipeline)
1. `PostClassQuiz` Pydantic output schema (`app/platform/llm/models/`): 10 questions, each with `optionsPerQuestion` options, exactly one correct, explanation. CamelModel.
2. `post_class_quiz_generation/v1.yaml` prompt — reasoning route; input = the active detailed-summary TEXT (resolved at Start, snapshotted on the attempt in 5c-adjacent start flow).
3. `OutputValidator` quiz branch (authoritative regardless of mechanism): structure (exactly 10; 4 options; one isCorrect; non-empty/no-dupe option text; explanation present; no dupe questionText) + size (payload ≤64KB, questionText ≤1000, option ≤500, explanation ≤2000) + escape-not-reject (store `<`/`>` faithfully).
4. `generate_post_class_quiz` job + `enqueue_generate_post_class_quiz(attempt_id)` (job_id `quiz-generate-{attemptId}`, Retry). The Start endpoint (lands here or 5c) creates `QuizAttempt(generating)`, COMMITS, enqueues after commit; compensating transaction marks `failed/enqueue_failed` if enqueue throws.
5. Job body: claim attempt FOR UPDATE (fence: only if `generating` and no questions); AIRequestLog before the call (rule 6); gateway call; validate; ATOMIC single transaction — persist QuizQuestion+AnswerOption (displayOrder shuffled) + stamp attempt provenance + flip → `in_progress` (totalQuestions=10, generationCompletedAt). On exhausted failure → `_mark_quiz_attempt_failed` (status `failed`, failureCategory). No in-place retry (Start Over makes a new attempt).
6. Reaper 4th action + AIRequestLog finalize-on-crashed.
7. Deterministic adapter quiz fixtures; tests for the whole path (CI deterministic).

## ⚠ Decisions that MUST be resolved before building (need your call)
- **D-A (BLOCKER — migration outside my block):** `ai_request_logs.ingestion_job_id` is **NOT NULL** (FK→ingestion_jobs) and `feature` CHECK = `('summary_brief','summary_detailed')`. The spec forbids a quiz IngestionJob and mandates an AIRequestLog row before the call. So 5b needs a migration: make `ingestion_job_id` **nullable** + widen the `feature` CHECK to include the quiz feature (the QuizAttempt→AIRequestLog link already exists from 5a). That migration is **0020 — outside the assigned 0014–0019 block.** Need a migration number (extend my block to 0020) or coordination guidance. (This is the already-logged open-question: "AIRequestLog.ingestion_job_id NOT NULL … Stage 8 will need it nullable.")
- **D-B (touches shared 4.5 infra):** the gateway (`complete`/`ContextRefs`/`open_request_log`/`feature` enum/`output_schema` union) is summary-specific (two summary types, required `ingestion_job_id`, `transcript_text`). 5b must generalize it (quiz feature, quiz schema, optional `ingestion_job_id`, input text = detailed-summary text). This edits code the summary pipeline depends on → regression risk (mitigated by the full suite). Confirm: generalize the shared gateway (recommended — keeps the limiter/logging/validation guarantees) vs. a parallel quiz path (discouraged — duplicates infra).
- **D-C (test enablement):** per-request fault injection is NOT implemented (open-question, global `LLM_FAULT_INJECTION` can't express inject→clear→succeed). The S6 recovery E2E + validator-retry test want it. Build a small per-request mechanism in 5b (recommended) or accept constructor-fault + limiter-based retry only (weaker).
- **D-D (decided, code wins):** structured output uses the existing JSON-mode path, not function-calling. → ADR-C.

## Test strategy
Deterministic-adapter valid fixture (reach 100% + specific wrong answers) + forced-invalid (validator/
retry). Tests: atomic persist (status `generating` ⇒ no questions; after ⇒ in_progress+10); fencing
(no double-generate); enqueue-failure compensation; worker-handler failure; reaper reaps LOST job
(`live is False`) but NOT queued (`True`/`None`) and finalizes the AIRequestLog; AIRequestLog written
before the call; size/structure validation; escape-not-reject.

## Risks & mitigations
- Shared-gateway edits → run the FULL suite (currently 407 on this branch) after each change; keep summary call sites green.
- Migration-block overflow (D-A) → blocked pending a number; do not invent 0020 without sign-off.
- Real-provider smoke (rule 11) is a 5d obligation, not 5b.

## Open questions
- D-A migration number; D-B shared-gateway-edit authorization; D-C fault-injection scope. See open-questions.md.
