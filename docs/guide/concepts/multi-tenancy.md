# Multi-Tenancy Model

Clouisle implements a team-based multi-tenancy model that provides secure data isolation while enabling flexible collaboration. This document explains how multi-tenancy works in Clouisle and its implications for data access and security.

## Overview

Multi-tenancy in Clouisle is built around the concept of **Teams**. Every resource (agents, workflows, knowledge bases, etc.) belongs to a team, and users can be members of multiple teams with different roles.

## Core Concepts

### Teams

A **Team** is the primary unit of data isolation in Clouisle. Think of a team as a workspace or organization within the platform.

**Key characteristics**:
- Every resource must belong to exactly one team
- Users can be members of multiple teams
- Each team has its own set of resources
- Teams are completely isolated from each other (except for super admins)

**Example**:
```
Company XYZ
├── Engineering Team
│   ├── Members: Alice (Owner), Bob (Admin), Carol (Member)
│   ├── Agents: Code Review Bot, Documentation Assistant
│   └── Knowledge Bases: Engineering Docs, API References
│
└── Marketing Team
    ├── Members: Alice (Member), David (Owner), Eve (Member)
    ├── Agents: Content Generator, Social Media Bot
    └── Knowledge Bases: Marketing Materials, Brand Guidelines
```

In this example:
- Alice is a member of both teams (Owner in Engineering, Member in Marketing)
- Engineering Team cannot access Marketing Team's resources
- Each team has its own isolated set of agents and knowledge bases

### Team Roles

Each team member has a role that determines their permissions within that team:

| Role | Permissions | Use Case |
|------|-------------|----------|
| **Owner** | Full control, can delete team, transfer ownership | Team creator, primary administrator |
| **Admin** | Manage members, create/edit/delete resources | Team administrators |
| **Member** | Create and manage own resources, use team resources | Regular team members |
| **Viewer** | Read-only access to team resources | Observers, auditors |

**Role hierarchy**:
```
Owner > Admin > Member > Viewer
```

### Resource Ownership

Every resource in Clouisle has two ownership attributes:

1. **Team**: Which team the resource belongs to
2. **Creator**: Which user created the resource

**Example**:
```json
{
  "agent_id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Customer Support Bot",
  "team_id": "660e8400-e29b-41d4-a716-446655440001",
  "created_by": "770e8400-e29b-41d4-a716-446655440002",
  "visibility": "team"
}
```

## Data Isolation

### Team-Level Isolation

**How it works**:
1. When a user makes a request, the system identifies which teams they belong to
2. Database queries automatically filter results to only include resources from those teams
3. Users cannot access resources from teams they're not members of

**Implementation**:
```python
# Automatic team filtering in queries
if user.is_superuser:
    # Super admins see everything
    agents = await Agent.all()
else:
    # Regular users only see their teams' resources
    user_team_ids = [membership.team_id for membership in user.team_memberships]
    agents = await Agent.filter(team_id__in=user_team_ids)
```

### User-Level Isolation

Some resources have additional user-level isolation:

**Conversations**:
- Regular users can only see their own conversations
- Admins (with `dashboard:access` permission) can see all conversations in their teams

**API Keys**:
- Users can only see and manage their own API keys
- Admins can see all API keys in their teams

### Super Admin Access

**Super Admins** bypass all isolation:
- Can access resources from any team
- Can view and manage all users
- Can access system-wide settings
- Used for platform administration and support

## Visibility Levels

Resources can have different visibility levels that control who can access them:

| Visibility | Description | Who Can Access |
|------------|-------------|----------------|
| **Private** | Only creator can access | Resource creator only |
| **Team** | Team members can access | All members of the resource's team |
| **Public** | Anyone can access | All users across all teams |

**Example use cases**:
- **Private**: Personal draft agents, experimental workflows
- **Team**: Production agents, shared knowledge bases
- **Public**: Template agents, public documentation

## Multi-Team Membership

Users can belong to multiple teams simultaneously, enabling cross-team collaboration.

### Benefits

**Flexibility**:
- Users can participate in multiple projects/departments
- Share expertise across teams
- Maintain separate contexts for different work

**Example scenario**:
```
Alice's Teams:
├── Engineering Team (Owner)
│   └── Can manage all engineering resources
├── Marketing Team (Member)
│   └── Can create content, use marketing agents
└── Executive Team (Viewer)
    └── Can view reports and dashboards
```

### Context Switching

When working with resources, users implicitly work within the context of a team:

**Creating a resource**:
```
POST /api/v1/agents
{
  "name": "New Agent",
  "team_id": "engineering-team-id",  // Explicitly specify team
  ...
}
```

**Listing resources**:
```
GET /api/v1/agents?team_id=engineering-team-id  // Filter by team
```

## Permission Model

Permissions in Clouisle work at two levels:

### 1. System-Level Permissions

Controlled by user roles (Super Admin, Admin, Member, Viewer):
- Determines access to dashboard features
- Controls user management capabilities
- Manages system settings

### 2. Team-Level Permissions

Controlled by team roles (Owner, Admin, Member, Viewer):
- Determines what users can do within a team
- Controls resource creation and management
- Manages team membership

**Permission check flow**:
```
1. Check if user has system-level permission (e.g., "agent:create")
2. Check if user is a member of the target team
3. Check if user's team role allows the operation
4. Check resource visibility settings
```

## Data Access Patterns

### Reading Resources

**List all agents I can access**:
```sql
SELECT * FROM agents
WHERE team_id IN (
  SELECT team_id FROM team_memberships
  WHERE user_id = current_user_id
)
OR visibility = 'public'
```

**Get specific agent**:
```sql
SELECT * FROM agents
WHERE id = agent_id
AND (
  team_id IN (SELECT team_id FROM team_memberships WHERE user_id = current_user_id)
  OR visibility = 'public'
)
```

### Creating Resources

**Create agent**:
1. User must be a member of the target team
2. User must have `agent:create` permission
3. User's team role must allow creation (Member or higher)
4. Agent is created with `team_id` set to the target team

### Updating Resources

**Update agent**:
1. User must be a member of the agent's team
2. User must have `agent:update` permission
3. User's team role must allow updates (Member or higher for own resources, Admin for others)

### Deleting Resources

**Delete agent**:
1. User must be a member of the agent's team
2. User must have `agent:delete` permission
3. User's team role must allow deletion (typically Admin or Owner)

## Security Considerations

### Preventing Data Leakage

**Team ID validation**:
- Always validate that the user is a member of the target team
- Never trust client-provided team IDs without verification
- Use server-side team membership checks

**Resource access checks**:
```python
async def check_team_access(user: User, team_id: str):
    if user.is_superuser:
        return True

    membership = await TeamMembership.filter(
        user_id=user.id,
        team_id=team_id
    ).first()

    if not membership:
        raise PermissionError("User is not a member of this team")

    return True
```

### Audit Logging

All team-related operations are logged:
- Team creation/deletion
- Member additions/removals
- Role changes
- Resource access across teams

### Rate Limiting

Rate limits are applied per-user, not per-team:
- Prevents abuse across multiple teams
- Ensures fair resource usage
- Protects against malicious actors

## Best Practices

### For Administrators

**Team Structure**:
- Create teams based on organizational structure (departments, projects)
- Use descriptive team names
- Document team purposes and membership criteria

**Role Assignment**:
- Follow principle of least privilege
- Assign Owner role sparingly (only 1-2 per team)
- Use Viewer role for read-only access needs
- Regular audit of team memberships

**Resource Organization**:
- Use consistent naming conventions
- Set appropriate visibility levels
- Document resource purposes
- Regular cleanup of unused resources

### For Developers

**API Usage**:
- Always specify `team_id` when creating resources
- Filter by `team_id` when listing resources
- Handle team membership errors gracefully
- Cache team membership checks when appropriate

**Testing**:
- Test with users in multiple teams
- Test with users in no teams
- Test cross-team access attempts
- Test role-based access controls

## Common Scenarios

### Scenario 1: User Joins New Team

**What happens**:
1. User receives invitation or is added by admin
2. User accepts invitation (if required)
3. User gains access to all team resources based on their role
4. User can now create resources in the new team

### Scenario 2: User Leaves Team

**What happens**:
1. User's team membership is removed
2. User loses access to all team resources
3. Resources created by the user remain in the team
4. User's conversations and API keys remain accessible to team admins

### Scenario 3: Team is Deleted

**What happens**:
1. All team resources are deleted (agents, workflows, knowledge bases)
2. All team memberships are removed
3. Audit logs are retained for compliance
4. Operation is irreversible (requires confirmation)

### Scenario 4: Resource Visibility Change

**Private → Team**:
- Resource becomes accessible to all team members
- Useful when moving from draft to production

**Team → Public**:
- Resource becomes accessible to all users
- Useful for sharing templates or examples
- Cannot be reversed if resource is used by other teams

**Public → Team**:
- Resource becomes restricted to team members
- Only possible if no other teams are using it

## Related Documentation

- [Permissions System](../admin-guide/permissions/PERMISSIONS.md) - Detailed permission model
- [Team Management](../admin-guide/teams/team-management.md) - Managing teams
- [User Management](../admin-guide/users/user-management.md) - Managing users
- [Security Checklist](../operations/security-checklist.md) - Security best practices
