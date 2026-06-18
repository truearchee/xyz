# Status

_Last updated: 2026-06-18 — **Stage 9 My Progress Dashboard is FULLY VERIFIED.** Backend schema/API/forecast/seed work is verified; benchmark privacy is pinned to caller-owned averages plus aggregate class data; frontend type-check is clean; the Stage 9 browser gate and full active Playwright suite both pass against the local E2E stack._

## Current branch
- Branch: `stage-9`
- Target branch: `origin/main`
- Migration block used: `0038-0039` inside the assigned `0038-0043` block.
- Local runtime: backend `http://localhost:8002`, frontend `http://localhost:3002` via `.context/stage9-compose.override.yml` because host `:8000` is occupied by another workspace.

## Stage 9 delivered
- ADR-052 records the single-tenant MVP decision before new tables; Stage 8 already owns ADR-050 and ADR-051.
- Finding recorded: design docs claim the Stage 4.9 Tailwind/shared UI system exists, but this checkout lacks it; Stage 9 UI uses the current inline-style idiom.
- Migration `0038`: grade schemes, grade boundaries, grade components, student grade records, active target-grade goals.
- Migration `0039`: week progress snapshots and lecture/lab section topic mastery snapshots.
- Decimal forecast engine with `final_no_remaining`, `achieved`, `impossible`, `on_track`, `at_risk`, `requires_high_score`.
- Current-student-only routes:
  - `GET /student/progress`
  - `GET /student/modules/{module_id}/progress`
  - `PUT /student/modules/{module_id}/target-grade`
- Privacy-safe responses: no other student identifiers, individual grade rows, component scores, standings, named comparisons, or other students' quiz averages; benchmark `studentAverage` is the requesting student's own value only.
- Demo seed: `backend/scripts/seed_progress_demo.py --reset-stage9-demo`, guarded against unsafe DBs and tied to Alembic head `0039`.
- Frontend route: `/student/progress`, linked from the student home and backed by generated OpenAPI client methods.
- E2E spec: `tests/e2e/9-my-progress.spec.ts`, run-scoped fixture with all six forecast states, no-AI-log assertion, payload privacy checks, cross-student 404, lecturer 403, and screenshot capture for all forecast states.
- Admin user list ordering was adjusted newest-first so the existing Stage 2 admin browser gate remains stable when interrupted E2E runs leave residue.

## Verification
```bash
docker compose run --rm -v "$PWD/backend:/app" -T backend pytest -q \
  tests/test_progress_forecast.py tests/test_progress_api.py
# 18 passed, 6 warnings in 3.13s

docker compose -f docker-compose.yml -f .context/stage9-compose.override.yml run --rm -T backend \
  sh -lc 'alembic heads && alembic downgrade 0033 && alembic upgrade head && alembic heads && alembic current'
# Reverified after rebase onto Stage 8.2: 0039 (head); downgraded 0039 -> 0038 -> 0033; upgraded 0033 -> 0038 -> 0039; current 0039 (head)

docker compose run --rm -v "$PWD/backend:/app" -T backend pytest -q
# 542 passed, 143 warnings in 103.04s

cd frontend && npx tsc --noEmit
# exit 0

docker compose -f docker-compose.yml -f .context/stage9-compose.override.yml exec -T frontend npx tsc --noEmit
# exit 0

npx playwright test tests/e2e/9-my-progress.spec.ts --list
# Total: 1 test in 1 file

npx playwright test --list
# Total: 16 tests in 14 files

docker compose -f docker-compose.yml -f .context/stage9-compose.override.yml run --rm \
  -v "$PWD/backend:/app" -T backend python scripts/seed_progress_demo.py --reset-stage9-demo
# passed; emitted two module IDs and Student A-F demo emails

PLAYWRIGHT_BASE_URL=http://localhost:3002 NEXT_PUBLIC_API_BASE_URL=http://localhost:8002 \
  STAGE9_SCREENSHOT_DIR=knowledge/steps/stage-09/screenshots \
  npx playwright test tests/e2e/9-my-progress.spec.ts --project=chromium --workers=1
# 1 passed (30.8s)

E2E_RUN_ID=e2e-stage9-followup-1781790440 \
  PLAYWRIGHT_BASE_URL=http://localhost:3002 NEXT_PUBLIC_API_BASE_URL=http://localhost:8002 \
  npx playwright test tests/e2e/9-my-progress.spec.ts --project=chromium --workers=1
# 1 passed (24.8s)

set -a; source .env.e2e; set +a
PLAYWRIGHT_BASE_URL=http://localhost:3002 NEXT_PUBLIC_API_BASE_URL=http://localhost:8002 \
  npx playwright test --workers=1
# 16 passed (4.7m)

git diff --check
# exit 0

curl -i -sS http://localhost:8002/health
# HTTP/1.1 200 OK

curl -i -sS http://localhost:3002/student/progress
# HTTP/1.1 200 OK
```

## Stage 9 documents
- Spec: [[specs/stage-09/9-my-progress-dashboard]]
- Plan: [[plans/stage-09/9-my-progress-dashboard]]
- Report: [[steps/stage-09/9-my-progress-dashboard]]
- ADR: [[decisions/adr-052-single-tenant-mvp]]
- Finding: [[steps/stage-09/findings-design-doc-reality-gap]]

## Open risks
- No known Stage 9 merge/rebase risks remain after reconciling the Stage 8.2 migration head and ADR numbering.

## Prior
- 2026-06-18 — Stage 7 core (7a-7c) FULLY VERIFIED; 7d remains separate work.
- 2026-06-18 — Stage 6 CLOSED and FULLY VERIFIED after rule-11 real-provider smoke and full active Playwright suite.
- 2026-06-17 — Stage 5.5 FULLY VERIFIED.
- 2026-06-12 — Stage 4.7 FULLY VERIFIED on main.
