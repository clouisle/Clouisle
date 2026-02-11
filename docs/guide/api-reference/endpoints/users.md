# Users API

This document describes the API endpoints for user management.

## Overview

The Users API allows you to:

- **Get current user**: Retrieve authenticated user information
- **Update profile**: Modify user profile and settings
- **List users**: Get all users (admin only)
- **Create users**: Add new users (admin only)
- **Update users**: Modify user accounts (admin only)
- **Delete users**: Remove users (admin only)

**Base URL**: `/api/v1/users`

## Authentication

All endpoints require authentication via JWT token or API key.

**Required scopes:**
- `user:read` - View user information
- `user:update` - Update user information
- `user:create` - Create users (admin only)
- `user:delete` - Delete users (admin only)

## Get Current User

Get information about the authenticated user.

### Endpoint

```
GET /api/v1/users/me
```

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/users/me" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "user-123",
    "email": "john.doe@example.com",
    "username": "johndoe",
    "full_name": "John Doe",
    "avatar_url": "https://example.com/avatars/johndoe.jpg",
    "role": "user",
    "is_active": true,
    "is_verified": true,
    "created_at": "2026-01-15T10:00:00Z",
    "last_login": "2026-02-11T14:30:00Z",
    "preferences": {
      "language": "en",
      "timezone": "America/New_York",
      "theme": "light"
    },
    "teams": [
      {
        "id": "team-456",
        "name": "Marketing Team",
        "role": "member"
      }
    ]
  },
  "msg": "success"
}
```

## Update Current User

Update the authenticated user's profile.

### Endpoint

```
PATCH /api/v1/users/me
```

### Request Body

```json
{
  "full_name": "John Smith",
  "avatar_url": "https://example.com/avatars/new-avatar.jpg",
  "preferences": {
    "language": "en",
    "timezone": "America/Los_Angeles",
    "theme": "dark"
  }
}
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `full_name` | string | No | User's full name |
| `avatar_url` | string | No | Avatar image URL |
| `preferences` | object | No | User preferences |

### Request Example

```bash
curl -X PATCH "https://your-domain.com/api/v1/users/me" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "John Smith",
    "preferences": {
      "theme": "dark"
    }
  }'
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "user-123",
    "full_name": "John Smith",
    "preferences": {
      "language": "en",
      "timezone": "America/New_York",
      "theme": "dark"
    },
    "updated_at": "2026-02-11T16:00:00Z"
  },
  "msg": "Profile updated successfully"
}
```

## Change Password

Change the authenticated user's password.

### Endpoint

```
POST /api/v1/users/me/password
```

### Request Body

```json
{
  "current_password": "old_password",
  "new_password": "new_secure_password"
}
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `current_password` | string | Yes | Current password |
| `new_password` | string | Yes | New password (min 8 chars) |

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/users/me/password" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "current_password": "old_password",
    "new_password": "new_secure_password"
  }'
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": null,
  "msg": "Password changed successfully"
}
```

**Error (401 Unauthorized):**

```json
{
  "code": 2001,
  "data": null,
  "msg": "Current password is incorrect"
}
```

## List Users

Get a list of all users (admin only).

### Endpoint

```
GET /api/v1/users
```

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `page` | integer | No | 1 | Page number |
| `page_size` | integer | No | 20 | Items per page (max: 100) |
| `role` | string | No | - | Filter by role: admin, user |
| `is_active` | boolean | No | - | Filter by active status |
| `search` | string | No | - | Search by name or email |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/users?page=1&page_size=20" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "user-123",
        "email": "john.doe@example.com",
        "username": "johndoe",
        "full_name": "John Doe",
        "avatar_url": "https://example.com/avatars/johndoe.jpg",
        "role": "user",
        "is_active": true,
        "is_verified": true,
        "created_at": "2026-01-15T10:00:00Z",
        "last_login": "2026-02-11T14:30:00Z",
        "team_count": 3
      }
    ],
    "total": 156,
    "page": 1,
    "page_size": 20,
    "total_pages": 8
  },
  "msg": "success"
}
```

## Get User

Get details of a specific user (admin only).

### Endpoint

```
GET /api/v1/users/{user_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `user_id` | string | Yes | User UUID |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/users/user-123" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "user-123",
    "email": "john.doe@example.com",
    "username": "johndoe",
    "full_name": "John Doe",
    "avatar_url": "https://example.com/avatars/johndoe.jpg",
    "role": "user",
    "is_active": true,
    "is_verified": true,
    "created_at": "2026-01-15T10:00:00Z",
    "last_login": "2026-02-11T14:30:00Z",
    "login_count": 234,
    "failed_login_count": 0,
    "preferences": {
      "language": "en",
      "timezone": "America/New_York",
      "theme": "light"
    },
    "teams": [
      {
        "id": "team-456",
        "name": "Marketing Team",
        "role": "member"
      }
    ],
    "stats": {
      "agents_created": 12,
      "workflows_created": 8,
      "conversations": 45,
      "api_keys": 3
    }
  },
  "msg": "success"
}
```

## Create User

Create a new user (admin only).

### Endpoint

```
POST /api/v1/users
```

### Request Body

```json
{
  "email": "alice@example.com",
  "username": "alice",
  "full_name": "Alice Johnson",
  "password": "secure_password",
  "role": "user",
  "is_active": true,
  "send_welcome_email": true
}
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | string | Yes | User email (unique) |
| `username` | string | Yes | Username (unique) |
| `full_name` | string | Yes | User's full name |
| `password` | string | Yes | Initial password (min 8 chars) |
| `role` | string | No | User role: admin, user (default: user) |
| `is_active` | boolean | No | Active status (default: true) |
| `send_welcome_email` | boolean | No | Send welcome email (default: true) |

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/users" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "alice@example.com",
    "username": "alice",
    "full_name": "Alice Johnson",
    "password": "secure_password",
    "role": "user"
  }'
```

### Response

**Success (201 Created):**

```json
{
  "code": 0,
  "data": {
    "id": "user-789",
    "email": "alice@example.com",
    "username": "alice",
    "full_name": "Alice Johnson",
    "role": "user",
    "is_active": true,
    "created_at": "2026-02-11T16:00:00Z"
  },
  "msg": "User created successfully"
}
```

**Error (409 Conflict):**

```json
{
  "code": 5001,
  "data": {
    "field": "email"
  },
  "msg": "User with this email already exists"
}
```

## Update User

Update a user's information (admin only).

### Endpoint

```
PATCH /api/v1/users/{user_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `user_id` | string | Yes | User UUID |

### Request Body

All fields are optional. Only include fields you want to update.

```json
{
  "full_name": "Alice Smith",
  "role": "admin",
  "is_active": true
}
```

### Request Example

```bash
curl -X PATCH "https://your-domain.com/api/v1/users/user-789" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "Alice Smith",
    "role": "admin"
  }'
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "user-789",
    "full_name": "Alice Smith",
    "role": "admin",
    "updated_at": "2026-02-11T16:05:00Z"
  },
  "msg": "User updated successfully"
}
```

## Delete User

Delete a user permanently (admin only).

### Endpoint

```
DELETE /api/v1/users/{user_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `user_id` | string | Yes | User UUID |

### Request Example

```bash
curl -X DELETE "https://your-domain.com/api/v1/users/user-789" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": null,
  "msg": "User deleted successfully"
}
```

## Reset User Password

Reset a user's password (admin only).

### Endpoint

```
POST /api/v1/users/{user_id}/reset-password
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `user_id` | string | Yes | User UUID |

### Request Body

```json
{
  "new_password": "new_secure_password",
  "send_email": true
}
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `new_password` | string | No | New password (if not provided, generates random) |
| `send_email` | boolean | No | Send password reset email (default: true) |

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/users/user-789/reset-password" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "send_email": true
  }'
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "temporary_password": "Abc123!@#Xyz"
  },
  "msg": "Password reset successfully"
}
```

## Get User Activity

Get user activity log (admin only).

### Endpoint

```
GET /api/v1/users/{user_id}/activity
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `user_id` | string | Yes | User UUID |

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `page` | integer | No | 1 | Page number |
| `page_size` | integer | No | 50 | Items per page (max: 100) |
| `start_date` | string | No | 30 days ago | Start date (ISO 8601) |
| `end_date` | string | No | Now | End date (ISO 8601) |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/users/user-789/activity?page=1&page_size=50" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "activity-001",
        "action": "create_agent",
        "resource_type": "agent",
        "resource_id": "agent-456",
        "resource_name": "Customer Support Agent",
        "timestamp": "2026-02-11T14:30:00Z",
        "ip_address": "192.168.1.100",
        "user_agent": "Mozilla/5.0..."
      }
    ],
    "total": 234,
    "page": 1,
    "page_size": 50,
    "total_pages": 5
  },
  "msg": "success"
}
```

## Error Codes

| Code | Message | Description |
|------|---------|-------------|
| `4000` | User not found | User does not exist |
| `2001` | Invalid credentials | Wrong password |
| `3000` | Permission denied | Insufficient permissions |
| `1001` | Validation failed | Invalid request data |
| `5001` | User already exists | Email or username taken |

## Rate Limits

| Endpoint | Limit |
|----------|-------|
| `GET /api/v1/users/me` | 100/minute |
| `PATCH /api/v1/users/me` | 30/minute |
| `POST /api/v1/users/me/password` | 5/minute |
| `GET /api/v1/users` | 100/minute (admin) |
| `POST /api/v1/users` | 10/minute (admin) |
| `PATCH /api/v1/users/{id}` | 30/minute (admin) |
| `DELETE /api/v1/users/{id}` | 10/minute (admin) |

## Best Practices

### Profile Updates

**✅ Do:**
- Validate email format
- Use strong passwords
- Update preferences regularly
- Keep profile information current

**❌ Don't:**
- Share account credentials
- Use weak passwords
- Skip email verification
- Ignore security settings

### Admin Operations

**✅ Do:**
- Verify user information before creation
- Use strong initial passwords
- Send welcome emails
- Document user changes
- Review user activity regularly

**❌ Don't:**
- Create users without verification
- Use default passwords
- Skip welcome emails
- Forget to audit changes
- Delete users without backup

## Code Examples

### Python

```python
import requests

def get_current_user(token):
    """Get current user information."""
    url = "https://your-domain.com/api/v1/users/me"
    headers = {
        "Authorization": f"Bearer {token}"
    }

    response = requests.get(url, headers=headers)
    result = response.json()

    if result['code'] == 0:
        return result['data']
    else:
        raise Exception(f"Error: {result['msg']}")

def update_profile(token, full_name, preferences):
    """Update user profile."""
    url = "https://your-domain.com/api/v1/users/me"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    data = {
        "full_name": full_name,
        "preferences": preferences
    }

    response = requests.patch(url, headers=headers, json=data)
    result = response.json()

    if result['code'] == 0:
        return result['data']
    else:
        raise Exception(f"Error: {result['msg']}")

# Usage
user = get_current_user("YOUR_TOKEN")
print(f"User: {user['full_name']}")

updated = update_profile(
    "YOUR_TOKEN",
    "John Smith",
    {"theme": "dark"}
)
print(f"Updated: {updated['full_name']}")
```

### JavaScript

```javascript
async function getCurrentUser(token) {
  const response = await fetch(
    'https://your-domain.com/api/v1/users/me',
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

async function updateProfile(token, fullName, preferences) {
  const response = await fetch(
    'https://your-domain.com/api/v1/users/me',
    {
      method: 'PATCH',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        full_name: fullName,
        preferences: preferences,
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
const user = await getCurrentUser('YOUR_TOKEN');
console.log('User:', user.full_name);

const updated = await updateProfile(
  'YOUR_TOKEN',
  'John Smith',
  { theme: 'dark' }
);
console.log('Updated:', updated.full_name);
```

## Related Documentation

- [Authentication](../authentication.md) - Authentication methods
- [Rate Limiting](../rate-limiting.md) - Rate limit details
- [User Management](../../admin-guide/users/user-management.md) - Admin guide
- [Profile Settings](../../user-guide/profile/profile-settings.md) - User guide

---

**Last Updated**: 2026-02-11
