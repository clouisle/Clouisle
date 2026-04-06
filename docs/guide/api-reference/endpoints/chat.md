# Chat API

This document describes the API endpoints for chat and conversation management.

## Overview

The Chat API allows you to:

- **Send messages**: Chat with AI agents
- **Stream responses**: Receive real-time streaming responses
- **Manage conversations**: Create, list, and delete conversations
- **View history**: Access conversation history
- **Share conversations**: Share with team members

**Base URL**: `/api/v1/chat`

## Authentication

All endpoints require authentication via JWT token or API key.

**Required scopes:**
- `agent:read` - View agents
- `agent:chat` - Chat with agents

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
| `agent_id` | string | No | - | Filter by agent ID |
| `search` | string | No | - | Search by title or content |

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
        "title": "Business Hours Inquiry",
        "agent_id": "agent-456",
        "agent_name": "Customer Support Agent",
        "message_count": 5,
        "last_message": "Thank you for the information!",
        "last_message_at": "2026-02-11T16:05:00Z",
        "created_at": "2026-02-11T16:00:00Z",
        "updated_at": "2026-02-11T16:05:00Z"
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
    "title": "Business Hours Inquiry",
    "agent_id": "agent-456",
    "agent_name": "Customer Support Agent",
    "message_count": 5,
    "created_at": "2026-02-11T16:00:00Z",
    "updated_at": "2026-02-11T16:05:00Z",
    "messages": [
      {
        "id": "msg-001",
        "role": "user",
        "content": "What are your business hours?",
        "created_at": "2026-02-11T16:00:00Z"
      },
      {
        "id": "msg-002",
        "role": "assistant",
        "content": "Our business hours are Monday-Friday, 9 AM to 5 PM EST.",
        "sources": [
          {
            "document_id": "doc-789",
            "document_name": "Business Hours Policy",
            "score": 0.95
          }
        ],
        "created_at": "2026-02-11T16:00:02Z"
      }
    ]
  },
  "msg": "success"
}
```

## Get Conversation Messages

Get messages from a conversation with pagination.

### Endpoint

```
GET /api/v1/conversations/{conversation_id}/messages
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `conversation_id` | string | Yes | Conversation UUID |

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `page` | integer | No | 1 | Page number |
| `page_size` | integer | No | 50 | Items per page (max: 100) |
| `before` | string | No | - | Get messages before this message ID |
| `after` | string | No | - | Get messages after this message ID |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/conversations/conv-123/messages?page=1&page_size=50" \
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
        "id": "msg-001",
        "conversation_id": "conv-123",
        "role": "user",
        "content": "What are your business hours?",
        "files": [],
        "created_at": "2026-02-11T16:00:00Z"
      },
      {
        "id": "msg-002",
        "conversation_id": "conv-123",
        "role": "assistant",
        "content": "Our business hours are Monday-Friday, 9 AM to 5 PM EST.",
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
        "created_at": "2026-02-11T16:00:02Z"
      }
    ],
    "total": 5,
    "page": 1,
    "page_size": 50,
    "has_more": false
  },
  "msg": "success"
}
```

## Update Conversation

Update conversation details.

### Endpoint

```
PATCH /api/v1/conversations/{conversation_id}
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
curl -X PATCH "https://your-domain.com/api/v1/conversations/conv-123" \
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

Regenerate the last assistant response.

### Endpoint

```
POST /api/v1/conversations/{conversation_id}/messages/{message_id}/regenerate
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `conversation_id` | string | Yes | Conversation UUID |
| `message_id` | string | Yes | Message UUID to regenerate |

### Request Body

```json
{
  "stream": false
}
```

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/conversations/conv-123/messages/msg-002/regenerate" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "stream": false
  }'
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "message_id": "msg-003",
    "response": "Our business hours are Monday through Friday, from 9:00 AM to 5:00 PM Eastern Standard Time.",
    "sources": [
      {
        "document_id": "doc-789",
        "document_name": "Business Hours Policy",
        "score": 0.95
      }
    ],
    "tokens_used": {
      "total": 180
    },
    "created_at": "2026-02-11T16:15:00Z"
  },
  "msg": "success"
}
```

## Share Conversation

Share a conversation with team members.

### Endpoint

```
POST /api/v1/conversations/{conversation_id}/share
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `conversation_id` | string | Yes | Conversation UUID |

### Request Body

```json
{
  "user_ids": ["user-001", "user-002"],
  "permission": "view"
}
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `user_ids` | array | Yes | User IDs to share with |
| `permission` | string | No | Permission level: view, comment, edit (default: view) |

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/conversations/conv-123/share" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "user_ids": ["user-001", "user-002"],
    "permission": "view"
  }'
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "conversation_id": "conv-123",
    "shared_with": [
      {
        "user_id": "user-001",
        "user_name": "Alice",
        "permission": "view"
      },
      {
        "user_id": "user-002",
        "user_name": "Bob",
        "permission": "view"
      }
    ]
  },
  "msg": "Conversation shared successfully"
}
```

## Unshare Conversation

Remove sharing access from a user.

### Endpoint

```
DELETE /api/v1/conversations/{conversation_id}/share/{user_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `conversation_id` | string | Yes | Conversation UUID |
| `user_id` | string | Yes | User UUID to unshare with |

### Request Example

```bash
curl -X DELETE "https://your-domain.com/api/v1/conversations/conv-123/share/user-001" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": null,
  "msg": "Conversation unshared successfully"
}
```

## Export Conversation

Export conversation to various formats.

### Endpoint

```
GET /api/v1/conversations/{conversation_id}/export
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `conversation_id` | string | Yes | Conversation UUID |

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `format` | string | No | json | Export format: json, markdown, pdf |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/conversations/conv-123/export?format=markdown" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -o conversation.md
```

### Response

**Success (200 OK):**

Returns file in requested format.

**Markdown example:**
```markdown
# Business Hours Inquiry

**Date**: 2026-02-11

## Conversation

**You** (16:00:00):
What are your business hours?

**Customer Support Agent** (16:00:02):
Our business hours are Monday-Friday, 9 AM to 5 PM EST.

**Sources**:
- Business Hours Policy (score: 0.95)
```

## Error Codes

| Code | Message | Description |
|------|---------|-------------|
| `6200` | Agent not found | Agent does not exist |
| `4000` | Conversation not found | Conversation does not exist |
| `4000` | Message not found | Message does not exist |
| `3000` | Permission denied | Insufficient permissions |
| `1001` | Validation failed | Invalid request data |

## Rate Limits

| Endpoint | Limit |
|----------|-------|
| `POST /api/v1/agents/{id}/chat` | 60/minute |
| `GET /api/v1/conversations` | 100/minute |
| `GET /api/v1/conversations/{id}` | 100/minute |
| `GET /api/v1/conversations/{id}/messages` | 100/minute |
| `PATCH /api/v1/conversations/{id}` | 30/minute |
| `DELETE /api/v1/conversations/{id}` | 10/minute |

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
- Export important conversations
- Share conversations appropriately
- Monitor conversation count

**❌ Don't:**
- Create unnecessary conversations
- Keep all conversations forever
- Share sensitive conversations
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

print(f"Response: {response['response']}")
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

console.log('Response:', response.response);
console.log('Conversation ID:', response.conversation_id);
```

## Related Documentation

- [Agents API](./agents.md) - Agent endpoints
- [SSE Streaming](../sse-streaming.md) - Streaming responses
- [Rate Limiting](../rate-limiting.md) - Rate limit details
- [Chatting with Agents](../../user-guide/chat/chatting-with-agents.md) - User guide

---

**Last Updated**: 2026-02-11
