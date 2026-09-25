# API Reference Overview

Welcome to the Clouisle API documentation. This guide provides comprehensive information about the Clouisle REST API, including authentication, request/response formats, error handling, and detailed endpoint documentation.

## Base URL

All API requests should be made to:

```
https://your-domain.com/api/v1
```

For local development:

```
http://localhost:8000/api/v1
```

## Quick Start

### 1. Authentication

Obtain an access token by logging in:

```bash
curl -X POST "https://your-domain.com/api/v1/login/access-token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=your_username&password=your_password"
```

Response:

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

### 2. Make Authenticated Requests

Include the token in the Authorization header:

```bash
curl -X GET "https://your-domain.com/api/v1/users/me" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

## Core Concepts

### Unified Response Format

All API responses follow this structure:

```json
{
  "code": 0,
  "data": { ... },
  "msg": "success"
}
```

- `code`: Response code (0 = success, non-zero = error)
- `data`: Response payload (varies by endpoint)
- `msg`: Human-readable message

See [Response Format](./response-format.md) for details.

## API Sections

Every route below is mounted under `/api/v1`. Paths in parentheses are the mounted prefixes.

### Authentication & Users
- [Authentication](./authentication.md) - Login, logout, registration, and password recovery
- [Login & Registration API](./endpoints/auth.md) - Captcha, login, TOTP challenge, registration, email verification, and password reset (`/login`, `/captcha`, `/register`, `/logout`, ...)
- [Users](./endpoints/users.md) - User management and profile operations (`/users`)
- [API Keys](./endpoints/api-keys.md) - API key lifecycle for programmatic and embed access (`/api-keys`)
- [Two-Factor Authentication](./endpoints/totp.md) - TOTP setup, status, and backup codes (`/totp`)
- [SSO](./endpoints/sso.md) - SSO provider discovery, login flow, and connection management (`/sso`)

### Organization
- [Teams](./endpoints/teams.md) - Team management and member operations (`/teams`)
- [Team Models](./endpoints/team-models.md) - Per-team model authorization, quota limits, and usage (`/teams/{team_id}/models`)
- [Site Settings](./endpoints/settings.md) - Public settings subset plus the admin settings API (`/site-settings/public`, `/admin/site-settings`)

### AI Features
- [Models](./endpoints/models.md) - Model catalog, connection testing, and model discovery (`/models`)
- [Agents](./endpoints/agents.md) - Agent configuration, publishing, conversations, and statistics (`/agents`)
- [Chat](./endpoints/chat.md) - Streaming chat completions and the durable run lifecycle (`/agents/{agent_id}/chat`)
- [Conversations](./endpoints/conversations.md) - Conversation and message statistics (`/conversations/stats`)
- [Prompt Generator](./endpoints/prompts.md) - AI prompt generation and optimization over SSE (`/prompts`)
- [Memories](./endpoints/memories.md) - Memory entities, relations, and the memory graph (`/memories`)

### Workflows
- [Workflows](./endpoints/workflows.md) - Workflow CRUD, publishing, runs, debugging, and webhook triggers (`/workflows`)
- [Workflow Versions](./endpoints/workflow-versions.md) - Version snapshots, history, diff, publish/archive (`/workflows/{workflow_id}/versions`, `/workflow-versions`)

### Knowledge & Tools
- [Knowledge Bases](./endpoints/knowledge-bases.md) - Documents, chunks, search, and cross-team sharing (`/knowledge-bases`)
- [Tools](./endpoints/tools.md) - Tool catalog, custom/MCP/database tools, configuration, and sharing (`/tools`)
- [Skills](./endpoints/skills.md) - Skill listing and ZIP/Git import (`/skills`)
- [Resource Packages](./endpoints/packages.md) - Package export/import and sandbox dependencies (`/packages`)

### Integration
- [Notifications](./endpoints/notifications.md) - In-app notification inbox and admin publishing (`/notifications`)
- [Embed](./endpoints/embed.md) - External iframe embedding authenticated with API keys (`/embed`)

### Admin Console

The admin console is a separate, permission-gated API mounted under `/api/v1/admin`. It is not given dedicated reference pages here; it is documented in the [Admin Guide](../admin-guide/) and uses the same `{code, data, msg}` envelope.

| Group | Prefix |
|---|---|
| Dashboard | `/api/v1/admin/dashboard` |
| Observability | `/api/v1/admin/observability` |
| Audit logs | `/api/v1/admin/audit-logs` |
| Conversations | `/api/v1/admin/conversations` |
| Users | `/api/v1/admin/users` |
| Roles | `/api/v1/admin/roles` |
| Permissions | `/api/v1/admin/permissions` |
| Site settings | `/api/v1/admin/site-settings` |
| Models | `/api/v1/admin/models` |
| SSO | `/api/v1/admin/sso` |
| Notifications | `/api/v1/admin/notifications` |
| Teams | `/api/v1/admin/teams` |
| Memories | `/api/v1/admin/memories` |
| Agents | `/api/v1/admin/agents` |
| Tools | `/api/v1/admin/tools` |
| Skills | `/api/v1/admin/skills` |
| Workflows | `/api/v1/admin/workflows` |
| Workflow metrics | `/api/v1/admin/workflows/metrics` |
| Knowledge bases | `/api/v1/admin/knowledge-bases` |
| Packages | `/api/v1/admin/packages` |
| TOTP | `/api/v1/admin/totp` |

### Advanced Topics
- [SSE Streaming](./sse-streaming.md) - Real-time event streaming
- [WebSocket API](./websocket-api.md) - WebSocket transport
- [Webhooks](./webhooks.md) - Outbound webhook payloads and inbound workflow triggers
- [Rate Limiting](./rate-limiting.md) - API usage limits
- [File Uploads](./file-uploads.md) - Multipart and binary upload conventions
- [Batch Operations](./batch-operations.md) - Multi-resource operations
- [Filtering](./filtering.md), [Sorting](./sorting.md), and [Pagination](./pagination.md) - List query conventions
- [Error Codes](./error-codes.md) and [Error Handling](./error-handling.md) - Error reference and handling
- [API Best Practices](./api-best-practices.md) - Conventions and recipes
- [SDK Examples](./sdk-examples.md) - Language-specific examples
- [Quick Start](./quick-start.md) - End-to-end walkthrough

## Next Steps

- [Authentication Guide](./authentication.md) - Learn about authentication methods
- [Response Format](./response-format.md) - Understand the response structure
- [Error Codes](./error-codes.md) - Reference for all error codes
- [Endpoint Documentation](./endpoints/users.md) - Explore specific endpoints
