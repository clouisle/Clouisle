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

### Authentication & Users
- [Authentication](./authentication.md) - Login, logout, registration, password reset
- [Users](./endpoints/users.md) - User management and profile operations

### Organization
- [Teams](./endpoints/teams.md) - Team management and member operations

### AI Features
- [Agents](./endpoints/agents.md) - AI agent configuration and management
- [Chat](./endpoints/chat.md) - Conversational AI interactions
- [Workflows](./endpoints/workflows.md) - Workflow automation and execution

### Knowledge Management
- [Knowledge Bases](./endpoints/knowledge-bases.md) - Document storage and retrieval

### Advanced Topics
- [SSE Streaming](./sse-streaming.md) - Real-time event streaming
- [Webhooks](./webhooks.md) - Webhook integration
- [Rate Limiting](./rate-limiting.md) - API usage limits

## Next Steps

- [Authentication Guide](./authentication.md) - Learn about authentication methods
- [Response Format](./response-format.md) - Understand the response structure
- [Error Codes](./error-codes.md) - Reference for all error codes
- [Endpoint Documentation](./endpoints/users.md) - Explore specific endpoints
