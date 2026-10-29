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

## 通过飞书机器人与 Agent 对话

如果管理员启用了飞书 Agent 对话，请在 **个人设置 → 飞书** 中选择回复自己的智能体并点击 **保存**；开启对话后，也可以私聊机器人发送 `/智能体`（`/agents`）查看自己有权访问的已发布 Agent，再用 `/使用 <编号>`（`/use <编号>`）切换。网页和飞书命令共用当前用户的选择，不影响其他用户。同一飞书聊天中，每个智能体单独保留会话，切回后继续之前的对话；切换只影响后续接收的消息，已接收消息和任务保留原绑定。未选择时不会自动使用管理员指定的 Agent。当前运行结束后，可用 `/新对话`（`/new`）为所选 Agent 开启新对话。

首次使用请先保存智能体，再打开 **启用智能体对话**。开关自动保存，仅影响本人。关闭后不接收新消息（包括命令），已接收但尚未处理的消息和待发送回复暂停，重新开启后继续处理；智能体选择和历史保留。关闭不会停止已开始的任务或撤回已发送的回复，关闭期间收到的新消息不会保存或补处理。需回到个人设置重新启用。

发送 `/status`（`/状态`）查看运行状态，发送 `/stop`（`/停止`）停止当前运行，发送 `/help`（`/帮助`）查看命令。Agent 通过 `ask_user` 等待回答时，在同一聊天发送文本会恢复原有运行，而不是创建新运行。机器人仅支持私聊文本；不处理群聊、附件和其他媒体，也不会通过机器人读取另一个聊天的历史记录。

飞书消息使用你已绑定且活跃的 Clouisle 账号，并遵循正常 Agent/team 权限。管理员仅配置共享通道，不再配置全局 Agent 名单。Agent 运行和对话仍保存在 Clouisle；飞书仅作为消息传输通道。

## Chat through the Feishu bot

If your administrator enabled Feishu Agent chat, choose your replying Agent in **Personal settings → Feishu** and click **Save**. Once chat is enabled, you can also message the bot with `/agents` (`/智能体`) and `/use <number>` (`/使用 <number>`). Both interfaces share your personal selection and cannot affect another user's selection. Each Agent keeps its own conversation within the same Feishu chat; switching back continues that conversation. Switching affects subsequently accepted messages only; accepted messages and runs retain their original binding. No Agent is selected automatically for a new user. `/new` (`/新对话`) starts a fresh conversation after the current run finishes.

For first use, save an Agent and turn on **Enable Agent chat**. The switch saves automatically and affects only you. Turning it off rejects new messages, including commands, and pauses previously accepted messages awaiting processing and replies awaiting delivery; turning it back on resumes pending work. Your Agent selection and history are preserved. Turning it off does not stop tasks already started or recall sent replies. New messages received while off are not saved for later processing. Return to personal settings to re-enable chat.

Use `/status` (`/状态`) to check progress, `/stop` (`/停止`) to stop the current run, and `/help` (`/帮助`) for commands. When an Agent is waiting for an `ask_user` answer, send a text response in that same chat; it resumes the waiting run rather than starting a new one. The bot supports private text chats only: group messages, attachments, and other media are not processed. Feishu does not expose another chat's history through the bot.

Feishu messages use your linked active Clouisle account and normal Agent/team permissions. Administrators configure the shared transport, not a global Agent list. Agent runs and conversations remain Clouisle records; Feishu is only the transport.

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
│  Agent: Clouisle is a multi-agent...           │
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
4. Wait for the original file to finish uploading
5. Add your message or question about the file
6. Click **Send**


Chat attachments are kept as scoped Asset references in conversation history. Documents are not automatically inserted into model context, including PDFs. The Agent uses `read_asset` to read bounded line ranges and `search_asset` to locate text. Complete extracted text is prepared on first use and persisted for subsequent reads; a continuation cursor allows the Agent to reach the end without returning the whole document at once. Each operation reauthorizes the original Asset and its conversation branch.

Images, audio, and video retain native model input when the selected adapter supports their modality and MIME type. For documents, line numbers refer to extracted text, not PDF pages. Explicit native PDF viewing uses bounded page selections; audio/video time selections require FFmpeg. Empty or failed extraction is reported rather than presented as a complete document; scanned images and complex layouts may require native viewing. A full-document task is not complete until reading reaches `eof`; model execution budgets may prevent completing that in one run.

The Agent discovers older files with `list_assets`, using an optional case-insensitive filename `query` and `kind` (`image`, `audio`, `video`, or `file`). Results include scope-local refs and metadata, never file bytes or download credentials. Pages contain 10 items by default (maximum 30). When `has_more` is true, repeat the query and kind with `next_cursor`; use `read_asset`/`search_asset` for document text or `view_asset` for native media. Discovery excludes unavailable/expired assets and files attached only to inactive branches, and cannot search another conversation.


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

### Response Anatomy & Visual Elements

Clouisle delivers a rich, structured assistant message structure:

```
┌────────────────────────────────────────────────────────┐
│ 💭 思考了 3 秒 (Thought for 3s)                 [▲/▼] │
│  ├── 正在读取文件: report.pdf... (Tool Action)         │
│  └── 分析检索到的要点并组织输出结构...                   │
├────────────────────────────────────────────────────────┤
│ 📚 检索来源 (Sources):                                 │
│  [📄 report.pdf (Chunk 2, 89%)] [📄 manual.md]        │
├────────────────────────────────────────────────────────┤
│                                                        │
│ Here is the quarterly summary based on your document: │
│                                                        │
│ 1. Revenue grew by 24% year-over-year.                 │
│ 2. Customer satisfaction score reached 96%.            │
│                                                        │
├────────────────────────────────────────────────────────┤
│ 📦 生成产物 (Artifacts):                               │
│  ┌──────────────────────────────────────────────────┐  │
│  │ 📊 quarterly_summary.xlsx    [预览]   [⬇️ 下载]  │  │
│  └──────────────────────────────────────────────────┘  │
├────────────────────────────────────────────────────────┤
│ [🔄 重新生成] [📋 复制] [‹ 2/3 ›]   ⏱️ 1.2s  ⚡ 42 t/s  │
└────────────────────────────────────────────────────────┘
```

#### 1. Chain of Thought (CoT) & Dynamic Tool Perception

The reasoning header dynamically reflects the model's high-level execution state in real time:
- **Pure Reasoning**: While the model streams reasoning tokens with no active tools, the header displays an animated shimmer with `思考中...` (`Thinking...`).
- **Single Active Tool**: The header semantically classifies the active tool call and displays intuitive action phrases (e.g., `正在读取文件...`, `正在运行代码...`, `正在查询：{name}...`, `正在请求接口：{endpoint}...`).
- **Parallel Tool Execution**: When multiple tools execute concurrently, the header aggregates them as `正在并行调用 {count} 个工具...` (`Calling {count} tools in parallel...`).
- **Completed State**: Once the agent finishes generating, the header shows the total reasoning duration (e.g., `思考了 4 秒` / `Thought for 4s`) and can be collapsed or expanded at any time.

#### 2. Interactive Human-in-the-Loop (`AskUserForm`)

When an agent needs human input or clarification before proceeding, it invokes the built-in `ask_user` tool:
- **Composer-Level Form**: The interactive question form appears directly above the input box (rather than being buried in the message stream).
- **Flexible Answers**:
  - **Option Chips**: Click predefined suggestion chips.
  - **Custom Text**: Type a custom text response beneath the options.
  - **Multi-Question Pagination**: Page through multiple structured questions.
  - **Skip Action**: Click **Skip All** (`跳过全部`) to bypass the prompt and allow the agent to make default assumptions.
- **Durable Execution**: Submitting the answer seamlessly resumes the active server run without resetting conversation history.

#### 3. Generated Artifacts & File Preview (`ArtifactFileList`)

When an agent or sandbox code execution generates output files (spreadsheets, charts, reports, images, code snippets):
- **Artifact list header**: Shows a package icon and the total file count. The list initially shows up to three files and provides **Show more** for the remainder.
- **Interactive previews**: Images open in the lightbox; PDF, DOCX, PPTX, XLSX/CSV, Markdown, HTML, text, audio, video, and Mermaid files use the shared preview panel when their type is supported.
- **Document controls**: DOCX previews provide thumbnails, page navigation, fit-to-width, and zoom controls. Spreadsheet previews provide sheet tabs and zoom controls without a second in-viewer download action.
- **Direct download**: Artifact rows and the preview header expose download actions, subject to the authenticated user's or API key's asset permissions.

#### 4. Protected assets and preview failures

Generated images, generated videos, and sandbox artifacts are protected assets. The UI fetches them with the active session/API token and does not fall back to a raw unauthenticated URL. The preview panel reports distinct states for unsupported types, files too large for preview, unauthorized access, permission denial, and load/parse failures. A file that is too large to preview may still be downloadable when the user is authorized.

#### 5. Source Citations (RAG)

When knowledge base retrieval is active:
- Sources are listed with document titles, chunk indexes, and similarity match percentages.
- Click any source badge to inspect the exact retrieved text segment in a popover.
The reasoning timeline preserves the order in which progress events were emitted. Retrieval, context compression, reasoning, tool calls, media results, and text generation can appear interleaved; the interface does not always place retrieval first.

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

- **off**: No retrieval, even if knowledge bases are configured.
- **auto**: Automatically retrieve on every message (traditional RAG).
- **agentic**: The agent decides when to search.

When an Agent has no knowledge-base associations, the backend normalizes its persisted mode to `off`, and the editor hides the RAG selector until a knowledge base is attached. With retrieval enabled, the response can include retrieved source chunks and stable citation IDs.

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
Agent: Clouisle is a multi-agent collaboration platform and workflow engine...

You: How do I install it?
Agent: To install Clouisle, follow these steps...
     [Agent remembers we're talking about Clouisle]
```

Long conversations are automatically compressed to fit the model's context window. The thought-process timeline shows when older history was summarized or completed tool results were compacted, but does not display token counts. If summarization fails after retries, earlier assistant and tool history is omitted while user messages and the recent conversation are retained; restate key details or start a new conversation if the answer seems to miss context. Agents can turn this behavior off in their Context Compression settings.

## Advanced Features & Multi-Version Branching

### Message Regeneration & Version Navigation

If you want a different answer from the agent:

1. Hover over the assistant's response.
2. Click the **🔄 Regenerate** button on the message action toolbar.
3. The agent streams a new response while preserving the previous output as a historical version.
4. Use the version paginator (`‹ 1/2 ›`) below the message to toggle between versions.

### Message Editing & Conversation Branching

You can edit any user message previously sent:

1. Hover over your message and click the **✏️ Edit** button.
2. Modify the text in the inline editor.
3. Click **Resend** or press **Enter**.
4. The conversation branches from that point onward, creating a new revision timeline while retaining earlier conversation branches.

### Copy & Speed Metrics

Each message action bar provides:
- **📋 Copy Message**: Copies the raw Markdown text to your clipboard.
- **Message Performance Stats**: Shows total generation latency, time-to-first-token, and tokens per second (t/s) (can be toggled off via agent settings).

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

**Last Updated**: 2026-09-08
