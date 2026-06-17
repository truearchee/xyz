# Status

_Last updated: 2026-06-17 — **Stage 6 FULLY VERIFIED — CLOSED; roadmap row flipped** (on branch `stage-6`;
6a committed at `19af1d3`, 6b at `024ae91`, 6c at `5e32206`, 6d + closeout in this commit). The final
blocker — the rule-11 real-provider quiz-pool smoke — is now **GREEN**: one real K2Think call on the
`nvidia` reasoning route returned HTTP **200**, model echo **`MBZUAI-IFM/K2-Think-v2`** == expected,
`finish_reason: stop`, and a validating **`GeneratedQuizPool`** (24 questions, one correct per question)
on the `quiz_pool_generation` → `quiz_pool` feature path. The earlier 401/403 was a placeholder key in
`.env`, not an invalid credential; with the real key in place (gitignored, never committed) auth cleared.
The complete green set: focused backend **61 passed**, full backend **501 passed**, ruff clean, frontend
`type-check` clean, 5d preservation browser gate **1 passed**, 6d browser gate **1 passed**, screenshot set
captured, full active Playwright **14 passed**, and rule-11 real-provider smoke **PASS**. Operational
watch-item recorded: the real pool generation took **322s**, exceeding the default 240s reasoning timeout
(needed 540s) — raise `LLM_DETAILED_TIMEOUT_SECONDS` for the pool route in production. Detail:
[[steps/stage-06/6d-ui-browser-gate-postclass-retrofit]] and [[steps/stage-06/6d-real-provider-smoke]].
Below are prior Stage 6 summaries._

_Prior (6b): **Stage 6b recap + exam-prep + authorization BACKEND VERIFIED + COMMITTED** (`024ae91`).
Migration **0025** adds `assessment_scopes` and multi-section `quiz_definitions` (`module_section_id`
nullable + `scope_key` + `assessment_scope_id` + dedup index). Recap/exam-prep resolve eligible scopes to
SHARED definitions on the 6a engine; authorization pins 404-not-403, lecturer-on-module, published-only
student sampling, unified multi-section visibility, D1 pre-warm, and D3 all-or-wait. 6b also pulled forward
scope-aware event metadata and section/pool-aware mistake creation. Verified: 6b suite 7 passed; full
backend 497 passed; ruff clean; tsc exit 0. See [[steps/stage-06/6b-recap-examprep-authorization]]._

_Prior (6a): **Stage 6a per-section pool foundation BACKEND VERIFIED + COMMITTED** (`19af1d3`). 6a builds
the Stage 6 question ENGINE — no
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

**Stage 6 — Complete Quiz Modes — FULLY VERIFIED / CLOSED** (overview spec [[specs/stage-06/6-complete-quiz-modes]];
sub-sessions 6a→6d, each gated before the next). Migration block **0023–0029** (6a used 0023–0024;
0025–0029 reserved; Stage 7 owns 0030–0031 — updated 2026-06-17 per the Stage 7 lock). The capacity
decision (per-section pool + per-attempt sampling, ADR-047) is the spine. **Stage 7 coordination (locked):**
event-type + AIRequestLog feature names go through Stage 7's single shared registry (union-aware CHECK +
CI union test) — Stage 6 registers its names there, never a second copy; 6a's hard-coded `quiz_pool`
feature is a tracked reconcile-at-integration item (not a 6a reopen). See [[steps/findings-6-shared-infra]].

- **6a — pool foundation — BACKEND VERIFIED + COMMITTED** (`19af1d3`). The engine + sampling/assembly/
  mistake-identity primitives, gate-proven.
- **6b — recap + exam_prep + authorization — BACKEND VERIFIED + COMMITTED** (`024ae91`). Migration 0025
  (`assessment_scopes` + multi-section `quiz_definitions`: nullable section + `scope_key` +
  `assessment_scope_id` + dedup index). AssessmentScope lecturer CRUD (lecturer-on-module 403);
  recap/exam-prep scope resolution → canonical-key SHARED definition → 6a `start_pooled_attempt`;
  section-eligibility read (assignment/supplementary + unpublished excluded silently); unified
  `get_visible_attempt` (multi-section module-level; post_class S7 gate preserved); D1 pre-warm; D3
  all-or-wait; 404-not-403 for unassigned. Pulled forward from 6c (forced by multi-section completion):
  scope-aware event metadata + section/pool-aware `answer()` mistake creation. OpenAPI client regenerated;
  `tsc` green. **Verified:** single head **0025**; 6b suite **7 passed**; full backend **497 passed**; ruff
  clean; tsc exit 0. See [[steps/stage-06/6b-recap-examprep-authorization]].
- **6c — retake reinforcement + mistakes-bank — BACKEND VERIFIED + COMMITTED** (`5e32206`). Retake prefix snapshots
  active current-student mistakes first, then draws a fresh pool sample excluding prefixed pool questions.
  Correct source-quiz prefix answers advance `retake_correct_count` and clear `show_in_retake_prefix` at 2;
  duplicate answers do not count; mistakes-bank practice does not advance the source-quiz counter. The
  bank is per module (`course_modules`), paginated, own-student-only, and assembled synchronously from
  snapshots with no AI/pool generation. **Verified:** 6c+6b+6a focused gate **19 passed**; full backend
  **501 passed**; changed-file ruff clean; single head **0025**; client regenerated; tsc exit 0. See
  [[steps/stage-06/6c-retake-mistakes-bank]].
- **6d — FULLY VERIFIED; STAGE 6 CLOSED.** Student module quiz modes UI
  (2x2 selector, recap/exam-prep modals, generating state, retake-prefix banner, mistakes-bank entry) and
  lecturer AssessmentScope create/list UI are built against shipped source components/patterns. Post-class
  now starts through the Stage 6 pooled path, with the old Stage 5 generation functions retained as the
  revert path. The 6d Playwright spec captures desktop/mobile screenshots and DB-backed assertions for
  retake+bank, cross-mode mistakes-bank aggregation, exam-prep scope correctness, pool reuse, and the
  404/403 authorization set. **Verified:** focused backend **61 passed**; full backend **501 passed**; ruff
  clean; frontend `type-check` clean; 5d preservation gate **1 passed**; 6d browser gate **1 passed**; full
  active E2E **14 passed**; screenshot set captured; **rule-11 real-provider quiz-pool smoke PASS** (HTTP
  200, model echo `MBZUAI-IFM/K2-Think-v2`, `GeneratedQuizPool` validated). Roadmap row flipped to FULLY
  VERIFIED. See [[steps/stage-06/6d-ui-browser-gate-postclass-retrofit]] and
  [[steps/stage-06/6d-real-provider-smoke]].

## Verification (6d so far)

```bash
docker compose build backend
# Image kyiv-backend Built

docker compose run --rm --no-deps backend pytest -q tests/test_quiz_endpoints.py tests/test_quiz_pool.py tests/test_quiz_mistakes_bank.py tests/test_quiz_recap_examprep.py
# 34 passed, 15 warnings in 9.29s

docker compose run --rm --no-deps backend pytest -q
# 501 passed, 137 warnings in 73.63s (0:01:13)

ruff check backend/app/domains/quiz/generation_service.py backend/app/domains/quiz/service.py backend/app/domains/quiz/schemas.py backend/app/domains/recovery/reaper.py backend/app/platform/query/quiz_read.py backend/tests/test_quiz_endpoints.py
# All checks passed!

docker compose run --rm --no-deps backend alembic heads
# 0025 (head)

docker compose run --rm --no-deps backend alembic current
# 0025 (head)

cd frontend && npx tsc --noEmit
# exit 0

RUN_ID=$(cat .context/6d-run-id.txt); E2E_RUN_ID="$RUN_ID" PLAYWRIGHT_BASE_URL=http://localhost:3001 NEXT_PUBLIC_API_BASE_URL=http://localhost:8001 npx playwright test tests/e2e/5d-post-class-quiz.spec.ts --workers=1
# 1 passed (16.3s)

RUN_ID=$(cat .context/6d-run-id.txt); E2E_RUN_ID="$RUN_ID" PLAYWRIGHT_BASE_URL=http://localhost:3001 NEXT_PUBLIC_API_BASE_URL=http://localhost:8001 npx playwright test tests/e2e/6d-quiz-modes-browser-gate.spec.ts --workers=1
# 1 passed (27.7s)

npx playwright test --list
# Total: 14 tests in 12 files

RUN_ID=$(cat .context/6d-full-run-id.txt); E2E_RUN_ID="$RUN_ID" PLAYWRIGHT_BASE_URL=http://localhost:3001 NEXT_PUBLIC_API_BASE_URL=http://localhost:8001 npx playwright test --workers=1
# 14 passed (2.8m)

docker compose build frontend
# Image albuquerque-frontend Built

docker compose run --rm --no-deps backend python scripts/gate3_quiz_pool_smoke.py
# FAIL: LLM_PROVIDER must be 'k2think' (export it before running Gate 3).

docker compose run --rm --no-deps -e LLM_PROVIDER=k2think -e LLM_API_KEY= backend python scripts/gate3_quiz_pool_smoke.py
# FAIL: LLM_API_KEY is not set in this environment (rotate + export the key).

docker compose run --rm --no-deps -e LLM_PROVIDER=k2think backend python scripts/gate3_quiz_pool_smoke.py
# FAIL: provider auth error (401/403) — key not rotated/valid? Body redacted.
```

Real-provider quiz-pool smoke (rule 11) — **GREEN** with the valid key in the gitignored `.env`:

```bash
docker compose run --rm --no-deps \
  -e LLM_PROVIDER=k2think -e LLM_CONTEXT_FALLBACK_ENABLED=false \
  -e LLM_DETAILED_TIMEOUT_SECONDS=540 \
  -v "$PWD/backend:/app" -w /app \
  backend python scripts/gate3_quiz_pool_smoke.py
# response model echo : MBZUAI-IFM/K2-Think-v2  (expected MBZUAI-IFM/K2-Think-v2)  -> OK
# finish_reason 'stop'; elapsed 322.4s; status_code 200; GeneratedQuizPool 24 questions; one-correct-per-q OK
# PASS: quiz pool route returned the configured model id (rule 11) and a parseable pool.
```

(240s default reasoning timeout was insufficient — the real call took 322s, so 540s was used; recorded as a
production watch-item in [[steps/stage-06/6d-real-provider-smoke]].)

## Prior verification (6a)

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
- 6b spec: [[specs/stage-06/6b-recap-examprep-authorization]]
- 6b plan: [[plans/stage-06/6b-recap-examprep-authorization]]
- 6b report: [[steps/stage-06/6b-recap-examprep-authorization]]
- 6c spec: [[specs/stage-06/6c-retake-mistakes-bank]]
- 6c plan: [[plans/stage-06/6c-retake-mistakes-bank]]
- 6c report: [[steps/stage-06/6c-retake-mistakes-bank]]
- 6d spec: [[specs/stage-06/6d-ui-browser-gate-postclass-retrofit]]
- 6d plan: [[plans/stage-06/6d-ui-browser-gate-postclass-retrofit]]
- 6d report: [[steps/stage-06/6d-ui-browser-gate-postclass-retrofit]]
- 6d real-provider smoke: [[steps/stage-06/6d-real-provider-smoke]]
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
