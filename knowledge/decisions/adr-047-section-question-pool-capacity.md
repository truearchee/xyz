---
type: adr
stage: "6"
status: accepted
created: 2026-06-17
updated: 2026-06-18
related-session: knowledge/specs/stage-06/6a-pool-foundation.md
---

# ADR-047 — Per-section question pool: the Stage 6 capacity decision

## Linked documents
- Overview spec: [[specs/stage-06/6-complete-quiz-modes]]
- Spec: [[specs/stage-06/6a-pool-foundation]]
- Plan: [[plans/stage-06/6a-pool-foundation]]
- Report: [[steps/stage-06/6a-pool-foundation]]
- Related: [[adr-043-lazy-per-attempt-quiz-generation]], [[adr-046-quiz-generation-recovery]],
  [[adr-029-transcript-replacement-atomic-swap]], [[adr-044-structured-quiz-output-json-validator-authority]]

## Context
Stage 5 generates quiz questions **per attempt** (one reasoning-model call each). At exam scale that does
not hold: 30 students × a 6-section recap = ~180 Nvidia calls ≈ 18 minutes of queue (TPM/RPM binds, rule
15). The roadmap's stated mechanism — "generate per section into a pool; sample fresh combinations per
attempt" — is adopted here.

## Decision
Questions are generated **once per SECTION**, stored, and reused for every student, every mode, and every
attempt that touches that section. AI generation never runs twice for the same `(section, model,
promptVersion)`.

- **Two layers.** Layer 1 = the durable **`section_question_pools` + `pool_questions`** store, keyed
  `(module_section_id, model, prompt_version)`, generated in ONE call from the section's **detailed
  summary** (never the transcript — exclusion) through the existing 4.5 gateway/limiter/AIRequestLog
  chain, validated by a new additive `GeneratedQuizPool` branch of the OutputValidator (min ≤ n ≤ max, so
  a reasoning model over/undershooting the target still succeeds; post_class's exactly-10 path is
  untouched). Layer 2 = the **QuizDefinition** (scope, not questions); each ATTEMPT is assembled by
  SAMPLING the in-scope pools and SNAPSHOTTING into per-attempt `QuizQuestion`/`AnswerOption` rows.
- **`model` = the resolved reasoning-route model** (`model_for_backend("nvidia")` = what
  `AIRequestLog.model_id` records); `prompt_version` = the `quiz_pool_generation` prompt version. A prompt
  bump transparently moves new attempts to a fresh pool — same discipline as Stage 7's definition cache.
- **One-active herd lock.** Two partial-unique indexes on the key: one `WHERE status='ready'` (the live
  pool) and one `WHERE status='generating'` (the migration-0007 `ingestion_jobs` pattern). Simultaneous
  first-requests for an ungenerated section produce EXACTLY ONE generation; the rest attach. Lazy by
  default; the lecturer exam-prep pre-warm (Decision #1) is a 6b add at background priority.
- **Sampling.** Pure, seedable, recency-biased (exposure derived from the student's prior
  `QuizQuestion.source_pool_question_id` rows — no separate ledger at MVP), even cross-section spread,
  exhaustion-recycle (oldest-seen first, **no** new AI call). A fixed seed → a reproducible sample (the
  browser gate's deterministic anchor); a different attempt seed → an observably different combination.
- **Snapshot-at-assembly.** Sampled questions/options are copied + shuffled into the attempt, which then
  owns an immutable snapshot — the 4.6 atomic-swap (ADR-029) applied to quizzes. Pool invalidation /
  regeneration NEVER mutates an in-progress or completed attempt.
- **Staleness.** The pool stores `source_summary_content_hash` = sha256 of the detailed summary's
  `content_json` (the signal the attempt already trusts) — **not** `source_transcript_checksum`, which is
  an upstream input and would miss summary-only regenerations. On a hash mismatch the live pool is
  transitioned `ready → superseded` (frees the ready slot) and a fresh pool generates.
- **Failure contract.** Validator-reject / 5xx → bounded RQ retry (rule 15); the claim re-activates a
  retryable `failed` pool to `generating` so the retry regenerates. Retries exhausted → terminal `failed`;
  a new request surfaces it (no auto-retry storm) and an explicit `retry_section_pool` re-enqueues under
  the same lock. A multi-section attempt whose pool terminally failed fails NAMING the section — never
  hangs in "preparing".
- **Scheduler-free two-level waiting.** The worker has no RQ scheduler (reserved for Stage 11.1). An
  attempt sits `generating` until all its in-scope pools are ready; the pool that becomes ready **fans
  in** an idempotent assembly job (under the `quiz-generate:{attemptId}` id) for every waiting attempt.
  The stuck-row reaper is extended: a pooled `generating` attempt is **live** while any in-scope pool is
  `generating` (so it is not false-reaped between fan-ins), and a stuck `generating` **pool** is reaped to
  `failed`/`crashed` so the herd lock self-heals.
- **MistakeRecord upsert identity.** Stable key `(student_id, source_quiz_definition_id,
  source_pool_question_id)` (partial-unique) — re-missing the same pooled question in the same
  QuizDefinition updates ONE record. Counters are preserved on conflict (re-miss never resets progress;
  Decision #2 default). NULL-pool rows fall back to the Stage 5 `uq_mistake_records_attempt_question`.

## Reconciling with Stage 5's wording
Stage 5 said "pool per QuizDefinition." This refines it to **pool per section, sampled by
QuizDefinition** — the cost-optimal, reuse-maximal unit. For a post_class QuizDefinition (1:1 with a
section) the two coincide; for recap/exam_prep the QuizDefinition samples across several section pools.

## Consequences
The exam-week example drops from ~180 calls to **~6** (one per section), shared across all students — and
fewer where post_class already generated the pool. Proven in 6a (deterministic adapter, full gateway path):
one-active lock incl. simultaneous first-requests; reuse + retake with no new generation at section
granularity; recency bias + even spread + exhaustion-recycle; snapshot immunity under supersession; the
reaper's pooled-attempt liveness + stuck-pool self-heal; the mistake upsert identity. **Deferred by design
(D4):** the post_class retrofit onto this model lands LAST (6d), behind a clean revert path, so a shipped
FULLY VERIFIED surface is the last thing touched — until then two generation paths coexist intentionally.

## Amendment (2026-06-18, F-6e) — pool request sizing, route, and reasoning-route timeout

The capacity decision (pool-once, sample-per-attempt) is unchanged. What changed is the **per-call
sizing**, after live K2Think probing revealed how K2-Think-v2 actually behaves on this prompt:

- **Throughput is ~73–76 completion-tok/s on BOTH routes**; the model reasons inline and tends to ramble
  to fill `max_tokens` (`finish_reason='length'`), so **wall-clock ≈ `max_tokens` / 73**. The original
  `max_tokens: 32000` therefore meant ~440s, which crossed the 540s smoke timeout under variance — the
  root cause of the 6e smoke regression. It was NOT a provider hang and NOT the route.
- **Request trimmed to the real need:** pool count **24 → 16** (largest single draw is post_class's 10;
  16 keeps retake-variation headroom), `max_tokens` **32000 → 20000** (covers the ~13.4k-token answer
  with margin, caps wall-clock ~274s). Validator floor **16 → 12** so the model over/undershooting the
  16 target still validates while still exceeding the 10 draw. `POOL_TARGET_SIZE` /
  `_DETERMINISTIC_POOL_SIZE` kept in sync at 16.
- **Route stays nvidia.** cerebras is the same model at the same speed and its 32768 window cannot hold a
  ~20k completion; `metadata.use_nvidia` is performance-inert (`backend_route_source='requested'`,
  ADR-025). No routing split was added.
- **Reasoning-route timeout 240 → 330, lease TTL 300 → 360.** The trimmed pool still needs ~274s, so 240
  is insufficient even after the work cut; 330 ≈ 1.2× the reduced worst case, well under the 540 owner
  ceiling. This resolves the carried "reasoning-route timeout" debt: root cause = oversized `max_tokens`
  driving a ramble-to-cap generation, not a tight timeout per se.
- **Non-determinism is absorbed by retry.** At temp 0 the provider still varies run-to-run (occasional
  truncation → `invalid_output`); the existing bounded RQ retry (`AI_RQ_RETRY_MAX=3`) recovers it, and
  the rule-11 smoke now mirrors that retry policy. Evidence + the green smoke:
  [[steps/stage-06/6d-real-provider-smoke]] (2026-06-18 section).
