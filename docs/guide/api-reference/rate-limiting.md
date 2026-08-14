# Rate Limiting

This document explains the rate limiting and throttling mechanisms in the Clouisle API.

## Overview

Clouisle does **not** implement per-endpoint or per-API-key request throttling middleware, and does not send `X-RateLimit-*` or `Retry-After` headers on ordinary requests.

Rate limiting exists only for specific security-sensitive or quota-bound operations:

1. **Login attempt lockout** — failed password logins lock the account
2. **TOTP verification lockout** — repeated 2FA failures temporarily lock verification
3. **Bulk email quota** — admin bulk email sending is capped at 100 emails/hour per sender
4. **Model provider rate limits** — upstream provider HTTP 429 errors are mapped to a Clouisle error code

## 1. Login Attempt Lockout

**Where**: `POST /api/v1/login/access-token` (and related login flows)

**Defaults** (configurable via site settings `max_login_attempts` and `lockout_duration_minutes`):

| Setting | Default | Description |
|---------|---------|-------------|
| `max_login_attempts` | 5 | Failed attempts before the account is locked |
| `lockout_duration_minutes` | 15 | Lockout duration in minutes |

After `max_login_attempts` consecutive failures, the account is locked: the user's `locked_until` is set, and further logins fail with `5300` (`ACCOUNT_LOCKED`). While locked, the remaining time is reported:

```json
{
  "code": 5300,
  "data": {
    "remaining_seconds": 600
  },
  "msg": "Account locked"
}
```

Before lockout, failed logins return `2003` (`INVALID_CREDENTIALS`) with the remaining attempts:

```json
{
  "code": 2003,
  "data": {
    "remaining_attempts": 3
  },
  "msg": "Incorrect email or password"
}
```

**Handling**: wait for the lockout window (default 15 minutes) or contact an administrator.

## 2. TOTP Verification Lockout

**Where**: `POST /api/v1/login/verify-totp` and related TOTP endpoints

**Defaults** (constants in `backend/app/core/totp_security.py`):

| Setting | Default |
|---------|---------|
| `MAX_ATTEMPTS` | 5 failures |
| `ATTEMPT_WINDOW` | 300 seconds (5 minutes) |
| `LOCKOUT_DURATION` | 900 seconds (15 minutes) |

After 5 failed TOTP codes within 5 minutes, TOTP verification is locked for 15 minutes. Failures return `5312` (`TOTP_RATE_LIMITED`) with the remaining lockout seconds:

```json
{
  "code": 5312,
  "data": {
    "seconds": 900
  },
  "msg": "Too many failed attempts. Please try again in 900 seconds."
}
```

## 3. Bulk Email Quota

**Where**: `POST /api/v1/admin/users/send-email`

Bulk email sending is limited to **100 emails per hour per sender**. Exceeding the cap returns `5400` (`RATE_LIMITED`):

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

If the remaining quota is insufficient for the requested recipient list, the response carries the shortfall:

```json
{
  "code": 5400,
  "data": {
    "requested": 150,
    "remaining": 40
  },
  "msg": "Email quota insufficient"
}
```

## 4. Model Provider Rate Limits

**Where**: knowledge-base document processing (embedding) and chat

When an upstream model provider (OpenAI, DashScope, SiliconFlow, Volcengine, Kling, etc.) returns HTTP 429 / rate-limit errors, the failure is classified and mapped:

- During KB document processing, a provider `RateLimitError` maps to `5400` (`RATE_LIMITED`); other provider errors map to quota (`6103`), configuration (`6104`), or not-found (`6100`) codes as appropriate
- During streaming chat, provider rate limits are surfaced as an SSE `error` event (with code `0`/generic message or provider-specific text), and the partial response is preserved

There is no fixed retry schedule on the API side; retry after the provider's limit window resets.

## Handling Rate Limits

### General Approach

Since there is no uniform rate-limit envelope, handle the specific codes:

```python
import time

def handle_quota_errors(result):
    if result['code'] == 5312:
        # TOTP lockout: wait the reported seconds
        time.sleep(result['data']['seconds'])
    elif result['code'] == 5300:
        # Account locked: wait the reported seconds
        time.sleep(result['data'].get('remaining_seconds', 900))
    elif result['code'] == 2003 and 'remaining_attempts' in (result.get('data') or {}):
        # Failed login (not locked yet) - back off
        print("Login failed. Back off before retrying.")
    elif result['code'] == 5400:
        # Email quota or provider rate limit: wait for the window
        print("Rate limited. Retry after the quota window resets.")
    elif result['code'] == 6103:
        # Model quota exceeded
        print("Model quota exceeded. Retry later.")
```

### Exponential Backoff

For transient provider/quota failures, back off exponentially and avoid hammering the endpoint:

```python
import time

def make_request_with_backoff(url, headers, max_retries=3):
    for attempt in range(max_retries):
        response = requests.get(url, headers=headers)
        data = response.json()

        if data['code'] == 0:
            return data['data']
        elif data['code'] in (5312, 5300, 5400, 6103):
            wait_time = min(2 ** attempt * 30, 300)
            print(f"Limited. Waiting {wait_time}s...")
            time.sleep(wait_time)
        else:
            raise Exception(f"Error {data['code']}: {data['msg']}")

    raise Exception("Max retries exceeded")
```

## Increasing Limits

- **Login/TOTP lockout parameters** are site settings (`max_login_attempts`, `lockout_duration_minutes`) adjustable by administrators
- **Email quota** (100/hour) is a hard-coded default in the admin send-email endpoint
- **Provider rate limits** are governed by your upstream model provider subscription; raise quota at the provider

## Best Practices

**✅ Do:**
- Back off exponentially on `5312`, `5300`, `5400`, and `6103`
- Rate-limit login attempts client-side to avoid tripping account lockout
- Monitor email quota when sending bulk notifications
- Handle the SSE `error` event for streamed chat

**❌ Don't:**
- Expect `X-RateLimit-*` headers or `retry_after` payloads — they do not exist
- Retry immediately on 429 responses
- Treat `5400` as a global API rate limit — it is specific to email/provider quotas

## Related Documentation

- [API Overview](./overview.md) - API introduction
- [Authentication](./authentication.md) - Authentication methods
- [Response Format](./response-format.md) - Response structure
- [Error Codes](./error-codes.md) - Complete error reference

---

**Last Updated**: 2026-08-14
