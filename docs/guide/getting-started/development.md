# Development Setup

This guide covers setting up a local development environment for contributing to Clouisle.

## Prerequisites

- Python 3.13+ with [uv](https://github.com/astral-sh/uv)
- [Bun](https://bun.sh/) 1.0+
- Docker & Docker Compose (for infrastructure services)

## 1. Clone the Repository

```bash
git clone https://github.com/clouisle/Clouisle.git
cd clouisle
```

## 2. Configure Environment

```bash
# Copy the root environment file for local development
cp .env.example .env
```

Generate secure passwords and update `.env`. Set strong random values for:
`SECRET_KEY`, `QDRANT_API_KEY`.

Note: the dev infrastructure (`deploy/docker-compose.dev.yml`) uses **fixed, hardcoded credentials** that ignore `.env`: PostgreSQL runs as `postgres` / `password` and Redis uses the password `clouisle-redis-cbd3c07d`. Only `QDRANT_API_KEY` is read from `.env` (it is required). Set `POSTGRES_PASSWORD` / `REDIS_PASSWORD` in `.env` only if you also edit the dev compose file to match.

## 3. Start Infrastructure

```bash
# Start PostgreSQL, Redis, and Qdrant
docker compose -f deploy/docker-compose.dev.yml --env-file .env up -d
```

## 4. Start Backend

```bash
# Install dependencies
uv sync --project backend

# Start the API server (database will be auto-initialized on first run)
uv run --project backend main.py server

# In separate terminals, start workers
uv run --project backend main.py worker
uv run --project backend main.py beat

# Optional: sandbox worker for code execution features
uv run --project backend main.py sandbox-worker -c 1
```

## 5. Start Frontend

```bash
# Install dependencies
bun install --cwd frontend

# Start development server
bun run --cwd frontend dev
```

## 6. Access the Application

- **Frontend**: http://localhost:3000
- **API Documentation**: http://localhost:8000/docs
- **First account**: there is no seeded default admin — the first user to register is automatically promoted to Super Admin

## Development Commands

### Backend

```bash
cd backend

# Lint
uv run ruff check .

# Format
uv run ruff format .

# Test
uv run pytest
```

### Frontend

```bash
# Lint
bun run --cwd frontend lint

# Build
bun run --cwd frontend build

# Test and coverage
bun run --cwd frontend test
bun run --cwd frontend test:coverage
bun run --cwd frontend coverage:check
```

### Sandbox Worker (optional)

```bash
# Start a sandbox worker for code execution features
uv run --project backend main.py sandbox-worker -c 1

# Or run in a dev container for isolation
uv run --project backend main.py sandbox-worker --local-dev -c 1
```

## Project Structure

```
clouisle/
├── backend/          # FastAPI backend
│   ├── app/          # Application code
│   │   ├── api/      # API endpoints and routers
│   │   ├── core/     # Core config, init, auth, etc.
│   │   ├── llm/      # LLM adapters and tool system
│   │   ├── models/   # Tortoise ORM models
│   │   ├── schemas/  # Pydantic schemas
│   │   ├── services/ # Business logic services
│   │   └── tasks/    # Celery task definitions
│   ├── tests/        # Test suite
│   ├── scripts/      # Utility scripts
│   └── pyproject.toml
├── frontend/         # Next.js frontend
│   ├── app/          # App Router pages
│   ├── components/   # React components
│   ├── lib/          # Utilities and API client
│   ├── hooks/        # Custom React hooks
│   └── contexts/     # React contexts
├── deploy/           # Deployment configs (Docker, K8s, Helm)
├── docs/             # Documentation
├── main.py           # Root startup script
└── scripts/          # Project-level scripts
```

## Troubleshooting

### Database initialization fails

Ensure PostgreSQL is running and accessible. The dev Compose file uses fixed PostgreSQL/Redis credentials and reads only `QDRANT_API_KEY` from `.env`; inspect `deploy/docker-compose.dev.yml` if the services do not start.

### Port conflicts

Default ports: backend `8000`, frontend `3000`, PostgreSQL `5432`, Redis `6379`, Qdrant `6333`. The dev Compose file exposes only PostgreSQL, Redis, and Qdrant; backend and frontend run separately, so change their launch/config settings when those ports conflict.

### Hot reload not working

The `server` command enables auto-reload by default. Files under `backend/` are watched. For manual restart, stop the process and re-run the server command.

---

See [Quick Start (Docker)](./quick-start.md) for production deployment.
