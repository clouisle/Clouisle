# Prompt Generator API

The Prompt Generator API provides AI-powered streaming endpoints for generating and optimizing system prompts for Agents and Workflows based on target capabilities, tools, knowledge bases, and behavioral style constraints.

**Base URL**: `/api/v1/prompts`

---

## Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/prompts/generate` | Generate a new structured system prompt via streaming SSE |
| `POST` | `/api/v1/prompts/optimize` | Optimize and refine an existing system prompt via streaming SSE |

---

## 1. Generate System Prompt

Generate a production-ready system prompt tailored to an agent's configured tools, knowledge bases, and role profile.

```http
POST /api/v1/prompts/generate HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "description": "A customer support specialist who troubleshoots billing issues and queries policy knowledge bases.",
  "language": "zh",
  "style": {
    "tone": "professional",
    "focus": "task-oriented",
    "include_cot": true,
    "include_constraints": true
  },
  "context": {
    "agent_name": "Billing Support Specialist",
    "agent_description": "Resolves user subscription and refund questions",
    "tools": [
      {"name": "query_invoice", "description": "Fetch user invoice by order ID"}
    ],
    "knowledge_bases": [
      {"name": "Refund Policy 2026", "description": "Rules on 14-day money back guarantees"}
    ],
    "rag_mode": "agentic"
  }
}
```

### Request Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `description` | string | Yes | High-level description of agent purpose and workflow |
| `language` | string | No | Target output language (`zh` or `en`, default: `zh`) |
| `style.tone` | string | No | `professional`, `friendly`, `concise`, or `detailed` |
| `style.focus` | string | No | `task-oriented`, `conversational`, or `balanced` |
| `style.include_cot` | boolean | No | Whether to include Chain-of-Thought thinking guidelines |
| `style.include_constraints` | boolean | No | Whether to include explicit safety and boundary constraints |
| `context` | object | No | Bound agent context; see the subfields below |
| `context.tools` | array | No | Configured tool metadata: `type`, `name`, optional `display_name`, `description`, IDs and `config`. Names identify tools; display labels do not replace them. MCP/skill entries do not enumerate their internal tools. |
| `context.knowledge_bases` | array | No | Linked knowledge base `name`, `description` and retrieval `config` |
| `context.rag_mode` | string | No | `off`: no linked-KB retrieval; `auto`: platform-injected retrieval; `agentic`: on-demand `knowledge_search` when knowledge bases are linked |
| `context.variables` | array | No | Defined variables and their type, required/default values, descriptions and limits; generated prompts may reference their `{{name}}` placeholders |
| `context.capabilities` | object | No | `enable_attachments`, `enable_user_input_request` (`ask_user`), `enable_citations`, `enable_memory`, `enable_image_generation`, `enable_video_generation`, plus `attachment_config`, `memory_config`, `image_generation_config`, `video_generation_config` |

The Agent orchestration editor supplies current editor values, including unsaved capability changes. Explicitly disabled capabilities are identified as disabled; their stale configuration is omitted from the generation context. Omitted capability flags mean unknown, not enabled. Context guides generation only: it does not grant runtime access or enable any tool.

Generation produces the business role, task workflow and output requirements, not a copy of the platform's runtime manuals. Runtime tool schemas and capability-dependent instructions remain authoritative. `{{query}}` refers to the current user message; `{{fileContent}}` is not supported for attachment injection. Citation instructions require both the citation preference and actual sources. These changes affect newly generated prompts only; existing saved system prompts are not rewritten.

Memory-specific generation follows the chat runtime: `enable_memory=false` exposes no memory tools. When enabled, `search_memory` and `get_memory_subgraph` can retrieve long-term user information. `memory_config.auto_extract=false` keeps those reads but removes entity/relation write tools; `true` (the runtime default when omitted) permits the available write tools, not guaranteed automatic saving on every turn. Generated business instructions should define relevant retrieval/storage conditions, not invent memories, relationships, tool arguments or persistence guarantees. Current conversation history, long-term memory and knowledge bases are distinct sources.

### Response (`200 OK`, `text/event-stream`)

Generation uses the enabled **global default chat model**, not the model selected for the Agent. Optimization uses the same selection. If that provider returns HTTP `402` or an insufficient-quota error, the SSE error has business code `6103` (`MODEL_QUOTA_EXCEEDED`) and a localized quota-exhaustion message, which the generation dialog displays. This does not replenish quota: check the provider account/API key for the global default model, fund or raise its quota, or explicitly configure another default chat model. No automatic retry or model fallback is performed by these endpoints. Other unexpected provider failures retain a generic safe message; raw provider payloads are not exposed to the client.

Streams the generated prompt as SSE events: `start` (`{"model": "..."}`), `content_delta` (`{"delta": "..."}`), `complete` (`{"total_length": n}`), and `error` (`{"code": ..., "msg": "..."}`).

---

## 2. Optimize Existing Prompt

Refine an existing prompt for clarity, conciseness, instruction-following adherence, and tool use accuracy. Unlike `/generate` (which takes a JSON body), this endpoint takes both inputs as **query parameters**.

```http
POST /api/v1/prompts/optimize?current_prompt=You%20are%20a%20support%20bot.%20Answer%20questions%20about%20products.&feedback=Make%20it%20more%20structured%20with%20markdown%20headings%2C%20handle%20edge%20cases%2C%20and%20ask%20clarifying%20questions%20before%20answering. HTTP/1.1
Authorization: Bearer <token>
```

### Query Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `current_prompt` | string | Yes | The system prompt to optimize |
| `feedback` | string | Yes | Instructions describing how the prompt should be improved |

There is no `language` parameter — the optimization meta-prompt is always built in Chinese and the model is asked to return the rewritten prompt.

### Response (`200 OK`, `text/event-stream`)

Streams the rewritten and optimized system prompt as SSE events: `start`, `content_delta` (`{"delta": "..."}`), `complete` (`{"total_length": n}`), and `error` (`{"code": ..., "msg": "..."}`).
