# Real-Time Streaming API

Clouisle does **not** provide a WebSocket endpoint. There is no `wss://.../ws` connection, no message protocol, and no channel subscription system.

Real-time functionality is implemented with **Server-Sent Events (SSE)** over plain HTTP, which is simpler, works through proxies/load balancers, and auto-reconnects:

| Use Case | Endpoint | Method |
|----------|----------|--------|
| Agent chat (token-by-token) | `/api/v1/agents/{agent_id}/chat/stream` | POST |
| Workflow execution events | `/api/v1/workflows/runs/{run_id}/stream` | GET |

## What SSE Gives You

- **One-way streaming**: server → client over a standard HTTP response
- **Automatic reconnection**: SSE clients reconnect and resume (workflow stream supports `from_sequence`)
- **Event-based framing**: `event:` + `data:` lines
- **Works with fetch**, `EventSource`-style parsers, `curl -N`, and any HTTP client

If you were looking for push notifications, those are delivered via the notification system (in-app, email, Feishu/Slack/webhook channels), and workflow completion can be tracked by streaming or polling the run.

## 1. Streaming Chat (Agent)

### Start the Stream

```bash
curl -N -X POST "https://your-domain.com/api/v1/agents/{agent_id}/chat/stream" \
  -H "Authorization: Bearer YOUR_TOKEN_OR_API_KEY" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "message": "Hello, how can you help me?",
    "conversation_id": null,
    "variables": {}
  }'
```

**Response headers:**

```
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
X-Accel-Buffering: no
```

### Event Flow

```
event: message_start
data: {"conversation_id": "...", "message_id": "..."}

event: content_delta
data: {"delta": "Hello"}

event: content_delta
data: {"delta": " there"}

event: message_end
data: {"usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17}, "timing": {...}, "version_number": 1, "version_count": 1}

event: error
data: {"code": 1000, "msg": "Something went wrong, please try again later"}
```

**Event types:** `message_start`, `rag_start`, `rag_context`, `reasoning_start`, `reasoning_delta`, `reasoning_end`, `content_delta`, `tool_call`, `tool_result`, `media_result`, `compression_start`, `compression_end`, `output_truncated`, `iteration_cap_reached`, `message_end`, `error` (see [SSE Streaming](./sse-streaming.md) for the full reference).

### Client Example (JavaScript)

```javascript
async function streamChat(agentId, message, conversationId = null) {
  const response = await fetch(
    `https://your-domain.com/api/v1/agents/${agentId}/chat/stream`,
    {
      method: 'POST',
      headers: {
        'Authorization': 'Bearer YOUR_TOKEN',
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream',
      },
      body: JSON.stringify({ message, conversation_id: conversationId, variables: {} }),
    }
  );

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let eventType = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('event: ')) {
        eventType = line.slice(7);
      } else if (line.startsWith('data: ') && eventType) {
        const data = JSON.parse(line.slice(6));
        handleChatEvent(eventType, data);
        eventType = '';
      }
    }
  }
}

function handleChatEvent(type, data) {
  switch (type) {
    case 'message_start':
      console.log(`Conversation: ${data.conversation_id}`);
      break;
    case 'content_delta':
      process.stdout.write(data.delta);
      break;
    case 'message_end':
      console.log(`\nDone. usage=${JSON.stringify(data.usage)}`);
      break;
    case 'error':
      console.error(`Error ${data.code}: ${data.msg}`);
      break;
  }
}
```

### Client Example (Python)

```python
import requests
import json

def stream_chat(agent_id, message):
    response = requests.post(
        f"https://your-domain.com/api/v1/agents/{agent_id}/chat/stream",
        headers={
            "Authorization": "Bearer YOUR_TOKEN",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        json={"message": message, "conversation_id": None, "variables": {}},
        stream=True,
    )

    event_type = ""
    for line in response.iter_lines():
        if not line:
            continue
        line = line.decode("utf-8")
        if line.startswith("event: "):
            event_type = line[7:]
        elif line.startswith("data: ") and event_type:
            data = json.loads(line[6:])
            if event_type == "content_delta":
                print(data.get("delta", ""), end="", flush=True)
            elif event_type == "message_end":
                print("\n[Done]")
            elif event_type == "error":
                print(f"\nError {data.get('code')}: {data.get('msg')}")
            event_type = ""
```

## 2. Streaming Workflow Execution

### Start the Run

```bash
curl -X POST "https://your-domain.com/api/v1/workflows/{workflow_id}/run" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"inputs": {...}}'
```

**Response** contains `run_id` and `stream_url`.

### Subscribe to the Stream

```bash
curl -N "https://your-domain.com/api/v1/workflows/runs/{run_id}/stream?from_sequence=0" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Event types:** `workflow_start`, `workflow_complete`, `workflow_waiting`, `workflow_error`, `node_start`, `node_complete`, `node_error`, `node_skip`, `token`, `chunk`, `output`, `progress`, `status`, `iteration_start`, `iteration_complete`, `debug`.

Each event's `data` is `{"event": ..., "data": ..., "node_id": ..., "timestamp": ..., "sequence": ...}`. Use `from_sequence=<last sequence>` to resume after a disconnect.

**Python example:**

```python
import requests
import json

def stream_workflow(run_id):
    response = requests.get(
        f"https://your-domain.com/api/v1/workflows/runs/{run_id}/stream?from_sequence=0",
        headers={"Authorization": "Bearer YOUR_TOKEN"},
        stream=True,
    )

    event_type = ""
    for line in response.iter_lines():
        if not line:
            continue
        line = line.decode("utf-8")
        if line.startswith("event: "):
            event_type = line[7:]
        elif line.startswith("data: ") and event_type:
            payload = json.loads(line[6:])
            print(f"[{event_type}] node={payload.get('node_id')} data={json.dumps(payload.get('data'), ensure_ascii=False)}")
            event_type = ""
```

## Comparison: WebSocket vs SSE

| Aspect | WebSocket | SSE (used by Clouisle) |
|--------|-----------|------------------------|
| Direction | Bidirectional | Server → client only (client sends via normal HTTP) |
| Protocol | `ws://`/`wss://` upgrade | Plain HTTP, `text/event-stream` |
| Auto-reconnect | Manual | Built-in |
| Resume | Manual | Workflow stream supports `from_sequence` |
| Proxy/load balancer friendliness | Often problematic | Works with standard HTTP infrastructure |
| Binary data | Native | Not applicable (JSON text) |

## Error Handling

- Authentication errors are returned as **HTTP status codes** before the stream begins (401/403)
- Mid-stream failures are emitted as `event: error` with `{"code": ..., "msg": ...}`, after which the stream ends
- For chat streams, partial content is persisted and the round is marked `error`

## Best Practices

**✅ Do:**
- Handle all documented event types
- Buffer incomplete SSE lines before parsing
- Add a client-side idle timeout for chat streams
- Resume workflow streams using `from_sequence`
- Close connections when done

**❌ Don't:**
- Try to open a WebSocket — there is no WebSocket endpoint
- Send chat messages over the workflow stream (or vice versa)
- Parse partial JSON lines — wait for the full `data:` line
- Block the UI thread while reading the stream

## Related Documentation

- [SSE Streaming](./sse-streaming.md) - Full SSE event reference
- [Quick Start](./quick-start.md) - Getting started guide
- [Workflows API](./endpoints/workflows.md) - Workflow endpoints
- [Agents API](./endpoints/agents.md) - Agent chat endpoints

---

**Last Updated**: 2026-08-14
