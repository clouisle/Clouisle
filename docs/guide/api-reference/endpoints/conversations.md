# Conversation Statistics API

The Conversation Statistics API aggregates conversation and message activity across the agents the caller can access. It is used by the conversation dashboard.

**Base URL**: `/api/v1/conversations`

Both routes require the `conversation:read` permission.

> Conversation listing, retrieval, and deletion (`GET`/`DELETE /api/v1/conversations`, `GET`/`DELETE /api/v1/conversations/{conversation_id}`) are documented in [Chat](./chat.md); bulk deletion is in [Batch Operations](../batch-operations.md). Admin conversation management is mounted under `/api/v1/admin/conversations`.

---

## Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/conversations/stats` | Totals and per-agent breakdown for accessible conversations |
| `GET` | `/api/v1/conversations/stats/trends` | Daily time series of conversations, messages, and tokens |

### Scoping

Both routes accept the same scoping parameters:

- Without `team_id`, the scope covers every agent in the teams the caller belongs to (all agents for a superuser).
- With `team_id`, the scope is limited to that team's agents, and team membership is verified.
- Callers with dashboard access (superuser, or the owner/admin of the named team) see all conversations in scope. Members and viewers see only their own conversations.
- Passing `own_only=true` restricts any caller to their own conversations.

If the caller has access to no agents, both endpoints return zeroed data (empty `conversations_by_agent` for stats; a full range of zero-value day buckets for trends) rather than an error.

---

## 1. Get Conversation Stats

```http
GET /api/v1/conversations/stats HTTP/1.1
Authorization: Bearer <token>
```

### Query Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `team_id` | string (UUID) | No | Limit statistics to a single team |
| `own_only` | boolean | No | Only count the caller's own conversations (default: `false`) |

### Response (`200 OK`)

```json
{
  "code": 0,
  "data": {
    "total_conversations": 1284,
    "total_messages": 18237,
    "conversations_by_agent": [
      {
        "agent_id": "1c2f1a2e-0f4e-4a8f-9d4a-2b0d7b3dcb6d",
        "agent_name": "Support Assistant",
        "agent_icon": "life-buoy",
        "count": 742
      }
    ]
  },
  "msg": "success"
}
```

`conversations_by_agent` lists at most the top 10 agents by conversation count, ordered descending. If an agent record can no longer be resolved, `agent_name` falls back to the localized "unknown" label and `agent_icon` is `null`.

---

## 2. Get Conversation Trends

```http
GET /api/v1/conversations/stats/trends?period=30d HTTP/1.1
Authorization: Bearer <token>
```

### Query Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `team_id` | string (UUID) | No | Limit trends to a single team |
| `period` | string | No | Time period: `7d` (default) or `30d`. Any other value is treated as `7d` |
| `own_only` | boolean | No | Only count the caller's own conversations (default: `false`) |

### Response (`200 OK`)

```json
{
  "code": 0,
  "data": {
    "period": "7d",
    "data": [
      {
        "date": "09/20",
        "conversations": 34,
        "messages": 512,
        "tokens": 187340,
        "users": {}
      }
    ]
  },
  "msg": "success"
}
```

| Field | Type | Description |
|---|---|---|
| `period` | string | The requested period |
| `data` | array | One entry per day, oldest first, ending with today |
| `data[].date` | string | Day label formatted as `MM/DD` |
| `data[].conversations` | integer | Conversations created that day |
| `data[].messages` | integer | Messages sent that day in accessible conversations |
| `data[].tokens` | integer | Sum of `prompt` and `completion` tokens used that day |
| `data[].users` | object | Per-user breakdown, keyed by user ID: `{"name": string, "conversations": integer, "tokens": integer}` |

`users` is populated only when a `team_id` is supplied and the caller has dashboard access for that team; otherwise it is an empty object.

---

## Related

- [Chat](./chat.md) — chat completion and conversation endpoints
- [Agent Monitor](./agents.md) — agent-scoped statistics endpoints from `agent_stats.py`
- [Batch Operations](../batch-operations.md) — bulk conversation deletion
