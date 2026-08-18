# Agents API

This document describes the API endpoints for managing and interacting with AI agents.

## Overview

The Agents API allows you to:

- **List agents**: Get all available agents
- **Get agent details**: Retrieve agent information
- **Create agents**: Create new AI agents
- **Update agents**: Modify agent configuration
- **Delete agents**: Remove agents
- **Chat with agents**: Send messages and receive responses
- **Publish/unpublish agents**: Control agent visibility

**Base URL**: `/api/v1/agents`

## Authentication

All endpoints require an authenticated JWT user session. The chat endpoints additionally accept an API key where noted.
**Required scopes:**
- `agent:read` - List and view agents
- `agent:create` - Create agents
- `agent:update` - Update agents
- `agent:delete` - Delete agents
- `agent:publish` - Publish or unpublish agents
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
| `page_size` | integer | No | 20 | Items per page |
| `team_id` | string | No | - | Filter by team ID |
| `status` | string | No | - | Filter by status: `draft`, `published` |
| `visibility` | string | No | - | Filter by visibility: `private`, `team`, `public` (legacy compatibility value) |
| `keyword` | string | No | - | Search by name or description |
| `own_only` | boolean | No | false | Only show agents created by the current user |

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
        "icon": "🤖",
        "avatar_url": "https://example.com/avatar.png",
        "team": {
          "id": "team-123",
          "name": "Support Team",
          "avatar_url": "https://example.com/team.png"
        },
        "model": {
          "id": "model-456",
          "name": "GPT-4",
          "provider": "openai",
          "provider_display_name": "OpenAI",
          "model_id": "gpt-4"
        },
        "status": "published",
        "visibility": "team",
        "conversation_count": 156,
        "message_count": 1234,
        "created_by": {
          "id": "user-001",
          "username": "alice",
          "avatar_url": "https://example.com/avatars/alice.jpg"
        },
        "created_at": "2026-02-11T10:00:00Z",
        "updated_at": "2026-02-11T15:30:00Z"
      }
    ],
    "total": 42,
    "page": 1,
    "page_size": 20
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
| `icon` | string | Icon emoji or URL |
| `avatar_url` | string | Agent avatar URL |
| `team` | object | Team info (`id`, `name`, `avatar_url`) |
| `model` | object | Model info (`id`, `name`, `provider`, `model_id`), `null` if unset |
| `status` | string | `draft` or `published` |
| `visibility` | string | `private` or `team` |
| `conversation_count` | integer | Number of conversations |
| `message_count` | integer | Number of messages |
| `created_by` | object | Creator info (`id`, `username`, `avatar_url`) |
| `created_at` | string | ISO 8601 timestamp |
| `updated_at` | string | ISO 8601 timestamp |

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
    "icon": "🤖",
    "avatar_url": "https://example.com/avatar.png",
    "team": {
      "id": "team-123",
      "name": "Support Team",
      "avatar_url": "https://example.com/team.png"
    },
    "model_id": "model-456",
    "model": {
      "id": "model-456",
      "name": "GPT-4",
      "provider": "openai",
      "provider_display_name": "OpenAI",
      "model_id": "gpt-4"
    },
    "system_prompt": "You are a helpful customer support agent...",
    "max_iterations": 5,
    "hide_tool_calls": false,
    "hide_message_actions": false,
    "hide_reasoning": false,
    "tools_config": [
      {
        "type": "builtin",
        "name": "web_search"
      }
    ],
    "enable_attachments": false,
    "enable_user_input_request": false,
    "enable_memory": false,
    "rag_mode": "agentic",
    "variables": [],
    "knowledge_bases": [
      {
        "id": "kb-assoc-001",
        "knowledge_base": {
          "id": "kb-789",
          "name": "Product Documentation",
          "description": "Product docs and FAQs",
          "icon": "📚",
          "document_count": 156
        },
        "retrieval_top_k": 5,
        "score_threshold": 0.3,
        "search_mode": "hybrid"
      }
    ],
    "status": "published",
    "visibility": "team",
    "conversation_count": 156,
    "message_count": 1234,
    "created_by": {
      "id": "user-001",
      "username": "alice",
      "avatar_url": "https://example.com/avatars/alice.jpg"
    },
    "created_at": "2026-02-11T10:00:00Z",
    "updated_at": "2026-02-11T15:30:00Z"
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
  "max_iterations": 5,
  "hide_tool_calls": false,
  "tools_config": [
    {
      "type": "builtin",
      "name": "web_search"
    }
  ],
  "enable_memory": false,
  "rag_mode": "agentic",
  "knowledge_base_configs": [
    {
      "knowledge_base_id": "kb-789",
      "retrieval_top_k": 5,
      "score_threshold": 0.3,
      "search_mode": "hybrid"
    }
  ],
  "visibility": "team"
}
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Agent name (max 100 chars) |
| `description` | string | No | Agent description (max 500 chars) |
| `icon` | string | No | Icon emoji or URL (max 500 chars) |
| `avatar_url` | string | No | Agent avatar URL |
| `team_id` | string | Yes | Team UUID |
| `model_id` | string | No | TeamModel UUID (optional; unset agents use the team default) |
| `system_prompt` | string | No | System prompt/instructions |
| `max_iterations` | integer | No | Max tool call iterations (1-200, default: 5) |
| `hide_tool_calls` | boolean | No | Hide tool call details in chat UI (default: false) |
| `hide_message_actions` | boolean | No | Hide token usage/speed stats in chat UI (default: false) |
| `hide_reasoning` | boolean | No | Hide reasoning/chain-of-thought in chat UI (default: false) |
| `tools_config` | array | No | Tool configs (`type`/`name`/`tool_id`/`server_id`/`skill_id`/`config`) |
| `tools_credentials` | object | No | Tool credentials (API keys, tokens, etc.) |
| `enable_attachments` | boolean | No | Enable file and image attachments (default: false) |
| `attachment_config` | object | No | Attachment limits configuration |
| `enable_user_input_request` | boolean | No | Enable user input request (default: false) |
| `enable_memory` | boolean | No | Enable memory across conversations (default: false) |
| `memory_config` | object | No | Memory configuration |
| `context_compression_config` | object | No | Context compression configuration |
| `enable_image_generation` | boolean | No | Enable image generation tool (default: false) |
| `image_generation_config` | object | No | Image generation configuration |
| `enable_video_generation` | boolean | No | Enable video generation tool (default: false) |
| `video_generation_config` | object | No | Video generation configuration |
| `rag_mode` | string | No | RAG mode: `off`, `auto`, `agentic` (default: `agentic`) |
| `knowledge_base_configs` | array | No | KB configs (`knowledge_base_id`, `retrieval_top_k`, `score_threshold`, `search_mode`) |
| `variables` | array | No | Chat input variable definitions |
| `opening_message` | string | No | Opening message shown in chat |
| `suggested_questions` | array | No | Suggested questions |
| `visibility` | string | No | `private` or `team` (default: `team`) |

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
    "tools_config": [{"type": "builtin", "name": "web_search"}],
    "knowledge_base_configs": [
      {
        "knowledge_base_id": "kb-789",
        "retrieval_top_k": 5,
        "score_threshold": 0.3,
        "search_mode": "hybrid"
      }
    ],
    "rag_mode": "agentic"
  }'
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
    "status": "draft",
    "visibility": "team",
    "team": {
      "id": "team-123",
      "name": "Support Team",
      "avatar_url": null
    },
    "model_id": "model-456",
    "model": {
      "id": "model-456",
      "name": "GPT-4",
      "provider": "openai",
      "provider_display_name": "OpenAI",
      "model_id": "gpt-4"
    },
    "created_at": "2026-02-11T10:00:00Z",
    "created_by": {
      "id": "user-001",
      "username": "alice",
      "avatar_url": null
    }
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
PUT /api/v1/agents/{agent_id}
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
  "max_iterations": 8,
  "tools_config": [
    {"type": "builtin", "name": "web_search"},
    {"type": "builtin", "name": "code_interpreter"}
  ],
  "rag_mode": "auto"
}
```

### Request Example

```bash
curl -X PUT "https://your-domain.com/api/v1/agents/550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Updated Agent Name",
    "max_iterations": 8
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
    "max_iterations": 8,
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

The publish endpoint returns the full `AgentOut` object (`200 OK`). The abbreviated example below shows the changed status field.

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "published"
  },
  "msg": "Agent published successfully"
}
```

The publish route sets the agent status to `published` and does not perform a model-presence validation. Error `6202` is used when a later chat/access path requires a published agent but receives a draft agent; it is not a publish response.

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

The unpublish endpoint returns the full `AgentOut` object (`200 OK`). The abbreviated example below shows the changed status field.

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "draft"
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
  "files": [
    {
      "name": "document.pdf",
      "url": "https://example.com/document.pdf",
      "type": "application/pdf"
    }
  ],
  "file_urls": [
    {
      "asset_id": "asset-456",
      "url": "https://your-domain.com/api/v1/upload/files/asset-456",
      "filename": "report.pdf"
    }
  ],
  "variables": {
    "customer_tier": "premium"
  }
}
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `message` | string | Yes | User message (max 32000 chars) |
| `images` | array | No | Images for vision (name, url, type) |
| `files` | array | No | Parsed files for upload (deprecated, use `file_urls`) |
| `file_urls` | array | No | Raw uploaded Asset metadata (`asset_id`, `url`, `filename`) |
| `conversation_id` | string | No | Conversation UUID (creates new if not provided) |
| `variables` | object | No | Variable values for the chat input form |
| `history_override` | array | No | Override conversation history (used for version switching/regeneration) |

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
    "message": {
      "id": "msg-456",
      "conversation_id": "conv-123",
      "role": "assistant",
      "content": "Our business hours are Monday-Friday, 9 AM to 5 PM EST.",
      "tool_calls": [],
      "tool_name": null,
      "model_used": "gpt-4",
      "token_usage": {
        "prompt": 150,
        "completion": 25,
        "total": 175
      },
      "duration_ms": 2300,
      "rag_context": [
        {
          "document_id": "doc-789",
          "document_name": "Business Hours Policy",
          "chunk_id": "chunk-012",
          "content": "Business hours: Monday-Friday, 9 AM to 5 PM EST",
          "score": 0.95
        }
      ],
      "created_at": "2026-02-11T16:00:00Z",
      "version_number": 1,
      "version_count": 1
    },
    "usage": {
      "prompt": 150,
      "completion": 25,
      "total": 175
    }
  },
  "msg": "success"
}
```

### Response (Streaming)

Streaming is a separate endpoint; there is no `stream` flag on `POST /chat`.

**Endpoint:** `POST /api/v1/agents/{agent_id}/chat/stream`

The request body is the same `ChatRequest` payload. The response is sent as Server-Sent Events (SSE).

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
| `period` | string | No | `7d` | Time period: `24h`, `7d`, `30d`, `all` |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/agents/550e8400-e29b-41d4-a716-446655440000/stats?period=30d" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "period": "30d",
    "overview": {
      "total_conversations": 156,
      "total_messages": 1234,
      "user_messages": 620,
      "assistant_messages": 610,
      "tool_messages": 4,
      "active_users": 23
    },
    "tokens": {
      "prompt_tokens": 250000,
      "completion_tokens": 206789,
      "total_tokens": 456789
    },
    "performance": {
      "avg_response_time_ms": 2300
    },
    "tools": {
      "tool_call_count": 512
    }
  },
  "msg": "success"
}
```

Additional stats endpoints exist at `GET /agents/{agent_id}/stats/trends` (period `24h`/`7d`/`30d`), `GET /agents/{agent_id}/stats/tool-usage` (period `24h`/`7d`/`30d`/`all`), and `GET /agents/{agent_id}/stats/recent-conversations` (limit, default 10).

## Error Codes

| Code | Message | Description |
|------|---------|-------------|
| `6200` | Agent not found | Agent does not exist |
| `6201` | Access denied | User has no access to the agent |
| `6202` | Agent not published | Agent is in draft status |
| `3000` | Permission denied | Insufficient permissions |
| `1001` | Validation failed | Invalid request data |
| `5104` | Duplicate name | Agent name is taken |

> **Note:** No per-endpoint rate limits are implemented. There is no rate-limit middleware on these endpoints.

## Related Documentation

- [API Overview](../overview.md) - API introduction
- [Authentication](../authentication.md) - Authentication methods
- [Rate Limiting](../rate-limiting.md) - Rate limit details
- [SSE Streaming](../sse-streaming.md) - Streaming responses
- [Agent Concepts](../../user-guide/agents/agent-configuration.md) - Agent configuration

---

**Last Updated**: 2026-02-11
