# Permission System Audit Report

## Scope

This report summarizes the current permission-system verification and follow-up audit across:

- Built-in global roles and default assignment
- Team member roles and team-role synchronization
- Effective permission checks
- Agent / Workflow / Viewer / Member boundaries
- Admin / platform route isolation
- Completeness, consistency, compliance, and maintainability risks

Primary implementation references:

- `backend/app/core/permissions.py`
- `backend/app/core/init_data.py`
- `backend/app/api/deps.py`
- `backend/app/services/team_role_sync.py`
- `backend/app/api/v1/endpoints/teams.py`
- `frontend/lib/route-permissions.ts`

## Verification Summary

### Confirmed Behavior

- `User.is_superuser` bypasses normal `PermissionChecker` checks.
- `PermissionChecker` checks global `User -> Role -> Permission` codes only.
- A literal `*` permission satisfies any `PermissionChecker` requirement.
- Team membership and resource visibility checks are implemented separately from global permission checks.
- Built-in global roles are `Super Admin`, `Admin`, `Member`, and `Viewer`.
- Team roles are currently intended as `owner`, `admin`, `member`, and `viewer`.
- `default_team_role` allows `viewer`, `member`, and `admin`; `owner` is not automatically assigned.
- Global `Viewer` is not true read-only: it can read/use resources through `chat`, `run`, and `execute` permissions.
- Team `viewer` does not automatically grant global `Viewer`.

### Fixes Already Applied in This Branch

- Removed `agent:delete` and `workflow:delete` from default global `Member` role initialization.
- Changed workbench home to use the platform conversation trends API instead of the admin conversation trends API.
- Replaced stale `dashboard:access` checks in conversation stats/trends with `admin:dashboard:access`.
- Updated permission docs to clarify:
  - `*` vs `is_superuser`
  - global roles vs team roles
  - default role/default team behavior
  - Viewer as view/use-only, not strict read-only
  - `team_role_sync` now mirrors team roles into `ScopedRoleAssignment` and no longer grants/removes global `Admin` / `Member`
  - default team registration creates `TeamMember` and immediately mirrors it into `ScopedRoleAssignment`
  - resource helpers have inconsistent team-role thresholds today

## Key Findings

### Fixed: Team Roles No Longer Grant Global Admin Powers

Team `owner` / `admin` now syncs to a team-scoped `Admin` assignment through `ScopedRoleAssignment`, not to the user's global roles. Scoped assignments are evaluated only for the requested scope, and `admin:*` remains global-only.

**Impact**: Team-local administration no longer creates a platform-wide global admin capability path.

**Follow-up**: Historical global `Admin` / `Member` assignments are not automatically removed because old data did not track whether they were manual or sync-derived.

---

### Fixed: Team Role Sync No Longer Removes Manual Global Roles

`sync_user_role_from_teams()` now maintains team-scoped assignments for the user's active teams and removes stale team-scoped assignments only. It no longer removes global roles named `Admin` or `Member`.

**Impact**: Manual global role assignments are preserved when team membership changes.

**Follow-up**: Operators may still need a one-time review of legacy global `Admin` / `Member` grants created before this change.

---

### Fixed: Default Team Assignment Creates Scoped Permissions

Default team registration now creates the `TeamMember` and immediately mirrors the membership into `ScopedRoleAssignment`. A user assigned to the default team receives effective team-scoped permissions without waiting for a later sync path.

**Impact**: The displayed default team role and the user's scoped team permissions are aligned at registration time.

---

### Fixed: Workflow Metrics Are Permission-Gated

Workflow metrics endpoints now enforce explicit permissions. Per-workflow reads require workflow access plus `workflow:read`; dashboard/global runtime reads require `admin:dashboard:access`; cache deletion requires `admin:settings:update`.

**Impact**: Authenticated users without the relevant team-scoped or global admin permission can no longer view runtime metrics or clear workflow cache.

---

### Fixed: Workflow Version Endpoints Enforce RBAC and Resource Access

Workflow version create, publish, archive, rollback, and read paths now validate workflow access and enforce the expected permission code for the action.

**Impact**: Authenticated users can no longer mutate or read workflow versions unless they can access the workflow and satisfy the relevant workflow permission.

---

### High: Default Admin Role Is Overbroad

Global `Admin` combines dashboard access, user management, audit export, admin resource management, and platform resource capabilities.

**Impact**: It is hard to assign a limited operational admin role without granting unrelated sensitive access.

**Recommendation**: Split global admin capabilities into narrower roles, for example:

- Dashboard Admin
- User Admin
- Audit Viewer
- Audit Exporter
- Platform Operator
- Content Admin

---

### High: Wildcard Permission Is Dangerous Outside Superuser

A role containing `*` satisfies all `PermissionChecker` checks. The code does not fully guarantee that only actual superusers can ever receive a role with `*`.

**Impact**: If `*` is assigned to a custom role, that role becomes effectively all-powerful for global permission checks.

**Recommendation**: Treat `*` as internal-only:

- prevent custom assignment of `*`
- or make `PermissionChecker` honor `*` only when `current_user.is_superuser` is true

---

### Medium: Team Member Role Values Are Not Strictly Validated

Team member role schemas accept strings. Add/update member logic blocks `owner` in some paths but does not consistently reject unknown values.

**Impact**: Invalid roles such as `admin ` or `superadmin` can be stored, producing undefined behavior.

**Recommendation**: Use a strict enum / `Literal["viewer", "member", "admin"]` at schema boundaries, and add a DB constraint if supported.

---

### Fixed: Team Access Helpers Are Centralized for Core Resources

Core Team, Agent, and Workflow paths now share explicit team/workflow access helpers, and the `require_admin=True` path consistently means team `owner` or `admin`.

**Impact**: Team `member` no longer passes owner/admin-only checks through divergent Agent/Workflow helper behavior.

**Follow-up**: Continue migrating Knowledge Base, Tool, Skill, and Notification helpers to the shared helper as those files are touched.

---

### Medium: Permission Registry Is Not a True Single Source of Truth

Permission codes are hardcoded across:

- `SystemPermissions`
- role initialization lists
- backend `PermissionChecker("...")` calls
- frontend route permissions
- docs tables

**Impact**: Drift is expected. A typo or missing role preset entry may become a runtime authorization bug.

**Recommendation**:

- derive role presets from `SystemPermissions` constants/groups
- replace backend permission string literals with constants as files are touched
- add a CI test that verifies every role preset and route permission exists in the backend permission catalog

---

### Medium: Admin / Platform Split Is Conceptually Mixed

Routes distinguish admin permissions from platform permissions in several places, but the default global `Admin` role intentionally bundles both.

**Impact**: The route model says “separate,” while the preset role model says “combined.” This is workable but must be explicit.

**Recommendation**: Document default `Admin` as “dashboard + platform operator,” or split it into separate global roles.

---

### Medium: Notification Delete Permission Is Defined but Not Enforced

`admin:notification:delete` exists and is assigned to Admin, but the delete endpoint uses active-user authentication plus ad hoc scope checks rather than `PermissionChecker("admin:notification:delete")`.

**Impact**: Custom roles granted that permission do not reliably get the capability; other users may pass through team-scope checks without that explicit permission.

**Recommendation**: Add `PermissionChecker("admin:notification:delete")`, then keep scope checks for data isolation only.

---

### Medium: Memory Permissions Are Inconsistent

Platform memory permissions are defined, but preset roles do not initialize them consistently, memory endpoints are mostly ownership/auth based, and frontend UI checks some memory permission codes.

**Impact**: Memory behavior is neither clearly RBAC-managed nor clearly ownership-only.

**Recommendation**: Pick one model:

- RBAC-managed: enforce/grant memory permissions consistently.
- Ownership-only: remove unused permission gates and document ownership-only semantics.

---

### Medium: RBAC Changes Need Better Audit Logging

Role and permission create/update/delete flows do not consistently log before/after permission sets. User role assignment audit details are limited.

**Impact**: Privilege changes may be hard to reconstruct during incident review.

**Recommendation**: Audit all role/permission/user-role changes with actor, target, before/after role and permission IDs, request metadata, and failure events.

---

### Medium: SSO Default Team Documentation Is Incomplete

Local registration assigns the default team. SSO user creation assigns provider/global default role but does not assign default team in the same way.

**Impact**: Operator/user docs can overpromise SSO provisioning behavior.

**Recommendation**: Either call default-team assignment during SSO user creation, or update SSO docs to say default team assignment currently applies to local registration only.

---

### Low: Frontend Permission Guards Are Duplicated

Two frontend `PermissionGuard` implementations exist with different behavior.

**Impact**: UI authorization fixes can land in one guard but not the other.

**Recommendation**: Keep one guard and one hook, then migrate callers.

---

### Low: Unknown Frontend Routes Default to Allowed

`canAccessRoute()` allows routes with no config.

**Impact**: New dashboard/admin pages can be exposed in the frontend until backend rejects them.

**Recommendation**: Fail closed for dashboard/admin route groups unless explicitly public.

---

### Low: Permission Docs Are Still Summary-Level

The admin guide intentionally summarizes permissions, but it omits some categories such as `admin:app:*`, `admin:capability:*`, `admin:knowledge-base:*`, `admin:team:*`, and `skill:*`.

**Impact**: Operators cannot fully design custom roles from the summary table alone.

**Recommendation**: Generate permission tables from `SystemPermissions.get_all_definitions()` or add a doc check that fails when a permission code is undocumented.

## Recommended Roadmap

### Phase 1: Close Immediate Authorization Holes

1. Enforce `admin:notification:delete` on notification deletion.
2. Strictly validate team member role values.
3. Prevent custom roles from using `*`, or make `*` effective only for `is_superuser`.

### Phase 2: Finish Scoped RBAC Migration

1. Continue migrating Knowledge Base, Tool, Skill, and Notification team checks to shared access helpers as those files are touched.
2. Review historical global `Admin` / `Member` grants that may have been created by legacy team-role sync.
3. Rename docs/UI labels where useful to distinguish:
   - Global Admin / Global Member / Global Viewer
   - Team Owner / Team Admin / Team Member / Team Viewer

### Phase 3: Reduce Drift

1. Continue migrating Knowledge Base, Tool, Skill, and Notification team checks to shared access helpers as those files are touched.
2. Replace backend raw permission strings with `SystemPermissions` constants as files are touched.
3. Add CI checks for:
   - role preset permissions exist in `SystemPermissions`
   - frontend route permission strings exist in backend catalog
   - docs permission tables mention all system permissions or intentionally exclude them

### Phase 4: Clarify Role Model

1. Split broad `Admin` into narrower roles if least privilege matters for production tenants.
2. Decide whether `Viewer` should remain view/use-only or become strict read-only.
3. Decide whether `Member` should retain destructive permissions for KB, Tool, Skill, API Keys, and conversations.
4. Decide whether Memory is RBAC-managed or ownership-only.

## Overall Assessment

The current permission system has a workable foundation: global permission codes, team-scoped role assignments, team membership checks, resource visibility checks, and frontend route gates all exist. The main remaining risk is semantic breadth and drift:

- team roles are mirrored into scoped RBAC assignments, not global roles
- global `Admin` bundles multiple administrative domains
- some non-core resource helpers still have local team-role thresholds
- permission codes are duplicated across backend, frontend, initialization, and docs

The highest-value fix has landed: team roles are decoupled from global roles. Next, continue closing the remaining workflow-adjacent/notification gaps and add small drift tests so future permission changes fail fast in CI.
