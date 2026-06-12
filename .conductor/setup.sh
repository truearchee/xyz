#!/bin/bash
set -e

# Копируем .env из основного репозитория
cp /Users/arthur.leontev/Desktop/LMS/test2/.env .env

# Добавляем уникальное имя проекта для изоляции Docker
echo "COMPOSE_PROJECT_NAME=xyz_${CONDUCTOR_WORKSPACE_NAME:-dev}" >> .env

# Устанавливаем зависимости frontend
cd frontend && npm install --silent && cd ..