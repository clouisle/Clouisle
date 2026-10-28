# Agent Configuration

This guide covers how to configure AI agents in Clouisle.

## Overview

Clouisle provides a dedicated **Agent Studio** (`/app/apps/{agent_id}`) with a responsive editor and live preview:
- **Orchestration Editor**: Configure the model, prompt, variables, knowledge bases, tools, chat behavior, and runtime parameters.
- **Live Preview Panel**: A persistent side-by-side chat sandbox on desktop, where you can test draft changes without publishing.
- **Top Toolbar**: Access agent metadata, preview, publication controls, the Embed widget drawer, and Agent Settings.

---

## Studio Interface & Layout

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ [🤖 Agent Name]  [Draft / Published]              [Embed] [Settings] [Publish Agent]   │
├─────────────────────────────────────────┬──────────────────────────────────────────────┤
│  ORCHESTRATION & CONFIGURATION (Left)   │  LIVE PREVIEW SANDBOX (Right)                │
│                                         │                                              │
│  ▼ Model Configuration                  │  ┌────────────────────────────────────────┐  │
│    [Select Team Model...]               │  │ 🤖 Agent Preview       [Reset Session] │  │
│                                         │  ├────────────────────────────────────────┤  │
│  ▼ System Prompt                        │  │ Opening Message:                       │  │
│    [ ✨ AI Generate Prompt ]            │  │ "Hello! How can I assist you today?"   │  │
│    [ Prompt Textarea / {{variables}} ]  │  │                                        │  │
│                                         │  │ [Suggested Question 1] [Question 2]    │  │
│  ▼ Variables                            │  │                                        │  │
│    [ + Add Variable (Text/Select/...) ] │  │ User: Test query...                    │  │
│                                         │  │ Agent: (Streaming response with tools) │  │
│  ▼ Knowledge Bases (RAG)                │  ├────────────────────────────────────────┤  │
│    [ + Add Knowledge Base ]             │  │ [📎] Type a test message...     [Send] │  │
│                                         │  └────────────────────────────────────────┘  │
│  ▼ Tools & Capabilities                 │                                              │
│    [ Builtin / Custom / MCP / Skill ]   │                                              │
│                                         │                                              │
│  ▼ Chat Behavior & Advanced Settings    │                                              │
└─────────────────────────────────────────┴──────────────────────────────────────────────┘
```

On phones, the side-by-side preview is hidden so the editor stays full-width. Select **Preview** in the toolbar to open the chat in a full-screen, drawer-like overlay; close the preview to return to editing.

### Accessing Agent Configuration

1. Navigate to **Apps** (`/app/apps`) from the main navigation bar.
2. Click on the **Agent** tab and choose the agent you want to edit.
3. The Agent Studio opens at `/app/apps/{agent_id}`.
4. All edits update your agent's **draft** configuration. Click **Publish Agent** on the top toolbar when ready to make changes live to team members.

---

## Basic Information & Settings Drawer

Click the **Settings** icon on the top toolbar to open the `AgentSettingsDrawer`:

```yaml
Name: Customer Support Agent
Description: Handles customer inquiries, technical troubleshooting, and ticket creation
Icon: 🤖 (Emoji or custom Image URL)
Visibility: team
```

**Fields:**
- **Name**: Display name (max 100 characters, required).
- **Description**: Summary of the agent's purpose and scope (max 500 characters).
- **Icon / Avatar**: Emoji character or external image URL.
- **Team**: Team ownership (assigned at creation; team is the sole organizational boundary).
- **Visibility**:
  - `private`: Visible and usable only by the creator.
  - `team`: Visible and usable by all team members.
- **Lifecycle Status**:
  - `draft`: Work-in-progress state. Edits can be previewed live in the right panel without affecting team users.
  - `published`: Production-ready state. Only published agents can be accessed via the standard Chat view or Embed widgets.

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

## System Prompt & AI Assistant

### Defining Agent Persona and Logic

The system prompt sets the foundational instructions, personality, operational constraints, and tool invocation rules.

**Standard Structure:**

```markdown
You are a [Role] specialized in [Domain].

Your responsibilities:
1. [Primary duty]
2. [Secondary duty]

Operational Guidelines:
- Always verify facts against attached knowledge bases before answering.
- Ask clarifying questions when user requirements are ambiguous.
- Structure outputs with Markdown headings and concise bullet points.

Tone: Professional, friendly, and structured.
```

### ✨ AI Prompt Generator

Clouisle includes an integrated AI Prompt Optimizer to help you craft high-performance prompts:

1. Click the **✨ AI Generate / Optimize** button at the top-right of the Prompt Editor.
2. Enter your agent's core intent in plain language (e.g., *"An IT helpdesk assistant that diagnoses network issues and searches our internal runbooks"*).
3. Provide optional context, constraints, and target output style.
4. Click **Generate**. The AI synthesizes a structured, production-ready system prompt including roles, constraints, tool instructions, and variable placeholders.
5. Click **Apply** to load the generated text directly into your editor.

### Dynamic Variables & Placeholders

System prompts support dynamic variable interpolation using double curly braces:

```markdown
You are an automated support engineer for {{company_name}}.
Your current customer tier is {{user_tier}}.

Answer the user inquiry: {{query}}
```

**Variable Types and Resolution:**
- **`{{query}}`**: Automatically bound to the current incoming user message.
- **Custom Variables**: Defined in the **Variables** configuration section. When configured:
  - The prompt editor highlights matched `{{variable_name}}` tokens.
  - During preview or live chat, a **Variable Input Bar / Drawer** prompts the user to supply values before starting the conversation.

---

## Dynamic Variables Editor

Dynamic variables allow agents to adapt to custom parameters supplied at conversation start.

### Supported Variable Types

| Type | Description | Input Widget |
|------|-------------|--------------|
| **Text** | Single-line short string | Text input box |
| **Paragraph** | Multi-line text block | Textarea |
| **Select** | Predefined single-choice list | Dropdown selector with configurable options |
| **Number** | Numeric value (integers/floats) | Number input field with optional min/max validation |
| **Checkbox** | Boolean true/false flag | Toggle switch or checkbox |
| **Secret** | Sensitive credentials or tokens | Masked input field (`password` type) |

### Variable Configuration Options

- **Key**: Variable name referenced in the prompt (e.g., `company_name`, alphanumeric + underscores).
- **Display Name**: User-friendly label shown in the input drawer.
- **Description / Tooltip**: Helpful hints for the user entering the value.
- **Required**: If enabled, users must fill this variable before sending the first message.
- **Default Value**: Initial pre-filled value.
- **Hidden**: Hides the variable from regular conversation drawers (useful when values are passed programmatically via API or Embed URL parameters).
## Chat Behavior Settings

The following toggles control the chat experience:

| Setting | Default | Description |
|---------|---------|-------------|
| **Max Iterations** | 5 (1-200) | Maximum tool-call iterations per round |
| **Hide tool calls** | off | Hide tool call details in the chat UI |
| **Hide message actions** | off | Hide token usage / speed stats in the chat UI |
| **Hide reasoning** | off | Hide reasoning / chain-of-thought in the chat UI |
| **Enable source citations** | off | Add source-citation instructions and display inline citations and the source list in chat and preview. Knowledge retrieval, web tools, and attachment reading still work when disabled. |
| **Hide artifact list** | off | Hide the generated files list under assistant messages in chat and preview. |
| **Enable attachments** | off | Allow file and image attachments (limits configurable) |
| **Enable interactive questions** | off | Allow the agent to pause and ask one or more structured questions; users can pick options, type custom text, or skip |
| **Enable memory** | off | Remember user information across conversations (memory config: max memories per retrieval, auto-extract, importance threshold) |

Source citations are opt-in (`enable_citations: true`) for both new and existing agents. Enable the switch in Agent Settings when answers should cite retrieved documents, web results, or attachments. When disabled, Clouisle does not inject citation requirements into the system prompt or automatic RAG context, and hides citation cards and the source list, including for existing messages. Enabling the switch does not add citation instructions to Workflow-mode Agent calls.


Background extraction is also controlled by the administrator's **Site Settings > Memory** category. For eligible pending user turns, the global switch, extraction model, cooldown (`10-3600` seconds), and pending-turn trigger (`1-50` turns) determine when extraction is queued; Agent memory must be enabled as well.
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
- No retrieval, even if knowledge bases are configured.

**auto:**
- Traditional RAG: automatically retrieve from the knowledge bases on every message.

**agentic:**
- Agentic RAG: the agent decides when to search.

When `knowledge_base_configs` is empty, the backend normalizes the persisted mode to `off`, regardless of the requested default. The Agent editor hides the RAG mode selector until at least one knowledge base is attached.


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

Long conversations are kept within the model's context window automatically. In the Agent editor, **Context Compression** controls:

- **Enabled**: summarize older history and compact completed tool results before each model call. Disabling it keeps the previous behavior of sending the full history (the model call may then fail when the history exceeds its window).
- **Summary Token Budget** (`summary_max_tokens`, 128–8000): target size of the generated history summary. Larger summaries preserve more detail but leave less room for the current round.
- **Show compression progress** (`emit_sse_events`): emit `compression_start` / `compression_end` events. When off, compression still happens but stays silent in chat and the SSE stream.

Compression never rewrites stored messages or tool records; it only changes the view sent to the model for that request. When older history is summarized or completed tool output is compacted, chat shows a short progress step with token counts, and the SSE `compression_end` event reports `stage` (`macro`, `micro`, or `fallback`) and `actions` (`context_summary`, `tool_result_compacted`, `summary_fallback`).

If the summarizer is unavailable, compression falls back to omitting summarized history while keeping current instructions and the recent tail, and the chat step states that earlier history was omitted. If even the protected content (system prompt, current turn, tool definitions, retained recent exchanges) cannot fit, the run fails with an explicit error instead of dropping your instructions.

The same settings are available through the API as `context_compression_config`; defaults are enabled with a 1000-token summary budget and progress events on.

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
## Testing with the Live Preview Panel

The right-hand column houses the **AgentPreviewPanel**, giving you an instant interactive feedback loop:

```
┌────────────────────────────────────────────────────────┐
│ 🤖 Customer Support Agent           [🔄 Reset Session] │
├────────────────────────────────────────────────────────┤
│ [📋 Variables: company_name = "Acme", tier = "Gold"]   │
├────────────────────────────────────────────────────────┤
│ 👋 Hi! Welcome to Acme Support. How can I help?        │
│                                                        │
│ [How do I reset my password?]  [Check service status]  │
├────────────────────────────────────────────────────────┤
│ 👤 User: How do I reset my password?                   │
│                                                        │
│ 🤖 Agent:                                              │
│ 💭 Thinking (Searching KB: support_manual)...          │
│ To reset your password, please follow these steps...   │
├────────────────────────────────────────────────────────┤
│ [📎] Type a test message...                     [Send] │
└────────────────────────────────────────────────────────┘
```

### Key Preview Features

1. **Instant Draft Execution**: Messages sent in the preview panel run against your current unsaved/draft configuration (prompt, model, tools, RAG settings) without requiring you to publish.
2. **🔄 Reset Session Button**: Click the reset icon in the top-right corner of the panel to clear the conversation history and start a fresh test run. Always reset after major prompt or tool modifications to ensure clean context.
3. **Variable Testing Drawer**: If you have defined custom variables, the preview panel displays a collapsible variable drawer at the top. You can modify variable values on the fly and verify prompt interpolation immediately.
4. **Tool and CoT Inspection**: Watch reasoning/Chain of Thought unfold in real time. Hover over tool call badges to inspect tool inputs and outputs.
5. **Ask User Interactive Testing**: If `Enable interactive questions` is enabled, verify how question prompts, choice chips, custom answers, and skips behave directly in the preview composer.
6. **Opening Message & Suggested Questions Preview**: Test whether your opening greeting and suggestion chips render and trigger correctly.

---

## Publishing & Sharing

Once satisfied with the preview results:

1. Click **Publish Agent** on the top toolbar.
2. The agent becomes active for your team in the **Apps** gallery and accessible via direct chat (`/chat/{agent_id}`) and run views (`/run/{agent_id}`).
3. Click the **Embed** button on the toolbar to configure and obtain code snippets for iframe or floating chat widget embedding on external websites. (See [Embed and Share](./embed-and-share.md) for full instructions).

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

**Last Updated**: 2026-09-27
