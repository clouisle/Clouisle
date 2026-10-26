# Sorting Guide

This guide explains how ordering works in the Clouisle API.

## Overview

Regular list endpoints do **not** support client-side sorting. There are no `sort_by` / `order` query parameters on the platform list endpoints (agents, conversations, knowledge bases, workflows, users, ...) — such parameters are silently ignored.

Each list endpoint returns items in a fixed server-side order (usually newest first). To control ordering you must fetch the data and sort client-side, except for agent conversations (`GET /agents/{agent_id}/conversations`), the only list endpoint that accepts `sort_by`. Admin dashboard rankings do not accept it.

## Fixed Server-Side Ordering

Common fixed orderings used by list endpoints:

| Endpoint | Order |
|----------|-------|
| `GET /api/v1/conversations` | `-updated_at` (most recently updated first) |
| `GET /api/v1/api-keys` | `-created_at` (newest first) |
| `GET /api/v1/knowledge-bases/{kb_id}/documents` | database default |
| `GET /api/v1/workflows` | `-updated_at` |
| `GET /api/v1/workflows/runs` | `-created_at` |
| `GET /api/v1/notifications` | `-created_at` |
| `GET /api/v1/knowledge-bases/{kb_id}/documents/{doc_id}/chunks` | `chunk_index` |

These are implementation details and may change; do not rely on the exact order other than the documented intent (e.g. "newest first").

## Sorting Exceptions

One list endpoint accepts `sort_by`; everywhere else the parameter is ignored.

### Agent conversations

```
GET /api/v1/agents/{agent_id}/conversations?sort_by=updated_at
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `sort_by` | string | `updated_at` | One of `created_at`, `updated_at`, `message_count`; any other value falls back to `updated_at` |

Results are always returned in descending order for the chosen field: timestamp fields are newest-first, and `message_count` returns the highest counts first. There is no ascending option.

### Admin dashboard rankings

`/api/v1/admin/dashboard/stats/agents/top` and `/workflows/summary` return pre-ranked lists. They do not accept `sort_by`; if you need another order, sort the returned rows client-side.

## Client-Side Sorting

Since list endpoints are fixed-order, sort the returned page (or your accumulated dataset) in memory:

**Python Example:**
```python
# Fetch a page of agents
agents = api.get('/api/v1/agents', params={'page': 1, 'page_size': 100})['items']

# Sort in memory by name
agents_by_name = sorted(agents, key=lambda x: x['name'])

# Sort in memory by created_at (newest first)
agents_by_date = sorted(agents, key=lambda x: x['created_at'], reverse=True)
```

**JavaScript Example:**
```javascript
// Fetch a page of agents
const result = await api.get('/api/v1/agents', {
  params: { page: 1, page_size: 100 }
});
const agents = result.items;

// Sort in memory by name
const agentsByName = [...agents].sort((a, b) =>
  a.name.localeCompare(b.name)
);

// Sort in memory by created_at (newest first)
const agentsByDate = [...agents].sort((a, b) =>
  new Date(b.created_at) - new Date(a.created_at)
);
```

> **Note:** Sorting in memory only reorders the current page. To sort across the whole dataset, fetch all pages first, then sort (see [Pagination](./pagination.md)).

## Best Practices

**✅ Do:**
- Sort fetched pages client-side when you need a custom order
- Use `sort_by` only on `/agents/{agent_id}/conversations`, the one list endpoint that accepts it
- Assume only the documented ordering intent (e.g. "newest first")

**❌ Don't:**
- Send `sort_by` / `sort_order` to other list endpoints — they are ignored
- Rely on the exact order of items without an explicit order guarantee
- Sort large datasets client-side without paginating first

## Related Documentation

- [Filtering Guide](./filtering.md) - Filtering results
- [Pagination Guide](./pagination.md) - Paginating results
- [API Reference](./endpoints/) - Endpoint documentation

---

**Last Updated**: 2026-08-14
