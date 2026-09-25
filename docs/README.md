# Clouisle Documentation

## Overview

Documentation is split by audience:

- `guide/` - user-facing and operator-facing documentation
- `dev/` - internal engineering, architecture, and implementation documentation

## Entry points

### User and operator docs
- [`guide/README.md`](guide/README.md)
- [Chinese product overview and guide navigation](guide/README_zh-CN.md)

### Developer docs
- [`dev/README.md`](dev/README.md)

## Key areas

### `docs/guide/`
Use this area for:
- getting started guides
- user workflows
- admin/operator workflows
- deployment and operations docs
- public API reference and concepts

### `docs/dev/`
Use this area for:
- backend conventions and implementation guides
- frontend conventions and implementation guides
- API implementation guidance
- design specs
- codebase analysis
- engineering status documents

## Other document areas

- [`plan/`](plan/) — design proposals, feature specs, and historical RFCs. These describe intended or in-progress work and are not guaranteed to match shipped behavior.
- [`analysis/`](analysis/) — one-off engineering analyses such as [`analysis/timeout-analysis.md`](analysis/timeout-analysis.md); historical diagnostics rather than maintained reference.
- [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) — live checklist of active and completed cross-cutting work items.

## Developer sections

- [`dev/backend/README.md`](dev/backend/README.md)
- [`dev/frontend/README.md`](dev/frontend/README.md)
- [`dev/api/BACKEND_API.md`](dev/api/BACKEND_API.md)
- [`dev/design/`](dev/design/)
- [`dev/analysis/README.md`](dev/analysis/README.md)
- [`dev/status/README.md`](dev/status/README.md)

## Quick links

- [Quick start](guide/getting-started/quick-start.md)
- [Architecture](guide/concepts/architecture.md)
- [Backend API reference](dev/api/BACKEND_API.md)
- [Backend API conventions](dev/backend/api-conventions.md)
- [Frontend conventions](dev/frontend/conventions.md)
- [Team model auth specification](dev/design/access-control/TEAM_MODEL_AUTH_SPEC.md)
- [Workflow engine architecture](dev/design/app-platform/WORKFLOW_ENGINE_ARCHITECTURE.md)
