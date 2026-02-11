# API Quick Start Guide

Get started with the Clouisle API in minutes. This guide walks you through making your first API calls.

## Prerequisites

- Clouisle account
- API token or API key
- HTTP client (curl, Python requests, or JavaScript fetch)

## Get Your API Token

### Option 1: JWT Token (User Authentication)

1. Log in to Clouisle
2. Go to **Settings** → **API Keys**
3. Click **Generate Token**
4. Copy your token (expires in 30 minutes)

### Option 2: API Key (Long-lived)

1. Log in to Clouisle
2. Go to **Settings** → **API Keys**
3. Click **Create API Key**
4. Select scopes (permissions)
5. Copy your API key (keep it secure!)

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

**Response:**
```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "agent-123",
        "name": "Customer Support Agent",
        "model": "gpt-4-turbo",
        "status": "active"
      }
    ],
    "total": 1
  },
  "msg": "success"
}
```

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

```bash
curl -X POST "$API_BASE_URL/api/v1/agents" \
  -H "Authorization: Bearer $CLOUISLE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My First Agent",
    "model": "gpt-4-turbo",
    "system_prompt": "You are a helpful assistant.",
    "temperature": 0.7,
    "max_tokens": 2000
  }'
```

**Python:**
```python
agent = requests.post(
    f"{API_BASE_URL}/api/v1/agents",
    headers={"Authorization": f"Bearer {TOKEN}"},
    json={
        "name": "My First Agent",
        "model": "gpt-4-turbo",
        "system_prompt": "You are a helpful assistant.",
        "temperature": 0.7,
        "max_tokens": 2000
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
    model: 'gpt-4-turbo',
    system_prompt: 'You are a helpful assistant.',
    temperature: 0.7,
    max_tokens: 2000
  })
});

const agent = await response.json();
const agentId = agent.data.id;
console.log(`Created agent: ${agentId}`);
```

### 2. Start a Conversation

```bash
curl -X POST "$API_BASE_URL/api/v1/conversations" \
  -H "Authorization: Bearer $CLOUISLE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agent-123",
    "title": "My First Conversation"
  }'
```

**Python:**
```python
conversation = requests.post(
    f"{API_BASE_URL}/api/v1/conversations",
    headers={"Authorization": f"Bearer {TOKEN}"},
    json={
        "agent_id": agent_id,
        "title": "My First Conversation"
    }
).json()

conversation_id = conversation['data']['id']
print(f"Started conversation: {conversation_id}")
```

**JavaScript:**
```javascript
const response = await fetch(`${API_BASE_URL}/api/v1/conversations`, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${TOKEN}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    agent_id: agentId,
    title: 'My First Conversation'
  })
});

const conversation = await response.json();
const conversationId = conversation.data.id;
console.log(`Started conversation: ${conversationId}`);
```

### 3. Send a Message

```bash
curl -X POST "$API_BASE_URL/api/v1/conversations/conv-123/messages" \
  -H "Authorization: Bearer $CLOUISLE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Hello! How can you help me?"
  }'
```

**Python:**
```python
message = requests.post(
    f"{API_BASE_URL}/api/v1/conversations/{conversation_id}/messages",
    headers={"Authorization": f"Bearer {TOKEN}"},
    json={
        "content": "Hello! How can you help me?"
    }
).json()

response_text = message['data']['response']
print(f"Agent: {response_text}")
```

**JavaScript:**
```javascript
const response = await fetch(
  `${API_BASE_URL}/api/v1/conversations/${conversationId}/messages`,
  {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${TOKEN}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      content: 'Hello! How can you help me?'
    })
  }
);

const message = await response.json();
const responseText = message.data.response;
console.log(`Agent: ${responseText}`);
```

### 4. Get Conversation History

```bash
curl -X GET "$API_BASE_URL/api/v1/conversations/conv-123/messages" \
  -H "Authorization: Bearer $CLOUISLE_TOKEN"
```

**Python:**
```python
messages = requests.get(
    f"{API_BASE_URL}/api/v1/conversations/{conversation_id}/messages",
    headers={"Authorization": f"Bearer {TOKEN}"}
).json()

for msg in messages['data']['items']:
    role = msg['role']
    content = msg['content']
    print(f"{role}: {content}")
```

**JavaScript:**
```javascript
const response = await fetch(
  `${API_BASE_URL}/api/v1/conversations/${conversationId}/messages`,
  {
    headers: {
      'Authorization': `Bearer ${TOKEN}`
    }
  }
);

const messages = await response.json();
messages.data.items.forEach(msg => {
  console.log(`${msg.role}: ${msg.content}`);
});
```

## Complete Example

### Python Complete Example

```python
import requests
import os

class CloudisleAPI:
    """Simple Clouisle API client."""

    def __init__(self, base_url, token):
        self.base_url = base_url
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        })

    def get(self, endpoint, **kwargs):
        response = self.session.get(f"{self.base_url}{endpoint}", **kwargs)
        return response.json()

    def post(self, endpoint, **kwargs):
        response = self.session.post(f"{self.base_url}{endpoint}", **kwargs)
        return response.json()

# Initialize client
api = CloudisleAPI(
    base_url="https://your-domain.com",
    token=os.getenv("CLOUISLE_TOKEN")
)

# 1. Create an agent
print("Creating agent...")
agent = api.post('/api/v1/agents', json={
    'name': 'Quick Start Agent',
    'model': 'gpt-4-turbo',
    'system_prompt': 'You are a helpful assistant.',
    'temperature': 0.7
})
agent_id = agent['data']['id']
print(f"✓ Created agent: {agent_id}")

# 2. Start a conversation
print("\nStarting conversation...")
conversation = api.post('/api/v1/conversations', json={
    'agent_id': agent_id,
    'title': 'Quick Start Conversation'
})
conversation_id = conversation['data']['id']
print(f"✓ Started conversation: {conversation_id}")

# 3. Send messages
print("\nSending messages...")
messages = [
    "Hello! What can you do?",
    "Tell me a joke.",
    "Thank you!"
]

for user_message in messages:
    print(f"\nUser: {user_message}")

    response = api.post(
        f'/api/v1/conversations/{conversation_id}/messages',
        json={'content': user_message}
    )

    agent_response = response['data']['response']
    print(f"Agent: {agent_response}")

# 4. Get conversation history
print("\n\nConversation History:")
print("-" * 50)
history = api.get(f'/api/v1/conversations/{conversation_id}/messages')

for msg in history['data']['items']:
    role = msg['role'].upper()
    content = msg['content']
    print(f"{role}: {content}\n")

print("✓ Quick start complete!")
```

### JavaScript Complete Example

```javascript
class CloudisleAPI {
  constructor(baseUrl, token) {
    this.baseUrl = baseUrl;
    this.token = token;
  }

  async get(endpoint) {
    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      headers: {
        'Authorization': `Bearer ${this.token}`,
        'Content-Type': 'application/json'
      }
    });
    return response.json();
  }

  async post(endpoint, data) {
    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(data)
    });
    return response.json();
  }
}

async function quickStart() {
  // Initialize client
  const api = new CloudisleAPI(
    'https://your-domain.com',
    process.env.CLOUISLE_TOKEN
  );

  // 1. Create an agent
  console.log('Creating agent...');
  const agent = await api.post('/api/v1/agents', {
    name: 'Quick Start Agent',
    model: 'gpt-4-turbo',
    system_prompt: 'You are a helpful assistant.',
    temperature: 0.7
  });
  const agentId = agent.data.id;
  console.log(`✓ Created agent: ${agentId}`);

  // 2. Start a conversation
  console.log('\nStarting conversation...');
  const conversation = await api.post('/api/v1/conversations', {
    agent_id: agentId,
    title: 'Quick Start Conversation'
  });
  const conversationId = conversation.data.id;
  console.log(`✓ Started conversation: ${conversationId}`);

  // 3. Send messages
  console.log('\nSending messages...');
  const messages = [
    'Hello! What can you do?',
    'Tell me a joke.',
    'Thank you!'
  ];

  for (const userMessage of messages) {
    console.log(`\nUser: ${userMessage}`);

    const response = await api.post(
      `/api/v1/conversations/${conversationId}/messages`,
      { content: userMessage }
    );

    const agentResponse = response.data.response;
    console.log(`Agent: ${agentResponse}`);
  }

  // 4. Get conversation history
  console.log('\n\nConversation History:');
  console.log('-'.repeat(50));
  const history = await api.get(
    `/api/v1/conversations/${conversationId}/messages`
  );

  history.data.items.forEach(msg => {
    const role = msg.role.toUpperCase();
    const content = msg.content;
    console.log(`${role}: ${content}\n`);
  });

  console.log('✓ Quick start complete!');
}

// Run
quickStart().catch(console.error);
```

## Streaming Responses

For real-time token-by-token responses, use Server-Sent Events (SSE):

### Python with SSE

```python
import requests
import json

def stream_message(conversation_id, message):
    """Send message and stream response."""
    url = f"{API_BASE_URL}/api/v1/conversations/{conversation_id}/messages/stream"

    response = requests.post(
        url,
        headers={
            'Authorization': f'Bearer {TOKEN}',
            'Content-Type': 'application/json'
        },
        json={'content': message},
        stream=True
    )

    print("Agent: ", end='', flush=True)

    for line in response.iter_lines():
        if line:
            line = line.decode('utf-8')
            if line.startswith('data: '):
                data = json.loads(line[6:])
                if data['type'] == 'token':
                    print(data['token'], end='', flush=True)
                elif data['type'] == 'done':
                    print("\n")
                    break

# Usage
stream_message(conversation_id, "Tell me a story")
```

### JavaScript with SSE

```javascript
async function streamMessage(conversationId, message) {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/conversations/${conversationId}/messages/stream`,
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${TOKEN}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ content: message })
    }
  );

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  process.stdout.write('Agent: ');

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    const chunk = decoder.decode(value);
    const lines = chunk.split('\n');

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = JSON.parse(line.slice(6));
        if (data.type === 'token') {
          process.stdout.write(data.token);
        } else if (data.type === 'done') {
          console.log('\n');
          return;
        }
      }
    }
  }
}

// Usage
await streamMessage(conversationId, 'Tell me a story');
```

## Error Handling

Always handle errors properly:

```python
try:
    response = api.post('/api/v1/agents', json={...})
    if response['code'] != 0:
        print(f"API Error: {response['msg']}")
        print(f"Error Code: {response['code']}")
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
   - [Knowledge Base API](./endpoints/knowledge-base.md)
   - [Document Upload Guide](./file-uploads.md)

2. **Workflows**: Automate tasks with visual workflows
   - [Workflow API](./endpoints/workflows.md)
   - [Workflow Nodes](../user-guide/workflows/workflow-nodes.md)

3. **Tools**: Extend agents with custom tools
   - [Tools API](./endpoints/tools.md)
   - [Tool Development](../user-guide/tools/tool-development.md)

4. **Webhooks**: Receive real-time event notifications
   - [Webhooks Guide](./webhooks-guide.md)

5. **WebSocket**: Real-time bidirectional communication
   - [WebSocket API](./websocket-api.md)

## Resources

- **API Reference**: [Complete API Documentation](./endpoints/)
- **Best Practices**: [API Best Practices](./api-best-practices.md)
- **Error Codes**: [Error Handling Guide](./error-handling.md)
- **Rate Limits**: [Rate Limiting Guide](./rate-limiting.md)
- **Examples**: [SDK Examples](./sdk-examples.md)

## Getting Help

- **Documentation**: [docs.clouisle.com](https://docs.clouisle.com)
- **API Status**: [status.clouisle.com](https://status.clouisle.com)
- **Support**: support@clouisle.com
- **Community**: [community.clouisle.com](https://community.clouisle.com)

---

**Last Updated**: 2026-02-11
