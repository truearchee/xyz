#!/bin/bash
set -e

cp ../.env .env 2>/dev/null || cp .env.example .env

echo "COMPOSE_PROJECT_NAME=xyz_${CONDUCTOR_WORKSPACE_NAME:-dev}" >> .env

cd frontend && npm install --silent && cd ..