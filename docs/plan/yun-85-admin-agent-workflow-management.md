# YUN-85 Admin Agent and Workflow Management Design Document

## Background & Goals

- The admin dashboard currently manages tools and skills under Capabilities, but it lacks equivalent global management for Agents and Workflows.
- User-facing Agent and Workflow pages are scoped by team membership and visibility, so administrators need admin-prefixed APIs that can list and manage resources across teams.
- Success criteria: admins can open a dashboard management page, switch between Agent and Workflow tabs, search/filter/paginate resources, and run management actions such as publish, unpublish, duplicate, and delete.

## High-Level Design

- Backend adds admin-scoped Agent and Workflow endpoints under `/api/v1/admin/agents` and `/api/v1/admin/workflows`.
- Backend endpoints query globally after admin permission checks and do not reuse user/team visibility access checks.
- Frontend adds a dashboard route `/apps`, matching existing admin dashboard route style, with Agent and Workflow tabs based on the existing `/capabilities` page pattern.
- Frontend tables use admin API clients, URL-backed search state, faceted filters, paginated results, badges, and permission-gated row actions.

## Implementation Plan

### Stage 1: Planning docs

- **Files modified**: `docs/IMPLEMENTATION_PLAN.md`, `docs/plan/yun-85-admin-agent-workflow-management.md`
- **Specific logic**: Add the feature to the active implementation index and record the design, stages, testing plan, and risks.
- **Validation**: Confirm the index links to this file and stage statuses reflect implementation progress.

### Stage 2: Backend admin permissions and router registration

- **Files modified**: `backend/app/core/permissions.py`, `backend/app/api/v1/admin/api.py`
- **Specific logic**: Add `admin:app:read`, `admin:app:update`, `admin:app:delete`, `admin:app:publish`, and `admin:app:duplicate` system permissions. Register admin Agent and Workflow routers.
- **Validation**: Startup permission sync should include the new permissions; OpenAPI should show `/api/v1/admin/agents` and `/api/v1/admin/workflows` routes.

### Stage 3: Backend admin Agent endpoints

- **Files modified**: `backend/app/api/v1/admin/endpoints/agents.py`, potentially `backend/app/schemas/agent.py`
- **Specific logic**: Implement global list, filter options, detail, publish, unpublish, duplicate, and delete endpoints using `PermissionChecker("admin:app:*")`. Return admin list data with team, creator, status, visibility, stats, and timestamps.
- **Validation**: Admin requests can list and manage Agents across teams; non-admin requests receive 403; missing Agent IDs return a `BusinessError` not-found response.

### Stage 4: Backend admin Workflow endpoints

- **Files modified**: `backend/app/api/v1/admin/endpoints/workflows.py`, potentially `backend/app/schemas/workflow.py`
- **Specific logic**: Implement global list, filter options, detail, publish, unpublish, duplicate, and delete endpoints using `PermissionChecker("admin:app:*")`. Return admin list data with team, creator, status, visibility, trigger type, version, stats, and timestamps.
- **Validation**: Admin requests can list and manage Workflows across teams; non-admin requests receive 403; missing Workflow IDs return a `BusinessError` not-found response.

### Stage 5: Frontend admin API clients

- **Files modified**: `frontend/lib/api/admin/agents.ts`, `frontend/lib/api/admin/workflows.ts`, `frontend/lib/api/admin/index.ts`
- **Specific logic**: Add typed clients for list, filters, detail, publish, unpublish, duplicate, and delete, following existing admin tools/skills client style.
- **Validation**: TypeScript consumers can import the new clients from the admin API barrel and call the new backend endpoints.

### Stage 6: Dashboard Apps management UI

- **Files modified**: `frontend/app/(dashboard)/apps/page.tsx`, `frontend/app/(dashboard)/apps/_components/admin-agents-panel.tsx`, `frontend/app/(dashboard)/apps/_components/admin-workflows-panel.tsx`, `frontend/app/(dashboard)/apps/_components/index.ts`
- **Specific logic**: Add `/apps` with Agent and Workflow tabs. Each tab loads admin data, supports search/filter/pagination, renders table badges, and exposes row actions for publish/unpublish, duplicate, and delete.
- **Validation**: Admin can navigate to `/apps`, switch tabs, search/filter, paginate, and run row actions with visible table updates.

### Stage 7: Navigation, route permissions, and i18n

- **Files modified**: `frontend/lib/route-permissions.ts`, `frontend/components/layout/app-sidebar.tsx`, `frontend/i18n/en/nav.json`, `frontend/i18n/zh/nav.json`, `frontend/i18n/en/apps.json`, `frontend/i18n/zh/apps.json`, generated i18n type files
- **Specific logic**: Add `/apps` route permission `admin:app:read`, add sidebar entry, add English and Chinese copy, and regenerate i18n types.
- **Validation**: Sidebar item is permission-gated, route guard blocks users without `admin:app:read`, and frontend type generation succeeds.

## Testing Strategy

- Backend checks: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy app/`, `uv run pytest`.
- Frontend checks: `node scripts/gen-i18n-types.ts`, `bun run lint`, `bun run build`.
- Manual happy path: admin opens `/apps`, loads both tabs, filters results, paginates, publishes/unpublishes, duplicates, and deletes test resources.
- Negative tests: non-admin cannot see or access `/apps`; direct calls to new admin APIs return 403; missing resources return not-found errors.
- Regression scope: existing user-facing `/app/apps`, `/agents`, `/workflows`, and admin `/capabilities` continue to work.

## Risks & Mitigation

- Global admin endpoints could accidentally reuse user visibility checks. Mitigation: query globally in admin modules and rely on `PermissionChecker` only.
- Agent records contain credentials and runtime config. Mitigation: keep the first admin UI to list/status/duplicate/delete actions and avoid broad credential editing.
- Frontend route guards only support a single permission per route. Mitigation: use shared `admin:app:read` for the page.
- Translation keys can drift. Mitigation: update both English and Chinese files and regenerate i18n types.
- Rollback plan: remove the `/apps` route/sidebar entry and unregister the two admin routers; database data is not migrated by this feature.
