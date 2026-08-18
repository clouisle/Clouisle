# Filtering Guide

This guide explains how to filter API results in Clouisle.

## Overview

There is no generic query-parameter filtering system. Each list endpoint exposes its own filter parameters; unsupported parameters are ignored. This guide documents the filters that actually exist per resource.

Common conventions:

- Filters are exact matches (single values). Comma-separated "OR" lists are **not** supported (except where the parameter accepts a repeated list, e.g. `status` on knowledge bases)
- `search` / `keyword` perform case-insensitive substring matching on names
- There are **no** date-range filters (`created_after`/`created_before`/`updated_*`), relative dates (`7d`, `1m`), boolean `is_active` filters, or numeric comparison filters (`message_count_gt`, ...) on the regular list endpoints

## Agents

`GET /api/v1/agents`

| Parameter | Type | Description |
|-----------|------|-------------|
| `team_id` | UUID | Only agents in this team (requires team membership) |
| `status` | string | Single value: `draft` or `published` |
| `visibility` | string | Single value: `private` or `team` |
| `keyword` | string | Case-insensitive match on name or description |
| `own_only` | boolean | Only agents created by the current user (non-superusers) |

**Examples:**
```bash
# Agents in a team
GET /api/v1/agents?team_id=550e8400-e29b-41d4-a716-446655440000

# Published agents only
GET /api/v1/agents?status=published

# My draft agents matching "support"
GET /api/v1/agents?own_only=true&status=draft&keyword=support
```

## Conversations

`GET /api/v1/conversations`

| Parameter | Type | Description |
|-----------|------|-------------|
| `team_id` | UUID | Only conversations in this team |
| `agent_id` | UUID | Only conversations with this agent |
| `user_id` | UUID | Only conversations by this user (admin only) |
| `search` | string | Case-insensitive match on conversation title |
| `untitled_only` | boolean | Only conversations without a title |

**Examples:**
```bash
# Conversations for an agent
GET /api/v1/conversations?agent_id=550e8400-e29b-41d4-a716-446655440000

# Conversations in a team
GET /api/v1/conversations?team_id=550e8400-e29b-41d4-a716-446655440000

# Search titles
GET /api/v1/conversations?search=invoice
```

## Knowledge Bases

`GET /api/v1/knowledge-bases`

| Parameter | Type | Description |
|-----------|------|-------------|
| `team_id` | UUID | Only KBs in this team (requires team membership) |
| `search` | string | Case-insensitive match on KB name |
| `status` | list (repeatable) | `active`, `processing`, `error`, `archived`; repeat the parameter for multiple values |
| `own_only` | boolean | Only KBs created by the current user (non-superusers) |

**Examples:**
```bash
# KBs in a team matching "docs"
GET /api/v1/knowledge-bases?team_id=550e8400-e29b-41d4-a716-446655440000&search=docs

# Active KBs (multiple status values via repeated parameters)
GET /api/v1/knowledge-bases?status=active&status=archived
```

## KB Documents

`GET /api/v1/knowledge-bases/{kb_id}/documents`

| Parameter | Type | Description |
|-----------|------|-------------|
| `search` | string | Case-insensitive match on document name |
| `status` | list (repeatable) | `pending`, `processing`, `completed`, `error`, ... |
| `doc_type` | list (repeatable) | `pdf`, `docx`, `txt`, `markdown`, `html`, `csv`, `xlsx`, `json`, `pptx`, `url`, ... |

**Example:**
```bash
# Failed PDF documents
GET /api/v1/knowledge-bases/550e8400-e29b-41d4-a716-446655440000/documents?status=error&doc_type=pdf
```

## API Keys

`GET /api/v1/api-keys`

| Parameter | Type | Description |
|-----------|------|-------------|
| `status` | list (repeatable) | `active`, `inactive`, `expired` |
| `user_id` | list (repeatable) | Filter by owner (admin only) |
| `search` | string | Case-insensitive match on name or key prefix |

**Example:**
```bash
# Active keys whose name/prefix contains "prod"
GET /api/v1/api-keys?status=active&search=prod
```

## Filter Examples

### Python Examples

```python
# Filter agents by team and status
agents = api.get('/api/v1/agents', params={
    'team_id': '550e8400-e29b-41d4-a716-446655440000',
    'status': 'published'
})

# Search agents by keyword
agents = api.get('/api/v1/agents', params={
    'keyword': 'customer support'
})

# Filter conversations by agent
conversations = api.get('/api/v1/conversations', params={
    'agent_id': '550e8400-e29b-41d4-a716-446655440000'
})

# Filter knowledge bases
kbs = api.get('/api/v1/knowledge-bases', params={
    'team_id': '550e8400-e29b-41d4-a716-446655440000',
    'search': 'docs'
})
```

### JavaScript Examples

```javascript
// Filter agents by team and status
const agents = await api.get('/api/v1/agents', {
  params: {
    team_id: '550e8400-e29b-41d4-a716-446655440000',
    status: 'published'
  }
});

// Filter conversations by agent
const conversations = await api.get('/api/v1/conversations', {
  params: {
    agent_id: '550e8400-e29b-41d4-a716-446655440000'
  }
});

// Filter knowledge bases
const kbs = await api.get('/api/v1/knowledge-bases', {
  params: {
    search: 'docs'
  }
});
```

### Dynamic Filters

```javascript
function buildAgentFilters(options) {
  const filters = {};

  if (options.teamId) {
    filters.team_id = options.teamId;
  }

  if (options.status) {
    filters.status = options.status;
  }

  if (options.keyword) {
    filters.keyword = options.keyword;
  }

  if (options.ownOnly) {
    filters.own_only = true;
  }

  return filters;
}

// Usage
const filters = buildAgentFilters({
  teamId: '550e8400-e29b-41d4-a716-446655440000',
  status: 'published',
  keyword: 'support'
});

const agents = await api.get('/api/v1/agents', { params: filters });
```

## Combining Filters with Pagination

All list endpoints accept `page` and `page_size` alongside filters:

```python
results = api.get('/api/v1/agents', params={
    'team_id': '550e8400-e29b-41d4-a716-446655440000',
    'status': 'published',
    'page': 1,
    'page_size': 20
})

print(f"Found {results['total']} results")
```

## Best Practices

**✅ Do:**
- Use the documented filters per endpoint
- Combine filters with pagination
- Handle empty results
- Cache filtered results when the data is stable
- Debounce search input in UIs

**❌ Don't:**
- Expect generic filters (`created_after`, `is_active`, `sort_by`, ...) to work — they are ignored by regular list endpoints
- Use comma-separated OR syntax (`status=active,inactive`) except where the parameter is a repeatable list
- Fetch without filters when you only need a subset
- Update search requests on every keystroke

## Troubleshooting

### No Results

**Problem:** Filter returns empty results

**Solutions:**
1. Check filter values are correct (e.g. `status` must be `draft`/`published` for agents)
2. Verify data exists and you have access (filters like `own_only` restrict visibility)
3. Try broader filters

### Filter Seemingly Ignored

**Problem:** A parameter has no effect

**Solutions:**
1. Verify the parameter is supported by that endpoint (see tables above)
2. Unsupported parameters are silently ignored
3. For KB/API-key `status`, pass the parameter multiple times for multiple values

## Related Documentation

- [Pagination Guide](./pagination.md) - Paginating results
- [Response Format](./response-format.md) - Response structure
- [API Reference](./endpoints/) - Endpoint documentation

---

**Last Updated**: 2026-08-14
