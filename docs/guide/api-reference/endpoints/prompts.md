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
| `context.tools` | array | No | Configured tools (`[{"name": ..., "description": ...}]`) |
| `context.knowledge_bases` | array | No | Knowledge base metadata (`[{"name": ..., "description": ...}]`) |
| `context.rag_mode` | string | No | RAG retrieval mode |
| `context.variables` | array | No | Defined variables |
| `context.capabilities` | object | No | Enabled runtime capabilities |

### Response (`200 OK`, `text/event-stream`)

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
