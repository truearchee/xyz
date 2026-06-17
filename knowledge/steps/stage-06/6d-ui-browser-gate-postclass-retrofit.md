---
type: session-report
stage: "06"
session: "6d"
slug: ui-browser-gate-postclass-retrofit
status: blocked-at-real-provider-smoke
created: 2026-06-17
updated: 2026-06-17
spec: knowledge/specs/stage-06/6d-ui-browser-gate-postclass-retrofit.md
plan: knowledge/plans/stage-06/6d-ui-browser-gate-postclass-retrofit.md
---

# Session 6d — UI + browser gate + post-class retrofit

## Linked documents
- Overview spec: [[specs/stage-06/6-complete-quiz-modes]]
- Spec: [[specs/stage-06/6d-ui-browser-gate-postclass-retrofit]]
- Plan: [[plans/stage-06/6d-ui-browser-gate-postclass-retrofit]]
- Report: [[steps/stage-06/6d-ui-browser-gate-postclass-retrofit]]
- Real-provider smoke: [[steps/stage-06/6d-real-provider-smoke]]
- Foundation: [[steps/stage-06/6a-pool-foundation]], [[steps/stage-06/6b-recap-examprep-authorization]], [[steps/stage-06/6c-retake-mistakes-bank]]
- Capacity ADR: [[decisions/adr-047-section-question-pool-capacity]]
- Stage 7 coordination: [[steps/findings-6-shared-infra]]
- Prior browser gate: [[steps/stage-05/5d-student-ui-browser-gate]]

## Result

6d implementation is built and the developer-run browser gate is green:

- 5d post-class preservation gate: green.
- 6d browser gate: green, including retake+bank, exam-prep scope correctness, in-browser pool reuse, the
  authorization set, and desktop/mobile screenshots for every new surface.
- Full active Playwright suite: green.
- Backend/full regression and frontend type-check: green.

Stage 6 remains open only because the real-provider quiz-pool smoke did not pass rule 11: the script reached
the provider with `LLM_PROVIDER=k2think`, but the local key was rejected with a redacted 401/403 auth error.
The roadmap row was not flipped.

## Implemented

- Added module-level student quiz modes UI:
  - 2x2 mode selector.
  - Recap scope modal with weeks/date-range inputs and availability check.
  - Exam-prep scope modal listing lecturer scopes.
  - Mistakes-bank modal/list/start flow.
  - Shared attempt shell with generating state, polling, answer feedback, completion, and retake-prefix
    banner driven by `mistakeReviewQuestionCount`.
- Added lecturer `AssessmentScopePanel` on the module detail page:
  - Create form for name + covered weeks.
  - List/table of existing scopes.
  - No edit/delete UI.
- Exposed existing attempt metadata through the student attempt DTO:
  - `newQuestionCount`
  - `mistakeReviewQuestionCount`
- Retrofitted post-class start onto the Stage 6 pooled start path:
  - Existing Stage 5 generation functions remain callable as the revert path.
  - Reaper pooled-attempt liveness no longer excludes `post_class`.
- Added `tests/e2e/6d-quiz-modes-browser-gate.spec.ts`:
  - Seeds two assigned students plus one unassigned student.
  - Browser-proves the new surfaces and captures desktop/mobile screenshots when runtime is available.
  - DB-proves source-section scope correctness, unpublished-section exclusion, pool reuse, own-student-only
    bank isolation, and 404/403 authorization behavior.
- Extended E2E manifest/teardown for Stage 6 quiz artifacts:
  - `aiRequestLogIds`
  - quiz answers/options/questions/attempts
  - mistakes, section pools, pool questions, quiz definitions, assessment scopes
- Added `backend/scripts/gate3_quiz_pool_smoke.py` for the Stage 6 quiz-pool real-provider smoke.
- Recorded the absent `knowledge/design-system.md` as a cross-stage Stage 4.9/Stage 7 residual in
  [[steps/findings-6-shared-infra]].

## Verification

```bash
docker compose build backend
# Image kyiv-backend Built

docker compose run --rm --no-deps backend pytest -q tests/test_llm_gateway.py tests/test_quiz_generation.py tests/test_quiz_pool.py tests/test_quiz_recap_examprep.py tests/test_quiz_mistakes_bank.py tests/test_quiz_endpoints.py
# 61 passed, 15 warnings in 15.70s

docker compose run --rm --no-deps backend pytest -q
# 501 passed, 137 warnings in 73.63s (0:01:13)

ruff check backend/app/workers/queues.py backend/app/platform/llm/gateway.py backend/app/platform/llm/provider.py backend/app/domains/quiz/generation_service.py backend/app/domains/quiz/service.py backend/app/domains/recovery/reaper.py backend/app/domains/recovery/rq_liveness.py backend/app/platform/query/quiz_read.py backend/app/domains/quiz/schemas.py backend/scripts/gate3_quiz_pool_smoke.py backend/tests/test_quiz_endpoints.py backend/tests/test_quiz_generation.py backend/tests/test_quiz_mistakes_bank.py backend/tests/test_quiz_pool.py backend/tests/test_quiz_recap_examprep.py
# All checks passed!

docker compose run --rm --no-deps backend alembic heads
# 0025 (head)

docker compose run --rm --no-deps backend alembic current
# 0025 (head)

mkdir -p .context/generated && docker compose run --rm --no-deps backend python - <<'PY' > .context/generated/openapi-6d.json
import json
from app.main import app
print(json.dumps(app.openapi()))
PY
cd frontend && npx --no-install openapi --input ../.context/generated/openapi-6d.json --output src/lib/api --client fetch
# exit 0

npm --prefix frontend run type-check
# > xyz-lms-frontend@0.1.0 type-check
# > tsc --noEmit

npx playwright test --list
# Total: 14 tests in 12 files

docker compose build frontend
# Image albuquerque-frontend Built

node --check tests/e2e/fixtures/teardown.mjs && node --check tests/e2e/fixtures/run-manifest.mjs
# exit 0

docker compose run --rm --no-deps backend python -m py_compile scripts/gate3_quiz_pool_smoke.py
# exit 0

RUN_ID=$(cat .context/6d-run-id.txt); E2E_RUN_ID="$RUN_ID" PLAYWRIGHT_BASE_URL=http://localhost:3001 NEXT_PUBLIC_API_BASE_URL=http://localhost:8001 npx playwright test tests/e2e/5d-post-class-quiz.spec.ts --workers=1
# 1 passed (16.3s)

RUN_ID=$(cat .context/6d-run-id.txt); E2E_RUN_ID="$RUN_ID" PLAYWRIGHT_BASE_URL=http://localhost:3001 NEXT_PUBLIC_API_BASE_URL=http://localhost:8001 npx playwright test tests/e2e/6d-quiz-modes-browser-gate.spec.ts --workers=1
# 1 passed (27.7s)

RUN_ID=$(cat .context/6d-full-run-id.txt); E2E_RUN_ID="$RUN_ID" PLAYWRIGHT_BASE_URL=http://localhost:3001 NEXT_PUBLIC_API_BASE_URL=http://localhost:8001 npx playwright test --workers=1
# 14 passed (2.8m)

docker compose run --rm --no-deps backend python scripts/gate3_quiz_pool_smoke.py
# FAIL: LLM_PROVIDER must be 'k2think' (export it before running Gate 3).

docker compose run --rm --no-deps -e LLM_PROVIDER=k2think backend python scripts/gate3_quiz_pool_smoke.py
# FAIL: provider auth error (401/403) — key not rotated/valid? Body redacted.

git diff --check
# exit 0
```

## Blocked verification

The only blocked gate is the real-provider rule-11 PASS. The smoke script fail-closed successfully, but the
available local key returned provider auth failure:

```bash
docker compose run --rm --no-deps -e LLM_PROVIDER=k2think backend python scripts/gate3_quiz_pool_smoke.py
# Stage 6d Gate 3 — quiz pool real-provider smoke (synthetic summary; secrets REDACTED)
# FAIL: provider auth error (401/403) — key not rotated/valid? Body redacted.
```

## Screenshot Evidence

Captured by the green 6d browser gate in `knowledge/steps/stage-06/screenshots/`:

- `knowledge/steps/stage-06/screenshots/mode-selector-{desktop,mobile}.png`
- `knowledge/steps/stage-06/screenshots/recap-scope-modal-{desktop,mobile}.png`
- `knowledge/steps/stage-06/screenshots/exam-prep-scope-modal-{desktop,mobile}.png`
- `knowledge/steps/stage-06/screenshots/generating-state-{desktop,mobile}.png`
- `knowledge/steps/stage-06/screenshots/retake-prefix-banner-{desktop,mobile}.png`
- `knowledge/steps/stage-06/screenshots/mistakes-bank-{desktop,mobile}.png`
- `knowledge/steps/stage-06/screenshots/assessment-scope-form-{desktop,mobile}.png`
- `knowledge/steps/stage-06/screenshots/assessment-scope-list-{desktop,mobile}.png`

## Known Limitations

- A lecturer mistyping an AssessmentScope has an API-only `PATCH` recovery path, but no delete route/API and
  no 6d edit/delete UI. This is an approved MVP limitation for 6d.
- `knowledge/design-system.md` is still absent. The implementation used shipped Stage 4.9/5d/5.5 source
  components/patterns as the binding design authority. This is tracked in [[steps/findings-6-shared-infra]]
  as cross-stage debt with Stage 7.
- The standard API client generation script could not be used verbatim because the local `:8000` backend
  port is held by a sibling stack. The client was regenerated from `.context/generated/openapi-6d.json`
  dumped from the rebuilt backend image instead.

## Modified Prior Sessions

- Session 5d — `backend/app/domains/quiz/service.py`, `backend/app/domains/quiz/generation_service.py`,
  `backend/tests/test_quiz_endpoints.py`: post-class start now uses the pooled path; Stage 5 generation
  remains callable as the revert path.
- Session 5d — `frontend/src/lib/api/wrapper.ts`, `frontend/src/lib/api/models/QuizAttemptForStudent.ts`:
  wrapper/client now expose Stage 6 mode endpoints and existing attempt count fields.
- Session 6a — `backend/app/domains/recovery/reaper.py`: pooled liveness includes `post_class` after the
  retrofit.
- Session 6b/6c — `backend/app/platform/query/quiz_read.py`, `backend/app/domains/quiz/schemas.py`:
  attempt read DTO carries new-vs-prefix counts to the browser.
- Session 4.3.5e E2E teardown infrastructure — `tests/e2e/fixtures/run-manifest.mjs`,
  `tests/e2e/fixtures/teardown.mjs`: cleanup now covers Stage 6 quiz/pool artifacts, AI log IDs, and the
  legacy direct VTT object key shape produced by early 6d browser-gate seeds.
- Session 6a — `backend/app/workers/queues.py`, `backend/app/domains/recovery/rq_liveness.py`, related
  tests/comments: RQ job IDs now use dash-only names because RQ rejects colon-containing IDs.
- Session 5d — `tests/e2e/5d-post-class-quiz.spec.ts`: preservation gate now expects the Stage 6 retake
  prefix count (`total=11`, `newQuestions=10`, `mistakePrefix=1`) after one saved mistake.

## Change History

- 2026-06-17 — Created from implementation, backend/static verification, and initial blocked browser/runtime
  evidence.
- 2026-06-17 — Updated after standing up the alternate local runtime, capturing screenshots, passing 5d
  preservation, passing the 6d browser gate, and passing the full active E2E suite. Stage 6 remains open
  only on the real-provider smoke auth failure.
