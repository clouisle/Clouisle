# API Keys API

This document describes the API endpoints for API key management.

## Overview

The API Keys API allows you to:

- **List API keys**: Get all your API keys
- **Create API keys**: Generate new API keys
- **Update API keys**: Modify API key settings
- **Delete API keys**: Revoke API keys
- **Rotate API keys**: Generate new keys

**Base URL**: `/api/v1/api-keys`

## Authentication

All endpoints require authentication via JWT token.

**Required scopes:**
- `api_key:read` - View API keys
- `api_key:create` - Create API keys
- `api_key:update` - Update API keys
- `api_key:delete` - Delete API keys

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
| `page_size` | integer | No | 20 | Items per page (max: 100) |
| `is_active` | boolean | No | - | Filter by active status |

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
        "prefix": "ak_prod_",
        "scopes": [
          "agent:read",
          "agent:chat",
          "workflow:execute"
        ],
        "is_active": true,
        "last_used_at": "2026-02-11T14:30:00Z",
        "expires_at": "2027-02-11T00:00:00Z",
        "created_at": "2026-02-11T10:00:00Z",
        "usage": {
          "total_requests": 12345,
          "requests_today": 234
        }
      },
      {
        "id": "key-456",
        "name": "Development API Key",
        "prefix": "ak_dev_",
        "scopes": [
          "agent:read",
          "workflow:read"
        ],
        "is_active": true,
        "last_used_at": "2026-02-10T16:00:00Z",
        "expires_at": "2026-08-11T00:00:00Z",
        "created_at": "2026-02-01T10:00:00Z",
        "usage": {
          "total_requests": 567,
          "requests_today": 12
        }
      }
    ],
    "total": 2,
    "page": 1,
    "page_size": 20,
    "total_pages": 1
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
    "prefix": "ak_prod_",
    "description": "API key for production environment",
    "scopes": [
      "agent:read",
      "agent:chat",
      "workflow:execute",
      "kb:read",
      "kb:search"
    ],
    "is_active": true,
    "last_used_at": "2026-02-11T14:30:00Z",
    "last_used_ip": "192.168.1.100",
    "expires_at": "2027-02-11T00:00:00Z",
    "created_at": "2026-02-11T10:00:00Z",
    "updated_at": "2026-02-11T10:00:00Z",
    "usage": {
      "total_requests": 12345,
      "successful_requests": 12100,
      "failed_requests": 245,
      "requests_today": 234,
      "requests_this_month": 5678
    },
    "rate_limits": {
      "requests_per_minute": 60,
      "requests_per_day": 10000
    }
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
  "description": "API key for production environment",
  "scopes": [
    "agent:read",
    "agent:chat",
    "workflow:execute"
  ],
  "expires_at": "2027-02-11T00:00:00Z",
  "rate_limits": {
    "requests_per_minute": 60,
    "requests_per_day": 10000
  }
}
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | API key name (max 100 chars) |
| `description` | string | No | API key description (max 500 chars) |
| `scopes` | array | Yes | List of permission scopes |
| `expires_at` | string | No | Expiration date (ISO 8601) |
| `rate_limits` | object | No | Custom rate limits |

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/api-keys" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Production API Key",
    "description": "API key for production environment",
    "scopes": [
      "agent:read",
      "agent:chat",
      "workflow:execute"
    ],
    "expires_at": "2027-02-11T00:00:00Z"
  }'
```

### Response

**Success (201 Created):**

```json
{
  "code": 0,
  "data": {
    "id": "key-789",
    "name": "Production API Key",
    "key": "ak_prod_1234567890abcdefghijklmnopqrstuvwxyz",
    "prefix": "ak_prod_",
    "scopes": [
      "agent:read",
      "agent:chat",
      "workflow:execute"
    ],
    "is_active": true,
    "expires_at": "2027-02-11T00:00:00Z",
    "created_at": "2026-02-11T16:00:00Z"
  },
  "msg": "API key created successfully. Save this key securely - it won't be shown again."
}
```

**Important:** The `key` field is only returned once. Store it securely.

## Update API Key

Update API key settings.

### Endpoint

```
PATCH /api/v1/api-keys/{key_id}
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
  "description": "Updated description",
  "scopes": [
    "agent:read",
    "agent:chat",
    "workflow:execute",
    "kb:read"
  ],
  "is_active": true
}
```

### Request Example

```bash
curl -X PATCH "https://your-domain.com/api/v1/api-keys/key-123" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Production API Key (Updated)",
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

Generate a new key value while preserving settings.

### Endpoint

```
POST /api/v1/api-keys/{key_id}/rotate
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `key_id` | string | Yes | API Key UUID |

### Request Body

```json
{
  "expires_at": "2027-02-11T00:00:00Z"
}
```

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/api-keys/key-123/rotate" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "expires_at": "2027-02-11T00:00:00Z"
  }'
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "key-123",
    "name": "Production API Key",
    "key": "ak_prod_newabc123xyz456def789ghi012jkl345mno",
    "prefix": "ak_prod_",
    "old_key_valid_until": "2026-02-18T16:00:00Z",
    "expires_at": "2027-02-11T00:00:00Z",
    "rotated_at": "2026-02-11T16:00:00Z"
  },
  "msg": "API key rotated successfully. Old key will remain valid for 7 days."
}
```

**Note:**
- The new key is returned only once
- Old key remains valid for 7 days (grace period)
- Update your applications with the new key before grace period ends

## Get API Key Usage

Get usage statistics for an API key.

### Endpoint

```
GET /api/v1/api-keys/{key_id}/usage
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `key_id` | string | Yes | API Key UUID |

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `start_date` | string | No | 30 days ago | Start date (ISO 8601) |
| `end_date` | string | No | Now | End date (ISO 8601) |
| `group_by` | string | No | day | Group by: hour, day, week, month |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/api-keys/key-123/usage?start_date=2026-02-01&end_date=2026-02-11" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "key_id": "key-123",
    "key_name": "Production API Key",
    "period": {
      "start": "2026-02-01T00:00:00Z",
      "end": "2026-02-11T23:59:59Z"
    },
    "summary": {
      "total_requests": 12345,
      "successful_requests": 12100,
      "failed_requests": 245,
      "success_rate": 98.0,
      "avg_response_time": 0.5
    },
    "daily_stats": [
      {
        "date": "2026-02-11",
        "requests": 1234,
        "successful": 1210,
        "failed": 24,
        "avg_response_time": 0.4
      },
      {
        "date": "2026-02-10",
        "requests": 1156,
        "successful": 1134,
        "failed": 22,
        "avg_response_time": 0.5
      }
    ],
    "endpoints": [
      {
        "endpoint": "/api/v1/agents/{id}/chat",
        "requests": 5678,
        "percentage": 46.0
      },
      {
        "endpoint": "/api/v1/workflows/{id}/execute",
        "requests": 3456,
        "percentage": 28.0
      }
    ]
  },
  "msg": "success"
}
```

## Validate API Key

Validate an API key and check its permissions.

### Endpoint

```
POST /api/v1/api-keys/validate
```

### Request Body

```json
{
  "key": "ak_prod_1234567890abcdefghijklmnopqrstuvwxyz"
}
```

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/api-keys/validate" \
  -H "Content-Type: application/json" \
  -d '{
    "key": "ak_prod_1234567890abcdefghijklmnopqrstuvwxyz"
  }'
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "valid": true,
    "key_id": "key-123",
    "name": "Production API Key",
    "scopes": [
      "agent:read",
      "agent:chat",
      "workflow:execute"
    ],
    "is_active": true,
    "expires_at": "2027-02-11T00:00:00Z",
    "rate_limits": {
      "requests_per_minute": 60,
      "requests_per_day": 10000,
      "remaining_today": 9766
    }
  },
  "msg": "API key is valid"
}
```

**Invalid Key (401 Unauthorized):**

```json
{
  "code": 2001,
  "data": {
    "valid": false,
    "reason": "Invalid API key"
  },
  "msg": "Invalid API key"
}
```

## Error Codes

| Code | Message | Description |
|------|---------|-------------|
| `4000` | API key not found | API key does not exist |
| `2001` | Invalid API key | API key is invalid or expired |
| `3000` | Permission denied | Insufficient permissions |
| `1001` | Validation failed | Invalid request data |
| `5400` | Rate limit exceeded | Too many requests |

## Rate Limits

| Endpoint | Limit |
|----------|-------|
| `GET /api/v1/api-keys` | 100/minute |
| `GET /api/v1/api-keys/{id}` | 100/minute |
| `POST /api/v1/api-keys` | 10/minute |
| `PATCH /api/v1/api-keys/{id}` | 30/minute |
| `DELETE /api/v1/api-keys/{id}` | 10/minute |
| `POST /api/v1/api-keys/{id}/rotate` | 5/minute |
| `POST /api/v1/api-keys/validate` | 100/minute |

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

def create_api_key(token, name, scopes):
    """Create a new API key."""
    url = "https://your-domain.com/api/v1/api-keys"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    data = {
        "name": name,
        "scopes": scopes,
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

def rotate_api_key(token, key_id):
    """Rotate an API key."""
    url = f"https://your-domain.com/api/v1/api-keys/{key_id}/rotate"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    data = {
        "expires_at": "2027-02-11T00:00:00Z"
    }

    response = requests.post(url, headers=headers, json=data)
    result = response.json()

    if result['code'] == 0:
        new_key = result['data']['key']
        print(f"New API Key: {new_key}")
        print(f"Old key valid until: {result['data']['old_key_valid_until']}")
        return result['data']
    else:
        raise Exception(f"Error: {result['msg']}")

# Usage
token = os.getenv("USER_TOKEN")

# Create API key
new_key = create_api_key(
    token,
    "Production API Key",
    ["agent:read", "agent:chat", "workflow:execute"]
)

# List API keys
keys = list_api_keys(token)
for key in keys:
    print(f"Key: {key['name']} - {key['prefix']}...")

# Rotate API key
rotated = rotate_api_key(token, "key-123")
```

### JavaScript

```javascript
async function createApiKey(token, name, scopes) {
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

async function rotateApiKey(token, keyId) {
  const response = await fetch(
    `https://your-domain.com/api/v1/api-keys/${keyId}/rotate`,
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        expires_at: '2027-02-11T00:00:00Z',
      }),
    }
  );

  const result = await response.json();

  if (result.code === 0) {
    console.log(`New API Key: ${result.data.key}`);
    console.log(`Old key valid until: ${result.data.old_key_valid_until}`);
    return result.data;
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
  ['agent:read', 'agent:chat', 'workflow:execute']
);

// List API keys
const keys = await listApiKeys(token);
keys.forEach(key => {
  console.log(`Key: ${key.name} - ${key.prefix}...`);
});

// Rotate API key
const rotated = await rotateApiKey(token, 'key-123');
```

## Related Documentation

- [Authentication](../authentication.md) - Authentication methods
- [API Key Scopes](../../user-guide/api-keys/api-key-scopes.md) - Scope reference
- [Managing API Keys](../../user-guide/api-keys/managing-api-keys.md) - User guide
- [Security Best Practices](../../best-practices/security.md) - Security guide

---

**Last Updated**: 2026-02-11
