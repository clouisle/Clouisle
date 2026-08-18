# API Quick Start Guide

Get started with the Clouisle API in minutes. This guide walks you through making your first API calls.

## Prerequisites

- Clouisle account
- API token or API key
- HTTP client (curl, Python requests, or JavaScript fetch)
- An existing team (agents belong to a team; `team_id` is a required UUID)

## Get Your API Token

### Option 1: JWT Token (User Authentication)

Login with your username and password to obtain a JWT:

```bash
curl -X POST "https://your-domain.com/api/v1/login/access-token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=your_username&password=your_password"
```

**Response:**
```json
{
  "code": 0,
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer"
  },
  "msg": "Login successful"
}
```

The token is valid for the `session_timeout_days` site setting (default **30 days**, configurable by administrators). There is no refresh endpoint — login again when it expires. Logout is `POST /api/v1/logout`.

### Option 2: API Key (Long-lived)

1. Log in to Clouisle
2. Go to **Settings** → **API Keys**
3. Click **Create API Key** (optionally restrict it to specific agents/workflows)
4. Copy your API key — the full key `clou_...` (68 characters) is shown only once

## Your First API Call

### Using curl

```bash
# Set your token
export CLOUISLE_TOKEN="your-token-here"
export API_BASE_URL="https://your-domain.com"

# List agents
curl -X GET "$API_BASE_URL/api/v1/agents" \
  -H "Authorization: Bearer $CLOUISLE_TOKEN" \
  -H "Content-Type: application/json"
```

**Response (paginated):**
```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "Customer Support Agent",
        "model": {
          "id": "550e8400-e29b-41d4-a716-446655440001",
          "name": "gpt-4o",
          "provider": "openai",
          "model_id": "gpt-4o"
        },
        "status": "draft",
        "visibility": "team"
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20
  },
  "msg": "success"
}
```

The `model` field is a `ModelInfo` object (id, name, provider, model_id), not a plain string. List filters: `team_id`, `status`, `visibility`, `keyword`, `own_only`.

### Using Python

```python
import requests
import os

# Configuration
API_BASE_URL = "https://your-domain.com"
TOKEN = os.getenv("CLOUISLE_TOKEN")

# Make request
response = requests.get(
    f"{API_BASE_URL}/api/v1/agents",
    headers={
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }
)

# Parse response
result = response.json()
if result['code'] == 0:
    agents = result['data']['items']
    print(f"Found {len(agents)} agents")
    for agent in agents:
        print(f"- {agent['name']} ({agent['id']})")
else:
    print(f"Error: {result['msg']}")
```

### Using JavaScript

```javascript
const API_BASE_URL = 'https://your-domain.com';
const TOKEN = process.env.CLOUISLE_TOKEN;

// Make request
const response = await fetch(`${API_BASE_URL}/api/v1/agents`, {
  headers: {
    'Authorization': `Bearer ${TOKEN}`,
    'Content-Type': 'application/json'
  }
});

// Parse response
const result = await response.json();
if (result.code === 0) {
  const agents = result.data.items;
  console.log(`Found ${agents.length} agents`);
  agents.forEach(agent => {
    console.log(`- ${agent.name} (${agent.id})`);
  });
} else {
  console.error(`Error: ${result.msg}`);
}
```

## Common Operations

### 1. Create an Agent

`team_id` is required (UUID). `model_id` references a **TeamModel** authorization record (UUID), and `model` is a `ModelInfo` object in responses.

```bash
curl -X POST "$API_BASE_URL/api/v1/agents" \
  -H "Authorization: Bearer $CLOUISLE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My First Agent",
    "team_id": "550e8400-e29b-41d4-a716-446655440000",
    "model_id": "550e8400-e29b-41d4-a716-446655440001",
    "system_prompt": "You are a helpful assistant.",
    "max_iterations": 5,
    "visibility": "team"
  }'
```

**Python:**
```python
agent = requests.post(
    f"{API_BASE_URL}/api/v1/agents",
    headers={"Authorization": f"Bearer {TOKEN}"},
    json={
        "name": "My First Agent",
        "team_id": "550e8400-e29b-41d4-a716-446655440000",
        "model_id": "550e8400-e29b-41d4-a716-446655440001",
        "system_prompt": "You are a helpful assistant.",
        "max_iterations": 5,
        "visibility": "team"
    }
).json()

agent_id = agent['data']['id']
print(f"Created agent: {agent_id}")
```

**JavaScript:**
```javascript
const response = await fetch(`${API_BASE_URL}/api/v1/agents`, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${TOKEN}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    name: 'My First Agent',
    team_id: '550e8400-e29b-41d4-a716-446655440000',
    model_id: '550e8400-e29b-41d4-a716-446655440001',
    system_prompt: 'You are a helpful assistant.',
    max_iterations: 5,
    visibility: 'team'
  })
});

const agent = await response.json();
const agentId = agent.data.id;
console.log(`Created agent: ${agentId}`);
```

### 2. Chat with an Agent

There is no separate "create conversation" endpoint — the chat endpoint implicitly creates a conversation for the user and returns its ID. Conversations are later listed via `GET /api/v1/conversations` and read via `GET /api/v1/conversations/{conversation_id}` (which embeds the messages).

```bash
curl -X POST "$API_BASE_URL/api/v1/agents/$AGENT_ID/chat" \
  -H "Authorization: Bearer $CLOUISLE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Hello! How can you help me?",
    "conversation_id": null,
    "variables": {}
  }'
```

**Python:**
```python
message = requests.post(
    f"{API_BASE_URL}/api/v1/agents/{agent_id}/chat",
    headers={"Authorization": f"Bearer {TOKEN}"},
    json={
        "message": "Hello! How can you help me?",
        "conversation_id": None,
        "variables": {}
    }
).json()

conversation_id = message['data']['conversation_id']
response_text = message['data']['message']['content']
print(f"Conversation: {conversation_id}")
print(f"Agent: {response_text}")
```

**JavaScript:**
```javascript
const response = await fetch(
  `${API_BASE_URL}/api/v1/agents/${agentId}/chat`,
  {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${TOKEN}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      message: 'Hello! How can you help me?',
      conversation_id: null,
      variables: {}
    })
  }
);

const message = await response.json();
const conversationId = message.data.conversation_id;
const responseText = message.data.message.content;
console.log(`Agent: ${responseText}`);
```

### 3. Continue a Conversation

Pass the `conversation_id` returned by the previous chat call to keep the context:

```python
response = requests.post(
    f"{API_BASE_URL}/api/v1/agents/{agent_id}/chat",
    headers={"Authorization": f"Bearer {TOKEN}"},
    json={
        "message": "Tell me more",
        "conversation_id": conversation_id,
        "variables": {}
    }
).json()
```

### 4. Get Conversation History

Conversation messages are embedded in the conversation detail response:

```bash
curl -X GET "$API_BASE_URL/api/v1/conversations/$CONVERSATION_ID" \
  -H "Authorization: Bearer $CLOUISLE_TOKEN"
```

**Python:**
```python
conversation = requests.get(
    f"{API_BASE_URL}/api/v1/conversations/{conversation_id}",
    headers={"Authorization": f"Bearer {TOKEN}"}
).json()

for msg in conversation['data']['messages']:
    role = msg['role']
    content = msg['content']
    print(f"{role}: {content}")
```

### 5. Stream a Chat Response (SSE)

For token-by-token streaming, use the SSE endpoint:

```bash
curl -N -X POST "$API_BASE_URL/api/v1/agents/$AGENT_ID/chat/stream" \
  -H "Authorization: Bearer $CLOUISLE_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "message": "Tell me a story",
    "conversation_id": null,
    "variables": {}
  }'
```

Events include `message_start`, `content_delta`, `reasoning_delta`, `tool_call`, `tool_result`, `message_end`, and `error`. See [SSE Streaming](./sse-streaming.md) for the full event reference.

## Error Handling

Always handle errors properly. Validation failures return HTTP 422 with `data.errors` as a field → messages dictionary:

```python
try:
    response = api.post('/api/v1/agents', json={...})
    if response['code'] != 0:
        print(f"API Error: {response['msg']}")
        print(f"Error Code: {response['code']}")
        if response['code'] == 1001:
            print(f"Field errors: {response['data']['errors']}")
    else:
        agent = response['data']
        print(f"Success: {agent['id']}")

except requests.exceptions.RequestException as e:
    print(f"Network Error: {e}")
```

```javascript
try {
  const response = await api.post('/api/v1/agents', {...});
  if (response.code !== 0) {
    console.error(`API Error: ${response.msg}`);
    console.error(`Error Code: ${response.code}`);
  } else {
    const agent = response.data;
    console.log(`Success: ${agent.id}`);
  }
} catch (error) {
  console.error(`Network Error: ${error.message}`);
}
```

## Next Steps

Now that you've made your first API calls, explore more features:

1. **Knowledge Bases**: Upload documents and enable RAG
   - [Knowledge Base API](./endpoints/knowledge-bases.md)
   - [Document Upload Guide](./file-uploads.md)

2. **Workflows**: Automate tasks with visual workflows
   - [Workflow API](./endpoints/workflows.md)

3. **Streaming**: Real-time chat and workflow output
   - [SSE Streaming](./sse-streaming.md)

4. **Webhooks**: Outbound notifications and inbound workflow triggers
   - [Webhooks Guide](./webhooks-guide.md)

## Resources

- **API Reference**: [Complete API Documentation](./endpoints/)
- **Best Practices**: [API Best Practices](./api-best-practices.md)
- **Error Codes**: [Error Codes](./error-codes.md)
- **Examples**: [HTTP Examples](./sdk-examples.md)

## Getting Help

- **OpenAPI**: Interactive docs are served at `/docs` (Swagger UI) and `/api/v1/openapi.json`
- **Documentation**: [docs.clouisle.com](https://docs.clouisle.com)
- **Support**: support@clouisle.com

---

**Last Updated**: 2026-08-14
