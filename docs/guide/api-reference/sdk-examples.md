# SDK Examples

This guide provides comprehensive SDK examples for integrating Clouisle into your applications.

## Python SDK

### Installation

```bash
pip install clouisle-sdk
# or
uv add clouisle-sdk
```

### Basic Setup

```python
from clouisle import CloudisleClient

# Initialize client
client = CloudisleClient(
    base_url="https://your-domain.com",
    api_key="your-api-key"
)

# Or with JWT token
client = CloudisleClient(
    base_url="https://your-domain.com",
    token="your-jwt-token"
)
```

### Agent Management

```python
# List agents
agents = client.agents.list(
    page=1,
    page_size=20,
    status="active"
)

for agent in agents.items:
    print(f"{agent.name} - {agent.model}")

# Get agent
agent = client.agents.get("agent-123")
print(f"Agent: {agent.name}")
print(f"Model: {agent.model}")
print(f"Status: {agent.status}")

# Create agent
agent = client.agents.create(
    name="Customer Support Agent",
    model="gpt-4-turbo",
    system_prompt="You are a helpful customer support agent.",
    temperature=0.7,
    max_tokens=2000,
    team_id="team-123"
)
print(f"Created: {agent.id}")

# Update agent
agent = client.agents.update(
    "agent-123",
    name="Updated Agent Name",
    system_prompt="Updated system prompt",
    temperature=0.8
)

# Delete agent
client.agents.delete("agent-123")
```

### Conversations

```python
# Start conversation
conversation = client.conversations.create(
    agent_id="agent-123",
    title="Customer Inquiry"
)

# Send message
message = client.conversations.send_message(
    conversation.id,
    content="Hello! I need help with my order."
)
print(f"Response: {message.response}")

# Stream message
for token in client.conversations.stream_message(
    conversation.id,
    content="Tell me a story"
):
    print(token, end='', flush=True)

# Get messages
messages = client.conversations.get_messages(conversation.id)
for msg in messages.items:
    print(f"{msg.role}: {msg.content}")

# List conversations
conversations = client.conversations.list(
    agent_id="agent-123",
    page=1,
    page_size=20
)
```

### Knowledge Bases

```python
# Create knowledge base
kb = client.knowledge_bases.create(
    name="Product Documentation",
    description="All product manuals and guides",
    embedding_model="text-embedding-3-large",
    chunk_size=1000,
    chunk_overlap=200
)

# Upload document
document = client.knowledge_bases.upload_document(
    kb.id,
    file_path="/path/to/document.pdf",
    metadata={
        "category": "manual",
        "version": "2.0"
    }
)

# Upload from URL
document = client.knowledge_bases.upload_from_url(
    kb.id,
    url="https://example.com/document.pdf",
    filename="product-manual.pdf"
)

# Search knowledge base
results = client.knowledge_bases.search(
    kb.id,
    query="How to reset password?",
    top_k=5,
    score_threshold=0.7
)

for result in results:
    print(f"Score: {result.score}")
    print(f"Content: {result.content}")
    print(f"Source: {result.metadata.get('source')}")
    print()

# List documents
documents = client.knowledge_bases.list_documents(
    kb.id,
    page=1,
    page_size=20
)

# Delete document
client.knowledge_bases.delete_document(kb.id, document.id)
```

### Workflows

```python
# Create workflow
workflow = client.workflows.create(
    name="Customer Inquiry Handler",
    description="Automated customer inquiry processing",
    trigger_type="webhook",
    nodes=[
        {
            "id": "start",
            "type": "start",
            "config": {
                "input_parameters": [
                    {"name": "customer_email", "type": "string", "required": True},
                    {"name": "inquiry_text", "type": "string", "required": True}
                ]
            }
        },
        {
            "id": "analyze",
            "type": "llm",
            "config": {
                "model": "gpt-4-turbo",
                "system_prompt": "Analyze customer inquiry",
                "user_prompt": "{{inquiry_text}}",
                "output_variable": "analysis"
            }
        },
        {
            "id": "end",
            "type": "end",
            "config": {
                "output": {
                    "status": "success",
                    "data": "{{analysis}}"
                }
            }
        }
    ],
    edges=[
        {"from": "start", "to": "analyze"},
        {"from": "analyze", "to": "end"}
    ]
)

# Execute workflow
execution = client.workflows.execute(
    workflow.id,
    input_data={
        "customer_email": "customer@example.com",
        "inquiry_text": "I need help with my order"
    }
)

# Wait for completion
execution = client.workflows.wait_for_completion(
    workflow.id,
    execution.id,
    timeout=60
)

print(f"Status: {execution.status}")
print(f"Output: {execution.output}")

# Get execution history
executions = client.workflows.list_executions(
    workflow.id,
    page=1,
    page_size=20
)
```

### Tools

```python
# List tools
tools = client.tools.list()

# Get tool
tool = client.tools.get("tool-123")

# Execute tool
result = client.tools.execute(
    "web_search",
    parameters={
        "query": "latest AI news",
        "num_results": 5
    }
)

# Create custom tool
tool = client.tools.create(
    name="Custom Calculator",
    description="Perform calculations",
    parameters={
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Math expression to evaluate"
            }
        },
        "required": ["expression"]
    },
    code="""
def execute(expression):
    try:
        result = eval(expression)
        return {"result": result}
    except Exception as e:
        return {"error": str(e)}
"""
)
```

### Batch Operations

```python
# Batch create agents
results = client.agents.batch_create([
    {
        "name": "Agent 1",
        "model": "gpt-4-turbo",
        "system_prompt": "You are helpful."
    },
    {
        "name": "Agent 2",
        "model": "claude-3-5-sonnet",
        "system_prompt": "You are helpful."
    }
])

print(f"Success: {results.summary.success_count}")
print(f"Failed: {results.summary.failed_count}")

# Batch delete
results = client.agents.batch_delete([
    "agent-123",
    "agent-456",
    "agent-789"
])
```

### Error Handling

```python
from clouisle.exceptions import (
    CloudisleError,
    AuthenticationError,
    PermissionError,
    NotFoundError,
    RateLimitError
)

try:
    agent = client.agents.get("agent-123")

except AuthenticationError as e:
    print(f"Authentication failed: {e.message}")
    # Refresh token or re-authenticate

except PermissionError as e:
    print(f"Permission denied: {e.message}")
    # Check user permissions

except NotFoundError as e:
    print(f"Resource not found: {e.message}")
    # Handle missing resource

except RateLimitError as e:
    print(f"Rate limit exceeded: {e.message}")
    print(f"Retry after: {e.retry_after} seconds")
    # Wait and retry

except CloudisleError as e:
    print(f"API error: {e.message}")
    print(f"Error code: {e.code}")
```

### Async Support

```python
import asyncio
from clouisle import AsyncCloudisleClient

async def main():
    # Initialize async client
    client = AsyncCloudisleClient(
        base_url="https://your-domain.com",
        api_key="your-api-key"
    )

    # Async operations
    agents = await client.agents.list()
    agent = await client.agents.get("agent-123")

    # Async streaming
    async for token in client.conversations.stream_message(
        "conv-123",
        content="Hello!"
    ):
        print(token, end='', flush=True)

    # Close client
    await client.close()

# Run
asyncio.run(main())
```

## JavaScript/TypeScript SDK

### Installation

```bash
npm install @clouisle/sdk
# or
yarn add @clouisle/sdk
# or
bun add @clouisle/sdk
```

### Basic Setup

```typescript
import { CloudisleClient } from '@clouisle/sdk';

// Initialize client
const client = new CloudisleClient({
  baseUrl: 'https://your-domain.com',
  apiKey: 'your-api-key'
});

// Or with JWT token
const client = new CloudisleClient({
  baseUrl: 'https://your-domain.com',
  token: 'your-jwt-token'
});
```

### Agent Management

```typescript
// List agents
const agents = await client.agents.list({
  page: 1,
  pageSize: 20,
  status: 'active'
});

agents.items.forEach(agent => {
  console.log(`${agent.name} - ${agent.model}`);
});

// Get agent
const agent = await client.agents.get('agent-123');
console.log(`Agent: ${agent.name}`);

// Create agent
const newAgent = await client.agents.create({
  name: 'Customer Support Agent',
  model: 'gpt-4-turbo',
  systemPrompt: 'You are a helpful customer support agent.',
  temperature: 0.7,
  maxTokens: 2000,
  teamId: 'team-123'
});

// Update agent
const updated = await client.agents.update('agent-123', {
  name: 'Updated Agent Name',
  systemPrompt: 'Updated system prompt',
  temperature: 0.8
});

// Delete agent
await client.agents.delete('agent-123');
```

### Conversations

```typescript
// Start conversation
const conversation = await client.conversations.create({
  agentId: 'agent-123',
  title: 'Customer Inquiry'
});

// Send message
const message = await client.conversations.sendMessage(
  conversation.id,
  {
    content: 'Hello! I need help with my order.'
  }
);
console.log(`Response: ${message.response}`);

// Stream message
const stream = await client.conversations.streamMessage(
  conversation.id,
  {
    content: 'Tell me a story'
  }
);

for await (const token of stream) {
  process.stdout.write(token);
}

// Get messages
const messages = await client.conversations.getMessages(conversation.id);
messages.items.forEach(msg => {
  console.log(`${msg.role}: ${msg.content}`);
});

// List conversations
const conversations = await client.conversations.list({
  agentId: 'agent-123',
  page: 1,
  pageSize: 20
});
```

### Knowledge Bases

```typescript
// Create knowledge base
const kb = await client.knowledgeBases.create({
  name: 'Product Documentation',
  description: 'All product manuals and guides',
  embeddingModel: 'text-embedding-3-large',
  chunkSize: 1000,
  chunkOverlap: 200
});

// Upload document
const document = await client.knowledgeBases.uploadDocument(
  kb.id,
  {
    file: fileBlob,
    metadata: {
      category: 'manual',
      version: '2.0'
    }
  }
);

// Upload from URL
const doc = await client.knowledgeBases.uploadFromUrl(
  kb.id,
  {
    url: 'https://example.com/document.pdf',
    filename: 'product-manual.pdf'
  }
);

// Search knowledge base
const results = await client.knowledgeBases.search(kb.id, {
  query: 'How to reset password?',
  topK: 5,
  scoreThreshold: 0.7
});

results.forEach(result => {
  console.log(`Score: ${result.score}`);
  console.log(`Content: ${result.content}`);
  console.log(`Source: ${result.metadata.source}`);
  console.log();
});
```

### Workflows

```typescript
// Create workflow
const workflow = await client.workflows.create({
  name: 'Customer Inquiry Handler',
  description: 'Automated customer inquiry processing',
  triggerType: 'webhook',
  nodes: [
    {
      id: 'start',
      type: 'start',
      config: {
        inputParameters: [
          { name: 'customer_email', type: 'string', required: true },
          { name: 'inquiry_text', type: 'string', required: true }
        ]
      }
    },
    {
      id: 'analyze',
      type: 'llm',
      config: {
        model: 'gpt-4-turbo',
        systemPrompt: 'Analyze customer inquiry',
        userPrompt: '{{inquiry_text}}',
        outputVariable: 'analysis'
      }
    },
    {
      id: 'end',
      type: 'end',
      config: {
        output: {
          status: 'success',
          data: '{{analysis}}'
        }
      }
    }
  ],
  edges: [
    { from: 'start', to: 'analyze' },
    { from: 'analyze', to: 'end' }
  ]
});

// Execute workflow
const execution = await client.workflows.execute(workflow.id, {
  customer_email: 'customer@example.com',
  inquiry_text: 'I need help with my order'
});

// Wait for completion
const completed = await client.workflows.waitForCompletion(
  workflow.id,
  execution.id,
  { timeout: 60000 }
);

console.log(`Status: ${completed.status}`);
console.log(`Output: ${completed.output}`);
```

### Error Handling

```typescript
import {
  CloudisleError,
  AuthenticationError,
  PermissionError,
  NotFoundError,
  RateLimitError
} from '@clouisle/sdk';

try {
  const agent = await client.agents.get('agent-123');

} catch (error) {
  if (error instanceof AuthenticationError) {
    console.error(`Authentication failed: ${error.message}`);
    // Refresh token or re-authenticate

  } else if (error instanceof PermissionError) {
    console.error(`Permission denied: ${error.message}`);
    // Check user permissions

  } else if (error instanceof NotFoundError) {
    console.error(`Resource not found: ${error.message}`);
    // Handle missing resource

  } else if (error instanceof RateLimitError) {
    console.error(`Rate limit exceeded: ${error.message}`);
    console.error(`Retry after: ${error.retryAfter} seconds`);
    // Wait and retry

  } else if (error instanceof CloudisleError) {
    console.error(`API error: ${error.message}`);
    console.error(`Error code: ${error.code}`);
  }
}
```

### React Hooks

```typescript
import { useAgent, useConversation, useKnowledgeBase } from '@clouisle/react';

function AgentComponent() {
  const { agent, loading, error } = useAgent('agent-123');

  if (loading) return <div>Loading...</div>;
  if (error) return <div>Error: {error.message}</div>;

  return (
    <div>
      <h1>{agent.name}</h1>
      <p>Model: {agent.model}</p>
    </div>
  );
}

function ChatComponent({ agentId }) {
  const {
    conversation,
    messages,
    sendMessage,
    loading
  } = useConversation(agentId);

  const handleSend = async (content: string) => {
    await sendMessage(content);
  };

  return (
    <div>
      <div className="messages">
        {messages.map(msg => (
          <div key={msg.id}>
            <strong>{msg.role}:</strong> {msg.content}
          </div>
        ))}
      </div>
      <input
        onKeyPress={(e) => {
          if (e.key === 'Enter') {
            handleSend(e.target.value);
            e.target.value = '';
          }
        }}
        disabled={loading}
      />
    </div>
  );
}
```

## Go SDK

### Installation

```bash
go get github.com/clouisle/clouisle-go
```

### Basic Setup

```go
package main

import (
    "context"
    "fmt"
    "github.com/clouisle/clouisle-go"
)

func main() {
    // Initialize client
    client := clouisle.NewClient(
        "https://your-domain.com",
        clouisle.WithAPIKey("your-api-key"),
    )

    ctx := context.Background()

    // List agents
    agents, err := client.Agents.List(ctx, &clouisle.ListAgentsParams{
        Page:     1,
        PageSize: 20,
        Status:   "active",
    })
    if err != nil {
        panic(err)
    }

    for _, agent := range agents.Items {
        fmt.Printf("%s - %s\n", agent.Name, agent.Model)
    }
}
```

### Agent Management

```go
// Get agent
agent, err := client.Agents.Get(ctx, "agent-123")
if err != nil {
    panic(err)
}

// Create agent
agent, err := client.Agents.Create(ctx, &clouisle.CreateAgentParams{
    Name:         "Customer Support Agent",
    Model:        "gpt-4-turbo",
    SystemPrompt: "You are a helpful customer support agent.",
    Temperature:  0.7,
    MaxTokens:    2000,
    TeamID:       "team-123",
})

// Update agent
agent, err := client.Agents.Update(ctx, "agent-123", &clouisle.UpdateAgentParams{
    Name:         clouisle.String("Updated Name"),
    Temperature:  clouisle.Float64(0.8),
})

// Delete agent
err := client.Agents.Delete(ctx, "agent-123")
```

### Error Handling

```go
import "github.com/clouisle/clouisle-go/errors"

agent, err := client.Agents.Get(ctx, "agent-123")
if err != nil {
    switch e := err.(type) {
    case *errors.AuthenticationError:
        fmt.Printf("Authentication failed: %s\n", e.Message)
    case *errors.PermissionError:
        fmt.Printf("Permission denied: %s\n", e.Message)
    case *errors.NotFoundError:
        fmt.Printf("Resource not found: %s\n", e.Message)
    case *errors.RateLimitError:
        fmt.Printf("Rate limit exceeded, retry after %d seconds\n", e.RetryAfter)
    default:
        fmt.Printf("Error: %s\n", err)
    }
    return
}
```

## Ruby SDK

### Installation

```bash
gem install clouisle
```

### Basic Setup

```ruby
require 'clouisle'

# Initialize client
client = Clouisle::Client.new(
  base_url: 'https://your-domain.com',
  api_key: 'your-api-key'
)

# List agents
agents = client.agents.list(page: 1, page_size: 20, status: 'active')
agents.items.each do |agent|
  puts "#{agent.name} - #{agent.model}"
end

# Create agent
agent = client.agents.create(
  name: 'Customer Support Agent',
  model: 'gpt-4-turbo',
  system_prompt: 'You are a helpful customer support agent.',
  temperature: 0.7,
  max_tokens: 2000,
  team_id: 'team-123'
)

# Send message
message = client.conversations.send_message(
  'conv-123',
  content: 'Hello!'
)
puts "Response: #{message.response}"
```

## Best Practices

### 1. Use Environment Variables

```python
import os

client = CloudisleClient(
    base_url=os.getenv('CLOUISLE_BASE_URL'),
    api_key=os.getenv('CLOUISLE_API_KEY')
)
```

### 2. Implement Retry Logic

```python
from clouisle.retry import RetryConfig

client = CloudisleClient(
    base_url="https://your-domain.com",
    api_key="your-api-key",
    retry_config=RetryConfig(
        max_retries=3,
        initial_delay=1.0,
        max_delay=60.0
    )
)
```

### 3. Use Async for Better Performance

```python
import asyncio

async def process_agents():
    async with AsyncCloudisleClient(...) as client:
        # Fetch multiple agents in parallel
        agents = await asyncio.gather(
            client.agents.get("agent-1"),
            client.agents.get("agent-2"),
            client.agents.get("agent-3")
        )
        return agents
```

### 4. Handle Errors Gracefully

```typescript
async function safeGetAgent(id: string) {
  try {
    return await client.agents.get(id);
  } catch (error) {
    if (error instanceof NotFoundError) {
      console.log(`Agent ${id} not found`);
      return null;
    }
    throw error;
  }
}
```

### 5. Use Pagination Efficiently

```python
# Fetch all agents efficiently
all_agents = []
page = 1

while True:
    result = client.agents.list(page=page, page_size=100)
    all_agents.extend(result.items)

    if not result.has_next:
        break

    page += 1
```

## Related Documentation

- [API Reference](./endpoints/) - Complete API documentation
- [Quick Start](./quick-start.md) - Getting started guide
- [Best Practices](./api-best-practices.md) - API best practices
- [Error Handling](./error-handling.md) - Error handling guide

---

**Last Updated**: 2026-02-11
