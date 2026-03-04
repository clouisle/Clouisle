# Permission System

This document describes the permission system design of the Clouisle platform, including special permissions, permission combinations, and data visibility rules.

## 1. Permission Categories

### 1.1 Special Permissions

| Permission | Description | Purpose |
|------------|-------------|---------|
| `*` | Super permission | Only Super Admin role has this, bypasses all permission checks |
| `dashboard:access` | Dashboard access | Controls access to admin dashboard, key permission distinguishing "admin" from "regular user" |

### 1.2 Dashboard Management Permissions (requires `dashboard:access`)

These permissions are for dashboard management functions, typically only admin roles have them:

| Permission | Description |
|------------|-------------|
| `user:read/create/update/delete` | User management |
| `role:read/create/update/delete` | Role management |
| `permission:read` | View permission list |
| `model:read/create/update/delete` | Model management |
| `settings:read` | View site settings |
| `settings:update` | Modify site settings |
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
| **Admin** | Administrator | `dashboard:access` + dashboard management + resource permissions |
| **Member** | Member | Resource permissions (no dashboard access) |
| **Viewer** | Viewer | Read-only + execute permissions (no dashboard access) |

### 2.2 Role Permission Comparison

| Permission | Super Admin | Admin | Member | Viewer |
|------------|:-----------:|:-----:|:------:|:------:|
| `*` | ✓ | | | |
| `dashboard:access` | ✓ | ✓ | | |
| `user:*` | ✓ | ✓ | | |
| `role:*` | ✓ | ✓ | | |
| `model:*` | ✓ | ✓ | | |
| `settings:read` | ✓ | ✓ | | |
| `settings:update` | ✓ | | | |
| `audit:*` | ✓ | ✓ | | |
| `team:read` | ✓ | ✓ | ✓ | ✓ |
| `team:create/update/manage` | ✓ | ✓ | ✓ | |
| `team:delete` | ✓ | ✓ | | |
| `agent:read/chat` | ✓ | ✓ | ✓ | ✓ |
| `agent:create/update/delete/publish` | ✓ | ✓ | ✓ | |
| `workflow:read/run` | ✓ | ✓ | ✓ | ✓ |
| `workflow:create/update/delete/publish` | ✓ | ✓ | ✓ | |
| `kb:read` | ✓ | ✓ | ✓ | ✓ |
| `kb:create/update/delete` | ✓ | ✓ | ✓ | |
| `tool:read/execute` | ✓ | ✓ | ✓ | ✓ |
| `tool:create/update/delete` | ✓ | ✓ | ✓ | |
| `apikey:read` | ✓ | ✓ | ✓ | ✓ |
| `apikey:create/update/delete` | ✓ | ✓ | ✓ | |
| `conversation:read` | ✓ | ✓ | ✓ | ✓ |
| `conversation:delete` | ✓ | ✓ | ✓ | |

---

## 3. Data Isolation Rules

### 3.1 Core Concepts

- **Super Admin**: No data isolation, can access all system data
- **Admin**: Team-level isolation, can access all data of their teams
- **Member/Viewer**: Team-level isolation + user-level isolation (for conversation data)

### 3.2 Impact of `dashboard:access` Permission

`dashboard:access` is the key permission distinguishing "admin view" from "user view":

| Data Type | With `dashboard:access` | Without `dashboard:access` |
|-----------|------------------------|---------------------------|
| User list | Visible (requires `user:read`) | Not visible |
| Role list | Visible (requires `role:read`) | Not visible |
| Model list | Visible (requires `model:read`) | Not visible |
| Audit logs | Visible (requires `audit:read`) | Not visible |
| Site settings | Visible (requires `settings:read`) | Not visible |
| **Conversation list** | **All users' conversations in team** | **Only own conversations** |
| **Conversation stats** | **Stats for all team conversations** | **Stats for own conversations only** |

### 3.3 Special Isolation for Conversation Data

Conversation data has finer-grained isolation:

```
Super Admin
└── Can view all conversations

Admin (has dashboard:access)
└── Can view all users' conversations in their teams
    └── All conversations in Team A
    └── All conversations in Team B (if member)

Member / Viewer (no dashboard:access)
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

**User Role**: Member (no `dashboard:access`)

**Visible Data**:
- ✓ Own created conversations
- ✓ Own conversation statistics
- ✗ Other team members' conversations
- ✗ Dashboard management menu

### 4.2 Scenario: Admin Viewing Activity Logs

**User Role**: Admin (has `dashboard:access`)

**Visible Data**:
- ✓ All users' conversations in team
- ✓ Team-level conversation statistics
- ✓ Dashboard management menu
- ✗ Other teams' conversations

### 4.3 Scenario: Read-Only User

**User Role**: Viewer

**Allowed Operations**:
- ✓ View team resources (Agent, Workflow, Knowledge Base, etc.)
- ✓ Chat with Agent (`agent:chat`)
- ✓ Run workflows (`workflow:run`)
- ✓ Execute tools (`tool:execute`)
- ✗ Create/modify/delete any resources
- ✗ Access dashboard management

### 4.4 Scenario: Site Settings Management

| Role | `settings:read` | `settings:update` | Allowed Operations |
|------|:---------------:|:-----------------:|-------------------|
| Super Admin | ✓ | ✓ | View and modify all settings |
| Admin | ✓ | ✗ | View settings only |
| Member | ✗ | ✗ | No access |

---

## 5. Frontend Menu Visibility

### 5.1 Sidebar Menu Permission Mapping

| Menu Item | Required Permission | Super Admin | Admin | Member | Viewer |
|-----------|---------------------|:-----------:|:-----:|:------:|:------:|
| Dashboard | `dashboard:access` | ✓ | ✓ | | |
| Teams | `team:read` | ✓ | ✓ | ✓ | ✓ |
| Knowledge Bases | `kb:read` | ✓ | ✓ | ✓ | ✓ |
| Activities | `conversation:read` | ✓ | ✓ | ✓ | ✓ |
| Users | `user:read` | ✓ | ✓ | | |
| Roles | `role:read` | ✓ | ✓ | | |
| Permissions | `permission:read` | ✓ | ✓ | | |
| API Keys | `apikey:read` | ✓ | ✓ | ✓ | ✓ |
| Models | `model:read` | ✓ | ✓ | | |
| Tools | `tool:read` | ✓ | ✓ | ✓ | ✓ |
| Notifications | `dashboard:access` | ✓ | ✓ | | |
| Audit Logs | `audit:read` | ✓ | ✓ | | |
| Site Settings | `settings:read` | ✓ | ✓ | | |

### 5.2 Management Menu Group Visibility

The "Management" menu group (including Users, Roles, Permissions, Models, Audit Logs, etc.) is only visible when the user has `dashboard:access` permission.

---

## 6. API Permission Checks

### 6.1 Permission Check Methods

```python
# Method 1: Single permission check
current_user: User = Depends(PermissionChecker("user:read"))

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
            if perm.code == "dashboard:access" or perm.code == "*":
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
| Department Manager | Admin | Responsible for department user and resource management |
| Developer | Member | Create and manage Agents, workflows, etc. |
| Business User | Viewer | Use Agents and workflows, no creation needed |

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
- Avoid assigning `dashboard:access` permission to regular users
- `settings:update` permission should be limited to system administrators only
