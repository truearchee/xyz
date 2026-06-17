---
type: session-report
stage: "06"
session: "6a"
slug: pool-foundation
status: complete
created: 2026-06-17
updated: 2026-06-17
spec: knowledge/specs/stage-06/6a-pool-foundation.md
plan: knowledge/plans/stage-06/6a-pool-foundation.md
commit: ""           # not yet committed (awaiting developer review)
---

# Session 6a — Report — Per-section pool foundation + capacity ADR

## Linked documents
- Overview spec: [[specs/stage-06/6-complete-quiz-modes]]
- Spec: [[specs/stage-06/6a-pool-foundation]]
- Plan: [[plans/stage-06/6a-pool-foundation]]
- Report: [[steps/stage-06/6a-pool-foundation]]
- Decision: [[decisions/adr-047-section-question-pool-capacity]]
- Coordination: [[steps/findings-6-shared-infra]]

## Summary
Built and gate-proved the Stage 6 question-engine: a durable, reusable **per-section question pool** keyed
`(section, model, promptVersion)` with one-call generation from the detailed summary, per-attempt seedable
recency-biased sampling + cross-section spread + exhaustion-recycle, snapshot-at-assembly immunity, a
one-active herd lock, the scheduler-free pool-completion fan-in, stale-pool atomic-swap, the
pool-generation failure contract + explicit retry, and the MistakeRecord pooled-upsert identity. **No mode
UI, no recap/exam_prep/mistakes_bank endpoints, no AssessmentScope, no post-class retrofit** (those are
6b/6c/6d). Migrations 0023–0024; additive `platform/llm` extensions coordinated for Stage 7.

## Files changed
(Source: `git diff --stat` + `git status`.)

**backend — new (engine):** `app/domains/quiz/pool_service.py`, `assembly_service.py`, `sampling.py`,
`mistakes.py`, `config.py`, `summary_text.py`; `app/platform/db/models/section_question_pool.py`,
`pool_question.py`; `alembic/versions/0023_section_question_pool.py`,
`0024_mistake_record_pool_identity.py`; `prompts/quiz_pool_generation/v1.yaml`.

**backend — additive edits:** `app/platform/db/models/__init__.py` (register 2 models),
`quiz_question.py` (+`source_pool_question_id`), `mistake_record.py` (+`source_pool_question_id` + the
upsert index); `app/platform/llm/models/quiz.py` (+`GeneratedQuizPool`), `models/prompt.py`
(`GatewayFeature += quiz_pool`), `validation.py` (+pool validator), `gateway.py` (union hints),
`provider.py` (pool fixture); `app/workers/queues.py` + `app/domains/quiz/jobs.py` (pool/assembly enqueue +
job wrappers); `prompts/CHECKSUMS.json` (new baseline).

**backend — modified prior sessions (see below):** `app/domains/recovery/reaper.py`, `rq_liveness.py`
(pooled-attempt liveness + stuck-pool reaping); `app/domains/admin/dev_reseed.py` (Alembic pin 0022→0024).

**backend — tests:** `tests/test_quiz_sampling.py` (6), `tests/test_quiz_pool.py` (8).

**knowledge:** `specs/stage-06/{6-complete-quiz-modes,6a-pool-foundation}.md`,
`plans/stage-06/6a-pool-foundation.md`, this report, `decisions/adr-047-section-question-pool-capacity.md`,
`steps/findings-6-shared-infra.md`.

## Verification
| Command | Result | Notes |
|---|---|---|
| `alembic upgrade head && downgrade base && upgrade head` | passed | round-trips through 0023→0024 on a fresh DB |
| `alembic heads` | `0024 (head)` | single head |
| `python -m tests.ci.prompt_drift_guard` | `PROMPT DRIFT GUARD: OK` | new `quiz_pool_generation/v1` registered |
| `pytest tests/test_quiz_sampling.py tests/test_quiz_pool.py` | `14 passed` | the 6a hard gate (see below) |
| `pytest -q` (full backend) | `490 passed, 137 warnings in 68.95s` | no regressions; +14 over the prior 476-ish |
| `ruff check` (all changed files) | `All checks passed!` | host ruff |

**6a hard gate (all proofs green):**
- **(1a) one-active herd lock** — `test_pool_one_active_lock_concurrent_first_requests`: **simultaneous**
  `ensure_section_pool` first-requests → exactly ONE pool row + ONE generation enqueue.
- **(1b) REUSE (stated explicitly — the backend ancestor of 6d's headline browser gate):** a second
  resolution against a `ready` pool issues **zero generation** and adds **no new `quiz_pool`
  `AIRequestLog` row**. Proven at two levels: `test_pool_generate_then_reuse_no_new_generation` (a reuse
  `ensure` keeps `captured.pools` flat and the `quiz_pool` log count at 1) **and**
  `test_multi_section_assemble_then_reuse_no_new_generation` (a second STUDENT's full assembly against the
  same `ready` pools keeps the `quiz_pool` log count at 2 — i.e. a second *assembly* generates nothing).
- **(2) sampling** — recency bias, even cross-section spread, exhaustion-recycle with no generation, seed
  determinism (`test_quiz_sampling.py`).
- **(3) MistakeRecord upsert identity** — a re-miss updates ONE record, counters preserved.
- **(4) snapshot immunity** — pool supersession leaves a started attempt byte-identical.
- **(5) reaper** — a pooled attempt is NOT reaped while its pool is `generating`; the stuck pool IS reaped;
  the no-pool-generating backstop reaps a truly-stuck attempt.

The 137 warnings are the pre-existing httpx ASGI-shortcut deprecations (carried debt, Stage 4.9). Frontend
`tsc` not run: 6a changed no frontend (it lands with the 6d UI).

## Deviations from spec
- **Staleness signal refined (owner-approved):** the pool stores `source_summary_content_hash` (sha256 of
  the detailed summary's `content_json`), **not** `source_transcript_checksum` as the v2 spec wrote — the
  latter is an upstream input that misses summary-only regenerations. Recorded in ADR-047.
- **Post-class retrofit sequenced to 6d (owner D4),** superseding spec v2's placement in 6a foundation.
- Migration allocation: 0023 (pools) + 0024 (mistake identity). The `quiz_definitions` multi-section
  change (DROP NOT NULL + `scope_key`) is **not** needed by the 6a engine (the sampler is a pure function;
  attempt-level tests use single/multi-section definitions with `module_section_id` set + `source_scope.
  sectionIds`), so it stays in 6b's migration (0025), as planned.

## Modified prior sessions
- Session 5.5d — `app/domains/admin/dev_reseed.py`: bumped `EXPECTED_ALEMBIC_VERSION` `0022 → 0024` (Stage
  6a advanced the head). The 5.5d dev-reseed precondition test asserts against this constant, so it stays
  green.
- Session 4.6c — `app/domains/recovery/reaper.py`, `rq_liveness.py`: additive pooled-attempt liveness
  (don't false-reap a pooled `generating` attempt while an in-scope pool generates) + stuck-pool reaping
  (self-heal the herd lock). post_class reaping is unchanged (the new check returns False for
  `quiz_mode='post_class'`); the existing reaper tests pass unchanged.

## Decisions made
ADR-047 — Per-section question pool: the Stage 6 capacity decision.

## Risks introduced
- The pool-completion **fan-in** + reaper backstop replace a scheduler. In the rare race where a pool
  finishes before its waiting attempt is committed (only realistic under a near-instant deterministic
  adapter; production pool generation is slow), the attempt is recovered by the reaper to `failed` → a
  clean Start Over re-assembles instantly. Documented in ADR-047; covered by the reaper backstop test.
- Additive `platform/llm` union/enum growth is a textual merge point with Stage 7 — see the findings note.

## Follow-ups
- 6b: AssessmentScope + recap/exam_prep modes + authorization (migration 0025: `quiz_definitions` DROP
  NOT NULL + `scope_key` + `assessment_scope_id`); D1 pre-warm.
- 6c: retake reinforcement (wire `upsert_pool_mistake` + the flip-at-2 into `service.answer`) + mistakes-
  bank + event metadata. **Carry-forward (owner):** for multi-section attempts (`module_section_id =
  NULL`), `completed_quiz` / `perfect_quiz_score` must POSITIVELY carry the scope reference (`quizMode` +
  in-scope `sectionIds` from `source_scope`, or `assessmentScopeId`) — not merely dodge the None-deref — so
  Stages 9/10/11 can attribute scope. Same transaction as the score.
- 6d: UI + browser gate + real-provider smoke (quiz-pool path) + post-class retrofit + full active E2E.

## Knowledge updates
- Filed the overview + 6a spec, the 6a plan, this report, ADR-047, the shared-infra findings note.
- STATUS.md overwritten; log.md appended. Roadmap status table NOT changed (Stage 6 closes at 6d).
- architecture/ not updated (no architecture map file tracks the quiz domain's internal modules; the
  spec/report trio + ADR are the authority).

## Close-the-loop checklist
- [x] Spec exists and approved
- [x] Plan existed and was approved before coding
- [x] Stayed in scope (deviations noted above)
- [x] Verification commands run; real output recorded
- [x] Report written from git diff + output, not memory
- [x] spec ↔ plan ↔ report links all resolve
- [x] STATUS.md overwritten; log.md appended
- [ ] architecture/ updated IF source paths changed — n/a (no quiz-internal architecture map)
- [x] ADR added (adr-047)
- [ ] open-questions.md updated — n/a (no unresolved questions; the fan-in race is documented in ADR-047)

## Change history
- 2026-06-17 — initial completion (uncommitted; awaiting developer review).
