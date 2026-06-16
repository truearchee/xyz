# Status

_Last updated: 2026-06-16 - **Stage 5.5a (schedule-driven section generation) BACKEND VERIFIED + committed at `76f496f`; 5.5b e2e suite rework applied (runtime green pending a free env).** On branch `stage-55` (off main `5cd5870`). Replaced the fixed 4-section template with schedule-driven generation: module creation requires a `schedule` (weekday × date-range) and generates lecture+lab sections with `week_number`/`session_date` synchronously in the creation transaction; missing schedule → **422**. Migration **0020** (nullable `week_start_day`/`session_pattern` jsonb/`quiz_day` on `course_modules`; reuses `starts_on`/`ends_on`; `down_revision='0013'`, rebase seam at merge). Pure `generate_sections` + the **28-section reference oracle** (11 May–26 Jun 2026, Mon/Tue/Wed lecture + Thu lab + Fri quiz day → 28 = 21 lectures + 7 labs, max week 7, 0 Friday). Verified (isolated `.context/dc-55a.yml`, no port collision with `test2`): `alembic upgrade head`→0020 single head + round-trip; **pytest 408 passed** (incl. atomicity + no-double-generate); ruff clean; OpenAPI client regenerated; **tsc exit 0** (minimal CreateModuleForm contract-compat, with a visible on-form note that the pattern is interim; picker+preview → 5.5e). **Known-red (PREDICTED, not yet observed):** the 7 active Playwright specs select sections by hardcoded title (`'Lecture 1'`/`'Lab 1'`/`'Assignment 1'`) which schedule titles no longer match, and 4.3.5e needs the now-ungenerated `assignment` section. They seed their OWN per-run modules and NONE consume the 5.5b resolver, so the rework is a **5.5b fix-now task** (deterministic titles / `type` selection / direct-seed the assignment section) — NOT deferred to 5.5d/5.5e. **5.5b opens by running the suite once for an OBSERVED failure list** (each red traced), fixing all fixable, quarantining only genuinely resolver-blocked specs (expected: none) with a close-out grep gate. Note: "no module without a schedule" is application-enforced only (0020 columns nullable; no DB constraint). ADR-040. **5.5b e2e rework (Path B) — APPLIED:** Neo's attributable run = **10 red / 1 pass, all mapped to prediction** (no 9th cause; 4.3.5b pass confirmed; quarantine=0 shown). Fixes: `nthSectionOfType` selection swap across 6 specs (throws on miss → fixes 4.5d-fault TypeError), 4.7-stage3 title assertions rewritten, 4.3.5c form fills new required date inputs, 4.3.5e pinned to a minimal schedule + `db.mjs insertSection` + direct-seeded assignment. `playwright --list` 11/9 clean; logic reviewed; quarantine 0. Runbook [[steps/e2e-run-procedure]]. **Runtime green PENDING** sole port ownership (kyiv holds :8000). Next → 5.5b feature work (metadata edit + D13 + `platform/query` resolver), separate commits._

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

- **Merge-time migration collision:** Stage 5 uses 0014-0020 while sibling work also used 0014-0016.
  Renumber/rebase one side before landing on `main`.
- **AIRequestLog mid-call crash residual:** still accepted and logged in [[open-questions]]; fixing it
  needs a broader AIRequestLog-to-source linkage, not a 5e repair.

## Environment note

The local `kyiv` Docker stack used for 5e has db/redis internal-only, backend on `localhost:8000`, and
frontend on `localhost:3001`; tests no longer assume the frontend origin is `localhost:3000`.
