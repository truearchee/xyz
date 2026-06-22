---
stage: "11.1"
title: 11.1 browser-gate blocker and local Supabase resolution
status: resolved
updated: 2026-06-20
---

# Findings — Stage 11.1 browser gate run (rule 10)

## Linked documents
- Spec: [[specs/stage-11/11.1-roster-risk-scheduler]]
- Plan: [[plans/stage-11/11.1-roster-risk-scheduler]]
- Report: [[steps/stage-11/11.1-roster-risk-scheduler]]
- ADR: [[decisions/adr-056-stage-11-scheduler-risk-contract]]

## Original blocker
Stage 11.1 was initially **BACKEND VERIFIED / gate-blocked**, not DONE. The implementation had backend,
migration, frontend type/unit, and OpenAPI dry-run proof, but the browser gate and rule-14 full active Playwright
suite could not run because this workspace did not have `.env.e2e`.

Exact blocker proof:

```text
E2E_RUN_ID=e2e-stage11-local node tests/e2e/fixtures/seed.mjs
```

Result:

```text
.env.e2e is required before seeding E2E fixtures
```

This was an environment prerequisite, not a product-code pass. The stage therefore stayed blocked until browser
proof existed.

## Resolution
The local Supabase path was viable and was used instead of hosted secrets:

- Local Supabase was available on `127.0.0.1:54321`.
- Ignored `.env` and `.env.e2e` were generated from local Supabase status. Secret values were never recorded in
  docs or chat.
- `.context/stage-11-local-e2e.override.yml` ran the app stack on backend `:8006` and frontend `:3006`.
- A clean app DB was migrated to `0056 (head)` and seeded with run id `e2e-stage11-local-1781946141`.

Final proof:

```text
npx playwright test tests/e2e/11.1-roster-risk-scheduler.spec.ts --workers=1
1 passed

npx playwright test --workers=1
22 passed (6.0m)
```

## Additional finding
The first full-suite rerun reused the same local run id and stale app DB state. That produced:

- Stage 5.5e duplicate membership: expected `201`, received `409`.
- Stage 8.5 stale glossary subject lookup for the standing student and normalized term `concise`.

The fix was not a product-code change: reset only the local app Compose DB volume, migrate, seed a fresh run id,
and rerun the full active suite. The 11.1 E2E spec also received a scoped cleanup-order fix so repeated 11.1 gate
runs delete memberships and dependent rows before deleting the test module.

## Status impact
Only sub-session 11.1 is FULLY VERIFIED. Stage 11 overall remains IN PROGRESS because 11.2+ have not started.
