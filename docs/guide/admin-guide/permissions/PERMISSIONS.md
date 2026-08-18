# Permission System

This document describes the permission system design of the Clouisle platform, including special permissions, permission combinations, and data visibility rules.

For exact implementation semantics, use `docs/dev/design/access-control/RBAC_SPEC.md` as the source of truth. This guide is operator-facing and intentionally summarizes the current model.

## 1. Permission Categories

### 1.1 Special Permissions

| Permission | Description | Purpose |
|------------|-------------|---------|
| `*` | Wildcard permission code | Satisfies permission-code checks; `User.is_superuser` is the runtime bypass used by backend checks |
| `admin:dashboard:access` | Dashboard access | Controls access to admin dashboard, key permission distinguishing "admin" from "regular user" |

### 1.2 Dashboard Management Permissions (requires `admin:dashboard:access`)

These permissions are for dashboard management functions, typically only admin roles have them:

| Permission | Description |
|------------|-------------|
| `admin:user:read/create/update/delete` | User management |
| `admin:role:read/create/update/delete` | Role management |
| `admin:permission:read` | View permission list |
| `admin:model:read/create/update/delete` | Model management |
| `admin:memory:read` | View memory records |
| `admin:conversation:read/delete` | Dashboard conversation management |
| `admin:notification:create/delete` | Dashboard notification management |
| `admin:team:read/create/update/delete` | System-wide team management |
| `admin:app:read/create/update/delete/publish/duplicate` | Agent and workflow (App) management across teams |
| `admin:capability:read/create/update/delete/execute` | Tool and skill (Capability) management across teams |
| `admin:knowledge-base:read/test/create/update/delete` | Knowledge base management from admin |
| `admin:settings:read` | View site settings |
| `admin:settings:update` | Modify site settings |
| `admin:sso:read` | View SSO providers and configuration |
| `admin:sso:update` | Manage SSO providers and user SSO connections |
| `audit:read` | View audit logs |
| `audit:export` | Export audit logs |

### 1.3 Resource Management Permissions (with data isolation)

These permissions are for managing business resources. All users may have them, but data is subject to team isolation:

| Permission | Description |
|------------|-------------|
| `team:read/create/update/delete/manage` | Team management |
| `agent:read/create/update/delete/publish/chat` | Agent management |
| `workflow:read/create/update/delete/publish/run/execute` | Workflow management |
| `kb:read/test/create/update/delete` | Knowledge base management |
| `tool:read/create/update/delete/execute` | Tool management |
| `skill:read/create/update/delete/execute` | Skill management |
| `apikey:read/create/update/delete` | API Key management |
| `conversation:read/delete` | Conversation management |

---

## 2. Role Definitions

### 2.1 System Preset Roles

| Role | Description | Key Permissions |
|------|-------------|-----------------|
| **Super Admin** | Super administrator | `*` (all permissions) |
| **Admin** | Dashboard administrator | `admin:dashboard:access` + system read visibility + team-scoped resource management |
| **Member** | Collaborative member | Daily resource creation and editing without dashboard access |
| **Viewer** | Default read/use-only user | Read/chat/run/execute permissions without dashboard access |

### 2.2 Role Permission Comparison

| Permission | Super Admin | Admin | Member | Viewer |
|------------|:-----------:|:-----:|:------:|:------:|
| `*` | ✓ | | | |
| `admin:dashboard:access` | ✓ | ✓ | | |
| `admin:user:*` | ✓ | ✓ | | |
| `admin:role:read` | ✓ | ✓ | | |
| `admin:role:create/update/delete` | ✓ | | | |
| `admin:permission:read` | ✓ | ✓ | | |
| `admin:permission:create/update/delete` | ✓ | | | |
| `admin:model:*` | ✓ | ✓ | | |
| `admin:memory:read` | ✓ | ✓ | | |
| `admin:conversation:read/delete` | ✓ | ✓ | | |
| `admin:notification:create/delete` | ✓ | ✓ | | |
| `admin:settings:read` | ✓ | ✓ | | |
| `admin:settings:update` | ✓ | | | |
| `admin:sso:read` | ✓ | ✓ | | |
| `admin:sso:update` | ✓ | | | |
| `audit:read` | ✓ | ✓ | | |
| `audit:export` | ✓ | ✓ | | |
| `team:read` | ✓ | ✓ | ✓ | ✓ |
| `team:create/update/manage` | ✓ | ✓ | | |
| `team:delete` | ✓ | ✓ | | |
| `agent:read/chat` | ✓ | ✓ | ✓ | ✓ |
| `agent:create/update` | ✓ | ✓ | ✓ | |
| `agent:delete/publish` | ✓ | ✓ | | |
| `workflow:read/run` | ✓ | ✓ | ✓ | ✓ |
| `workflow:create/update` | ✓ | ✓ | ✓ | |
| `workflow:delete/publish` | ✓ | ✓ | | |
| `workflow:execute` | ✓ | ✓ | | |
| `kb:read` | ✓ | ✓ | ✓ | ✓ |
| `kb:test` | ✓ | ✓ | ✓ | ✓ |
| `kb:create/update` | ✓ | ✓ | ✓ | |
| `kb:delete` | ✓ | ✓ | ✓ | |
| `tool:read/execute` | ✓ | ✓ | ✓ | ✓ |
| `tool:create/update/delete` | ✓ | ✓ | ✓ | |
| `skill:read/execute` | ✓ | ✓ | ✓ | ✓ |
| `skill:create/update/delete` | ✓ | ✓ | ✓ | |
| `apikey:read` | ✓ | ✓ | ✓ | |
| `apikey:create/update/delete` | ✓ | ✓ | ✓ | |
| `conversation:read` | ✓ | ✓ | ✓ | ✓ |
| `conversation:delete` | ✓ | ✓ | ✓ | |

### 2.3 Default Assignment

New users receive the configured default global role. During system initialization, `default_role_id` is set to the global **Viewer** role when no default exists.

If `default_team_id` is configured, new users also join that team with `default_team_role`. The default team role is `member`; valid automatic team roles are `viewer`, `member`, and `admin`. `owner` is never assigned automatically.

Global roles and team roles are separate: global roles provide permission codes, while team roles are mirrored into team-scoped role assignments. Team-scoped permissions apply only inside the target team and cannot satisfy `admin:*` dashboard permissions.

### 2.4 Scoped Team Role Assignments

Team membership is mirrored into team-scoped role assignments:

| Team role | Scoped role in that team |
|-----------|--------------------------|
| Owner | Admin |
| Admin | Admin |
| Member | Member |
| Viewer | Viewer |

This does not grant or remove global roles. Legacy global `Admin` / `Member` assignments from earlier behavior are not automatically cleaned up because their source cannot be distinguished from manual assignments.

---

## 3. Data Visibility and Isolation

### 3.1 Scope model

- **Dashboard APIs** under `/api/v1/admin/...` are system-wide for users with the required `admin:*`, `audit:*`, or dashboard permission. They are not automatically limited to the administrator's team; for example, admin Agents/Workflows and team listings query system resources.
- **Platform APIs** under `/api/v1/...` enforce the resource's team membership and permission checks. Use these endpoints when documenting team-isolated resource access.
- **Super Admin/Admin** is a dashboard authorization distinction, not a promise that every endpoint exposes the same data scope. Conversation and statistics endpoints have their own ownership/team rules.

### 3.2 Impact of `admin:dashboard:access`

`admin:dashboard:access` controls access to dashboard surfaces. Each surface still requires its specific permission, such as `admin:user:read`, `admin:model:read`, `admin:settings:read`, or `audit:read`. Without the dashboard permission, users should use the corresponding team-scoped platform routes where available.

### 3.3 Team-scoped resource access

For platform Agents, Workflows, Knowledge Bases, Tools, and similar resources, the effective scope is determined by the resource's team membership and the caller's scoped permission. A system resource such as an unscoped Skill or an explicitly shared Tool may follow different rules; do not infer universal isolation from the role name.

### 3.4 Practical rule

Document the route and permission together: identify whether the example calls `/api/v1/admin/...` (system-wide dashboard API) or `/api/v1/...` (team-scoped platform API), then apply the endpoint's explicit ownership and membership checks.

---

## 4. Permission Combination Scenarios

### 4.1 Regular platform user

A Member or Viewer without `admin:dashboard:access` can use platform routes only where their scoped permissions allow it. For example, a Viewer may read/chat/run resources but cannot create, modify, delete, or publish them.

### 4.2 Dashboard administrator

An Admin with `admin:dashboard:access` can use each system-wide dashboard API for which it has the required `admin:*` or `audit:*` permission. Do not describe the result as limited to the Admin's teams unless that specific endpoint documents a team filter.

### 4.3 Site settings and SSO

`admin:settings:read`/`admin:settings:update` and `admin:sso:read`/`admin:sso:update` remain separate permissions. The current role matrix grants update permissions to Super Admin; Admin is read-only for these settings unless an explicit custom role changes that assignment.

### 4.4 Audit log archiving

Editing storage settings requires `admin:settings:update`; archiving/exporting audit logs requires `audit:export`. These capabilities are independent and should not share one frontend gate.
---

## 5. Frontend Menu Visibility

### 5.1 Sidebar Menu Permission Mapping

| Menu Item | Required Permission | Super Admin | Admin | Member | Viewer |
|-----------|---------------------|:-----------:|:-----:|:------:|:------:|
| Dashboard | `admin:dashboard:access` | ✓ | ✓ | | |
| Teams | `team:read` | ✓ | ✓ | ✓ | ✓ |
| Knowledge Bases | `admin:knowledge-base:read` | ✓ | ✓ | | |
| Activities | `conversation:read` | ✓ | ✓ | ✓ | ✓ |
| Users | `admin:user:read` | ✓ | ✓ | | |
| Roles | `admin:role:read` | ✓ | ✓ | | |
| Permissions | `admin:permission:read` | ✓ | ✓ | | |
| API Keys | `apikey:read` | ✓ | ✓ | ✓ | |
| Models | `admin:model:read` | ✓ | ✓ | | |
| Apps | `admin:app:read` | ✓ | ✓ | | |
| Capabilities | `admin:capability:read` | ✓ | ✓ | | |
| Memories | `admin:memory:read` | ✓ | ✓ | | |
| Observability | `admin:dashboard:access` | ✓ | ✓ | | |
| Notifications | `admin:dashboard:access` | ✓ | ✓ | | |
| Audit Logs | `audit:read` | ✓ | ✓ | | |
| Site Settings | `admin:settings:read` | ✓ | ✓ | | |

### 5.2 Management Menu Group Visibility

The "Management" menu group (including Users, Roles, Permissions, Models, Audit Logs, etc.) is only visible when the user has `admin:dashboard:access` permission.

---

## 6. API Permission Checks

### 6.1 Permission Check Methods

```python
# Method 1: Single permission check
current_user: User = Depends(PermissionChecker("admin:user:read"))

# Method 2: Super admin only (deprecated, use permission check instead)
# current_user: User = Depends(get_current_active_superuser)
```

### 6.2 Data Isolation Implementation

```python
# Check for admin permission
has_dashboard_access = current_user.is_superuser
if not has_dashboard_access:
    for role in current_user.roles:
        for perm in role.permissions:
            if perm.code == "admin:dashboard:access" or perm.code == "*":
                has_dashboard_access = True
                break

# Filter data based on permission level
if current_user.is_superuser:
    # Super admin: no filter
    query = Model.all()
elif has_dashboard_access:
    # Admin: team-level filter
    query = Model.filter(team_id__in=user_team_ids)
else:
    # Regular user: user-level filter (e.g., conversations)
    query = Model.filter(user_id=current_user.id)
```

---

## 7. Best Practices

### 7.1 Role Assignment Recommendations

| User Type | Recommended Role | Description |
|-----------|------------------|-------------|
| System Administrator | Super Admin | Responsible for system configuration, user management |
| Department Manager | Admin | View dashboard data and manage team resources without changing the permission system |
| Developer | Member | Create and edit day-to-day resources without dashboard access |
| Business User | Viewer | Default view/use-only access for using agents and workflows |

### 7.2 Custom Roles

You can create custom roles based on business needs, for example:

**Data Analyst**:
- `agent:read`, `agent:chat`
- `workflow:read`, `workflow:run`
- `kb:read`
- `conversation:read`

**Content Manager**:
- `kb:read`, `kb:create`, `kb:update`, `kb:delete`
- `agent:read`

### 7.3 Principle of Least Privilege

- Only grant users the minimum permissions needed to complete their work
- Avoid assigning `admin:dashboard:access` permission to regular users
- `admin:settings:update` permission should be limited to system administrators only
- Review legacy global `Admin` / `Member` grants after enabling scoped RBAC; team roles no longer maintain those global roles
