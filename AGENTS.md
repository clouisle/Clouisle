# AGENTS.md

This file provides quick guidance to code agents working in this repository.

## Project Overview

Clouisle is an enterprise-grade knowledge base and AI Agent platform. The repository is a monorepo with a FastAPI backend and a Next.js frontend.

## Top-level directories

- `backend/` - FastAPI application and services
- `frontend/` - Next.js application
- `deploy/` - deployment and Docker assets
- `docs/guide/` - user and operator docs
- `docs/dev/` - internal engineering docs

## Core commands

### Backend
```bash
uv sync
uvicorn app.main:app --reload
uv run ruff check .
uv run ruff format .
uv run mypy app/
uv run pytest
```

### Frontend
```bash
bun install
bun dev
bun run lint
bun run build
```

### Infrastructure
```bash
docker-compose -f deploy/docker-compose.dev.yml up -d
```

## Basic rules

- Treat this file as a quick entrypoint only.
- Follow existing code patterns in the touched module.
- Keep admin/platform boundaries isolated.
- Keep detailed implementation guidance in `docs/dev/`.
- Update docs when architecture or conventions change.

## Detailed docs

- `docs/dev/README.md`
- `docs/dev/api/BACKEND_API.md`
- `docs/dev/backend/api-conventions.md`
- `docs/dev/backend/migrations-and-init-data.md`
- `docs/dev/backend/audit-logging.md`
- `docs/dev/backend/celery-and-async-jobs.md`
- `docs/dev/frontend/conventions.md`
- `docs/dev/design/README.md`
- `docs/dev/design/access-control/TEAM_MODEL_AUTH_SPEC.md`
- `docs/dev/design/access-control/RBAC_SPEC.md`
- `docs/dev/design/app-platform/WORKFLOW_ENGINE_ARCHITECTURE.md`

## Design grouping map

- `docs/dev/design/app-platform/` - Agent, workflow, node, and tool platform specs
- `docs/dev/design/ai-data/` - LLM, knowledge base, and memory specs
- `docs/dev/design/access-control/` - RBAC, team auth, and quota-related specs
- `docs/dev/design/notifications/` - notification and external channel specs
