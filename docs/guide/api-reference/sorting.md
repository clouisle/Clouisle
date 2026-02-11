# Sorting Guide

This guide explains how to sort API results in Clouisle.

## Overview

Sorting allows you to order API results by specific fields. Most list endpoints support sorting.

## Sort Parameters

### Standard Parameters

**Sort Parameters:**

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `sort_by` | string | Field to sort by | `sort_by=created_at` |
| `order` | string | Sort order: asc, desc | `order=desc` |

**Example Request:**

```bash
curl -X GET "https://your-domain.com/api/v1/agents?sort_by=created_at&order=desc" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Sortable Fields

### Common Sortable Fields

**Most resources support:**
- `created_at` - Creation date
- `updated_at` - Last update date
- `name` - Name (alphabetical)
- `id` - ID (default)

### Resource-Specific Fields

**Agents:**
- `name` - Agent name
- `created_at` - Creation date
- `updated_at` - Last update
- `message_count` - Number of messages
- `conversation_count` - Number of conversations

**Workflows:**
- `name` - Workflow name
- `created_at` - Creation date
- `updated_at` - Last update
- `execution_count` - Number of executions
- `success_rate` - Success rate

**Conversations:**
- `created_at` - Creation date
- `updated_at` - Last message date
- `message_count` - Number of messages

**Users:**
- `email` - Email address
- `full_name` - Full name
- `created_at` - Registration date
- `last_login` - Last login date

## Sort Examples

### Python Examples

**Basic Sorting:**
```python
# Sort by creation date (newest first)
agents = api.get('/api/v1/agents', params={
    'sort_by': 'created_at',
    'order': 'desc'
})

# Sort by name (alphabetical)
agents = api.get('/api/v1/agents', params={
    'sort_by': 'name',
    'order': 'asc'
})

# Sort by message count (highest first)
agents = api.get('/api/v1/agents', params={
    'sort_by': 'message_count',
    'order': 'desc'
})
```

**Sort with Filters:**
```python
# Sort active agents by name
agents = api.get('/api/v1/agents', params={
    'status': 'active',
    'sort_by': 'name',
    'order': 'asc'
})

# Sort recent conversations by date
conversations = api.get('/api/v1/conversations', params={
    'created_after': '2026-01-01',
    'sort_by': 'created_at',
    'order': 'desc'
})
```

**Sort with Pagination:**
```python
# Get first page sorted by date
agents = api.get('/api/v1/agents', params={
    'sort_by': 'created_at',
    'order': 'desc',
    'page': 1,
    'page_size': 20
})
```

### JavaScript Examples

**Basic Sorting:**
```javascript
// Sort by creation date (newest first)
const agents = await api.get('/api/v1/agents', {
  params: {
    sort_by: 'created_at',
    order: 'desc'
  }
});

// Sort by name (alphabetical)
const agents = await api.get('/api/v1/agents', {
  params: {
    sort_by: 'name',
    order: 'asc'
  }
});
```

**Dynamic Sorting:**
```javascript
function fetchAgents(sortBy = 'created_at', order = 'desc') {
  return api.get('/api/v1/agents', {
    params: { sort_by: sortBy, order }
  });
}

// Usage
const agentsByDate = await fetchAgents('created_at', 'desc');
const agentsByName = await fetchAgents('name', 'asc');
const agentsByUsage = await fetchAgents('message_count', 'desc');
```

## Multiple Sort Fields

### Secondary Sort

Some endpoints support multiple sort fields:

```bash
GET /api/v1/agents?sort_by=status,created_at&order=asc,desc
```

**Python Example:**
```python
# Sort by status (asc), then by date (desc)
agents = api.get('/api/v1/agents', params={
    'sort_by': 'status,created_at',
    'order': 'asc,desc'
})
```

**JavaScript Example:**
```javascript
const agents = await api.get('/api/v1/agents', {
  params: {
    sort_by: 'status,created_at',
    order: 'asc,desc'
  }
});
```

## Sort Direction

### Ascending (asc)

**Ascending order:**
- Numbers: 1, 2, 3, ...
- Dates: oldest first
- Text: A, B, C, ...

```python
# Oldest first
agents = api.get('/api/v1/agents', params={
    'sort_by': 'created_at',
    'order': 'asc'
})

# A to Z
agents = api.get('/api/v1/agents', params={
    'sort_by': 'name',
    'order': 'asc'
})
```

### Descending (desc)

**Descending order:**
- Numbers: ..., 3, 2, 1
- Dates: newest first
- Text: Z, Y, X, ...

```python
# Newest first
agents = api.get('/api/v1/agents', params={
    'sort_by': 'created_at',
    'order': 'desc'
})

# Z to A
agents = api.get('/api/v1/agents', params={
    'sort_by': 'name',
    'order': 'desc'
})
```

## UI Implementation

### React Sort Component

```jsx
import { useState, useEffect } from 'react';

function SortableTable() {
  const [agents, setAgents] = useState([]);
  const [sortBy, setSortBy] = useState('created_at');
  const [order, setOrder] = useState('desc');

  useEffect(() => {
    fetchAgents();
  }, [sortBy, order]);

  const fetchAgents = async () => {
    const result = await api.get('/api/v1/agents', {
      params: { sort_by: sortBy, order }
    });
    setAgents(result.items);
  };

  const handleSort = (field) => {
    if (sortBy === field) {
      // Toggle order
      setOrder(order === 'asc' ? 'desc' : 'asc');
    } else {
      // New field, default to desc
      setSortBy(field);
      setOrder('desc');
    }
  };

  const SortIcon = ({ field }) => {
    if (sortBy !== field) return null;
    return order === 'asc' ? '↑' : '↓';
  };

  return (
    <table>
      <thead>
        <tr>
          <th onClick={() => handleSort('name')}>
            Name <SortIcon field="name" />
          </th>
          <th onClick={() => handleSort('created_at')}>
            Created <SortIcon field="created_at" />
          </th>
          <th onClick={() => handleSort('message_count')}>
            Messages <SortIcon field="message_count" />
          </th>
        </tr>
      </thead>
      <tbody>
        {agents.map(agent => (
          <tr key={agent.id}>
            <td>{agent.name}</td>
            <td>{agent.created_at}</td>
            <td>{agent.message_count}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

### Sort Dropdown

```jsx
function SortDropdown({ onSortChange }) {
  const [sortBy, setSortBy] = useState('created_at');
  const [order, setOrder] = useState('desc');

  const handleSortChange = (field) => {
    setSortBy(field);
    onSortChange(field, order);
  };

  const handleOrderChange = (newOrder) => {
    setOrder(newOrder);
    onSortChange(sortBy, newOrder);
  };

  return (
    <div className="sort-controls">
      <select
        value={sortBy}
        onChange={(e) => handleSortChange(e.target.value)}
      >
        <option value="created_at">Date Created</option>
        <option value="updated_at">Last Updated</option>
        <option value="name">Name</option>
        <option value="message_count">Message Count</option>
      </select>

      <select
        value={order}
        onChange={(e) => handleOrderChange(e.target.value)}
      >
        <option value="desc">Descending</option>
        <option value="asc">Ascending</option>
      </select>
    </div>
  );
}
```

## Advanced Sorting

### Sort Builder

**Python Sort Builder:**
```python
class SortBuilder:
    """Build sort parameters."""

    def __init__(self):
        self.sort_fields = []
        self.sort_orders = []

    def by(self, field, order='desc'):
        """Add sort field."""
        self.sort_fields.append(field)
        self.sort_orders.append(order)
        return self

    def by_date(self, order='desc'):
        """Sort by creation date."""
        return self.by('created_at', order)

    def by_name(self, order='asc'):
        """Sort by name."""
        return self.by('name', order)

    def by_usage(self, order='desc'):
        """Sort by usage."""
        return self.by('message_count', order)

    def build(self):
        """Build sort parameters."""
        if not self.sort_fields:
            return {}

        return {
            'sort_by': ','.join(self.sort_fields),
            'order': ','.join(self.sort_orders)
        }

# Usage
sort = (SortBuilder()
    .by_date('desc')
    .by_name('asc')
    .build())

agents = api.get('/api/v1/agents', params=sort)
```

**JavaScript Sort Builder:**
```javascript
class SortBuilder {
  constructor() {
    this.sortFields = [];
    this.sortOrders = [];
  }

  by(field, order = 'desc') {
    this.sortFields.push(field);
    this.sortOrders.push(order);
    return this;
  }

  byDate(order = 'desc') {
    return this.by('created_at', order);
  }

  byName(order = 'asc') {
    return this.by('name', order);
  }

  byUsage(order = 'desc') {
    return this.by('message_count', order);
  }

  build() {
    if (this.sortFields.length === 0) {
      return {};
    }

    return {
      sort_by: this.sortFields.join(','),
      order: this.sortOrders.join(',')
    };
  }
}

// Usage
const sort = new SortBuilder()
  .byDate('desc')
  .byName('asc')
  .build();

const agents = await api.get('/api/v1/agents', { params: sort });
```

### Sort Presets

**Common Sort Presets:**
```python
class SortPresets:
    """Common sort presets."""

    @staticmethod
    def newest_first():
        """Sort by newest first."""
        return {'sort_by': 'created_at', 'order': 'desc'}

    @staticmethod
    def oldest_first():
        """Sort by oldest first."""
        return {'sort_by': 'created_at', 'order': 'asc'}

    @staticmethod
    def alphabetical():
        """Sort alphabetically."""
        return {'sort_by': 'name', 'order': 'asc'}

    @staticmethod
    def most_active():
        """Sort by most active."""
        return {'sort_by': 'message_count', 'order': 'desc'}

    @staticmethod
    def recently_updated():
        """Sort by recently updated."""
        return {'sort_by': 'updated_at', 'order': 'desc'}

# Usage
agents = api.get('/api/v1/agents', params=SortPresets.newest_first())
agents = api.get('/api/v1/agents', params=SortPresets.alphabetical())
agents = api.get('/api/v1/agents', params=SortPresets.most_active())
```

## Combining Sort, Filter, and Pagination

### Complete Example

**Python:**
```python
def get_agents(
    team_id=None,
    status=None,
    search=None,
    sort_by='created_at',
    order='desc',
    page=1,
    page_size=20
):
    """Get agents with filtering, sorting, and pagination."""
    params = {
        'sort_by': sort_by,
        'order': order,
        'page': page,
        'page_size': page_size
    }

    if team_id:
        params['team_id'] = team_id
    if status:
        params['status'] = status
    if search:
        params['search'] = search

    return api.get('/api/v1/agents', params=params)

# Usage
agents = get_agents(
    team_id='team-123',
    status='active',
    search='customer',
    sort_by='message_count',
    order='desc',
    page=1,
    page_size=50
)
```

**JavaScript:**
```javascript
async function getAgents({
  teamId = null,
  status = null,
  search = null,
  sortBy = 'created_at',
  order = 'desc',
  page = 1,
  pageSize = 20
} = {}) {
  const params = {
    sort_by: sortBy,
    order,
    page,
    page_size: pageSize
  };

  if (teamId) params.team_id = teamId;
  if (status) params.status = status;
  if (search) params.search = search;

  return api.get('/api/v1/agents', { params });
}

// Usage
const agents = await getAgents({
  teamId: 'team-123',
  status: 'active',
  search: 'customer',
  sortBy: 'message_count',
  order: 'desc',
  page: 1,
  pageSize: 50
});
```

## Client-Side Sorting

### Sort in Memory

**When to use:**
- Small datasets (< 1000 items)
- All data already loaded
- Frequent sort changes

**Python Example:**
```python
# Fetch all data
agents = api.get('/api/v1/agents', params={'page_size': 100})['items']

# Sort in memory
agents_by_name = sorted(agents, key=lambda x: x['name'])
agents_by_date = sorted(agents, key=lambda x: x['created_at'], reverse=True)
agents_by_usage = sorted(agents, key=lambda x: x['message_count'], reverse=True)
```

**JavaScript Example:**
```javascript
// Fetch all data
const result = await api.get('/api/v1/agents', {
  params: { page_size: 100 }
});
const agents = result.items;

// Sort in memory
const agentsByName = [...agents].sort((a, b) =>
  a.name.localeCompare(b.name)
);

const agentsByDate = [...agents].sort((a, b) =>
  new Date(b.created_at) - new Date(a.created_at)
);

const agentsByUsage = [...agents].sort((a, b) =>
  b.message_count - a.message_count
);
```

## Performance Optimization

### Indexed Fields

**Use indexed fields for better performance:**
- `id` - Always indexed
- `created_at` - Usually indexed
- `updated_at` - Usually indexed
- Custom indexes may exist

**Check with admin if sorting is slow.**

### Caching

**Cache sorted results:**
```python
from functools import lru_cache
import json

@lru_cache(maxsize=100)
def get_sorted_agents(sort_by, order):
    """Get agents with caching."""
    return api.get('/api/v1/agents', params={
        'sort_by': sort_by,
        'order': order
    })

# Usage
agents = get_sorted_agents('created_at', 'desc')
```

## Best Practices

### Sorting

**✅ Do:**
- Use indexed fields
- Specify sort order explicitly
- Combine with pagination
- Cache sorted results
- Use meaningful sort fields
- Provide sort UI controls
- Show current sort state

**❌ Don't:**
- Sort on non-indexed fields
- Assume default order
- Sort without pagination
- Re-fetch unnecessarily
- Use arbitrary fields
- Hide sort options
- Forget to show sort state

### Performance

**✅ Do:**
- Sort on server when possible
- Use client-side for small datasets
- Cache results
- Limit result set size
- Use appropriate indexes

**❌ Don't:**
- Sort large datasets client-side
- Skip caching
- Return all results
- Ignore performance
- Sort on computed fields

## Troubleshooting

### Invalid Sort Field

**Problem:** Sort field not recognized

**Solutions:**
1. Check field name spelling
2. Verify field is sortable
3. Review API documentation
4. Use default sort field

### Slow Sorting

**Problem:** Sorting is slow

**Solutions:**
1. Use indexed fields
2. Add database indexes
3. Reduce result set size
4. Use pagination
5. Cache results

### Inconsistent Order

**Problem:** Sort order seems random

**Solutions:**
1. Specify order explicitly
2. Use stable sort field (e.g., ID)
3. Add secondary sort
4. Check for null values

## Related Documentation

- [Filtering Guide](./filtering.md) - Filtering results
- [Pagination Guide](./pagination.md) - Paginating results
- [API Reference](./endpoints/) - Endpoint documentation
- [Performance Guide](../best-practices/performance.md) - Performance tips

---

**Last Updated**: 2026-02-11
