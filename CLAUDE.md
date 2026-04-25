# CLAUDE.md

This file provides quick guidance for Claude Code when working in this repository.

## Project Overview

Clouisle is an enterprise-grade knowledge base and AI Agent platform. The repository is a monorepo with a FastAPI backend and a Next.js frontend.

## Top-level directories

- `backend/` - FastAPI application and business logic
- `frontend/` - Next.js application
- `deploy/` - Docker and deployment files
- `docs/guide/` - user and operator documentation
- `docs/dev/` - internal developer and architecture documentation

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

- Keep changes localized and follow patterns already used in the touched area.
- Keep detailed subsystem rules in `docs/dev/` instead of expanding this file.
- All backend user-facing messages must use i18n.
- Use `BusinessError` for backend business errors.
- Dashboard/admin and platform/user routes remain isolated on both backend and frontend.
- When behavior or conventions change, update the relevant docs under `docs/`.

## i18n tooling (frontend)

- **生成类型**：`node scripts/gen-i18n-types.ts` — 从 `i18n/en/*.json` 生成 `i18n/types/*.ts` 类型定义
- **检查翻译**：`node scripts/lint-translations.ts [--strict]` — 检查缺失键 + ICU 格式 + 类型对齐
- 类型文件（`i18n/types/`）是自动生成的，**不要手动编辑**
- 代码中引用 i18n 文本使用生成的类型：`t('workflow.run')` → typed, 无需手动写字符串字面量
- **新增翻译时，`en/` 和 `zh/` 必须同步添加**（不是只改 en 然后期待自动同步），改完重新生成类型
- `zh/` 的翻译为中文，`en/` 的翻译为英文，不要出现中文 key 或英文 key

## Read these docs for details

### General developer docs
- `docs/dev/README.md`
- `docs/dev/analysis/README.md`

### Backend
- `docs/dev/api/BACKEND_API.md`
- `docs/dev/backend/api-conventions.md`
- `docs/dev/backend/migrations-and-init-data.md`
- `docs/dev/backend/audit-logging.md`
- `docs/dev/backend/celery-and-async-jobs.md`

### Frontend
- `docs/dev/frontend/conventions.md`

### Design specs
- `docs/dev/design/README.md`
- `docs/dev/design/access-control/RBAC_SPEC.md`
- `docs/dev/design/access-control/TEAM_MODEL_AUTH_SPEC.md`
- `docs/dev/design/app-platform/WORKFLOW_ENGINE_ARCHITECTURE.md`
- `docs/dev/design/app-platform/TOOL_SYSTEM_SPEC.md`

### Design grouping map
- `docs/dev/design/app-platform/` - Agent, workflow, node, and tool platform specs
- `docs/dev/design/ai-data/` - LLM, knowledge base, and memory specs
- `docs/dev/design/access-control/` - RBAC, team auth, and quota-related specs
- `docs/dev/design/notifications/` - notification and external channel specs

## Pre-commit checks

Before commit, make sure these pass:
- Backend: `ruff check`, `ruff format --check`, `mypy app/`
- Frontend: `bun run lint`, `bun run build`
