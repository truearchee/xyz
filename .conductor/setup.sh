#!/bin/bash
set -e

# Явно указываем PATH чтобы docker, npm и другие инструменты были доступны
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:$PATH"

# Добавляем уникальное имя проекта для изоляции Docker
echo "COMPOSE_PROJECT_NAME=xyz_${CONDUCTOR_WORKSPACE_NAME:-dev}" >> .env

# Устанавливаем зависимости frontend
cd frontend && npm install --silent && cd ..