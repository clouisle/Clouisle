# HTTP API Examples

Clouisle does **not** publish official SDK packages (Python, JavaScript, Go, Ruby, or otherwise). The API is a standard REST + JSON interface served over HTTPS, and the OpenAPI specification is available at:

- **Swagger UI**: `https://your-domain.com/docs`
- **OpenAPI JSON**: `https://your-domain.com/api/v1/openapi.json`

Any HTTP client can call the API directly. This guide provides copy-pasteable examples in the most common languages. If you need a typed client, generate one from the OpenAPI spec (e.g. `openapi-generator`, `openapi-typescript`).

## Common Setup

All requests use:

- Base URL: `https://your-domain.com/api/v1`
- JSON request/response bodies (unless noted)
- `Authorization: Bearer <token>` header (JWT or `clou_` API key)
- Unified response envelope: `{"code": 0, "data": ..., "msg": "success"}`

## Authentication

### Login (JWT)

`POST /api/v1/login/access-token` — form-encoded `username` and `password`.

**curl:**
```bash
curl -X POST "https://your-domain.com/api/v1/login/access-token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=your_username&password=your_password"
```

**Python:**
```python
import requests

response = requests.post(
    "https://your-domain.com/api/v1/login/access-token",
    data={"username": "your_username", "password": "your_password"},
)
token = response.json()["data"]["access_token"]
```

The token is valid for the `session_timeout_days` site setting (default 30 days).

### API Key

Create a key via the UI or `POST /api/v1/api-keys`, then send it as a Bearer token:

```bash
export CLOUISLE_API_KEY="clou_your_full_key_here"
curl -X GET "https://your-domain.com/api/v1/agents" \
  -H "Authorization: Bearer $CLOUISLE_API_KEY"
```

## Agent Examples

### List Agents

```bash
curl -X GET "https://your-domain.com/api/v1/agents?team_id=550e8400-e29b-41d4-a716-446655440000&page=1&page_size=20" \
  -H "Authorization: Bearer $CLOUISLE_TOKEN"
```

**Python:**
```python
import requests

result = requests.get(
    "https://your-domain.com/api/v1/agents",
    headers={"Authorization": f"Bearer {token}"},
    params={"team_id": "550e8400-e29b-41d4-a716-446655440000", "page": 1, "page_size": 20},
).json()

for agent in result["data"]["items"]:
    print(agent["id"], agent["name"], agent["status"])
```

### Create an Agent

`POST /api/v1/agents` — `team_id` is required (UUID); `model_id` is a TeamModel authorization UUID (optional); `model` in responses is a `ModelInfo` object.

**curl:**
```bash
curl -X POST "https://your-domain.com/api/v1/agents" \
  -H "Authorization: Bearer $CLOUISLE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Customer Support Agent",
    "team_id": "550e8400-e29b-41d4-a716-446655440000",
    "model_id": "550e8400-e29b-41d4-a716-446655440001",
    "system_prompt": "You are a helpful customer support agent.",
    "max_iterations": 5,
    "visibility": "team"
  }'
```

### Chat with an Agent

`POST /api/v1/agents/{agent_id}/chat` — conversations are created implicitly; pass `conversation_id` to continue one.

**Python:**
```python
import requests

result = requests.post(
    f"https://your-domain.com/api/v1/agents/{agent_id}/chat",
    headers={"Authorization": f"Bearer {token}"},
    json={
        "message": "Hello! I need help with my order.",
        "conversation_id": None,
        "variables": {},
    },
).json()

conversation_id = result["data"]["conversation_id"]
print(result["data"]["message"]["content"])
```

### Stream a Chat (SSE)

`POST /api/v1/agents/{agent_id}/chat/stream` — see [SSE Streaming](./sse-streaming.md).

**JavaScript:**
```javascript
const response = await fetch(
  `https://your-domain.com/api/v1/agents/${agentId}/chat/stream`,
  {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream',
    },
    body: JSON.stringify({ message: 'Tell me a story', conversation_id: null, variables: {} }),
  }
);

const reader = response.body.getReader();
const decoder = new TextDecoder();
let buffer = '';

while (true) {
  const { done, value } = await reader.read();
  if (done) break;

  buffer += decoder.decode(value, { stream: true });
  const lines = buffer.split('\n');
  buffer = lines.pop() || '';

  let eventType = '';
  for (const line of lines) {
    if (line.startsWith('event: ')) {
      eventType = line.slice(7);
    } else if (line.startsWith('data: ') && eventType) {
      const data = JSON.parse(line.slice(6));
      if (eventType === 'content_delta') process.stdout.write(data.delta);
      if (eventType === 'message_end') console.log('\n[Done]');
      eventType = '';
    }
  }
}
```

## Conversation Examples

### List Conversations

```bash
curl -X GET "https://your-domain.com/api/v1/conversations?agent_id=550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer $CLOUISLE_TOKEN"
```

### Get a Conversation (with Messages)

```python
import requests

conversation = requests.get(
    f"https://your-domain.com/api/v1/conversations/{conversation_id}",
    headers={"Authorization": f"Bearer {token}"},
).json()

for msg in conversation["data"]["messages"]:
    print(msg["role"], msg["content"])
```

### Batch Delete Conversations

```bash
curl -X DELETE "https://your-domain.com/api/v1/conversations?ids=550e8400-e29b-41d4-a716-446655440000&ids=550e8400-e29b-41d4-a716-446655440001" \
  -H "Authorization: Bearer $CLOUISLE_TOKEN"
```

## Knowledge Base Examples

### Upload a Document

```bash
curl -X POST "https://your-domain.com/api/v1/knowledge-bases/$KB_ID/documents/upload" \
  -H "Authorization: Bearer $CLOUISLE_TOKEN" \
  -F "file=@/path/to/document.pdf"
```

### Search

`POST /api/v1/knowledge-bases/{kb_id}/search`:

```python
import requests

result = requests.post(
    f"https://your-domain.com/api/v1/knowledge-bases/{kb_id}/search",
    headers={"Authorization": f"Bearer {token}"},
    json={
        "query": "How to reset password?",
        "search_mode": "hybrid",
        "top_k": 5,
    },
).json()

for item in result["data"]["results"]:
    print(item["document_name"], item["score"])
```

## Workflow Examples

### Run a Workflow

`POST /api/v1/workflows/{workflow_id}/run`:

**curl:**
```bash
curl -X POST "https://your-domain.com/api/v1/workflows/$WORKFLOW_ID/run" \
  -H "Authorization: Bearer $CLOUISLE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"inputs": {"customer_email": "customer@example.com", "inquiry_text": "I need help"}}'
```

**Response** includes `run_id` and `stream_url`:
```json
{
  "code": 0,
  "data": {
    "run_id": "550e8400-e29b-41d4-a716-446655440000",
    "stream_url": "/api/v1/workflows/runs/550e8400-e29b-41d4-a716-446655440000/stream"
  },
  "msg": "success"
}
```

### Stream Workflow Events (SSE)

```bash
curl -N "https://your-domain.com/api/v1/workflows/runs/$RUN_ID/stream?from_sequence=0" \
  -H "Authorization: Bearer $CLOUISLE_TOKEN"
```

Events: `workflow_start`, `workflow_complete`, `workflow_waiting`, `workflow_error`, `node_start`, `node_complete`, `node_error`, `node_skip`, `token`, `chunk`, `output`, `progress`, `status`, `iteration_start`, `iteration_complete`, `debug`. See [SSE Streaming](./sse-streaming.md).

### Trigger a Workflow via Webhook

`POST /api/v1/workflows/webhook/{webhook_token}` with a `clou_` API key:

```bash
curl -X POST "https://your-domain.com/api/v1/workflows/webhook/$WEBHOOK_TOKEN" \
  -H "Authorization: Bearer $CLOUISLE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"customer_email": "customer@example.com", "inquiry_text": "I need help"}'
```

## Error Handling

Always check `code` before using `data`. Validation failures return HTTP 422 with a field → messages dictionary:

```python
import requests

response = requests.post(
    "https://your-domain.com/api/v1/agents",
    headers={"Authorization": f"Bearer {token}"},
    json={"name": "x"},  # missing required team_id
)
result = response.json()

if result["code"] != 0:
    if result["code"] == 1001:
        for field, messages in result["data"]["errors"].items():
            print(f"{field}: {', '.join(messages)}")
    else:
        print(f"Error {result['code']}: {result['msg']}")
```

## Generating a Client from OpenAPI

Because there is no official SDK, generate a typed client from the OpenAPI spec:

```bash
# TypeScript types
npx openapi-typescript https://your-domain.com/api/v1/openapi.json -o api.d.ts

# OpenAPI Generator (Python, Java, Go, ...)
openapi-generator generate -i https://your-domain.com/api/v1/openapi.json -g python -o ./client
```

## Related Documentation

- [Quick Start](./quick-start.md) - Getting started guide
- [API Reference](./endpoints/) - Complete API documentation
- [Best Practices](./api-best-practices.md) - API best practices
- [Error Handling](./error-handling.md) - Error handling guide

---

**Last Updated**: 2026-08-14
