#!/usr/bin/env sh
# Stage 4.8b (B7) — repeatable staging deploy. OPERATOR-run: your authenticated `flyctl` + the two
# pre-created Fly apps. This script NEVER creates apps or inlines secrets (O5). Run from the repo root.
#
#   scripts/deploy-staging.sh            # full deploy (backend release runs migrate + bootstrap)
#   scripts/deploy-staging.sh --dry-run  # env gate only
#
# Before running: `set -a; . ./.env.staging; set +a` (so check-staging-env + the NEXT_PUBLIC_* build
# args + REDIS_URL are in the environment). flyctl secrets are set separately by the operator.
set -eu

BACKEND_APP="${STAGING_BACKEND_APP:-xyz-lms-backend-staging}"
FRONTEND_APP="${STAGING_FRONTEND_APP:-xyz-lms-frontend-staging}"
BACKEND_URL="${STAGING_BACKEND_URL:-https://${BACKEND_APP}.fly.dev}"

echo "== check-staging-env gate =="
sh scripts/check-staging-env

if [ "${1:-}" = "--dry-run" ]; then
  echo "dry-run: env gate only — not deploying."
  exit 0
fi

command -v fly >/dev/null 2>&1 || { echo "flyctl not found / not authenticated"; exit 1; }

# MF5 — deploy the IMMUTABLE artifact: build+push ONCE, capture the pushed image digest, then deploy
# THAT digest. Never a bare `fly deploy` that rebuilds / re-resolves a mutable tag. (Confirm the
# --json image field name against your flyctl version; the property is: deploy the ref you just built.)
deploy_pinned() {
  app="$1"; cfg="$2"; shift 2
  echo "== build+push $app (immutable digest) =="
  ref=$(fly deploy -c "$cfg" -a "$app" --build-only --push "$@" --json 2>/dev/null \
        | sed -n 's/.*"image"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  [ -n "$ref" ] || { echo "could not resolve pushed image digest for $app"; exit 1; }
  case "$ref" in *@sha256:*) : ;; *) echo "WARNING: $app image ref is not digest-pinned: $ref" ;; esac
  echo "== deploy $app from pinned ref: $ref =="
  fly deploy -c "$cfg" -a "$app" --image "$ref"
}

# Backend FIRST — its release_command runs `alembic upgrade head` (DIRECT) + bootstrap; a non-zero
# release ABORTS the deploy and the new version never serves (MF1 / migrate-as-release).
deploy_pinned "$BACKEND_APP" backend/fly.toml

# Frontend — NEXT_PUBLIC_* are inlined at build (Decision D1). NEXT_PUBLIC_E2E_TEST_HOOKS is never passed.
deploy_pinned "$FRONTEND_APP" frontend/fly.toml \
  --build-arg "NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL:?set NEXT_PUBLIC_API_BASE_URL}" \
  --build-arg "NEXT_PUBLIC_SUPABASE_URL=${NEXT_PUBLIC_SUPABASE_URL:?set NEXT_PUBLIC_SUPABASE_URL}" \
  --build-arg "NEXT_PUBLIC_SUPABASE_ANON_KEY=${NEXT_PUBLIC_SUPABASE_ANON_KEY:?set NEXT_PUBLIC_SUPABASE_ANON_KEY}"

echo "== verify /health/ready (bounded poll; first ready boot = alembic at head) =="
i=0
until [ "$(curl -s -o /dev/null -w '%{http_code}' "$BACKEND_URL/health/ready" || echo 000)" = "200" ]; do
  i=$((i + 1)); [ "$i" -ge 30 ] && { echo "readiness never reached 200"; exit 1; }
  sleep 5
done
echo "  /health/ready: 200"

echo "== MF4: worker registry — ingestion/embedding/ai each registered =="
if [ -n "${REDIS_URL:-}" ]; then
  python backend/scripts/check_workers.py || { echo "worker-registry check FAILED"; exit 1; }
else
  echo "  REDIS_URL not set locally — run: fly ssh console -a $BACKEND_APP -C 'python scripts/check_workers.py'"
fi

echo "== deploy complete =="
