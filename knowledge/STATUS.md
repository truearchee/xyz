# Status

_Last updated: 2026-06-22 — **Stage 11.7 corrective AgentRun requeue recovery is FULLY VERIFIED.** Existing `queued`/`failed` `AgentRun`s now reconcile against the stable RQ job id before enqueueing, genuinely live RQ jobs are not duplicated, focused scheduler/API tests are green (`17 passed`), the 11.1 browser gate is green, the rule-14 full active Playwright split is green (`25` success + `2` fault), and Alembic remains `0059 (head)`. **Stage 11 remains feature-complete (11.1–11.6), with the 11.7 recovery fix applied.** Per owner: do not rebase or merge yet._

## Current branch
- Branch: `stage-11-ai-analytics`
- Target branch: `origin/main`
- Current base head before local changes: `4756f72`
- Migration block: `0056-0072`
- Migrations used: `0056`, `0057`, `0058`, `0059`
- Current Alembic head verified in Docker: `0059 (head)` (below the Stage-10 `0060` block)

## Stage 11.7 Corrective Recovery — Fully Verified
- **Stuck-run recovery:** fixed the AgentRun commit-before-RQ-enqueue gap. Later scheduler ticks or manual
  trigger retries now re-enqueue existing `queued`/`failed` runs instead of leaving them stranded.
- **Stable job identity:** the stable `agent-run-{run_id}` RQ job id remains authoritative. The helper reconciles
  against RQ first; live jobs (`queued`, `started`, `deferred`, `scheduled`) suppress duplicate enqueue.
- **Stale job recovery:** stale non-live RQ jobs are deleted before enqueueing the same stable job id again.
- **Idempotency preserved:** Postgres `AgentRun.idempotency_key` still chooses the run row; RQ reconciliation only
  fixes the queue handoff. Manual/scheduler paths remain AI-free and do not touch `AIRequestLog`.
- **No migration:** Alembic head stays `0059 (head)`.

## Stage 11.7 Verification
- Compile: targeted `python -m compileall ...` for the queue/scheduler/router/test files -> pass.
- Focused scheduler/API tests: `tests/test_scheduler.py tests/test_analytics_api.py` -> `17 passed`.
- 11.1 browser gate: `tests/e2e/11.1-roster-risk-scheduler.spec.ts` -> `1 passed`.
- Full active Playwright suite, rule-14 split, clean DB, `.env.e2e` sourced, deterministic provider:
  success set `--grep-invert "fault gate"` -> `25 passed (6.3m)`;
  fault set `4.5d-summary-fault.spec.ts` -> `2 passed (27.7s)`.
- Alembic/current stack: `0059 (head)`.
- Unrelated tracked Stage 6 screenshot churn restored; `knowledge/open-questions.md` is clean.

## Stage 11.6 Delivered — Fully Verified
- **Grade-forecast advice:** added `GET /student/modules/{module_id}/forecast-advice` — a student-self AI
  note that EXPLAINS the Stage 9 deterministic forecast on the My-Progress surface. AI phrases only; every
  number is Stage 9's (the `calculate_forecast` engine is reused through one shared input-assembly path,
  `build_forecast_input`; no new grade math).
- **Lazy + cached AI (mirrors 11.2):** one BACKGROUND call per `(student, module)` advice row, regenerated
  only on `inputHash`/promptVersion change, provenance recorded, template fallback when AI is down. Advice
  is lazy-on-read (no `AgentRun`/scheduler dependency). Route `grade_forecast_advice/v1` =
  `MBZUAI-IFM/K2-Think-v2` / `cerebras` (ADR-059).
- **Two validators:** numeric/fact consistency + a state-aware contradiction guard, plus the reused 11.2
  student-copy safety guard (extended with an impossible-case shaming lexicon). The impossible case is
  honest + constructive (names the best reachable grade, states the target is not possible, no false hope,
  no shaming, no diagnosis).
- **Surface:** tone-neutral `ForecastAdviceCard` in the My-Progress forecast area (after the forecast
  panel, before the gamification block — untouched). Template renders immediately; AI swaps in via a
  backoff poll with an `aria-live`, height-stable fill.
- **Reproducibility:** advice row carries `algorithmVersion` + `inputHash` + `sourceCutoffAt` +
  `forecastState`; AI cache carries `aiProvenance { modelId, promptVersion, inputHash, generatedAt }`.
- **Migration `0059`:** `student_forecast_advice` (one row per student/module) + widened
  `ai_request_logs.feature` CHECK/tuple for `grade_forecast_advice`. No Stage 10 read.

## Stage 11.6 Verification
- Backend: `pytest -q` -> `718 passed` (2 host-only env failures unrelated to 11.6); new 11.6 tests
  `47 passed`; regression subset `114 passed`; Alembic round-trip single head `0059`; prompt drift guard OK.
- Frontend: `tsc --noEmit` green; `ForecastAdviceCard.test.tsx` + `AnalyticsRiskPanels.test.tsx` -> `7 passed`.
- 11.6 browser gate: `1 passed (7.8s)` (local Supabase, deterministic provider) — impossible incl.
- Full active Playwright suite (rule 14), documented split (clean DB, `--workers=1`, deterministic):
  success set `--grep-invert "fault gate"` `25 passed`; fault set `4.5d-summary-fault.spec.ts` `2 passed`.
- Rule-11 real-provider smoke: echoed `MBZUAI-IFM/K2-Think-v2` for reachable + impossible, validators pass
  ([[steps/stage-11/11.6-real-provider-smoke]]).

## Stage 11.5 Delivered — Fully Verified
- **Calendar export:** added `GET /student/workload/plans/{plan_id}/calendar.ics`, returning a
  `text/calendar; charset=utf-8` attachment for an owned active workload plan.
- **Snapshot semantics:** exports are file downloads only. There is no Google/Apple OAuth, external sync,
  subscription feed, or auto-update behavior.
- **iCalendar contract:** `VCALENDAR` includes `VERSION:2.0`, `PRODID:XYZ LMS`, `METHOD:PUBLISH`,
  `X-XYZ-SNAPSHOT:true`, stable plan-item/deadline UIDs, per-export `DTSTAMP`, UTC `DTSTART`/`DTEND`, study
  summaries, and reason/estimate descriptions.
- **Deadlines:** active/published module sections with `due_at` export as timed 15-minute deadline marker events.
- **Timezone:** plan events export absolute UTC `Z` instants. The browser gate proves a Europe/London
  DST-boundary 18:00 study block imports as the same instant for an Asia/Dubai viewer instead of being
  re-anchored to 18:00 viewer time.
- **Privacy/authz:** student self only by direct `plan_id`; another same-module student receives 403; lecturer,
  admin, and unassigned users receive 403; response payload carries no other-student data.
- **Read-only UI:** `StudentWorkloadPlanner` adds `Download calendar snapshot` only when a plan exists. Plan item
  rows still expose no edit/done/drag/accept/reject controls.
- **Empty/inactive behavior:** empty active plans export valid empty calendars; superseded plans return explicit
  409 instead of stale export.
- **No migration / no AI:** Alembic remains `0058`; no prompts, providers, validators, `AIRequestLog`, model
  routes, or rule-11 smoke were added.

## Stage 11.5 Verification
- Compile: calendar export, analytics service, and analytics router compile.
- Focused backend: `pytest backend/tests/test_workload_calendar_export.py backend/tests/test_workload_planner.py -q`
  -> `10 passed, 2 skipped`.
- Frontend: `tsc --noEmit` passed; `AnalyticsRiskPanels.test.tsx` -> `4 passed`.
- Docker Alembic: `alembic upgrade head`, `alembic current`, and `alembic heads` -> `0058 (head)`.
- 11.5 browser gate: `1 passed (5.9s)`, including download parsing, stable UIDs, 403-by-plan-id, and the
  cross-timezone/DST absolute-instant assertion.
- Full active Playwright suite, deterministic provider:
  - success set `--grep-invert "fault gate"` -> `24 passed (5.8m)`;
  - isolated fault set `4.5d-summary-fault.spec.ts` -> `2 passed (25.6s)`.
- Closeout note: Stage 7 and fault reruns require `.env.e2e` exported; fault mode also requires
  `LLM_PROVIDER=deterministic` so forced-fault classification is actually exercised.

## Stage 11.4 Delivered — Fully Verified
- **Planner schema:** migration `0058_workload_planner.py` adds `student_availability`,
  `workload_plans`, and `workload_plan_items` below `0057`.
- **Deterministic algorithm:** added six-phase workload planning from remaining `due_at` deadlines, latest 11.1
  risk snapshot gaps, Stage 9 forecast context, student availability, and config-backed estimates/windows.
- **Owner-locked horizon:** when `CourseModule.ends_on` exists, the horizon is the whole remaining course. The
  legacy fallback triggers only when course end is genuinely unknown and uses the later of latest known remaining
  `due_at` and the config-backed fallback horizon.
- **Overflow/tight handling:** deadline recovery may exceed the daily cap only by the configured allowance.
  Physically impossible work is placed as far as it fits and tight-flagged; zero-capacity residuals remain visible
  as tight unscheduled items.
- **Reproducibility:** plans store `algorithmVersion`, stable `inputHash`, `availabilityVersion`, and
  `sourceCutoffAt`; regeneration supersedes the old active plan and creates one active replacement.
- **API/UI:** added student-only availability and plan endpoints plus a read-only, list-first
  `StudentWorkloadPlanner` on student module detail and My Progress. Availability is editable; plan items have no
  edit/done/drag/accept/reject controls.
- **Privacy/authz:** student self only; same-module students do not see each other's plans or IDs; lecturer,
  admin, and unassigned access returns 403.
- **No AI / no rule-11 smoke:** 11.4 adds no prompts, providers, validators, `AIRequestLog`, model routes, or
  rule-11 smoke.

## Stage 11.4 Verification
- Docker Alembic: `0057 -> 0058`; `alembic heads/current` -> `0058 (head)`; downgrade/upgrade round trip passed.
- Focused backend: `pytest backend/tests/test_workload_planner.py backend/tests/test_analytics_api.py -q` ->
  `6 passed, 7 skipped`.
- Frontend: `tsc --noEmit` passed; `AnalyticsRiskPanels.test.tsx` -> `4 passed`.
- 11.4 browser/API gate: `1 passed (8.6s)` on backend `:8006`, frontend `:3006`.
- Full active Playwright suite, deterministic provider:
  - success set `--grep-invert "fault gate"` -> `23 passed (5.8m)`;
  - isolated fault set `4.5d-summary-fault.spec.ts` -> `2 passed (26.3s)`.
- Closeout fixes: quoted migration CHECK constraints for `"window"`, initialized the 11.4 run manifest, imported
  `StudentProgressSnapshot` in the analytics read model, renamed the My Progress availability button to preserve
  the Stage 9 no-Save assertion, and recreated E2E services with `LLM_PROVIDER=deterministic` before final suite
  proof.

## Stage 11.3 Delivered — Fully Verified
- **Deterministic aggregates:** added compute-on-read lecturer assessment analytics over completed quiz attempts,
  `StudentAnswer`, and `AnswerOption`: per-question correct rate, most-missed ordering, and wrong-option
  distractor counts/rates.
- **Topic mastery contract:** verified `QuizQuestion` carries `source_section_id` and `source_summary_id` but no
  `topic_id` or `source_week_number`. Topic mastery uses only source section or summary-to-section provenance;
  null, missing, or cross-module provenance renders an explicit unavailable state.
- **Small-cohort rule:** answer groups below 3 submissions return `Not enough submissions for an aggregate insight`
  instead of percentages.
- **API/UI:** added `GET /lecturer/modules/{module_id}/analytics/assessment-insights` and mounted
  `LecturerAssessmentInsightsPanel` on the lecturer module page.
- **Privacy/authz:** lecturer role only, owned-module only, cross-course lecturer/student/admin get 403, and the API
  response carries no student names, emails, IDs, or per-student answer rows.
- **No AI / no migration:** 11.3 does not touch prompts, providers, `AIRequestLog`, scheduled jobs, Stage 10,
  assistant, gamification, or Alembic. Head remains `0057`.

## Stage 11.3 Verification
- Topic metadata checked first: `source_section_id` and `source_summary_id` present; `topic_id` and
  `source_week_number` absent.
- Focused backend: `tests/test_analytics_assessment.py tests/test_analytics_api.py` → `8 passed, 7 warnings`.
- Frontend type-check: pass.
- Frontend unit suite: `3 passed`, `12 passed`.
- Alembic current/heads: `0057 (head)` / `0057 (head)`.
- 11.3 browser gate: `1 passed (13.7s)`.
- Full active Playwright suite: final clean run `24 passed (8.4m)`.
- Full backend suite: `661 passed, 165 warnings`.
- `git diff --check`: pass.
- Finding fixed during closeout: the Stage 4.5 fault-compose path used a stale shared `kyiv-backend` image for
  `ai_worker`; rebuilding the image from this workspace source fixed assistant failures before the final full
  Playwright run.

## Stage 11.2 Delivered — Fully Verified
- **Recommendation persistence:** migration `0057_student_recommendations.py` adds `recommendations` and widens
  `AIRequestLog.feature` for `recommendation_copy`.
- **Deterministic lifecycle:** recommendations derive from 11.1 `student_risk_snapshots.risk_reasons`; no second
  risk algorithm, no Stage 10 reads, and no AI eligibility/risk calculation.
- **State contract:** separate `lecturerState` and `studentState`; one active recommendation per
  `(student, reasonCode, target)`; dismissed audiences are not re-shown.
- **Live visibility:** reads revalidate against current deterministic risk reasons, so cleared problems hide
  immediately while persisted rows retain state/cache/provenance.
- **AI phrasing:** `recommendation_copy/v1` uses V2/Cerebras (`MBZUAI-IFM/K2-Think-v2`) through `platform/llm`,
  BACKGROUND priority, one call per recommendation, async cached copy, provenance, and deterministic template
  fallback.
- **Validators:** numeric/fact consistency and student-copy safety validators reject invented numbers, peer
  comparisons, diagnoses, unsupported facts, new reasons, and unsafe student language. Positive-control tests prove
  valid AI output renders instead of always falling back.
- **API/UI:** lecturer detail shows reasons, metrics, draft, student preview, and Copy draft / Mark acted / Dismiss
  only; student My Progress and dashboard show at most one gentle dismissible nudge.
- **ADR:** `adr-057-stage-11-recommendation-copy-route.md` records the recommendation-copy route/model decision.

## Stage 11.2 Verification
- Alembic current and heads in Docker: `0057 (head)`.
- Backend Docker suite with smoke-script syntax check: `659 passed, 164 warnings in 295.83s`.
- Frontend type-check: pass; unit tests: `3 passed`, `11 passed`.
- 11.2 browser gate: `1 passed (13.1s)`.
- Full active Playwright suite: final clean run `23 passed (11.3m)`.
- Real-provider smoke: pass. `recommendation_copy/v1` returned model echo `MBZUAI-IFM/K2-Think-v2`
  == configured `MBZUAI-IFM/K2-Think-v2`, `finish_reason='stop'`, status `200`, parseable
  `RecommendationCopy`, and both validators passed. Key redacted.
- `/review`: no whitespace errors, no Send endpoint, authz/state paths covered by tests.
- `/qa`: live local browser gates green.
- `/cso`: no new secret values or DOM HTML sinks found; `npm audit --audit-level=high` reports existing frontend
  dependency advisories (`next`, `undici`, `js-yaml`, `postcss`) that Stage 11.2 did not introduce.
- Finding fixed during closeout: root `.env` now carries the real provider for the smoke, so E2E compose/fault
  overrides explicitly pin normal Playwright runs to the deterministic provider boundary.

## Stage 11.1 Delivered
- **Scheduler foundation:** added `platform/scheduler` as a Python scheduler service/container. It uses a Postgres advisory lock, calculates the daily 06:00 institution-local run, creates/reuses due `AgentRun`s, and enqueues deterministic jobs onto the existing default RQ worker queue.
- **Run ledger:** migration `0056_agent_runs_risk_snapshots.py` adds `agent_runs` with trigger/scope, scheduled time, triggering admin, algorithm version, status/timestamps, counts, idempotency key, and sanitized failure message.
- **Risk snapshots:** migration `0056` adds `student_risk_snapshots` with run/student/module, `riskTier`, structured `riskReasons`, `algorithmVersion`, `inputHash`, `sourceCutoffAt`, and `computedAt`.
- **Deterministic risk-v1:** new analytics domain computes per-course risk from shipped inputs only: Stage 9 forecast data, quiz attempts, `StudentActivityEvent`, section deadlines/schedule, and topic mastery. No Stage 10 data and no AI are read or written.
- **Live-on-read UI:** lecturer/student risk views compute current risk on read; scheduled/manual runs persist snapshots/counts for history and proactive layers.
- **Retention:** scheduled/manual runs prune historical snapshots after the config-backed retention window while preserving the latest snapshot per student/module.
- **API:** added `POST /admin/analytics/agent-runs`, `GET /admin/analytics/agent-runs/{id}`, `GET /lecturer/modules/{module_id}/analytics/roster-risk`, and `GET /student/modules/{module_id}/risk`.
- **Student-safe boundary:** the student risk endpoint returns only student-safe reason text, not `riskTier`, severity, lecturer text, cited metrics, or peer data. The admin manual trigger is rate-limited after admin auth.
- **Frontend:** lecturer module pages show roster risk, `Needs support: N`, tier filter, reasons, and cited metrics. Student module/progress surfaces show a gentle `Where you stand` card with no visible tier label or peer comparison.
- **ADR:** `adr-056-stage-11-scheduler-risk-contract.md` records scheduler/advisory-lock/idempotency/risk-contract decisions.

## Verification
- `git diff --check` — pass.
- `python -m compileall ...` for analytics/scheduler/API/queue files — pass.
- Host focused pytest without DB env — `9 passed, 8 skipped`.
- Docker Alembic:
  - `alembic heads` → `0056 (head)`.
  - fresh `alembic upgrade head` reached `0041 -> 0056`.
  - `alembic current` → `0056 (head)`.
  - `alembic downgrade 0041` → success.
  - `alembic upgrade head` → success.
- Docker focused backend — `tests/test_analytics_risk.py tests/test_rate_limit.py tests/test_scheduler.py tests/test_analytics_api.py` → `17 passed`.
- Docker full backend — `638 passed, 4 skipped, 162 warnings in 118.51s`.
- Frontend container type-check — `tsc --noEmit` exit 0.
- Frontend unit tests — `3 passed`, `11 passed`.
- OpenAPI dry-run into `.context/stage-11/generated-api` matched the committed analytics client shape; diffs were whitespace only. This includes the narrowed student-safe risk DTO.
- Local Supabase-backed E2E:
  - app stack on backend `:8006`, frontend `:3006`;
  - clean app DB migrated to `0056 (head)`;
  - `E2E_RUN_ID=e2e-stage11-local-1781946141 node tests/e2e/fixtures/seed.mjs` seeded 5 Supabase Auth users and 5 app users;
  - `npx playwright test tests/e2e/11.1-roster-risk-scheduler.spec.ts --workers=1` → `1 passed`;
  - `npx playwright test --workers=1` → `22 passed (6.0m)`.

## Gate Findings
- The earlier `.env.e2e` blocker was recorded as BACKEND-VERIFIED / gate-blocked in [[steps/stage-11/findings-11.1-gate-run]].
- Local Supabase resolved the missing-secret prerequisite without hosted credentials.
- A stale same-run-id full-suite retry caused non-Stage-11 failures until the local app DB was reset and reseeded cleanly.

## Stage 11 documents
- Master spec: [[specs/stage-11/11-proactive-ai-agent-analytics]]
- Spec: [[specs/stage-11/11.1-roster-risk-scheduler]]
- Plan: [[plans/stage-11/11.1-roster-risk-scheduler]]
- Report: [[steps/stage-11/11.1-roster-risk-scheduler]]
- Spec: [[specs/stage-11/11.2-student-detail-recommendations]]
- Plan: [[plans/stage-11/11.2-student-detail-recommendations]]
- Report: [[steps/stage-11/11.2-student-detail-recommendations]]
- Spec: [[specs/stage-11/11.3-assessment-analysis-question-insights]]
- Plan: [[plans/stage-11/11.3-assessment-analysis-question-insights]]
- Report: [[steps/stage-11/11.3-assessment-analysis-question-insights]]
- Spec: [[specs/stage-11/11.4-workload-planner]]
- Plan: [[plans/stage-11/11.4-workload-planner]]
- Report: [[steps/stage-11/11.4-workload-planner]]
- Spec: [[specs/stage-11/11.5-calendar-ics-export]]
- Plan: [[plans/stage-11/11.5-calendar-ics-export]]
- Report: [[steps/stage-11/11.5-calendar-ics-export]]
- Spec: [[specs/stage-11/11.6-grade-forecast-advice]]
- Plan: [[plans/stage-11/11.6-grade-forecast-advice]]
- Report: [[steps/stage-11/11.6-grade-forecast-advice]]
- Real-provider smoke: [[steps/stage-11/11.6-real-provider-smoke]]
- Spec: [[specs/stage-11/11.7-agent-run-requeue-recovery]]
- Plan: [[plans/stage-11/11.7-agent-run-requeue-recovery]]
- Report: [[steps/stage-11/11.7-agent-run-requeue-recovery]]
- Real-provider smoke: [[steps/stage-11/11.2-real-provider-smoke]]
- Findings: [[steps/stage-11/findings-11.1-gate-run]]
- ADR: [[decisions/adr-056-stage-11-scheduler-risk-contract]]
- ADR: [[decisions/adr-057-stage-11-recommendation-copy-route]]
- ADR: [[decisions/adr-058-stage-11-workload-planner-algorithm]]
- ADR: [[decisions/adr-059-stage-11-grade-forecast-advice-route]]

## Prior
- 2026-06-20 — Stage 8.5 Save-to-Glossary from the Assistant FULLY VERIFIED.
- 2026-06-19 — Stage 8.4 Assistant Workspace + floating widget FULLY VERIFIED.
- 2026-06-18 — Stage 9 My Progress FULLY VERIFIED.
- 2026-06-18 — Stage 7 core, Stage 6, Stage 5.5, and Stage 5 FULLY VERIFIED.
