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

**Enable streaming in workflow execution:**

```bash
curl -X POST "https://your-domain.com/api/v1/workflows/{workflow_id}/run" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": {...},
    "stream": true
  }'
```

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
| `tool_call` | Tool call with tool name and arguments |
| `tool_result` | Tool execution result |
| `user_input_request` | Agent requests user input with predefined options |
| `output_truncated` | Output was truncated due to max output token limit |
| `message_end` | Message ended with token usage statistics |
| `error` | Error occurred |

## Agent Chat Streaming

### Stream Events

**Event sequence:**

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
  "code": 6102,
  "msg": "Model API error"
}
```

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
event: start
data: {"run_id": "run-789", "workflow_id": "workflow-123"}

event: node_start
data: {"node_id": "node-1", "node_type": "start"}

event: node_complete
data: {"node_id": "node-1", "duration": 0.1}

event: node_start
data: {"node_id": "node-2", "node_type": "http_request"}

event: progress
data: {"progress": 0.33, "message": "Fetching document..."}

event: node_complete
data: {"node_id": "node-2", "duration": 2.5, "output": {...}}

event: end
data: {"status": "completed", "duration": 83, "output": {...}}
```

### Event Details

**Node start event:**
```json
{
  "type": "node_start",
  "node_id": "node-2",
  "node_type": "http_request",
  "node_name": "Fetch Document",
  "timestamp": "2026-02-11T14:30:01Z"
}
```

**Node complete event:**
```json
{
  "type": "node_complete",
  "node_id": "node-2",
  "status": "completed",
  "duration": 2.5,
  "output": {
    "text": "Document content...",
    "size": 2500
  }
}
```

**Progress event:**
```json
{
  "type": "progress",
  "progress": 0.33,
  "nodes_completed": 2,
  "nodes_total": 6,
  "message": "Fetching document..."
}
```

**Node error event:**
```json
{
  "type": "node_error",
  "node_id": "node-2",
  "error": {
    "message": "HTTP request failed",
    "details": "Connection timeout"
  }
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
    switch (data.code) {
      case 2002:
        // Token expired - refresh and retry
        refreshToken().then(() => reconnect());
        break;
      case 5400:
        // Rate limit - wait and retry
        setTimeout(() => reconnect(), 5000);
        break;
      default:
        // Other error - show to user
        showError(data.msg);
    }
  }
}
```

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
1. Check `stream: true` in request
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

**Last Updated**: 2026-03-15
