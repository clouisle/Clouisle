# Users API

This document describes the API endpoints for user management.

## Overview

The Users API allows you to:

- **Get current user**: Retrieve authenticated user information
- **Update profile**: Modify user profile and settings
- **Change password**: Change the authenticated user's password
- **List users**: Get all users (admin only)
- **Create users**: Add new users (admin only)
- **Update users**: Modify user accounts (admin only)
- **Delete users**: Remove users (admin only)

**Base URLs**:
- Current user: `/api/v1/users`
- Admin: `/api/v1/admin/users`

## Authentication

All endpoints require authentication via JWT token or API key.

**Required scopes (admin):**
- `admin:user:read` - View user information
- `admin:user:create` - Create users
- `admin:user:update` - Update user accounts
- `admin:user:delete` - Delete users

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
    "username": "johndoe",
    "email": "john.doe@example.com",
    "is_active": true,
    "approval_status": "approved",
    "is_superuser": false,
    "avatar_url": "https://example.com/avatars/johndoe.jpg",
    "locale": "en",
    "created_at": "2026-01-15T10:00:00Z",
    "last_login": "2026-02-11T14:30:00Z",
    "auth_source": "local",
    "external_id": null,
    "email_verified": true,
    "force_password_change": false,
    "password_expiration_exempt": false,
    "status": "active",
    "roles": [],
    "sso_connections": []
  },
  "msg": "success"
}
```

## Update Current User

Update the authenticated user's profile.

### Endpoint

```
PUT /api/v1/users/me
```

### Request Body

```json
{
  "username": "johnsmith",
  "email": "john.smith@example.com",
  "avatar_url": "https://example.com/avatars/new-avatar.jpg",
  "locale": "en",
  "email_verification_code": "123456"
}
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `username` | string | No | New username (must be unique) |
| `email` | string | No | New email (must be unique; requires verification code if email verification is enabled) |
| `email_verification_code` | string | No | Email verification code required when changing email |
| `avatar_url` | string | No | Avatar image URL |
| `locale` | string | No | Interface language (e.g. `en`, `zh`) |

### Request Example

```bash
curl -X PUT "https://your-domain.com/api/v1/users/me" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "johnsmith",
    "avatar_url": "https://example.com/avatars/new-avatar.jpg"
  }'
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "user-123",
    "username": "johnsmith",
    "email": "john.doe@example.com",
    "is_active": true,
    "approval_status": "approved",
    "is_superuser": false,
    "avatar_url": "https://example.com/avatars/new-avatar.jpg",
    "locale": "en",
    "created_at": "2026-01-15T10:00:00Z",
    "last_login": "2026-02-11T14:30:00Z",
    "auth_source": "local",
    "external_id": null,
    "email_verified": true,
    "force_password_change": false,
    "password_expiration_exempt": false,
    "status": "active",
    "roles": [],
    "sso_connections": []
  },
  "msg": "Profile updated successfully"
}
```

## Change Password

Change the authenticated user's password.

### Endpoint

```
POST /api/v1/users/me/change-password
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
| `new_password` | string | Yes | New password (validated against password policy) |

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/users/me/change-password" \
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
  "code": 2003,
  "data": null,
  "msg": "Current password is incorrect"
}
```

## List Users

Get a list of all users (admin only).

### Endpoint

```
GET /api/v1/admin/users
```

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `page` | integer | No | 1 | Page number |
| `page_size` | integer | No | 20 | Items per page (max: 100) |
| `status` | array | No | - | Filter by status: `active`, `inactive`, `pending` (repeatable) |
| `search` | string | No | - | Search by username or email |
| `role` | array | No | - | Filter by role name (repeatable) |
| `exclude_user_id` | array | No | - | User IDs to exclude from the result (repeatable) |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/admin/users?page=1&page_size=20" \
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
        "username": "johndoe",
        "email": "john.doe@example.com",
        "is_active": true,
        "approval_status": "approved",
        "is_superuser": false,
        "avatar_url": "https://example.com/avatars/johndoe.jpg",
        "locale": "en",
        "created_at": "2026-01-15T10:00:00Z",
        "last_login": "2026-02-11T14:30:00Z",
        "auth_source": "local",
        "external_id": null,
        "email_verified": true,
        "force_password_change": false,
        "password_expiration_exempt": false,
        "status": "active",
        "roles": [],
        "sso_connections": []
      }
    ],
    "total": 156,
    "page": 1,
    "page_size": 20
  },
  "msg": "success"
}
```

## Get User

Get details of a specific user (admin only).

### Endpoint

```
GET /api/v1/admin/users/{user_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `user_id` | string | Yes | User UUID |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/admin/users/user-123" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "user-123",
    "username": "johndoe",
    "email": "john.doe@example.com",
    "is_active": true,
    "approval_status": "approved",
    "is_superuser": false,
    "avatar_url": "https://example.com/avatars/johndoe.jpg",
    "locale": "en",
    "created_at": "2026-01-15T10:00:00Z",
    "last_login": "2026-02-11T14:30:00Z",
    "auth_source": "local",
    "external_id": null,
    "email_verified": true,
    "force_password_change": false,
    "password_expiration_exempt": false,
    "status": "active",
    "roles": [],
    "sso_connections": []
  },
  "msg": "success"
}
```

## Create User

Create a new user (admin only).

### Endpoint

```
POST /api/v1/admin/users
```

### Request Body

```json
{
  "username": "alice",
  "email": "alice@example.com",
  "password": "secure_password",
  "is_active": true,
  "approval_status": "approved",
  "is_superuser": false,
  "avatar_url": null,
  "locale": "en"
}
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `username` | string | Yes | Username (unique) |
| `email` | string | Yes | User email (unique) |
| `password` | string | Yes | Initial password |
| `is_active` | boolean | No | Active status (default: true) |
| `approval_status` | string | No | Approval status (default: `approved`) |
| `is_superuser` | boolean | No | Superuser flag (default: false) |
| `avatar_url` | string | No | Avatar image URL |
| `locale` | string | No | Interface language (default: `en`) |

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/admin/users" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "alice",
    "email": "alice@example.com",
    "password": "secure_password"
  }'
```

### Response

**Success (201 Created):**

```json
{
  "code": 0,
  "data": {
    "id": "user-789",
    "username": "alice",
    "email": "alice@example.com",
    "is_active": true,
    "approval_status": "approved",
    "is_superuser": false,
    "avatar_url": null,
    "locale": "en",
    "created_at": "2026-02-11T16:00:00Z",
    "last_login": null,
    "auth_source": "local",
    "external_id": null,
    "email_verified": false,
    "force_password_change": false,
    "password_expiration_exempt": false,
    "status": "active",
    "roles": [],
    "sso_connections": []
  },
  "msg": "User created successfully"
}
```

**Error (409 Conflict):**

```json
{
  "code": 5002,
  "data": null,
  "msg": "Username already exists"
}
```

```json
{
  "code": 5003,
  "data": null,
  "msg": "Email already exists"
}
```

## Update User

Update a user's information (admin only).

### Endpoint

```
PUT /api/v1/admin/users/{user_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `user_id` | string | Yes | User UUID |

### Request Body

All fields are optional. Only include fields you want to update.

```json
{
  "email": "alice.smith@example.com",
  "password": "new_password",
  "is_active": true,
  "avatar_url": null,
  "locale": "en",
  "roles": ["admin"]
}
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | string | No | New email |
| `password` | string | No | New password |
| `is_active` | boolean | No | Active status |
| `avatar_url` | string | No | Avatar image URL |
| `locale` | string | No | Interface language |
| `roles` | array | No | Role names to assign |

### Request Example

```bash
curl -X PUT "https://your-domain.com/api/v1/admin/users/user-789" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "is_active": true,
    "roles": ["admin"]
  }'
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "user-789",
    "username": "alice",
    "email": "alice@example.com",
    "is_active": true,
    "approval_status": "approved",
    "is_superuser": false,
    "avatar_url": null,
    "locale": "en",
    "created_at": "2026-02-11T16:00:00Z",
    "last_login": null,
    "auth_source": "local",
    "external_id": null,
    "email_verified": false,
    "force_password_change": false,
    "password_expiration_exempt": false,
    "status": "active",
    "roles": [
      {
        "id": "role-admin",
        "name": "admin",
        "description": null,
        "is_system_role": true,
        "permissions": []
      }
    ],
    "sso_connections": []
  },
  "msg": "User updated successfully"
}
```

## Delete User

Delete a user permanently (admin only).

### Endpoint

```
DELETE /api/v1/admin/users/{user_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `user_id` | string | Yes | User UUID |

### Request Example

```bash
curl -X DELETE "https://your-domain.com/api/v1/admin/users/user-789" \
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

## Activate / Deactivate User (admin)

Toggle a user's active status.

### Endpoints

```
POST /api/v1/admin/users/{user_id}/activate
POST /api/v1/admin/users/{user_id}/deactivate
```

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/admin/users/user-789/deactivate" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

### Response

**Success (200 OK):**

Returns the updated `UserSchema` with `is_active` toggled.

## Reset User Password

> **Note:** Not implemented / Roadmap. There is no direct password-reset endpoint. Admin alternatives under `/api/v1/admin/users/{user_id}`:
> - `POST /{user_id}/force-password-change` - force the user to change their password at next login
> - `POST /{user_id}/reset-password-expiration` - reset the password expiration timer
> - `POST /{user_id}/exempt-password-expiration` - toggle password expiration exemption

## Get User Activity

> **Note:** Not implemented / Roadmap. There is no per-user activity endpoint. User actions are recorded in the audit log (`GET /api/v1/admin/audit-logs`).

## Error Codes

| Code | Message | Description |
|------|---------|-------------|
| `4001` | User not found | User does not exist |
| `2003` | Invalid credentials | Wrong password |
| `3000` | Permission denied | Insufficient permissions |
| `1001` | Validation failed | Invalid request data |
| `5002` | Username already exists | Username is taken |
| `5003` | Email already exists | Email is taken |

> **Note:** No per-endpoint rate limits are implemented. There is no rate-limit middleware on these endpoints.

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

def update_profile(token, username, avatar_url=None, locale=None):
    """Update user profile."""
    url = "https://your-domain.com/api/v1/users/me"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    data = {
        "username": username,
        "avatar_url": avatar_url,
        "locale": locale
    }

    response = requests.put(url, headers=headers, json=data)
    result = response.json()

    if result['code'] == 0:
        return result['data']
    else:
        raise Exception(f"Error: {result['msg']}")

# Usage
user = get_current_user("YOUR_TOKEN")
print(f"User: {user['username']}")

updated = update_profile("YOUR_TOKEN", "johnsmith", locale="en")
print(f"Updated: {updated['username']}")
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

async function updateProfile(token, username, avatarUrl = null, locale = null) {
  const response = await fetch(
    'https://your-domain.com/api/v1/users/me',
    {
      method: 'PUT',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        username: username,
        avatar_url: avatarUrl,
        locale: locale,
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
console.log('User:', user.username);

const updated = await updateProfile('YOUR_TOKEN', 'johnsmith', null, 'en');
console.log('Updated:', updated.username);
```

## Related Documentation

- [Authentication](../authentication.md) - Authentication methods
- [Rate Limiting](../rate-limiting.md) - Rate limit details
- [User Management](../../admin-guide/users/user-management.md) - Admin guide
- [Profile Settings](../../user-guide/profile/profile-settings.md) - User guide

---

**Last Updated**: 2026-02-11
