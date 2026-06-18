---
type: session-spec
stage: 09
session: "9"
slug: my-progress-dashboard
status: approved
created: 2026-06-18
updated: 2026-06-18
owner: developer
plan: knowledge/plans/stage-09/9-my-progress-dashboard.md
report: knowledge/steps/stage-09/9-my-progress-dashboard.md
---

# Session 9 — My Progress Dashboard

> Filed from `.context/attachments/SUNQVC/pasted_text_2026-06-18_14-56-06.txt`.
> Scope confirmed by the developer request: "PLEASE IMPLEMENT THIS PLAN".

## Linked documents
- Spec: [[specs/stage-09/9-my-progress-dashboard]]
- Plan: [[plans/stage-09/9-my-progress-dashboard]]
- Report: [[steps/stage-09/9-my-progress-dashboard]]
- Roadmap: [[roadmap]]
- Design plan: [[design-plan]]
- Design system: [[design-system]]
- ADR: [[decisions/adr-052-single-tenant-mvp]]
- Finding: [[steps/stage-09/findings-design-doc-reality-gap]]

## Goal
Build the Stage 9 My Progress dashboard so a student can see seeded-but-real progress data, set a target grade, and receive a deterministic forecast, including the impossible state.

## Why now
Stage 9 follows the roadmap after quiz, schedule, glossary, and assistant foundations. It creates deterministic progress/forecast data models without making any AI calls and prepares data surfaces later consumed by gamification and analytics.

## Read first
- `.context/attachments/SUNQVC/pasted_text_2026-06-18_14-56-06.txt`
- `knowledge/roadmap.md`
- `knowledge/design-plan.md` §2.7
- `knowledge/design-system.md`
- `knowledge/steps/stage-09/findings-design-doc-reality-gap.md`

## Source paths likely touched
- `backend/alembic/versions/0038_*.py`, `0039_*.py`, `0040_*.py`
- `backend/app/platform/db/models/*progress*.py`, `backend/app/platform/db/models/*grade*.py`
- `backend/app/domains/progress/*`
- `backend/app/platform/query/progress_read.py`
- `backend/app/api/routers/progress.py`, `backend/app/main.py`
- `backend/scripts/seed_progress_demo.py`
- `frontend/src/app/(app)/student/page.tsx`
- `frontend/src/app/(app)/student/progress/page.tsx`
- `frontend/src/features/progress/*`
- `frontend/src/lib/api/*` generated client and wrapper
- `tests/e2e/9-my-progress.spec.ts`
- `tests/e2e/fixtures/db.mjs`

## Build
- Record the single-tenant MVP ADR before adding tables.
- Use migrations only in the assigned block `0038` through `0043`.
- Add grade scheme, grade boundary, grade component, student grade record, active target-grade goal, week progress snapshot, and topic mastery snapshot tables.
- Implement a pure Decimal forecast engine with states `final_no_remaining`, `achieved`, `impossible`, `on_track`, `at_risk`, and `requires_high_score`.
- Persist the target-grade goal only; forecast computation is read-only and never creates forecast rows.
- Add current-user-only student progress APIs:
  - `GET /student/progress`
  - `GET /student/modules/{module_id}/progress`
  - `PUT /student/modules/{module_id}/target-grade`
- Return only privacy-safe read models. Do not expose other student identifiers, individual grade records, standings, or component scores.
- Add idempotent demo seed and deterministic E2E fixture helpers. Both realize all six forecast states.
- Build the My Progress UI in the current inline-style idiom because the claimed Stage 4.9 Tailwind/shared component system is not present in this checkout.

## Do not build
- No real-student data.
- No grade-entry UI.
- No lecturer/admin grade-scheme setup form.
- No live LMS integration.
- No rankings, named comparisons, mental-health diagnosis, or risk labelling.
- No AI calls anywhere in Stage 9.
- No gamification logic beyond a placeholder.
- No generic Add Goal modal or goal types beyond target grade.
- No Tailwind/component-library import from the 4.9f branch.

## Data model changes
- Migration `0038`: grade foundation tables:
  - `course_grade_schemes`
  - `grade_boundaries`
  - `grade_components`
  - `student_grade_records`
  - `student_target_grade_goals`
- Migration `0039`: progress snapshot tables:
  - `student_progress_snapshots`
  - `student_topic_mastery_snapshots`
- Migration `0040`: benchmark/config support only if needed. Prefer fields on `course_grade_schemes` unless a separate table is necessary.
- New tables carry no `organization_id` per ADR-052.

## API changes
- `GET /student/progress` returns a current-student module-grid summary.
- `GET /student/modules/{module_id}/progress` returns a current-student module detail with forecast, trend, topic mastery, benchmark, target, and available target grades.
- `PUT /student/modules/{module_id}/target-grade` upserts the one active target-grade goal for the current student/module and returns the recomputed module progress detail.
- All routes are student-only, `Cache-Control: private, no-store`, and current-user-only. There is no `studentId` route or query parameter.

## Worker / job changes
None. Stage 9 has no AI and no worker jobs.

## Authz rules
- 401 and 403 follow existing wrapper conventions.
- Non-student role receives 403 before resource lookup.
- Unassigned/inactive module returns pinned 404.
- A student cannot address another student's progress because routes are current-user-only; negative tests also cover unassigned module access as 404.

## Verification
- `docker compose run --rm -v "$PWD/backend:/app" -T backend pytest -q` -> green.
- `docker compose run --rm -v "$PWD/backend:/app" -T backend pytest -q tests/test_progress_forecast.py tests/test_progress_api.py` -> green.
- Alembic round-trip `upgrade head -> downgrade base -> upgrade head`; `alembic heads` single head.
- `bash scripts/generate-api-client.sh` -> generated client updated.
- `cd frontend && npx tsc --noEmit` -> exit 0.
- `PLAYWRIGHT_BASE_URL=http://localhost:3001 E2E_RUN_ID=<run-id> npx playwright test tests/e2e/9-my-progress.spec.ts --workers=1` -> green.
- `PLAYWRIGHT_BASE_URL=http://localhost:3001 E2E_RUN_ID=<run-id> npx playwright test --workers=1` -> full active suite green at close.

## Knowledge updates required
- `knowledge/plans/stage-09/9-my-progress-dashboard.md`
- `knowledge/steps/stage-09/9-my-progress-dashboard.md`
- `knowledge/decisions/adr-052-single-tenant-mvp.md`
- `knowledge/steps/stage-09/findings-design-doc-reality-gap.md`
- `knowledge/STATUS.md`
- `knowledge/log.md`
- `knowledge/roadmap.md`
- `knowledge/open-questions.md` only if unresolved items remain.
- `knowledge/architecture/` only if a source-path architecture map needs updating.

## Done means
Forecast engine deterministic and tested across all six states and edge cases; scheme weights validated; target persists and forecast writes nothing; progress, mastery, and benchmark render from seeded DB rows; class benchmark is aggregate-only with suppression while the caller's own quiz average may be shown; no `AIRequestLog` rows are created by Stage 9 flows; negative auth tests pass; browser observes live target recompute including impossible state; full active E2E suite is green; knowledge loop is closed.

## Developer source content
The supplied spec is the authority for exact product scope. Key locked content preserved from the pasted document:

- Stage 9 answers: "how am I doing, and what do I need to hit my target grade?"
- This stage is read-heavy and math-heavy, not AI-heavy. Every number is deterministic and no model calls are allowed.
- Data is seeded fake data on realistic profiles, written to real DB tables on the production-like schema.
- The only live student interaction is setting/changing a target grade per module.
- Prerequisites:
  - Single-tenant MVP ADR.
  - Design Plan §2.7 and `design-system.md` read before implementation.
  - Stage 5/5.5/6 read models confirmed; Stage 9 reads via `platform/query`.
- Reconciliation:
  - Forecast taxonomy extends Design Plan §2.7 from four treatments to six engine states by adding `achieved` and `final_no_remaining`.
  - Benchmark metric is quiz average, not formal grade standing.
  - Generic goal creation is deferred; target-grade goal only.
- Numeric conventions:
  - `GradeComponent.weight` is a decimal fraction in DB (`0.15`, not `15`).
  - `StudentGradeRecord.percentageScore` is `0-100`.
  - Weighted points are `percentageScore * weight`.
  - Scheme weights sum to `1.0000` within Decimal tolerance.
  - A component is graded only when that student has a grade row.
  - Engine arithmetic uses Decimal, not float.
- Current standing:
  - `earnedSoFar = sum(percentageScore * weight)` over graded components.
  - `remainingWeight = sum(weights)` over not-yet-graded components.
  - `maxReachable = earnedSoFar + remainingWeight * 100`.
  - `minReachable = earnedSoFar`.
- Forecast decision order:
  - `FINAL_NO_REMAINING` when `remainingWeight = 0`.
  - `ACHIEVED` when `minReachable >= targetPoints`.
  - `IMPOSSIBLE` when `maxReachable < targetPoints`.
  - Otherwise compute required remaining average and classify by `onTrackMax=70`, `atRiskMax=85`, and `100`.
- Impossible UI:
  - Headline: `Best grade still reachable: B+`.
  - Detail explains that even 100% remaining cannot reach the target.
- Target persistence:
  - One active `target_grade` goal per `(studentId, moduleId)`.
  - Changing the target updates the one row.
  - No persisted `GradeForecast` table.
- Scenario matrix:
  - Student A / Module 1 / target A- -> `on_track`.
  - Student B / Module 1 / target A -> `at_risk`.
  - Student C / Module 2 / target A -> `requires_high_score`.
  - Student D / Module 2 / target A -> `impossible`.
  - Student E / Module 1 / target B -> `achieved`.
  - Student F / Module 1 / all graded -> `final_no_remaining`.
- Progress snapshots:
  - `StudentProgressSnapshot` is week-scoped and append-style.
  - Unique seeded MVP key is `(studentId, moduleId, weekNumber)`.
  - Topic mastery topic is a lecture/lab section.
- Benchmark:
  - Class quiz average aggregate only.
  - The requesting student's own quiz average may be returned for the "Your average" UI.
  - No named comparison, ranking, or individual grade/standing exposure.
  - Suppress below stored cohort minimum.
- Seeds:
  - Demo seed is persistent, idempotent, rich, and resettable.
  - E2E fixtures are small, deterministic, run-scoped, and cleanup-safe.
- Quality bar:
  - State by icon + label, not color alone.
  - "How this is calculated" expandable.
  - Charts include accessible text fallbacks.
  - Target control is keyboard-reachable and auto-saves.
  - Reduced-motion respected.

## Amendments
- 2026-06-18: Benchmark privacy clarification after independent review: `studentAverage` may
  contain only the requesting student's own quiz average. The class benchmark remains aggregate-only
  (`classAverage` + `cohortSize`), and the endpoint must never expose any other student's identity,
  per-student row, component score, standing, or individual quiz average.
