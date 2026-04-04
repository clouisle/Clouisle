# Permission System

This document describes the permission system design of the Clouisle platform, including special permissions, permission combinations, and data visibility rules.

## 1. Permission Categories

### 1.1 Special Permissions

| Permission | Description | Purpose |
|------------|-------------|---------|
| `*` | Super permission | Only Super Admin role has this, bypasses all permission checks |
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
| `workflow:read/create/update/delete/publish/run` | Workflow management |
| `kb:read/create/update/delete` | Knowledge base management |
| `tool:read/create/update/delete/execute` | Tool management |
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
| **Viewer** | Default read-only user | Read/chat/run/execute permissions without dashboard access |

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
| `kb:read` | ✓ | ✓ | ✓ | ✓ |
| `kb:create/update` | ✓ | ✓ | ✓ | |
| `kb:delete` | ✓ | ✓ | | |
| `tool:read/execute` | ✓ | ✓ | ✓ | ✓ |
| `tool:create/update/delete` | ✓ | ✓ | | |
| `apikey:read` | ✓ | ✓ | ✓ | |
| `apikey:create/update/delete` | ✓ | ✓ | ✓ | |
| `conversation:read` | ✓ | ✓ | ✓ | ✓ |
| `conversation:delete` | ✓ | ✓ | ✓ | |

---

## 3. Data Isolation Rules

### 3.1 Core Concepts

- **Super Admin**: No data isolation, can access all system data
- **Admin**: Team-level isolation, can access all data of their teams
- **Member/Viewer**: Team-level isolation + user-level isolation (for conversation data)

### 3.2 Impact of `admin:dashboard:access` Permission

`admin:dashboard:access` is the key permission distinguishing "admin view" from "user view":

| Data Type | With `admin:dashboard:access` | Without `admin:dashboard:access` |
|-----------|------------------------|---------------------------|
| User list | Visible (requires `admin:user:read`) | Not visible |
| Role list | Visible (requires `admin:role:read`) | Not visible |
| Model list | Visible (requires `admin:model:read`) | Not visible |
| Audit logs | Visible (requires `audit:read`) | Not visible |
| Site settings | Visible (requires `admin:settings:read`) | Not visible |
| **Conversation list** | **All users' conversations in team** | **Only own conversations** |
| **Conversation stats** | **Stats for all team conversations** | **Stats for own conversations only** |

### 3.3 Special Isolation for Conversation Data

Conversation data has finer-grained isolation:

```
Super Admin
└── Can view all conversations

Admin (has admin:dashboard:access)
└── Can view all users' conversations in their teams
    └── All conversations in Team A
    └── All conversations in Team B (if member)

Member / Viewer (no admin:dashboard:access)
└── Can only view own conversations
    └── Own conversations created in Team A
    └── Own conversations created in Team B
```

### 3.4 Isolation for Other Resources

For resources other than conversations (Agent, Workflow, Knowledge Base, etc.):

| Role | Visible Scope |
|------|---------------|
| Super Admin | All resources |
| Admin | All resources in their teams |
| Member | All resources in their teams |
| Viewer | All resources in their teams (read-only) |

---

## 4. Permission Combination Scenarios

### 4.1 Scenario: Regular User Viewing Activity Logs

**User Role**: Member or Viewer (no `admin:dashboard:access`)

**Visible Data**:
- ✓ Own created conversations
- ✓ Own conversation statistics
- ✗ Other team members' conversations
- ✗ Dashboard management menu

### 4.2 Scenario: Admin Viewing Activity Logs

**User Role**: Admin (has `admin:dashboard:access`)

**Visible Data**:
- ✓ All users' conversations in team
- ✓ Team-level conversation statistics
- ✓ Dashboard management menu
- ✗ Other teams' conversations

### 4.3 Scenario: Read-Only User

**User Role**: Viewer (default role)

**Allowed Operations**:
- ✓ View team resources (Agent, Workflow, Knowledge Base, etc.)
- ✓ Chat with Agent (`agent:chat`)
- ✓ Run workflows (`workflow:run`)
- ✓ Execute tools (`tool:execute`)
- ✗ Create/modify/delete any resources
- ✗ Access dashboard management

### 4.4 Scenario: Site Settings Management

| Role | `admin:settings:read` | `admin:settings:update` | Allowed Operations |
|------|:---------------:|:-----------------:|-------------------|
| Super Admin | ✓ | ✓ | View and modify all settings |
| Admin | ✓ | ✗ | View settings only |
| Member | ✗ | ✗ | No access |

### 4.5 Scenario: SSO Management

| Role | `admin:sso:read` | `admin:sso:update` | Allowed Operations |
|------|:----------------:|:------------------:|-------------------|
| Super Admin | ✓ | ✓ | View and manage all SSO providers and disconnect SSO connections |
| Admin | ✓ | ✗ | View SSO configuration only |
| Member | ✗ | ✗ | No access |

### 4.6 Scenario: Audit Log Archiving

- Editing storage settings requires `admin:settings:update`
- Archiving audit logs requires `audit:export`
- These two capabilities are independent and should not share a single frontend gate

---

## 5. Frontend Menu Visibility

### 5.1 Sidebar Menu Permission Mapping

| Menu Item | Required Permission | Super Admin | Admin | Member | Viewer |
|-----------|---------------------|:-----------:|:-----:|:------:|:------:|
| Dashboard | `admin:dashboard:access` | ✓ | ✓ | | |
| Teams | `team:read` | ✓ | ✓ | ✓ | ✓ |
| Knowledge Bases | `kb:read` | ✓ | ✓ | ✓ | ✓ |
| Activities | `conversation:read` | ✓ | ✓ | ✓ | ✓ |
| Users | `admin:user:read` | ✓ | ✓ | | |
| Roles | `admin:role:read` | ✓ | ✓ | | |
| Permissions | `admin:permission:read` | ✓ | ✓ | | |
| API Keys | `apikey:read` | ✓ | ✓ | ✓ | |
| Models | `admin:model:read` | ✓ | ✓ | | |
| Tools | `tool:read` | ✓ | ✓ | ✓ | ✓ |
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
| Business User | Viewer | Default read-only access for using agents and workflows |

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
