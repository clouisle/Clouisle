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
- Strict test coverage gates: Backend line & branch coverage >= 95.00% (`backend/scripts/check_coverage.py`), and Frontend function & line coverage gates.
- License compliance: strictly avoid copyleft licenses (GPL/AGPL). Any indirect exception must be approved in `license-policy.yml`.

## Core Architectural & Engineering Invariants

1. **Permissions & Multi-Tenant Boundary**:
   - Double-check frontend `<PermissionGuard>` alongside backend route dependencies (`require_kb_update`, `check_team_access`).
   - Shared/non-owned resources must downgrade to read-only mode for consumers; strictly guard against IDOR.
2. **High-Volume & Batch Processing**:
   - Never pass bulk ID arrays in URL queries (HTTP 431). Use `sessionStorage` or backend batch IDs.
   - Transaction-level isolation via UUID keys: use `batch_id = uuid4()` to prevent multi-user/multi-tab counter overwrites.
   - Atomic convergence: use Redis `DECR`/`INCR` instead of database `SELECT count(*)` polling in Celery workers.
   - Failure exit safety: decrement batch counters on all failure/exception exits to prevent deadlocks.
   - Request pooling & toast hygiene: throttle large client requests in batches of 5–10; aggregate toast messages into a single progress indicator.
   - Union-gate notification resolution: prioritize failure awareness for partial batches and respect site-setting notification toggles.
3. **External Dependencies & Licensing**:
   - Prefer concise standard library / native implementations (<= 30 lines) over adding new npm/pip packages.
   - Assume external network services (LLMs, OCR, SMTP, S3) will fail or time out: enforce explicit timeouts, circuit breakers, and rate limit protections.
4. **Responsive & Adaptive UX**:
   - Avoid `100vh` on mobile viewports; use `h-svh`/flex containers with `min-h-0` to avoid address-bar clipping and nested scroll deadlocks.
   - Adapt complex two-column layouts into stack/drawer views on small screens; ensure touch targets are at least 44x44px.
5. **Full-Chain i18n**:
   - Extract all user-facing strings into `zh` and `en` dictionaries. Match translations namespaces strictly to prevent runtime `MISSING_MESSAGE` errors.

## Detailed docs

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
