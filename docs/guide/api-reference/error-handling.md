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
    "errors": {
      "email": ["Email is required"]
    }
  },
  "msg": "Validation failed"
}
```

**Response Fields:**

- `code`: Error code (non-zero indicates error)
- `data`: Additional error details (optional); for validation errors it is a dictionary mapping field names to arrays of messages
- `msg`: Human-readable error message

### HTTP Status Codes

| Status Code | Meaning | When Used |
|-------------|---------|-----------|
| 200 | OK | Successful request |
| 201 | Created | Resource created successfully |
| 400 | Bad Request | `BusinessError` default for invalid requests |
| 401 | Unauthorized | Authentication failed |
| 403 | Forbidden | Permission denied / invalid JWT |
| 404 | Not Found | Resource not found |
| 422 | Unprocessable Entity | Pydantic validation error (code `1001`) |
| 429 | Too Many Requests | Quota exceeded (model quota, TOTP lockout) |
| 500 | Internal Server Error | Server error |

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
| 6300-6399 | SSO | SSO errors |

### Common Error Codes

**General Errors (1000-1999):**
- `1000`: Unknown error
- `1001`: Validation failed (HTTP 422)
- `1002`: Bad request
- `1003`: Internal server error

**Authentication Errors (2000-2999):**
- `2000`: Unauthorized
- `2001`: Invalid token
- `2002`: Token expired (API key)
- `2003`: Invalid credentials (wrong password or invalid/expired JWT)

**Permission Errors (3000-3999):**
- `3000`: Permission denied
- `3001`: Insufficient privileges
- `3002`: Not team member

**Resource Errors (4000-4999):**
- `4000`: Resource not found
- `4001`: User not found

**Rate Limiting (5400-5499):**
- `5400`: Rate limited (email quota / provider rate limit)

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
            raise ApiError(1003, "Invalid JSON response")

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
            # Handle HTTP errors (code 1002 = bad request; 1003 = internal error)
            if e.response.status_code == 400:
                result = e.response.json()
                raise ApiError(result.get('code', 1002), result.get('msg', 'Bad request'))
            elif e.response.status_code == 401:
                raise ApiError(2000, "Unauthorized - check your token")
            elif e.response.status_code == 403:
                raise ApiError(3000, "Permission denied")
            elif e.response.status_code == 404:
                raise ApiError(4000, "Resource not found")
            elif e.response.status_code == 422:
                result = e.response.json()
                raise ApiError(1001, result.get('msg', 'Validation failed'), result.get('data'))
            elif e.response.status_code == 429:
                # Quota exceeded (e.g. model quota 6103, TOTP lockout 5312)
                result = e.response.json()
                raise ApiError(result.get('code', 0), result.get('msg', 'Quota exceeded'))
            else:
                raise ApiError(1003, f"HTTP error: {e.response.status_code}")

        except requests.exceptions.ConnectionError:
            raise ApiError(1003, "Connection error - check your network")

        except requests.exceptions.Timeout:
            raise ApiError(1003, "Request timeout")

        except requests.exceptions.RequestException as e:
            raise ApiError(1003, f"Request failed: {str(e)}")

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
        throw new ApiError(1003, 'Invalid JSON response');
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
        throw new ApiError(1003, 'Network error - check your connection');
      }

      // Handle timeout
      if (error.name === 'AbortError') {
        throw new ApiError(1003, 'Request timeout');
      }

      // Unknown error
      throw new ApiError(1003, `Request failed: ${error.message}`);
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

            # Retry quota errors with a fixed delay
            if e.code == 6103:
                time.sleep(30)
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

      // Retry quota errors with a fixed delay
      if (error.code === 6103) {
        await new Promise(resolve => setTimeout(resolve, 30000));
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

**Error Response (HTTP 422):**

```json
{
  "code": 1001,
  "data": {
    "errors": {
      "email": ["Invalid email format"]
    }
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
        for field, messages in e.data.get('errors', {}).items():
            for message in messages:
                print(f"Validation error on {field}: {message}")
```

### Multiple Field Errors

**Error Response:**

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

**Handle Multiple Errors:**

```python
try:
    user = api.post('/users', json=data)
except ApiError as e:
    if e.code == 1001 and 'errors' in e.data:
        for field, messages in e.data['errors'].items():
            for message in messages:
                print(f"{field}: {message}")
```

## Rate Limiting

### Handle Quota / Rate Limit Errors

Clouisle does not implement per-request throttling with `retry_after` payloads. Code `5400` is raised for email-sending quotas and mapped model-provider rate limits; model quota exhaustion uses `6103`.

**Rate Limit Response (email quota):**

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

**Handle Rate Limits:**

```python
import time

try:
    result = api.get('/agents')
except ApiError as e:
    if e.code == 6103:
        # Model quota exceeded - wait and retry later
        print("Model quota exceeded. Waiting 30 seconds...")
        time.sleep(30)
        result = api.get('/agents')  # Retry
    elif e.code == 5400:
        # Email/quota limit - wait for the window to reset
        print("Rate limited. Retry after the quota window resets.")
```

> **Note:** If you receive an HTTP 429, the `Retry-After` header is not guaranteed to be present — the response `data` carries the relevant limit information instead.

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
            # Handle JWT expiration (2003) - login again
            if e.code == 2003:
                print("JWT invalid/expired, logging in again...")
                self.login_again()
                return self.api.request(method, endpoint, **kwargs)

            # Handle API key expiry (2002)
            elif e.code == 2002:
                print("API key expired, create a new key...")
                raise

            # Handle quota limits
            elif e.code == 6103:
                print("Model quota exceeded, waiting 30s...")
                time.sleep(30)
                return self.api.request(method, endpoint, **kwargs)

            else:
                raise

    def login_again(self):
        """Re-authenticate to get a fresh JWT."""
        # Implement login logic
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
