# Status

_Last updated: 2026-06-25 - Stage 12f final deploy-boundary review fix applied locally; ready for owner
gate rerun. No final commit, push, PR, or merge from this pass._

## Current branch
- Branch: `stage-12f-orientation`
- Target: `origin/main`
- Base on this branch: Stage 12f spec/plan and commits 1-8 are present above `origin/main`.
- Current worktree: review-fix changes are uncommitted per owner instruction. `package-lock.json` has an
  unrelated pre-existing workspace-name change (`bucharest` -> `rio-de-janeiro`) and was not touched.

## Stage 12f deploy-readiness state
- Production deploy path is fail-closed:
  - `docker-compose.prod.yml` requires `XYZ_PROD_ENV_FILE`.
  - Backend app services replace the base app-service `.env` with the reviewed prod env file.
  - Frontend resets inherited `env_file` to empty and renders only `NODE_ENV` + `NEXT_PUBLIC_*`.
  - Backend/workers/scheduler exit before app boot unless `LLM_PROVIDER=k2think`.
  - `scripts/build-production.sh` owns `build`, `migrate`, `current`, `up`, and `all` with the same explicit
    env file.
  - The hygiene gate parses the production env file as data (`--env-file`) and never shell-sources secrets.
- Deterministic full-MVP `/qa` smoke is split into `docker-compose.qa.yml` (non-prod only); the production
  overlay no longer carries the deterministic test LLM adapter.
- Normal E2E and fault overlays pin literal `LLM_PROVIDER=deterministic`, so shell/project env cannot route
  the rule-14 path to K2Think.
- Forced 500 responses now carry CORS (for allowed origins) and the baseline security headers.
- Deploy docs now warn against bare base-compose deploy/migration commands and preserve the reviewed env
  through build, migration, and backend runtime; the frontend secret-boundary check is in the handoff.
- `knowledge/open-questions.md`: provider leak resolved; `seed.mjs` auth-user pagination explicitly
  deferred-with-owner.

## Verification snapshot
- `bash -n scripts/build-production.sh` passed.
- `python3 -m py_compile backend/app/platform/production_hygiene.py` passed.
- `docker compose run --rm --no-deps -v "$PWD/backend:/app" backend pytest tests/test_production_hygiene.py -q`
  passed: `15 passed`.
- `python3 backend/app/platform/production_hygiene.py --env-file .context/12f-gate-clean.env` passed.
- Hygiene failed as expected with `--env-file .context/12f-gate-dirty-hook.env`.
- Hygiene failed as expected with `--env-file .context/12f-gate-dirty-llm.env`.
- `./scripts/build-production.sh .context/12f-gate-dirty-llm.env build` failed before build as expected.
- A manual parser proof preserved a literal `LLM_API_KEY=abc$FOO\`touch ...\`` value and did not create the
  sentinel file.
- A direct `build-production.sh` temp-env proof with backticks failed before build and also left the sentinel
  absent.
- `./scripts/build-production.sh .context/12f-gate-dirty-llm.env current` failed before Alembic as expected.
- Prod overlay render without `XYZ_PROD_ENV_FILE` failed as expected.
- Prod overlay render with `.context/12f-gate-clean.env` passed and showed backend app env from the reviewed
  clean env, not base `.env`.
- Prod overlay rendered frontend env has `env_file: null` and exactly
  `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_E2E_TEST_HOOKS`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`,
  `NEXT_PUBLIC_SUPABASE_URL`, `NODE_ENV`; explicit secret-key scan returned `true`.
- Prod overlay runtime with deterministic provider exited 64 before app boot.
- `LLM_PROVIDER=k2think` E2E render showed backend/worker/ai_worker/embedding_worker/scheduler all
  `deterministic`; fault overlay ai_worker also rendered `deterministic`.
- `docker compose run --rm --no-deps backend pytest tests/test_error_envelope.py tests/test_security_headers.py -q`
  passed: `15 passed, 3 warnings`.
- QA overlay rendered separately with non-prod deterministic backend and frontend hooks off.
- `git diff --check` passed.
- Stale untracked `tests/e2e/.runs/gate1.log` removed.

## Owner gate evidence
- Gate 1: owner clean rerun reported **36 passed + 1 known flake that passed on isolated retry**. The stale
  red `gate1.log` was an earlier artifact, not current evidence.
- Gate 2: owner full-MVP `/qa` smoke rerun reported green.
- Gate 3: [[steps/stage-12/12f-real-provider-smoke]] recorded PASS against real K2Think with model echo
  `MBZUAI-IFM/K2-Think-v2`.

## Linked documents
- Spec: [[specs/stage-12/12f-deploy-readiness-mvp-smoke]]
- Plan: [[plans/stage-12/12f-deploy-readiness-mvp-smoke]]
- Report: [[steps/stage-12/12f-deploy-readiness-mvp-smoke]]
- Real-provider smoke: [[steps/stage-12/12f-real-provider-smoke]]
- Findings: [[steps/findings-12]]
- Decision: [[decisions/adr-064-deploy-readiness-production-candidate]]
- Deploy procedure: [docs/deploy-procedure.md](../docs/deploy-procedure.md)
- Go-live checklist: [docs/go-live-checklist.md](../docs/go-live-checklist.md)
