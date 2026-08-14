# Pagination Guide

This guide explains how to work with paginated API responses in Clouisle.

## Overview

Pagination allows you to retrieve large datasets in manageable chunks. List endpoints in Clouisle return page-based results.

## Pagination Parameters

### Query Parameters

**Standard Parameters:**

| Parameter | Type | Default | Max | Description |
|-----------|------|---------|-----|-------------|
| `page` | integer | 1 | - | Page number (1-indexed) |
| `page_size` | integer | 20 | varies | Items per page |

`page_size` is not uniformly capped: most list endpoints accept any value, while some endpoints (e.g. conversations, admin observability) constrain it with `le=100`. Check the individual endpoint schema for the exact bound.

**Example Request:**

```bash
curl -X GET "https://your-domain.com/api/v1/agents?page=2&page_size=50" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Response Format

### Paginated Response Structure

```json
{
  "code": 0,
  "data": {
    "items": [...],
    "total": 156,
    "page": 2,
    "page_size": 50
  },
  "msg": "success"
}
```

**Response Fields:**

- `items`: Array of items for current page
- `total`: Total number of items across all pages
- `page`: Current page number
- `page_size`: Number of items per page

There are **no** `total_pages`, `has_next`, or `has_prev` fields, and no cursor-based pagination. Compute page boundaries client-side from `total` and `page_size`:

```python
total_pages = math.ceil(total / page_size)  # last page, for iteration
has_next = page < total_pages
has_prev = page > 1
```

## Pagination Strategies

### Page-Based Pagination

**Navigate by page number:**

```python
# Get first page
response = api.get("/api/v1/agents", params={"page": 1, "page_size": 20})

# Get next page
response = api.get("/api/v1/agents", params={"page": 2, "page_size": 20})
```

### Iterate All Pages

**Python Example:**

```python
import math

def get_all_items(endpoint, params=None):
    """Fetch all items from paginated endpoint."""
    params = params or {}
    params['page'] = 1
    params['page_size'] = 100

    all_items = []

    while True:
        response = api.get(endpoint, params=params)
        data = response['data']

        all_items.extend(data['items'])

        total_pages = math.ceil(data['total'] / data['page_size'])
        if params['page'] >= total_pages:
            break

        params['page'] += 1

    return all_items

# Usage
all_agents = get_all_items("/api/v1/agents")
print(f"Total agents: {len(all_agents)}")
```

**JavaScript Example:**

```javascript
async function getAllItems(endpoint, params = {}) {
  params.page = 1;
  params.page_size = 100;

  const allItems = [];

  while (true) {
    const response = await api.get(endpoint, { params });
    const data = response.data;

    allItems.push(...data.items);

    const totalPages = Math.ceil(data.total / data.page_size);
    if (params.page >= totalPages) {
      break;
    }

    params.page++;
  }

  return allItems;
}

// Usage
const allAgents = await getAllItems('/api/v1/agents');
console.log(`Total agents: ${allAgents.length}`);
```

## Best Practices

### Performance

**✅ Do:**
- Use a large page size (up to the endpoint's cap) for bulk operations
- Cache results when appropriate
- Implement pagination in UI
- Show loading indicators
- Handle empty results gracefully

**❌ Don't:**
- Fetch all pages unnecessarily
- Use very small page sizes
- Ignore pagination metadata
- Block UI during pagination
- Forget error handling

### Error Handling

**Handle Pagination Errors:**

```python
def safe_paginate(endpoint, params=None):
    """Safely paginate with error handling."""
    params = params or {}
    params['page'] = 1
    params['page_size'] = 100

    all_items = []
    max_retries = 3

    while True:
        for attempt in range(max_retries):
            try:
                response = api.get(endpoint, params=params)
                data = response['data']
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                time.sleep(2 ** attempt)  # Exponential backoff

        all_items.extend(data['items'])

        total_pages = math.ceil(data['total'] / data['page_size'])
        if params['page'] >= total_pages:
            break

        params['page'] += 1

    return all_items
```

## UI Implementation

### React Example

```jsx
import { useState, useEffect } from 'react';

function PaginatedList() {
  const [items, setItems] = useState([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchItems();
  }, [page]);

  const fetchItems = async () => {
    setLoading(true);
    try {
      const response = await api.get('/api/v1/agents', {
        params: { page, page_size: 20 }
      });

      setItems(response.data.items);
      setTotalPages(
        Math.ceil(response.data.total / response.data.page_size)
      );
    } catch (error) {
      console.error('Failed to fetch items:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      {loading ? (
        <div>Loading...</div>
      ) : (
        <>
          <ul>
            {items.map(item => (
              <li key={item.id}>{item.name}</li>
            ))}
          </ul>

          <div className="pagination">
            <button
              onClick={() => setPage(p => p - 1)}
              disabled={page === 1}
            >
              Previous
            </button>

            <span>Page {page} of {totalPages}</span>

            <button
              onClick={() => setPage(p => p + 1)}
              disabled={page === totalPages}
            >
              Next
            </button>
          </div>
        </>
      )}
    </div>
  );
}
```

### Infinite Scroll

```jsx
import { useState, useEffect, useRef } from 'react';

function InfiniteScrollList() {
  const [items, setItems] = useState([]);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const [loading, setLoading] = useState(false);
  const observerRef = useRef();

  useEffect(() => {
    fetchItems();
  }, [page]);

  useEffect(() => {
    const observer = new IntersectionObserver(
      entries => {
        if (entries[0].isIntersecting && hasMore && !loading) {
          setPage(p => p + 1);
        }
      },
      { threshold: 1.0 }
    );

    if (observerRef.current) {
      observer.observe(observerRef.current);
    }

    return () => observer.disconnect();
  }, [hasMore, loading]);

  const fetchItems = async () => {
    setLoading(true);
    try {
      const response = await api.get('/api/v1/agents', {
        params: { page, page_size: 20 }
      });

      setItems(prev => [...prev, ...response.data.items]);
      const totalPages = Math.ceil(
        response.data.total / response.data.page_size
      );
      setHasMore(page < totalPages);
    } catch (error) {
      console.error('Failed to fetch items:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <ul>
        {items.map(item => (
          <li key={item.id}>{item.name}</li>
        ))}
      </ul>

      {hasMore && (
        <div ref={observerRef}>
          {loading ? 'Loading...' : 'Load more'}
        </div>
      )}
    </div>
  );
}
```

## Pagination Metadata

### Calculate Pagination Info

```python
import math

def calculate_pagination(total, page, page_size):
    """Calculate pagination metadata client-side."""
    total_pages = math.ceil(total / page_size) if total > 0 else 0
    has_next = page < total_pages
    has_prev = page > 1
    start_index = (page - 1) * page_size
    end_index = min(start_index + page_size, total)

    return {
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages,
        'has_next': has_next,
        'has_prev': has_prev,
        'start_index': start_index,
        'end_index': end_index,
        'showing': f'{start_index + 1}-{end_index} of {total}'
    }

# Usage
info = calculate_pagination(total=156, page=2, page_size=50)
print(info['showing'])  # "51-100 of 156"
```

## Common Patterns

### Search with Pagination

```python
def search_paginated(query, page=1, page_size=20):
    """Search with pagination."""
    response = api.get('/api/v1/agents', params={
        'keyword': query,
        'page': page,
        'page_size': page_size
    })
    return response['data']

# Usage
results = search_paginated('customer support', page=1)
print(f"Found {results['total']} results")
```

### Filter with Pagination

```python
def filter_paginated(filters, page=1, page_size=20):
    """Filter with pagination."""
    params = {
        'page': page,
        'page_size': page_size,
        **filters
    }

    response = api.get('/api/v1/agents', params=params)
    return response['data']

# Usage
results = filter_paginated({
    'status': 'active',
    'team_id': 'team-123'
}, page=1)
```

## Troubleshooting

### Empty Results

**Problem:** No items returned

**Solutions:**
1. Check if page number is valid
2. Verify filters are correct
3. Check total count
4. Try page 1

### Inconsistent Results

**Problem:** Items appear/disappear between pages (items created/deleted during iteration)

**Solutions:**
1. Ordering is fixed per endpoint (typically newest first)
2. Cache results if needed
3. Re-run the query to confirm the final state

### Performance Issues

**Problem:** Slow pagination

**Solutions:**
1. Increase page size
2. Add database indexes
3. Implement caching

## Related Documentation

- [Filtering Guide](./filtering.md) - Filtering results
- [Response Format](./response-format.md) - Response structure
- [Error Handling](./error-handling.md) - Error handling

---

**Last Updated**: 2026-08-14
