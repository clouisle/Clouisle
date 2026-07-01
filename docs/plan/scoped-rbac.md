# Scoped RBAC Design Document

## Background & Goals

The current permission system combines global RBAC with team-local roles and then syncs team roles back into global roles. This creates two problems:

- a team-local `admin` can receive global `Admin` permissions;
- removing team membership can remove global `Admin` / `Member` roles even when they were assigned manually.

Goals:

- close known authorization gaps before changing schema;
- centralize team access checks;
- add team-scoped role assignments without removing existing global roles;
- keep `admin:*` permissions global-only;
- keep resource visibility and creator ownership checks separate from RBAC.

## High-Level Design

The landing is staged.

1. Add one shared team-access helper and patch high-risk Workflow endpoints.
2. Add an additive scoped role assignment table and backfill it from `TeamMember.role`.
3. Add scoped permission helpers and migrate Team, Agent, and Workflow checks first.
4. Frontend compatibility was not needed for this landing because the backend did not expose scoped permission data in `/users/me`.

Existing global `PermissionChecker` remains the global/admin-route gate. Scoped checks are added beside it; they do not replace the whole authorization stack in one pass.

## Implementation Plan

### Stage 1: Shared team access and immediate workflow authorization fixes

- **Status**: Completed.

- **Files modified**:
  - `backend/app/api/team_access.py`
  - `backend/app/api/v1/endpoints/agents.py`
  - `backend/app/api/v1/endpoints/workflows.py`
  - `backend/app/api/v1/workflow_versions.py`
  - `backend/app/api/v1/workflow_metrics.py`
  - representative team helper call sites as needed

- **Specific logic**:
  - Add shared `check_team_access(team_id, user, require_admin=False)`.
  - Use `owner/admin` only for `require_admin=True`.
  - Reuse or extract workflow resource access checks for version and metrics endpoints.
  - Add permission checks for workflow version read/update/publish actions.
  - Require admin permission for global workflow metrics/cache endpoints.

- **Validation**:
  - Non-member gets 403 for team resources.
  - Team member cannot pass owner/admin-only checks.
  - Workflow version and metrics endpoints reject unrelated users.

### Stage 2: Scoped role assignment model and migration

- **Status**: Completed.

- **Files modified**:
  - `backend/app/models/user.py`
  - `backend/app/core/init_data.py`
  - `backend/app/services/team_role_sync.py`
  - `backend/app/api/v1/admin/endpoints/roles.py`

- **Specific logic**:
  - Add `ScopedRoleAssignment` with `user`, `role`, `scope_type`, `scope_id`, `source`, timestamps, and unique `(user, role, scope_type, scope_id)`.
  - Add idempotent startup migration and indexes.
  - Backfill team memberships into scoped assignments.
  - Update role deletion guard to reject roles used by scoped assignments.
  - Stop new team-role changes from granting global `Admin`.
  - Do not bulk-remove existing global `Admin` / `Member` roles.

- **Validation**:
  - Migration is idempotent.
  - Scoped assignments are created for existing team members.
  - Existing global permission checks still pass.

### Stage 3: Scoped permission helper and first endpoint migration

- **Status**: Completed.

- **Files modified**:
  - `backend/app/api/scoped_permissions.py` or `backend/app/api/deps.py`
  - `backend/app/api/v1/endpoints/teams.py`
  - `backend/app/api/v1/endpoints/agents.py`
  - `backend/app/api/v1/endpoints/workflows.py`

- **Specific logic**:
  - Add `user_has_global_permission`, `user_has_scoped_permission`, and `check_scoped_permission` in `deps.py`.
  - Resolution order: superuser, global permission, scoped permission, deny.
  - Ensure scoped team roles do not satisfy `admin:*`.
  - Apply scoped checks first to Team, Agent, and Workflow paths.

- **Validation**:
  - Team-scoped Admin works only in its team.
  - Team-scoped Admin cannot access dashboard/admin routes.
  - Scoped permission tests cover global-only `admin:*` denial and non-admin scoped permission allow.
  - Superuser bypass remains intact.

### Stage 4: Frontend compatibility if needed

- **Status**: Completed.

- **Files modified**:
  - `frontend/lib/api/auth.ts`
  - `frontend/hooks/use-permissions.ts`
  - `frontend/components/permission-guard.tsx`

- **Specific logic**:
  - Keep flat role permissions working.
  - Add optional scoped permission shape only if `/users/me` exposes it.
  - Extend `hasPermission(permission, teamId?)` without changing old callers.
  - Do not add `X-Team-ID`.

- **Validation**:
  - Existing guards still work.
  - Frontend lint passes if frontend files change.

### Stage 5: Documentation and cleanup

- **Status**: Completed.

- **Files modified**:
  - `docs/dev/design/access-control/RBAC_SPEC.md`
  - `docs/dev/design/access-control/PERMISSION_AUDIT_REPORT.md`
  - relevant user/admin permission guides

- **Specific logic**:
  - Document scoped RBAC as the target model.
  - Mark team-to-global sync as legacy or removed depending on final code.
  - Document that legacy global roles are not automatically removed.

- **Validation**:
  - Docs match implementation behavior.

## Testing Strategy

- Backend targeted tests for team access, workflow versions, workflow metrics, scoped assignment migration, scoped permission checks, and role deletion guard.
- `uv run ruff check` and `uv run ruff format --check` for changed backend files.
- `uv run mypy app/` if feasible.
- `bun run lint` only if frontend files change.

## Risks & Mitigation

- **Risk**: removing global `Admin` / `Member` breaks users because current data lacks source tracking.  
  **Mitigation**: do not bulk-remove existing global roles.

- **Risk**: member edit behavior changes for Agent/Workflow.  
  **Mitigation**: first enforce explicit owner/admin semantics where helper says admin; scoped roles can later grant finer write permissions intentionally.

- **Risk**: large migration surface.  
  **Mitigation**: additive table, idempotent migration, and staged endpoint rollout.

- **Rollback**: previous code can ignore the additive scoped assignment table. Stage 1 changes are file-local and reversible.
