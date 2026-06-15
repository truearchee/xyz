---
type: stage-spec
stage: "05"
slug: shared-quiz-engine-event-spine
status: draft-awaiting-approval
created: 2026-06-13
updated: 2026-06-13
owner: developer
inputs: ["knowledge/roadmap.md §Stage 5", "knowledge/design-plan.md §2.4", "knowledge/design-system.md"]
---

# Stage 5 — Shared Quiz Engine + Event Spine (UMBRELLA SPEC)

> Two-input rule (design-system.md): written from **roadmap §Stage 5 + design-plan §2.4 + design-system.md
> (the as-built component contracts)**. **No source edits until this spec + the per-slice plans are approved.**
> Browser gate uses the **deterministic adapter** (rule 11/§14) → Stage 5 is NOT blocked by the
> Workstream-A credential issue.

## Goal
A shared **MCQ** quiz engine + the platform **activity event spine**. A student opens a lecture/lab whose
detailed summary is ready, sees a post-class quiz, starts it, answers, gets **immediate per-question
feedback**, finishes with a score; a wrong answer becomes a recorded mistake; a `quiz_completed`
`StudentActivityEvent` is inserted **in the same transaction as the score**.

## Locked decisions (entry session, 2026-06-13)
1. **Output enforcement = the EXISTING gateway path** (`gateway.complete` + a `QuizQuestions` Pydantic
   `output_schema` + `OutputValidator`), same as brief/detailed. The deterministic adapter gains a canned
   `quiz_generation` output for the gate. **Function/tool-calling is DEFERRED** to a finding (it only matters
   for the real provider, which is credential-blocked — F-C5/F-4.5-27); shipping it now would be unverifiable.
2. **Source + shape = the detailed summary**, **5 questions × 4 options**, exactly one correct; **one AI call
   per quiz** (rule 15). Correctness pinned to **option identity**, shuffled on display (never the letter).
3. **Trigger = pre-generate** when the detailed summary completes (enqueue a `generate_quiz` job, pipeline-
   consistent with summaries). Quiz is **available** once the `QuizDefinition` is ready; the **attempt
   snapshots questions on start** (questions belong to the attempt — locked; schema must NOT preclude a
   Stage-6 pool, flagged not built).
- Roadmap-locked (specced as-is, not re-decided): per-question immediate feedback (UI proof); event insert
  atomic with the score (rule 7, idempotency `source_id` = attempt id); define the pagination envelope now.

### Umbrella-level schema locks (settled 2026-06-13 — load-bearing, can't be "confirm in 5a"; all touch migration 0014)
4. **O1 — keep the `QuizDefinition` when its source summary is superseded; `stale` is DERIVED, not stored.**
   The reason is lifecycle, not provenance: a `QuizAttempt` **snapshots its questions on start**, so attempts
   are immutable history while the definition is the live generator — a superseded summary must not vanish
   questions from an in-progress or past attempt. The schema lock: `QuizDefinition.source_transcript_checksum`
   (immutable, set at generation). `stale` is **computed at read** (`derive_quiz_state` compares it to the
   section's current active-transcript checksum) — the SAME mechanism as 4.7 summary precedence, no
   materialized boolean to drift on the write path. A stale quiz is **available-but-stale** (still takeable),
   distinct from a summary's *unavailable*. No hide, no auto-regenerate (Stage-6 concern).
5. **O2 — store the counts, don't hardcode.** `QuizDefinition.question_count` + `.options_per_question`
   (defaults 5 / 4); the generator READS them. No config UI (Stage-6 recap/exam modes vary the count → storing
   now avoids a Stage-6 migration; configurability is deferred-until-asked).
6. **Pagination envelope is a SHARED contract** (5b) — lands in `platform/query` (or an equivalent shared
   schemas location), NOT inside `domains/quizzes/`, so glossary/conversations/events reuse one envelope, not
   a fork. Shape `{ items, total, limit, offset }`. (Refines F-5-3.)
7. **Event-spine idempotency is a CONSTRAINT, not a label.** `StudentActivityEvent` carries a UNIQUE
   constraint on `(user_id, event_type, source_id)`; the insert is `ON CONFLICT DO NOTHING` inside the score
   txn, so a double-fire (retry / double-submit / replay) inserts exactly ONE `quiz_completed` event. 5b's DB
   test asserts a double-submit → one row. (Stage-10 gamification reproduces state from these events → a
   duplicate would be a duplicated badge/streak.)

## Backend scope
**New domain `app/domains/quizzes/`** (mirrors `student_summaries/` + `transcripts/summary_service`):
`service.py`, `generation_service.py`, `policy.py` (`QuizAccessPolicy`), `precedence.py`
(`derive_quiz_state`), `schemas.py`.

**Models (`platform/db/models/`) + migration 0014:**
- `QuizDefinition` — FK `module_section_id` (+ `source_transcript_id`, `source_detailed_summary_id`),
  `content_json` (the questions + options + correct option id), `content_schema_version`,
  **`source_transcript_checksum`** (O1 — staleness basis, derived at read), **`question_count`** (default 5)
  + **`options_per_question`** (default 4) (O2 — stored, generator reads them), full AI provenance
  (`model_id`/`prompt_version`/`prompt_content_hash`/`backend_used`/`reasoning_level`/`input_hash`/
  `ai_request_log_id`/`created_by_ingestion_job_id`), one-active partial-unique per section.
- `QuizAttempt` — FK `user_id` + `quiz_definition_id`, `question_snapshot_json` (questions+options as shown,
  locked at start), `score`, `total`, `started_at`, `submitted_at`, status (`in_progress`/`submitted`).
- `StudentAnswer` — FK `quiz_attempt_id` + question ref, `selected_option_id`, `is_correct`, `answered_at`
  (one per question; immediate-feedback writes happen here).
- `MistakeRecord` — **minimum schema only**: `retake_correct_count`, `show_in_retake_prefix`,
  `source_quiz_definition_id`, `source_question_snapshot` (+ `user_id`, created on a wrong answer). The
  mistakes-bank MODE/retake UX is Stage 6 — Stage 5 only CREATES the record.
- `StudentActivityEvent` (**`platform/events/` — greenfield, rule 7**) — `user_id`, `event_type`
  (`quiz_completed` first), `module_id`, `section_id`, `source_id` (→ the attempt id), `occurred_at`,
  `payload` JSONB (score/total). **UNIQUE `(user_id, event_type, source_id)`** (item 7); the insert is
  `ON CONFLICT DO NOTHING` inside the score txn → a double-fire yields exactly one row. Source action + event
  insert **commit in one DB txn**. Gamification (later) CONSUMES; never owns. *(Table + constraint in 0014/5a;
  the atomic insert + the double-submit DB test in 5b.)*

**Generation flow** (template = `transcripts/summary_service`):
- On detailed-summary completion, enqueue a `generate_quiz` `IngestionJob` (idempotent, one-active).
- Worker: claim → `gateway.complete(prompt_key=quiz_generation, output_schema=QuizQuestions, …)` (ONE call)
  → on success persist `QuizDefinition` + provenance from `AIRequestLog` → mark completed; on failure mark
  `failure_category` (no artifact), bounded RQ-retry like summaries.
- New prompt `prompts/quiz_generation/v1.yaml` (model/backend/max_tokens; `{{detailed_summary}}` injection;
  strict JSON output contract). Deterministic adapter returns 5 canned MCQs for `quiz_generation`.

**Attempt + scoring:**
- `POST …/quiz/attempt` (start) — `QuizAccessPolicy` (published + enrolled + detailed-summary-ready, else
  404/403 byte-identical to the 4.7 rules); snapshot questions (shuffled) into the attempt.
- `POST …/quiz/attempt/{id}/answer` — record `StudentAnswer`, return correct/incorrect **immediately**
  (correctness on option identity); a wrong answer creates a `MistakeRecord`.
- `POST …/quiz/attempt/{id}/submit` (or auto on last answer) — compute score; **insert `StudentActivityEvent`
  (`quiz_completed`) in the SAME txn** as the score write (rule 7).
- **Pagination envelope** (new, defined here, reused by glossary/conversations/events later): list endpoints
  (attempts, later mistakes) return `{ items: [...], total, limit, offset }`. Existing admin bare-arrays are
  NOT retrofitted (Stage 12 — finding).

## Thin UI scope (on the 4.9 system; mobile-first, §2.4)
- **`SectionQuiz.tsx`** inline in `StudentSectionView` after the summaries block — reuses the
  `SectionSummaries` bounded-polling pattern (states: not-yet/generating/available/unavailable via the
  Progress-Step + Badge conventions; failed = explicit text).
- **`QuizAttempt.tsx`** — question card with all answer-option states per §2.4 (selected / correct /
  incorrect / correct-not-chosen), **immediate feedback**, score screen, a **mistakes-bank notice** (no
  retake flow). Built from Button/Card/Badge/Modal/Progress as-built; token-only; no new public components
  (a missing role is a finding, not an improvisation).
- Generated client: regenerate → `api.quizzes.*` via the wrapper (rule 3).

## UI proof obligation
A student answers a question and sees **correct/incorrect feedback immediately** in a real browser against
the real backend — and a wrong answer **visibly becomes a recorded mistake**.

## Browser gate (deterministic pipeline, §14)
Student opens a lecture/lab with a completed detailed summary → post-class quiz **available** → starts attempt
→ generated questions appear → answers → **immediate feedback** → wrong answer creates a mistake → score →
**`quiz_completed` event inserted in the same txn as the score** (asserted in DB). Security: unpublished →
404, unenrolled → 404 (byte-identical), non-student → 403 — same two-surface discipline as 4.7.

## Exclusions
Recap / exam-prep / mistakes-bank **modes**; **retake-reinforcement BEHAVIOR** — 5a/5b CREATE the
`MistakeRecord` + the `quiz_completed` event but build ZERO retake logic (the `retake_correct_count` /
`show_in_retake_prefix` flip after N correct retakes is Stage 6; the fields exist per F-5-2 but the behavior
is excluded); leaderboards; graded exams; real tool/function-calling (F-5-1); the existing admin bare-array
pagination retrofit (Stage 12); Stage-6 question pool (schema must not preclude it — flagged, not built);
Stage 5.5 schedule fields.

## Findings to file (rule 13)
- **F-5-1** tool/function-calling deferred — reuse json+OutputValidator now; real tool-calling lands when the
  real provider is reachable (depends on F-C5/F-4.5-27).
- **F-5-2** Stage-6 question-pool shape — `QuizDefinition.content_json` + attempt snapshot chosen so a pool
  can be added without migration pain; the decision is Stage 6's.
- **F-5-3** pagination envelope introduced for new lists only, as a SHARED contract in `platform/query`
  (reused by glossary/conversations/events); existing admin bare-arrays not retrofitted → Stage 12.

## Verification
Backend `pytest` (schema/migration round-trip, generation, scoring, atomic event, policy 404/403, shuffling-
by-identity); §8 frontend gates; **full active Playwright suite + the new Stage 5 quiz gate green** on the
deterministic pipeline; one AI call per quiz asserted; event-in-same-txn asserted in DB.

## Proposed slices (each = sub-spec → plan → approval → build, per the gated loop)
- **5a** — schema + migration 0014 + `platform/events` + the generation flow (prompt + deterministic quiz
  output + enqueue-on-summary-complete + persist + provenance). Backend-verified.
- **5b** — attempt lifecycle (start/answer/submit), scoring, immediate-feedback contract, mistake creation,
  the atomic `quiz_completed` event, the pagination envelope. Backend-verified.
- **5c** — `SectionQuiz` + `QuizAttempt` UI + client regen + the browser gate (the UI proof) → FULLY VERIFIED.

## Open questions
- **O1 — RESOLVED** (umbrella lock 4): keep the `QuizDefinition`; `stale` derived at read from
  `source_transcript_checksum` (4.7 mechanism); available-but-stale; no hide / no auto-regenerate.
- **O2 — RESOLVED** (umbrella lock 5): `question_count`/`options_per_question` stored (default 5/4), generator
  reads them, no config UI.
- (none open)
