---
type: architecture
stage: 01
created: 2026-05-29
updated: 2026-05-29 16:40
related-session: knowledge/specs/stage-01/1.1-repo-skeleton.md
---

# Repo Skeleton Architecture

## Linked documents
- Spec: [[specs/stage-01/1.1-repo-skeleton]]
- Plan: [[plans/stage-01/1.1-repo-skeleton]]
- Report: [[steps/stage-01/1.1-repo-skeleton]]

## Current structure
The repository is organized as a local development skeleton with Docker Compose at the root, a FastAPI backend under `backend/`, a Next.js frontend under `frontend/`, PostgreSQL initialization SQL under `docker/postgres/init/`, runtime prompts under `prompts/`, and utility scripts under `scripts/`.

## Runtime boundaries
- `backend/` owns the FastAPI app, Alembic migration tooling, async SQLAlchemy session factory, and RQ worker entrypoint.
- `frontend/` owns the Next.js app and generated OpenAPI TypeScript client output under `frontend/src/lib/api/`.
- `docker-compose.yml` wires PostgreSQL with pgvector, Redis, backend, worker, and frontend for local development.

## Current intentional gaps
No database tables, models, auth, storage, AI integration, job handlers, UI components, or product workflows exist in this skeleton.
