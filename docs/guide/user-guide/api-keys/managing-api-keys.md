# Managing API Keys

This guide explains how to create and manage API keys for programmatic access to Clouisle.

## Overview

API keys allow you to:

- **Authenticate API requests**: Access Clouisle API programmatically
- **Automate workflows**: Build integrations and automations
- **Control access**: Grant specific permissions via scopes
- **Monitor usage**: Track API key usage and activity
- **Secure access**: Revoke keys when needed

## Understanding API Keys

### What are API Keys?

API keys are authentication tokens that allow applications to access the Clouisle API without requiring user login.

**Key characteristics:**
- **Long-lived**: Don't expire unless you set an expiration date
- **Scoped**: Limited to specific permissions
- **Revocable**: Can be disabled at any time
- **Trackable**: Usage is logged and monitored

**Format:**
```
clou_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8
```

### API Keys vs JWT Tokens

| Feature | API Keys | JWT Tokens |
|---------|----------|------------|
| **Lifetime** | Long-lived (days/months) | Short-lived (30 minutes) |
| **Use Case** | Programmatic access | User sessions |
| **Revocation** | Manual | Automatic expiration |
| **Scopes** | Configurable | Based on user permissions |
| **Best For** | Integrations, scripts | Web/mobile apps |

## Accessing API Keys

### From Profile Settings

**Steps:**

1. Click your **profile icon** in top-right corner
2. Select **"Profile Settings"** or **"Settings"**
3. Navigate to **"API Keys"** tab
4. View all your API keys

**Or:**

- Navigate directly to `/settings/api-keys`

### API Keys List

**List view:**
```
┌─────────────────────────────────────────────────────┐
│ API Keys                              [+ Create Key] │
├─────────────────────────────────────────────────────┤
│                                                     │
│ 🔑 Production API Key                               │
│    clou_1234...                                     │
│    Created: 2026-01-15                              │
│    Last used: 2 hours ago                           │
│    Expires: Never                                   │
│    Scopes: agent:read, agent:chat, kb:read          │
│    [View Details] [Revoke]                          │
│                                                     │
│ 🔑 Development API Key                              │
│    clou_5678...                                     │
│    Created: 2026-02-01                              │
│    Last used: Never                                 │
│    Expires: 2026-12-31                              │
│    Scopes: agent:read                               │
│    [View Details] [Revoke]                          │
│                                                     │
│ 🔑 Testing API Key (Revoked)                        │
│    clou_9012...                                     │
│    Created: 2025-12-01                              │
│    Revoked: 2026-01-15                              │
│    [Delete]                                         │
│                                                     │
└─────────────────────────────────────────────────────┘
```

## Creating API Keys

### Create New Key

**Steps:**

1. Go to **API Keys** section
2. Click **"+ Create Key"** button
3. Fill in the form:
   - **Name**: Descriptive name for the key
   - **Scopes**: Select permissions (see Scopes section)
   - **Expiration**: Set expiry date (optional)
   - **Rate Limit**: Custom rate limit (optional, admin only)
4. Click **"Create Key"**
5. **Copy the key immediately** (shown only once)
6. Store the key securely

**Create key form:**
```
┌─────────────────────────────────────────┐
│ Create API Key                          │
├─────────────────────────────────────────┤
│                                         │
│ Name: *                                 │
│ [Production API Key____________]        │
│                                         │
│ Description: (optional)                 │
│ [Used for production integrations]      │
│                                         │
│ Scopes: *                               │
│ ☑ agent:read                            │
│ ☑ agent:chat                            │
│ ☑ kb:read                               │
│ ☐ agent:create                          │
│ ☐ agent:update                          │
│ ☐ agent:delete                          │
│                                         │
│ Expiration:                             │
│ ○ Never                                 │
│ ● Custom date: [2027-12-31_____]        │
│                                         │
│ [Cancel]  [Create Key]                  │
│                                         │
└─────────────────────────────────────────┘
```

### Key Created Successfully

**After creation:**
```
┌─────────────────────────────────────────┐
│ ✅ API Key Created Successfully          │
├─────────────────────────────────────────┤
│                                         │
│ Your API key has been created.          │
│                                         │
│ ⚠️ IMPORTANT: Copy this key now.        │
│ You won't be able to see it again.     │
│                                         │
│ clou_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6  │
│                                         │
│ [Copy to Clipboard]                     │
│                                         │
│ Store this key securely:                │
│ • Don't commit to version control       │
│ • Use environment variables             │
│ • Don't share publicly                  │
│                                         │
│ [I've Saved the Key]                    │
│                                         │
└─────────────────────────────────────────┘
```

**⚠️ Critical**: The full API key is only shown once. If you lose it, you must create a new key.

## API Key Scopes

### Available Scopes

Scopes control what the API key can access:

| Scope | Description |
|-------|-------------|
| `agent:read` | View agents |
| `agent:create` | Create agents |
| `agent:update` | Update agents |
| `agent:delete` | Delete agents |
| `agent:chat` | Chat with agents |
| `workflow:read` | View workflows |
| `workflow:run` | Execute workflows |
| `kb:read` | View knowledge bases |
| `kb:create` | Create knowledge bases |
| `kb:update` | Update knowledge bases |
| `kb:delete` | Delete knowledge bases |
| `team:read` | View team information |
| `user:read` | View user information |
| `*` | All permissions (use with caution) |

### Scope Examples

**Read-only access:**
```json
{
  "scopes": ["agent:read", "workflow:read", "kb:read"]
}
```

**Chat-only access:**
```json
{
  "scopes": ["agent:read", "agent:chat"]
}
```

**Full agent management:**
```json
{
  "scopes": [
    "agent:read",
    "agent:create",
    "agent:update",
    "agent:delete",
    "agent:chat"
  ]
}
```

**Workflow execution:**
```json
{
  "scopes": ["workflow:read", "workflow:run"]
}
```

### Principle of Least Privilege

**Best practice**: Grant only the minimum scopes needed.

**✅ Good:**
```
Use Case: Chat integration
Scopes: agent:read, agent:chat
```

**❌ Bad:**
```
Use Case: Chat integration
Scopes: * (all permissions)
```

## Using API Keys

### Making API Requests

**Include the API key in the `Authorization` header:**

```bash
curl -X GET "https://your-domain.com/api/v1/agents" \
  -H "Authorization: Bearer clou_your_api_key_here"
```

### Code Examples

**Python:**
```python
import requests
import os

# Load API key from environment variable
api_key = os.getenv("CLOUISLE_API_KEY")

headers = {
    "Authorization": f"Bearer {api_key}"
}

response = requests.get(
    "https://your-domain.com/api/v1/agents",
    headers=headers
)

data = response.json()
print(data)
```

**JavaScript:**
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

const data = await response.json();
console.log(data);
```

**cURL:**
```bash
# Set API key as environment variable
export CLOUISLE_API_KEY="clou_your_api_key_here"

# Use in requests
curl -X GET "https://your-domain.com/api/v1/agents" \
  -H "Authorization: Bearer $CLOUISLE_API_KEY"
```

## Managing API Keys

### Viewing Key Details

**Steps:**

1. Go to **API Keys** section
2. Click **"View Details"** on a key
3. View key information:
   - Name and description
   - Prefix (first 9 characters)
   - Scopes
   - Creation date
   - Last used date
   - Expiration date
   - Usage statistics

**Key details:**
```
┌─────────────────────────────────────────┐
│ API Key Details                         │
├─────────────────────────────────────────┤
│                                         │
│ Name: Production API Key                │
│ Prefix: clou_1234                       │
│                                         │
│ Created: 2026-01-15 10:00:00            │
│ Last Used: 2026-02-11 14:30:00          │
│ Expires: Never                          │
│                                         │
│ Scopes:                                 │
│ • agent:read                            │
│ • agent:chat                            │
│ • kb:read                               │
│                                         │
│ Usage (Last 30 Days):                   │
│ • Total Requests: 12,345                │
│ • Success Rate: 99.2%                   │
│ • Avg Response Time: 234ms              │
│                                         │
│ [Edit] [Revoke] [Close]                 │
│                                         │
└─────────────────────────────────────────┘
```

### Editing API Keys

**What you can edit:**
- Name
- Description
- Scopes (can only add, not remove)
- Expiration date

**What you cannot edit:**
- The key itself
- Creation date
- Usage history

**Steps:**

1. Click **"Edit"** on a key
2. Update editable fields
3. Click **"Save Changes"**

**Note**: To change scopes that require removal, create a new key and revoke the old one.

### Revoking API Keys

**When to revoke:**
- Key is compromised
- Key is no longer needed
- Replacing with new key
- Employee/contractor leaves
- Security incident

**Steps:**

1. Go to **API Keys** section
2. Click **"Revoke"** on the key
3. Confirm revocation
4. Key is immediately disabled

**Revoke confirmation:**
```
┌─────────────────────────────────────────┐
│ ⚠️ Revoke API Key?                      │
├─────────────────────────────────────────┤
│                                         │
│ Are you sure you want to revoke this    │
│ API key?                                │
│                                         │
│ Key: clou_1234...                       │
│ Name: Production API Key                │
│                                         │
│ This action cannot be undone.           │
│                                         │
│ All requests using this key will fail   │
│ immediately.                            │
│                                         │
│ [Cancel]  [Revoke Key]                  │
│                                         │
└─────────────────────────────────────────┘
```

**After revocation:**
- Key is immediately disabled
- All API requests with this key will fail
- Key remains in list as "Revoked"
- Usage history is preserved
- Can be permanently deleted later

### Deleting API Keys

**Difference from revoking:**
- **Revoke**: Disables key, keeps history
- **Delete**: Permanently removes key and history

**Steps:**

1. Revoke the key first (if not already revoked)
2. Click **"Delete"** on the revoked key
3. Confirm deletion
4. Key is permanently removed

**Note**: Only revoked keys can be deleted.

## API Key Security

### Storing API Keys

**✅ Do:**
- Store in environment variables
- Use secret management services (AWS Secrets Manager, HashiCorp Vault)
- Encrypt keys at rest
- Use different keys for different environments
- Rotate keys regularly

**❌ Don't:**
- Commit keys to version control
- Hardcode keys in source code
- Share keys via email or chat
- Store keys in plain text files
- Use same key across multiple applications

**Example - Environment Variables:**

```bash
# .env file (add to .gitignore)
CLOUISLE_API_KEY=clou_your_api_key_here
CLOUISLE_BASE_URL=https://your-domain.com/api/v1
```

```python
# Load from environment
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("CLOUISLE_API_KEY")
base_url = os.getenv("CLOUISLE_BASE_URL")
```

### Key Rotation

**Best practice**: Rotate API keys regularly (every 90 days).

**Rotation process:**

1. **Create new key** with same scopes
2. **Update applications** to use new key
3. **Test** that new key works
4. **Monitor** for any issues
5. **Revoke old key** after grace period
6. **Delete old key** after verification

**Zero-downtime rotation:**

1. Create new key
2. Update half of your applications
3. Monitor for 24 hours
4. Update remaining applications
5. Wait 7 days
6. Revoke old key

### Monitoring API Key Usage

**What to monitor:**
- Request volume
- Error rates
- Unusual access patterns
- Geographic locations
- Time of day patterns

**Signs of compromise:**
- Sudden spike in requests
- Requests from unexpected locations
- High error rates
- Access to unauthorized resources
- Requests outside normal hours

**Action if compromised:**
1. **Revoke key immediately**
2. **Create new key**
3. **Review audit logs**
4. **Notify security team**
5. **Update applications**
6. **Investigate breach**

## Rate Limits

### Default Limits

API keys are subject to rate limits:

| Tier | Requests/Hour | Requests/Minute |
|------|---------------|-----------------|
| **Default** | 1,000 | 100 |
| **Custom** | Configurable | Configurable |

**Checking rate limits:**

Rate limit information is included in response headers:

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

See [Rate Limiting](../../api-reference/rate-limiting.md) for details.

## Best Practices

### Creating API Keys

**✅ Do:**
- Use descriptive names
- Set expiration dates
- Grant minimum required scopes
- Create separate keys for different applications
- Document key purpose and usage

**❌ Don't:**
- Use generic names like "API Key 1"
- Create keys without expiration
- Grant `*` (all) scope unless necessary
- Share keys between applications
- Create keys without documenting

### Using API Keys

**✅ Do:**
- Store keys securely
- Use environment variables
- Implement error handling
- Monitor usage
- Rotate keys regularly
- Revoke unused keys

**❌ Don't:**
- Hardcode keys in code
- Commit keys to version control
- Share keys publicly
- Ignore rate limits
- Keep unused keys active
- Use same key everywhere

### Security

**✅ Do:**
- Treat keys like passwords
- Use HTTPS for all requests
- Implement key rotation
- Monitor for suspicious activity
- Revoke compromised keys immediately
- Use different keys per environment

**❌ Don't:**
- Share keys via insecure channels
- Use keys on untrusted networks
- Ignore security alerts
- Reuse revoked keys
- Store keys in client-side code

## Troubleshooting

### API Key Not Working

**Problem**: Requests fail with authentication error

**Solutions:**
1. Verify key is not revoked
2. Check key hasn't expired
3. Ensure key has required scopes
4. Verify `Authorization` header format
5. Check for typos in key
6. Try creating a new key

### Rate Limit Exceeded

**Problem**: Getting 429 errors

**Solutions:**
1. Check rate limit headers
2. Implement exponential backoff
3. Reduce request frequency
4. Use caching
5. Request higher rate limit
6. Create multiple keys for different services

### Key Compromised

**Problem**: Suspect key has been exposed

**Solutions:**
1. **Revoke key immediately**
2. Create new key
3. Update all applications
4. Review audit logs
5. Check for unauthorized access
6. Notify security team

### Cannot Create Key

**Problem**: Create button is disabled or fails

**Solutions:**
1. Check if you have permission
2. Verify you haven't reached key limit
3. Check if organization allows API keys
4. Contact administrator
5. Try different browser

## Related Documentation

- [API Overview](../../api-reference/overview.md) - API introduction
- [Authentication](../../api-reference/authentication.md) - Authentication methods
- [API Key Scopes](./api-key-scopes.md) - Detailed scope reference
- [Rate Limiting](../../api-reference/rate-limiting.md) - Rate limit details
- [Security Best Practices](../../best-practices/security.md) - Security guidelines

## Getting Help

If you need assistance with API keys:

1. **Documentation**: Review this guide
2. **API Reference**: Check API documentation
3. **Support**: Contact your organization's support team
4. **Administrator**: Reach out to your Clouisle administrator

---

**Last Updated**: 2026-02-11
