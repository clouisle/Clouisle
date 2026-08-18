# Permission Management

This guide covers how to manage permissions and access control as an administrator.

## Overview

As an administrator, you can:

- **Manage roles**: Create and configure custom roles
- **Assign permissions**: Control which permissions each role has
- **Set team permissions**: Configure team-level roles and memberships
- **Manage API scopes**: Control API key access permissions
- **Audit access**: Review role and permission assignments
- **Troubleshoot**: Debug permission issues

## Permission Model

### Permission Hierarchy

```
System level (Super Admin/Admin dashboard APIs)
  ├── Global settings (`admin:settings:*`)
  ├── User management (`admin:user:*`)
  ├── Role and permission management (`admin:role:*`, `admin:permission:*`)
  ├── Team management (`admin:team:*`)
  ├── Model management (`admin:model:*`)
  ├── App management (`admin:app:*`)
  ├── Capability management (`admin:capability:*`)
  ├── Knowledge-base management (`admin:knowledge-base:*`)
  ├── SSO management (`admin:sso:*`)
  └── Audit logs (`audit:read`, `audit:export`)

Team-scoped platform APIs
  ├── Team permissions (`team:read/create/update/delete/manage`)
  └── Resource permissions (`agent:*`, `workflow:*`, `kb:*`, `tool:*`, `skill:*`)
```

Dashboard permissions authorize system-wide admin APIs for Super Admin/Admin users; team-scoped permissions authorize platform resource APIs only within the user's teams. Team member roles map to scoped permissions as `admin → Admin`, `member → Member`, and `viewer → Viewer`; `Owner` is a team ownership concept, not an additional selectable member role in this permission matrix.

### Permission Types

**Dashboard / Admin Permissions (require `admin:dashboard:access`):**
- `admin:user:*` - Manage users
- `admin:role:*` - Manage roles
- `admin:permission:*` - Manage permissions
- `admin:model:*` - Manage models
- `admin:team:*` - Manage teams system-wide
- `admin:app:*` - Manage agents and workflows across teams
- `admin:capability:*` - Manage tools and skills across teams
- `admin:knowledge-base:*` - Manage knowledge bases from admin
- `admin:settings:read/update` - View/modify site settings
- `admin:sso:read/update` - View/manage SSO
- `admin:conversation:*` - Manage conversations
- `admin:memory:*` - Manage memory records
- `admin:notification:*` - Manage notifications
- `audit:read` / `audit:export` - View/export audit logs

**Team / Resource Permissions (team-isolated):**
- `team:read/create/update/delete/manage` - Team management
- `agent:read/create/update/delete/publish/chat` - Agent management
- `workflow:read/create/update/delete/publish/run/execute` - Workflow management
- `kb:read/test/create/update/delete` - Knowledge base management
- `tool:read/create/update/delete/execute` - Tool management
- `skill:read/create/update/delete/execute` - Skill management
- `apikey:read/create/update/delete` - API Key management
- `conversation:read/delete` - Conversation management

In the admin dashboard, tools and skills are reached through **Capabilities** (`/capabilities`), not a separate Tools navigation item.

## Accessing Permission Management

### Admin Dashboard

1. Log in as administrator
2. Navigate to **Admin** → **Permissions**
3. View permission management interface

### Permission Views

- **Roles**: Predefined and custom roles
- **Users**: User permissions and roles
- **Teams**: Team permissions
- **API Scopes**: API access permissions
- **Audit**: Permission change history

## Role Management

### System Roles

**Super Admin:**
```yaml
Name: Super Admin
Type: System
Description: Full system access
Permissions:
  - "*" (all permissions)
```

**Admin:**
```yaml
Name: Admin
Type: System
Description: Dashboard access, system read visibility, and team-scoped resource management
Permissions:
  - admin:dashboard:access
  - admin:user:read/create/update/delete
  - admin:role:read
  - admin:permission:read
  - admin:team:read/create/update/delete
  - admin:model:read/create/update/delete
  - admin:app:read/create/update/delete/publish/duplicate
  - admin:capability:read/create/update/delete/execute
  - admin:knowledge-base:read/test/create/update/delete
  - admin:settings:read
  - admin:sso:read
  - admin:conversation:read/delete
  - admin:notification:create/delete
  - admin:memory:read
  - audit:read
  - audit:export
  # Team-scoped permissions use explicit codes; there is no wildcard permission code.
```

**Member:**
```yaml
Name: Member
Type: System
Description: Collaborative member role without dashboard access
Permissions:
  - team:read
  - agent:read/create/update/chat
  - workflow:read/create/update/run
  - kb:read/test/create/update/delete
  - tool:read/create/update/delete/execute
  - skill:read/create/update/delete/execute
  - apikey:read/create/update/delete
  - conversation:read/delete
```

**Viewer:**
```yaml
Name: Viewer
Type: System
Description: Default read-only role with execute permissions
Permissions:
  - team:read
  - agent:read
  - agent:chat
  - workflow:read
  - workflow:run
  - kb:read
  - kb:test
  - tool:read
  - tool:execute
  - skill:read
  - skill:execute
  - conversation:read
```

### Team-scoped roles and permissions

Team membership roles are relationship roles, not wildcard permission sets. The fixed roles are `owner`, `admin`, `member`, and `viewer`; startup migration maps `owner` and `admin` to the scoped **Admin** role, `member` to **Member**, and `viewer` to **Viewer**.

The platform permission codes are explicit values such as:

| Area | Codes |
|------|-------|
| Teams | `team:read`, `team:create`, `team:update`, `team:delete`, `team:manage` |
| Agents | `agent:read`, `agent:create`, `agent:update`, `agent:delete`, `agent:publish`, `agent:chat` |
| Workflows | `workflow:read`, `workflow:create`, `workflow:update`, `workflow:delete`, `workflow:publish`, `workflow:run` |
| Knowledge bases | `kb:read`, `kb:create`, `kb:update`, `kb:delete`, `kb:test` |

Use `team:update`/`team:delete` for team mutations and `team:manage` for member management. There are no `team:view` or `team:members` permission codes and platform permissions are not expressed as `team:*` wildcards in the permission registry.

Global dashboard permissions use the separate `admin:*` namespace; a team-scoped role does not grant dashboard access.

### Create Custom Role

1. Navigate to **Admin** → **Permissions** → **Roles**
2. Click **Create Role**
3. Fill in role details:
   - **Name**: Role name
   - **Description**: Role description

4. Select permissions:
   - Browse permission categories
   - Check permissions to include
   - Use "Select All" for categories

5. Review permissions
6. Click **Create Role**

Custom roles are global roles (`is_system_role = false`). Permissions can be replaced later via `PUT /api/v1/admin/roles/{role_id}/permissions`.

**Custom Role Example:**
```yaml
Name: Content Manager
Description: Manages knowledge bases and documents

Permissions:
  - team:read
  - kb:create
  - kb:read
  - kb:update
  - kb:delete
  - kb:test
  - agent:read
  - agent:chat
```

### Edit Role

1. Navigate to **Roles**
2. Select role
3. Click **Edit**
4. Modify:
   - Role name
   - Description
   - Permissions
5. Save changes

**Note:** System roles (Super Admin, Admin, Member, Viewer) cannot be modified or deleted. Custom roles are edited via `PUT /api/v1/admin/roles/{role_id}` and `PUT /api/v1/admin/roles/{role_id}/permissions` (replaces the full permission set).

### Delete Role

1. Navigate to **Roles**
2. Select custom role
3. Click **Delete**
4. Choose action for users with this role:
   - Assign to different role
   - Remove role (keep user)
5. Confirm deletion

## User Permissions

### View User Permissions

1. Navigate to **Admin** → **Users**
2. Select user
3. View the user's global roles and team memberships
4. View:
   - Global roles
   - Team memberships and team roles
   - Effective permissions (derived from the user's global roles plus team-scoped role assignments)

**User Permission View:**
```yaml
User: john.doe@example.com
Global Roles: Member

Team Memberships:
  Support Team:
    Role: Admin
  Sales Team:
    Role: Member
```

### Change User System Role

1. Navigate to **Admin** → **Users**
2. Select user
3. Click **Edit**
4. Change the user's global role:
   - Super Admin
   - Admin
   - Member
   - Viewer
5. Save changes

**Warning:** Assigning Admin grants dashboard access and system read permissions; Super Admin grants full system access.

### Grant Special Permissions

> **Note:** Not implemented / Roadmap. There is no per-user permission grant/revoke with scope and expiry. The endpoints `GET /users/{user_id}/permissions`, `/permissions/check`, and `POST/DELETE /users/{user_id}/permissions` do not exist. Permissions are assigned through global roles (`PUT /api/v1/admin/roles/{role_id}/permissions`) and team memberships.

## Team Permissions

### View Team Permissions

1. Navigate to **Teams**
2. Select team
3. View members and their team roles

### Configure Team Roles

Team membership is mirrored into team-scoped role assignments:

| Team role | Scoped role in that team |
|-----------|--------------------------|
| Owner | Admin |
| Admin | Admin |
| Member | Member |
| Viewer | Viewer |

> **Note:** Team roles are the fixed set Owner / Admin / Member / Viewer. There is no per-team permission override (adding/removing individual permissions for a team). Custom global roles can be created and assigned as a user's global role, but team-scoped access uses the mirrored role assignments above.

### Resource Permissions

**Agent Permissions:**
```yaml
Agent: Customer Support Agent
Owner: john.doe@example.com
Team: Support Team

Access Control:
  Owner: Full access
  Team Admins: Full access
  Team Members: Read, Chat
  Team Viewers: Read, Chat
  Other Teams: No access
```

**Workflow Permissions:**
```yaml
Workflow: Customer Inquiry Processing
Owner: jane.smith@example.com
Team: Support Team

Access Control:
  Owner: Full access
  Team Admins: Full access
  Team Members: Read, Execute
  Team Viewers: Read
  Other Teams: No access
```

### Share Resources

Cross-team sharing is limited:

- **Tools**: Custom tools can be shared with other teams via `POST /api/v1/admin/tools/{tool_id}/share` (and listed/unshared with `GET /{tool_id}/shares` / `DELETE /{tool_id}/share/{team_id}`).
- **Agents / Workflows / Knowledge Bases**: There is no per-resource share with per-team permission levels. Cross-team visibility is controlled by the resource's `visibility` (Team / Public for agents), and access is otherwise team-isolated.

## API Scope Management

### API Scopes

API keys carry a `scopes` list (default `["chat"]`; empty means full access), a `rate_limit` (requests per minute, 0 = unlimited), an `expires_at` date, and can be associated with specific agents and workflows. API keys are managed in **API Keys** (`/api-keys`) and via `POST /api/v1/api-keys`.

### Configure API Key Scopes

1. Navigate to **API Keys**
2. Select API key
3. Edit scopes and associations
4. Save changes

**API Key Scope Example:**
```yaml
API Key: ak_...
Owner: integration@example.com
Scopes:
  - chat

Rate Limit: 1000 (requests/minute)
Expires At: 2027-02-11
Associated Agents: 2
Associated Workflows: 1
```

## Permission Auditing

### View Permission Changes

> **Note:** Not implemented / Roadmap. There is no dedicated permission-change audit view, and the audit log has no `granted` / `revoked` actions. Role changes and team membership changes do produce audit log entries (e.g. `update_user`, `add_team_member`, `update_team_member`, `create_role`, `update_role`), which can be reviewed in **Audit Logs**.

### Permission Usage Reports

> **Note:** Not implemented / Roadmap. Permission usage reports (usage by user/team, unused permissions, over-privileged users) do not exist.

## Troubleshooting

### Permission Denied Errors

**Symptoms:**
- User cannot access feature
- "Permission denied" error
- 403 Forbidden response

**Solutions:**

1. **Check user permissions:**
   ```bash
   Admin → Users → Select user
   Permissions → View effective permissions
   ```

2. **Check team membership:**
   - Verify user is in correct team
   - Check team role
   - Verify team has access to resource

3. **Check resource permissions:**
   - Verify resource is shared with team
   - Check resource access level
   - Verify resource is not private

4. **Check API key scopes:**
   - Verify API key has required scopes
   - Check scope restrictions
   - Regenerate key if needed

### Over-Privileged Users

**Symptoms:**
- Users have unnecessary permissions
- Security audit findings

**Solutions:**

1. **Review user permissions:**
   - Review the user's global roles and team memberships in **Users**
   - Cross-check against the role permission matrix

2. **Apply least privilege:**
   - Remove unused permissions from roles
   - Downgrade roles if appropriate
   - Use custom roles for specific needs

3. **Regular audits:**
   - Schedule quarterly permission reviews
   - Update roles based on job changes

### Permission Conflicts

**Symptoms:**
- Unexpected permission behavior
- Inconsistent access

**Solutions:**

1. **Check permission hierarchy:**
   - Global roles provide permission codes
   - Team-scoped roles apply only inside the target team
   - `admin:*` permissions cannot be satisfied by team-scoped assignments

2. **Review role assignments:**
   - View the user's global roles and team memberships
   - Check the role permission sets in **Roles**

3. **Resolve conflicts:**
   - Adjust role permission sets
   - Use more specific roles
   - Document permission decisions

## Best Practices

### Permission Management

**✅ Do:**
- Follow principle of least privilege
- Use roles instead of individual permissions
- Document permission decisions
- Review permissions regularly
- Audit permission changes
- Use temporary permissions when appropriate
- Test permission changes in staging

**❌ Don't:**
- Grant admin access unnecessarily
- Use overly broad permissions
- Skip documentation
- Forget to review
- Ignore audit logs
- Make permanent what should be temporary
- Change permissions in production without testing

### Role Design

**✅ Do:**
- Create roles based on job functions
- Use descriptive role names
- Document role purposes
- Keep roles simple and focused
- Review roles regularly
- Version role changes

**❌ Don't:**
- Create too many roles
- Use vague role names
- Skip documentation
- Make roles too complex
- Forget to review
- Change roles without versioning

### Security

**✅ Do:**
- Enforce strong authentication
- Use 2FA for privileged accounts
- Rotate API keys regularly
- Monitor permission usage
- Audit permission changes
- Restrict admin access
- Use IP whitelisting for sensitive operations

**❌ Don't:**
- Allow weak passwords
- Skip 2FA for admins
- Use static API keys forever
- Ignore usage patterns
- Skip audit logs
- Grant admin access freely
- Allow unrestricted access

## API Access

### Manage Permissions via API

Admin role and permission endpoints live under `/api/v1/admin/roles` and `/api/v1/admin/permissions` and require `admin:role:*` / `admin:permission:*` permissions.

**Role Operations:**
```python
# List roles
roles = api.get("/api/v1/admin/roles")

# Create role
role = api.post("/api/v1/admin/roles", json={
    "name": "Content Manager",
    "description": "Manages knowledge bases",
    "permissions": ["team:read", "kb:read", "kb:create", "kb:update", "kb:delete", "kb:test"]
})

# Replace a role's permissions (PUT, not PATCH)
api.put(f"/api/v1/admin/roles/{role_id}/permissions", json={
    "permissions": ["kb:read", "kb:create"]
})
```

**Permission Operations:**
```python
# List permissions (optionally filtered by scope)
permissions = api.get("/api/v1/admin/permissions", params={"scope": ["admin", "team"]})

# List permission scopes
scopes = api.get("/api/v1/admin/permissions/scopes")
```

> **Note:** There are no per-user permission endpoints (`/users/{user_id}/permissions`).

## Related Documentation

- [Team Roles](../../user-guide/teams/team-roles.md) - User guide to roles
- [API Key Scopes](../../user-guide/api-keys/api-key-scopes.md) - API scope reference
- [Security Checklist](../../operations/security-checklist.md) - Security guidance
- [Audit Logs](../audit-logs/audit-log-management.md) - Audit log management

---

**Last Updated**: 2026-02-11
