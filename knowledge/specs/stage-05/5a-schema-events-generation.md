---
type: session-spec
stage: "05"
session: "5a"
slug: schema-events-generation
status: draft-awaiting-approval
created: 2026-06-13
updated: 2026-06-13
owner: developer
umbrella: knowledge/specs/stage-05/5-shared-quiz-engine-event-spine.md
plan: knowledge/plans/stage-05/5a-schema-events-generation.md
---

# Session 5a — Schema + Event Spine + Quiz Generation (BACKEND VERIFIED target)

> Slice 1 of [[specs/stage-05/5-shared-quiz-engine-event-spine]]. Backend-only, NO HTTP endpoint / UI /
> attempt / event-INSERT (those are 5b/5c). **No source edits until this spec + plan are approved.**

## Goal
Stand up the full Stage-5 **schema** (one migration, 0014) + the greenfield **`platform/events`** model, and
wire the **quiz GENERATION** half: when a section's **detailed summary completes**, one AI call produces a
`QuizDefinition` (5×4 MCQ) through the proven gateway path, persisted with full provenance — idempotent,
failure-handled, deterministic-adapter-backed for the gate.

## Build
**Models + migration 0014 (the WHOLE Stage-5 schema, one migration; later slices only WIRE writes):**
- `QuizDefinition` — `module_section_id`, `source_transcript_id`, `source_detailed_summary_id`,
  **`source_transcript_checksum`** (O1 staleness basis), **`question_count`** (default 5),
  **`options_per_question`** (default 4), `content_json` (questions + options + `correct_option_id`),
  `content_schema_version`, AI provenance (`model_id`/`prompt_version`/`prompt_content_hash`/`backend_used`/
  `reasoning_level`/`input_hash`/`ai_request_log_id`/`created_by_ingestion_job_id`), **one-active
  partial-unique per section**.
- `QuizAttempt`, `StudentAnswer`, `MistakeRecord` (min schema: `retake_correct_count`,
  `show_in_retake_prefix`, `source_quiz_definition_id`, `source_question_snapshot`, `user_id`) — **tables
  created now, WRITES are 5b** (one migration avoids a 0015 in 5b).
- `StudentActivityEvent` (**`app/platform/events/` — greenfield**) — `user_id`, `event_type`, `module_id`,
  `section_id`, `source_id`, `occurred_at`, `payload` JSONB, **UNIQUE `(user_id, event_type, source_id)`**.
  Model + table + constraint now; the atomic INSERT + double-submit test are 5b.

**Generation pipeline (template = `transcripts/summary_service`):**
- `prompts/quiz_generation/v1.yaml` — model/backend/max_tokens; injects `{{detailed_summary}}` (+
  `question_count`/`options_per_question`); strict JSON output contract (a single object: `{questions:[…]}`).
- `QuizQuestions` Pydantic `output_schema` (in `platform/llm/models/`): N questions × M options, exactly one
  `correct_option_id`, validated by the existing `OutputValidator` (no tool-calling — F-5-1).
- `DeterministicTestProvider._render_output` gains a `quiz_generation` branch → 5 canned MCQs (4 options,
  one correct) so the gate runs deterministically (mirrors brief/detailed).
- **Enqueue trigger:** in the detailed-summary completion path (`_persist_summary_success` for the DETAILED
  spec), idempotently insert a `generate_quiz` `IngestionJob` (one-active per section) + enqueue it. Brief
  completion does NOT trigger.
- **Worker `generate_quiz`:** claim → `gateway.complete(prompt_key=quiz_generation, output_schema=QuizQuestions,
  …)` (exactly ONE call) → on success persist `QuizDefinition` (copy provenance from `AIRequestLog`, set
  `source_transcript_checksum`) → mark job completed; on failure mark `failure_category` (no artifact),
  bounded RQ-retry like summaries.
- **`derive_quiz_state` (pure fn, `domains/quizzes/precedence.py`):** `not_applicable` (non-lecture/lab) /
  `generating` (job queued/running) / `available` / `available_stale` (definition exists but
  `source_transcript_checksum` ≠ section's active checksum — the 4.7 read-time compare) / `unavailable`
  (detailed summary not ready / generation failed). Pure + unit-tested; the HTTP read endpoint is 5b/5c.

## Do not build (5a)
HTTP endpoints / client regen / any UI; attempt start/answer/submit; `StudentAnswer`/`MistakeRecord`/
`StudentActivityEvent` WRITES; the pagination envelope; retake behavior; real tool-calling.

## Verification (BACKEND VERIFIED)
`pytest`: 0014 fresh-DB round-trip (up/down); `generate_quiz` produces a `QuizDefinition` with full provenance
+ `ai_request_log_id`; **exactly ONE gateway call** per generation (asserted); deterministic adapter returns a
valid 5×4 single-correct MCQ payload that passes `OutputValidator`; **one-active idempotency** (re-enqueue is
a no-op); `derive_quiz_state` returns `available_stale` on a checksum mismatch and `generating`/`unavailable`
correctly; enqueue fires on DETAILED completion only, not brief. `tsc`/frontend untouched (no client change
yet). No new HTTP surface → no E2E in 5a (the browser gate is 5c).

## Findings
Carries the umbrella F-5-1/-2/-3. New only if generation surfaces one (e.g. the deterministic adapter shape
forcing a schema tweak) — recorded here.

## Open questions
- **OA1** — `content_schema_version` starting value + the exact `content_json` shape (question id stability
  for the 5b attempt snapshot + correctness-by-identity). Proposed: `v1`; each question + option gets a
  stable id (uuid7 at generation) so the attempt snapshot and `StudentAnswer.selected_option_id` pin to
  identity, never display order. Confirm in the 5a plan walkthrough.
