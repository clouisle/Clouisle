# Sorting Guide

This guide explains how ordering works in the Clouisle API.

## Overview

Regular list endpoints do **not** support client-side sorting. There are no `sort_by` / `order` query parameters on the platform list endpoints (agents, conversations, knowledge bases, workflows, users, ...) — such parameters are silently ignored.

Each list endpoint returns items in a fixed server-side order (usually newest first). To control ordering you must fetch the data and sort client-side, or use the one endpoint that does support sorting (admin observability, see below).

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
| `GET /api/v1/models` | `sort_order`, then `name` |
| `GET /api/v1/knowledge-bases/{kb_id}/documents/{doc_id}/chunks` | `chunk_index` |

These are implementation details and may change; do not rely on the exact order other than the documented intent (e.g. "newest first").

## Admin Observability Sorting (the exception)

The admin observability endpoint **does** support sorting:

```
GET /api/v1/admin/observability/agents
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `sort_by` | string | `requests` | Field to sort by |
| `sort_order` | string | `desc` | `asc` or `desc` |

**Example:**
```bash
curl -X GET "https://your-domain.com/api/v1/admin/observability/agents?sort_by=requests&sort_order=desc" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

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
- Use the admin observability `sort_by`/`sort_order` parameters where supported
- Assume only the documented ordering intent (e.g. "newest first")

**❌ Don't:**
- Send `sort_by` / `order` to regular list endpoints — they are ignored
- Rely on the exact order of items without an explicit order guarantee
- Sort large datasets client-side without paginating first

## Related Documentation

- [Filtering Guide](./filtering.md) - Filtering results
- [Pagination Guide](./pagination.md) - Paginating results
- [API Reference](./endpoints/) - Endpoint documentation

---

**Last Updated**: 2026-08-14
