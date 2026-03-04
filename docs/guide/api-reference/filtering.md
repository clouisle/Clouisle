# Filtering Guide

This guide explains how to filter API results in Clouisle.

## Overview

Filtering allows you to narrow down API results based on specific criteria. Most list endpoints support filtering.

## Filter Parameters

### Common Filter Parameters

**Standard Filters:**

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `search` | string | Search by name or text | `search=customer` |
| `status` | string | Filter by status | `status=active` |
| `is_active` | boolean | Filter by active state | `is_active=true` |
| `created_after` | string | Created after date | `created_after=2026-01-01` |
| `created_before` | string | Created before date | `created_before=2026-12-31` |
| `updated_after` | string | Updated after date | `updated_after=2026-01-01` |
| `updated_before` | string | Updated before date | `updated_before=2026-12-31` |

### Resource-Specific Filters

**Agents:**
```bash
GET /api/v1/agents?team_id=team-123&model=gpt-4-turbo&is_published=true
```

**Workflows:**
```bash
GET /api/v1/workflows?team_id=team-123&trigger_type=webhook&status=active
```

**Conversations:**
```bash
GET /api/v1/conversations?agent_id=agent-123&user_id=user-456&has_messages=true
```

**Users:**
```bash
GET /api/v1/users?role=admin&is_active=true&team_id=team-123
```

## Filter Syntax

### Exact Match

**Single Value:**
```bash
GET /api/v1/agents?status=active
```

**Multiple Values (OR):**
```bash
GET /api/v1/agents?status=active,inactive
```

### Text Search

**Search in name/description:**
```bash
GET /api/v1/agents?search=customer support
```

**Case-insensitive search:**
```bash
GET /api/v1/agents?search=CUSTOMER  # Matches "customer", "Customer", "CUSTOMER"
```

### Boolean Filters

**Boolean values:**
```bash
GET /api/v1/agents?is_active=true
GET /api/v1/agents?is_published=false
```

### Date Filters

**Date range:**
```bash
GET /api/v1/agents?created_after=2026-01-01&created_before=2026-12-31
```

**Relative dates:**
```bash
GET /api/v1/agents?created_after=7d  # Last 7 days
GET /api/v1/agents?created_after=1m  # Last month
GET /api/v1/agents?created_after=1y  # Last year
```

### Numeric Filters

**Comparison operators:**
```bash
GET /api/v1/agents?message_count_gt=100    # Greater than
GET /api/v1/agents?message_count_gte=100   # Greater than or equal
GET /api/v1/agents?message_count_lt=1000   # Less than
GET /api/v1/agents?message_count_lte=1000  # Less than or equal
```

**Range:**
```bash
GET /api/v1/agents?message_count_gte=100&message_count_lte=1000
```

## Combining Filters

### Multiple Filters (AND)

**All conditions must match:**
```bash
GET /api/v1/agents?team_id=team-123&status=active&is_published=true
```

### Complex Queries

**Combine different filter types:**
```bash
GET /api/v1/agents?
  team_id=team-123&
  status=active,published&
  created_after=2026-01-01&
  search=customer&
  message_count_gte=100
```

## Filter Examples

### Python Examples

**Basic Filtering:**
```python
# Filter by team
agents = api.get('/api/v1/agents', params={
    'team_id': 'team-123'
})

# Filter by status
agents = api.get('/api/v1/agents', params={
    'status': 'active'
})

# Multiple filters
agents = api.get('/api/v1/agents', params={
    'team_id': 'team-123',
    'status': 'active',
    'is_published': True
})
```

**Date Filtering:**
```python
from datetime import datetime, timedelta

# Last 7 days
week_ago = (datetime.now() - timedelta(days=7)).isoformat()
agents = api.get('/api/v1/agents', params={
    'created_after': week_ago
})

# Date range
agents = api.get('/api/v1/agents', params={
    'created_after': '2026-01-01',
    'created_before': '2026-12-31'
})
```

**Search Filtering:**
```python
# Search by name
agents = api.get('/api/v1/agents', params={
    'search': 'customer support'
})

# Search with other filters
agents = api.get('/api/v1/agents', params={
    'search': 'customer',
    'team_id': 'team-123',
    'status': 'active'
})
```

**Numeric Filtering:**
```python
# Greater than
agents = api.get('/api/v1/agents', params={
    'message_count_gt': 100
})

# Range
agents = api.get('/api/v1/agents', params={
    'message_count_gte': 100,
    'message_count_lte': 1000
})
```

### JavaScript Examples

**Basic Filtering:**
```javascript
// Filter by team
const agents = await api.get('/api/v1/agents', {
  params: {
    team_id: 'team-123'
  }
});

// Multiple filters
const agents = await api.get('/api/v1/agents', {
  params: {
    team_id: 'team-123',
    status: 'active',
    is_published: true
  }
});
```

**Date Filtering:**
```javascript
// Last 7 days
const weekAgo = new Date();
weekAgo.setDate(weekAgo.getDate() - 7);

const agents = await api.get('/api/v1/agents', {
  params: {
    created_after: weekAgo.toISOString()
  }
});

// Date range
const agents = await api.get('/api/v1/agents', {
  params: {
    created_after: '2026-01-01',
    created_before: '2026-12-31'
  }
});
```

**Dynamic Filters:**
```javascript
function buildFilters(options) {
  const filters = {};

  if (options.teamId) {
    filters.team_id = options.teamId;
  }

  if (options.status) {
    filters.status = options.status;
  }

  if (options.search) {
    filters.search = options.search;
  }

  if (options.createdAfter) {
    filters.created_after = options.createdAfter;
  }

  return filters;
}

// Usage
const filters = buildFilters({
  teamId: 'team-123',
  status: 'active',
  search: 'customer'
});

const agents = await api.get('/api/v1/agents', { params: filters });
```

## Advanced Filtering

### Filter Builder

**Python Filter Builder:**
```python
class FilterBuilder:
    """Build API filters dynamically."""

    def __init__(self):
        self.filters = {}

    def add(self, key, value):
        """Add filter."""
        if value is not None:
            self.filters[key] = value
        return self

    def search(self, query):
        """Add search filter."""
        return self.add('search', query)

    def team(self, team_id):
        """Add team filter."""
        return self.add('team_id', team_id)

    def status(self, status):
        """Add status filter."""
        return self.add('status', status)

    def active(self, is_active=True):
        """Add active filter."""
        return self.add('is_active', is_active)

    def created_after(self, date):
        """Add created after filter."""
        return self.add('created_after', date)

    def created_before(self, date):
        """Add created before filter."""
        return self.add('created_before', date)

    def build(self):
        """Build filter dict."""
        return self.filters

# Usage
filters = (FilterBuilder()
    .team('team-123')
    .status('active')
    .search('customer')
    .created_after('2026-01-01')
    .build())

agents = api.get('/api/v1/agents', params=filters)
```

**JavaScript Filter Builder:**
```javascript
class FilterBuilder {
  constructor() {
    this.filters = {};
  }

  add(key, value) {
    if (value !== null && value !== undefined) {
      this.filters[key] = value;
    }
    return this;
  }

  search(query) {
    return this.add('search', query);
  }

  team(teamId) {
    return this.add('team_id', teamId);
  }

  status(status) {
    return this.add('status', status);
  }

  active(isActive = true) {
    return this.add('is_active', isActive);
  }

  createdAfter(date) {
    return this.add('created_after', date);
  }

  createdBefore(date) {
    return this.add('created_before', date);
  }

  build() {
    return this.filters;
  }
}

// Usage
const filters = new FilterBuilder()
  .team('team-123')
  .status('active')
  .search('customer')
  .createdAfter('2026-01-01')
  .build();

const agents = await api.get('/api/v1/agents', { params: filters });
```

### Filter Presets

**Common Filter Presets:**
```python
class FilterPresets:
    """Common filter presets."""

    @staticmethod
    def active_agents(team_id=None):
        """Get active agents."""
        filters = {'status': 'active', 'is_active': True}
        if team_id:
            filters['team_id'] = team_id
        return filters

    @staticmethod
    def recent_conversations(days=7):
        """Get recent conversations."""
        from datetime import datetime, timedelta
        date = (datetime.now() - timedelta(days=days)).isoformat()
        return {'created_after': date}

    @staticmethod
    def published_agents():
        """Get published agents."""
        return {'is_published': True, 'status': 'active'}

    @staticmethod
    def high_usage_agents(min_messages=1000):
        """Get high usage agents."""
        return {'message_count_gte': min_messages}

# Usage
agents = api.get('/api/v1/agents', params=FilterPresets.active_agents('team-123'))
conversations = api.get('/api/v1/conversations', params=FilterPresets.recent_conversations(7))
```

## UI Implementation

### React Filter Component

```jsx
import { useState } from 'react';

function AgentFilters({ onFilterChange }) {
  const [filters, setFilters] = useState({
    search: '',
    team_id: '',
    status: '',
    is_active: true
  });

  const handleChange = (key, value) => {
    const newFilters = { ...filters, [key]: value };
    setFilters(newFilters);
    onFilterChange(newFilters);
  };

  const handleReset = () => {
    const resetFilters = {
      search: '',
      team_id: '',
      status: '',
      is_active: true
    };
    setFilters(resetFilters);
    onFilterChange(resetFilters);
  };

  return (
    <div className="filters">
      <input
        type="text"
        placeholder="Search..."
        value={filters.search}
        onChange={(e) => handleChange('search', e.target.value)}
      />

      <select
        value={filters.team_id}
        onChange={(e) => handleChange('team_id', e.target.value)}
      >
        <option value="">All Teams</option>
        <option value="team-123">Team 1</option>
        <option value="team-456">Team 2</option>
      </select>

      <select
        value={filters.status}
        onChange={(e) => handleChange('status', e.target.value)}
      >
        <option value="">All Status</option>
        <option value="active">Active</option>
        <option value="inactive">Inactive</option>
      </select>

      <label>
        <input
          type="checkbox"
          checked={filters.is_active}
          onChange={(e) => handleChange('is_active', e.target.checked)}
        />
        Active Only
      </label>

      <button onClick={handleReset}>Reset Filters</button>
    </div>
  );
}

// Usage
function AgentList() {
  const [agents, setAgents] = useState([]);
  const [filters, setFilters] = useState({});

  useEffect(() => {
    fetchAgents();
  }, [filters]);

  const fetchAgents = async () => {
    const result = await api.get('/api/v1/agents', { params: filters });
    setAgents(result.items);
  };

  return (
    <div>
      <AgentFilters onFilterChange={setFilters} />
      <ul>
        {agents.map(agent => (
          <li key={agent.id}>{agent.name}</li>
        ))}
      </ul>
    </div>
  );
}
```

### URL Query Parameters

**Sync filters with URL:**
```javascript
import { useSearchParams } from 'react-router-dom';

function AgentList() {
  const [searchParams, setSearchParams] = useSearchParams();

  // Read filters from URL
  const filters = {
    search: searchParams.get('search') || '',
    team_id: searchParams.get('team_id') || '',
    status: searchParams.get('status') || ''
  };

  // Update URL when filters change
  const handleFilterChange = (newFilters) => {
    const params = new URLSearchParams();

    Object.entries(newFilters).forEach(([key, value]) => {
      if (value) {
        params.set(key, value);
      }
    });

    setSearchParams(params);
  };

  // Fetch with filters from URL
  useEffect(() => {
    fetchAgents(filters);
  }, [searchParams]);

  return (
    <div>
      <AgentFilters
        filters={filters}
        onFilterChange={handleFilterChange}
      />
      {/* ... */}
    </div>
  );
}
```

## Filter Validation

### Validate Filters

**Python Validation:**
```python
def validate_filters(filters):
    """Validate filter parameters."""
    errors = []

    # Validate date format
    if 'created_after' in filters:
        try:
            datetime.fromisoformat(filters['created_after'])
        except ValueError:
            errors.append('Invalid created_after date format')

    # Validate boolean
    if 'is_active' in filters:
        if not isinstance(filters['is_active'], bool):
            errors.append('is_active must be boolean')

    # Validate enum
    if 'status' in filters:
        valid_statuses = ['active', 'inactive', 'draft']
        if filters['status'] not in valid_statuses:
            errors.append(f'status must be one of: {valid_statuses}')

    if errors:
        raise ValueError(f"Invalid filters: {', '.join(errors)}")

    return filters

# Usage
try:
    filters = validate_filters({
        'team_id': 'team-123',
        'status': 'active',
        'created_after': '2026-01-01'
    })
    agents = api.get('/api/v1/agents', params=filters)
except ValueError as e:
    print(f"Validation error: {e}")
```

## Performance Optimization

### Filter Caching

**Cache filtered results:**
```python
from functools import lru_cache
import json

@lru_cache(maxsize=100)
def get_filtered_agents(filter_json):
    """Get agents with caching."""
    filters = json.loads(filter_json)
    return api.get('/api/v1/agents', params=filters)

# Usage
filters = {'team_id': 'team-123', 'status': 'active'}
agents = get_filtered_agents(json.dumps(filters, sort_keys=True))
```

### Debounced Search

**Debounce search input:**
```javascript
import { useState, useEffect } from 'react';

function useDebounce(value, delay = 500) {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => clearTimeout(handler);
  }, [value, delay]);

  return debouncedValue;
}

// Usage
function SearchFilter() {
  const [search, setSearch] = useState('');
  const debouncedSearch = useDebounce(search, 500);

  useEffect(() => {
    if (debouncedSearch) {
      fetchAgents({ search: debouncedSearch });
    }
  }, [debouncedSearch]);

  return (
    <input
      type="text"
      value={search}
      onChange={(e) => setSearch(e.target.value)}
      placeholder="Search..."
    />
  );
}
```

## Best Practices

### Filtering

**✅ Do:**
- Use specific filters
- Combine filters for precision
- Validate filter values
- Handle empty results
- Cache filtered results
- Debounce search input
- Show active filters to users
- Allow filter reset

**❌ Don't:**
- Over-filter (too restrictive)
- Skip validation
- Ignore empty results
- Fetch without filters
- Update on every keystroke
- Hide active filters
- Forget reset option

### Performance

**✅ Do:**
- Use indexed fields for filtering
- Limit result set size
- Cache common filters
- Use pagination with filters
- Optimize database queries

**❌ Don't:**
- Filter on non-indexed fields
- Return all results
- Skip caching
- Forget pagination
- Ignore query performance

## Troubleshooting

### No Results

**Problem:** Filter returns empty results

**Solutions:**
1. Check filter values are correct
2. Verify data exists
3. Try broader filters
4. Check permissions
5. Review filter logic

### Slow Filtering

**Problem:** Filtering is slow

**Solutions:**
1. Add database indexes
2. Use pagination
3. Cache results
4. Optimize queries
5. Reduce filter complexity

### Invalid Filters

**Problem:** Filter validation fails

**Solutions:**
1. Check filter syntax
2. Verify parameter names
3. Validate data types
4. Review API documentation
5. Check for typos

## Related Documentation

- [Pagination Guide](./pagination.md) - Paginating results
- [Sorting Guide](./sorting.md) - Sorting results
- [Search Guide](./search.md) - Search functionality
- [API Reference](./endpoints/) - Endpoint documentation

---

**Last Updated**: 2026-02-11
