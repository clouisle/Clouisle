# API Keys API

This document describes the API endpoints for API key management.

## Overview

The API Keys API allows you to:

- **List API keys**: Get all your API keys
- **Create API keys**: Generate new API keys
- **Update API keys**: Modify API key settings
- **Delete API keys**: Revoke API keys
- **Activate/deactivate API keys**: Toggle key status

**Base URL**: `/api/v1/api-keys`

## Authentication

All API-key management endpoints require an authenticated JWT user with the applicable permission.

**Required permissions:**
- `apikey:read` - View API keys
- `apikey:create` - Create API keys
- `apikey:update` - Update API keys
- `apikey:delete` - Delete API keys

**Note:** API keys cannot be used to manage other API keys.

## List API Keys

Get a list of all your API keys.

### Endpoint

```
GET /api/v1/api-keys
```

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `page` | integer | No | 1 | Page number |
| `page_size` | integer | No | 20 | Items per page |
| `status` | array | No | - | Filter by status: `active`, `inactive`, `expired` (repeatable) |
| `user_id` | array | No | - | Filter by owner user ID (admin only) |
| `search` | string | No | - | Search by name or key prefix |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/api-keys" \
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
        "id": "key-123",
        "name": "Production API Key",
        "key_prefix": "clou_a1b2c3d",
        "user_id": "user-001",
        "user": {
          "id": "user-001",
          "username": "alice"
        },
        "scopes": [
          "chat",
          "agent:read"
        ],
        "rate_limit": 1000,
        "is_active": true,
        "last_used_at": "2026-02-11T14:30:00Z",
        "expires_at": "2027-02-11T00:00:00Z",
        "agents": [
          {
            "id": "agent-001",
            "name": "Customer Support Agent",
            "icon": "🤖"
          }
        ],
        "workflows": [],
        "created_at": "2026-02-11T10:00:00Z",
        "updated_at": "2026-02-11T10:00:00Z"
      },
      {
        "id": "key-456",
        "name": "Development API Key",
        "key_prefix": "clou_f6e5d4c",
        "user_id": "user-001",
        "user": {
          "id": "user-001",
          "username": "alice"
        },
        "scopes": [
          "chat"
        ],
        "rate_limit": 1000,
        "is_active": true,
        "last_used_at": "2026-02-10T16:00:00Z",
        "expires_at": "2026-08-11T00:00:00Z",
        "agents": [],
        "workflows": [],
        "created_at": "2026-02-01T10:00:00Z",
        "updated_at": "2026-02-01T10:00:00Z"
      }
    ],
    "total": 2,
    "page": 1,
    "page_size": 20
  },
  "msg": "success"
}
```

**Note:** The actual API key value is only shown once during creation.

## Get API Key

Get details of a specific API key.

### Endpoint

```
GET /api/v1/api-keys/{key_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `key_id` | string | Yes | API Key UUID |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/api-keys/key-123" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "key-123",
    "name": "Production API Key",
    "key_prefix": "clou_a1b2c3d",
    "user_id": "user-001",
    "user": {
      "id": "user-001",
      "username": "alice"
    },
    "scopes": [
      "chat",
      "agent:read"
    ],
    "rate_limit": 1000,
    "is_active": true,
    "last_used_at": "2026-02-11T14:30:00Z",
    "expires_at": "2027-02-11T00:00:00Z",
    "agents": [
      {
        "id": "agent-001",
        "name": "Customer Support Agent",
        "icon": "🤖"
      }
    ],
    "workflows": [],
    "created_at": "2026-02-11T10:00:00Z",
    "updated_at": "2026-02-11T10:00:00Z"
  },
  "msg": "success"
}
```

## Create API Key

Create a new API key.

### Endpoint

```
POST /api/v1/api-keys
```

### Request Body

```json
{
  "name": "Production API Key",
  "scopes": [
    "chat",
    "agent:read"
  ],
  "rate_limit": 1000,
  "expires_at": "2027-02-11T00:00:00Z",
  "agent_ids": [
    "agent-001"
  ],
  "workflow_ids": []
}
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | API key name (max 100 chars) |
| `scopes` | array | No | List of permission scopes (default: `["chat"]`) |
| `rate_limit` | integer | No | Rate limit per minute, `0` means unlimited (default: 1000) |
| `expires_at` | string | No | Expiration date (ISO 8601) |
| `agent_ids` | array | No | Agent IDs this key can access (empty = no restriction) |
| `workflow_ids` | array | No | Workflow IDs this key can access (empty = no restriction) |

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/api-keys" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Production API Key",
    "scopes": ["chat", "agent:read"],
    "rate_limit": 1000,
    "expires_at": "2027-02-11T00:00:00Z"
  }'
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "key-789",
    "name": "Production API Key",
    "key": "clou_a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4e5f67890",
    "key_prefix": "clou_a1b2c3d",
    "user_id": "user-001",
    "user": {
      "id": "user-001",
      "username": "alice"
    },
    "scopes": [
      "chat",
      "agent:read"
    ],
    "rate_limit": 1000,
    "is_active": true,
    "expires_at": "2027-02-11T00:00:00Z",
    "agents": [],
    "workflows": [],
    "created_at": "2026-02-11T16:00:00Z",
    "updated_at": "2026-02-11T16:00:00Z"
  },
  "msg": "API key created successfully. Save this key securely - it won't be shown again."
}
```

**Important:** The `key` field is only returned once. Store it securely.

## Update API Key

Update API key settings.

### Endpoint

```
PUT /api/v1/api-keys/{key_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `key_id` | string | Yes | API Key UUID |

### Request Body

All fields are optional. Only include fields you want to update.

```json
{
  "name": "Production API Key (Updated)",
  "scopes": [
    "chat",
    "agent:read"
  ],
  "rate_limit": 500,
  "is_active": true,
  "agent_ids": ["agent-001"],
  "workflow_ids": []
}
```

### Request Example

```bash
curl -X PUT "https://your-domain.com/api/v1/api-keys/key-123" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Production API Key (Updated)",
    "rate_limit": 500,
    "is_active": true
  }'
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "key-123",
    "name": "Production API Key (Updated)",
    "is_active": true,
    "updated_at": "2026-02-11T16:05:00Z"
  },
  "msg": "API key updated successfully"
}
```

**Note:** Updating scopes takes effect immediately for all requests.

## Delete API Key

Delete (revoke) an API key permanently.

### Endpoint

```
DELETE /api/v1/api-keys/{key_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `key_id` | string | Yes | API Key UUID |

### Request Example

```bash
curl -X DELETE "https://your-domain.com/api/v1/api-keys/key-123" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": null,
  "msg": "API key deleted successfully"
}
```

**Note:** Deleted API keys cannot be recovered. All requests using this key will fail immediately.

## Rotate API Key

> **Note:** Not implemented / Roadmap. There is no key-rotation endpoint. To rotate a key, create a new key and delete the old one.

## Get API Key Stats

Get aggregate statistics across all API keys the current user can see.

### Endpoint

```
GET /api/v1/api-keys/stats
```

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/api-keys/stats" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "total": 3,
    "active": 2,
    "inactive": 0,
    "expired": 1
  },
  "msg": "success"
}
```

## Activate / Deactivate API Key

Toggle a key between active and inactive without deleting it.

### Endpoints

```
POST /api/v1/api-keys/{key_id}/activate
POST /api/v1/api-keys/{key_id}/deactivate
```

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/api-keys/key-123/deactivate" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "key-123",
    "name": "Production API Key",
    "key_prefix": "clou_a1b2c3d",
    "user_id": "user-001",
    "scopes": ["chat", "agent:read"],
    "rate_limit": 1000,
    "is_active": false,
    "expires_at": "2027-02-11T00:00:00Z",
    "agents": [],
    "workflows": [],
    "created_at": "2026-02-11T10:00:00Z",
    "updated_at": "2026-02-11T16:00:00Z"
  },
  "msg": "success"
}
```

## Validate API Key

> **Note:** Not implemented / Roadmap. There is no key-validation endpoint; authenticate normally with the key (as `Authorization: Bearer clou_...`) against the API.

## Error Codes

| Code | Message | Description |
|------|---------|-------------|
| `4000` | Not found | API key does not exist |
| `2001` | Invalid token | API key is invalid or expired |
| `3000` | Permission denied | Insufficient permissions |
| `1001` | Validation failed | Invalid request data |

> **Note:** No per-endpoint rate limits are implemented. The `rate_limit` field is stored for informational purposes and is not enforced by middleware.

## Best Practices

### Security

**✅ Do:**
- Store API keys securely (environment variables, secret managers)
- Use different keys for different environments
- Rotate keys regularly (every 90 days)
- Use minimal required scopes
- Set expiration dates
- Monitor key usage
- Revoke unused keys
- Use HTTPS only

**❌ Don't:**
- Commit keys to version control
- Share keys between applications
- Use same key for dev and production
- Grant excessive scopes
- Create keys without expiration
- Ignore usage alerts
- Keep old keys active
- Send keys over insecure channels

### Key Management

**✅ Do:**
- Name keys descriptively
- Document key purposes
- Track key ownership
- Set up usage alerts
- Review keys regularly
- Use grace period during rotation
- Test new keys before revoking old ones

**❌ Don't:**
- Use generic names
- Skip documentation
- Forget key owners
- Ignore usage patterns
- Keep unused keys
- Rotate without grace period
- Revoke keys immediately

## Code Examples

### Python

```python
import requests
import os

def create_api_key(token, name, scopes, rate_limit=1000):
    """Create a new API key."""
    url = "https://your-domain.com/api/v1/api-keys"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    data = {
        "name": name,
        "scopes": scopes,
        "rate_limit": rate_limit,
        "expires_at": "2027-02-11T00:00:00Z"
    }

    response = requests.post(url, headers=headers, json=data)
    result = response.json()

    if result['code'] == 0:
        # Store the key securely
        api_key = result['data']['key']
        print(f"API Key created: {api_key}")
        print("Save this key securely - it won't be shown again!")
        return result['data']
    else:
        raise Exception(f"Error: {result['msg']}")

def list_api_keys(token):
    """List all API keys."""
    url = "https://your-domain.com/api/v1/api-keys"
    headers = {
        "Authorization": f"Bearer {token}"
    }

    response = requests.get(url, headers=headers)
    result = response.json()

    if result['code'] == 0:
        return result['data']['items']
    else:
        raise Exception(f"Error: {result['msg']}")

# Usage
token = os.getenv("USER_TOKEN")

# Create API key
new_key = create_api_key(
    token,
    "Production API Key",
    ["chat", "agent:read"]
)

# List API keys
keys = list_api_keys(token)
for key in keys:
    print(f"Key: {key['name']} - {key['key_prefix']}...")
```

### JavaScript

```javascript
async function createApiKey(token, name, scopes, rateLimit = 1000) {
  const response = await fetch(
    'https://your-domain.com/api/v1/api-keys',
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        name: name,
        scopes: scopes,
        rate_limit: rateLimit,
        expires_at: '2027-02-11T00:00:00Z',
      }),
    }
  );

  const result = await response.json();

  if (result.code === 0) {
    const apiKey = result.data.key;
    console.log(`API Key created: ${apiKey}`);
    console.log('Save this key securely - it won\'t be shown again!');
    return result.data;
  } else {
    throw new Error(result.msg);
  }
}

async function listApiKeys(token) {
  const response = await fetch(
    'https://your-domain.com/api/v1/api-keys',
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

// Usage
const token = process.env.USER_TOKEN;

// Create API key
const newKey = await createApiKey(
  token,
  'Production API Key',
  ['chat', 'agent:read']
);

// List API keys
const keys = await listApiKeys(token);
keys.forEach(key => {
  console.log(`Key: ${key.name} - ${key.key_prefix}...`);
});
```

## Related Documentation

- [Authentication](../authentication.md) - Authentication methods
- [API Key Scopes](../../user-guide/api-keys/api-key-scopes.md) - Scope reference
- [Managing API Keys](../../user-guide/api-keys/managing-api-keys.md) - User guide
- [Security Checklist](../../operations/security-checklist.md) - Security guidance

---

**Last Updated**: 2026-02-11
