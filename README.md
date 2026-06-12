# Prerequisites

- Docker Desktop
- Node 20
- Python 3.12

# First-time setup

```bash
cp .env.example .env
```

# Start all services

```bash
docker compose up
```

# Run migrations

```bash
docker compose exec backend alembic upgrade head
```

# Generate API client

Regenerate the OpenAPI TypeScript client (rule 3) whenever the backend contract changes, then commit it.
One-command alias (F008, Stage 4.9e §7.3) — run from `frontend/` (needs the backend up at `:8000`):

```bash
npm run gen:api          # alias for ../scripts/generate-api-client.sh
# or from the repo root:
bash scripts/generate-api-client.sh
```

# Service URLs

- Backend: http://localhost:8000
- Frontend: http://localhost:3000

# Run backend tests

```bash
docker compose exec backend pytest
```

# Frontend type-check

```bash
docker compose exec frontend npx tsc --noEmit
```
