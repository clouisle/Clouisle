# Agent Configuration

This guide covers how to configure AI agents in Clouisle.

## Overview

Agent configuration includes:

- **Basic settings**: Name, description, icon/avatar
- **Model**: The team-authorized LLM model used for chat
- **System prompt**: Define agent behavior
- **Knowledge bases**: Attach knowledge sources with per-KB retrieval settings
- **Tools**: Enable agent capabilities (builtin, custom, MCP, skills)
- **RAG mode**: off / auto / agentic
- **Chat behavior**: attachments, memory, image/video generation, variables

## Accessing Agent Configuration

### From Agent List

1. Navigate to **Agents**
2. Click on agent to configure
3. Click **Settings** or **Edit** button
4. Modify configuration
5. Click **Save Changes**

## Basic Information

### Agent Details

**Configure basic information:**

```yaml
Name: Customer Support Agent
Description: Handles customer inquiries and support tickets
Icon: 🤖
Team: Support Team
```

**Fields:**
- **Name**: Display name (max 100 chars, required)
- **Description**: Agent purpose (max 500 chars)
- **Icon**: Emoji or image URL (max 500 chars)
- **Avatar URL**: Optional avatar image URL
- **Team**: Team ownership (set at creation)

**Status:** An agent is `draft` until you publish it. Only published agents are available to chat with.

**Visibility:** `private` (only you) or `team` (all team members). There is no public visibility.

## Model Selection

### Choose LLM Model

Select one of the models that your team has been granted access to (team-authorized models). The available options come from the models configured by your administrator.

**Model Selection:**

```yaml
Model: <team-authorized model>
```

**Considerations:**
- **Performance**: More capable models = better responses
- **Cost**: Balance quality vs. cost
- **Speed**: Faster models for real-time chat
- **Context**: Longer context for complex tasks

## System Prompt

### Define Agent Behavior

**System Prompt Structure:**

```
You are a [role] that [purpose].

Your responsibilities:
- [Responsibility 1]
- [Responsibility 2]

Guidelines:
- [Guideline 1]
- [Guideline 2]

Tone: [Professional/Friendly/Casual]
```

**Example - Customer Support Agent:**

```
You are a helpful customer support agent for Clouisle, an AI platform.

Your responsibilities:
- Answer customer questions about features and usage
- Help troubleshoot technical issues
- Guide users through common tasks

Guidelines:
- Always be polite and professional
- Use the knowledge base to provide accurate information
- If you don't know something, admit it and offer to escalate

Tone: Friendly and professional
```

### Dynamic Variables

**Use variables in the system prompt:**

```
You are a customer support agent for {{company_name}}.

Respond to the user's request: {{query}}
```

**Available variables:** Custom variables defined in the agent's **Variables** section (text, paragraph, select, number, checkbox types), plus `{{query}}` for the current chat request. Only values supplied for those variables are substituted; Clouisle does not inject built-in user, team, date, or time variables.

## Chat Behavior Settings

The following toggles control the chat experience:

| Setting | Default | Description |
|---------|---------|-------------|
| **Max tool iterations** | 5 (1-200) | Maximum tool-call iterations per round |
| **Hide tool calls** | off | Hide tool call details in the chat UI |
| **Hide message actions** | off | Hide token usage / speed stats in the chat UI |
| **Hide reasoning** | off | Hide reasoning / chain-of-thought in the chat UI |
| **Enable attachments** | off | Allow file and image attachments (limits configurable) |
| **Enable interactive questions** | off | Allow the agent to pause and ask one or more structured questions; users can pick options, type custom text, or skip |
| **Enable memory** | off | Remember user information across conversations (memory config: max memories per retrieval, auto-extract, importance threshold) |

## Knowledge Base Configuration

### Attach Knowledge Bases

**Add knowledge sources:**

1. Go to the **Knowledge Bases** section of agent configuration
2. Click **Add Knowledge Base**
3. Select a knowledge base
4. Configure per-KB retrieval settings
5. Save configuration

**Configuration:**

```yaml
Knowledge Base:
  ID: <knowledge_base_id>
  Retrieval Top K: 5
  Score Threshold: 0.3
  Search Mode: hybrid
```

### Per-KB Search Settings

- **Retrieval Top K**: Number of chunks to retrieve (default 5, range 1-100)
- **Score Threshold**: Minimum similarity score, 0-1, lower = more results (default 0.3)
- **Search Mode**: `vector`, `fulltext`, or `hybrid` (default `hybrid`)

There is no cross-KB priority ordering; each attached knowledge base is searched with its own settings.

## RAG Configuration

### RAG Modes

**off:**
- No retrieval, even if knowledge bases are configured

**auto:**
- Traditional RAG: automatically retrieve from the knowledge bases on every message

**agentic:**
- Agentic RAG: the agent decides when to search (default)

## Tool Configuration

### Enable Tools

Configure tools as a JSON list of `{type, name/tool_id/server_id/skill_id, config}` entries:

**Tool types:**
- **builtin**: e.g. web search, calculator, datetime (by name)
- **custom**: team custom tools (by tool_id)
- **mcp**: MCP server tools (by server_id)
- **skill**: skills (by skill_id)

**Tool credentials** (API keys/tokens for tools such as web search) can be provided as a JSON object per agent.

## Advanced Settings

### Context Compression

Long conversations are kept within the model's context window automatically. The `context_compression_config` controls compaction behavior (micro compaction of reasoning/tool results, macro summary compaction, preflight token budget guard, retry on context-length errors, and session memory). These defaults work out of the box; advanced users can tune them via the API.

### Image / Video Generation

Agents can be granted image generation and video generation tool calling:

- **Image generation config**: default model, width/height, max images, reference-image support, provider allowlist, confirmation requirement
- **Video generation config**: default model, duration limits, aspect ratio, polling interval/timeout, provider allowlist, confirmation requirement

### Streaming

Responses stream in real time. `streaming_config` controls the global timeout, heartbeat interval, and per-tool timeouts.

### Opening Message & Suggested Questions

Configure an optional opening message and suggested questions shown when a new conversation starts.

### Embed

`embed_config` controls the embeddable widget for this agent (enabled, allowed domains, theme, bubble).

## Testing Configuration

### Test Agent

1. Click **Test Agent** (this runs the workflow debug flow or a test chat)
2. Send a disposable test message
3. Review the response, source citations, and tool usage
4. Adjust configuration if needed

## Best Practices

**✅ Do:**
- Test configuration thoroughly
- Start with the default settings
- Write clear, specific system prompts
- Attach relevant knowledge bases with sensible retrieval settings

**❌ Don't:**
- Over-complicate the system prompt
- Enable unnecessary tools
- Publish before testing

## Related Documentation

- [Chatting with Agents](../chat/chatting-with-agents.md) - Using agents
- [Knowledge Base Settings](../knowledge-base/kb-settings.md) - KB configuration
- [Model Management](../../admin-guide/models/model-management.md) - Model admin

---

**Last Updated**: 2026-02-11
