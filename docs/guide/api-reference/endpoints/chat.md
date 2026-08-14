# Chat API

This document describes the API endpoints for chat and conversation management.

## Overview

The Chat API allows you to:

- **Send messages**: Chat with AI agents
- **Stream responses**: Receive real-time streaming responses
- **Manage conversations**: Create, list, and delete conversations
- **View history**: Access conversation history

Chat endpoints live under the agents router; conversation-management endpoints live under their own router.

**Base URLs**:
- Chat: `/api/v1/agents`
- Conversations: `/api/v1/conversations`

## Authentication

All endpoints require authentication via JWT token or API key.

**Required scopes:**
- `agent:read` - View agents
- `agent:chat` - Chat with agents
- `conversation:read` - List and view conversations
- `conversation:delete` - Delete conversations

## Send Message

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
curl -X POST "https://your-domain.com/api/v1/agents/agent-123/chat" \
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

## List Conversations

Get a list of all conversations.

### Endpoint

```
GET /api/v1/conversations
```

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `page` | integer | No | 1 | Page number |
| `page_size` | integer | No | 20 | Items per page (max: 100) |
| `team_id` | string | No | - | Filter by team |
| `agent_id` | string | No | - | Filter by agent ID |
| `user_id` | string | No | - | Filter by user (admin/dashboard access only) |
| `search` | string | No | - | Search by title |
| `untitled_only` | boolean | No | false | Show only untitled conversations |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/conversations?page=1&page_size=20" \
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
        "id": "conv-123",
        "agent_id": "agent-456",
        "agent_name": "Customer Support Agent",
        "agent_icon": "🤖",
        "title": "Business Hours Inquiry",
        "message_count": 5,
        "created_at": "2026-02-11T16:00:00Z",
        "updated_at": "2026-02-11T16:05:00Z",
        "user_id": "user-123",
        "user_name": "alice"
      }
    ],
    "total": 42,
    "page": 1,
    "page_size": 20
  },
  "msg": "success"
}
```

## Get Conversation

Get details of a specific conversation.

### Endpoint

```
GET /api/v1/conversations/{conversation_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `conversation_id` | string | Yes | Conversation UUID |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/conversations/conv-123" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "conv-123",
    "agent_id": "agent-456",
    "agent_name": "Customer Support Agent",
    "agent_icon": "🤖",
    "title": "Business Hours Inquiry",
    "variables": {},
    "message_count": 5,
    "token_usage": 875,
    "created_at": "2026-02-11T16:00:00Z",
    "updated_at": "2026-02-11T16:05:00Z",
    "messages": [
      {
        "id": "msg-001",
        "conversation_id": "conv-123",
        "role": "user",
        "content": "What are your business hours?",
        "created_at": "2026-02-11T16:00:00Z",
        "version_number": 1,
        "version_count": 1
      },
      {
        "id": "msg-002",
        "conversation_id": "conv-123",
        "role": "assistant",
        "content": "Our business hours are Monday-Friday, 9 AM to 5 PM EST.",
        "tool_calls": [],
        "rag_context": [
          {
            "document_id": "doc-789",
            "document_name": "Business Hours Policy",
            "score": 0.95
          }
        ],
        "created_at": "2026-02-11T16:00:02Z",
        "version_number": 1,
        "version_count": 1
      }
    ]
  },
  "msg": "success"
}
```

## Get Conversation Messages

> **Note:** Not implemented / Roadmap. There is no paginated `GET /conversations/{id}/messages` endpoint. Messages are included inline in `GET /api/v1/conversations/{conversation_id}` (see [Get Conversation](#get-conversation)).

## Update Conversation

Update conversation details (e.g. rename). This endpoint lives under the agents router.

### Endpoint

```
PATCH /api/v1/agents/conversations/{conversation_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `conversation_id` | string | Yes | Conversation UUID |

### Request Body

```json
{
  "title": "Updated Conversation Title"
}
```

### Request Example

```bash
curl -X PATCH "https://your-domain.com/api/v1/agents/conversations/conv-123" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Updated Conversation Title"
  }'
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "conv-123",
    "title": "Updated Conversation Title",
    "updated_at": "2026-02-11T16:10:00Z"
  },
  "msg": "Conversation updated successfully"
}
```

## Delete Conversation

Delete a conversation permanently.

### Endpoint

```
DELETE /api/v1/conversations/{conversation_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `conversation_id` | string | Yes | Conversation UUID |

### Request Example

```bash
curl -X DELETE "https://your-domain.com/api/v1/conversations/conv-123" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": null,
  "msg": "Conversation deleted successfully"
}
```

## Regenerate Response

Regenerate an assistant message. This endpoint lives under the agents router and is addressed by `agent_id` + `message_id` (no `conversation_id` in the path).

### Endpoint

```
POST /api/v1/agents/{agent_id}/messages/{message_id}/regenerate
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `agent_id` | string | Yes | Agent UUID |
| `message_id` | string | Yes | Message UUID to regenerate |

### Request Body

```json
{
  "variables": {}
}
```

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/agents/agent-123/messages/msg-002/regenerate" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "variables": {}
  }'
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "conversation_id": "conv-123",
    "message": {
      "id": "msg-003",
      "conversation_id": "conv-123",
      "role": "assistant",
      "content": "Our business hours are Monday through Friday, from 9:00 AM to 5:00 PM Eastern Standard Time.",
      "token_usage": {
        "total": 180
      },
      "created_at": "2026-02-11T16:15:00Z",
      "version_number": 2,
      "version_count": 2
    },
    "usage": {
      "total": 180
    }
  },
  "msg": "success"
}
```

## Share Conversation

> **Note:** Not implemented / Roadmap. There is no conversation-sharing endpoint.

## Unshare Conversation

> **Note:** Not implemented / Roadmap. There is no conversation-unsharing endpoint.

## Export Conversation

> **Note:** Not implemented / Roadmap. There is no conversation-export endpoint.

## Error Codes

| Code | Message | Description |
|------|---------|-------------|
| `6200` | Agent not found | Agent does not exist |
| `6210` | Conversation not found | Conversation does not exist |
| `6211` | Message not found | Message does not exist |
| `3000` | Permission denied | Insufficient permissions |
| `1001` | Validation failed | Invalid request data |

> **Note:** No per-endpoint rate limits are implemented. There is no rate-limit middleware on these endpoints.

## Best Practices

### Message Handling

**✅ Do:**
- Keep messages concise and clear
- Provide context when needed
- Use conversation_id to maintain context
- Handle streaming for better UX
- Implement retry logic for failures

**❌ Don't:**
- Send extremely long messages
- Create new conversation for each message
- Ignore error responses
- Skip error handling
- Spam the API

### Conversation Management

**✅ Do:**
- Use descriptive conversation titles
- Clean up old conversations
- Monitor conversation count

**❌ Don't:**
- Create unnecessary conversations
- Keep all conversations forever
- Forget to delete test conversations

## Code Examples

### Python

```python
import requests

def chat_with_agent(agent_id, message, conversation_id=None):
    """Send message to agent."""
    url = f"https://your-domain.com/api/v1/agents/{agent_id}/chat"
    headers = {
        "Authorization": "Bearer YOUR_TOKEN",
        "Content-Type": "application/json"
    }
    data = {
        "message": message,
        "conversation_id": conversation_id
    }

    response = requests.post(url, headers=headers, json=data)
    result = response.json()

    if result['code'] == 0:
        return result['data']
    else:
        raise Exception(f"Error: {result['msg']}")

# Usage
response = chat_with_agent(
    agent_id="agent-123",
    message="What are your business hours?",
    conversation_id="conv-123"
)

print(f"Response: {response['message']['content']}")
print(f"Conversation ID: {response['conversation_id']}")
```

### JavaScript

```javascript
async function chatWithAgent(agentId, message, conversationId = null) {
  const url = `https://your-domain.com/api/v1/agents/${agentId}/chat`;

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Authorization': 'Bearer YOUR_TOKEN',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      message: message,
      conversation_id: conversationId,
    }),
  });

  const result = await response.json();

  if (result.code === 0) {
    return result.data;
  } else {
    throw new Error(result.msg);
  }
}

// Usage
const response = await chatWithAgent(
  'agent-123',
  'What are your business hours?',
  'conv-123'
);

console.log('Response:', response.message.content);
console.log('Conversation ID:', response.conversation_id);
```

## Related Documentation

- [Agents API](./agents.md) - Agent endpoints
- [SSE Streaming](../sse-streaming.md) - Streaming responses
- [Rate Limiting](../rate-limiting.md) - Rate limit details
- [Chatting with Agents](../../user-guide/chat/chatting-with-agents.md) - User guide

---

**Last Updated**: 2026-02-11
