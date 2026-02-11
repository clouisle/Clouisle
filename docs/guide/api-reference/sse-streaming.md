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

**Enable streaming in chat request:**

```bash
curl -X POST "https://your-domain.com/api/v1/agents/{agent_id}/chat" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Explain quantum computing",
    "stream": true
  }'
```

**Key parameter:**
- `stream: true` - Enable streaming mode

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
| `start` | Stream started |
| `token` | New token/chunk of text |
| `source` | RAG source citation |
| `tool_call` | Tool invocation |
| `tool_result` | Tool execution result |
| `error` | Error occurred |
| `end` | Stream completed |

## Agent Chat Streaming

### Stream Events

**Event sequence:**

```
event: start
data: {"conversation_id": "conv-123", "message_id": "msg-456"}

event: token
data: {"content": "Quantum"}

event: token
data: {"content": " computing"}

event: token
data: {"content": " is"}

event: source
data: {"document_id": "doc-789", "score": 0.95, "content": "..."}

event: token
data: {"content": " a"}

event: token
data: {"content": " revolutionary"}

event: end
data: {"tokens_used": {"total": 175}, "response_time": 2.3}
```

### Event Details

**Start event:**
```json
{
  "type": "start",
  "conversation_id": "conv-123",
  "message_id": "msg-456",
  "timestamp": "2026-02-11T14:30:00Z"
}
```

**Token event:**
```json
{
  "type": "token",
  "content": "Quantum",
  "index": 0
}
```

**Source event (RAG):**
```json
{
  "type": "source",
  "source": {
    "document_id": "doc-789",
    "document_name": "Quantum Computing Basics",
    "chunk_id": "chunk-012",
    "content": "Quantum computing uses quantum mechanics...",
    "score": 0.95
  }
}
```

**Tool call event:**
```json
{
  "type": "tool_call",
  "tool": "web_search",
  "arguments": {
    "query": "latest quantum computing news"
  }
}
```

**Tool result event:**
```json
{
  "type": "tool_result",
  "tool": "web_search",
  "result": {
    "results": [
      {"title": "...", "url": "...", "snippet": "..."}
    ]
  }
}
```

**Error event:**
```json
{
  "type": "error",
  "error": {
    "code": 6102,
    "message": "Model API error",
    "details": "Rate limit exceeded"
  }
}
```

**End event:**
```json
{
  "type": "end",
  "tokens_used": {
    "prompt": 150,
    "completion": 25,
    "total": 175
  },
  "response_time": 2.3,
  "finish_reason": "stop"
}
```

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

**Using EventSource API:**

```javascript
const eventSource = new EventSource(
  'https://your-domain.com/api/v1/agents/agent-123/chat',
  {
    headers: {
      'Authorization': 'Bearer YOUR_TOKEN'
    }
  }
);

// Handle different event types
eventSource.addEventListener('start', (event) => {
  const data = JSON.parse(event.data);
  console.log('Stream started:', data);
});

eventSource.addEventListener('token', (event) => {
  const data = JSON.parse(event.data);
  // Append token to UI
  appendToken(data.content);
});

eventSource.addEventListener('source', (event) => {
  const data = JSON.parse(event.data);
  // Display source citation
  showSource(data.source);
});

eventSource.addEventListener('end', (event) => {
  const data = JSON.parse(event.data);
  console.log('Stream ended:', data);
  eventSource.close();
});

eventSource.addEventListener('error', (event) => {
  console.error('Stream error:', event);
  eventSource.close();
});

// Handle connection errors
eventSource.onerror = (error) => {
  console.error('Connection error:', error);
  eventSource.close();
};
```

**Using fetch with streaming:**

```javascript
async function streamChat(message) {
  const response = await fetch(
    'https://your-domain.com/api/v1/agents/agent-123/chat',
    {
      method: 'POST',
      headers: {
        'Authorization': 'Bearer YOUR_TOKEN',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        message: message,
        stream: true
      })
    }
  );

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();

    if (done) break;

    const chunk = decoder.decode(value);
    const lines = chunk.split('\n\n');

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = JSON.parse(line.slice(6));
        handleEvent(data);
      }
    }
  }
}

function handleEvent(data) {
  switch (data.type) {
    case 'start':
      console.log('Stream started');
      break;
    case 'token':
      appendToken(data.content);
      break;
    case 'source':
      showSource(data.source);
      break;
    case 'end':
      console.log('Stream ended');
      break;
    case 'error':
      console.error('Error:', data.error);
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
    url = "https://your-domain.com/api/v1/agents/agent-123/chat"
    headers = {
        "Authorization": "Bearer YOUR_TOKEN",
        "Content-Type": "application/json"
    }
    data = {
        "message": message,
        "stream": True
    }

    response = requests.post(
        url,
        headers=headers,
        json=data,
        stream=True
    )

    for line in response.iter_lines():
        if line:
            line = line.decode('utf-8')
            if line.startswith('data: '):
                data = json.loads(line[6:])
                handle_event(data)

def handle_event(data):
    event_type = data.get('type')

    if event_type == 'start':
        print('Stream started')
    elif event_type == 'token':
        print(data['content'], end='', flush=True)
    elif event_type == 'source':
        print(f"\n[Source: {data['source']['document_name']}]")
    elif event_type == 'end':
        print('\nStream ended')
    elif event_type == 'error':
        print(f"\nError: {data['error']['message']}")

# Usage
stream_chat("Explain quantum computing")
```

**Using httpx with async:**

```python
import httpx
import json
import asyncio

async def stream_chat(message):
    url = "https://your-domain.com/api/v1/agents/agent-123/chat"
    headers = {
        "Authorization": "Bearer YOUR_TOKEN",
        "Content-Type": "application/json"
    }
    data = {
        "message": message,
        "stream": True
    }

    async with httpx.AsyncClient() as client:
        async with client.stream(
            "POST",
            url,
            headers=headers,
            json=data
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith('data: '):
                    data = json.loads(line[6:])
                    await handle_event(data)

async def handle_event(data):
    event_type = data.get('type')

    if event_type == 'token':
        print(data['content'], end='', flush=True)
    elif event_type == 'end':
        print('\nStream ended')

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

type StreamEvent struct {
    Type    string          `json:"type"`
    Content string          `json:"content,omitempty"`
    Source  json.RawMessage `json:"source,omitempty"`
}

func streamChat(message string) error {
    url := "https://your-domain.com/api/v1/agents/agent-123/chat"

    payload := map[string]interface{}{
        "message": message,
        "stream":  true,
    }

    payloadBytes, _ := json.Marshal(payload)

    req, err := http.NewRequest("POST", url, strings.NewReader(string(payloadBytes)))
    if err != nil {
        return err
    }

    req.Header.Set("Authorization", "Bearer YOUR_TOKEN")
    req.Header.Set("Content-Type", "application/json")

    client := &http.Client{}
    resp, err := client.Do(req)
    if err != nil {
        return err
    }
    defer resp.Body.Close()

    scanner := bufio.NewScanner(resp.Body)
    for scanner.Scan() {
        line := scanner.Text()
        if strings.HasPrefix(line, "data: ") {
            data := line[6:]
            var event StreamEvent
            if err := json.Unmarshal([]byte(data), &event); err != nil {
                continue
            }
            handleEvent(event)
        }
    }

    return scanner.Err()
}

func handleEvent(event StreamEvent) {
    switch event.Type {
    case "start":
        fmt.Println("Stream started")
    case "token":
        fmt.Print(event.Content)
    case "end":
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
eventSource.addEventListener('error', (event) => {
  const data = JSON.parse(event.data);

  switch (data.error.code) {
    case 2002:
      // Token expired - refresh and retry
      refreshToken().then(() => reconnect());
      break;
    case 5400:
      // Rate limit - wait and retry
      setTimeout(() => reconnect(), data.error.retry_after * 1000);
      break;
    default:
      // Other error - show to user
      showError(data.error.message);
  }
});
```

### Timeout Handling

**Implement timeout:**

```javascript
let timeoutId;

eventSource.addEventListener('token', (event) => {
  // Reset timeout on each token
  clearTimeout(timeoutId);
  timeoutId = setTimeout(() => {
    console.error('Stream timeout');
    eventSource.close();
    showError('Response timeout');
  }, 30000); // 30 second timeout
});

eventSource.addEventListener('end', (event) => {
  clearTimeout(timeoutId);
});
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

**Last Updated**: 2026-02-11
