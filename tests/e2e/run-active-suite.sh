#!/usr/bin/env bash
# Stage 4.9e §7.4 (F-4.9-2 prevention) — canonical local active-suite run with UNCONDITIONAL teardown.
#
# A `trap cleanup EXIT` guarantees prefix-scoped teardown runs on ANY exit (normal, a crashed spec, or
# Ctrl-C) — the "afterAll/finally semantics" §7.4 requires, so e2e data never accumulates into orphans
# (the Phase-0 baseline failure, F-4.9-1). A PRE-RUN orphan check fails loud if a prior run already leaked.
# This supports the 3-part fault orchestration (seed ONCE, teardown ONCE at the end) — which a per-Playwright-
# invocation globalTeardown could not (it would wipe the seed between the success-set and fault invocations).
#
# Prereq: the e2e stack is up (docker compose -f docker-compose.yml -f docker-compose.e2e.yml up -d --build)
# and local Supabase is running. Runs --workers=1 (4.7-R2 capacity).
set -uo pipefail
cd "$(dirname "$0")/../.."

export E2E_RUN_ID="${E2E_RUN_ID:-e2e-$(date +%s)-active}"
echo "== E2E_RUN_ID=$E2E_RUN_ID =="

echo "== [pre-run] orphan check =="
if ! node tests/e2e/fixtures/check-orphans.mjs; then
  echo "ABORT: orphaned e2e data present — purge before running the suite (F-4.9-1)."
  exit 1
fi

cleanup() {
  echo "== [trap] unconditional teardown (runs on ANY exit) =="
  node tests/e2e/fixtures/teardown.mjs "$E2E_RUN_ID" || echo "WARN: teardown best-effort failed — check orphans"
  docker compose -f docker-compose.yml -f docker-compose.e2e.yml up -d ai_worker >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "== seed =="
node tests/e2e/fixtures/seed.mjs >/dev/null

echo "== success set (9; --grep-invert 'fault gate') =="
npx playwright test --workers=1 --grep-invert "fault gate" --reporter=line; S=$?

echo "== fault: invalid_output =="
LLM_FAULT_INJECTION=invalid_output docker compose -f docker-compose.yml -f docker-compose.e2e.yml -f docker-compose.fault.yml up -d ai_worker >/dev/null 2>&1
sleep 10
npx playwright test --workers=1 --grep "invalid_output" --reporter=line; FO=$?

echo "== fault: invalid_input =="
LLM_FAULT_INJECTION=invalid_input docker compose -f docker-compose.yml -f docker-compose.e2e.yml -f docker-compose.fault.yml up -d ai_worker >/dev/null 2>&1
sleep 10
npx playwright test --workers=1 --grep "invalid_input" --reporter=line; FI=$?

echo "== RESULTS: success_set=$S invalid_output=$FO invalid_input=$FI =="
[ "$S" -eq 0 ] && [ "$FO" -eq 0 ] && [ "$FI" -eq 0 ]   # exit non-zero if any failed (teardown still runs via trap)
