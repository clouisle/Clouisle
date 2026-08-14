# Managing API Keys

This guide explains how to create and manage API keys for programmatic access to Clouisle.

## Overview

API keys allow you to:

- **Authenticate API requests**: Access the Clouisle API programmatically
- **Automate workflows**: Build integrations and automations
- **Restrict access**: Bind a key to specific agents and workflows
- **Revoke access**: Deactivate or delete keys when needed

## Understanding API Keys

### What are API Keys?

API keys are authentication tokens that let applications access the Clouisle API without a user login session. A key authenticates as its owner user, so the owner's role permissions apply to every request.

**Key characteristics:**
- **Long-lived**: Don't expire unless you set an expiration date
- **Bound**: Can be limited to specific agents and workflows
- **Revocable**: Can be deactivated at any time
- **Shown once**: The full key is only displayed at creation

**Format:**
```
clou_<64 hexadecimal characters>
```

The key is generated as 64 random hex characters (32 bytes) prefixed with `clou_`. Only the first 12 characters (`key_prefix`) are stored in plaintext and shown in listings; the full key is hashed.

### API Keys vs JWT Tokens

| Feature | API Keys | JWT Tokens |
|---------|----------|------------|
| **Lifetime** | Long-lived (days/months) | Session-based (default 30 days) |
| **Use Case** | Programmatic access | User sessions |
| **Revocation** | Manual deactivate/delete | Automatic expiration |
| **Access control** | User permissions + agent/workflow bindings | User permissions |

## Accessing API Keys

### From the Platform

1. Click your **profile icon** in the top-right corner
2. Select **"API Keys"** from the user menu
3. Or navigate directly to `/app/api-keys`

### API Keys List

The list shows each key's name, `key_prefix` (first 12 characters), status (active / inactive / expired), expiration date, last-used time, and its agent/workflow bindings. Admins can filter by status, search by name or prefix, and see all keys; regular users only see their own keys.

## Creating API Keys

### Create New Key

**Steps:**

1. Go to **API Keys** (`/app/api-keys`)
2. Click **"+ Create Key"** button
3. Fill in the form:
   - **Name**: Descriptive name (required, max 100 chars)
   - **Expiration**: Optional expiry date
   - **Rate Limit**: Optional per-minute limit (0 = unlimited; default 1000) — any user with `apikey:create` can set it
   - **Agents**: Optional list of agents this key can access
   - **Workflows**: Optional list of workflows this key can access
4. Click **"Create Key"**
5. **Copy the key immediately** (shown only once; the stored hash cannot be reversed)

**Server defaults:** If not specified, `scopes` defaults to `["chat"]` and `rate_limit` to `1000`.

### Key Created Successfully

**⚠️ Critical**: The full API key is only shown once. If you lose it, you must create a new key.

## Editing API Keys

**What you can edit (via `PUT /api/v1/api-keys/{id}`):**
- Name
- Scopes (replaced freely; there is no add-only rule)
- Rate limit
- Expiration date
- Active state (`is_active`)
- Agent / workflow bindings

**What you cannot edit:**
- The key itself (there is no rotation endpoint)

## Deactivating / Reactivating API Keys

Deactivation (revoke) disables the key immediately without deleting it:

- `POST /api/v1/api-keys/{id}/deactivate`
- `POST /api/v1/api-keys/{id}/activate` (re-enable)

## Deleting API Keys

`DELETE /api/v1/api-keys/{id}` permanently removes the key. There is no rule requiring the key to be revoked first.

## Using API Keys

**Include the API key in the `Authorization` header:**

```bash
curl -X GET "https://your-domain.com/api/v1/agents" \
  -H "Authorization: Bearer clou_your_api_key_here"
```

**Python:**
```python
import requests

api_key = "clou_your_api_key_here"

response = requests.get(
    "https://your-domain.com/api/v1/agents",
    headers={"Authorization": f"Bearer {api_key}"},
)
```

**Access rules:**
- The key must be active and unexpired
- If the key is bound to agents, only those agents are accessible; with no agent bindings, all agents are accessible
- If the key is bound to workflows, only those workflows can be run; with no workflow bindings, all workflows are accessible
- The owner user's role permissions apply to all requests

## Stats

`GET /api/v1/api-keys/stats` returns key statistics (total, active, inactive, expired) for the current user (or all users for admins).

## Rate Limits

`rate_limit` is stored per key (requests per minute; 0 = unlimited; default 1000) and can be set by any user with `apikey:create`. It is **not enforced** by the backend, and no `X-RateLimit-*` response headers are emitted.

## Best Practices

**✅ Do:**
- Use descriptive names
- Set expiration dates
- Bind keys to the specific agents/workflows they need
- Store keys in environment variables or a secret manager
- Deactivate unused keys

**❌ Don't:**
- Commit keys to version control
- Share keys publicly
- Keep unused keys active

## Troubleshooting

### API Key Not Working

**Problem**: Requests fail with authentication error

**Solutions:**
1. Verify the key is active (`is_active`) and not expired
2. Check the `Authorization` header format: `Bearer clou_...`
3. Check for typos — only the first 12 characters are shown after creation
4. Verify the key is allowed to access the target agent/workflow
5. Create a new key if the full key was lost

### Key Compromised

**Problem**: Suspect key has been exposed

**Solutions:**
1. **Deactivate the key immediately**
2. Create a new key and update your applications
3. Review audit logs

## Related Documentation

- [API Key Scopes](./api-key-scopes.md) - The `scopes` field
- [API Reference](../../api-reference/overview.md) - API introduction

---

**Last Updated**: 2026-02-11
