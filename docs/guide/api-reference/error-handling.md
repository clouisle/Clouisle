# Error Handling Guide

This guide explains how to handle errors when using the Clouisle API.

## Overview

The Clouisle API uses a unified error response format with specific error codes to help you identify and handle different error scenarios.

## Error Response Format

### Standard Error Response

```json
{
  "code": 1001,
  "data": {
    "field": "email",
    "error": "Email is required"
  },
  "msg": "Validation failed"
}
```

**Response Fields:**

- `code`: Error code (non-zero indicates error)
- `data`: Additional error details (optional)
- `msg`: Human-readable error message

### HTTP Status Codes

| Status Code | Meaning | When Used |
|-------------|---------|-----------|
| 200 | OK | Successful request |
| 201 | Created | Resource created successfully |
| 400 | Bad Request | Invalid request data |
| 401 | Unauthorized | Authentication failed |
| 403 | Forbidden | Permission denied |
| 404 | Not Found | Resource not found |
| 409 | Conflict | Resource conflict |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Server error |
| 503 | Service Unavailable | Service temporarily unavailable |

## Error Code Ranges

### Code Categories

| Range | Category | Description |
|-------|----------|-------------|
| 0 | Success | Request successful |
| 1000-1999 | General Errors | Validation, bad request, internal error |
| 2000-2999 | Authentication | Unauthorized, invalid token, expired token |
| 3000-3999 | Permission | Permission denied, not team member |
| 4000-4999 | Resource | Not found |
| 5000-5099 | Registration | Disabled, already exists, verification |
| 5100-5199 | Duplicate | Name exists, already member |
| 5200-5299 | Operation Forbidden | Cannot delete, cannot remove |
| 5300-5399 | Login Security | Account locked, too many attempts |
| 5400-5499 | Rate Limiting | Rate limit exceeded |
| 6000-6099 | Knowledge Base | KB errors |
| 6100-6199 | Model | Model errors |
| 6200-6299 | Agent | Agent errors |
| 6300-6399 | Tool | Tool errors |

### Common Error Codes

**General Errors (1000-1999):**
- `1000`: Bad request
- `1001`: Validation failed
- `1002`: Internal server error

**Authentication Errors (2000-2999):**
- `2000`: Unauthorized
- `2001`: Invalid credentials
- `2002`: Token expired
- `2003`: Invalid token

**Permission Errors (3000-3999):**
- `3000`: Permission denied
- `3001`: Not team member

**Resource Errors (4000-4999):**
- `4000`: Resource not found

**Rate Limiting (5400-5499):**
- `5400`: Rate limit exceeded

## Error Handling Patterns

### Python Example

```python
import requests
from typing import Optional, Dict, Any

class ApiError(Exception):
    """API error exception."""

    def __init__(self, code: int, message: str, data: Optional[Dict] = None):
        self.code = code
        self.message = message
        self.data = data or {}
        super().__init__(self.message)

    def __str__(self):
        return f"ApiError({self.code}): {self.message}"

class CloudisleAPI:
    """Clouisle API client with error handling."""

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        })

    def _handle_response(self, response: requests.Response) -> Dict[Any, Any]:
        """Handle API response and errors."""
        try:
            result = response.json()
        except ValueError:
            raise ApiError(1002, "Invalid JSON response")

        # Check for API error
        if result.get('code', 0) != 0:
            raise ApiError(
                code=result['code'],
                message=result.get('msg', 'Unknown error'),
                data=result.get('data')
            )

        return result.get('data')

    def request(self, method: str, endpoint: str, **kwargs) -> Dict[Any, Any]:
        """Make API request with error handling."""
        url = f"{self.base_url}{endpoint}"

        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return self._handle_response(response)

        except requests.exceptions.HTTPError as e:
            # Handle HTTP errors
            if e.response.status_code == 401:
                raise ApiError(2000, "Unauthorized - check your token")
            elif e.response.status_code == 403:
                raise ApiError(3000, "Permission denied")
            elif e.response.status_code == 404:
                raise ApiError(4000, "Resource not found")
            elif e.response.status_code == 429:
                retry_after = e.response.headers.get('Retry-After', 60)
                raise ApiError(5400, f"Rate limit exceeded. Retry after {retry_after}s")
            else:
                raise ApiError(1002, f"HTTP error: {e.response.status_code}")

        except requests.exceptions.ConnectionError:
            raise ApiError(1002, "Connection error - check your network")

        except requests.exceptions.Timeout:
            raise ApiError(1002, "Request timeout")

        except requests.exceptions.RequestException as e:
            raise ApiError(1002, f"Request failed: {str(e)}")

    def get(self, endpoint: str, **kwargs) -> Dict[Any, Any]:
        """GET request."""
        return self.request('GET', endpoint, **kwargs)

    def post(self, endpoint: str, **kwargs) -> Dict[Any, Any]:
        """POST request."""
        return self.request('POST', endpoint, **kwargs)

# Usage
api = CloudisleAPI('https://your-domain.com/api/v1', 'YOUR_TOKEN')

try:
    agents = api.get('/agents')
    print(f"Found {len(agents['items'])} agents")

except ApiError as e:
    if e.code == 2000:
        print("Authentication failed - please login again")
    elif e.code == 3000:
        print("You don't have permission to view agents")
    elif e.code == 5400:
        print(f"Rate limit exceeded: {e.message}")
    else:
        print(f"API error: {e}")
```

### JavaScript Example

```javascript
class ApiError extends Error {
  constructor(code, message, data = {}) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.data = data;
  }
}

class CloudisleAPI {
  constructor(baseUrl, token) {
    this.baseUrl = baseUrl;
    this.token = token;
  }

  async request(method, endpoint, options = {}) {
    const url = `${this.baseUrl}${endpoint}`;
    const config = {
      method,
      headers: {
        'Authorization': `Bearer ${this.token}`,
        'Content-Type': 'application/json',
        ...options.headers,
      },
      ...options,
    };

    try {
      const response = await fetch(url, config);

      // Parse JSON response
      let result;
      try {
        result = await response.json();
      } catch (e) {
        throw new ApiError(1002, 'Invalid JSON response');
      }

      // Check for API error
      if (result.code !== 0) {
        throw new ApiError(
          result.code,
          result.msg || 'Unknown error',
          result.data
        );
      }

      return result.data;

    } catch (error) {
      // Handle ApiError
      if (error instanceof ApiError) {
        throw error;
      }

      // Handle network errors
      if (error.name === 'TypeError' && error.message.includes('fetch')) {
        throw new ApiError(1002, 'Network error - check your connection');
      }

      // Handle timeout
      if (error.name === 'AbortError') {
        throw new ApiError(1002, 'Request timeout');
      }

      // Unknown error
      throw new ApiError(1002, `Request failed: ${error.message}`);
    }
  }

  async get(endpoint, params = {}) {
    const queryString = new URLSearchParams(params).toString();
    const url = queryString ? `${endpoint}?${queryString}` : endpoint;
    return this.request('GET', url);
  }

  async post(endpoint, data = {}) {
    return this.request('POST', endpoint, {
      body: JSON.stringify(data),
    });
  }
}

// Usage
const api = new CloudisleAPI('https://your-domain.com/api/v1', 'YOUR_TOKEN');

try {
  const agents = await api.get('/agents');
  console.log(`Found ${agents.items.length} agents`);

} catch (error) {
  if (error instanceof ApiError) {
    switch (error.code) {
      case 2000:
        console.error('Authentication failed - please login again');
        break;
      case 3000:
        console.error('You don\'t have permission to view agents');
        break;
      case 5400:
        console.error(`Rate limit exceeded: ${error.message}`);
        break;
      default:
        console.error(`API error (${error.code}): ${error.message}`);
    }
  } else {
    console.error('Unexpected error:', error);
  }
}
```

## Retry Logic

### Exponential Backoff

```python
import time
from typing import Callable, Any

def retry_with_backoff(
    func: Callable,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0
) -> Any:
    """Retry function with exponential backoff."""
    delay = initial_delay

    for attempt in range(max_retries):
        try:
            return func()

        except ApiError as e:
            # Don't retry client errors (4xx)
            if 4000 <= e.code < 5000:
                raise

            # Don't retry authentication errors
            if 2000 <= e.code < 3000:
                raise

            # Retry rate limit errors
            if e.code == 5400:
                retry_after = e.data.get('retry_after', delay)
                time.sleep(retry_after)
                continue

            # Last attempt, raise error
            if attempt == max_retries - 1:
                raise

            # Wait before retry
            time.sleep(min(delay, max_delay))
            delay *= exponential_base

# Usage
def fetch_agents():
    return api.get('/agents')

agents = retry_with_backoff(fetch_agents, max_retries=3)
```

### JavaScript Retry

```javascript
async function retryWithBackoff(
  func,
  maxRetries = 3,
  initialDelay = 1000,
  maxDelay = 60000,
  exponentialBase = 2
) {
  let delay = initialDelay;

  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      return await func();

    } catch (error) {
      if (!(error instanceof ApiError)) {
        throw error;
      }

      // Don't retry client errors (4xx)
      if (error.code >= 4000 && error.code < 5000) {
        throw error;
      }

      // Don't retry authentication errors
      if (error.code >= 2000 && error.code < 3000) {
        throw error;
      }

      // Retry rate limit errors
      if (error.code === 5400) {
        const retryAfter = error.data.retry_after || delay;
        await new Promise(resolve => setTimeout(resolve, retryAfter * 1000));
        continue;
      }

      // Last attempt, throw error
      if (attempt === maxRetries - 1) {
        throw error;
      }

      // Wait before retry
      await new Promise(resolve => setTimeout(resolve, Math.min(delay, maxDelay)));
      delay *= exponentialBase;
    }
  }
}

// Usage
const agents = await retryWithBackoff(
  () => api.get('/agents'),
  3
);
```

## Validation Errors

### Field Validation

**Error Response:**

```json
{
  "code": 1001,
  "data": {
    "field": "email",
    "error": "Invalid email format",
    "value": "invalid-email"
  },
  "msg": "Validation failed"
}
```

**Handle Validation Errors:**

```python
try:
    user = api.post('/users', json={
        'email': 'invalid-email',
        'password': '123'
    })
except ApiError as e:
    if e.code == 1001:
        field = e.data.get('field')
        error = e.data.get('error')
        print(f"Validation error on {field}: {error}")
```

### Multiple Field Errors

**Error Response:**

```json
{
  "code": 1001,
  "data": {
    "errors": [
      {
        "field": "email",
        "error": "Invalid email format"
      },
      {
        "field": "password",
        "error": "Password too short"
      }
    ]
  },
  "msg": "Validation failed"
}
```

**Handle Multiple Errors:**

```python
try:
    user = api.post('/users', json=data)
except ApiError as e:
    if e.code == 1001 and 'errors' in e.data:
        for error in e.data['errors']:
            print(f"{error['field']}: {error['error']}")
```

## Rate Limiting

### Handle Rate Limits

**Rate Limit Response:**

```json
{
  "code": 5400,
  "data": {
    "retry_after": 60,
    "limit": "100 requests per minute",
    "reset_at": "2026-02-11T16:01:00Z"
  },
  "msg": "Rate limit exceeded"
}
```

**Handle Rate Limits:**

```python
import time

try:
    result = api.get('/agents')
except ApiError as e:
    if e.code == 5400:
        retry_after = e.data.get('retry_after', 60)
        print(f"Rate limited. Waiting {retry_after} seconds...")
        time.sleep(retry_after)
        result = api.get('/agents')  # Retry
```

## Best Practices

### Error Handling

**✅ Do:**
- Always handle errors
- Use try-catch blocks
- Check error codes
- Implement retry logic
- Log errors
- Show user-friendly messages
- Handle network errors
- Validate input before sending

**❌ Don't:**
- Ignore errors
- Show raw error messages to users
- Retry indefinitely
- Retry client errors (4xx)
- Skip error logging
- Expose sensitive error details

### User Experience

**✅ Do:**
- Show clear error messages
- Provide actionable feedback
- Offer retry options
- Log errors for debugging
- Handle errors gracefully
- Show loading states
- Disable actions during errors

**❌ Don't:**
- Show technical error details
- Leave users confused
- Block UI indefinitely
- Lose user data on error
- Ignore error states

## Error Recovery

### Automatic Recovery

```python
class ResilientAPI:
    """API client with automatic error recovery."""

    def __init__(self, base_url, token):
        self.api = CloudisleAPI(base_url, token)
        self.token = token

    def request_with_recovery(self, method, endpoint, **kwargs):
        """Make request with automatic recovery."""
        try:
            return self.api.request(method, endpoint, **kwargs)

        except ApiError as e:
            # Handle token expiration
            if e.code == 2002:
                print("Token expired, refreshing...")
                self.refresh_token()
                return self.api.request(method, endpoint, **kwargs)

            # Handle rate limiting
            elif e.code == 5400:
                retry_after = e.data.get('retry_after', 60)
                print(f"Rate limited, waiting {retry_after}s...")
                time.sleep(retry_after)
                return self.api.request(method, endpoint, **kwargs)

            # Handle temporary errors
            elif e.code == 1002:
                print("Temporary error, retrying...")
                time.sleep(5)
                return self.api.request(method, endpoint, **kwargs)

            else:
                raise

    def refresh_token(self):
        """Refresh authentication token."""
        # Implement token refresh logic
        pass
```

## Troubleshooting

### Common Issues

**Authentication Failed:**
- Check token is valid
- Verify token not expired
- Ensure correct authorization header

**Permission Denied:**
- Check user has required permissions
- Verify team membership
- Check API key scopes

**Rate Limit Exceeded:**
- Implement exponential backoff
- Reduce request frequency
- Use batch operations
- Cache results

**Resource Not Found:**
- Verify resource ID is correct
- Check resource exists
- Ensure proper permissions

## Related Documentation

- [Authentication](./authentication.md) - Authentication methods
- [Rate Limiting](./rate-limiting.md) - Rate limit details
- [Response Format](./response-format.md) - Response structure
- [Error Codes](./error-codes.md) - Complete error code list

---

**Last Updated**: 2026-02-11
