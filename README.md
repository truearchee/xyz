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

```bash
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

# Deployment

- Deploy procedure (production-candidate): [docs/deploy-procedure.md](docs/deploy-procedure.md)
- Go-live checklist (product owner): [docs/go-live-checklist.md](docs/go-live-checklist.md)

Stage 12 closes the MVP as **deploy-ready / production-candidate** — there is no hosted environment yet
(decision D-12-A); the real go-live is tracked in the checklist above.
