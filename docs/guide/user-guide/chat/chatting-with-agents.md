# Chatting with AI Agents

This guide explains how to interact with AI agents in Clouisle for conversational AI experiences.

## Overview

AI Agents in Clouisle are conversational assistants that can:
- Answer questions based on knowledge bases
- Use tools to perform actions
- Execute workflows
- Maintain context across multiple turns
- Stream responses in real-time

## Starting a Conversation

### From Platform Interface

1. Navigate to **Apps** or **Agents** section
2. Browse available agents or search by name
3. Click on an agent card to open it
4. Click **"Start Chat"** or **"New Conversation"**
5. The chat interface opens

### From Chat Interface

1. Navigate to **Chat** section
2. Click **"New Chat"** button
3. Select an agent from the list
4. Start typing your message

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
| **Settings** | Agent configuration and parameters |
| **Message History** | Scrollable conversation history |
| **Input Box** | Type your messages here |
| **Attach Button** | Upload files (if enabled) |
| **Send Button** | Send your message |
| **Sources** | Referenced documents (if RAG enabled) |

## Sending Messages

### Text Messages

**Basic message:**
1. Type your message in the input box
2. Press **Enter** or click **Send**
3. Wait for agent response (streaming)

**Multi-line message:**
1. Type your message
2. Press **Shift + Enter** for new line
3. Press **Enter** to send

**Tips:**
- Be specific and clear in your questions
- Provide context when needed
- Break complex questions into parts
- Use proper grammar for better understanding

### File Uploads

If the agent supports file uploads:

1. Click the **📎 Attach** button
2. Select file(s) from your computer
3. Supported formats depend on agent configuration:
   - Documents: PDF, DOCX, TXT, MD
   - Images: PNG, JPG, JPEG (if vision enabled)
   - Data: CSV, XLSX, JSON
4. Wait for file to upload
5. Add your message or question about the file
6. Click **Send**

**File upload limits:**
- Max file size: Configured by agent (typically 10-50 MB)
- Max files per message: Configured by agent (typically 1-5)

See [File Uploads](./file-uploads.md) for detailed information.

## Understanding Agent Responses

### Streaming Responses

Agents stream responses in real-time:
- Text appears word-by-word as generated
- You can read while the agent is still typing
- Stop generation by clicking **Stop** button

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

**Source Citations (RAG Mode):**
```
📚 Sources:
- document1.pdf (Page 5)
- guide.md (Section 3)
- api-docs.pdf (Page 12)
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
- Source citations (if using knowledge base)
- Clear structure and formatting
- Follow-up suggestions

**If response quality is poor:**
- Rephrase your question more clearly
- Provide more context
- Break complex questions into simpler parts
- Check if agent has access to relevant knowledge base

## Agent Capabilities

### Knowledge Base Access (RAG)

Agents can retrieve information from connected knowledge bases.

**Citation Mode:**
```
You: What is the refund policy?

Agent: According to our policy document, refunds are
processed within 14 days of request [1].

[1] refund-policy.pdf, Page 2
```

**Rewrite Mode:**
```
You: What is the refund policy?

Agent: Refunds are processed within 14 days of your
request. You can initiate a refund by contacting
customer support with your order number.
```

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

**API Calls:**
```
You: Create a support ticket for login issue

Agent: 🔧 Creating ticket...
✅ Ticket #12345 created successfully
Status: Open
Priority: High
```

### Multi-Turn Conversations

Agents maintain context across messages:

```
You: What is Clouisle?
Agent: Clouisle is an AI platform...

You: How do I install it?
Agent: To install Clouisle, follow these steps...
     [Agent remembers we're talking about Clouisle]

You: What about Docker?
Agent: For Docker installation of Clouisle...
     [Agent maintains full context]
```

**Context window:**
- Agents remember recent messages (typically last 10-20 messages)
- Very long conversations may lose early context
- Start new conversation for unrelated topics

## Advanced Features

### Message Regeneration

If you're not satisfied with a response:

1. Hover over the agent's message
2. Click **🔄 Regenerate** button
3. Agent generates a new response
4. Previous response is saved (can switch between versions)

### Message Editing

Edit your sent messages:

1. Hover over your message
2. Click **✏️ Edit** button
3. Modify your message
4. Press **Enter** to resend
5. Conversation branches from this point

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

Navigate branches using arrow buttons.

### Copy and Share

**Copy message:**
1. Hover over message
2. Click **📋 Copy** button
3. Message copied to clipboard

**Share conversation:**
1. Click **Share** button in top-right
2. Choose sharing option:
   - Copy link (if enabled)
   - Export as text
   - Export as markdown

## Conversation Settings

Access settings by clicking **⚙️ Settings** button:

### Model Parameters

Adjust agent behavior (if allowed):

| Parameter | Range | Effect |
|-----------|-------|--------|
| **Temperature** | 0.0 - 2.0 | Creativity (0=focused, 2=creative) |
| **Max Tokens** | 100 - 4000 | Response length |
| **Top P** | 0.0 - 1.0 | Response diversity |

**Presets:**
- **Precise**: Temperature 0.3, focused answers
- **Balanced**: Temperature 0.7, natural responses
- **Creative**: Temperature 1.2, varied responses

### RAG Settings

If agent uses knowledge base:

| Setting | Options | Description |
|---------|---------|-------------|
| **Retrieval Mode** | Citation / Rewrite | How sources are used |
| **Top K** | 3-10 | Number of documents to retrieve |
| **Score Threshold** | 0.5-0.9 | Minimum relevance score |

### Tool Settings

Enable/disable specific tools:
- ☑️ Web Search
- ☑️ Calculator
- ☐ File Parser
- ☑️ Custom Tools

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

**Start new conversation when:**
- Switching to unrelated topic
- Agent seems confused about context
- Conversation becomes very long (>50 messages)
- You want a fresh start

**Continue conversation when:**
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
- Ask about information not in knowledge base
- Expect agent to know real-time information
- Assume all documents are indexed

## Troubleshooting

### Agent Not Responding

**Problem**: No response after sending message

**Solutions:**
1. Check internet connection
2. Refresh the page
3. Check if agent is active
4. Try a different agent
5. Contact administrator

### Slow Responses

**Problem**: Agent takes long time to respond

**Solutions:**
1. Check your internet speed
2. Reduce max tokens setting
3. Simplify your question
4. Try during off-peak hours
5. Contact administrator about server load

### Irrelevant Responses

**Problem**: Agent gives unrelated answers

**Solutions:**
1. Rephrase your question more clearly
2. Provide more context
3. Start new conversation (clear context)
4. Check if agent has relevant knowledge base
5. Try a different agent specialized for your topic

### Sources Not Showing

**Problem**: No source citations in RAG mode

**Solutions:**
1. Verify agent has knowledge base connected
2. Check RAG mode is enabled (not "Disabled")
3. Ask more specific questions
4. Verify documents are indexed
5. Lower score threshold in settings

### File Upload Fails

**Problem**: Cannot upload files

**Solutions:**
1. Check file size (must be under limit)
2. Verify file format is supported
3. Check if agent allows file uploads
4. Try a different file
5. Contact administrator

See [File Uploads](./file-uploads.md) for detailed troubleshooting.

## Tips and Tricks

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| **Enter** | Send message |
| **Shift + Enter** | New line |
| **Ctrl/Cmd + K** | New conversation |
| **Ctrl/Cmd + /** | Focus input |
| **Esc** | Stop generation |

### Power User Features

**Quick commands:**
- Type `/help` for agent-specific help
- Type `/clear` to clear conversation
- Type `/settings` to open settings

**Markdown formatting:**
```
**bold text**
*italic text*
`code`
[link](url)
- bullet list
1. numbered list
```

### Getting Better Results

**Iterative refinement:**
1. Start with general question
2. Review response
3. Ask follow-up for details
4. Refine based on answers

**Example:**
```
You: Tell me about API authentication
Agent: [General overview]

You: What about JWT tokens specifically?
Agent: [JWT details]

You: Show me a code example
Agent: [Code example]
```

## Related Documentation

- [File Uploads](./file-uploads.md) - Uploading files in chat
- [Conversation Management](./conversation-management.md) - Managing conversations
- [Agent Configuration](../../admin-guide/agents/agent-configuration.md) - Admin guide
- [RAG Configuration](../../admin-guide/agents/rag-configuration.md) - RAG setup

## Getting Help

If you need assistance:

1. **In-App Help**: Click **?** icon for agent-specific help
2. **Documentation**: Review this guide and related docs
3. **Support**: Contact your organization's support team
4. **Administrator**: Reach out to your Clouisle administrator

---

**Last Updated**: 2026-02-11
