#!/usr/bin/env bash
# Stage 12f — production-candidate build gate.
#
# Wires the Stage 12b production_hygiene assertion (backend/app/platform/production_hygiene.py — pure
# stdlib, no app/DB imports) into the build/deploy path: it FAILS THE BUILD (non-zero exit) if any E2E
# test hook or fault-injection switch is enabled, or if LLM_PROVIDER is not the real provider. Run it in
# the deploy/build environment BEFORE building the images, so the forbidden NEXT_PUBLIC_* hooks can never
# be baked into the frontend bundle.
#
# Usage:  ./scripts/build-production.sh [ENV_FILE] [build|migrate|current|up|all]
#   ENV_FILE defaults to .env.production and must set the real production env (LLM_PROVIDER=k2think; every
#   NEXT_PUBLIC_* test hook and fault-injection flag unset/false). The same ENV_FILE is carried into
#   docker compose for build interpolation AND runtime app-service env_file resolution.
set -euo pipefail

cd "$(dirname "$0")/.."

ENV_FILE="${1:-.env.production}"
ACTION="${2:-build}"
PYTHON="${PYTHON:-python3}"

case "$ENV_FILE" in
  build|migrate|current|up|all)
    ACTION="$ENV_FILE"
    ENV_FILE=".env.production"
    ;;
esac

usage() {
  cat >&2 <<'EOF'
Usage: ./scripts/build-production.sh [ENV_FILE] [build|migrate|current|up|all]

Actions:
  build    Run production_hygiene, then build images (default).
  migrate  Run production_hygiene, then alembic upgrade head using ENV_FILE.
  current  Run production_hygiene, then alembic current using ENV_FILE.
  up       Run production_hygiene, then start the stack using ENV_FILE.
  all      build, migrate, current, then up.
EOF
}

if [[ ! -f "$ENV_FILE" ]]; then
  echo "build-production: env file '$ENV_FILE' not found" >&2
  exit 2
fi

# docker-compose.prod.yml uses this service env_file override so app runtime and release-phase
# migrations read the reviewed production env, not the repo-local .env from the base compose file.
export XYZ_PROD_ENV_FILE="$ENV_FILE"
COMPOSE=(docker compose --env-file "$ENV_FILE" -f docker-compose.yml -f docker-compose.prod.yml)

run_hygiene() {
  echo "==> Production hygiene check ($ENV_FILE)"
  # Pure-stdlib assertion against the env file parsed as data (never shell-sourced); a non-zero exit
  # aborts before image build, migration, or runtime start.
  "$PYTHON" backend/app/platform/production_hygiene.py --env-file "$ENV_FILE"
}

build_images() {
  run_hygiene
  echo "==> Building production images (docker-compose.prod.yml, env: $ENV_FILE)"
  "${COMPOSE[@]}" build
}

migrate() {
  run_hygiene
  echo "==> Running release-phase migration (env: $ENV_FILE)"
  "${COMPOSE[@]}" run --rm backend alembic upgrade head
}

current() {
  run_hygiene
  echo "==> Checking migration head (env: $ENV_FILE)"
  "${COMPOSE[@]}" run --rm backend alembic current
}

start_stack() {
  run_hygiene
  echo "==> Starting production-candidate stack (env: $ENV_FILE)"
  "${COMPOSE[@]}" up -d
}

case "$ACTION" in
  build)
    build_images
    echo "==> Production build complete. Continue with:"
    echo "    ./scripts/build-production.sh $ENV_FILE migrate"
    echo "    ./scripts/build-production.sh $ENV_FILE current"
    echo "    ./scripts/build-production.sh $ENV_FILE up"
    ;;
  migrate)
    migrate
    ;;
  current)
    current
    ;;
  up)
    start_stack
    ;;
  all)
    build_images
    migrate
    current
    start_stack
    ;;
  *)
    echo "build-production: unknown action '$ACTION'" >&2
    usage
    exit 2
    ;;
esac
