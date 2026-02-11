# API Best Practices

This guide provides best practices for using the Clouisle API effectively and securely.

## Authentication

### Token Management

**✅ Do:**
- Store tokens securely (environment variables, secure storage)
- Refresh tokens before expiration
- Use API keys for server-to-server communication
- Implement token rotation
- Use different tokens for different environments
- Revoke compromised tokens immediately
- Monitor token usage

**❌ Don't:**
- Hardcode tokens in source code
- Share tokens between users
- Use expired tokens
- Store tokens in version control
- Use production tokens in development
- Ignore token expiration
- Skip token monitoring

**Example (Python):**
```python
import os
from datetime import datetime, timedelta

class TokenManager:
    """Manage API tokens with auto-refresh."""

    def __init__(self):
        self.token = None
        self.expires_at = None
        self.refresh_token = os.getenv('CLOUISLE_REFRESH_TOKEN')

    def get_token(self):
        """Get valid token, refresh if needed."""
        if not self.token or self.is_expired():
            self.refresh()
        return self.token

    def is_expired(self):
        """Check if token is expired or expiring soon."""
        if not self.expires_at:
            return True
        # Refresh 5 minutes before expiration
        return datetime.now() >= self.expires_at - timedelta(minutes=5)

    def refresh(self):
        """Refresh access token."""
        response = requests.post(
            f"{API_BASE_URL}/api/v1/auth/refresh",
            json={'refresh_token': self.refresh_token}
        )
        data = response.json()['data']
        self.token = data['access_token']
        self.expires_at = datetime.fromisoformat(data['expires_at'])

# Usage
token_manager = TokenManager()
headers = {'Authorization': f'Bearer {token_manager.get_token()}'}
```

### API Key Security

**✅ Do:**
- Use scoped API keys (minimum required permissions)
- Rotate API keys regularly
- Use different keys for different services
- Monitor API key usage
- Set expiration dates
- Revoke unused keys
- Log API key activities

**❌ Don't:**
- Use admin keys for everything
- Never rotate keys
- Share keys across services
- Ignore usage patterns
- Create keys without expiration
- Keep unused keys active
- Skip audit logging

## Error Handling

### Robust Error Handling

**✅ Do:**
- Handle all error codes
- Implement retry logic with exponential backoff
- Log errors with context
- Show user-friendly error messages
- Validate input before sending
- Handle network errors
- Implement circuit breakers

**❌ Don't:**
- Ignore error responses
- Retry indefinitely
- Skip error logging
- Show raw error messages to users
- Send invalid data
- Assume network is reliable
- Keep retrying failed services

**Example (Python):**
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

            # Last attempt, raise error
            if attempt == max_retries - 1:
                raise

            # Log retry
            print(f"Attempt {attempt + 1} failed: {e.message}")
            print(f"Retrying in {delay} seconds...")

            # Wait before retry
            time.sleep(min(delay, max_delay))
            delay *= exponential_base

# Usage
def fetch_agents():
    return api.get('/api/v1/agents')

agents = retry_with_backoff(fetch_agents, max_retries=3)
```

**Example (JavaScript):**
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

      // Last attempt, throw error
      if (attempt === maxRetries - 1) {
        throw error;
      }

      // Log retry
      console.log(`Attempt ${attempt + 1} failed: ${error.message}`);
      console.log(`Retrying in ${delay}ms...`);

      // Wait before retry
      await new Promise(resolve => setTimeout(resolve, Math.min(delay, maxDelay)));
      delay *= exponentialBase;
    }
  }
}

// Usage
const agents = await retryWithBackoff(
  () => api.get('/api/v1/agents'),
  3
);
```

## Rate Limiting

### Respect Rate Limits

**✅ Do:**
- Monitor rate limit headers
- Implement rate limiting in client
- Use exponential backoff on 429 errors
- Batch requests when possible
- Cache responses
- Use webhooks instead of polling
- Spread requests over time

**❌ Don't:**
- Ignore rate limit headers
- Retry immediately on 429
- Send unnecessary requests
- Skip caching
- Poll for updates
- Send burst requests
- Ignore Retry-After header

**Example (Python):**
```python
import time
from datetime import datetime

class RateLimitedClient:
    """API client with rate limiting."""

    def __init__(self, api_client):
        self.api = api_client
        self.rate_limit = None
        self.rate_remaining = None
        self.rate_reset = None

    def request(self, method, endpoint, **kwargs):
        """Make request with rate limit handling."""
        # Wait if rate limit exceeded
        if self.rate_remaining == 0 and self.rate_reset:
            wait_time = self.rate_reset - time.time()
            if wait_time > 0:
                print(f"Rate limit exceeded. Waiting {wait_time:.1f}s...")
                time.sleep(wait_time)

        try:
            response = self.api.request(method, endpoint, **kwargs)

            # Update rate limit info from headers
            self.rate_limit = response.headers.get('X-RateLimit-Limit')
            self.rate_remaining = int(response.headers.get('X-RateLimit-Remaining', 0))
            self.rate_reset = float(response.headers.get('X-RateLimit-Reset', 0))

            return response

        except ApiError as e:
            if e.code == 5400:  # Rate limit exceeded
                retry_after = e.data.get('retry_after', 60)
                print(f"Rate limited. Waiting {retry_after}s...")
                time.sleep(retry_after)
                return self.request(method, endpoint, **kwargs)
            raise

# Usage
client = RateLimitedClient(api)
response = client.request('GET', '/api/v1/agents')
```

## Performance

### Optimize API Usage

**✅ Do:**
- Use pagination for large datasets
- Request only needed fields
- Use batch operations
- Implement caching
- Use compression
- Minimize request size
- Use CDN for static assets

**❌ Don't:**
- Fetch all data at once
- Request unnecessary fields
- Make individual requests
- Skip caching
- Send uncompressed data
- Send large payloads
- Fetch static assets repeatedly

**Example (Caching):**
```python
from functools import lru_cache
from datetime import datetime, timedelta

class CachedAPIClient:
    """API client with caching."""

    def __init__(self, api_client, cache_ttl=300):
        self.api = api_client
        self.cache = {}
        self.cache_ttl = cache_ttl

    def get(self, endpoint, params=None):
        """Get with caching."""
        cache_key = self._make_cache_key(endpoint, params)

        # Check cache
        if cache_key in self.cache:
            cached_data, cached_at = self.cache[cache_key]
            if datetime.now() - cached_at < timedelta(seconds=self.cache_ttl):
                return cached_data

        # Fetch from API
        data = self.api.get(endpoint, params=params)

        # Cache result
        self.cache[cache_key] = (data, datetime.now())

        return data

    def _make_cache_key(self, endpoint, params):
        """Generate cache key."""
        import json
        params_str = json.dumps(params or {}, sort_keys=True)
        return f"{endpoint}:{params_str}"

    def invalidate(self, endpoint=None):
        """Invalidate cache."""
        if endpoint:
            # Invalidate specific endpoint
            self.cache = {
                k: v for k, v in self.cache.items()
                if not k.startswith(endpoint)
            }
        else:
            # Invalidate all
            self.cache.clear()

# Usage
cached_api = CachedAPIClient(api, cache_ttl=300)
agents = cached_api.get('/api/v1/agents')  # Fetches from API
agents = cached_api.get('/api/v1/agents')  # Returns from cache
```

### Efficient Pagination

**✅ Do:**
- Use maximum page size (100)
- Use cursor pagination for large datasets
- Fetch pages in parallel when order doesn't matter
- Stop when you have enough data
- Cache paginated results

**❌ Don't:**
- Use small page sizes
- Fetch all pages unnecessarily
- Fetch pages sequentially always
- Continue fetching after finding what you need
- Re-fetch same pages

**Example:**
```python
async def fetch_pages_parallel(endpoint, total_pages, page_size=100):
    """Fetch multiple pages in parallel."""
    import asyncio
    import aiohttp

    async def fetch_page(session, page):
        async with session.get(
            f"{API_BASE_URL}{endpoint}",
            params={'page': page, 'page_size': page_size},
            headers={'Authorization': f'Bearer {TOKEN}'}
        ) as response:
            return await response.json()

    async with aiohttp.ClientSession() as session:
        tasks = [
            fetch_page(session, page)
            for page in range(1, total_pages + 1)
        ]
        results = await asyncio.gather(*tasks)

    # Combine results
    all_items = []
    for result in results:
        all_items.extend(result['data']['items'])

    return all_items

# Usage
items = asyncio.run(fetch_pages_parallel('/api/v1/agents', total_pages=5))
```

## Data Validation

### Validate Before Sending

**✅ Do:**
- Validate all input data
- Use schema validation
- Check data types
- Validate required fields
- Sanitize user input
- Check data ranges
- Validate formats (email, URL, etc.)

**❌ Don't:**
- Send unvalidated data
- Skip type checking
- Assume data is valid
- Trust user input
- Ignore validation errors
- Send out-of-range values
- Skip format validation

**Example (Python with Pydantic):**
```python
from pydantic import BaseModel, EmailStr, validator
from typing import Optional

class CreateAgentRequest(BaseModel):
    """Validate agent creation request."""
    name: str
    model: str
    system_prompt: str
    temperature: float = 0.7
    max_tokens: int = 2000
    team_id: str

    @validator('name')
    def validate_name(cls, v):
        if len(v) < 3:
            raise ValueError('Name must be at least 3 characters')
        if len(v) > 100:
            raise ValueError('Name must be at most 100 characters')
        return v

    @validator('temperature')
    def validate_temperature(cls, v):
        if not 0 <= v <= 1:
            raise ValueError('Temperature must be between 0 and 1')
        return v

    @validator('max_tokens')
    def validate_max_tokens(cls, v):
        if not 1 <= v <= 128000:
            raise ValueError('Max tokens must be between 1 and 128000')
        return v

# Usage
try:
    request = CreateAgentRequest(
        name='Customer Support',
        model='gpt-4-turbo',
        system_prompt='You are helpful.',
        temperature=0.7,
        max_tokens=2000,
        team_id='team-123'
    )
    agent = api.post('/api/v1/agents', json=request.dict())
except ValueError as e:
    print(f"Validation error: {e}")
```

## Security

### Secure API Usage

**✅ Do:**
- Use HTTPS for all requests
- Validate SSL certificates
- Sanitize all input
- Use parameterized queries
- Implement CSRF protection
- Log security events
- Monitor for suspicious activity

**❌ Don't:**
- Use HTTP in production
- Skip certificate validation
- Trust user input
- Concatenate SQL queries
- Skip CSRF tokens
- Ignore security logs
- Miss suspicious patterns

**Example (Input Sanitization):**
```python
import re
from html import escape

def sanitize_input(text: str) -> str:
    """Sanitize user input."""
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)

    # Escape special characters
    text = escape(text)

    # Remove control characters
    text = ''.join(char for char in text if ord(char) >= 32 or char == '\n')

    # Trim whitespace
    text = text.strip()

    return text

# Usage
user_input = "<script>alert('xss')</script>Hello"
safe_input = sanitize_input(user_input)  # "Hello"
```

## Monitoring

### Monitor API Usage

**✅ Do:**
- Log all API requests
- Monitor response times
- Track error rates
- Set up alerts
- Monitor rate limits
- Track API costs
- Review logs regularly

**❌ Don't:**
- Skip logging
- Ignore slow requests
- Miss error patterns
- React after problems
- Ignore rate limit warnings
- Forget cost tracking
- Never review logs

**Example (Logging):**
```python
import logging
import time
from functools import wraps

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('api_client')

def log_api_call(func):
    """Decorator to log API calls."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        method = args[0] if args else 'UNKNOWN'
        endpoint = args[1] if len(args) > 1 else 'UNKNOWN'

        try:
            result = func(*args, **kwargs)
            duration = time.time() - start_time

            logger.info(
                f"{method} {endpoint} - Success - {duration:.3f}s"
            )

            return result

        except ApiError as e:
            duration = time.time() - start_time

            logger.error(
                f"{method} {endpoint} - Error {e.code}: {e.message} - {duration:.3f}s"
            )

            raise

    return wrapper

class MonitoredAPIClient:
    """API client with monitoring."""

    @log_api_call
    def request(self, method, endpoint, **kwargs):
        return api.request(method, endpoint, **kwargs)

# Usage
monitored_api = MonitoredAPIClient()
agents = monitored_api.request('GET', '/api/v1/agents')
```

## Testing

### Test API Integration

**✅ Do:**
- Write unit tests
- Test error scenarios
- Mock API responses
- Test rate limiting
- Test authentication
- Test edge cases
- Use test environment

**❌ Don't:**
- Skip testing
- Test only happy path
- Use real API in tests
- Ignore rate limits in tests
- Use production credentials
- Forget edge cases
- Test in production

**Example (Python with pytest):**
```python
import pytest
from unittest.mock import Mock, patch

@pytest.fixture
def mock_api():
    """Mock API client."""
    api = Mock()
    return api

def test_get_agents_success(mock_api):
    """Test successful agent retrieval."""
    mock_api.get.return_value = {
        'items': [
            {'id': 'agent-1', 'name': 'Agent 1'},
            {'id': 'agent-2', 'name': 'Agent 2'}
        ],
        'total': 2
    }

    result = mock_api.get('/api/v1/agents')

    assert len(result['items']) == 2
    assert result['total'] == 2

def test_get_agents_error(mock_api):
    """Test agent retrieval error."""
    mock_api.get.side_effect = ApiError(4000, 'Not found')

    with pytest.raises(ApiError) as exc_info:
        mock_api.get('/api/v1/agents')

    assert exc_info.value.code == 4000

def test_retry_on_rate_limit():
    """Test retry on rate limit."""
    with patch('time.sleep'):  # Mock sleep
        api = Mock()
        api.get.side_effect = [
            ApiError(5400, 'Rate limit exceeded'),
            {'items': [], 'total': 0}
        ]

        result = retry_with_backoff(lambda: api.get('/api/v1/agents'))

        assert api.get.call_count == 2
        assert result['total'] == 0
```

## Documentation

### Document API Usage

**✅ Do:**
- Document all API calls
- Include code examples
- Document error handling
- Show request/response examples
- Document rate limits
- Keep documentation updated
- Include troubleshooting guide

**❌ Don't:**
- Skip documentation
- Use outdated examples
- Forget error cases
- Hide implementation details
- Ignore rate limits
- Let docs get stale
- Skip troubleshooting

## Versioning

### Handle API Versions

**✅ Do:**
- Use versioned endpoints (/api/v1/)
- Handle version deprecation
- Test with new versions
- Monitor version changes
- Plan for migrations
- Support multiple versions temporarily
- Document version differences

**❌ Don't:**
- Use unversioned endpoints
- Ignore deprecation notices
- Skip version testing
- Miss version updates
- Delay migrations
- Support old versions forever
- Forget version docs

## Summary Checklist

### Before Going to Production

- [ ] Use HTTPS for all requests
- [ ] Store tokens securely
- [ ] Implement token refresh
- [ ] Handle all error codes
- [ ] Implement retry logic
- [ ] Respect rate limits
- [ ] Implement caching
- [ ] Validate all input
- [ ] Sanitize user input
- [ ] Log API requests
- [ ] Monitor error rates
- [ ] Set up alerts
- [ ] Write tests
- [ ] Document API usage
- [ ] Use production credentials
- [ ] Test in staging environment
- [ ] Plan for scaling
- [ ] Implement monitoring
- [ ] Set up error tracking
- [ ] Review security practices

## Related Documentation

- [Authentication](./authentication.md) - Authentication guide
- [Error Handling](./error-handling.md) - Error handling
- [Rate Limiting](./rate-limiting.md) - Rate limits
- [Security](../best-practices/security.md) - Security practices
- [Performance](../best-practices/performance.md) - Performance optimization

---

**Last Updated**: 2026-02-11
