# Rate Limiting

This document explains rate limiting in the Clouisle API.

## Overview

Rate limiting controls the number of API requests you can make within a time window. This ensures:

- **Fair usage**: Prevents any single user from monopolizing resources
- **System stability**: Protects the system from overload
- **Cost control**: Manages infrastructure costs
- **Security**: Mitigates abuse and DDoS attacks

## Rate Limit Tiers

### Default Limits

| Tier | Requests/Hour | Requests/Minute | Concurrent Requests |
|------|---------------|-----------------|---------------------|
| **Free** | 100 | 10 | 2 |
| **Basic** | 1,000 | 100 | 5 |
| **Pro** | 10,000 | 500 | 20 |
| **Enterprise** | Custom | Custom | Custom |

**Note**: Limits are configurable by administrators and may vary by organization.

### Per-Endpoint Limits

Some endpoints have specific limits:

| Endpoint | Limit | Reason |
|----------|-------|--------|
| **POST /api/v1/login/access-token** | 5/minute | Prevent brute force |
| **POST /api/v1/register** | 3/hour | Prevent spam accounts |
| **POST /api/v1/agents/{id}/chat** | 60/minute | Manage LLM costs |
| **POST /api/v1/workflows/{id}/run** | 30/minute | Manage compute resources |
| **POST /api/v1/kb/documents/upload** | 10/minute | Manage storage I/O |

## Rate Limit Headers

### Response Headers

Every API response includes rate limit information:

```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1644580800
X-RateLimit-Window: 3600
```

### Header Descriptions

| Header | Type | Description |
|--------|------|-------------|
| `X-RateLimit-Limit` | integer | Maximum requests allowed in window |
| `X-RateLimit-Remaining` | integer | Requests remaining in current window |
| `X-RateLimit-Reset` | integer | Unix timestamp when limit resets |
| `X-RateLimit-Window` | integer | Window duration in seconds |

### Example Response

```bash
curl -i "https://your-domain.com/api/v1/agents" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

```
HTTP/1.1 200 OK
Content-Type: application/json
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1644580800
X-RateLimit-Window: 3600

{
  "code": 0,
  "data": { ... },
  "msg": "success"
}
```

## Rate Limit Exceeded

### Error Response

When you exceed the rate limit:

**HTTP Status**: 429 Too Many Requests

**Response:**
```json
{
  "code": 5400,
  "data": {
    "retry_after": 3600,
    "limit": 1000,
    "remaining": 0,
    "reset": 1644580800
  },
  "msg": "Rate limit exceeded. Retry after 3600 seconds"
}
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `retry_after` | integer | Seconds to wait before retrying |
| `limit` | integer | Your rate limit |
| `remaining` | integer | Requests remaining (0) |
| `reset` | integer | Unix timestamp when limit resets |

### Headers on 429 Response

```
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1644580800
Retry-After: 3600

{
  "code": 5400,
  "data": { ... },
  "msg": "Rate limit exceeded"
}
```

## Handling Rate Limits

### Check Before Request

**Best practice**: Check rate limit headers before making requests.

**Python example:**
```python
import requests
import time

def make_request_with_rate_limit(url, headers):
    """Make request with rate limit checking."""
    response = requests.get(url, headers=headers)

    # Check rate limit headers
    remaining = int(response.headers.get('X-RateLimit-Remaining', 0))
    reset = int(response.headers.get('X-RateLimit-Reset', 0))

    if remaining < 10:
        # Low on requests, wait until reset
        wait_time = reset - time.time()
        if wait_time > 0:
            print(f"Rate limit low. Waiting {wait_time}s...")
            time.sleep(wait_time)

    return response.json()
```

### Exponential Backoff

**When rate limited**: Use exponential backoff to retry.

**Python example:**
```python
import requests
import time

def make_request_with_backoff(url, headers, max_retries=3):
    """Make request with exponential backoff."""
    for attempt in range(max_retries):
        response = requests.get(url, headers=headers)
        data = response.json()

        if data['code'] == 0:
            return data['data']
        elif data['code'] == 5400:
            # Rate limited
            retry_after = data['data']['retry_after']
            wait_time = min(retry_after, 2 ** attempt * 60)
            print(f"Rate limited. Waiting {wait_time}s...")
            time.sleep(wait_time)
        else:
            raise Exception(f"Error {data['code']}: {data['msg']}")

    raise Exception("Max retries exceeded")
```

### Request Queuing

**For high-volume applications**: Implement a request queue.

**Python example:**
```python
import queue
import threading
import time
import requests

class RateLimitedClient:
    def __init__(self, rate_limit=100, window=3600):
        self.rate_limit = rate_limit
        self.window = window
        self.queue = queue.Queue()
        self.requests_made = []
        self.lock = threading.Lock()

        # Start worker thread
        self.worker = threading.Thread(target=self._process_queue)
        self.worker.daemon = True
        self.worker.start()

    def _process_queue(self):
        """Process queued requests."""
        while True:
            # Get next request
            url, headers, callback = self.queue.get()

            # Wait if rate limit reached
            with self.lock:
                now = time.time()
                # Remove old requests outside window
                self.requests_made = [
                    t for t in self.requests_made
                    if now - t < self.window
                ]

                if len(self.requests_made) >= self.rate_limit:
                    # Wait until oldest request expires
                    wait_time = self.window - (now - self.requests_made[0])
                    time.sleep(wait_time)

                # Make request
                response = requests.get(url, headers=headers)
                self.requests_made.append(time.time())

            # Call callback with response
            callback(response.json())
            self.queue.task_done()

    def get(self, url, headers, callback):
        """Queue a GET request."""
        self.queue.put((url, headers, callback))

# Usage
client = RateLimitedClient(rate_limit=100, window=3600)

def handle_response(data):
    print(f"Received: {data}")

client.get(
    "https://your-domain.com/api/v1/agents",
    {"Authorization": "Bearer YOUR_TOKEN"},
    handle_response
)
```

## Rate Limit Strategies

### Batch Requests

**Instead of multiple requests**: Use batch endpoints when available.

**❌ Don't:**
```python
# 100 separate requests
for agent_id in agent_ids:
    response = requests.get(
        f"https://your-domain.com/api/v1/agents/{agent_id}",
        headers=headers
    )
```

**✅ Do:**
```python
# 1 batch request
response = requests.post(
    "https://your-domain.com/api/v1/agents/batch",
    headers=headers,
    json={"ids": agent_ids}
)
```

### Caching

**Cache responses**: Reduce redundant requests.

**Python example:**
```python
import requests
from functools import lru_cache
import time

@lru_cache(maxsize=100)
def get_agent(agent_id, cache_time):
    """Get agent with caching."""
    response = requests.get(
        f"https://your-domain.com/api/v1/agents/{agent_id}",
        headers={"Authorization": "Bearer YOUR_TOKEN"}
    )
    return response.json()

# Use with cache time to invalidate cache
cache_time = int(time.time() / 300)  # 5-minute cache
agent = get_agent("agent-id", cache_time)
```

### Pagination

**For large datasets**: Use pagination to reduce request size.

**Python example:**
```python
def get_all_agents(headers):
    """Get all agents with pagination."""
    all_agents = []
    page = 1
    page_size = 100  # Maximum page size

    while True:
        response = requests.get(
            "https://your-domain.com/api/v1/agents",
            headers=headers,
            params={"page": page, "page_size": page_size}
        )
        data = response.json()

        if data['code'] != 0:
            break

        agents = data['data']['items']
        all_agents.extend(agents)

        # Check if more pages
        if page >= data['data']['total_pages']:
            break

        page += 1

    return all_agents
```

## Monitoring Rate Limits

### Tracking Usage

**Monitor your rate limit usage:**

**Python example:**
```python
import requests

def track_rate_limit(url, headers):
    """Track rate limit usage."""
    response = requests.get(url, headers=headers)

    limit = int(response.headers.get('X-RateLimit-Limit', 0))
    remaining = int(response.headers.get('X-RateLimit-Remaining', 0))
    reset = int(response.headers.get('X-RateLimit-Reset', 0))

    usage_percent = ((limit - remaining) / limit) * 100

    print(f"Rate Limit Usage: {usage_percent:.1f}%")
    print(f"Remaining: {remaining}/{limit}")
    print(f"Resets at: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(reset))}")

    return response.json()
```

### Alerting

**Set up alerts**: Get notified when approaching limits.

**Python example:**
```python
def make_request_with_alert(url, headers, alert_threshold=0.9):
    """Make request with rate limit alerting."""
    response = requests.get(url, headers=headers)

    limit = int(response.headers.get('X-RateLimit-Limit', 0))
    remaining = int(response.headers.get('X-RateLimit-Remaining', 0))

    usage = (limit - remaining) / limit

    if usage >= alert_threshold:
        # Send alert (email, Slack, etc.)
        send_alert(f"Rate limit at {usage*100:.1f}%")

    return response.json()
```

## Increasing Rate Limits

### Requesting Higher Limits

**If you need higher limits:**

1. **Assess your needs**: Calculate required request rate
2. **Optimize first**: Implement caching, batching, pagination
3. **Contact administrator**: Request limit increase
4. **Provide justification**: Explain use case and expected load
5. **Consider upgrade**: Move to higher tier if available

**Example request:**
```
Subject: Rate Limit Increase Request

Current Limit: 1,000 requests/hour
Requested Limit: 5,000 requests/hour

Use Case: Automated data synchronization system
Expected Load: 3,000-4,000 requests/hour during business hours
Optimizations Implemented:
- Request batching
- Response caching (5-minute TTL)
- Pagination with max page size

Justification: Current limit causes synchronization delays
during peak hours, impacting business operations.
```

### API Key Limits

**Different API keys can have different limits:**

- Create separate API keys for different applications
- Assign appropriate limits to each key
- Monitor usage per key

**Example:**
```
Production API Key:  10,000 requests/hour
Development API Key: 1,000 requests/hour
Testing API Key:     100 requests/hour
```

## Best Practices

### Efficient API Usage

**✅ Do:**
- Check rate limit headers before making requests
- Implement exponential backoff for retries
- Use batch endpoints when available
- Cache responses to reduce redundant requests
- Use pagination for large datasets
- Monitor your rate limit usage
- Request limit increases proactively

**❌ Don't:**
- Ignore rate limit headers
- Retry immediately after 429 error
- Make unnecessary requests
- Fetch all data at once without pagination
- Use same API key for all applications
- Wait until hitting limits to optimize

### Error Handling

**✅ Do:**
```python
def make_request(url, headers):
    try:
        response = requests.get(url, headers=headers)
        data = response.json()

        if data['code'] == 0:
            return data['data']
        elif data['code'] == 5400:
            # Rate limited - wait and retry
            retry_after = data['data']['retry_after']
            time.sleep(retry_after)
            return make_request(url, headers)
        else:
            raise Exception(f"Error: {data['msg']}")
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        return None
```

**❌ Don't:**
```python
def make_request(url, headers):
    # No error handling
    response = requests.get(url, headers=headers)
    return response.json()['data']
```

## Code Examples

### JavaScript/TypeScript

```typescript
interface RateLimitInfo {
  limit: number;
  remaining: number;
  reset: number;
}

async function makeRequestWithRateLimit(
  url: string,
  headers: Record<string, string>
): Promise<any> {
  const response = await fetch(url, { headers });

  // Extract rate limit headers
  const rateLimitInfo: RateLimitInfo = {
    limit: parseInt(response.headers.get('X-RateLimit-Limit') || '0'),
    remaining: parseInt(response.headers.get('X-RateLimit-Remaining') || '0'),
    reset: parseInt(response.headers.get('X-RateLimit-Reset') || '0'),
  };

  const data = await response.json();

  if (data.code === 5400) {
    // Rate limited
    const retryAfter = data.data.retry_after * 1000; // Convert to ms
    console.log(`Rate limited. Waiting ${retryAfter}ms...`);
    await new Promise(resolve => setTimeout(resolve, retryAfter));
    return makeRequestWithRateLimit(url, headers);
  }

  // Log rate limit info
  console.log(`Rate limit: ${rateLimitInfo.remaining}/${rateLimitInfo.limit}`);

  return data.data;
}
```

### Go

```go
package main

import (
    "encoding/json"
    "fmt"
    "net/http"
    "strconv"
    "time"
)

type RateLimitInfo struct {
    Limit     int
    Remaining int
    Reset     int64
}

func makeRequestWithRateLimit(url string, headers map[string]string) (interface{}, error) {
    client := &http.Client{}
    req, err := http.NewRequest("GET", url, nil)
    if err != nil {
        return nil, err
    }

    for key, value := range headers {
        req.Header.Set(key, value)
    }

    resp, err := client.Do(req)
    if err != nil {
        return nil, err
    }
    defer resp.Body.Close()

    // Extract rate limit headers
    rateLimitInfo := RateLimitInfo{
        Limit:     parseInt(resp.Header.Get("X-RateLimit-Limit")),
        Remaining: parseInt(resp.Header.Get("X-RateLimit-Remaining")),
        Reset:     parseInt64(resp.Header.Get("X-RateLimit-Reset")),
    }

    var result map[string]interface{}
    json.NewDecoder(resp.Body).Decode(&result)

    if code, ok := result["code"].(float64); ok && code == 5400 {
        // Rate limited
        data := result["data"].(map[string]interface{})
        retryAfter := int(data["retry_after"].(float64))
        fmt.Printf("Rate limited. Waiting %d seconds...\n", retryAfter)
        time.Sleep(time.Duration(retryAfter) * time.Second)
        return makeRequestWithRateLimit(url, headers)
    }

    fmt.Printf("Rate limit: %d/%d\n", rateLimitInfo.Remaining, rateLimitInfo.Limit)

    return result["data"], nil
}

func parseInt(s string) int {
    i, _ := strconv.Atoi(s)
    return i
}

func parseInt64(s string) int64 {
    i, _ := strconv.ParseInt(s, 10, 64)
    return i
}
```

## Related Documentation

- [API Overview](./overview.md) - API introduction
- [Authentication](./authentication.md) - Authentication methods
- [Response Format](./response-format.md) - Response structure
- [Error Codes](./error-codes.md) - Complete error reference

---

**Last Updated**: 2026-02-11
