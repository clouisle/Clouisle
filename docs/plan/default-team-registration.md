# Default Team Registration Design Document

## Background & Goals

- Problem to solve: new users can receive a global default role on registration, but admins cannot configure a default team membership or the user's role inside that team.
- Success criteria:
  - Admins can choose no default team, or one existing team.
  - Admins can choose the default team role: viewer, member, or admin.
  - Newly registered non-first local users are added to the configured team with the configured role.
  - The first registered Super Admin behavior remains unchanged.
  - Global default role assignment stays independent from team role assignment.

## High-Level Design

- Backend stores two private security site settings:
  - `default_team_id`: selected team ID, empty string disables automatic team assignment.
  - `default_team_role`: selected team role, default `member`.
- Admin settings validation prevents saving invalid team IDs or unsupported roles.
- Registration calls a small service helper after existing global default role assignment.
- Frontend security settings page loads admin teams and renders two new controls near the existing default role selector.

## Implementation Plan

### Stage 1: Planning Docs

- **Files modified**: `docs/IMPLEMENTATION_PLAN.md`, `docs/plan/default-team-registration.md`
- **Specific logic**: Register this feature in the high-level plan and document the implementation/test approach.
- **Validation**: Confirm docs describe default team, team role, unsupported owner role, and rollback behavior.

### Stage 2: Backend Settings and Validation

- **Files modified**: `backend/app/models/site_setting.py`, `backend/app/api/v1/admin/endpoints/site_settings.py`
- **Specific logic**:
  - Add `default_team_id` and `default_team_role` to default security settings.
  - Validate `default_team_role` against `viewer`, `member`, and `admin`.
  - Validate non-empty `default_team_id` as an existing non-deleted `Team`.
- **Validation**:
  - Save empty default team successfully.
  - Reject `owner` as default team role.
  - Reject missing/deleted team IDs.

### Stage 3: Registration Assignment

- **Files modified**: `backend/app/services/team_role_sync.py`, `backend/app/api/v1/endpoints/login.py`
- **Specific logic**:
  - Add `assign_default_team(user)` helper.
  - Read settings using `SiteSetting.get_value`.
  - Use `TeamMember.get_or_create` for idempotent membership creation.
  - Skip missing/deleted teams at runtime without failing registration.
  - Call the helper for normal non-first local registration users after `assign_default_role(user)`.
- **Validation**:
  - No default team creates no membership.
  - Valid default team creates membership with viewer/member/admin.
  - First Super Admin registration is unchanged.

### Stage 4: Frontend Settings UI

- **Files modified**: `frontend/lib/api/site-settings.ts`, `frontend/lib/api/admin/site-settings.ts`, `frontend/app/(dashboard)/site-settings/security/page.tsx`, `frontend/i18n/en/siteSettings.json`, `frontend/i18n/zh/siteSettings.json`, generated i18n types
- **Specific logic**:
  - Extend `SecuritySettings` with `default_team_id` and `default_team_role`.
  - Normalize settings defaults in the admin site settings client.
  - Load admin teams in the security settings page.
  - Add default team and default team role selects.
  - Hide unsupported `owner` role from the selector.
  - Regenerate i18n types after translation changes.
- **Validation**:
  - Page loads with existing settings.
  - Empty default team can be selected and saved.
  - Team role select supports viewer/member/admin only.
  - Frontend lint/build pass.

### Stage 5: Tests and Regression Checks

- **Files modified**: focused backend tests, exact test file determined by existing fixtures
- **Specific logic**:
  - Add tests for helper behavior and settings validation where practical.
  - Run existing backend and frontend checks.
- **Validation**:
  - `uv run ruff check .`
  - `uv run mypy app/`
  - `uv run pytest`
  - `node scripts/gen-i18n-types.ts`
  - `bun run lint`
  - `bun run build`

## Testing Strategy

- Happy path tests:
  - Configure a team and role `member`; register a user; verify team membership.
  - Repeat helper-level checks for `viewer` and `admin`.
- Error path tests:
  - Reject `owner` through settings validation.
  - Reject missing team IDs through settings validation.
  - Runtime stale team config does not fail registration.
- Regression scope:
  - Existing global default role assignment still works.
  - First registered user remains Super Admin and keeps current early return behavior.
  - Security settings page continues to save existing password, SSO, and registration fields.

## Risks & Mitigation

- Possible side effect: default team role might be confused with global default role.
  - Mitigation: UI copy explicitly says team role.
- Possible side effect: deleted team config could break registration.
  - Mitigation: admin validation prevents saving deleted teams; runtime helper skips stale values.
- Possible side effect: team role sync could unexpectedly change global RBAC roles.
  - Mitigation: do not call `sync_user_role_from_teams` in the registration helper.
- Rollback plan:
  - Clear `default_team_id` to disable automatic team assignment.
  - Revert the helper call in registration if needed; existing settings are inert without the call.
