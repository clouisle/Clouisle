# SSE Streaming

This document explains how to use Server-Sent Events (SSE) for streaming responses from the Clouisle API.

## Overview

SSE streaming allows you to:

- **Real-time responses**: Receive data as it's generated
- **Token-by-token output**: Stream LLM responses word by word
- **Progress updates**: Monitor long-running operations
- **Reduced latency**: Start processing data before completion
- **Better UX**: Show progress to users immediately

## What is SSE?

Server-Sent Events (SSE) is a standard for streaming data from server to client over HTTP.

**Characteristics:**
- One-way communication (server to client)
- Text-based protocol
- Automatic reconnection
- Event-based messaging
- Works over standard HTTP

**Use cases:**
- Streaming chat responses
- Real-time notifications
- Progress updates
- Live data feeds

## Enabling Streaming

### Agent Chat Streaming

**Send a streaming chat request:**

```bash
curl -X POST "https://your-domain.com/api/v1/agents/{agent_id}/chat/stream" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "message": "Explain quantum computing",
    "conversation_id": null,
    "variables": {}
  }'
```

### Workflow Streaming

Workflow runs stream via SSE over a separate endpoint. First, start the run:

```bash
curl -X POST "https://your-domain.com/api/v1/workflows/{workflow_id}/run" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": {...}
  }'
```

The response returns `run_id` and `stream_url`:

```json
{
  "code": 0,
  "data": {
    "run_id": "run-789",
    "stream_url": "/api/v1/workflows/runs/run-789/stream"
  },
  "msg": "success"
}
```

Then subscribe to the stream (SSE GET, optional `from_sequence` query parameter for resuming after a disconnect):

```bash
curl -N "https://your-domain.com/api/v1/workflows/runs/{run_id}/stream?from_sequence=0" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

> **Note:** `WorkflowRunRequest` accepts only `inputs` — there is no `stream` field. Streaming is always consumed via `GET /api/v1/workflows/runs/{run_id}/stream`. The stream endpoint requires an authenticated user with access to the workflow, including for runs started through a webhook; a webhook token is not stream authorization.

## SSE Response Format

### Content Type

**Response headers:**
```
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
X-Accel-Buffering: no
```

### Event Format

**SSE event structure:**
```
event: <event_type>
data: <json_data>

```

**Note**: Each event ends with two newlines (`\n\n`).

### Event Types

| Event Type | Description |
|------------|-------------|
| `message_start` | Stream started, contains conversation_id and message_id |
| `rag_start` | RAG retrieval started |
| `rag_context` | RAG retrieval results with relevant documents |
| `reasoning_start` | Reasoning started (if model supports) |
| `reasoning_delta` | Reasoning content delta |
| `reasoning_end` | Reasoning ended with duration |
| `content_delta` | Response content delta (text token) |
| `tool_call` | Tool call with tool name and the original model-supplied arguments |
| `tool_result` | Tool execution result |
| `media_result` | UI-only media result; inspect `success`, and fetch protected URLs with authentication; it is not LLM replay text |
| `compression_start` | Context compression started; data contains `stage` (`macro`/`micro`) and `trigger` |
| `compression_end` | Context compression finished; data contains `stage` (`macro`/`micro`/`fallback`), `actions`, token counts, and budget metadata |
| `output_truncated` | Output was truncated due to max output token limit |
| `iteration_cap_reached` | The agent reached the max tool-call iteration cap |
| `message_end` | Message ended with token usage statistics |
| `error` | Error occurred |

`rag_start` and `rag_context` are emitted only when retrieval actually runs. If retrieval is not executed, the persisted `rag_context` is `null`; if retrieval runs and returns no contexts, it is `[]`.

Clients should preserve the received event order when rendering the thought-process timeline. Retrieval, compression, reasoning, tool, media, and text events may be interleaved.

`media_result` examples:

```text
event: media_result
data: {"kind":"media.image","success":true,"images":[{"image":{"url":"/api/v1/upload/files/generated-images/2026/09/9a8b7c6d5e4f_55667788.png","asset_ref":"a1b2","format":"png"}}]}

event: media_result
data: {"kind":"media.image","success":false,"images":[],"error":"Image generation failed"}
```

Inspect `success` before rendering. When it is `false`, handle the `error` field and show a failure state instead of treating the event as a successfully generated asset. Fetch URLs in protected categories with the active JWT or API key; do not expose or guess the four-character `asset_ref`.


## Agent Chat Streaming

### Stream Events

**Event sequence:** The following is an example, not a fixed ordering. Preserve the order received from the stream; events may interleave as the Agent works.


```
event: message_start
data: {"conversation_id": "conv-123", "message_id": "msg-456"}

event: rag_start
data: {}

event: rag_context
data: {"contexts": [{"document_name": "Quantum Computing Basics", "content": "...", "score": 0.95}]}

event: content_delta
data: {"delta": "Quantum"}

event: content_delta
data: {"delta": " computing"}

event: content_delta
data: {"delta": " is"}

event: content_delta
data: {"delta": " a revolutionary"}

event: message_end
data: {"usage": {"prompt_tokens": 150, "completion_tokens": 25, "total_tokens": 175}, "timing": {"first_token_ms": 320, "duration_ms": 2300, "tokens_per_second": 10.9}}
```

Agent chat runs are durable (`AgentRun`): events carry an envelope with
`run_id`, `sequence`, `timestamp`, `round_id`, `message_id` and `type` so
reconnects resume via `after_sequence` without duplicates. Run-scoped events:

```
event: run_start
data: {"status": "running", "run_id": "run-123"}

event: run_status
data: {"status": "waiting", "pending_tool_call_id": "call-123", "pending_tool_name": "ask_user", "pending_tool_input": {"questions": [...]}}

event: input_accepted
data: {"kind": "steer", "content": "..."}

event: run_end
data: {"status": "completed", "message_id": "msg-456"}
```

`run_status` reports run lifecycle transitions. A run enters `waiting` when the
model calls `ask_user` or a tool call requires approval.

For `ask_user`, `pending_tool_input` contains the questions; submit answers
through the run answer endpoint to resume.

For approval, `pending_tool_name` stays the original tool name and
`pending_tool_input` is the interaction marker:

```
event: tool_call
data: {"tool_call_id": "call-123", "tool_name": "mcp_delete_task", "tool_display_name": "Delete task", "arguments": {"task_id": "T-42"}}

event: run_status
data: {"status": "waiting", "pending_tool_call_id": "call-123", "pending_tool_name": "mcp_delete_task", "pending_tool_input": {"interaction_kind": "tool_approval", "execution_id": "9f1c2a7e-4b8d-4c61-9a30-2f5b8e1d7c44"}}
```

`tool_call.arguments` is always the original model-supplied arguments object,
including on an approval pause. The approval is bound to that exact call.
Only the caller who started the run can decide it: the signed-in user for an
interactive run, or the same API key for an Agent run started with
`Authorization: Bearer clou_...`. A different key — even one owned by the same
user — cannot decide, and neither can another user, team administrator or
superuser. Read the secret-safe call
projection from `GET /api/v1/tool-executions/{execution_id}`, whose
`parameters_preview` is already redacted:

- `POST /api/v1/tool-executions/{execution_id}/decision` decides the pending
  gate directly. Body: `decision` (`approve` or `reject`), optional `reason`
  (max 2000 characters) and `idempotency_key`. The approvals inbox
  equivalents are `GET /api/v1/tool-approvals` and
  `POST /api/v1/tool-approvals/{request_id}/decision`.
- These routes accept the same JWT or API key as the run. The key must still be
  active, authorized for the Agent (no Agent associations covers all Agents)
  and match the key that started the run, otherwise the decision fails with
  `6504 tool_approval_not_authorized`.
  Reading the execution through `GET /api/v1/tool-executions[/{id}]` gives
  `403 tool_execution_access_denied`, and an unknown or foreign execution id
  returns `404 tool_execution_not_found`. A revoked or expired key fails
  authentication with `401 invalid_api_key` / `api_key_expired`. A key that lost
  its Agent scope is also unauthorized for the decision; the Agent run routes
  return `403 api_key_no_agent_access`.
- An API key's inbox and execution list include only executions whose durable
  AgentRun was submitted by that key. Legacy runs created before run-level key
  binding (no recorded key id) are omitted from lists; if you hold such an
  execution id, direct detail/decision still validates the legacy binding and
  rejects a conflicting key.
- The response returns the immutable decision, `execution_status` and
  `remaining_approvals`. A decision never edits the bound parameters or
  performs the side effect: after every gate is approved, the worker resumes
  the original call and emits a normal `tool_result` for the same
  `tool_call_id`.
- Rejecting, expiry, revocation or a stopped run cancels the call and ends it
  with a tool error; it never becomes an approval. Do not send approval pauses
  to the answers endpoint — it returns `409 pending_interaction_mismatch`.

An API-key Agent run parks in `waiting` exactly like an interactive run; the
stream then closes. After the same key approves, reconnect to
`/agents/{agent_id}/chat/runs/{run_id}/stream?after_sequence=N` and the resumed
worker emits the `tool_result` and continues. The non-streaming `/chat`
endpoint cannot complete an approval-required call; start it through
`/chat/runs` (202) instead.

Embed, legacy-channel and scheduled entrypoints remain non-interactive: they
never wait for approval. A tool whose policy requires confirmation fails closed
with an error `tool_result` and no side effect. Workflow tool calls never create
an approval gate, so a workflow run (including one started with a workflow API
key or a nested call) never pauses for tool approval.

`run_end` is exactly one terminal event per run (`completed | stopped |
failed | interrupted`). Streams stop after a terminal event.

### Event Details

**message_start event:**
```json
{
  "conversation_id": "conv-123",
  "message_id": "msg-456"
}
```

**content_delta event:**
```json
{
  "delta": "Quantum"
}
```

**rag_start event:**
```json
{}
```

**rag_context event (RAG sources):**
```json
{
  "contexts": [
    {
      "document_name": "Quantum Computing Basics",
      "content": "Quantum computing uses quantum mechanics...",
      "score": 0.95
    }
  ]
}
```

**reasoning_start event:**
```json
{}
```

**reasoning_delta event:**
```json
{
  "delta": "Let me think about this..."
}
```

**reasoning_end event:**
```json
{}
```

**tool_call event:**
```json
{
  "tool_name": "web_search",
  "tool_call_id": "call-123",
  "arguments": {
    "query": "latest quantum computing news"
  }
}
```

**tool_result event:**
```json
{
  "tool_call_id": "call-123",
  "tool_name": "web_search",
  "result": {
    "results": [
      {"title": "...", "url": "...", "snippet": "..."}
    ]
  }
}
```

**output_truncated event:**
```json
{}
```

> This event is sent when the response is truncated because it reached the max output token limit configured in model settings.

**error event:**
```json
{
  "code": 1000,
  "msg": "Something went wrong, please try again later"
}
```

The `error` event carries a nonzero error code and a localized message. Generic and timeout failures use `1000` (`UNKNOWN_ERROR`); a `BusinessError` can supply its own code. For agent chat streams, the stream is terminated after the `error` event.

**message_end event:**
```json
{
  "usage": {
    "prompt_tokens": 150,
    "completion_tokens": 25,
    "total_tokens": 175
  },
  "timing": {
    "first_token_ms": 320,
    "duration_ms": 2300,
    "tokens_per_second": 10.9
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `usage.prompt_tokens` | integer | Number of input tokens |
| `usage.completion_tokens` | integer | Number of output tokens |
| `usage.total_tokens` | integer | Total tokens (input + output) |
| `timing.first_token_ms` | integer \| null | Time to first token in milliseconds |
| `timing.duration_ms` | integer | Total generation time in milliseconds |
| `timing.tokens_per_second` | number \| null | Output token generation speed |

## Workflow Streaming

### Stream Events

**Event sequence:**

```
event: workflow_start
data: {"event": "workflow_start", "data": {"workflow_id": "workflow-123", "workflow_name": "Document workflow", "inputs": {"customer_id": "customer-456"}}, "node_id": null, "timestamp": "2026-02-11T14:30:00Z", "sequence": 1}

event: node_start
data: {"event": "node_start", "data": {"node_type": "knowledge_retrieval", "node_label": "Fetch document", "is_streaming": false}, "node_id": "node-1", "timestamp": "2026-02-11T14:30:00Z", "sequence": 2}

event: node_complete
data: {"event": "node_complete", "data": {"outputs": {"text": "Document content..."}, "duration_ms": 100, "node_type": "knowledge_retrieval", "is_streaming": false}, "node_id": "node-1", "timestamp": "2026-02-11T14:30:00Z", "sequence": 3}

event: workflow_waiting
data: {"event": "workflow_waiting", "data": {"node_id": "approval-1"}, "node_id": "approval-1", "timestamp": "2026-02-11T14:30:01Z", "sequence": 4}

event: workflow_complete
data: {"event": "workflow_complete", "data": {"outputs": {"answer": "Done"}, "duration_ms": 83000}, "node_id": null, "timestamp": "2026-02-11T14:31:23Z", "sequence": 5}
```

### Event Types

| Event Type | Description |
|------------|-------------|
| `workflow_start` | Workflow execution started |
| `workflow_complete` | Workflow completed successfully |
| `workflow_waiting` | Run is parked at a pause node; `data.node_id` identifies the node |
| `workflow_error` | Workflow failed |
| `node_start` | Node execution started |
| `node_complete` | Node completed |
| `node_error` | Node failed |
| `node_skip` | Node skipped (branch not taken) |
| `token` | LLM token streaming |
| `chunk` | Generic chunk output |
| `output` | Final output |
| `progress` | Progress update |
| `status` | Status change |
| `iteration_start` | Iteration started |
| `iteration_complete` | Iteration completed |
| `debug` | Debug info (only in debug mode) |

Each SSE event's `data` payload is a JSON object with `event` (event type), `data` (event-specific payload), `node_id` (associated node, if any), `timestamp`, and `sequence` (monotonic sequence number used with the `from_sequence` resume parameter).

### Event Details

Workflow events use the standard SSE envelope. `data.data` holds the event-specific payload (shown here abbreviated).

**Node start event:**
```json
{
  "event": "node_start",
  "data": {},
  "node_id": "node-2",
  "timestamp": "2026-02-11T14:30:01Z",
  "sequence": 4
}
```

**Node complete event:**
```json
{
  "event": "node_complete",
  "data": {
    "outputs": {
      "text": "Document content..."
    },
    "duration_ms": 2500,
    "node_type": "knowledge_retrieval",
    "is_streaming": false
  },
  "node_id": "node-2",
  "timestamp": "2026-02-11T14:30:03Z",
  "sequence": 6
}
```

**Progress event:**
```json
{
  "event": "progress",
  "data": {
    "progress": 0.33,
    "nodes_completed": 2,
    "nodes_total": 6,
    "message": "Fetching document..."
  },
  "node_id": "node-2",
  "timestamp": "2026-02-11T14:30:02Z",
  "sequence": 5
}
```

**Node error event:**
```json
{
  "event": "node_error",
  "data": {
    "error": {
      "message": "HTTP request failed",
      "details": "Connection timeout"
    }
  },
  "node_id": "node-2",
  "timestamp": "2026-02-11T14:30:04Z",
  "sequence": 7
}
```

## Client Implementation

### JavaScript/TypeScript

**Using fetch with streaming:**

```javascript
async function streamChat(message) {
  const response = await fetch(
    'https://your-domain.com/api/v1/agents/agent-123/chat/stream',
    {
      method: 'POST',
      headers: {
        'Authorization': 'Bearer YOUR_API_KEY',
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream',
      },
      body: JSON.stringify({
        message: message,
        conversation_id: null,
        variables: {}
      })
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
        handleEvent(eventType, data);
        eventType = '';
      }
    }
  }
}

function handleEvent(eventType, data) {
  switch (eventType) {
    case 'message_start':
      console.log('Conversation ID:', data.conversation_id);
      break;
    case 'content_delta':
      process.stdout.write(data.delta);
      break;
    case 'rag_context':
      console.log('Sources:', data.contexts?.length);
      break;
    case 'output_truncated':
      console.warn('Output was truncated');
      break;
    case 'message_end':
      console.log('\nDone. Usage:', data.usage);
      if (data.timing) {
        console.log('First token:', data.timing.first_token_ms + 'ms');
        console.log('Total time:', data.timing.duration_ms + 'ms');
        console.log('Speed:', data.timing.tokens_per_second + ' T/s');
      }
      break;
    case 'error':
      console.error('Error:', data.msg);
      break;
  }
}
```

### Python

**Using requests with streaming:**

```python
import requests
import json

def stream_chat(message):
    url = "https://your-domain.com/api/v1/agents/agent-123/chat/stream"
    headers = {
        "Authorization": "Bearer YOUR_API_KEY",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    data = {
        "message": message,
        "conversation_id": None,
        "variables": {},
    }

    response = requests.post(
        url,
        headers=headers,
        json=data,
        stream=True
    )

    event_type = ""
    for line in response.iter_lines():
        if line:
            line = line.decode('utf-8')
            if line.startswith('event: '):
                event_type = line[7:]
            elif line.startswith('data: ') and event_type:
                data = json.loads(line[6:])
                handle_event(event_type, data)
                event_type = ""

def handle_event(event_type, data):
    if event_type == 'message_start':
        print(f"Conversation: {data.get('conversation_id')}")
    elif event_type == 'content_delta':
        print(data.get('delta', ''), end='', flush=True)
    elif event_type == 'rag_context':
        contexts = data.get('contexts', [])
        print(f"\n[Found {len(contexts)} sources]")
    elif event_type == 'output_truncated':
        print("\n[Warning: Output was truncated]")
    elif event_type == 'message_end':
        print(f"\nDone. Usage: {data.get('usage')}")
        timing = data.get('timing')
        if timing:
            print(f"First token: {timing.get('first_token_ms')}ms")
            print(f"Total time: {timing.get('duration_ms')}ms")
            print(f"Speed: {timing.get('tokens_per_second')} T/s")
    elif event_type == 'error':
        print(f"\nError: {data.get('msg')}")

# Usage
stream_chat("Explain quantum computing")
```

**Using httpx with async:**

```python
import httpx
import json
import asyncio

async def stream_chat(message):
    url = "https://your-domain.com/api/v1/agents/agent-123/chat/stream"
    headers = {
        "Authorization": "Bearer YOUR_API_KEY",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    data = {
        "message": message,
        "conversation_id": None,
        "variables": {},
    }

    async with httpx.AsyncClient() as client:
        async with client.stream(
            "POST",
            url,
            headers=headers,
            json=data
        ) as response:
            event_type = ""
            async for line in response.aiter_lines():
                if line.startswith('event: '):
                    event_type = line[7:]
                elif line.startswith('data: ') and event_type:
                    data = json.loads(line[6:])
                    if event_type == 'content_delta':
                        print(data.get('delta', ''), end='', flush=True)
                    elif event_type == 'output_truncated':
                        print("\n[Warning: Output was truncated]")
                    elif event_type == 'message_end':
                        print('\nDone')
                    event_type = ""

# Usage
asyncio.run(stream_chat("Explain quantum computing"))
```

### Go

**Using http.Client:**

```go
package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
)

func streamChat(message string) error {
	url := "https://your-domain.com/api/v1/agents/agent-123/chat/stream"

	payload := map[string]interface{}{
		"message":         message,
		"conversation_id": nil,
		"variables":       map[string]interface{}{},
	}

	payloadBytes, _ := json.Marshal(payload)

	req, err := http.NewRequest("POST", url, strings.NewReader(string(payloadBytes)))
	if err != nil {
		return err
	}

	req.Header.Set("Authorization", "Bearer YOUR_API_KEY")
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "text/event-stream")

	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	scanner := bufio.NewScanner(resp.Body)
	eventType := ""
	for scanner.Scan() {
		line := scanner.Text()
		if strings.HasPrefix(line, "event: ") {
			eventType = line[7:]
		} else if strings.HasPrefix(line, "data: ") && eventType != "" {
			data := line[6:]
			handleEvent(eventType, data)
			eventType = ""
		}
	}

	return scanner.Err()
}

func handleEvent(eventType string, rawData string) {
	switch eventType {
	case "message_start":
		fmt.Println("Stream started")
	case "content_delta":
		var data map[string]string
		json.Unmarshal([]byte(rawData), &data)
		fmt.Print(data["delta"])
	case "output_truncated":
		fmt.Println("\n[Warning: Output was truncated]")
	case "message_end":
		fmt.Println("\nStream ended")
	case "error":
		fmt.Println("\nError occurred")
	}
}

func main() {
	streamChat("Explain quantum computing")
}
```

## Error Handling

### Connection Errors

**Handle connection failures:**

```javascript
eventSource.onerror = (error) => {
  console.error('Connection error:', error);

  // Retry logic
  if (retryCount < maxRetries) {
    setTimeout(() => {
      retryCount++;
      reconnect();
    }, retryDelay);
  } else {
    console.error('Max retries exceeded');
    showError('Connection failed');
  }
};
```

### Stream Errors

**Handle stream-level errors:**

```javascript
// In your event handler
function handleEvent(eventType, data) {
  if (eventType === 'error') {
    // The stream is terminated after an error event
    console.error(`Stream error (${data.code}): ${data.msg}`);
    reconnect();
  }
}
```

**Note:** authentication failures for SSE endpoints are reported as HTTP status codes before the stream starts (e.g. 401/403 for invalid tokens) — not as stream events.

### Timeout Handling

**Implement timeout:**

```javascript
let timeoutId;
let lastEventTime = Date.now();

function handleEvent(eventType, data) {
  // Reset timeout on each event
  clearTimeout(timeoutId);
  lastEventTime = Date.now();
  timeoutId = setTimeout(() => {
    console.error('Stream timeout');
    abortController.abort();
    showError('Response timeout');
  }, 30000); // 30 second timeout

  if (eventType === 'message_end') {
    clearTimeout(timeoutId);
  }
}
```

## Best Practices

### Client-Side

**✅ Do:**
- Handle all event types
- Implement error handling
- Add timeout logic
- Close connections when done
- Implement retry with backoff
- Show progress to users
- Buffer incomplete events

**❌ Don't:**
- Ignore error events
- Leave connections open indefinitely
- Retry immediately on error
- Block UI during streaming
- Parse incomplete JSON
- Forget to close EventSource

### Performance

**✅ Do:**
- Use connection pooling
- Implement backpressure
- Buffer tokens for smooth display
- Debounce UI updates
- Monitor memory usage
- Close unused connections

**❌ Don't:**
- Create multiple connections
- Update UI for every token
- Keep all tokens in memory
- Ignore connection limits
- Stream unnecessarily large responses

## Troubleshooting

### Stream Not Starting

**Problem**: No events received

**Solutions:**
1. Use the correct streaming endpoint (`POST /api/v1/agents/{agent_id}/chat/stream`, `GET /api/v1/workflows/runs/{run_id}/stream`)
2. Verify authentication
3. Check network connectivity
4. Verify endpoint supports streaming
5. Check browser/client SSE support
6. Review server logs

### Incomplete Events

**Problem**: Partial or malformed events

**Solutions:**
1. Buffer incomplete lines
2. Check for `\n\n` delimiter
3. Handle chunked responses
4. Verify JSON parsing
5. Check encoding (UTF-8)

### Connection Drops

**Problem**: Stream disconnects unexpectedly

**Solutions:**
1. Implement auto-reconnect
2. Check network stability
3. Verify timeout settings
4. Monitor server health
5. Check proxy/firewall settings
6. Use keep-alive headers

### High Latency

**Problem**: Slow token delivery

**Solutions:**
1. Check network latency
2. Verify server performance
3. Reduce token buffer size
4. Check rate limiting
5. Monitor server load

## Related Documentation

- [Agents API](./endpoints/agents.md) - Agent chat endpoints
- [Workflows API](./endpoints/workflows.md) - Workflow endpoints
- [Rate Limiting](./rate-limiting.md) - Rate limit details
- [Error Codes](./error-codes.md) - Error reference

---

**Last Updated**: 2026-09-08
