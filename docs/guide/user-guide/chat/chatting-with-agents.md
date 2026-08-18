# Chatting with AI Agents

This guide explains how to interact with AI agents in Clouisle for conversational AI experiences.

## Overview

AI Agents in Clouisle are conversational assistants that can:
- Answer questions based on knowledge bases (RAG)
- Use tools to perform actions
- Maintain context across multiple turns
- Stream responses in real-time

## Starting a Conversation

### From the Apps page

1. Navigate to **Apps** (`/app/apps`).
2. Open the **Agent** tab and find the agent you want to use.
3. Open the agent card menu and choose **Chat**.
4. The agent chat opens at `/chat/{agent_id}`. Send your first message.

There is no global Chat/Conversations page or global **New Chat** picker. Each agent's chat page contains that agent's recent conversations.

### From an existing agent chat

1. Open the agent's chat page.
2. Use the conversation controls in that page to continue a recent conversation or start a new one.
3. Type your message and send it.

## Chat Interface

### Layout

```
┌─────────────────────────────────────────────────┐
│  Agent Name                    [Settings] [...]  │
├─────────────────────────────────────────────────┤
│                                                  │
│  Agent: Hello! How can I help you today?        │
│                                                  │
│  You: What is Clouisle?                         │
│                                                  │
│  Agent: Clouisle is an enterprise-grade...      │
│  [Sources: doc1.pdf, doc2.md]                   │
│                                                  │
│                                                  │
├─────────────────────────────────────────────────┤
│  [📎] Type your message...            [Send] │
└─────────────────────────────────────────────────┘
```

### Key Elements

| Element | Description |
|---------|-------------|
| **Agent Name** | Current agent you're chatting with |
| **Message History** | Scrollable conversation history |
| **Input Box** | Type your messages here |
| **Attach Button** | Upload files (if the agent enables attachments) |
| **Send Button** | Send your message |
| **Sources** | Referenced documents (if RAG mode is enabled) |

## Sending Messages

### Text Messages

**Basic message:**
1. Type your message in the input box
2. Press **Enter** or click **Send**
3. Wait for the agent response (streaming)

**Multi-line message:**
1. Type your message
2. Press **Shift + Enter** for a new line
3. Press **Enter** to send

### File Uploads

If the agent supports file uploads (attachments enabled):

1. Click the **📎 Attach** button
2. Select file(s) from your computer
3. Supported formats depend on the agent's attachment configuration (PDF, DOCX, TXT, MD, CSV, XLSX, PPTX, images, etc.)
4. Wait for the file to upload/parse
5. Add your message or question about the file
6. Click **Send**

**Upload limits:**
- All chat uploads are limited to **10 MB per file** (server-enforced)
- Max files per message is configurable by the agent (default 5)

See [File Uploads](./file-uploads.md) for detailed information.

## Understanding Agent Responses

### Streaming Responses

Agents stream responses in real-time:
- Text appears word-by-word as generated
- You can read while the agent is still typing
- Stop generation by clicking the **Stop** button

### Response Components

**Text Response:**
```
The main answer to your question appears here.
It can include:
- Formatted text (bold, italic)
- Lists and bullet points
- Code blocks
- Links
```

**Source Citations (RAG):**
```
📚 Sources:
- document1.pdf (Page 5)
- guide.md (Section 3)
```

**Tool Usage:**
```
🔧 Using tool: web_search
Searching for: "latest AI trends"
Found 5 results...
```

**Thinking Process (if enabled):**
```
💭 Thinking...
Analyzing the question...
Retrieving relevant documents...
Formulating response...
```

### Response Quality

**High-quality responses include:**
- Direct answer to your question
- Relevant context and details
- Source citations (if using a knowledge base)
- Clear structure and formatting

**If response quality is poor:**
- Rephrase your question more clearly
- Provide more context
- Break complex questions into simpler parts
- Check if the agent has access to a relevant knowledge base

## Agent Capabilities

### Knowledge Base Access (RAG)

Agents retrieve information from connected knowledge bases according to their RAG mode:

- **off**: No retrieval, even if knowledge bases are configured
- **auto**: Automatically retrieve on every message (traditional RAG)
- **agentic**: The agent decides when to search (default)

With retrieval enabled, the agent's responses can include the retrieved source chunks.

**Tips for better RAG results:**
- Ask specific questions
- Mention document names if known
- Request sources explicitly: "What does the manual say about..."
- Follow up for clarification

### Tool Usage

Agents can use tools to perform actions:

**Web Search:**
```
You: What's the weather in San Francisco?

Agent: 🔧 Searching weather data...
The current weather in San Francisco is 65°F (18°C),
partly cloudy with light winds.
```

**Calculator:**
```
You: What's 15% of $250?

Agent: 🔧 Calculating...
15% of $250 is $37.50
```

### Multi-Turn Conversations

Agents maintain context across messages:

```
You: What is Clouisle?
Agent: Clouisle is an AI platform...

You: How do I install it?
Agent: To install Clouisle, follow these steps...
     [Agent remembers we're talking about Clouisle]
```

Long conversations are automatically compressed to fit the model's context window.

## Advanced Features

### Message Regeneration

If you're not satisfied with a response:

1. Hover over the agent's message
2. Click the **🔄 Regenerate** button
3. The agent generates a new response
4. The previous response is saved as a version (you can switch between versions)

### Message Editing

Edit your sent messages:

1. Hover over your message
2. Click the **✏️ Edit** button
3. Modify your message
4. Press **Enter** to resend
5. The conversation branches from this point

### Message Branching

Conversations can have multiple branches:

```
Main conversation:
You: Tell me about AI
Agent: AI is...

Branch 1 (edit message):
You: Tell me about ML
Agent: ML is...

Branch 2 (regenerate):
Agent: AI, or Artificial Intelligence...
```

Navigate branches using the arrow buttons.

### Copy Message

1. Hover over a message
2. Click the **📋 Copy** button
3. The message is copied to the clipboard

> **Note:** Conversation sharing and export are **not implemented**.

## Best Practices

### Writing Effective Prompts

**✅ Do:**
```
Good: "What are the steps to reset my password in the
admin dashboard?"

Good: "Summarize the key points from the Q3 report
about revenue growth"

Good: "Compare the features of Plan A and Plan B in
a table format"
```

**❌ Don't:**
```
Bad: "password?"
Bad: "tell me everything"
Bad: "help"
```

**Tips:**
- Be specific about what you want
- Specify format if needed (table, list, summary)
- Provide relevant context
- Ask one thing at a time for complex topics

### Managing Context

**Start a new conversation when:**
- Switching to an unrelated topic
- The agent seems confused about context
- You want a fresh start

**Continue a conversation when:**
- Asking follow-up questions
- Building on previous answers
- Maintaining context is important

### Using Knowledge Bases Effectively

**✅ Do:**
- Ask specific questions about documents
- Request sources: "According to the manual..."
- Mention document names if known
- Follow up for clarification

**❌ Don't:**
- Ask about information not in the knowledge base
- Expect the agent to know real-time information
- Assume all documents are indexed

## Troubleshooting

### Agent Not Responding

**Problem**: No response after sending a message

**Solutions:**
1. Check your internet connection
2. Refresh the page
3. Check if the agent is published
4. Try a different agent
5. Contact the administrator

### Slow Responses

**Problem**: Agent takes a long time to respond

**Solutions:**
1. Check your internet speed
2. Simplify your question
3. Try during off-peak hours
4. Contact the administrator about server load

### Irrelevant Responses

**Problem**: Agent gives unrelated answers

**Solutions:**
1. Rephrase your question more clearly
2. Provide more context
3. Start a new conversation (clear context)
4. Check if the agent has a relevant knowledge base
5. Try a different agent specialized for your topic

### Sources Not Showing

**Problem**: No source citations in RAG mode

**Solutions:**
1. Verify the agent has a knowledge base connected
2. Check the agent's RAG mode is not "off"
3. Ask more specific questions
4. Verify documents are indexed (status: completed)

### File Upload Fails

**Problem**: Cannot upload files

**Solutions:**
1. Check file size (must be under 10 MB)
2. Verify the file format is supported
3. Check if the agent allows file uploads
4. Try a different file
5. Contact the administrator

See [File Uploads](./file-uploads.md) for detailed troubleshooting.

## Related Documentation

- [File Uploads](./file-uploads.md) - Uploading files in chat
- [Conversation Management](./conversation-management.md) - Managing conversations
- [Agent Configuration](../agents/agent-configuration.md) - Configuring agents

## Getting Help

If you need assistance:

1. **Documentation**: Review this guide and related docs
2. **Support**: Contact your organization's support team
3. **Administrator**: Reach out to your Clouisle administrator

---

**Last Updated**: 2026-02-11
