# Status

_Last updated: 2026-06-17 — **Stage 6 IN PROGRESS — 6c retake + mistakes-bank BACKEND VERIFIED**
(on branch `stage-6`; 6a committed at `19af1d3`, 6b committed at `024ae91`). 6c adds the backend retake
mistake-review prefix, cumulative source-quiz flip-at-2, and per-module own-student-only mistakes-bank
list/start from snapshots (no AI/pool generation). OpenAPI client regenerated, tsc green; full backend
**501 passed**, single head **0025** (no 6c migration). Detail:
[[steps/stage-06/6c-retake-mistakes-bank]]. Below are prior Stage 6 summaries._

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

**Stage 6 — Complete Quiz Modes — IN PROGRESS** (overview spec [[specs/stage-06/6-complete-quiz-modes]];
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
- **6c — retake reinforcement + mistakes-bank — BACKEND VERIFIED** (this session). Retake prefix snapshots
  active current-student mistakes first, then draws a fresh pool sample excluding prefixed pool questions.
  Correct source-quiz prefix answers advance `retake_correct_count` and clear `show_in_retake_prefix` at 2;
  duplicate answers do not count; mistakes-bank practice does not advance the source-quiz counter. The
  bank is per module (`course_modules`), paginated, own-student-only, and assembled synchronously from
  snapshots with no AI/pool generation. **Verified:** 6c+6b+6a focused gate **19 passed**; full backend
  **501 passed**; changed-file ruff clean; single head **0025**; client regenerated; tsc exit 0. See
  [[steps/stage-06/6c-retake-mistakes-bank]].
- **6d — NOT STARTED.** UI (compose 4.9 primitives, reuse `mcq.tsx` verbatim) + browser gate +
  real-provider smoke on the quiz-pool path + the post-class retrofit (D4, last, revertible) + full active
  E2E suite (rule 14). Stage 6 closes here; the roadmap status table flips then.

## Verification (6c)

```bash
docker compose run --rm --no-deps backend pytest -q tests/test_quiz_mistakes_bank.py tests/test_quiz_recap_examprep.py tests/test_quiz_pool.py
# 19 passed
docker compose run --rm --no-deps backend pytest -q
# 501 passed, 137 warnings in 71.88s
ruff check <changed backend files>
# All checks passed!
docker compose run --rm --no-deps backend alembic heads
# 0025 (head)
cd frontend && npx tsc --noEmit
# exit 0
```

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
