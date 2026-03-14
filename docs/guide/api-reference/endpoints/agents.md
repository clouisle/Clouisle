# Agents API

This document describes the API endpoints for managing and interacting with AI agents.

## Overview

The Agents API allows you to:

- **List agents**: Get all available agents
- **Get agent details**: Retrieve agent information
- **Create agents**: Create new AI agents (admin only)
- **Update agents**: Modify agent configuration (admin only)
- **Delete agents**: Remove agents (admin only)
- **Chat with agents**: Send messages and receive responses
- **Publish/unpublish agents**: Control agent visibility

**Base URL**: `/api/v1/agents`

## Authentication

All endpoints require authentication via JWT token or API key.

**Required scopes:**
- `agent:read` - List and view agents
- `agent:create` - Create agents
- `agent:update` - Update agents
- `agent:delete` - Delete agents
- `agent:chat` - Chat with agents

## List Agents

Get a list of all agents you have access to.

### Endpoint

```
GET /api/v1/agents
```

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `page` | integer | No | 1 | Page number |
| `page_size` | integer | No | 20 | Items per page (max: 100) |
| `team_id` | string | No | - | Filter by team ID |
| `status` | string | No | - | Filter by status: `draft`, `published` |
| `search` | string | No | - | Search by name or description |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/agents?page=1&page_size=20" \
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
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "Customer Support Agent",
        "description": "Helps customers with common questions",
        "avatar_url": "https://example.com/avatar.png",
        "status": "published",
        "team_id": "team-123",
        "team_name": "Support Team",
        "model_id": "model-456",
        "model_name": "GPT-4",
        "system_prompt": "You are a helpful customer support agent...",
        "temperature": 0.7,
        "max_tokens": 2000,
        "tools": ["web_search", "calculator"],
        "knowledge_bases": ["kb-789"],
        "rag_mode": "citation",
        "created_at": "2026-02-11T10:00:00Z",
        "updated_at": "2026-02-11T15:30:00Z",
        "created_by": "user-001",
        "is_public": true
      }
    ],
    "total": 42,
    "page": 1,
    "page_size": 20,
    "total_pages": 3
  },
  "msg": "success"
}
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Agent UUID |
| `name` | string | Agent name |
| `description` | string | Agent description |
| `avatar_url` | string | Agent avatar URL |
| `status` | string | `draft` or `published` |
| `team_id` | string | Team UUID |
| `team_name` | string | Team name |
| `model_id` | string | LLM model UUID |
| `model_name` | string | LLM model name |
| `system_prompt` | string | System prompt/instructions |
| `temperature` | float | Temperature (0.0-2.0) |
| `max_tokens` | integer | Maximum response tokens |
| `tools` | array | Enabled tool names |
| `knowledge_bases` | array | Connected KB IDs |
| `rag_mode` | string | RAG mode: `disabled`, `citation`, `rewrite` |
| `created_at` | string | ISO 8601 timestamp |
| `updated_at` | string | ISO 8601 timestamp |
| `created_by` | string | Creator user ID |
| `is_public` | boolean | Public visibility |

## Get Agent

Get details of a specific agent.

### Endpoint

```
GET /api/v1/agents/{agent_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `agent_id` | string | Yes | Agent UUID |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/agents/550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Customer Support Agent",
    "description": "Helps customers with common questions",
    "avatar_url": "https://example.com/avatar.png",
    "status": "published",
    "team_id": "team-123",
    "team_name": "Support Team",
    "model_id": "model-456",
    "model_name": "GPT-4",
    "system_prompt": "You are a helpful customer support agent...",
    "temperature": 0.7,
    "max_tokens": 2000,
    "top_p": 0.9,
    "frequency_penalty": 0.0,
    "presence_penalty": 0.0,
    "tools": ["web_search", "calculator"],
    "knowledge_bases": [
      {
        "id": "kb-789",
        "name": "Product Documentation",
        "description": "Product docs and FAQs"
      }
    ],
    "rag_mode": "citation",
    "rag_config": {
      "top_k": 5,
      "score_threshold": 0.7,
      "rerank": true
    },
    "created_at": "2026-02-11T10:00:00Z",
    "updated_at": "2026-02-11T15:30:00Z",
    "created_by": "user-001",
    "is_public": true,
    "stats": {
      "total_conversations": 156,
      "total_messages": 1234,
      "avg_response_time": 2.3
    }
  },
  "msg": "success"
}
```

**Error (404 Not Found):**

```json
{
  "code": 6200,
  "data": {
    "agent_id": "550e8400-e29b-41d4-a716-446655440000"
  },
  "msg": "Agent not found"
}
```

## Create Agent

Create a new AI agent.

### Endpoint

```
POST /api/v1/agents
```

### Request Body

```json
{
  "name": "Customer Support Agent",
  "description": "Helps customers with common questions",
  "avatar_url": "https://example.com/avatar.png",
  "team_id": "team-123",
  "model_id": "model-456",
  "system_prompt": "You are a helpful customer support agent...",
  "temperature": 0.7,
  "max_tokens": 2000,
  "top_p": 0.9,
  "frequency_penalty": 0.0,
  "presence_penalty": 0.0,
  "tools": ["web_search", "calculator"],
  "knowledge_bases": ["kb-789"],
  "rag_mode": "citation",
  "rag_config": {
    "top_k": 5,
    "score_threshold": 0.7,
    "rerank": true
  },
  "is_public": false
}
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Agent name (max 100 chars) |
| `description` | string | No | Agent description (max 500 chars) |
| `avatar_url` | string | No | Agent avatar URL |
| `team_id` | string | Yes | Team UUID |
| `model_id` | string | Yes | LLM model UUID |
| `system_prompt` | string | Yes | System prompt/instructions |
| `temperature` | float | No | Temperature (0.0-2.0, default: 0.7) |
| `max_tokens` | integer | No | Max response tokens (default: 2000) |
| `top_p` | float | No | Top-p sampling (0.0-1.0, default: 0.9) |
| `frequency_penalty` | float | No | Frequency penalty (0.0-2.0, default: 0.0) |
| `presence_penalty` | float | No | Presence penalty (0.0-2.0, default: 0.0) |
| `tools` | array | No | Tool names to enable |
| `knowledge_bases` | array | No | KB IDs to connect |
| `rag_mode` | string | No | RAG mode: `disabled`, `citation`, `rewrite` |
| `rag_config` | object | No | RAG configuration |
| `is_public` | boolean | No | Public visibility (default: false) |

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/agents" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Customer Support Agent",
    "description": "Helps customers with common questions",
    "team_id": "team-123",
    "model_id": "model-456",
    "system_prompt": "You are a helpful customer support agent...",
    "temperature": 0.7,
    "tools": ["web_search"],
    "knowledge_bases": ["kb-789"],
    "rag_mode": "citation"
  }'
```

### Response

**Success (201 Created):**

```json
{
  "code": 0,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Customer Support Agent",
    "description": "Helps customers with common questions",
    "status": "draft",
    "team_id": "team-123",
    "model_id": "model-456",
    "created_at": "2026-02-11T10:00:00Z",
    "created_by": "user-001"
  },
  "msg": "Agent created successfully"
}
```

**Error (1001 Validation Error):**

```json
{
  "code": 1001,
  "data": {
    "errors": [
      {
        "field": "name",
        "message": "Name is required"
      },
      {
        "field": "model_id",
        "message": "Invalid model ID"
      }
    ]
  },
  "msg": "Validation failed"
}
```

## Update Agent

Update an existing agent.

### Endpoint

```
PATCH /api/v1/agents/{agent_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `agent_id` | string | Yes | Agent UUID |

### Request Body

All fields are optional. Only include fields you want to update.

```json
{
  "name": "Updated Agent Name",
  "description": "Updated description",
  "system_prompt": "Updated system prompt...",
  "temperature": 0.8,
  "tools": ["web_search", "calculator", "code_interpreter"],
  "rag_mode": "rewrite"
}
```

### Request Example

```bash
curl -X PATCH "https://your-domain.com/api/v1/agents/550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Updated Agent Name",
    "temperature": 0.8
  }'
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Updated Agent Name",
    "temperature": 0.8,
    "updated_at": "2026-02-11T16:00:00Z"
  },
  "msg": "Agent updated successfully"
}
```

## Delete Agent

Delete an agent permanently.

### Endpoint

```
DELETE /api/v1/agents/{agent_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `agent_id` | string | Yes | Agent UUID |

### Request Example

```bash
curl -X DELETE "https://your-domain.com/api/v1/agents/550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": null,
  "msg": "Agent deleted successfully"
}
```

**Error (6200 Not Found):**

```json
{
  "code": 6200,
  "data": {
    "agent_id": "550e8400-e29b-41d4-a716-446655440000"
  },
  "msg": "Agent not found"
}
```

## Publish Agent

Publish an agent to make it available for use.

### Endpoint

```
POST /api/v1/agents/{agent_id}/publish
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `agent_id` | string | Yes | Agent UUID |

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/agents/550e8400-e29b-41d4-a716-446655440000/publish" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "published",
    "published_at": "2026-02-11T16:00:00Z"
  },
  "msg": "Agent published successfully"
}
```

**Error (6201 Not Published):**

```json
{
  "code": 6201,
  "data": null,
  "msg": "Agent is not published"
}
```

## Unpublish Agent

Unpublish an agent to make it unavailable.

### Endpoint

```
POST /api/v1/agents/{agent_id}/unpublish
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `agent_id` | string | Yes | Agent UUID |

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/agents/550e8400-e29b-41d4-a716-446655440000/unpublish" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "draft",
    "unpublished_at": "2026-02-11T16:00:00Z"
  },
  "msg": "Agent unpublished successfully"
}
```

## Chat with Agent

Send a message to an agent and receive a response.

### Endpoint

```
POST /api/v1/agents/{agent_id}/chat
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `agent_id` | string | Yes | Agent UUID |

### Request Body

```json
{
  "message": "What are your business hours?",
  "conversation_id": "conv-123",
  "stream": false,
  "files": [
    {
      "name": "document.pdf",
      "url": "https://example.com/document.pdf",
      "type": "application/pdf"
    }
  ],
  "context": {
    "user_id": "user-456",
    "session_id": "session-789"
  }
}
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `message` | string | Yes | User message |
| `conversation_id` | string | No | Conversation UUID (creates new if not provided) |
| `stream` | boolean | No | Enable streaming (default: false) |
| `files` | array | No | Attached files |
| `context` | object | No | Additional context |

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/agents/550e8400-e29b-41d4-a716-446655440000/chat" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What are your business hours?",
    "conversation_id": "conv-123"
  }'
```

### Response (Non-Streaming)

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "conversation_id": "conv-123",
    "message_id": "msg-456",
    "response": "Our business hours are Monday-Friday, 9 AM to 5 PM EST.",
    "sources": [
      {
        "document_id": "doc-789",
        "document_name": "Business Hours Policy",
        "chunk_id": "chunk-012",
        "content": "Business hours: Monday-Friday, 9 AM to 5 PM EST",
        "score": 0.95
      }
    ],
    "tool_calls": [],
    "tokens_used": {
      "prompt": 150,
      "completion": 25,
      "total": 175
    },
    "response_time": 2.3,
    "created_at": "2026-02-11T16:00:00Z"
  },
  "msg": "success"
}
```

### Response (Streaming)

When `stream: true`, the response is sent as Server-Sent Events (SSE).

**Content-Type**: `text/event-stream`

**Event format:**

```
event: message_start
data: {"conversation_id": "conv-123", "message_id": "msg-456"}

event: content_delta
data: {"delta": "Our"}

event: content_delta
data: {"delta": " business"}

event: content_delta
data: {"delta": " hours"}

event: rag_context
data: {"contexts": [{"document_name": "FAQ", "content": "...", "score": 0.95}]}

event: message_end
data: {"usage": {"prompt_tokens": 150, "completion_tokens": 25, "total_tokens": 175}, "timing": {"first_token_ms": 320, "duration_ms": 2300, "tokens_per_second": 10.9}}
```

See [SSE Streaming](../sse-streaming.md) for details.

## Get Agent Statistics

Get usage statistics for an agent.

### Endpoint

```
GET /api/v1/agents/{agent_id}/stats
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `agent_id` | string | Yes | Agent UUID |

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `start_date` | string | No | 30 days ago | Start date (ISO 8601) |
| `end_date` | string | No | Now | End date (ISO 8601) |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/agents/550e8400-e29b-41d4-a716-446655440000/stats?start_date=2026-01-01T00:00:00Z&end_date=2026-02-11T23:59:59Z" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "total_conversations": 156,
    "total_messages": 1234,
    "total_tokens": 456789,
    "avg_response_time": 2.3,
    "success_rate": 0.98,
    "daily_stats": [
      {
        "date": "2026-02-11",
        "conversations": 12,
        "messages": 89,
        "tokens": 12345
      }
    ]
  },
  "msg": "success"
}
```

## Error Codes

| Code | Message | Description |
|------|---------|-------------|
| `6200` | Agent not found | Agent does not exist |
| `6201` | Agent not published | Agent is in draft status |
| `3000` | Permission denied | Insufficient permissions |
| `1001` | Validation failed | Invalid request data |
| `5100` | Name already exists | Agent name is taken |

## Rate Limits

| Endpoint | Limit |
|----------|-------|
| `GET /api/v1/agents` | 100/minute |
| `GET /api/v1/agents/{id}` | 100/minute |
| `POST /api/v1/agents` | 10/minute |
| `PATCH /api/v1/agents/{id}` | 30/minute |
| `DELETE /api/v1/agents/{id}` | 10/minute |
| `POST /api/v1/agents/{id}/chat` | 60/minute |

## Related Documentation

- [API Overview](../overview.md) - API introduction
- [Authentication](../authentication.md) - Authentication methods
- [Rate Limiting](../rate-limiting.md) - Rate limit details
- [SSE Streaming](../sse-streaming.md) - Streaming responses
- [Agent Concepts](../../concepts/agents.md) - Understanding agents

---

**Last Updated**: 2026-02-11
