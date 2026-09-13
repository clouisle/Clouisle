# Embed API

The Embed API provides dedicated endpoints for integrating Clouisle agents and workflows into external websites via iframe or third-party web clients using API Key authentication without session cookies.

**Base URL**: `/api/v1/embed`

---

## Authentication

Embed endpoints authenticate via API Key only (prefixed with `clou_`). Authentication can be supplied via:
- **Authorization Header**: `Authorization: Bearer clou_...`
- **Query Parameter**: `?token=clou_...`

---

## Agent Embed Endpoints

### 1. Get Embed Agent Info

Retrieve public agent configuration (title, icon, opening message, suggested questions, variables, file upload capabilities) for the embed chat widget.

```http
GET /api/v1/embed/agents/{agent_id}/info HTTP/1.1
Authorization: Bearer clou_api_key
```

#### Response (`200 OK`)

```json
{
  "code": 0,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Customer Support Agent",
    "description": "Helps users with product queries",
    "icon": "🤖",
    "avatar_url": null,
    "opening_message": "Hello! How can I help you today?",
    "suggested_questions": [
      "What are the pricing tiers?",
      "How do I reset my password?"
    ],
    "variables": [],
    "powered_by_text": "Powered by Clouisle",
    "enable_attachments": true,
    "attachment_config": {
      "max_file_count": 5,
      "max_file_size_mb": 10
    }
  },
  "msg": "success"
}
```

---

### 2. Stream Embed Agent Chat

Send a chat message and receive a streaming Server-Sent Events (SSE) response.

```http
POST /api/v1/embed/agents/{agent_id}/chat/stream HTTP/1.1
Authorization: Bearer clou_api_key
Content-Type: application/json

{
  "message": "What is the refund policy?",
  "conversation_id": "conv-uuid-optional",
  "variables": {}
}
```

#### Response (`200 OK`, `text/event-stream`)

Streams standard SSE event chunks (`message_start`, `content`, `thought`, `tool_start`, `tool_end`, `message_end`).

---

### 3. Start Durable Chat Run

Create an asynchronous, durable AgentRun for reliable execution that survives client disconnections.

```http
POST /api/v1/embed/agents/{agent_id}/chat/runs HTTP/1.1
Authorization: Bearer clou_api_key
Content-Type: application/json

{
  "message": "Analyze sales data",
  "conversation_id": null,
  "variables": {}
}
```

#### Response (`202 Accepted`)

```json
{
  "code": 0,
  "data": {
    "run_id": "run-uuid-1234",
    "conversation_id": "conv-uuid-5678",
    "status": "queued"
  },
  "msg": "Run accepted"
}
```

---

### 4. Stream Chat Run Events

Subscribe to replayable SSE events for a specific run, with duplicate suppression via `after_sequence`.

```http
GET /api/v1/embed/agents/{agent_id}/chat/runs/{run_id}/stream?after_sequence=0 HTTP/1.1
Authorization: Bearer clou_api_key
```

---

### 5. Get Run Status and Replay Events

- `GET /api/v1/embed/agents/{agent_id}/chat/runs/{run_id}`: Get current lifecycle status (`queued`, `running`, `waiting`, `completed`, `failed`, `stopped`, `interrupted`).
- `GET /api/v1/embed/agents/{agent_id}/chat/runs/{run_id}/events?after_sequence=0`: Fetch buffered structured events.

---

### 6. Steer or Submit User Interaction to Chat Run

- `POST /api/v1/embed/agents/{agent_id}/chat/runs/{run_id}/inputs`: Queue mid-run steering or follow-up prompt (`{"content": "focus on Q3", "delivery": "steer"}`).
- `POST /api/v1/embed/agents/{agent_id}/chat/runs/{run_id}/answers`: Submit answers to an `ask_user` tool prompt (`{"tool_call_id": "call-1", "answers": {"choice": "Cloud"}}`).
- `POST /api/v1/embed/agents/{agent_id}/chat/runs/{run_id}/stop`: Terminate the running agent loop.

---

### 7. Embed Conversation Messages and File Upload

- `GET /api/v1/embed/agents/{agent_id}/conversations/{conversation_id}/messages`: Get message history for an embed session.
- `POST /api/v1/embed/agents/{agent_id}/upload/file`: Upload attachments for embed conversations (`multipart/form-data`).

---

## Workflow Embed Endpoints

### 1. Get Embed Workflow Info

```http
GET /api/v1/embed/workflows/{workflow_id}/info HTTP/1.1
Authorization: Bearer clou_api_key
```

Returns workflow name, description, icon, input parameter schema, and status.

---

### 2. Execute Embed Workflow

```http
POST /api/v1/embed/workflows/{workflow_id}/run HTTP/1.1
Authorization: Bearer clou_api_key
Content-Type: application/json

{
  "inputs": {
    "query": "Generate summary report",
    "format": "markdown"
  }
}
```

#### Response (`200 OK`)

```json
{
  "code": 0,
  "data": {
    "run_id": "wf-run-uuid-1234",
    "status": "running"
  },
  "msg": "Workflow run started"
}
```

---

### 3. Stream Workflow Run Progress

```http
GET /api/v1/embed/workflows/runs/{run_id}/stream?from_sequence=0 HTTP/1.1
Authorization: Bearer clou_api_key
```

Returns real-time node execution progress, intermediate outputs, and the final workflow execution result.
