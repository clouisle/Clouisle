# Permission Management

This guide covers how to manage permissions and access control as an administrator.

## Overview

As an administrator, you can:

- **Manage roles**: Create and configure custom roles
- **Assign permissions**: Control access to features and resources
- **Set team permissions**: Configure team-level access control
- **Manage API scopes**: Control API access permissions
- **Audit access**: Monitor permission changes and usage
- **Troubleshoot**: Debug permission issues

## Permission Model

### Permission Hierarchy

```
System Level (Admin)
  ├── Global Settings
  ├── User Management
  ├── Team Management
  └── System Configuration

Team Level (Owner, Admin, Member, Viewer)
  ├── Team Settings
  ├── Member Management
  ├── Resource Management
  └── Resource Access

Resource Level (Owner, Editor, Viewer)
  ├── Agents
  ├── Workflows
  ├── Knowledge Bases
  └── Conversations
```

### Permission Types

**System Permissions:**
- `system:admin` - Full system access
- `system:settings` - Manage system settings
- `system:users` - Manage all users
- `system:teams` - Manage all teams
- `system:audit` - View audit logs

**Team Permissions:**
- `team:manage` - Manage team settings
- `team:members` - Manage team members
- `team:resources` - Manage team resources
- `team:view` - View team information

**Resource Permissions:**
- `agent:create` - Create agents
- `agent:read` - View agents
- `agent:update` - Update agents
- `agent:delete` - Delete agents
- `agent:chat` - Chat with agents
- `agent:publish` - Publish agents

**Similar patterns for:**
- `workflow:*`
- `kb:*` (knowledge bases)
- `model:*`
- `tool:*`
- `api_key:*`

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

**Admin:**
```yaml
Name: Admin
Type: System
Description: Full system access
Permissions:
  - system:*
  - team:*
  - agent:*
  - workflow:*
  - kb:*
  - model:*
  - tool:*
  - user:*
  - api_key:*
```

**User:**
```yaml
Name: User
Type: System
Description: Standard user access
Permissions:
  - team:view
  - agent:read
  - agent:chat
  - workflow:read
  - workflow:execute
  - kb:read
  - kb:search
  - api_key:create
  - api_key:read
  - api_key:update
  - api_key:delete
```

### Team Roles

**Owner:**
```yaml
Name: Owner
Type: Team
Description: Team owner with full control
Permissions:
  - team:manage
  - team:members
  - team:delete
  - agent:*
  - workflow:*
  - kb:*
```

**Admin:**
```yaml
Name: Admin
Type: Team
Description: Team administrator
Permissions:
  - team:manage
  - team:members
  - agent:*
  - workflow:*
  - kb:*
```

**Member:**
```yaml
Name: Member
Type: Team
Description: Team member with standard access
Permissions:
  - team:view
  - agent:create
  - agent:read
  - agent:update
  - agent:chat
  - workflow:create
  - workflow:read
  - workflow:update
  - workflow:execute
  - kb:create
  - kb:read
  - kb:update
  - kb:search
```

**Viewer:**
```yaml
Name: Viewer
Type: Team
Description: Read-only team access
Permissions:
  - team:view
  - agent:read
  - agent:chat
  - workflow:read
  - kb:read
  - kb:search
```

### Create Custom Role

1. Navigate to **Admin** → **Permissions** → **Roles**
2. Click **Create Role**
3. Fill in role details:
   - **Name**: Role name
   - **Type**: System or Team
   - **Description**: Role description
   - **Color**: Role color (for UI)

4. Select permissions:
   - Browse permission categories
   - Check permissions to include
   - Use "Select All" for categories

5. Review permissions
6. Click **Create Role**

**Custom Role Example:**
```yaml
Name: Content Manager
Type: Team
Description: Manages knowledge bases and documents
Color: #10B981

Permissions:
  - team:view
  - kb:create
  - kb:read
  - kb:update
  - kb:delete
  - kb:search
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

**Note:** Cannot edit system roles (Admin, User).

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
3. Click **Permissions** tab
4. View:
   - System role
   - Team memberships and roles
   - Effective permissions
   - Permission sources

**User Permission View:**
```yaml
User: john.doe@example.com
System Role: User

Team Memberships:
  Support Team:
    Role: Admin
    Permissions: team:*, agent:*, workflow:*, kb:*

  Sales Team:
    Role: Member
    Permissions: team:view, agent:*, workflow:*, kb:*

Effective Permissions:
  - system:login
  - team:view (all teams)
  - team:manage (Support Team)
  - agent:* (Support Team, Sales Team)
  - workflow:* (Support Team, Sales Team)
  - kb:* (Support Team, Sales Team)
```

### Change User System Role

1. Navigate to **Admin** → **Users**
2. Select user
3. Click **Edit**
4. Change **System Role**:
   - Admin
   - User
5. Save changes

**Warning:** Changing to Admin grants full system access.

### Grant Special Permissions

For specific use cases, grant individual permissions:

1. Navigate to user permissions
2. Click **Grant Permission**
3. Select permission
4. Set scope (global or specific team)
5. Set expiration (optional)
6. Add reason/note
7. Save permission

**Special Permission Example:**
```yaml
User: jane.smith@example.com
Permission: model:manage
Scope: Global
Granted By: admin@example.com
Granted At: 2026-02-11 15:00:00
Expires: 2026-03-11 15:00:00
Reason: Temporary access for model configuration
```

### Revoke Permissions

1. Navigate to user permissions
2. Find permission to revoke
3. Click **Revoke**
4. Add reason
5. Confirm revocation

## Team Permissions

### View Team Permissions

1. Navigate to **Admin** → **Teams**
2. Select team
3. Click **Permissions** tab
4. View:
   - Team roles
   - Member permissions
   - Resource access
   - Permission inheritance

### Configure Team Roles

1. Select team
2. Go to **Permissions** → **Roles**
3. View available roles:
   - Owner
   - Admin
   - Member
   - Viewer
   - Custom roles

4. Click **Configure Role**
5. Modify role permissions for this team
6. Save changes

**Team-Specific Role Configuration:**
```yaml
Team: Support Team
Role: Member

Default Permissions:
  - agent:create
  - agent:read
  - agent:update
  - agent:chat

Team Override:
  + agent:delete (added)
  + agent:publish (added)
  - agent:create (removed)

Effective Permissions:
  - agent:read
  - agent:update
  - agent:delete
  - agent:chat
  - agent:publish
```

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

Share resources with other teams:

1. Select resource (agent, workflow, KB)
2. Click **Share**
3. Select teams to share with
4. Set permissions:
   - View only
   - View and use
   - View, use, and edit
5. Save sharing settings

**Shared Resource Example:**
```yaml
Agent: General FAQ Agent
Owner Team: Support Team
Shared With:
  Sales Team:
    Permission: View and use
    Can chat: Yes
    Can edit: No

  Engineering Team:
    Permission: View only
    Can chat: No
    Can edit: No
```

## API Scope Management

### API Scopes

**Available Scopes:**
```yaml
Agent Scopes:
  - agent:read
  - agent:create
  - agent:update
  - agent:delete
  - agent:chat
  - agent:publish

Workflow Scopes:
  - workflow:read
  - workflow:create
  - workflow:update
  - workflow:delete
  - workflow:execute

Knowledge Base Scopes:
  - kb:read
  - kb:create
  - kb:update
  - kb:delete
  - kb:search

Team Scopes:
  - team:read
  - team:manage

User Scopes:
  - user:read
  - user:update

Model Scopes:
  - model:read
  - model:manage

Tool Scopes:
  - tool:read
  - tool:use
```

### Configure API Key Scopes

1. Navigate to **Admin** → **API Keys**
2. Select API key
3. Click **Edit Scopes**
4. Select scopes:
   - Check scopes to grant
   - Uncheck to revoke
5. Save changes

**API Key Scope Example:**
```yaml
API Key: ak_...
Owner: integration@example.com
Scopes:
  - agent:read
  - agent:chat
  - workflow:read
  - workflow:execute
  - kb:read
  - kb:search

Restrictions:
  - Cannot create/update/delete resources
  - Cannot manage teams
  - Cannot access admin functions
```

### Scope Validation

API requests are validated against scopes:

```python
# Request with insufficient scope
GET /api/v1/agents
Authorization: Bearer ak_...
Scopes: workflow:read

# Response
{
  "code": 3000,
  "msg": "Insufficient permissions. Required scope: agent:read"
}
```

## Permission Auditing

### View Permission Changes

1. Navigate to **Admin** → **Permissions** → **Audit**
2. View permission change log:
   - User
   - Action (granted, revoked, modified)
   - Permission
   - Scope
   - Timestamp
   - Changed by

3. Filter by:
   - User
   - Action
   - Permission type
   - Date range

**Permission Audit Log:**
```yaml
2026-02-11 15:30:00
  User: john.doe@example.com
  Action: Granted
  Permission: model:manage
  Scope: Global
  Changed By: admin@example.com
  Reason: Temporary access for model configuration

2026-02-11 14:20:00
  User: jane.smith@example.com
  Action: Role Changed
  From: Member
  To: Admin
  Team: Support Team
  Changed By: owner@example.com

2026-02-11 10:15:00
  User: bob.wilson@example.com
  Action: Revoked
  Permission: agent:delete
  Scope: Sales Team
  Changed By: admin@example.com
  Reason: Security policy update
```

### Permission Usage Reports

**Generate Report:**
1. Navigate to **Admin** → **Permissions** → **Reports**
2. Select report type:
   - Permission usage by user
   - Permission usage by team
   - Unused permissions
   - Over-privileged users
3. Configure parameters
4. Generate report
5. Export (CSV, PDF)

**Permission Usage Report Example:**
```yaml
Report: Permission Usage by User
Period: 2026-02-01 to 2026-02-11

john.doe@example.com:
  Permissions: 45
  Used: 32 (71%)
  Unused: 13 (29%)
  Most Used:
    - agent:chat (1,234 times)
    - kb:search (567 times)
    - workflow:execute (234 times)

jane.smith@example.com:
  Permissions: 38
  Used: 38 (100%)
  Unused: 0 (0%)
  Most Used:
    - agent:update (456 times)
    - kb:update (345 times)
    - team:manage (123 times)
```

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
   ```bash
   Admin → Permissions → Reports
   Generate "Over-privileged Users" report
   ```

2. **Apply least privilege:**
   - Remove unused permissions
   - Downgrade roles if appropriate
   - Use custom roles for specific needs

3. **Regular audits:**
   - Schedule quarterly permission reviews
   - Remove temporary permissions
   - Update roles based on job changes

### Permission Conflicts

**Symptoms:**
- Unexpected permission behavior
- Inconsistent access

**Solutions:**

1. **Check permission hierarchy:**
   - System permissions override team permissions
   - Team permissions override resource permissions
   - Explicit denies override allows

2. **Review permission sources:**
   ```bash
   Admin → Users → Select user
   Permissions → View permission sources
   ```

3. **Resolve conflicts:**
   - Remove conflicting permissions
   - Use more specific scopes
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

**Check User Permissions:**
```python
# Get user permissions
permissions = api.get(f"/api/v1/users/{user_id}/permissions")

# Check specific permission
has_permission = api.get(
    f"/api/v1/users/{user_id}/permissions/check",
    params={"permission": "agent:create", "team_id": "team-123"}
)
```

**Grant Permission:**
```python
# Grant permission to user
api.post(f"/api/v1/users/{user_id}/permissions", json={
    "permission": "model:manage",
    "scope": "global",
    "expires_at": "2026-03-11T15:00:00Z",
    "reason": "Temporary access for model configuration"
})
```

**Revoke Permission:**
```python
# Revoke permission
api.delete(
    f"/api/v1/users/{user_id}/permissions/{permission_id}",
    json={"reason": "No longer needed"}
)
```

## Related Documentation

- [Team Roles](../../user-guide/teams/team-roles.md) - User guide to roles
- [API Key Scopes](../../user-guide/api-keys/api-key-scopes.md) - API scope reference
- [Security Best Practices](../../best-practices/security.md) - Security guide
- [Audit Logs](../audit-logs/audit-log-management.md) - Audit log management

---

**Last Updated**: 2026-02-11
