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
- `conversation:read` - List and view conversations
- `conversation:delete` - Delete conversations and messages

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
| `enable_user_input_request` | boolean | No | Enable the model-callable `ask_user` tool (default: false) |
| `enable_memory` | boolean | No | Enable memory across conversations (default: false) |
| `memory_config` | object | No | Memory configuration |
| `context_compression_config` | object | No | Context compression configuration |
| `enable_image_generation` | boolean | No | Enable image generation tool (default: false) |
| `image_generation_config` | object | No | Image generation configuration |
| `enable_video_generation` | boolean | No | Enable video generation tool (default: false) |
| `video_generation_config` | object | No | Video generation configuration |
| `rag_mode` | string | No | RAG mode: `off`, `auto`, `agentic` (default `agentic` when a knowledge base is attached; normalized to `off` when `knowledge_base_configs` is empty) |
| `knowledge_base_configs` | array | No | KB configs (`knowledge_base_id`, `retrieval_top_k`, `score_threshold`, `search_mode`); an empty list forces `rag_mode` to `off` |
| `variables` | array | No | Chat input variable definitions |
| `opening_message` | string | No | Opening message shown in chat |
| `suggested_questions` | array | No | Suggested questions |
| `visibility` | string | No | `private` or `team` (default: `private`; legacy `public` is normalized to `team`) |

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
    "visibility": "private",
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

## Duplicate Agent

Duplicate an existing agent within its team, copying configurations with a modified name. The following are duplicated:

- **Prompts**: System prompt, opening message, suggested questions, powered-by text
- **Configurations**: Tools, attachments, memory, context compression, RAG mode, variables, iteration limits
- **Media generation**: Image and video generation settings, **except** `allow_model_override` is removed from both configs for security
- **Knowledge bases**: All knowledge base associations with retrieval settings

The duplicated agent is always created as **PRIVATE** visibility and **DRAFT** status.

### Endpoint

```
POST /api/v1/agents/{agent_id}/duplicate
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `agent_id` | string | Yes | Agent UUID to duplicate |

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/agents/550e8400-e29b-41d4-a716-446655440000/duplicate" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

Returns the newly created `AgentOut` object (`200 OK`) with status `draft`.

```json
{
  "code": 0,
  "data": {
    "id": "new-agent-uuid",
    "name": "Customer Support Agent (Copy)",
    "status": "draft",
    "visibility": "private"
  },
  "msg": "Agent duplicated successfully"
}
```

## Get Agent Video Generation Status

Check the polling status and generated media results of an asynchronous video generation task started by an agent.

### Endpoint

```
GET /api/v1/agents/{agent_id}/media/video-status?task_id={task_id}
```

### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task_id` | string | Yes | Video generation task ID |

### Response

```json
{
  "code": 0,
  "data": {
    "task_id": "video-task-uuid",
    "status": "succeeded",
    "video_url": "https://example.com/videos/output.mp4"
  },
  "msg": "success"
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
  "file_urls": [
    {
      "asset_id": "550e8400-e29b-41d4-a716-446655440000",
      "url": "https://your-domain.com/api/v1/upload/files/general/2026/09/7f3a1c9d2b10_a1b2c3d4.pdf",
      "filename": "7f3a1c9d2b10_a1b2c3d4.pdf",
      "size": 1048576,
      "mime_type": "application/pdf"
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
| `images` | array | No | Vision images (`asset_id` or `asset_ref`, `type`, `url`) |
| `files` | array | No | Parsed file content (deprecated, use `file_urls`) |
| `file_urls` | array | No | Uploaded Asset metadata: `asset_id`, `filename`, `url`, `size`, and `mime_type` |
| `conversation_id` | string | No | Conversation UUID (creates new if not provided) |
| `variables` | object | No | Variable values for the chat input form |
| `history_override` | array | No | Override conversation history (used for version switching/regeneration) |

The upload response names the MIME field `content_type`, while `ChatRequest.file_urls` requires `mime_type`; map `content_type` to `mime_type` before reusing the metadata. Preserve the returned `asset_id`, `url`, `filename`, and `size`; the URL already includes the category, date path, and generated storage filename. Do not build `/upload/files/{asset_id}` URLs. For generated media, an `asset_ref` is scoped to a conversation or workflow run and is only valid in that scope.

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

## Get Public Agent Info

Get the public chat-page view of an agent: minimal, non-sensitive fields plus the opening message, suggested questions, variables, and attachment settings. The route is implemented in the chat module (`backend/app/api/v1/endpoints/chat.py`) but is mounted under `/api/v1/agents`.

### Endpoint

```
GET /api/v1/agents/{agent_id}/public
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `agent_id` | string | Yes | Agent UUID |

### Authentication

Authentication is effectively required: the route declares an optional-auth dependency, but the lookup helper rejects an unauthenticated caller with `401 not_authenticated`. Authenticated callers still need visibility rights:

- `private`: the creator, a superuser, or — for creator-less legacy rows — any member of the agent's team.
- `team` (including legacy `public`): any member of the agent's team; superusers bypass the check.

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
    "opening_message": "Hi! How can I help you today?",
    "suggested_questions": ["What are your business hours?"],
    "powered_by_text": null,
    "variables": [],
    "enable_attachments": false,
    "attachment_config": null,
    "hide_tool_calls": false,
    "hide_message_actions": false,
    "hide_reasoning": false,
    "created_by": {
      "id": "user-001",
      "username": "alice",
      "avatar_url": null
    }
  },
  "msg": "success"
}
```

Unlike `GET /api/v1/agents/{agent_id}`, this response never exposes the model, system prompt, tool configuration, or statistics fields.

**Error (404 Not Found):** `6200` when the agent does not exist.
**Error (403 Forbidden):** `6201` when the caller cannot see the agent.

## Agent Conversations

Conversation endpoints registered on the agents router. Because the router is mounted at `/agents`, the conversation segment resolves to `/api/v1/agents/conversations/...`. Every route is scoped to the authenticated user (`Conversation.user`); another user's conversation is treated as not found (`404`).

> A separate, team/admin-oriented copy of the list/detail routes lives at `/api/v1/conversations` — see [Chat API](./chat.md).

### List Agent Conversations

```
GET /api/v1/agents/{agent_id}/conversations
```

Returns the current user's own conversations for one agent. Requires `conversation:read` and access to the agent (via the canonical `check_agent_access` guard).

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `search` | string | No | - | Match title or conversation ID (contains) |
| `created_after` | string (ISO 8601) | No | - | Only conversations created at or after this time |
| `created_before` | string (ISO 8601) | No | - | Only conversations created at or before this time |
| `sort_by` | string | No | `updated_at` | Sort field: `created_at`, `updated_at`, `message_count` (any other value falls back to `updated_at`) |
| `page` | integer | No | 1 | Page number (min 1) |
| `page_size` | integer | No | 20 | Items per page (1-100) |

Conversations are ordered by the sort field, descending. The response is a `PageData[ConversationListOut]` envelope (`items`, `total`, `page`, `page_size`) with `agent_name` and `agent_icon` filled in from the agent.

### List My Conversations

```
GET /api/v1/agents/conversations/my
```

Returns all of the current user's conversations across agents. Requires `conversation:read`.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `agent_id` | string | No | - | Filter by agent UUID |
| `page` | integer | No | 1 | Page number |
| `page_size` | integer | No | 20 | Items per page |

The response is a `PageData[ConversationListOut]` envelope; `agent_name` and `agent_icon` are `null` when the agent has been deleted.

### Get Conversation

```
GET /api/v1/agents/conversations/{conversation_id}
```

Returns the conversation together with its visible messages, including per-message `version_count`. Requires `conversation:read`; only the owner can read it (`6210` — conversation not found — for anyone else).

The response data is a `ConversationWithMessages`: the `ConversationOut` fields (`id`, `agent_id`, `agent_name`, `agent_icon`, `title`, `variables`, `message_count`, `token_usage`, `created_at`, `updated_at`) plus `messages` (a `MessageOut[]` — see [Chat API](./chat.md) for the message shape).

### Update Conversation

```
PATCH /api/v1/agents/conversations/{conversation_id}
```

Rename a conversation. Requires `conversation:read`; only the owner can update it.

### Request Body

```json
{
  "title": "Updated Conversation Title"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | string | No | New title (1-200 chars) |

Omitting `title` leaves the conversation unchanged. The response is the updated `ConversationOut` with `msg_key` `conversation_updated`.

### Delete Conversation

```
DELETE /api/v1/agents/conversations/{conversation_id}
```

Permanently delete a conversation. Requires `conversation:delete`; only the owner can delete it. The agent's `conversation_count` and `message_count` are decremented before the conversation (and its messages) are removed.

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "conv-123"
  },
  "msg": "Conversation deleted successfully"
}
```

### Delete Message

```
DELETE /api/v1/agents/conversations/{conversation_id}/messages/{message_id}
```

Delete a single message from a conversation. Requires `conversation:delete`; the message must belong to the caller's conversation. The conversation's `message_count` and `token_usage` are updated in the same row-locked transaction that removes the message; a missing conversation or message returns `6210` or `6211`.

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "msg-456"
  },
  "msg": "Message deleted successfully"
}
```

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
      "avg_response_time_ms": 2300,
      "first_token_ms": {
        "p50": 1200,
        "p95": 9000,
        "avg": 2500,
        "samples": 480
      }
    },
    "tools": {
      "tool_call_count": 512
    },
    "health": {
      "completed": 90,
      "failed": 6,
      "stopped": 4,
      "interrupted": 3,
      "unrecognised": 0,
      "in_flight": 2,
      "total": 103,
      "success_rate": 0.8738
    },
    "interventions": {
      "steer": 12,
      "stop": 3,
      "follow_up": 5,
      "total": 20
    }
  },
  "msg": "success"
}
```

`health` counts this agent's runs by outcome:

| Field | Meaning |
|-------|---------|
| `completed` / `failed` / `stopped` | Run reached that terminal state. |
| `interrupted` | **Terminal.** The worker executing the run was lost (crash, restart, eviction), so the run never reached completion. Counts toward `total` and lowers `success_rate`. |
| `unrecognised` | Terminal from the caller's perspective only in the sense that it is not counted anywhere else: the stored status is not one this build knows (typically a value written by a different release). Reported separately so enum drift is visible instead of being folded into a bucket or failing the request. |
| `in_flight` | Non-terminal runs (`queued`, `running`, `stopping`, `completing`, `waiting`). Excluded from `total` and from `success_rate`. |
| `total` | `completed + failed + stopped + interrupted`. |
| `success_rate` | `completed / total`, or `0` when there are no terminal runs. |

Additional stats endpoints exist at `GET /api/v1/agents/{agent_id}/stats/trends` (period `24h`/`7d`/`30d`) and `GET /api/v1/agents/{agent_id}/stats/tool-usage` (period `24h`/`7d`/`30d`/`all`).

All three statistics routes are implemented in `backend/app/api/v1/endpoints/agent_stats.py` (the router is mounted at `/api/v1/agents`, so the paths above are exact). They authorize through the canonical `check_agent_access` guard used across the agents router — called with `require_write=True`, i.e. the agent owner or a team admin — so an unknown agent returns `6200` (404) and a caller without access is rejected.

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

**Last Updated**: 2026-09-26
