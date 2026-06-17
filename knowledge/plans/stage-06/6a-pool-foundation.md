---
type: session-plan
stage: "06"
session: "6a"
slug: pool-foundation
status: executed     # proposed → approved → executed
created: 2026-06-17
updated: 2026-06-17
spec: knowledge/specs/stage-06/6a-pool-foundation.md
report: knowledge/steps/stage-06/6a-pool-foundation.md
---

# Session 6a — Implementation Plan — Per-section pool foundation + capacity ADR

## Linked documents
- Overview spec: [[specs/stage-06/6-complete-quiz-modes]]
- Spec: [[specs/stage-06/6a-pool-foundation]]
- Plan: [[plans/stage-06/6a-pool-foundation]]
- Report: [[steps/stage-06/6a-pool-foundation]]

> The full Stage-6 architecture (all four seams, the four locked owner decisions, the migration
> allocation, the reuse map, the verification gates) lives in the approved plan file
> `/Users/arthur.leontev/.claude/plans/system-instruction-the-user-has-peaceful-sutton.md`. This file is
> the 6a-scoped HOW.

## Locked decisions (owner-confirmed 2026-06-17 — cite in the ADR)
- **D1** Exam-prep pre-warm = **on create** (background priority; idempotent skip). *Affects 6b, not 6a.*
- **D2** Mistakes-bank/"2-correct" = **source-quiz only, cumulative, no re-add**. *6a lands the upsert identity; the flip is 6c.*
- **D3** Partial-readiness = **all-or-wait** (protects the shared-QuizDefinition canonical key). *Affects 6b.*
- **D4** Post-class retrofit = **last, in 6d, revertible** (supersedes spec v2's 6a placement). *6a leaves post-class on its Stage 5 path.*
- **Staleness signal** = sha256 of the detailed summary's `content_json` (= attempt's `source_summary_content_hash`), **not** `source_transcript_checksum`.
- **Guard-rail 1** the pool one-active lock `(section, model, promptVersion)` is independent of the per-attempt `quiz-generate:{attemptId}` assembly job-id → asserted in the hard gate.

## Scope confirmation
Delivers the reusable per-section pool engine + sampling/assembly/mistake-identity primitives, gate-proven,
with **no mode UI, no recap/exam_prep/mistakes_bank endpoints, no AssessmentScope, no post-class retrofit**
(those are 6b/6c/6d). Additive only; migrations 0023–0024; no shared-contract changes (only additive
`platform/llm` union/feature-enum growth, coordinated via a findings note). Nothing ambiguous remains —
the four seams were validated against the real schema during planning.

## Approach
Mirror the Stage 5 lazy-generation machinery (`generation_service.py`) but split the AI generation (now at
the **pool** level, keyed `(section, model, promptVersion)`, herd-locked) from the **attempt** (now
assembled by sampling + snapshot, no AI). Two-level waiting is driven **scheduler-free** by a
pool-completion fan-in (the worker has no RQ scheduler; reserved for 11.1). Reuse the gateway/limiter/
AIRequestLog chain unchanged; extend the validator/schema **additively** for a variable-count pool. The
MistakeRecord pool-upsert identity is landed now (used in 6c) so the schema is stable. The reaper learns
that a pooled `generating` attempt is legitimately alive while its pools generate.

## Changes, file by file
- `backend/alembic/versions/0023_section_question_pool.py` — `section_question_pools` (+ two partial-unique
  indexes), `pool_questions`, `quiz_questions.source_pool_question_id` (add column, then FK after
  `pool_questions` exists — deferred-FK style of 0019), widen `ai_request_logs.feature` CHECK to include
  `'quiz_pool'`. `down_revision = "0022"`.
- `backend/alembic/versions/0024_mistake_record_pool_identity.py` — `mistake_records.source_pool_question_id`
  (FK nullable) + partial-unique `(student_id, source_quiz_definition_id, source_pool_question_id) WHERE source_pool_question_id IS NOT NULL`. `down_revision = "0023"`.
- `backend/app/platform/db/models/section_question_pool.py`, `pool_question.py` — new models (uuid7 PK,
  the index/constraint set above; options JSONB on `pool_questions`). Register in `models/__init__.py`.
- `backend/app/platform/db/models/quiz_question.py`, `mistake_record.py` — add the nullable
  `source_pool_question_id` column/FK (+ the mistake upsert index in `__table_args__`).
- `backend/app/platform/llm/models/quiz.py` — add `GeneratedQuizPool` (`questions: list[GeneratedQuizQuestion]`)
  + `QUIZ_POOL_SCHEMA_VERSION`.
- `backend/app/platform/llm/models/prompt.py` — `GatewayFeature` Literal += `'quiz_pool'`.
- `backend/app/platform/llm/validation.py` — `_validate_quiz_pool` branch (reuse `_candidate_objects` +
  `_select_last_valid`; enforce `POOL_MIN ≤ len ≤ POOL_MAX` + the same per-question checks); dispatch on
  `GeneratedQuizPool`. `PostClassQuiz` path untouched.
- `backend/app/platform/llm/gateway.py` — widen `complete()` `output_schema` union hint (additive).
- `backend/prompts/quiz_pool_generation/v1.yaml` — new prompt (reasoning route `nvidia`/`K2-Think-v2`,
  asks for `POOL_TARGET` questions from `{{transcript}}` = the detailed-summary text; higher `max_tokens`).
  Regenerate `backend/prompts/CHECKSUMS.json` via its generator.
- `backend/app/domains/quiz/config.py` — named defaults (no magic numbers).
- `backend/app/domains/quiz/pool_service.py` — `ensure_section_pool` (get-or-create + herd-locked enqueue),
  `generate_section_pool_async` (claim→gateway(`GeneratedQuizPool`, summary text via `_summary_to_text`)→
  validate→persist `pool_questions`→flip `ready`→fan-in), `mark_pool_failed`, staleness/supersede helper.
- `backend/app/domains/quiz/sampling.py` — seedable recency-biased even-spread sampler + exhaustion-recycle;
  exposure query over prior `QuizQuestion.source_pool_question_id`. Seeded `random.Random` (seed from
  `attempt_id`; env-gated test override).
- `backend/app/domains/quiz/assembly_service.py` — `try_assemble_attempt_async` (fenced/idempotent;
  all-ready → sample+snapshot+flip; some-generating → no-op; any-failed → fail naming section); the
  snapshot writer (mirrors `_persist_generation_success`, seeded shuffle).
- `backend/app/domains/quiz/mistakes.py` (or extend an existing helper) — the MistakeRecord ON-CONFLICT
  upsert keyed on the pool identity with the Stage 5 fallback (helper; wired into `service.answer()` in 6c).
- `backend/app/workers/queues.py`, `backend/app/domains/quiz/jobs.py` — `enqueue_generate_section_pool`,
  `enqueue_try_assemble_attempt`; job wrappers.
- `backend/app/domains/recovery/reaper.py`, `rq_liveness.py` — pooled-attempt liveness (additive; documented
  as a prior-session modification per AGENTS.md).
- `backend/tests/...` — the five 6a hard-gate proofs + unit tests for sampler/validator/staleness.

## Order of operations
1. Migrations 0023 + 0024; models + registration; round-trip + single-head check.
2. `config.py`; `GeneratedQuizPool` + `_validate_quiz_pool` + gateway union; `quiz_pool_generation/v1.yaml` +
   CHECKSUMS regen; feature-enum/CHECK widening. Coordinate findings note.
3. `pool_service` (generation + herd lock + staleness/supersede) + queues/jobs; unit-test generation +
   the one-active lock (gate proof 1).
4. `sampling` (recency/spread/exhaustion/seed) + unit tests (gate proof 2).
5. `assembly_service` (fan-in + snapshot + fence) + the multi-section waiting/failure paths.
6. Reaper pooled-attempt liveness (gate proof 5).
7. MistakeRecord upsert helper + identity test (gate proof 3); snapshot-immunity test (gate proof 4).
8. Run the full backend suite + ruff + migration round-trip; write the report + ADR + findings note.

## Test strategy
Each gate proof is a deterministic backend/integration test using the existing deterministic LLM adapter at
the provider boundary (AIRequestLog still written, so "no new generation row at section granularity" is
assertable in CI). Concurrency for proof 1 via parallel `start`-equivalents hitting the herd lock. Sampler
seedability makes proofs 2/4 reproducible. Reaper proof injects liveness/now exactly as the Stage 4.6c
tests do. Maps to the spec's Verification block.

## Risks & mitigations
- Reaper false-reap of waiting pooled attempts → the pooled-liveness extension + an explicit "not reaped
  while pool generating" test.
- `module_section_id` NULL deref on event/visibility paths → that surfaces in 6b/6c; 6a keeps the column
  set additive and does not emit events.
- Shared-`platform/llm` union/feature growth colliding with Stage 7 → additive-only + findings note;
  trivial textual rebase, no behavioral coupling.
- Pool sizing (`POOL_TARGET=24`) must serve the eventual post-class 10-draw (6d) with retake headroom →
  sized against the largest per-section draw, configurable.

## Open questions
- Confirm the `CHECKSUMS.json` generation command (do not hand-edit) before adding the new prompt.
- Confirm the reaper's existing age/grace constants comfortably exceed pool-generation latency for the
  waiting window (else widen the grace for pooled attempts). Promote to `open-questions.md` if unresolved.
