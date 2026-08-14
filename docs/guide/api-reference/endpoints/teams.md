# Teams API

This document describes the API endpoints for team management.

## Overview

The Teams API allows you to:

- **List my teams**: Get the teams the current user belongs to
- **Get team details**: Retrieve team information including members
- **Create teams**: Create new teams (admin only)
- **Update teams**: Modify team settings
- **Delete teams**: Remove teams (admin only)
- **Manage members**: Add, remove, and update team members

**Base URLs**:
- Platform: `/api/v1/teams`
- Admin: `/api/v1/admin/teams`

## Authentication

All endpoints require authentication via JWT token or API key.

**Required scopes:**
- `team:read` - View team information
- `team:manage` - Manage teams
- `admin:team:read` - List all teams (admin)
- `admin:team:create` - Create teams (admin)
- `admin:team:delete` - Delete teams (admin)

## List My Teams

Get all teams the current user belongs to, with the user's role in each.

### Endpoint

```
GET /api/v1/teams/my
```

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/teams/my" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": [
    {
      "id": "team-123",
      "name": "Marketing Team",
      "description": "Marketing and content creation team",
      "avatar_url": null,
      "role": "member",
      "joined_at": "2026-01-15T10:00:00Z"
    }
  ],
  "msg": "success"
}
```

**Note:** There is no `GET /api/v1/teams` list endpoint for all teams. Admins can list all teams (paginated, with `search` by name or description) via `GET /api/v1/admin/teams` (page/page_size, default page_size 50), which requires `admin:team:read`.

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
    "avatar_url": null,
    "is_default": false,
    "owner": {
      "id": "user-456",
      "username": "alice",
      "email": "alice@example.com",
      "avatar_url": "https://example.com/avatars/alice.jpg"
    },
    "created_at": "2026-01-15T10:00:00Z",
    "updated_at": "2026-02-11T15:30:00Z",
    "members": [
      {
        "id": "membership-001",
        "user_id": "user-456",
        "username": "alice",
        "email": "alice@example.com",
        "avatar_url": "https://example.com/avatars/alice.jpg",
        "role": "owner",
        "joined_at": "2026-01-15T10:00:00Z"
      },
      {
        "id": "membership-002",
        "user_id": "user-789",
        "username": "bob",
        "email": "bob@example.com",
        "avatar_url": null,
        "role": "member",
        "joined_at": "2026-01-16T10:00:00Z"
      }
    ]
  },
  "msg": "success"
}
```

## Create Team

Create a new team (admin only).

### Endpoint

```
POST /api/v1/admin/teams
```

### Request Body

```json
{
  "name": "Sales Team",
  "description": "Sales and customer relations team",
  "avatar_url": null
}
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Team name |
| `description` | string | No | Team description |
| `avatar_url` | string | No | Team avatar URL |

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/admin/teams" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Sales Team",
    "description": "Sales and customer relations team"
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
    "avatar_url": null,
    "is_default": false,
    "owner": null,
    "created_at": "2026-02-11T16:00:00Z",
    "updated_at": "2026-02-11T16:00:00Z"
  },
  "msg": "Team created successfully"
}
```

## Update Team

Update team information.

### Endpoint

```
PUT /api/v1/teams/{team_id}
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
  "avatar_url": null
}
```

### Request Example

```bash
curl -X PUT "https://your-domain.com/api/v1/teams/team-123" \
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
    "description": null,
    "avatar_url": null,
    "is_default": false,
    "owner": {
      "id": "user-456",
      "username": "alice",
      "email": "alice@example.com",
      "avatar_url": null
    },
    "created_at": "2026-01-15T10:00:00Z",
    "updated_at": "2026-02-11T16:05:00Z"
  },
  "msg": "Team updated successfully"
}
```

## Delete Team

Delete a team permanently (admin only).

### Endpoint

```
DELETE /api/v1/admin/teams/{team_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `team_id` | string | Yes | Team UUID |

### Request Example

```bash
curl -X DELETE "https://your-domain.com/api/v1/admin/teams/team-123" \
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

> **Note:** Not implemented / Roadmap. There is no separate `GET /teams/{team_id}/members` endpoint. The full member list is included in `GET /api/v1/teams/{team_id}` (see [Get Team](#get-team)).

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
    "id": "membership-003",
    "user_id": "user-999",
    "username": "carol",
    "email": "carol@example.com",
    "avatar_url": null,
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
PUT /api/v1/teams/{team_id}/members/{user_id}
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
curl -X PUT "https://your-domain.com/api/v1/teams/team-123/members/user-999" \
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
    "id": "membership-003",
    "user_id": "user-999",
    "username": "carol",
    "email": "carol@example.com",
    "avatar_url": null,
    "role": "admin",
    "joined_at": "2026-02-11T16:00:00Z"
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

> **Note:** Not implemented / Roadmap. There is no team statistics endpoint.

## Error Codes

| Code | Message | Description |
|------|---------|-------------|
| `4004` | Team not found | Team does not exist |
| `3000` | Permission denied | Insufficient permissions |
| `3002` | Not team member | User is not a team member |
| `1001` | Validation failed | Invalid request data |
| `5102` | Name already exists | Team name is taken |
| `5103` | Already team member | User is already a member |

> **Note:** No per-endpoint rate limits are implemented. There is no rate-limit middleware on these endpoints.

## Code Examples

### Python

```python
import requests

def list_my_teams(token):
    """List teams the current user belongs to."""
    url = "https://your-domain.com/api/v1/teams/my"
    headers = {
        "Authorization": f"Bearer {token}"
    }

    response = requests.get(url, headers=headers)
    result = response.json()

    if result['code'] == 0:
        return result['data']
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
teams = list_my_teams("YOUR_TOKEN")
for team in teams:
    print(f"Team: {team['name']} (role: {team['role']})")

member = add_team_member("YOUR_TOKEN", "team-123", "user-999", "member")
print(f"Added member: {member['user_id']}")
```

### JavaScript

```javascript
async function listMyTeams(token) {
  const response = await fetch(
    'https://your-domain.com/api/v1/teams/my',
    {
      headers: {
        'Authorization': `Bearer ${token}`,
      },
    }
  );

  const result = await response.json();

  if (result.code === 0) {
    return result.data;
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
const teams = await listMyTeams('YOUR_TOKEN');
teams.forEach(team => {
  console.log(`Team: ${team.name} (role: ${team.role})`);
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
