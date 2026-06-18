---
type: session-spec
stage: "06"
session: "6a"
slug: pool-foundation
status: done            # draft → approved → in-progress → done → superseded
created: 2026-06-17
updated: 2026-06-17
owner: developer
plan: knowledge/plans/stage-06/6a-pool-foundation.md
report: knowledge/steps/stage-06/6a-pool-foundation.md
---

# Session 6a — Per-section pool foundation + capacity ADR

## Linked documents
- Overview spec: [[specs/stage-06/6-complete-quiz-modes]]
- Spec: [[specs/stage-06/6a-pool-foundation]]
- Plan: [[plans/stage-06/6a-pool-foundation]]
- Report: [[steps/stage-06/6a-pool-foundation]]

## Goal
A durable, reusable **per-section question pool** keyed `(section, model, promptVersion)` exists and is
proven: questions are AI-generated **once per section** from the detailed summary, **sampled** per attempt
with recency bias + cross-section spread + snapshot-at-assembly, under a one-active generation lock — with
the MistakeRecord pool-upsert identity in place. This is the engine the new modes (6b/6c) sit on; **no mode
UI is built in 6a.**

## Why now
Per-attempt generation (Stage 5) does not scale to exam week (30 students × 6-section recap ≈ 180 reasoning
calls ≈ 18 min queue). The capacity ADR resolves this with reuse: generate once per section, sample per
attempt. 6a builds and gate-proves that engine on surfaces with no shipped contract, before the modes that
consume it — and before the 6d post-class retrofit touches a FULLY VERIFIED surface.

## Read first
- [[specs/stage-06/6-complete-quiz-modes]] (overview, esp. "The capacity decision" + "Data model")
- `backend/app/domains/quiz/generation_service.py` (the Stage 5 lazy-per-attempt pattern to mirror)
- `backend/app/platform/db/models/ingestion_job.py` (the migration-0007 one-active partial-unique pattern)
- `backend/app/domains/recovery/reaper.py` + `backend/app/domains/recovery/rq_liveness.py` (liveness keying)
- `backend/app/platform/llm/validation.py` + `backend/app/platform/llm/gateway.py` (additive schema dispatch)

## Source paths likely touched
- `backend/alembic/versions/0023_*.py`, `0024_*.py` (additive; quiz domain only)
- `backend/app/platform/db/models/section_question_pool.py`, `pool_question.py` (new); `quiz_question.py`,
  `mistake_record.py`, `__init__.py` (additive columns/registration)
- `backend/app/domains/quiz/pool_service.py`, `sampling.py`, `assembly_service.py`, `config.py`, `jobs.py` (new/edit)
- `backend/app/platform/llm/models/quiz.py`, `models/prompt.py`, `validation.py`, `gateway.py` (additive)
- `backend/prompts/quiz_pool_generation/v1.yaml` (new) + `backend/prompts/CHECKSUMS.json` (regen)
- `backend/app/workers/queues.py` (additive enqueue fns)
- `backend/app/domains/recovery/reaper.py`, `rq_liveness.py` (pooled-attempt liveness — additive)
- `backend/tests/...` (6a hard-gate tests)

## Build
- Section pool store (`section_question_pools` + `pool_questions`) keyed `(section, model, promptVersion)`,
  status `generating|ready|failed|superseded`, two partial-unique indexes (ready slot + generating herd lock).
- One-call pool generation from the detailed summary through the existing gateway/limiter/AIRequestLog chain;
  `GeneratedQuizPool` schema + `_validate_quiz_pool` (min≤len≤max) + new `quiz_pool_generation/v1.yaml`
  prompt (reasoning route); widen `GatewayFeature` + `ai_request_logs.feature` for `'quiz_pool'`.
- Per-attempt sampling: seedable, recency-biased (exposure derived from prior `QuizQuestion.source_pool_question_id`
  rows), even cross-section spread, exhaustion-recycle **with no AI call**; snapshot-at-assembly into
  per-attempt `QuizQuestion`/`AnswerOption` rows (shuffle at snapshot via the seeded Random).
- Scheduler-free multi-section assembly: ensure pools (herd-locked) → attempt `generating` → pool-completion
  **fan-in** → idempotent fenced assembly job (`quiz-generate:{attemptId}` job-id) → `in_progress`; failure
  names the section.
- Stale-pool invalidation: store `source_summary_content_hash`; supersede the live pool + regenerate on
  mismatch (atomic-swap). Snapshot immunity for started attempts.
- MistakeRecord pool-upsert identity: `source_pool_question_id` + partial-unique
  `(student_id, source_quiz_definition_id, source_pool_question_id)`; ON-CONFLICT upsert with Stage 5 fallback.
- Reaper: a pooled `generating` attempt counts live while any in-scope pool is `generating`.
- `config.py` named defaults (POST_CLASS_QUIZ_LEN=10, RECAP_EXAM_PER_SECTION=5, POOL_TARGET=24, POOL_MIN/MAX=16/32, spread=even).
- Capacity ADR.

## Do not build
- **No mode selector / scope modal / any Stage 6 UI** (6d).
- **No recap / exam_prep / mistakes_bank endpoints or AssessmentScope** (6b/6c) — only the pool engine +
  the sampling/assembly/mistake-identity primitives they will call.
- **No post-class retrofit** (D4 = 6d). Post-class stays on its Stage 5 per-attempt path in 6a.
- No changes to shared **contracts** (limiter/registry/queue/pagination interfaces) — only additive schema
  union / feature enum growth (coordinate via findings note).
- No pool top-up / regeneration on exhaustion (post-MVP). No denormalized exposure table (derive at MVP).
- No migrations outside **0023–0028**.

## Data model changes
New `section_question_pools`, `pool_questions`. Additive: `quiz_questions.source_pool_question_id` (FK,
nullable); `mistake_records.source_pool_question_id` (FK, nullable) + partial-unique upsert index;
`ai_request_logs.feature` CHECK widened for `'quiz_pool'`. Migrations **0023** (pools + pool_questions +
quiz_questions FK + feature CHECK) and **0024** (mistake_records FK + index). Both round-trip on a fresh DB;
single alembic head.

## API changes
None student/lecturer-facing in 6a (engine + internal services only). Sampling/assembly are invoked by 6b/6c.

## Worker / job changes
New `ai`-queue jobs: `generate_section_pool` (job-id `quiz-pool:{poolId}`), `try_assemble_attempt` (job-id
`quiz-generate:{attemptId}`). Enqueue-after-commit + compensate, mirroring Stage 5. No RQ scheduler
introduced (reserved for 11.1) — fan-in drives assembly. Reaper liveness extended for pooled attempts.

## Authz rules
None new in 6a (no endpoints). The student published/assigned filter and 404 rules land in 6b.

## Verification
- `docker compose exec backend pytest` → all pass, incl. the **6a hard-gate** tests:
  1. simultaneous first-requests for the same ungenerated section → **exactly one** pool generation (one
     `quiz_pool` AIRequestLog at section granularity); both assembly jobs attach via fan-in.
  2. sampling: recency bias, even cross-section spread, exhaustion-recycle with **no** generation call;
     seed determinism (same seed → same sample; different attempt → different combo).
  3. MistakeRecord upsert identity: re-missing a re-sampled pool question in the same QuizDefinition updates
     **one** record.
  4. snapshot immunity: pool supersession does not mutate a started attempt.
  5. reaper: a waiting pooled attempt is not reaped while its pool is `generating`.
- `docker compose exec backend ruff check .` → clean
- `docker compose exec backend alembic upgrade head && alembic downgrade base && alembic upgrade head` → round-trips
- `docker compose exec backend alembic heads` → single head (0024)
- `docker compose exec frontend npx tsc --noEmit` → clean (no FE changes expected, but the suite must stay green)

## Knowledge updates required
- `knowledge/steps/stage-06/6a-pool-foundation.md` (report — always)
- `knowledge/decisions/adr-0xx-section-question-pool-capacity.md` (the capacity ADR)
- `knowledge/steps/findings-6-shared-infra.md` (the additive `platform/llm` union/feature-enum coordination note)
- `knowledge/architecture/` only if a durable source-path map changed

## Done means
The pool engine exists; the 6a hard gate passes (all five proofs); migrations round-trip with a single head;
backend + ruff green; the capacity ADR is recorded; no mode UI or shipped-surface change landed.

## Amendments
_Add dated entries here if scope changes mid-flight. Do not silently edit the sections above._
