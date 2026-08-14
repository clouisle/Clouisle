# Webhooks

This document explains the webhook capabilities in Clouisle.

## Overview

Clouisle has **two** webhook mechanisms:

1. **Outbound notifications (generic webhook)** — when a notification is sent with the `webhook` channel enabled, Clouisle POSTs a customizable payload to a single URL configured in site settings. There is no webhook-subscription CRUD API and no per-event-type subscriptions.
2. **Inbound workflow trigger** — `POST /api/v1/workflows/webhook/{webhook_token}` starts a published workflow whose trigger type is `webhook`.

## Outbound Notifications (Generic Webhook)

### How it Works

1. An administrator configures a single webhook URL in **site settings** (fields `webhook_enabled`, `webhook_url`, `webhook_method`, `webhook_headers`, `webhook_body_template`, `webhook_secret`)
2. When a notification (system/team notification, auto-notification, security alert, ...) is created with the `webhook` delivery channel enabled, Clouisle schedules an async task
3. The task renders the body template with the notification's variables and sends the HTTP request
4. The delivery status is recorded in the `notification_deliveries` table

### Configuration (Site Settings)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `webhook_enabled` | bool | `false` | Enable generic webhook notifications |
| `webhook_url` | string | `""` | Target URL |
| `webhook_method` | string | `"POST"` | HTTP method (`POST` or `GET`) |
| `webhook_headers` | json | `{}` | Custom request headers |
| `webhook_body_template` | string | `{"title": "{{title}}", "content": "{{content}}", "link_url": "{{link_url}}"}` | Body template with `{{title}}`, `{{content}}`, `{{link_url}}` placeholders |
| `webhook_secret` | string | `""` | Secret for HMAC signature |

If the body template renders to valid JSON it is sent as JSON; otherwise it is sent as plain text. For `GET`, the variables are sent as query parameters.

### Test the Webhook

**Endpoint:** `POST /api/v1/admin/site-settings/test-webhook`

**Authorization:** `admin:settings:update`

Sends a test notification (title/content with the site name) through the configured webhook:

```bash
curl -X POST "https://your-domain.com/api/v1/admin/site-settings/test-webhook" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

**Response:**
```json
{
  "code": 0,
  "data": null,
  "msg": "Test webhook sent"
}
```

### Signature Verification

When `webhook_secret` is configured, the outgoing request includes two signature headers computed as **HMAC-SHA256** over the **rendered body string**:

```
X-Webhook-Signature: sha256=<hex digest>
X-Webhook-Signature-256: <hex digest>
```

**Verify on your receiving endpoint:**

```python
import hmac
import hashlib

def verify_webhook_signature(payload: str, signature: str, secret: str) -> bool:
    expected = hmac.new(
        secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, f"sha256={expected}")
```

**Node.js:**
```javascript
const crypto = require('crypto');

function verifyWebhookSignature(payload, signature, secret) {
  const expected = crypto
    .createHmac('sha256', secret)
    .update(payload)
    .digest('hex');

  return crypto.timingSafeEqual(
    Buffer.from(`sha256=${expected}`),
    Buffer.from(signature)
  );
}
```

> **Note:** the signature is computed over the **raw body string** (before JSON parsing). Always verify against the raw request body.

### Retry Behavior

Delivery is handled by the Celery task `send_notification_webhook`:

- **Max retries**: 3 (in addition to the initial attempt)
- **Countdown**: `60 * (retries + 1)` seconds — 60s, 120s, 180s
- **Success**: an HTTP 2xx response marks the delivery `success`
- **Failure**: the delivery is marked `failed` with the error message, and the task retries per the schedule above

### Delivery Records

Each webhook delivery is tracked in the `notification_deliveries` table (channel `webhook`):

- `status`: `pending` → `sending` → `success` / `failed`
- `error_message`: failure reason (if any)
- `retry_count`: number of retries performed
- `sent_at`: timestamp of the successful send

There is **no** public API for webhook delivery logs or statistics — query the database or the notification admin UI.

## Inbound Workflow Trigger

A published workflow with trigger type **webhook** can be started by any caller holding a valid `clou_` API key.

**Endpoint:**
```
POST /api/v1/workflows/webhook/{webhook_token}
```

**Authorization:** `Authorization: Bearer clou_<api key>` (required; the key's owner is recorded as the caller)

**Request:** the JSON body is the workflow's input variables:

```bash
curl -X POST "https://your-domain.com/api/v1/workflows/webhook/$WEBHOOK_TOKEN" \
  -H "Authorization: Bearer $CLOUISLE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_email": "customer@example.com",
    "inquiry_text": "I need help with my order"
  }'
```

**Response:**
```json
{
  "code": 0,
  "data": {
    "run_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "pending",
    "stream_url": "/api/v1/workflows/runs/550e8400-e29b-41d4-a716-446655440000/stream"
  },
  "msg": "success"
}
```

The `stream_url` can be polled via SSE (`GET /api/v1/workflows/runs/{run_id}/stream`) to track execution. Webhook-triggered runs are publicly streamable (no auth required); see [SSE Streaming](./sse-streaming.md).

### Requirements & Errors

| Condition | Result |
|-----------|--------|
| Missing/invalid `Authorization` header | `2000` (`UNAUTHORIZED`), HTTP 401 |
| API key format not `clou_...` | `2000` (`UNAUTHORIZED`) |
| API key authentication failure | `2000` (`UNAUTHORIZED`) |
| Unknown `webhook_token` | `1004` (`FORBIDDEN`), HTTP 403 |
| Workflow not published | `1004` (`FORBIDDEN`) |
| Workflow trigger type is not `webhook` | `1004` (`FORBIDDEN`) |
| API key restricted to other workflows | `3000` (`PERMISSION_DENIED`), HTTP 403 |

The webhook token is compared in constant time and can be regenerated via `POST /api/v1/workflows/{workflow_id}/regenerate-webhook-token`.

## Example Receiver

**Python (FastAPI/Flask-style):**

```python
import hmac
import hashlib
from flask import Flask, request, jsonify

app = Flask(__name__)
WEBHOOK_SECRET = "your-configured-webhook-secret"

@app.route("/webhooks/clouisle", methods=["POST"])
def handle_webhook():
    payload = request.get_data(as_text=True)

    signature = request.headers.get("X-Webhook-Signature")
    expected = hmac.new(
        WEBHOOK_SECRET.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not signature or not hmac.compare_digest(signature, f"sha256={expected}"):
        return jsonify({"error": "Invalid signature"}), 401

    data = request.get_json(silent=True) or request.form.to_dict()
    print(f"Notification: {data.get('title')} - {data.get('content')}")
    return jsonify({"status": "success"}), 200
```

**Node.js (Express):**

```javascript
const express = require('express');
const crypto = require('crypto');

const app = express();
const WEBHOOK_SECRET = 'your-configured-webhook-secret';

app.post(
  '/webhooks/clouisle',
  express.raw({ type: () => true }), // raw body for signature verification
  (req, res) => {
    const payload = req.body.toString();
    const signature = req.headers['x-webhook-signature'];

    const expected = crypto
      .createHmac('sha256', WEBHOOK_SECRET)
      .update(payload)
      .digest('hex');

    if (!signature || !crypto.timingSafeEqual(
      Buffer.from(`sha256=${expected}`),
      Buffer.from(signature)
    )) {
      return res.status(401).json({ error: 'Invalid signature' });
    }

    let data;
    try {
      data = JSON.parse(payload);
    } catch {
      data = { raw: payload };
    }
    console.log(`Notification: ${data.title} - ${data.content}`);
    res.status(200).json({ status: 'success' });
  }
);
```

## Best Practices

**✅ Do:**
- Verify `X-Webhook-Signature` against the **raw body** with constant-time comparison
- Return a 2xx quickly from your receiver; Clouisle retries failures (3 retries at 60s/120s/180s)
- Make your receiver idempotent — the same notification may be delivered more than once (initial attempt + retries)
- Restrict inbound workflow-trigger API keys to the specific workflow via `workflow_ids`

**❌ Don't:**
- Expect per-event webhook subscriptions or delivery-log APIs — only the single site-settings URL exists
- Use HTTP (unencrypted) URLs
- Trust the payload without validating it
- Block on long processing inside the receiver

## Troubleshooting

### No Notifications Received

**Solutions:**
1. Check `webhook_enabled` is `true` and `webhook_url` is set in site settings
2. Verify the notification was created with the `webhook` delivery channel
3. Test with `POST /api/v1/admin/site-settings/test-webhook`
4. Check the `notification_deliveries` table for the delivery status/error

### Signature Verification Failing

**Solutions:**
1. Confirm `webhook_secret` matches on both sides
2. Compute the signature over the **raw body string** (not the parsed JSON)
3. Compare against either `X-Webhook-Signature` (`sha256=...` prefix) or `X-Webhook-Signature-256` (hex only)

### Deliveries Failing

**Solutions:**
1. Verify your endpoint responds 2xx within the 30s timeout
2. Check the delivery `error_message` in `notification_deliveries`
3. After 3 retries the delivery is marked failed; fix the receiver and trigger a new notification

## Related Documentation

- [Webhooks Guide](./webhooks-guide.md) - Outbound webhook configuration guide
- [SSE Streaming](./sse-streaming.md) - Streaming workflow execution
- [Workflows API](./endpoints/workflows.md) - Workflow endpoints
- [Notifications API](./endpoints/settings.md) - Notification configuration

---

**Last Updated**: 2026-08-14
