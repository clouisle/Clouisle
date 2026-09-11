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
- Record field-level before/after diffs in audit logs via `AuditLogService.snapshot`/`build_changes` (see `docs/dev/backend/audit-logging.md`).
- Keep detailed implementation guidance in `docs/dev/`.
- Update docs when architecture or conventions change.

## High-Volume & Batch Processing Conventions

When designing or implementing batch operations (e.g., uploading, chunking, embedding, or re-indexing 500+ documents/entities):
1. **Never pass bulk ID arrays in URL queries**: Request line/header limits (8KB–16KB) trigger HTTP 431 errors. Use client storage (`sessionStorage`) or an explicit backend transaction/batch ID. Always maintain recovery banners on parent pages if users drop off or close tabs.
2. **Transaction-level isolation via UUID batch keys**: Never bind transient status counters or locks to static dimensions (`user_id`, `kb_id`). Use unique `batch_id = uuid4()` to prevent multi-user, multi-tab, or concurrent upload collisions.
3. **Atomic state convergence without database hammering**: Use Redis atomic counters (`DECR`/`INCR`) for async completion detection. Avoid repeated database `SELECT count(*) WHERE status in (...)` inside async workers.
4. **Guaranteed lifecycle exit for all error branches**: Any mechanism relying on counter decrement or chord convergence must decrement on both success and failure/exception branches to prevent counter deadlocks and lost completion signals. Ensure TTLs on all temporary Redis keys.
5. **Frontend request pooling & notification de-duplication**: Throttle large client requests in small concurrency batches (5–10 items) rather than unbounded `Promise.all`. For batch notifications and toasts, aggregate progress into a single updating indicator (`toast.loading`) rather than emitting one toast per completed item.
6. **Union-gate notification resolution**: For partial-success / partial-failure batches, align with site-setting notification switches by prioritizing error awareness (`high` warning priority) and ensuring notifications fire if either success or failure events are enabled.
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
