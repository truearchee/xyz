# Status

_Last updated: 2026-06-17 - **Stage 5.5 FULLY VERIFIED and migration-chain ready for merge.** Branch `stage-55` is rebased onto `origin/main` (`15595c4`, Stage 5 merged; main migration head `0020`). Stage 5.5 migrations now follow main linearly: `0021_module_schedule_config.py` (`down_revision = "0020"`) then `0022_section_asset_kind.py` (`down_revision = "0021"`). Dev reseed now expects Alembic `0022`. Verification ran in the rebuilt isolated `.context/dc-55a.yml` backend stack: `alembic upgrade head` applied `0013 -> ... -> 0020 -> 0021 -> 0022`; `alembic downgrade -1` ran `0022 -> 0021`; `alembic upgrade head` re-applied `0021 -> 0022`; `alembic heads` and `alembic current` both reported `0022 (head)`. Host `cd backend && alembic upgrade head` was attempted first and failed before migration execution because the host Python lacks `pgvector`; Docker is the documented repo path. See [[specs/stage-05/5.5g-migration-chain-rebase]], [[plans/stage-05/5.5g-migration-chain-rebase]], and [[steps/stage-05/5.5g-migration-chain-rebase]]._

_Prior: 2026-06-17 - **Stage 5.5d dev reseed VERIFIED; Stage 5.5 remains IN PROGRESS.** On branch `stage-55` (off main `5cd5870`). 5.5a is committed at `76f496f`: schedule-driven module creation requires a `schedule`, generates lecture/lab sections with stored `week_number`/`session_date`, and migration `0020` adds nullable schedule provenance (`week_start_day`, `session_pattern`, `quiz_day`) to `course_modules`. 5.5b e2e rework is committed at `ab017db` (fixes applied, `playwright --list` clean, runtime green pending sole port ownership); 5.5b backend feature work is committed at `5a7fb15` (metadata PATCH endpoint + D13 recompute guard + stored-week resolver, full backend **413 passed**). 5.5c is committed at `adbd507`: `section_assets.asset_kind` via migration `0021`, lab `.ipynb` attachments, backend streaming download headers, upload-time lab `dueAt`, no-pipeline DB proof, full backend **418 passed**, frontend `tsc --noEmit` exit 0. 5.5d adds dev-only reseed tooling and ADR-043. No authored per-module schedule map exists, so reseed explicitly uses the reference schedule for all recreated dev modules. Actual dev run: stage-55 DB migrated `0020 -> 0021`; 16 modules replaced; 962 old sections deleted; 16 modules recreated; 448 stamped sections generated; legacy template titles = 0; one published lab fixture has `{attachment, processable}` assets. Verified: targeted reseed tests **3 passed**; full backend **421 passed, 119 warnings**; `ruff check backend` clean. Next -> 5.5e thin UI/browser gate/full active E2E suite._

_Prior: 2026-06-12 - **Stage 4.7 (student-facing summaries) FULLY VERIFIED — LANDED ON MAIN.** Human-stamped after the P1 assertion-strength audit + Steps 1–3 (4.6d-P1 independence gate, two attributable merges, full re-verification on main). **Verified ON MAIN HEAD `0e0654f`:** backend **389 passed**; full active Playwright suite **11/11** (9 success serial + 2 fault: 4.3.5b/c/e, 4.4, 4.5d-summary-browser + fault ×2, 4.6d ×2 reload-free, 4.7-stage3-content-visibility, 4.7-student-summaries). 4.7a backend boundary: `StudentSummaryAccessPolicy` (§5: row R 403 before lookup; D/P/I byte-identical 404), §6 precedence (corruption≠supersession DISTINCT + logged, two pinned tests), scoped read model (§8.6 MODULE-LEVEL join, >1-active fail-safe, no fetch-then-branch), server-side markdown shaping, Option-B endpoints + coarse list, §8.3 hygiene, `Cache-Control: private, no-store`, migration 0013. 4.7b UI: thin student section page (4 per-slot states + bounded polling + react-markdown raw-HTML-off). **P1 (Stage 3 content-visibility E2E) RESTORED + GREEN (no drift).** Review R1 (sentinel canary strengthened, non-vacuous), R2 (`--workers=1` = CAPACITY: embed RQ-retries 3×[30,120,300]s, non-terminal, GAP ruled out — non-blocking), R3 (row-3 unit test added) all resolved. **4.6d-P1 (F-4.6d-3 fix) also LANDED on main** (independently verified: 3 attributable regression tests + e2e reload-free) via merge `fe9d924`; 4.7 via `0e0654f`. ADR-034..039. Dev `xyz_lms` at 0013. On branch `main`. Next → 4.8 (staging deploy)._

## Current state

Stage 5 is **FULLY VERIFIED** on this branch and now has a follow-up review-fix session:

- 5a foundation: quiz/event schema, EventRecorder, pagination envelope, availability read model, DTOs.
- 5b generation/recovery: lazy post-class quiz generation through the shared LLM gateway, stable RQ job id
  `quiz-generate:{attemptId}`, `generation_job_id` stamped after enqueue, reaper liveness wired.
- 5c HTTP surface: availability/start/detail/answer/complete/attempts aggregate.
- 5d UI/gates: student quiz panel, browser gate green, real-provider smoke green and re-confirmed at
  `finish_reason='stop'` after `max_tokens` was raised to 16000.
- 5e review fixes: dynamic CORS health test, generation-job provenance repair, missing CHECK negative
  tests, pagination-doc reconciliation, stale report cleanup.

Current verification from 5e:

```bash
docker compose exec -T backend pytest -q tests/test_health.py
# 4 passed, 4 warnings in 0.02s

docker compose exec -T backend pytest -q tests/test_db_spine.py tests/test_quiz_schema.py tests/test_event_recorder.py tests/test_quiz_schemas_dto.py tests/test_quiz_generation.py tests/test_quiz_endpoints.py
# 61 passed, 15 warnings in 16.57s

docker compose exec -T backend pytest -q
# 442 passed, 126 warnings in 55.20s

docker compose exec -T frontend npx tsc --noEmit
# exit 0
```

## Stage 5 documents

- Stage spec: [[specs/stage-05/5-shared-quiz-engine-event-spine]]
- 5a report: [[steps/stage-05/5a-quiz-foundation]]
- 5a spec: [[specs/stage-05/5a-quiz-foundation]]
- 5a plan: [[plans/stage-05/5a-quiz-foundation]]
- 5b report: [[steps/stage-05/5b-quiz-generation-recovery]]
- 5b spec: [[specs/stage-05/5b-quiz-generation-recovery]]
- 5b plan: [[plans/stage-05/5b-quiz-generation-recovery]]
- 5c report: [[steps/stage-05/5c-answer-feedback-scoring-retake]]
- 5c spec: [[specs/stage-05/5c-answer-feedback-scoring-retake]]
- 5c plan: [[plans/stage-05/5c-answer-feedback-scoring-retake]]
- 5d report: [[steps/stage-05/5d-student-ui-browser-gate]]
- 5d spec: [[specs/stage-05/5d-student-ui-browser-gate]]
- 5d plan: [[plans/stage-05/5d-student-ui-browser-gate]]
- 5d real-provider smoke: [[steps/stage-05/5d-real-provider-smoke]]
- 5e report: [[steps/stage-05/5e-review-finding-fixes]]
- ADRs: [[decisions/adr-040-activity-event-spine]], [[decisions/adr-041-pagination-envelope]],
  [[decisions/adr-042-quiz-availability-computed-read-only]], [[decisions/adr-043-lazy-per-attempt-quiz-generation]],
  [[decisions/adr-044-structured-quiz-output-json-validator-authority]],
  [[decisions/adr-045-airequestlog-decoupled-gateway-generalized]], [[decisions/adr-046-quiz-generation-recovery]]

## Open risks

- **Stage 5.5 migration collision resolved:** Stage 5 now owns `0014` through `0020` on main; Stage 5.5
  has been rebased to `0021 -> 0022` with a single Alembic head.
- **AIRequestLog mid-call crash residual:** still accepted and logged in [[open-questions]]; fixing it
  needs a broader AIRequestLog-to-source linkage, not a 5e repair.

## Environment note

The local `kyiv` Docker stack used for 5e has db/redis internal-only, backend on `localhost:8000`, and
frontend on `localhost:3001`; tests no longer assume the frontend origin is `localhost:3000`.
