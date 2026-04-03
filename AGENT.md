# Clouisle Project Guide

This root file is now only a lightweight entrypoint for project structure and documentation routing.

## Project Overview

Clouisle is a monorepo application with:
- `backend/` - FastAPI backend
- `frontend/` - Next.js frontend
- `deploy/` - deployment resources
- `docs/guide/` - user and operator documentation
- `docs/dev/` - internal developer documentation

## Basic norms

- Use root guidance files only for quick orientation.
- Put detailed engineering rules and subsystem notes in `docs/dev/`.
- Keep user-facing and operator-facing content in `docs/guide/`.
- Preserve the separation between dashboard/admin and platform/user code paths.
- Update the relevant docs when implementation rules change.

## Start here

- Internal engineering docs: `docs/dev/README.md`
- Public/user docs: `docs/guide/README.md`
- Backend API details: `docs/dev/api/BACKEND_API.md`
- Backend conventions: `docs/dev/backend/api-conventions.md`
- Frontend conventions: `docs/dev/frontend/conventions.md`
- Design docs index: `docs/dev/design/README.md`
- Team and authorization design: `docs/dev/design/access-control/TEAM_MODEL_AUTH_SPEC.md`
- Workflow architecture: `docs/dev/design/app-platform/WORKFLOW_ENGINE_ARCHITECTURE.md`

## Design grouping map

- `docs/dev/design/app-platform/` - Agent, workflow, node, and tool platform specs
- `docs/dev/design/ai-data/` - LLM, knowledge base, and memory specs
- `docs/dev/design/access-control/` - RBAC, team auth, and quota-related specs
- `docs/dev/design/notifications/` - notification and external channel specs
