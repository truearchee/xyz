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
