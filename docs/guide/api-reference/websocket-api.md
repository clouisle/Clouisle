# WebSocket API Guide

This guide explains how to use WebSocket connections for real-time communication with Clouisle.

## Overview

WebSocket API provides real-time, bidirectional communication for chat conversations, live updates, and streaming responses. Unlike HTTP polling, WebSocket maintains a persistent connection for instant data exchange.

## Use Cases

- **Real-time Chat**: Stream agent responses token-by-token
- **Live Updates**: Receive instant notifications about events
- **Workflow Monitoring**: Track workflow execution in real-time
- **Document Processing**: Monitor document processing progress
- **Collaborative Editing**: Sync changes across multiple users

## Connection

### WebSocket URL

```
wss://your-domain.com/api/v1/ws
```

**Protocol**: Use `wss://` (secure WebSocket) in production

### Authentication

**Query Parameter:**
```
wss://your-domain.com/api/v1/ws?token=YOUR_JWT_TOKEN
```

**Or Header (if supported by client):**
```
Authorization: Bearer YOUR_JWT_TOKEN
```

### Connection Lifecycle

1. **Connect**: Establish WebSocket connection
2. **Authenticate**: Send auth message (if not using query param)
3. **Subscribe**: Subscribe to channels/events
4. **Exchange**: Send and receive messages
5. **Disconnect**: Close connection gracefully

## Message Format

### Standard Message Structure

```json
{
  "type": "message_type",
  "id": "msg_123",
  "timestamp": "2026-02-11T16:00:00Z",
  "data": {
    "key": "value"
  }
}
```

**Fields:**
- `type`: Message type (e.g., "chat.message", "workflow.update")
- `id`: Unique message ID
- `timestamp`: Message timestamp (ISO 8601)
- `data`: Message payload

### Message Types

**Client → Server:**
- `auth` - Authenticate connection
- `subscribe` - Subscribe to channel
- `unsubscribe` - Unsubscribe from channel
- `chat.send` - Send chat message
- `ping` - Keep-alive ping

**Server → Client:**
- `auth.success` - Authentication successful
- `auth.error` - Authentication failed
- `subscribed` - Subscription confirmed
- `unsubscribed` - Unsubscription confirmed
- `chat.message` - Chat message received
- `chat.token` - Streaming token
- `chat.complete` - Message complete
- `event` - Event notification
- `error` - Error message
- `pong` - Keep-alive pong

## Authentication

### Authenticate After Connection

```json
{
  "type": "auth",
  "data": {
    "token": "YOUR_JWT_TOKEN"
  }
}
```

**Response (Success):**
```json
{
  "type": "auth.success",
  "data": {
    "user_id": "user-123",
    "expires_at": "2026-02-11T16:30:00Z"
  }
}
```

**Response (Error):**
```json
{
  "type": "auth.error",
  "data": {
    "error": "Invalid token"
  }
}
```

## Subscriptions

### Subscribe to Channel

```json
{
  "type": "subscribe",
  "data": {
    "channel": "conversation:conv-123"
  }
}
```

**Response:**
```json
{
  "type": "subscribed",
  "data": {
    "channel": "conversation:conv-123"
  }
}
```

### Available Channels

**Conversation Channels:**
- `conversation:{conversation_id}` - Specific conversation
- `agent:{agent_id}` - All conversations for agent

**Workflow Channels:**
- `workflow:{workflow_id}` - Workflow execution updates
- `workflow:execution:{execution_id}` - Specific execution

**Document Channels:**
- `document:{document_id}` - Document processing updates
- `kb:{kb_id}` - All documents in knowledge base

**Team Channels:**
- `team:{team_id}` - Team-wide events
- `user:{user_id}` - User-specific events

### Unsubscribe from Channel

```json
{
  "type": "unsubscribe",
  "data": {
    "channel": "conversation:conv-123"
  }
}
```

## Chat Messages

### Send Message

```json
{
  "type": "chat.send",
  "data": {
    "conversation_id": "conv-123",
    "message": "Hello, how can you help me?",
    "stream": true
  }
}
```

### Receive Streaming Response

**Token Stream:**
```json
{
  "type": "chat.token",
  "data": {
    "conversation_id": "conv-123",
    "message_id": "msg-456",
    "token": "Hello",
    "index": 0
  }
}
```

```json
{
  "type": "chat.token",
  "data": {
    "conversation_id": "conv-123",
    "message_id": "msg-456",
    "token": " there",
    "index": 1
  }
}
```

**Completion:**
```json
{
  "type": "chat.complete",
  "data": {
    "conversation_id": "conv-123",
    "message_id": "msg-456",
    "full_message": "Hello there! How can I help you today?",
    "metadata": {
      "model": "gpt-4-turbo",
      "tokens": 12,
      "duration": 1.5
    }
  }
}
```

### Receive Non-Streaming Response

```json
{
  "type": "chat.message",
  "data": {
    "conversation_id": "conv-123",
    "message_id": "msg-456",
    "message": "Hello there! How can I help you today?",
    "metadata": {
      "model": "gpt-4-turbo",
      "tokens": 12,
      "duration": 1.5
    }
  }
}
```

## Event Notifications

### Event Message

```json
{
  "type": "event",
  "data": {
    "event": "workflow.completed",
    "resource_id": "wf-exec-123",
    "resource_type": "workflow_execution",
    "details": {
      "status": "success",
      "duration": 45
    }
  }
}
```

## Keep-Alive

### Ping

Send ping every 30 seconds to keep connection alive:

```json
{
  "type": "ping"
}
```

**Response:**
```json
{
  "type": "pong",
  "timestamp": "2026-02-11T16:00:00Z"
}
```

## Error Handling

### Error Message

```json
{
  "type": "error",
  "data": {
    "code": 4001,
    "message": "Subscription failed",
    "details": {
      "channel": "conversation:conv-123",
      "reason": "Permission denied"
    }
  }
}
```

### Error Codes

- `4000`: Bad request
- `4001`: Subscription failed
- `4002`: Authentication required
- `4003`: Permission denied
- `4004`: Resource not found
- `4005`: Rate limit exceeded

## Python Examples

### Basic WebSocket Client

```python
import asyncio
import websockets
import json

async def connect_websocket(token):
    """Connect to WebSocket and handle messages."""
    uri = f"wss://your-domain.com/api/v1/ws?token={token}"

    async with websockets.connect(uri) as websocket:
        print("Connected to WebSocket")

        # Subscribe to conversation
        await websocket.send(json.dumps({
            "type": "subscribe",
            "data": {
                "channel": "conversation:conv-123"
            }
        }))

        # Receive messages
        async for message in websocket:
            data = json.loads(message)
            print(f"Received: {data['type']}")

            if data['type'] == 'chat.token':
                print(data['data']['token'], end='', flush=True)
            elif data['type'] == 'chat.complete':
                print(f"\n\nComplete: {data['data']['full_message']}")

# Usage
asyncio.run(connect_websocket('YOUR_JWT_TOKEN'))
```

### Send Chat Message

```python
async def send_chat_message(websocket, conversation_id, message):
    """Send chat message via WebSocket."""
    await websocket.send(json.dumps({
        "type": "chat.send",
        "data": {
            "conversation_id": conversation_id,
            "message": message,
            "stream": True
        }
    }))

# Usage
async with websockets.connect(uri) as websocket:
    await send_chat_message(websocket, "conv-123", "Hello!")
```

### Handle Streaming Response

```python
async def handle_streaming_response(websocket):
    """Handle streaming chat response."""
    full_message = ""

    async for message in websocket:
        data = json.loads(message)

        if data['type'] == 'chat.token':
            token = data['data']['token']
            full_message += token
            print(token, end='', flush=True)

        elif data['type'] == 'chat.complete':
            print(f"\n\nFull message: {full_message}")
            break

        elif data['type'] == 'error':
            print(f"\nError: {data['data']['message']}")
            break
```

### WebSocket Client with Reconnection

```python
import asyncio
import websockets
import json
from typing import Callable

class WebSocketClient:
    """WebSocket client with auto-reconnection."""

    def __init__(self, url: str, token: str):
        self.url = url
        self.token = token
        self.websocket = None
        self.running = False
        self.handlers = {}

    def on(self, message_type: str, handler: Callable):
        """Register message handler."""
        self.handlers[message_type] = handler

    async def connect(self):
        """Connect to WebSocket."""
        uri = f"{self.url}?token={self.token}"
        self.websocket = await websockets.connect(uri)
        self.running = True
        print("Connected to WebSocket")

    async def disconnect(self):
        """Disconnect from WebSocket."""
        self.running = False
        if self.websocket:
            await self.websocket.close()
            print("Disconnected from WebSocket")

    async def send(self, message_type: str, data: dict):
        """Send message."""
        if not self.websocket:
            raise Exception("Not connected")

        await self.websocket.send(json.dumps({
            "type": message_type,
            "data": data
        }))

    async def subscribe(self, channel: str):
        """Subscribe to channel."""
        await self.send("subscribe", {"channel": channel})

    async def listen(self):
        """Listen for messages with auto-reconnection."""
        while self.running:
            try:
                if not self.websocket:
                    await self.connect()

                async for message in self.websocket:
                    data = json.loads(message)
                    message_type = data['type']

                    # Call registered handler
                    if message_type in self.handlers:
                        await self.handlers[message_type](data['data'])

            except websockets.exceptions.ConnectionClosed:
                print("Connection closed, reconnecting...")
                await asyncio.sleep(5)
            except Exception as e:
                print(f"Error: {e}")
                await asyncio.sleep(5)

# Usage
client = WebSocketClient(
    "wss://your-domain.com/api/v1/ws",
    "YOUR_JWT_TOKEN"
)

# Register handlers
async def on_token(data):
    print(data['token'], end='', flush=True)

async def on_complete(data):
    print(f"\n\nComplete: {data['full_message']}")

client.on('chat.token', on_token)
client.on('chat.complete', on_complete)

# Connect and listen
async def main():
    await client.connect()
    await client.subscribe("conversation:conv-123")
    await client.listen()

asyncio.run(main())
```

## JavaScript Examples

### Basic WebSocket Client

```javascript
const ws = new WebSocket('wss://your-domain.com/api/v1/ws?token=YOUR_JWT_TOKEN');

ws.onopen = () => {
  console.log('Connected to WebSocket');

  // Subscribe to conversation
  ws.send(JSON.stringify({
    type: 'subscribe',
    data: {
      channel: 'conversation:conv-123'
    }
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Received:', data.type);

  if (data.type === 'chat.token') {
    process.stdout.write(data.data.token);
  } else if (data.type === 'chat.complete') {
    console.log('\n\nComplete:', data.data.full_message);
  }
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};

ws.onclose = () => {
  console.log('Disconnected from WebSocket');
};
```

### Send Chat Message

```javascript
function sendChatMessage(ws, conversationId, message) {
  ws.send(JSON.stringify({
    type: 'chat.send',
    data: {
      conversation_id: conversationId,
      message: message,
      stream: true
    }
  }));
}

// Usage
sendChatMessage(ws, 'conv-123', 'Hello!');
```

### WebSocket Client Class

```javascript
class WebSocketClient {
  constructor(url, token) {
    this.url = url;
    this.token = token;
    this.ws = null;
    this.handlers = {};
    this.reconnectDelay = 5000;
  }

  on(messageType, handler) {
    this.handlers[messageType] = handler;
  }

  connect() {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(`${this.url}?token=${this.token}`);

      this.ws.onopen = () => {
        console.log('Connected to WebSocket');
        resolve();
      };

      this.ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        const messageType = data.type;

        if (this.handlers[messageType]) {
          this.handlers[messageType](data.data);
        }
      };

      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        reject(error);
      };

      this.ws.onclose = () => {
        console.log('Connection closed, reconnecting...');
        setTimeout(() => this.connect(), this.reconnectDelay);
      };
    });
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
    }
  }

  send(messageType, data) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      throw new Error('WebSocket not connected');
    }

    this.ws.send(JSON.stringify({
      type: messageType,
      data: data
    }));
  }

  subscribe(channel) {
    this.send('subscribe', { channel });
  }

  unsubscribe(channel) {
    this.send('unsubscribe', { channel });
  }
}

// Usage
const client = new WebSocketClient(
  'wss://your-domain.com/api/v1/ws',
  'YOUR_JWT_TOKEN'
);

// Register handlers
client.on('chat.token', (data) => {
  process.stdout.write(data.token);
});

client.on('chat.complete', (data) => {
  console.log('\n\nComplete:', data.full_message);
});

// Connect
await client.connect();
await client.subscribe('conversation:conv-123');
```

### React WebSocket Hook

```javascript
import { useEffect, useRef, useState } from 'react';

function useWebSocket(url, token) {
  const [connected, setConnected] = useState(false);
  const [messages, setMessages] = useState([]);
  const wsRef = useRef(null);

  useEffect(() => {
    const ws = new WebSocket(`${url}?token=${token}`);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('Connected');
      setConnected(true);
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      setMessages(prev => [...prev, data]);
    };

    ws.onclose = () => {
      console.log('Disconnected');
      setConnected(false);
    };

    return () => {
      ws.close();
    };
  }, [url, token]);

  const send = (messageType, data) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: messageType,
        data: data
      }));
    }
  };

  const subscribe = (channel) => {
    send('subscribe', { channel });
  };

  return { connected, messages, send, subscribe };
}

// Usage in component
function ChatComponent({ conversationId, token }) {
  const { connected, messages, send, subscribe } = useWebSocket(
    'wss://your-domain.com/api/v1/ws',
    token
  );

  useEffect(() => {
    if (connected) {
      subscribe(`conversation:${conversationId}`);
    }
  }, [connected, conversationId]);

  const sendMessage = (message) => {
    send('chat.send', {
      conversation_id: conversationId,
      message: message,
      stream: true
    });
  };

  return (
    <div>
      <div>Status: {connected ? 'Connected' : 'Disconnected'}</div>
      <div>
        {messages.map((msg, i) => (
          <div key={i}>{msg.type}: {JSON.stringify(msg.data)}</div>
        ))}
      </div>
      <button onClick={() => sendMessage('Hello!')}>
        Send Message
      </button>
    </div>
  );
}
```

## Best Practices

### Connection Management

**✅ Do:**
- Implement auto-reconnection
- Handle connection errors gracefully
- Send keep-alive pings
- Close connections properly
- Monitor connection state
- Use connection pooling for multiple channels
- Implement exponential backoff for reconnection

**❌ Don't:**
- Ignore connection errors
- Skip keep-alive pings
- Leave connections open indefinitely
- Create multiple connections unnecessarily
- Reconnect immediately after failure
- Forget to clean up on disconnect

### Message Handling

**✅ Do:**
- Validate message format
- Handle all message types
- Process messages asynchronously
- Implement message queuing
- Log important messages
- Handle partial messages
- Implement timeout for responses

**❌ Don't:**
- Assume message format
- Ignore unknown message types
- Block on message processing
- Process messages synchronously
- Skip message logging
- Expect complete messages always
- Wait indefinitely for responses

### Performance

**✅ Do:**
- Use binary frames for large data
- Compress messages when possible
- Batch multiple updates
- Implement message throttling
- Monitor memory usage
- Clean up old messages
- Use efficient JSON parsing

**❌ Don't:**
- Send large text messages
- Skip compression
- Send updates individually
- Send unlimited messages
- Keep all messages in memory
- Accumulate messages indefinitely
- Use slow JSON parsers

### Security

**✅ Do:**
- Use WSS (secure WebSocket)
- Validate authentication tokens
- Implement rate limiting
- Validate all incoming data
- Use CORS properly
- Monitor for abuse
- Log security events

**❌ Don't:**
- Use WS (insecure)
- Skip token validation
- Allow unlimited messages
- Trust incoming data
- Ignore CORS
- Skip abuse monitoring
- Forget security logging

## Troubleshooting

### Connection Failed

**Problem:** Cannot establish WebSocket connection

**Solutions:**
1. Check WebSocket URL is correct
2. Verify authentication token
3. Check firewall/proxy settings
4. Ensure WSS is supported
5. Review server logs

### Connection Drops

**Problem:** Connection drops frequently

**Solutions:**
1. Implement keep-alive pings
2. Check network stability
3. Increase timeout values
4. Implement auto-reconnection
5. Monitor server health

### Messages Not Received

**Problem:** Not receiving expected messages

**Solutions:**
1. Verify subscription to correct channel
2. Check message handlers are registered
3. Review server logs
4. Test with simple messages
5. Check permissions

### High Latency

**Problem:** Messages arrive with delay

**Solutions:**
1. Check network latency
2. Optimize message size
3. Use compression
4. Check server load
5. Monitor connection quality

## Related Documentation

- [Chat API](./endpoints/conversations.md) - Chat endpoints
- [Streaming](./streaming.md) - SSE streaming
- [Webhooks](./webhooks-guide.md) - Webhook events
- [Authentication](./authentication.md) - Authentication methods

---

**Last Updated**: 2026-02-11
