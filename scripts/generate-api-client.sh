#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR/frontend"

npx --no-install openapi \
  --input http://localhost:8000/openapi.json \
  --output src/lib/api \
  --client fetch

find src/lib/api -name '*.ts' -type f -exec perl -0pi -e 's/\n+\z/\n/' {} +
