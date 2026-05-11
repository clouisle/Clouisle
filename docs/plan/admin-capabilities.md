# Admin Capabilities Design Document

## Background & Goals

- Rename the admin Tools area to Capabilities because it now manages both Tools and Skills.
- Move the admin route from `/tools` to `/capabilities` while keeping the platform route `/app/capabilities` unchanged.
- Add Tools and Skills tabs to the admin Capabilities page.
- Add admin-prefixed backend APIs so admin UI calls `/admin/tools` and `/admin/skills`, not the team-scoped platform APIs.

Success criteria:

- Admin sidebar/search show Capabilities and route to `/capabilities`.
- Tools tab continues to manage tools through admin-prefixed APIs.
- Skills tab manages Skills through admin-prefixed APIs, including system and team scopes.
- Platform `/tools`, `/skills`, and `/app/capabilities` behavior remains unchanged.

## High-Level Design

- Backend adds `admin:capability:*` permissions and routers under `backend/app/api/v1/admin/endpoints/`.
- Admin routers reuse existing tool/skill schemas and services where safe, but do not relax platform API authorization.
- Frontend dashboard route becomes `frontend/app/(dashboard)/capabilities/` with a tabs shell.
- Admin Tools and Skills clients call `frontend/lib/api/admin/tools.ts` and `frontend/lib/api/admin/skills.ts`.

## Implementation Plan

### Stage 1: Admin capability permissions

- **Files modified**: `backend/app/core/permissions.py`, `backend/app/core/init_data.py`, `frontend/i18n/en/permissions.json`, `frontend/i18n/zh/permissions.json`
- **Specific logic**: Add `admin:capability:read/create/update/delete/execute` and seed them into admin roles.
- **Validation**: Check permission sync definitions and frontend permission labels.

### Stage 2: Admin APIs

- **Files modified**: `backend/app/api/v1/admin/api.py`, `backend/app/api/v1/admin/endpoints/tools.py`, `backend/app/api/v1/admin/endpoints/skills.py`, `backend/app/services/skill.py`, `backend/app/services/skill_import.py`, `backend/app/schemas/skill.py`
- **Specific logic**:
  - Add `/admin/tools` endpoints used by the admin Tools UI.
  - Add `/admin/skills` list/detail/update/delete/test/import endpoints.
  - Add admin-only helpers for all-team/system Skill access and import scope handling.
- **Validation**: Confirm admin routes register and platform routes keep existing checks.

### Stage 3: Admin route rename and navigation

- **Files modified**: `frontend/app/(dashboard)/capabilities/`, `frontend/components/layout/app-sidebar.tsx`, `frontend/components/layout/header.tsx`, `frontend/lib/route-permissions.ts`, `frontend/i18n/en/nav.json`, `frontend/i18n/zh/nav.json`, `frontend/i18n/en/tools.json`, `frontend/i18n/zh/tools.json`
- **Specific logic**: Move dashboard `/tools` UI to `/capabilities`, update route pushes/search/sidebar labels, protect `/capabilities` with `admin:capability:read`.
- **Validation**: Build output includes `/capabilities` and `/capabilities/code`; old admin route references are gone or redirect only.

### Stage 4: Admin Tools tab

- **Files modified**: `frontend/app/(dashboard)/capabilities/page.tsx`, `frontend/app/(dashboard)/capabilities/_components/tools-client.tsx`, `frontend/app/(dashboard)/capabilities/code/page.tsx`, `frontend/lib/api/admin/tools.ts`
- **Specific logic**: Add tabs shell, keep existing Tools UI under the Tools tab, switch calls to `adminToolsApi`, and use admin capability permissions.
- **Validation**: Tool list/create/edit/delete/test network calls use `/admin/tools`.

### Stage 5: Admin Skills tab

- **Files modified**: `frontend/app/(dashboard)/capabilities/_components/admin-skills-panel.tsx`, `frontend/lib/api/admin/skills.ts`
- **Specific logic**: Implement system/team scoped Skills management using `/admin/skills`: list/filter, import preview/install, enable/disable, update metadata, delete, and test.
- **Validation**: Skills tab can manage system and team Skills without using team-scoped `/skills` endpoints.

### Stage 6: Validation

- **Files modified**: `docs/IMPLEMENTATION_PLAN.md` status updates only.
- **Specific logic**: Run targeted backend/frontend checks and update implementation status.
- **Validation**:
  - `node scripts/gen-i18n-types.ts`
  - `node scripts/lint-translations.ts`
  - `bun run lint`
  - `bun run build`
  - backend `ruff`/`mypy` or focused checks where practical.

## Testing Strategy

- Happy path: admin opens `/capabilities`, switches between Tools and Skills, and performs basic list/test/import flows.
- Error path: non-admin calls to `/admin/tools` and `/admin/skills` are denied; missing Skill/Tool IDs return 404 business errors.
- Regression scope: platform `/app/capabilities`, platform `/tools`, platform `/skills`, admin models/resources sidebar, and header search.

## Risks & Mitigation

- Admin endpoints could accidentally weaken platform authorization. Keep admin helpers separate and call them only from admin routers.
- Tools API surface is broad. Implement only endpoints used by the current admin UI first, then add missing routes if validation shows a call path.
- SkillsPanel has team-scoped assumptions. Build an admin-specific panel that reuses UI patterns but not platform data access.
- Route rename may break bookmarks. Add a lightweight redirect only if it does not keep duplicate UI code.
