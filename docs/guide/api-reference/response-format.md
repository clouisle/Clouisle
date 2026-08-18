# Response Format

This document describes the unified response format used by all Clouisle API endpoints.

## Unified Response Structure

All API responses follow a consistent structure:

```json
{
  "code": 0,
  "data": { ... },
  "msg": "success"
}
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `code` | integer | Response code (0 = success, non-zero = error) |
| `data` | any | Response payload (varies by endpoint) |
| `msg` | string | Human-readable message |

## Success Responses

### Code 0 - Success

All successful requests return `code: 0`:

```json
{
  "code": 0,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Example Agent",
    "created_at": "2026-02-11T10:00:00Z"
  },
  "msg": "success"
}
```

### Data Types

The `data` field varies by endpoint:

**Single Object:**
```json
{
  "code": 0,
  "data": {
    "id": "...",
    "name": "..."
  },
  "msg": "success"
}
```

**List of Objects:**
```json
{
  "code": 0,
  "data": {
    "items": [
      {"id": "1", "name": "Item 1"},
      {"id": "2", "name": "Item 2"}
    ],
    "total": 2,
    "page": 1,
    "page_size": 20
  },
  "msg": "success"
}
```

**Null Data:**
```json
{
  "code": 0,
  "data": null,
  "msg": "Operation completed successfully"
}
```

**Boolean Data:**
```json
{
  "code": 0,
  "data": true,
  "msg": "success"
}
```

## Error Responses

### Non-Zero Codes

Errors return non-zero codes:

```json
{
  "code": 2000,
  "data": null,
  "msg": "Not authenticated"
}
```

### Error Code Ranges

| Range | Category | Examples |
|-------|----------|----------|
| **0** | Success | Operation successful |
| **1000-1999** | General Errors | Unknown error, validation, bad request, internal error |
| **2000-2999** | Authentication | Unauthorized, invalid token, expired key |
| **3000-3999** | Permission | Permission denied, not team member |
| **4000-4999** | Resource | Not found |
| **5000-5099** | Registration | Registration disabled, email verification |
| **5100-5199** | Duplicate | Name already exists, already team member |
| **5200-5299** | Operation Forbidden | Cannot delete, cannot remove |
| **5300-5399** | Login Security | Account locked, captcha, password policy |
| **5310-5319** | TOTP 2FA | TOTP errors |
| **5400-5499** | Rate Limiting | Email quota, provider rate limits |
| **6000-6099** | Knowledge Base | KB errors |
| **6100-6199** | Model | Model errors, quota |
| **6200-6299** | Agent | Agent errors |
| **6300-6399** | SSO | SSO errors |

See [Error Codes](./error-codes.md) for complete list.

### Error Data

Some errors include additional data:

**Validation Errors (1001):**
```json
{
  "code": 1001,
  "data": {
    "errors": {
      "email": ["Invalid email format"],
      "password": ["String should have at least 8 characters"]
    }
  },
  "msg": "Validation failed"
}
```

The `data.errors` value is a dictionary mapping each invalid field to a list of error messages.

**Rate Limit / Quota Errors (5400):**
```json
{
  "code": 5400,
  "data": {
    "limit": 100,
    "period": "hour"
  },
  "msg": "Email sending rate limit exceeded. Please try again later."
}
```

The `5400` code is raised for email-sending quotas (100/hour) and mapped provider rate limits; the `data` shape varies by caller.

**Resource Not Found (4000):**
```json
{
  "code": 4000,
  "data": null,
  "msg": "Not found"
}
```

Not-found errors do not carry a unified `{resource_type, resource_id}` payload; the message is derived from the error's message key.

## Pagination

List endpoints support pagination:

### Request Parameters

```
GET /api/v1/agents?page=1&page_size=20
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | integer | 1 | Page number (1-indexed) |
| `page_size` | integer | 20 | Items per page (some endpoints cap this at 100) |

### Response Format

```json
{
  "code": 0,
  "data": {
    "items": [
      {"id": "1", "name": "Agent 1"},
      {"id": "2", "name": "Agent 2"}
    ],
    "total": 100,
    "page": 1,
    "page_size": 20
  },
  "msg": "success"
}
```

### Pagination Fields

| Field | Type | Description |
|-------|------|-------------|
| `items` | array | List of items for current page |
| `total` | integer | Total number of items |
| `page` | integer | Current page number |
| `page_size` | integer | Items per page |

There are no `total_pages`, `has_next`, or `has_prev` fields — compute them client-side when needed.

### Pagination Examples

**First page:**
```
GET /api/v1/agents?page=1&page_size=20
```

**Second page:**
```
GET /api/v1/agents?page=2&page_size=20
```

**Calculate total pages client-side:**
```
total_pages = ceil(total / page_size)
```

## HTTP Status Codes

Clouisle uses standard HTTP status codes:

| Status | Meaning | When Used |
|--------|---------|-----------|
| **200** | OK | Successful API request |
| **400** | Bad Request | `BusinessError` default for invalid requests |
| **401** | Unauthorized | Authentication required or failed |
| **403** | Forbidden | Insufficient permissions / invalid JWT |
| **404** | Not Found | Resource not found |
| **422** | Unprocessable Entity | Pydantic validation error (`1001`) |
| **429** | Too Many Requests | Only endpoint-specific quota or lockout responses |
| **500** | Internal Server Error | Server error |

Note: validation errors return **422** (not 400). The response `code` field is the authoritative error identifier — branch on it, not on the HTTP status.

### Status Code vs Response Code

**HTTP Status Code**: Transport-level status
**Response Code**: Application-level status

Example:
```
HTTP/1.1 401 Unauthorized

{
  "code": 2000,
  "data": null,
  "msg": "Not authenticated"
}
```

## Response Headers

### Standard Headers

Responses use the standard HTTP headers (`Content-Type: application/json` for JSON endpoints, `text/event-stream` for SSE streams). Clouisle does **not** add custom response headers such as `X-Request-ID`, `X-Response-Time`, `X-RateLimit-*`, or pagination headers (`X-Total-Count`, `X-Page`, `X-Page-Size`).

Pagination metadata is returned exclusively in the response body (`data.total`, `data.page`, `data.page_size`).

## Timestamps

All timestamps use ISO 8601 format (UTC):

```json
{
  "created_at": "2026-02-11T10:00:00Z",
  "updated_at": "2026-02-11T15:30:00Z"
}
```

**Format**: `YYYY-MM-DDTHH:mm:ssZ`

**Parsing examples:**

**JavaScript:**
```javascript
const date = new Date("2026-02-11T10:00:00Z");
```

**Python:**
```python
from datetime import datetime
date = datetime.fromisoformat("2026-02-11T10:00:00Z")
```

## UUIDs

Resource IDs use UUID v4 format:

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Format**: `xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx`

## Null Values

Null values are represented as `null` (not empty string):

```json
{
  "code": 0,
  "data": {
    "name": "Agent",
    "description": null,
    "avatar_url": null
  },
  "msg": "success"
}
```

## Empty Arrays

Empty lists are represented as empty arrays:

```json
{
  "code": 0,
  "data": {
    "items": [],
    "total": 0,
    "page": 1,
    "page_size": 20
  },
  "msg": "success"
}
```

## Boolean Values

Booleans are `true` or `false` (not 1/0 or "true"/"false"):

```json
{
  "code": 0,
  "data": {
    "is_active": true,
    "is_published": false
  },
  "msg": "success"
}
```

## Handling Responses

### Success Check

**Check response code:**
```python
response = requests.get(url, headers=headers)
data = response.json()

if data['code'] == 0:
    # Success
    result = data['data']
else:
    # Error
    error_msg = data['msg']
```

### Error Handling

**Handle specific errors:**
```python
data = response.json()

if data['code'] == 2000:
    # Unauthorized - login again
    pass
elif data['code'] == 4000:
    # Not found - handle missing resource
    pass
elif data['code'] == 6103:
    # Model quota exceeded - wait and retry
    time.sleep(30)
```

### Validation Errors

**Extract field errors (dictionary):**
```python
if data['code'] == 1001:
    errors = data['data']['errors']  # {"field": ["msg", ...]}
    for field, messages in errors.items():
        for message in messages:
            print(f"{field}: {message}")
```

### Pagination Handling

**Iterate through pages (compute `total_pages` client-side):**
```python
import math

page = 1
all_items = []

while True:
    response = requests.get(
        f"{url}?page={page}&page_size=100",
        headers=headers
    )
    data = response.json()

    if data['code'] != 0:
        break

    items = data['data']['items']
    all_items.extend(items)

    total_pages = math.ceil(data['data']['total'] / data['data']['page_size'])
    if page >= total_pages:
        break

    page += 1
```

## Code Examples

### Python

```python
import requests

def make_request(url, headers):
    """Make API request and handle response."""
    response = requests.get(url, headers=headers)
    data = response.json()

    if data['code'] == 0:
        return data['data']
    else:
        raise Exception(f"API Error {data['code']}: {data['msg']}")

# Usage
try:
    result = make_request(
        "https://your-domain.com/api/v1/agents",
        {"Authorization": "Bearer YOUR_TOKEN"}
    )
    print(f"Found {len(result['items'])} agents")
except Exception as e:
    print(f"Error: {e}")
```

### JavaScript

```javascript
async function makeRequest(url, headers) {
  const response = await fetch(url, { headers });
  const data = await response.json();

  if (data.code === 0) {
    return data.data;
  } else {
    throw new Error(`API Error ${data.code}: ${data.msg}`);
  }
}

// Usage
try {
  const result = await makeRequest(
    'https://your-domain.com/api/v1/agents',
    { 'Authorization': 'Bearer YOUR_TOKEN' }
  );
  console.log(`Found ${result.items.length} agents`);
} catch (error) {
  console.error('Error:', error.message);
}
```

### TypeScript

```typescript
interface ApiResponse<T> {
  code: number;
  data: T | null;
  msg: string;
}

interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

async function makeRequest<T>(
  url: string,
  headers: Record<string, string>
): Promise<T> {
  const response = await fetch(url, { headers });
  const data: ApiResponse<T> = await response.json();

  if (data.code === 0 && data.data !== null) {
    return data.data;
  } else {
    throw new Error(`API Error ${data.code}: ${data.msg}`);
  }
}

// Usage
interface Agent {
  id: string;
  name: string;
}

const result = await makeRequest<PaginatedResponse<Agent>>(
  'https://your-domain.com/api/v1/agents',
  { 'Authorization': 'Bearer YOUR_TOKEN' }
);
```

## Best Practices

### Always Check Response Code

**✅ Do:**
```python
data = response.json()
if data['code'] == 0:
    # Process data
    pass
else:
    # Handle error
    pass
```

**❌ Don't:**
```python
data = response.json()
result = data['data']  # May fail if error
```

### Handle Null Values

**✅ Do:**
```python
description = data['data'].get('description') or "No description"
```

**❌ Don't:**
```python
description = data['data']['description']  # May be null
```

### Validate Data Types

**✅ Do:**
```python
if isinstance(data['data'], dict):
    # Process object
    pass
elif isinstance(data['data'], list):
    # Process list
    pass
```

### Use Type Hints

**✅ Do:**
```python
from typing import Optional, Dict, Any

def process_response(data: Dict[str, Any]) -> Optional[Dict]:
    if data['code'] == 0:
        return data['data']
    return None
```

## Related Documentation

- [API Overview](./overview.md) - API introduction
- [Authentication](./authentication.md) - Authentication methods
- [Error Codes](./error-codes.md) - Complete error reference
- [Rate Limiting](./rate-limiting.md) - Rate limit details

---

**Last Updated**: 2026-02-11
