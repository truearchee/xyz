---
type: architecture
stage: 01
created: 2026-05-29
updated: 2026-05-30
related-session: knowledge/specs/stage-01/1.1-repo-skeleton.md
---

# Repo Skeleton Architecture

## Linked documents
- Spec: [[specs/stage-01/1.1-repo-skeleton]]
- Plan: [[plans/stage-01/1.1-repo-skeleton]]
- Report: [[steps/stage-01/1.1-repo-skeleton]]
- Spec: [[specs/stage-02/2.3-admin-flows]]
- Plan: [[plans/stage-02/2.3-admin-flows]]
- Report: [[steps/stage-02/2.3-admin-flows]]

## Current structure
The repository is organized as a local development skeleton with Docker Compose at the root, a FastAPI backend under `backend/`, a Next.js frontend under `frontend/`, PostgreSQL initialization SQL under `docker/postgres/init/`, runtime prompts under `prompts/`, and utility scripts under `scripts/`.

## Runtime boundaries
- `backend/` owns the FastAPI app, Alembic migration tooling, async SQLAlchemy session factory, and RQ worker entrypoint.
- `frontend/` owns the Next.js app and generated OpenAPI TypeScript client output under `frontend/src/lib/api/`.
- `docker-compose.yml` wires PostgreSQL with pgvector, Redis, backend, worker, and frontend for local development.
- `backend/app/domains/admin/` owns admin business rules and camelCase API DTOs for course setup flows.
- `backend/app/platform/supabase_client.py` is the only construction point for the async Supabase Admin client.

## Current intentional gaps
No storage, AI integration, job handlers, UI components, lecturer endpoints, or student endpoints exist in this skeleton. Database tables and models start with the Session 2.1 DB spine; see [[architecture/db-spine]]. Auth infrastructure starts with Session 2.2 and role guards start with Session 2.3; see [[architecture/auth-current-user-context]].
