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
    "token_type": "bearer",
    "expires_in": 1800
  },
  "msg": "Login successful"
}
```

### Using the Token

Include the token in the `Authorization` header:

```bash
curl -X GET "https://your-domain.com/api/v1/users/me" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

### Token Expiration

- **Default lifetime**: 30 minutes
- **Refresh**: Login again to get a new token
- **Expired token**: Returns `401 Unauthorized` with code `2002`

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
   - Scopes (permissions)
   - Expiration date (optional)
   - Rate limit (optional)
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
    "expires_at": "2027-12-31T23:59:59Z"
  }'
```

**Response:**
```json
{
  "code": 0,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "key": "clou_1234567890abcdefghijklmnopqrstuvwxyz",
    "prefix": "clou_1234",
    "name": "Production API Key",
    "scopes": ["agent:read", "agent:chat", "kb:read"],
    "created_at": "2026-02-11T10:00:00Z",
    "expires_at": "2027-12-31T23:59:59Z"
  },
  "msg": "API key created successfully"
}
```

**⚠️ Important**: The full API key is only shown once. Store it securely.

### Using an API Key

Include the API key in the `Authorization` header with `Bearer` prefix:

```bash
curl -X GET "https://your-domain.com/api/v1/agents" \
  -H "Authorization: Bearer clou_1234567890abcdefghijklmnopqrstuvwxyz"
```

### API Key Format

API keys follow this format:
```
clou_[40 random characters]
```

Example: `clou_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8`

### API Key Scopes

Scopes control what the API key can access:

| Scope | Description |
|-------|-------------|
| `agent:read` | Read agents |
| `agent:create` | Create agents |
| `agent:update` | Update agents |
| `agent:delete` | Delete agents |
| `agent:chat` | Chat with agents |
| `workflow:read` | Read workflows |
| `workflow:run` | Execute workflows |
| `kb:read` | Read knowledge bases |
| `kb:create` | Create knowledge bases |
| `kb:update` | Update knowledge bases |
| `*` | All permissions (use with caution) |

**Example - Read-only access:**
```json
{
  "scopes": ["agent:read", "workflow:read", "kb:read"]
}
```

**Example - Chat-only access:**
```json
{
  "scopes": ["agent:read", "agent:chat"]
}
```

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

| Code | Message | Description |
|------|---------|-------------|
| `2000` | Unauthorized | No authentication provided |
| `2001` | Invalid credentials | Wrong username/password |
| `2002` | Token expired | JWT token or API key expired |
| `2003` | Invalid token | Malformed or invalid token |
| `2004` | Account inactive | User account deactivated |
| `2005` | Account locked | Too many failed login attempts |

### Error Response Format

```json
{
  "code": 2000,
  "data": null,
  "msg": "Unauthorized: Authentication required"
}
```

### Handling Authentication Errors

**401 Unauthorized:**
```python
response = requests.get(url, headers=headers)

if response.status_code == 401:
    data = response.json()
    if data['code'] == 2002:
        # Token expired, refresh token
        new_token = refresh_token()
        # Retry request
    elif data['code'] == 2000:
        # No auth provided, add auth header
        pass
```

## Security Best Practices

### JWT Tokens

**✅ Do:**
- Store tokens securely (encrypted storage)
- Use HTTPS for all API requests
- Implement token refresh logic
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

API keys are subject to rate limits:

**Default limits:**
- 1000 requests per hour per key
- 100 requests per minute per key

**Rate limit headers:**
```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1644580800
```

**Rate limit exceeded:**
```json
{
  "code": 5400,
  "data": {
    "retry_after": 3600
  },
  "msg": "Rate limit exceeded. Retry after 3600 seconds"
}
```

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

### Verify Scopes

```bash
# This should succeed (if key has agent:read scope)
curl -X GET "https://your-domain.com/api/v1/agents" \
  -H "Authorization: Bearer YOUR_API_KEY"

# This should fail (if key doesn't have agent:create scope)
curl -X POST "https://your-domain.com/api/v1/agents" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Agent"}'
```

## Related Documentation

- [API Overview](./overview.md) - API introduction
- [Response Format](./response-format.md) - Response structure
- [Error Codes](./error-codes.md) - Complete error reference
- [Rate Limiting](./rate-limiting.md) - Rate limit details
- [API Keys Management](../user-guide/api-keys/managing-api-keys.md) - User guide

---

**Last Updated**: 2026-02-11
