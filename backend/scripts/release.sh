#!/usr/bin/env sh
# Stage 4.8b (B5) — release-phase command (the BACKEND Fly app's release_command target). Lives in the
# backend image at /app/scripts/release.sh.
#
# Runs the schema migration over the DIRECT connection, THEN the idempotent identity bootstrap.
# `set -e`: ANY non-zero step aborts the release → Fly aborts the deploy → the new version never
# serves. This is the migrate-as-release contract — a deploy that succeeds against a broken migration
# is the silent failure this guards against (proven by backend/tests/test_release_abort.py + the
# hosted poison-migration rehearsal in the runbook). O2: migrate first, bootstrap second; the coupling
# (a Supabase blip in bootstrap aborts an otherwise-fine migration deploy) is accepted under
# expand-only migrations and documented in deploy/staging-runbook.md.
set -eu

cd "$(dirname "$0")/.."   # → app root (alembic.ini lives here)

echo "[release] alembic upgrade head (over DIRECT_DATABASE_URL)"
alembic upgrade head

echo "[release] bootstrap identities (idempotent; passwords never logged)"
python -m app.cli.bootstrap_identities

echo "[release] done"
