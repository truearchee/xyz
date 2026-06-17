# Status

_Last updated: 2026-06-17 — **Stage 6 IN PROGRESS — 6a per-section pool foundation BACKEND VERIFIED**
(uncommitted, on branch `stage-6`, off main head `a8cea6e`). 6a builds the Stage 6 question ENGINE — no
mode UI, no recap/exam_prep/mistakes_bank endpoints, no AssessmentScope, no post-class retrofit (those are
6b–6d). Migrations **0023** (`section_question_pools` + `pool_questions` + `quiz_questions.
source_pool_question_id` + the `ai_request_logs.feature` `'quiz_pool'` CHECK) and **0024**
(`mistake_records.source_pool_question_id` + the partial-unique pooled-upsert identity). New engine:
`pool_service` (one-call generation from the detailed summary, ready/generating partial-unique herd lock,
`content_json`-hash staleness atomic-swap → superseded, failure contract + explicit retry, pool-completion
fan-in), `sampling` (pure, seedable, recency bias + even cross-section spread + exhaustion-recycle),
`assembly_service` (scheduler-free two-level wait, snapshot-at-assembly immunity), `mistakes`
(ON-CONFLICT pooled upsert), `config` (named defaults). Additive `platform/llm`: `GeneratedQuizPool` +
`_validate_quiz_pool` + `GatewayFeature += quiz_pool` + a new `quiz_pool_generation/v1` prompt (the
post_class exactly-10 path untouched) — coordinated with Stage 7 in [[steps/findings-6-shared-infra]].
Reaper extended (prior-session 4.6c): pooled-attempt liveness (no false-reap while a pool generates) +
stuck-pool self-heal. Verified in the rebuilt `kyiv-backend` image against the `db` service: Alembic
`upgrade head → downgrade base → upgrade head` clean; `alembic heads` = `0024 (head)`; prompt drift guard
OK; 6a hard gate **14 tests** (6 sampler + 8 engine); full backend **490 passed, 137 warnings**; `ruff`
clean. Owner decisions D1–D4 locked (all spec-recommended); D4 sequences the post-class retrofit LAST,
superseding spec v2. ADR-047. See [[steps/stage-06/6a-pool-foundation]]._

_Prior: 2026-06-17 — **Stage 5.5 FULLY VERIFIED and migration-chain ready for merge.** Branch `stage-55`
rebased onto `origin/main`; Stage 5.5 migrations follow main linearly `0020 → 0021 → 0022`; dev reseed
expected Alembic `0022` (bumped to `0024` by Stage 6a). Browser gate GREEN; reference oracle exactly 28
sections; full active Playwright suite 12/12; backend 424 passed. See
[[steps/stage-05/5.5g-migration-chain-rebase]]._

_Prior: 2026-06-12 — **Stage 4.7 (student-facing summaries) FULLY VERIFIED — LANDED ON MAIN** (head
`0e0654f`): backend 389 passed; full active Playwright suite 11/11; ADR-034..039._

## Current state

**Stage 6 — Complete Quiz Modes — IN PROGRESS** (overview spec [[specs/stage-06/6-complete-quiz-modes]];
sub-sessions 6a→6d, each gated before the next). Migration block **0023–0028** (6a used 0023–0024;
0025–0028 reserved). The capacity decision (per-section pool + per-attempt sampling, ADR-047) is the spine.

- **6a — pool foundation — BACKEND VERIFIED** (this session). The engine + sampling/assembly/mistake-
  identity primitives, gate-proven. No student/lecturer surface yet.
- **6b — NOT STARTED.** Recap + exam_prep modes + AssessmentScope + authorization (migration 0025:
  `quiz_definitions` DROP NOT NULL on `module_section_id` + `scope_key` + `assessment_scope_id`); D1
  exam-prep pre-warm; section-eligibility + student published/assigned filter + 404 rules; multi-section
  visibility read.
- **6c — NOT STARTED.** Retake reinforcement (wire `upsert_pool_mistake` + the atomic flip-at-2 into
  `service.answer`) + mistakes-bank (per module, from snapshots, paginated) + event metadata (mode +
  multi-section scope) for all modes.
- **6d — NOT STARTED.** UI (compose 4.9 primitives, reuse `mcq.tsx` verbatim) + browser gate +
  real-provider smoke on the quiz-pool path + the post-class retrofit (D4, last, revertible) + full active
  E2E suite (rule 14). Stage 6 closes here; the roadmap status table flips then.

## Verification (6a)

```bash
# rebuilt kyiv-backend image; db service up (backend host :8000 held by a sibling stack → ran via `run`)
docker compose run --rm --no-deps backend sh -c "alembic upgrade head && alembic downgrade base && alembic upgrade head && alembic heads"
# … single head: 0024 (head)
docker compose run --rm --no-deps backend python -m tests.ci.prompt_drift_guard
# PROMPT DRIFT GUARD: OK
docker compose run --rm --no-deps backend pytest -q tests/test_quiz_sampling.py tests/test_quiz_pool.py
# 14 passed
docker compose run --rm --no-deps backend pytest -q
# 490 passed, 137 warnings in 68.95s
ruff check <changed files>
# All checks passed!
```

## Stage 6 documents
- Overview spec: [[specs/stage-06/6-complete-quiz-modes]]
- 6a spec: [[specs/stage-06/6a-pool-foundation]]
- 6a plan: [[plans/stage-06/6a-pool-foundation]]
- 6a report: [[steps/stage-06/6a-pool-foundation]]
- ADR: [[decisions/adr-047-section-question-pool-capacity]]
- Shared-infra coordination (Stage 7): [[steps/findings-6-shared-infra]]

## Open risks
- **Scheduler-free fan-in race (documented, ADR-047):** in the rare case a pool finishes before its
  waiting attempt commits (only realistic under a near-instant deterministic adapter; production pool
  generation is slow), the reaper backstops the attempt to `failed` → a clean Start Over re-assembles. No
  RQ scheduler is introduced (reserved for Stage 11.1).
- **`platform/llm` union/enum growth** is an additive textual merge point with Stage 7 — see the findings
  note; no behavioral coupling.
- **httpx ASGI-shortcut deprecations** (137 warnings) remain carried debt for Stage 4.9.

## Environment note
No source volume mount in `docker-compose.yml` (the `kyiv-backend` image bakes the code), so the backend
image must be **rebuilt** (`docker compose build backend`) before migrations/tests see new code. The
backend host port `:8000` is held by a sibling workspace stack, so migrations/tests run via
`docker compose run --rm --no-deps backend …` (no port binding) against the shared `db`/`redis` services.
