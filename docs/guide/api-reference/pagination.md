# Pagination Guide

This guide explains how to work with paginated API responses in Clouisle.

## Overview

Pagination allows you to retrieve large datasets in manageable chunks. All list endpoints in Clouisle support pagination.

## Pagination Parameters

### Query Parameters

**Standard Parameters:**

| Parameter | Type | Default | Max | Description |
|-----------|------|---------|-----|-------------|
| `page` | integer | 1 | - | Page number (1-indexed) |
| `page_size` | integer | 20 | 100 | Items per page |

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
    "page_size": 50,
    "total_pages": 4,
    "has_next": true,
    "has_prev": true
  },
  "msg": "success"
}
```

**Response Fields:**

- `items`: Array of items for current page
- `total`: Total number of items across all pages
- `page`: Current page number
- `page_size`: Number of items per page
- `total_pages`: Total number of pages
- `has_next`: Whether there is a next page
- `has_prev`: Whether there is a previous page

## Pagination Strategies

### Page-Based Pagination

**Navigate by page number:**

```python
# Get first page
response = api.get("/api/v1/agents", params={"page": 1, "page_size": 20})

# Get next page
response = api.get("/api/v1/agents", params={"page": 2, "page_size": 20})

# Get last page
total_pages = response['data']['total_pages']
response = api.get("/api/v1/agents", params={"page": total_pages, "page_size": 20})
```

### Iterate All Pages

**Python Example:**

```python
def get_all_items(endpoint, params=None):
    """Fetch all items from paginated endpoint."""
    params = params or {}
    params['page'] = 1
    params['page_size'] = 100  # Max page size

    all_items = []

    while True:
        response = api.get(endpoint, params=params)
        data = response['data']

        all_items.extend(data['items'])

        if not data['has_next']:
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

    if (!data.has_next) {
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

### Cursor-Based Pagination

Some endpoints support cursor-based pagination for better performance with large datasets.

**Request:**

```bash
curl -X GET "https://your-domain.com/api/v1/conversations?cursor=eyJpZCI6MTIzfQ&limit=50" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Response:**

```json
{
  "code": 0,
  "data": {
    "items": [...],
    "next_cursor": "eyJpZCI6MTczfQ",
    "has_more": true
  },
  "msg": "success"
}
```

**Iterate with Cursor:**

```python
def get_all_items_cursor(endpoint, params=None):
    """Fetch all items using cursor pagination."""
    params = params or {}
    params['limit'] = 100

    all_items = []
    cursor = None

    while True:
        if cursor:
            params['cursor'] = cursor

        response = api.get(endpoint, params=params)
        data = response['data']

        all_items.extend(data['items'])

        if not data.get('has_more'):
            break

        cursor = data.get('next_cursor')

    return all_items
```

## Best Practices

### Performance

**✅ Do:**
- Use maximum page size (100) for bulk operations
- Use cursor pagination for large datasets
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

        if not data['has_next']:
            break

        params['page'] += 1

    return all_items
```

### Rate Limiting

**Respect Rate Limits:**

```python
import time

def paginate_with_rate_limit(endpoint, params=None, delay=0.1):
    """Paginate with rate limiting."""
    params = params or {}
    params['page'] = 1
    params['page_size'] = 100

    all_items = []

    while True:
        response = api.get(endpoint, params=params)
        data = response['data']

        all_items.extend(data['items'])

        if not data['has_next']:
            break

        params['page'] += 1
        time.sleep(delay)  # Rate limit delay

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
      setTotalPages(response.data.total_pages);
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
      setHasMore(response.data.has_next);
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
def calculate_pagination(total, page, page_size):
    """Calculate pagination metadata."""
    total_pages = (total + page_size - 1) // page_size
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
        'search': query,
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

### Sort with Pagination

```python
def sort_paginated(sort_by, order='asc', page=1, page_size=20):
    """Sort with pagination."""
    response = api.get('/api/v1/agents', params={
        'sort_by': sort_by,
        'order': order,
        'page': page,
        'page_size': page_size
    })
    return response['data']

# Usage
results = sort_paginated('created_at', order='desc', page=1)
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

**Problem:** Items appear/disappear between pages

**Solutions:**
1. Use cursor pagination for consistency
2. Sort by stable field (e.g., ID)
3. Cache results if needed
4. Use transactions for critical operations

### Performance Issues

**Problem:** Slow pagination

**Solutions:**
1. Increase page size
2. Use cursor pagination
3. Add database indexes
4. Implement caching
5. Use CDN for static data

## Related Documentation

- [Filtering Guide](./filtering.md) - Filtering results
- [Sorting Guide](./sorting.md) - Sorting results
- [Rate Limiting](./rate-limiting.md) - Rate limits
- [Error Handling](./error-handling.md) - Error handling

---

**Last Updated**: 2026-02-11
