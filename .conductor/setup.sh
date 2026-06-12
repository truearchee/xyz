#!/bin/bash
set -e

# Добавляем уникальное имя проекта для изоляции Docker
echo "COMPOSE_PROJECT_NAME=xyz_${CONDUCTOR_WORKSPACE_NAME:-dev}" >> .env

# Устанавливаем зависимости frontend
cd frontend && npm install --silent && cd ..