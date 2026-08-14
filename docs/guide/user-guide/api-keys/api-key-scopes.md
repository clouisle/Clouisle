# API Key Scopes

This document describes the `scopes` field of API keys in Clouisle.

## Overview

Every API key carries a `scopes` field — a JSON array of strings (for example `["chat"]`). Scopes are **stored metadata only**: the backend records the value you provide, but authentication does **not** read or enforce scopes. There is no fixed scope enumeration, no validation of scope names, and no per-request scope check.

What actually controls an API key's access is:

- **Active state**: the key must be `is_active` and not expired
- **Agent associations**: if the key is associated with specific agents, it can only access those agents; if it has no agent associations, it can access all agents
- **Workflow associations**: same rule as agents — restricted to associated workflows, or all workflows when none are associated
- **User permissions**: the key authenticates as its owner user, so the owner's role permissions apply to all requests

## Default Value

If you do not provide `scopes`, the key is created with the default:

```json
["chat"]
```

## Providing Scopes

When creating or updating a key, `scopes` accepts any JSON array of strings. Examples that will be stored as given:

```json
["agent:read", "agent:chat", "kb:read"]
```

```json
["read", "write"]
```

```json
[]
```

> **Note:** These values are stored and returned by the API but are not enforced by the backend. Do not rely on scopes for access control.

## Update Semantics

Scopes can be replaced freely when updating a key (`PUT /api/v1/api-keys/{id}`) — there is no "only add, never remove" rule, and no separate scope-management endpoint.

## Example Requests

**List knowledge bases (real route):**

```bash
curl -X GET "https://your-domain.com/api/v1/knowledge-bases" \
  -H "Authorization: Bearer clou_<your-api-key>"
```

**Upload a document (real route):**

```bash
curl -X POST "https://your-domain.com/api/v1/knowledge-bases/{kb_id}/documents/upload" \
  -H "Authorization: Bearer clou_<your-api-key>" \
  -F "file=@document.pdf"
```

**Chat with an agent:**

```bash
curl -X POST "https://your-domain.com/api/v1/agents/{id}/chat" \
  -H "Authorization: Bearer clou_<your-api-key>" \
  -d '{"message": "Hello"}'
```

**Workflow execution:**

```bash
curl -X POST "https://your-domain.com/api/v1/workflows/{id}/run" \
  -H "Authorization: Bearer clou_<your-api-key>" \
  -d '{"inputs": {...}}'
```

## Error Codes

When a request fails due to authentication or authorization, the response body uses these codes:

| Code | Meaning |
|------|---------|
| `2001` | Invalid token / invalid API key |
| `2002` | Token expired (including expired API key) |
| `3000` | Permission denied |

> **Note:** A `3000` response means the authenticated user (or the key's agent/workflow association) lacks permission — it does not reflect the `scopes` field.

## What Does NOT Exist

- No `model:read` / `model:use` or `tool:read` / `tool:use` scopes
- No wildcard `*` scope handling
- No scope validation, enumeration, or documentation of accepted scope names
- No scope-required error payload with `required_scope` / `provided_scopes`

## Related Documentation

- [Managing API Keys](./managing-api-keys.md) - Create and manage API keys

---

**Last Updated**: 2026-02-11
