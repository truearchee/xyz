#!/usr/bin/env bash
# Stage 12f — production-candidate build gate.
#
# Wires the Stage 12b production_hygiene assertion (backend/app/platform/production_hygiene.py — pure
# stdlib, no app/DB imports) into the build/deploy path: it FAILS THE BUILD (non-zero exit) if any E2E
# test hook or fault-injection switch is enabled, or if LLM_PROVIDER is not the real provider. Run it in
# the deploy/build environment BEFORE building the images, so the forbidden NEXT_PUBLIC_* hooks can never
# be baked into the frontend bundle.
#
# Usage:  ./scripts/build-production.sh [ENV_FILE]
#   ENV_FILE defaults to .env.production and must set the real production env (LLM_PROVIDER=k2think; every
#   NEXT_PUBLIC_* test hook and fault-injection flag unset/false).
set -euo pipefail

cd "$(dirname "$0")/.."

ENV_FILE="${1:-.env.production}"
PYTHON="${PYTHON:-python3}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "build-production: env file '$ENV_FILE' not found" >&2
  exit 2
fi

# Load the deploy env so the hygiene assertion AND the frontend build args (docker-compose.prod.yml)
# both see the real values.
set -a
# shellcheck source=/dev/null
. "$ENV_FILE"
set +a

echo "==> Production hygiene check ($ENV_FILE)"
# Pure-stdlib assertion against the loaded environment; a non-zero exit aborts the build via set -e
# BEFORE any image is built.
"$PYTHON" backend/app/platform/production_hygiene.py

echo "==> Building production images (docker-compose.prod.yml)"
docker compose -f docker-compose.yml -f docker-compose.prod.yml build

echo "==> Production build complete. Bring it up with:"
echo "    docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d"
