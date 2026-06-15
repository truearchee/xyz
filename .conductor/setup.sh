#!/bin/bash
set -e

export PATH="$HOME/.local/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:$PATH"

cp "$CONDUCTOR_ROOT_PATH/.env" .env

echo "COMPOSE_PROJECT_NAME=xyz_${CONDUCTOR_WORKSPACE_NAME:-dev}" >> .env

cd frontend && npm install --silent && cd ..