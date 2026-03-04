# Teams API

This document describes the API endpoints for team management.

## Overview

The Teams API allows you to:

- **List teams**: Get all accessible teams
- **Get team details**: Retrieve team information
- **Create teams**: Create new teams (admin only)
- **Update teams**: Modify team settings (admin only)
- **Delete teams**: Remove teams (admin only)
- **Manage members**: Add, remove, and update team members

**Base URL**: `/api/v1/teams`

## Authentication

All endpoints require authentication via JWT token or API key.

**Required scopes:**
- `team:read` - View team information
- `team:manage` - Manage teams (admin only)

## List Teams

Get a list of all teams you have access to.

### Endpoint

```
GET /api/v1/teams
```

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `page` | integer | No | 1 | Page number |
| `page_size` | integer | No | 20 | Items per page (max: 100) |
| `search` | string | No | - | Search by name |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/teams?page=1&page_size=20" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "team-123",
        "name": "Marketing Team",
        "description": "Marketing and content creation team",
        "member_count": 12,
        "owner": {
          "id": "user-456",
          "name": "Alice Johnson",
          "email": "alice@example.com"
        },
        "your_role": "member",
        "created_at": "2026-01-15T10:00:00Z",
        "updated_at": "2026-02-11T15:30:00Z"
      }
    ],
    "total": 5,
    "page": 1,
    "page_size": 20,
    "total_pages": 1
  },
  "msg": "success"
}
```

## Get Team

Get details of a specific team.

### Endpoint

```
GET /api/v1/teams/{team_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `team_id` | string | Yes | Team UUID |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/teams/team-123" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "team-123",
    "name": "Marketing Team",
    "description": "Marketing and content creation team",
    "member_count": 12,
    "owner": {
      "id": "user-456",
      "name": "Alice Johnson",
      "email": "alice@example.com"
    },
    "your_role": "member",
    "settings": {
      "allow_member_invites": true,
      "public_join_requests": false,
      "require_approval": true
    },
    "limits": {
      "max_agents": 100,
      "max_workflows": 50,
      "max_storage": 10737418240
    },
    "usage": {
      "agents": 23,
      "workflows": 15,
      "knowledge_bases": 8,
      "storage_used": 2469606195
    },
    "created_at": "2026-01-15T10:00:00Z",
    "updated_at": "2026-02-11T15:30:00Z"
  },
  "msg": "success"
}
```

## Create Team

Create a new team (admin only).

### Endpoint

```
POST /api/v1/teams
```

### Request Body

```json
{
  "name": "Sales Team",
  "description": "Sales and customer relations team",
  "owner_id": "user-789",
  "settings": {
    "allow_member_invites": true,
    "public_join_requests": false,
    "require_approval": true
  },
  "limits": {
    "max_agents": 100,
    "max_workflows": 50,
    "max_storage": 10737418240
  }
}
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Team name (max 100 chars) |
| `description` | string | No | Team description (max 500 chars) |
| `owner_id` | string | Yes | User ID of team owner |
| `settings` | object | No | Team settings |
| `limits` | object | No | Resource limits |

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/teams" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Sales Team",
    "description": "Sales and customer relations team",
    "owner_id": "user-789"
  }'
```

### Response

**Success (201 Created):**

```json
{
  "code": 0,
  "data": {
    "id": "team-456",
    "name": "Sales Team",
    "description": "Sales and customer relations team",
    "owner_id": "user-789",
    "created_at": "2026-02-11T16:00:00Z"
  },
  "msg": "Team created successfully"
}
```

## Update Team

Update team information.

### Endpoint

```
PATCH /api/v1/teams/{team_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `team_id` | string | Yes | Team UUID |

### Request Body

All fields are optional. Only include fields you want to update.

```json
{
  "name": "Updated Team Name",
  "description": "Updated description",
  "settings": {
    "allow_member_invites": false
  }
}
```

### Request Example

```bash
curl -X PATCH "https://your-domain.com/api/v1/teams/team-123" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Updated Team Name"
  }'
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "team-123",
    "name": "Updated Team Name",
    "updated_at": "2026-02-11T16:05:00Z"
  },
  "msg": "Team updated successfully"
}
```

## Delete Team

Delete a team permanently (admin only).

### Endpoint

```
DELETE /api/v1/teams/{team_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `team_id` | string | Yes | Team UUID |

### Request Example

```bash
curl -X DELETE "https://your-domain.com/api/v1/teams/team-123" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": null,
  "msg": "Team deleted successfully"
}
```

## List Team Members

Get all members of a team.

### Endpoint

```
GET /api/v1/teams/{team_id}/members
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `team_id` | string | Yes | Team UUID |

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `page` | integer | No | 1 | Page number |
| `page_size` | integer | No | 50 | Items per page (max: 100) |
| `role` | string | No | - | Filter by role: owner, admin, member, viewer |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/teams/team-123/members" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "user_id": "user-456",
        "email": "alice@example.com",
        "full_name": "Alice Johnson",
        "avatar_url": "https://example.com/avatars/alice.jpg",
        "role": "owner",
        "joined_at": "2026-01-15T10:00:00Z"
      },
      {
        "user_id": "user-789",
        "email": "bob@example.com",
        "full_name": "Bob Smith",
        "avatar_url": "https://example.com/avatars/bob.jpg",
        "role": "admin",
        "joined_at": "2026-01-16T10:00:00Z"
      }
    ],
    "total": 12,
    "page": 1,
    "page_size": 50,
    "total_pages": 1
  },
  "msg": "success"
}
```

## Add Team Member

Add a member to a team.

### Endpoint

```
POST /api/v1/teams/{team_id}/members
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `team_id` | string | Yes | Team UUID |

### Request Body

```json
{
  "user_id": "user-999",
  "role": "member"
}
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `user_id` | string | Yes | User UUID to add |
| `role` | string | No | Member role: admin, member, viewer (default: member) |

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/teams/team-123/members" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user-999",
    "role": "member"
  }'
```

### Response

**Success (201 Created):**

```json
{
  "code": 0,
  "data": {
    "user_id": "user-999",
    "team_id": "team-123",
    "role": "member",
    "joined_at": "2026-02-11T16:00:00Z"
  },
  "msg": "Member added successfully"
}
```

## Update Team Member

Update a team member's role.

### Endpoint

```
PATCH /api/v1/teams/{team_id}/members/{user_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `team_id` | string | Yes | Team UUID |
| `user_id` | string | Yes | User UUID |

### Request Body

```json
{
  "role": "admin"
}
```

### Request Example

```bash
curl -X PATCH "https://your-domain.com/api/v1/teams/team-123/members/user-999" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "role": "admin"
  }'
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "user_id": "user-999",
    "team_id": "team-123",
    "role": "admin",
    "updated_at": "2026-02-11T16:05:00Z"
  },
  "msg": "Member role updated successfully"
}
```

## Remove Team Member

Remove a member from a team.

### Endpoint

```
DELETE /api/v1/teams/{team_id}/members/{user_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `team_id` | string | Yes | Team UUID |
| `user_id` | string | Yes | User UUID |

### Request Example

```bash
curl -X DELETE "https://your-domain.com/api/v1/teams/team-123/members/user-999" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": null,
  "msg": "Member removed successfully"
}
```

## Get Team Statistics

Get usage statistics for a team.

### Endpoint

```
GET /api/v1/teams/{team_id}/stats
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `team_id` | string | Yes | Team UUID |

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `start_date` | string | No | 30 days ago | Start date (ISO 8601) |
| `end_date` | string | No | Now | End date (ISO 8601) |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/teams/team-123/stats" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "member_count": 12,
    "resource_usage": {
      "agents": 23,
      "workflows": 15,
      "knowledge_bases": 8,
      "storage_used": 2469606195,
      "storage_limit": 10737418240
    },
    "activity": {
      "total_conversations": 1234,
      "workflow_executions": 456,
      "documents_uploaded": 89,
      "api_calls": 12345
    },
    "daily_stats": [
      {
        "date": "2026-02-11",
        "conversations": 89,
        "workflow_executions": 34,
        "documents_uploaded": 5
      }
    ]
  },
  "msg": "success"
}
```

## Error Codes

| Code | Message | Description |
|------|---------|-------------|
| `4000` | Team not found | Team does not exist |
| `3000` | Permission denied | Insufficient permissions |
| `3001` | Not team member | User is not a team member |
| `1001` | Validation failed | Invalid request data |
| `5100` | Name already exists | Team name is taken |
| `5101` | Already team member | User is already a member |

## Rate Limits

| Endpoint | Limit |
|----------|-------|
| `GET /api/v1/teams` | 100/minute |
| `GET /api/v1/teams/{id}` | 100/minute |
| `POST /api/v1/teams` | 10/minute (admin) |
| `PATCH /api/v1/teams/{id}` | 30/minute |
| `DELETE /api/v1/teams/{id}` | 10/minute (admin) |
| `GET /api/v1/teams/{id}/members` | 100/minute |
| `POST /api/v1/teams/{id}/members` | 30/minute |

## Code Examples

### Python

```python
import requests

def list_teams(token):
    """List all accessible teams."""
    url = "https://your-domain.com/api/v1/teams"
    headers = {
        "Authorization": f"Bearer {token}"
    }

    response = requests.get(url, headers=headers)
    result = response.json()

    if result['code'] == 0:
        return result['data']['items']
    else:
        raise Exception(f"Error: {result['msg']}")

def add_team_member(token, team_id, user_id, role="member"):
    """Add a member to a team."""
    url = f"https://your-domain.com/api/v1/teams/{team_id}/members"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    data = {
        "user_id": user_id,
        "role": role
    }

    response = requests.post(url, headers=headers, json=data)
    result = response.json()

    if result['code'] == 0:
        return result['data']
    else:
        raise Exception(f"Error: {result['msg']}")

# Usage
teams = list_teams("YOUR_TOKEN")
for team in teams:
    print(f"Team: {team['name']} ({team['member_count']} members)")

member = add_team_member("YOUR_TOKEN", "team-123", "user-999", "member")
print(f"Added member: {member['user_id']}")
```

### JavaScript

```javascript
async function listTeams(token) {
  const response = await fetch(
    'https://your-domain.com/api/v1/teams',
    {
      headers: {
        'Authorization': `Bearer ${token}`,
      },
    }
  );

  const result = await response.json();

  if (result.code === 0) {
    return result.data.items;
  } else {
    throw new Error(result.msg);
  }
}

async function addTeamMember(token, teamId, userId, role = 'member') {
  const response = await fetch(
    `https://your-domain.com/api/v1/teams/${teamId}/members`,
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        user_id: userId,
        role: role,
      }),
    }
  );

  const result = await response.json();

  if (result.code === 0) {
    return result.data;
  } else {
    throw new Error(result.msg);
  }
}

// Usage
const teams = await listTeams('YOUR_TOKEN');
teams.forEach(team => {
  console.log(`Team: ${team.name} (${team.member_count} members)`);
});

const member = await addTeamMember('YOUR_TOKEN', 'team-123', 'user-999', 'member');
console.log('Added member:', member.user_id);
```

## Related Documentation

- [Authentication](../authentication.md) - Authentication methods
- [Rate Limiting](../rate-limiting.md) - Rate limit details
- [Team Management](../../admin-guide/teams/team-management.md) - Admin guide
- [Team Roles](../../user-guide/teams/team-roles.md) - Understanding roles

---

**Last Updated**: 2026-02-11
