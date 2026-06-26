---
type: steps
stage: 12
session: "12f"
slug: deploy-readiness-mvp-smoke
status: complete
created: 2026-06-25
updated: 2026-06-25
spec: knowledge/specs/stage-12/12f-deploy-readiness-mvp-smoke.md
plan: knowledge/plans/stage-12/12f-deploy-readiness-mvp-smoke.md
---

# Report - Session 12f - Deploy-Readiness + Full-MVP Smoke

> Written from `git diff` + captured command output. Stage 12 closes as deploy-ready /
> production-candidate only; no hosted deploy exists yet (D-12-A), and the owner merges.

## Summary
12f produced the production-candidate build/deploy boundary and the owner handoff docs: non-root backend and
frontend images, production frontend build with hooks off, security headers, CORS finalization on `:3000`,
`/health/ready`, build hygiene wiring, deploy procedure, go-live checklist, ADR-064, and findings/roadmap
reconciliation.

After independent pre-landing review, the deploy-boundary and backlog fixes were applied in this workspace:

- `docker-compose.prod.yml` now fails closed: app services require `XYZ_PROD_ENV_FILE`, replace the base
  backend app-service `env_file: .env` with that reviewed env file, reset the frontend `env_file` to empty,
  and exit before app boot unless `LLM_PROVIDER=k2think`.
- The rendered frontend container environment is limited to `NODE_ENV` plus `NEXT_PUBLIC_*`; DB, Redis,
  Supabase secret/storage, and LLM key material do not enter the Next.js runtime environment.
- Deterministic full-MVP `/qa` smoke moved to the separate non-prod `docker-compose.qa.yml` overlay. The
  production-candidate overlay no longer carries the deterministic test LLM adapter.
- The normal E2E and fault overlays now pin literal `LLM_PROVIDER=deterministic`, so shell/project env cannot
  leak `k2think` into rule-14/fault runs.
- The catch-all 500 path now reuses the security-header helper as well as the manual CORS repair.
- `knowledge/open-questions.md` closes the Stage 12 E2E provider leak and explicitly defers the
  `seed.mjs` 1000-user auth pagination backlog with owner.
- `scripts/build-production.sh` now owns the documented deploy path for `build`, `migrate`, `current`, `up`,
  and `all`, always using the same explicit env file for hygiene, Compose interpolation, release-phase
  migration, and runtime start. The hygiene gate parses that env file as data (`--env-file`) and never
  shell-sources production secrets.

No final commit, push, PR, or merge was done in this review-fix pass, per owner instruction.

## Files changed
Branch commits already contain the main 12f implementation relative to `origin/main`:
`git diff --stat origin/main...HEAD` reports 26 files changed, including Dockerfiles, CORS/error/health
backend changes, frontend production config, deploy docs, ADR-064, spec/plan, findings, and the 12f CORS E2E
assertion.

This review-fix working tree additionally changes:

- `docker-compose.prod.yml` - require `XYZ_PROD_ENV_FILE`, override backend app env files, reset frontend
  env files, k2think-only runtime guard.
- `docker-compose.e2e.yml`, `docker-compose.fault.yml` - literal deterministic LLM provider for E2E/fault.
- `docker-compose.qa.yml` - new non-prod deterministic `/qa` overlay.
- `backend/app/platform/http/errors.py`, `backend/app/platform/http/security_headers.py`, and
  `backend/tests/test_error_envelope.py` - shared security-header helper applied to forced 500 responses and
  regression-tested.
- `scripts/build-production.sh` - env-preserving `build|migrate|current|up|all` deploy entrypoint; no
  shell-sourcing of production secrets.
- `backend/app/platform/production_hygiene.py` and `backend/tests/test_production_hygiene.py` - safe env-file
  parser plus regression proving `$` and backticks are preserved as data and not executed.
- `docs/deploy-procedure.md`, `docs/go-live-checklist.md` - commands now preserve the reviewed prod env and
  warn against bare base-compose deploy commands; frontend secret-boundary checks added.
- `knowledge/open-questions.md` - E2E provider leak closed; `seed.mjs` pagination deferred-with-owner.
- `knowledge/specs/stage-12/12f-deploy-readiness-mvp-smoke.md`,
  `knowledge/plans/stage-12/12f-deploy-readiness-mvp-smoke.md`,
  `knowledge/decisions/adr-064-deploy-readiness-production-candidate.md`, and `knowledge/steps/findings-12.md`
  - deploy-boundary, provider, 500-header, and backlog dispositions recorded.
- `knowledge/steps/stage-12/12f-real-provider-smoke.md` - owner-run Gate 3 evidence added to the branch.
- `tests/e2e/.runs/gate1.log` - stale red untracked artifact removed; it is not evidence for the current gate.

`package-lock.json` has an unrelated pre-existing workspace-name change (`bucharest` -> `rio-de-janeiro`);
this pass left it untouched.

## Verification run here
Local checks targeted the current pre-landing findings and diff hygiene:

| Command | Result |
|---|---|
| `bash -n scripts/build-production.sh` | PASS, exit 0 |
| `python3 -m py_compile backend/app/platform/production_hygiene.py` | PASS, exit 0 |
| `docker compose run --rm --no-deps -v "$PWD/backend:/app" backend pytest tests/test_production_hygiene.py -q` | PASS: `15 passed` |
| `python3 backend/app/platform/production_hygiene.py --env-file .context/12f-gate-clean.env` | PASS: `Production hygiene check passed` |
| `python3 backend/app/platform/production_hygiene.py --env-file .context/12f-gate-dirty-hook.env` | EXPECTED FAIL, exit 1 on `NEXT_PUBLIC_E2E_TEST_HOOKS='true'` |
| `python3 backend/app/platform/production_hygiene.py --env-file .context/12f-gate-dirty-llm.env` | EXPECTED FAIL, exit 1 on `LLM_PROVIDER='deterministic'` |
| `./scripts/build-production.sh .context/12f-gate-dirty-llm.env build` | EXPECTED FAIL before build; hygiene aborts on deterministic provider |
| `./scripts/build-production.sh .context/12f-gate-dirty-llm.env current` | EXPECTED FAIL before Alembic; hygiene aborts on deterministic provider |
| Manual temp-env proof with `LLM_API_KEY=abc$FOO\`touch <sentinel>\`` parsed through `load_env_file` + `main(["--env-file", ...])` | PASS: printed literal `$FOO`/backtick value and `sentinel_exists=False` |
| Direct `build-production.sh <temp-env> build` proof with backticks + dirty provider | EXPECTED FAIL before build; `script_failed_before_build_and_sentinel_absent=true` |
| `docker compose -f docker-compose.yml -f docker-compose.prod.yml config --services` | EXPECTED FAIL: missing required `XYZ_PROD_ENV_FILE` |
| `XYZ_PROD_ENV_FILE=.context/12f-gate-clean.env docker compose --env-file .context/12f-gate-clean.env -f docker-compose.yml -f docker-compose.prod.yml config --services` | PASS: renders the prod overlay services |
| `... config --format json | jq '.services.backend.environment'` | PASS: backend app env contains the reviewed clean env values plus `ENVIRONMENT=production`; no base `.env` dev values |
| `... config --format json | jq -e '.services.frontend.environment as $env | ... secret absence ...'` | PASS: returned `true`; frontend env has no DB/Redis/Supabase secret/LLM key material |
| `... config --format json | jq -r '.services.frontend | {env_file: .env_file, environment_keys: (.environment \| keys)}'` | PASS: `env_file: null`; keys are only `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_E2E_TEST_HOOKS`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_SUPABASE_URL`, `NODE_ENV` |
| `XYZ_PROD_ENV_FILE=.context/12f-gate-dirty-llm.env docker compose --env-file .context/12f-gate-dirty-llm.env -f docker-compose.yml -f docker-compose.prod.yml run --rm --no-deps backend` | EXPECTED FAIL, exit 64: `production-candidate stack requires LLM_PROVIDER=k2think` |
| `LLM_PROVIDER=k2think docker compose --env-file .env.e2e -f docker-compose.yml -f docker-compose.e2e.yml config --format json \| jq -r '.services.backend.environment.LLM_PROVIDER, .services.worker.environment.LLM_PROVIDER, .services.ai_worker.environment.LLM_PROVIDER, .services.embedding_worker.environment.LLM_PROVIDER, .services.scheduler.environment.LLM_PROVIDER'` | PASS: all five lines were `deterministic` |
| `LLM_PROVIDER=k2think docker compose -f docker-compose.yml -f docker-compose.fault.yml config --format json \| jq -r '.services.ai_worker.environment.LLM_PROVIDER'` | PASS: `deterministic` |
| `docker compose -f docker-compose.yml -f docker-compose.qa.yml config --services` | PASS: deterministic `/qa` overlay renders separately |
| `docker compose -f docker-compose.yml -f docker-compose.qa.yml config --format json ...` | PASS: QA backend is `ENVIRONMENT=development` / `LLM_PROVIDER=deterministic`; frontend hooks remain `"false"` |
| `docker compose run --rm --no-deps backend pytest tests/test_error_envelope.py tests/test_security_headers.py -q` | PASS: `15 passed, 3 warnings` |
| `git diff --check` | PASS |
| `test ! -e tests/e2e/.runs/gate1.log` | PASS: stale red log removed |

## Owner gates recorded
These are owner-supplied / owner-run gates, not rerun by this review-fix pass:

- **Gate 1 - rule-14 full Playwright:** clean rerun was **36 passed + 1 known flake that passed on isolated
  retry**. The stale red `tests/e2e/.runs/gate1.log` was from an earlier run and is removed/ignored.
- **Gate 2 - full-MVP `/qa` smoke:** owner reran green. After the P1 fix, the documented deterministic
  `/qa` path is the separate non-prod `docker-compose.qa.yml` overlay.
- **Gate 3 - real-provider smoke:** PASS in [[steps/stage-12/12f-real-provider-smoke]].
  Model echo `MBZUAI-IFM/K2-Think-v2` matched expected; attempt 1; status 200; parseable 16-question
  `GeneratedQuizPool`; 261.7 s; `finish_reason=length` accepted as known K2Think reasoning variance.

## Deviations / residual risk
- I did not rerun the full backend suite, frontend typecheck, full Playwright, `/qa`, `/review`, or `/cso` in
  this pass. The owner will rerun the independent review and owner gates after these deploy-boundary fixes.
- I did not run a clean production image build because the requested fresh local proof was the hygiene gate
  teeth and prod-overlay fail-closed behavior.
- The real hosted deploy, `/canary`, managed-PG extension bootstrap verification, backup/restore drill,
  rollback rehearsal, Stage 8.3 SSE, F-12C-CASCADE deletion mechanism, Next.js bump, key rotation, pentest,
  and nonce-based CSP remain deferred-with-owner in `docs/go-live-checklist.md`.

## Close-the-loop checklist
- [x] Spec exists and is `status: approved`.
- [x] Plan exists and is `status: approved`.
- [x] P1/P2 scope changes recorded in spec, plan, ADR-064, findings, deploy docs, open questions, and this
  report.
- [x] Verification commands run for the P1/P2 fixes; real command results recorded above.
- [x] Spec / plan / report links resolve.
- [x] `STATUS.md` updated with the current 12f state.
- [x] `knowledge/log.md` appended.
- [x] `architecture/` not updated in this review-fix pass; no architecture path changed after the existing 12f
  branch commits.
- [x] No new ADR needed beyond ADR-064 amendment.
- [x] `knowledge/open-questions.md` updated: provider leak resolved; `seed.mjs` auth pagination deferred with
  owner.

## Change history
- 2026-06-25 - Pre-landing review fixes: prod overlay now fails closed on `LLM_PROVIDER=k2think`, replaces
  base app `.env` at runtime, script owns build/migrate/current/up with the reviewed env file, and deterministic
  `/qa` smoke moved to `docker-compose.qa.yml`.
- 2026-06-25 22:22 +04 - Second pre-landing review fixes: frontend prod env no longer receives backend
  secrets, E2E/fault compose pins literal deterministic provider, forced 500 responses apply security headers,
  and open-question backlog items were resolved/deferred.
- 2026-06-25 23:01 +04 - Final pre-landing deploy-boundary fix: `build-production.sh` no longer
  shell-sources the production env file; `production_hygiene.py --env-file` parses dotenv values as data, with
  a regression for `$`/backtick preservation and no command execution.

## Linked documents
- Spec: [[specs/stage-12/12f-deploy-readiness-mvp-smoke]]
- Plan: [[plans/stage-12/12f-deploy-readiness-mvp-smoke]]
- Report: [[steps/stage-12/12f-deploy-readiness-mvp-smoke]]
- Real-provider smoke: [[steps/stage-12/12f-real-provider-smoke]]
- Stage spec: [[specs/stage-12/12-release-hardening]]
- Findings: [[steps/findings-12]]
- Decision: [[decisions/adr-064-deploy-readiness-production-candidate]]
- Deploy docs: [docs/deploy-procedure.md](../../../docs/deploy-procedure.md) and
  [docs/go-live-checklist.md](../../../docs/go-live-checklist.md)
