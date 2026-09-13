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
| `context` | object | No | Bound tools, knowledge base metadata, and RAG configuration |

### Response (`200 OK`, `text/event-stream`)

Streams real-time markdown text chunks containing the generated prompt.

---

## 2. Optimize Existing Prompt

Refine an existing prompt for clarity, conciseness, instruction-following adherence, and tool use accuracy.

```http
POST /api/v1/prompts/optimize HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "current_prompt": "You are a support bot. Answer questions about products.",
  "feedback": "Make it more structured with markdown headings, handle edge cases, and ask clarifying questions before answering.",
  "language": "zh"
}
```

### Response (`200 OK`, `text/event-stream`)

Streams the rewritten and optimized system prompt.
