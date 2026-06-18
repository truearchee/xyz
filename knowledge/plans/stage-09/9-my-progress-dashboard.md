---
type: session-plan
stage: 09
session: "9"
slug: my-progress-dashboard
status: executed
created: 2026-06-18
updated: 2026-06-18
spec: knowledge/specs/stage-09/9-my-progress-dashboard.md
report: knowledge/steps/stage-09/9-my-progress-dashboard.md
---

# Session 9 — Implementation Plan — My Progress Dashboard

## Linked documents
- Spec: [[specs/stage-09/9-my-progress-dashboard]]
- Plan: [[plans/stage-09/9-my-progress-dashboard]]
- Report: [[steps/stage-09/9-my-progress-dashboard]]
- ADR: [[decisions/adr-052-single-tenant-mvp]]
- Finding: [[steps/stage-09/findings-design-doc-reality-gap]]

## Scope confirmation
Deliver the whole Stage 9 dashboard sequence: deterministic grade forecast, target-grade persistence, progress/mastery snapshots, privacy-safe class quiz-average benchmark, demo/E2E seeds, student UI, browser gate, and closeout knowledge updates.

Do not build grade-entry UI, grade-scheme setup UI, generic goals, rankings, named comparisons, mental-health/risk labels, gamification logic, AI calls, or the deferred Tailwind/shared-component repaint.

## Approach
Use the current codebase patterns: SQLAlchemy models plus Alembic migrations; Pydantic camelCase DTOs; `platform/query` for read models; student routes under `/student/...` with `private, no-store`; frontend calls through generated OpenAPI client and `wrapper.ts`; E2E fixtures through run-scoped DB helpers.

## Changes, file by file
- `knowledge/decisions/adr-052-single-tenant-mvp.md` — record no `organization_id` on Stage 9 tables.
- `backend/alembic/versions/0038_*.py` — grade schemes, boundaries, components, records, active target goals.
- `backend/alembic/versions/0039_*.py` — progress and topic mastery snapshots.
- `backend/app/platform/db/models/` — matching ORM models exported from `__init__.py`.
- `backend/app/domains/progress/` — forecast engine, schemas, service, demo/E2E seed helpers.
- `backend/app/platform/query/progress_read.py` — current-user-only dashboard/detail/benchmark queries.
- `backend/app/api/routers/progress.py` + `backend/app/main.py` — student API surface.
- `backend/scripts/seed_progress_demo.py` — guarded idempotent demo seed CLI.
- `frontend/src/app/(app)/student/page.tsx` and `student/progress/page.tsx` — add progress navigation and route.
- `frontend/src/features/progress/` — dashboard UI in existing inline-style idiom.
- `frontend/src/lib/api/wrapper.ts` + generated client — expose progress methods.
- `backend/tests/` and `tests/e2e/` — forecast, API, seed, and browser-gate coverage.

## Order of operations
1. File approved spec/plan, ADR, and design-gap finding.
2. Add migrations and ORM models in block `0038-0040`.
3. Add forecast engine and backend unit tests.
4. Add progress read model/service/router and API tests.
5. Add demo seed and E2E fixture helpers.
6. Regenerate OpenAPI client and add wrapper methods.
7. Add student progress UI and E2E browser gate.
8. Run backend, migration, frontend, and Playwright verification.
9. Write report from `git diff` and command output; update `STATUS.md`, `log.md`, and `roadmap.md`.

## Test strategy
- Unit-test forecast state machine and Decimal boundaries directly.
- API-test student role, current-user-only access, target upsert, privacy-safe JSON, no forecast-time writes, and no AI logs.
- Seed-test demo idempotency and scenario matrix.
- E2E-test all six forecast states via deterministic fixtures, target auto-save, impossible headline, JSON privacy, no AIRequestLog rows, benchmark visibility, and gamification placeholder.
- Close with full backend pytest, frontend type-check, Alembic round-trip, Stage 9 Playwright gate, and full active Playwright suite.

## Risks & mitigations
- Design docs claim Tailwind/shared UI exists but code does not -> record finding and build inline-style UI in current idiom.
- Parallel Stage 8 migration/ADR work -> use assigned migration block `0038-0043`; reconciled during rebase by chaining after Stage 8.2 head `0033` and using ADR-052 for the single-tenant decision.
- Privacy leakage through benchmark -> return aggregate-only DTOs and assert JSON never includes other student identifiers or individual scores.
- Flaky E2E seed -> keep demo and E2E datasets separate; E2E is run-scoped and deterministic.

## Open questions
- None blocking. Stage 8 landed first; ADR numbering was reconciled to ADR-052 during rebase.
