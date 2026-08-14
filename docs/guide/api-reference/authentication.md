# Authentication

This guide explains how to authenticate with the Clouisle API.

## Authentication Methods

Clouisle supports two authentication methods:

1. **JWT Token Authentication** - For user sessions
2. **API Key Authentication** - For programmatic access

## JWT Token Authentication

### Obtaining a Token

**Endpoint**: `POST /api/v1/login/access-token`

**Request:**
```bash
curl -X POST "https://your-domain.com/api/v1/login/access-token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=your_username&password=your_password"
```

**Response:**
```json
{
  "code": 0,
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer"
  },
  "msg": "Login successful"
}
```

The response contains only `access_token` and `token_type`. There is no `expires_in` field. If the administrator enforces a password change, the response additionally includes `force_password_change: true` and `reason` (`"expired"` or `"force"`).

### Using the Token

Include the token in the `Authorization` header:

```bash
curl -X GET "https://your-domain.com/api/v1/users/me" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

### Token Expiration

- **Default lifetime**: The access token is valid for the `session_timeout_days` site setting (default **30 days**, configurable by administrators)
- **JWT fallback**: If the site setting is absent, the JWT configuration falls back to `ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 8` (8 days)
- **Refresh**: There is no refresh endpoint — login again to get a new token
- **Expired JWT**: Returns `403 Forbidden` with code `2003` (`INVALID_CREDENTIALS`); only **API key** expiry returns `401 Unauthorized` with code `2002` (`TOKEN_EXPIRED`)

### Logout

**Endpoint**: `POST /api/v1/login/logout`

**Request:**
```bash
curl -X POST "https://your-domain.com/api/v1/login/logout" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Response:**
```json
{
  "code": 0,
  "data": null,
  "msg": "Logout successful"
}
```

## API Key Authentication

### Creating an API Key

API keys are created through the web interface or API:

**Via Web Interface:**
1. Navigate to **API Keys** section
2. Click **"Create API Key"**
3. Configure key settings:
   - Name
   - Scopes (stored for reference; access is enforced via user roles and agent/workflow associations)
   - Restricted agents / workflows (optional)
   - Expiration date (optional)
   - Rate limit (optional, informational only)
4. Click **"Create"**
5. **Copy the key immediately** (shown only once)

**Via API:**

**Endpoint**: `POST /api/v1/api-keys`

**Request:**
```bash
curl -X POST "https://your-domain.com/api/v1/api-keys" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Production API Key",
    "scopes": ["agent:read", "agent:chat", "kb:read"],
    "rate_limit": 1000,
    "expires_at": "2027-12-31T23:59:59Z",
    "agent_ids": [],
    "workflow_ids": []
  }'
```

**Response:**
```json
{
  "code": 0,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "key": "clou_1234567890abcdef...",
    "key_prefix": "clou_1234567",
    "name": "Production API Key",
    "scopes": ["agent:read", "agent:chat", "kb:read"],
    "rate_limit": 1000,
    "created_at": "2026-02-11T10:00:00Z",
    "expires_at": "2027-12-31T23:59:59Z"
  },
  "msg": "API key created successfully"
}
```

**⚠️ Important**: The full API key is only shown once at creation time. The `key_prefix` field stores the first 12 characters of the key for identification; it cannot be used to authenticate.

### Using an API Key

Include the API key in the `Authorization` header with `Bearer` prefix:

```bash
curl -X GET "https://your-domain.com/api/v1/agents" \
  -H "Authorization: Bearer clou_1234567890abcdefghijklmnopqrstuvwxyz"
```

### API Key Format

API keys follow this format:
```
clou_<64 hexadecimal characters>
```

The key is generated from 32 random bytes (`secrets.token_hex(32)`), so the full key is 68 characters long including the `clou_` prefix.

Example: `clou_a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4e5f67890`

### API Key Scopes

The `scopes` field is stored on the key (default `["chat"]`) but is **not** used for authorization checks. Access control for API-key-authenticated requests is enforced through:

- **User roles/permissions**: the key authenticates as its owning user, whose role permissions govern what the user can do
- **`agent_ids` / `workflow_ids` associations**: the key can optionally be restricted to specific agents and workflows. If no agents/workflows are associated, the key may access all agents/workflows the owning user can reach; if associations exist, access to any other agent/workflow is denied

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Key name (1-100 chars) |
| `scopes` | string[] | Stored, not enforced; defaults to `["chat"]` |
| `rate_limit` | integer | Stored on the key (default 1000 per minute, 0 = unlimited); not enforced by middleware |
| `expires_at` | datetime \| null | Optional expiration |
| `agent_ids` | UUID[] | Agents this key may access (empty = all) |
| `workflow_ids` | UUID[] | Workflows this key may access (empty = all) |

### API Key Expiration

**Setting expiration:**
```json
{
  "expires_at": "2027-12-31T23:59:59Z"
}
```

**No expiration:**
```json
{
  "expires_at": null
}
```

**Expired key response:**
```json
{
  "code": 2002,
  "data": null,
  "msg": "API key expired"
}
```

## Authentication Errors

### Common Error Codes

| Code | HTTP Status | Message | Description |
|------|-------------|---------|-------------|
| `2000` | 401 | Unauthorized | No authentication provided |
| `2001` | 401 | Invalid token | Malformed/revoked token or invalid API key |
| `2002` | 401 | Token expired | **API key** expired |
| `2003` | 403 | Invalid credentials | Wrong username/password, or JWT expired/invalid |
| `2004` | 401 | Inactive user | User account deactivated or pending approval |
| `5300` | 403 | Account locked | Too many failed login attempts |

### Error Response Format

```json
{
  "code": 2000,
  "data": null,
  "msg": "Not authenticated"
}
```

### Handling Authentication Errors

**401/403 Unauthorized:**
```python
response = requests.get(url, headers=headers)

if response.status_code in (401, 403):
    data = response.json()
    if data['code'] == 2002:
        # API key expired - create a new key
        pass
    elif data['code'] == 2003:
        # JWT invalid/expired - login again
        login_again()
    elif data['code'] in (2000, 2001):
        # No auth provided / invalid token, check header
        pass
```

## Security Best Practices

### JWT Tokens

**✅ Do:**
- Store tokens securely (encrypted storage)
- Use HTTPS for all API requests
- Re-authenticate (login again) before tokens expire — there is no refresh endpoint
- Clear tokens on logout
- Set appropriate token lifetime

**❌ Don't:**
- Store tokens in localStorage (XSS risk)
- Share tokens between users
- Log tokens in plain text
- Use tokens in URL parameters
- Hardcode tokens in source code

### API Keys

**✅ Do:**
- Store keys in environment variables
- Use minimal required scopes
- Set expiration dates
- Rotate keys regularly
- Monitor key usage
- Revoke unused keys

**❌ Don't:**
- Commit keys to version control
- Share keys publicly
- Use same key for multiple applications
- Grant `*` scope unless necessary
- Leave keys without expiration

### Rate Limiting

There is no per-endpoint or per-key request throttling middleware, and no `X-RateLimit-*` response headers. The `rate_limit` field on an API key is stored for informational purposes but is not enforced.

Rate limiting exists only for specific security-sensitive flows:

- **Login attempts**: account lockout after failed attempts (default 5 attempts within a 15-minute window)
- **TOTP verification**: temporary lockout after repeated failures
- **Email sending**: a quota of 100 emails/hour; exceeding it returns code `5400`
- **Model provider rate limits**: provider HTTP 429 errors are mapped to code `5400` during knowledge-base processing

See [Rate Limiting](./rate-limiting.md) for details.

## Code Examples

### Python

**JWT Authentication:**
```python
import requests

# Login
response = requests.post(
    "https://your-domain.com/api/v1/login/access-token",
    data={
        "username": "your_username",
        "password": "your_password"
    }
)

data = response.json()
token = data['data']['access_token']

# Use token
headers = {
    "Authorization": f"Bearer {token}"
}

response = requests.get(
    "https://your-domain.com/api/v1/users/me",
    headers=headers
)
```

**API Key Authentication:**
```python
import requests
import os

# Load API key from environment
api_key = os.getenv("CLOUISLE_API_KEY")

headers = {
    "Authorization": f"Bearer {api_key}"
}

response = requests.get(
    "https://your-domain.com/api/v1/agents",
    headers=headers
)
```

### JavaScript

**JWT Authentication:**
```javascript
// Login
const response = await fetch(
  'https://your-domain.com/api/v1/login/access-token',
  {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: new URLSearchParams({
      username: 'your_username',
      password: 'your_password',
    }),
  }
);

const data = await response.json();
const token = data.data.access_token;

// Use token
const userResponse = await fetch(
  'https://your-domain.com/api/v1/users/me',
  {
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  }
);
```

**API Key Authentication:**
```javascript
const apiKey = process.env.CLOUISLE_API_KEY;

const response = await fetch(
  'https://your-domain.com/api/v1/agents',
  {
    headers: {
      'Authorization': `Bearer ${apiKey}`,
    },
  }
);
```

### cURL

**JWT Authentication:**
```bash
# Login
TOKEN=$(curl -s -X POST "https://your-domain.com/api/v1/login/access-token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=your_username&password=your_password" \
  | jq -r '.data.access_token')

# Use token
curl -X GET "https://your-domain.com/api/v1/users/me" \
  -H "Authorization: Bearer $TOKEN"
```

**API Key Authentication:**
```bash
# Set API key
export CLOUISLE_API_KEY="clou_your_api_key_here"

# Use API key
curl -X GET "https://your-domain.com/api/v1/agents" \
  -H "Authorization: Bearer $CLOUISLE_API_KEY"
```

## Testing Authentication

### Test JWT Token

```bash
# Get token
curl -X POST "https://your-domain.com/api/v1/login/access-token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=test&password=test123"

# Test token
curl -X GET "https://your-domain.com/api/v1/users/me" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Test API Key

```bash
# Test API key
curl -X GET "https://your-domain.com/api/v1/agents" \
  -H "Authorization: Bearer clou_your_api_key"
```

### Verify Access Control

Access control for API keys is based on the owning user's role permissions plus the key's agent/workflow associations:

```bash
# This should succeed (if the owning user can read agents)
curl -X GET "https://your-domain.com/api/v1/agents" \
  -H "Authorization: Bearer YOUR_API_KEY"

# This succeeds only if the key is associated with this agent,
# or is associated with no agents at all
curl -X POST "https://your-domain.com/api/v1/agents/{agent_id}/chat" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello"}'
```

## Related Documentation

- [API Overview](./overview.md) - API introduction
- [Response Format](./response-format.md) - Response structure
- [Error Codes](./error-codes.md) - Complete error reference
- [Rate Limiting](./rate-limiting.md) - Rate limit details
- [API Keys Management](../user-guide/api-keys/managing-api-keys.md) - User guide

---

**Last Updated**: 2026-02-11
