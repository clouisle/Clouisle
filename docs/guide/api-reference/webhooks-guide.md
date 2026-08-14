# Webhooks Guide

This guide explains how to configure and use webhooks in Clouisle.

## Overview

Clouisle supports two webhook integrations:

- **Outbound notifications** — send a notification payload to a single site-configured URL (HMAC-signed, with retries). This replaces event-subscription webhooks; there is no per-event CRUD API.
- **Inbound workflow triggers** — start a published webhook-triggered workflow with an API key.

## 1. Outbound Notifications

### Configuration

Outbound webhook settings live in the **site settings** (admin UI, category `webhook`):

| Setting | Default | Description |
|---------|---------|-------------|
| `webhook_enabled` | `false` | Master switch |
| `webhook_url` | `""` | Target URL (required when enabled) |
| `webhook_method` | `POST` | `POST` or `GET` |
| `webhook_headers` | `{}` | Custom headers (JSON) |
| `webhook_body_template` | `{"title": "{{title}}", "content": "{{content}}", "link_url": "{{link_url}}"}` | Body template; placeholders `{{title}}`, `{{content}}`, `{{link_url}}` are substituted and JSON-escaped |
| `webhook_secret` | `""` | HMAC signing secret (optional) |

**Flow:**

1. A notification is created with the `webhook` channel enabled (system events, security alerts, auto-notifications, team notifications, ...)
2. The async task `send_notification_webhook` renders the template with the notification's `title`/`content`/`link_url` and sends the request (30s timeout)
3. Valid JSON templates are sent as `application/json`; otherwise the rendered string is sent as text; `GET` sends the variables as query parameters
4. Delivery state is persisted in the `notification_deliveries` table

### Verify the Signature

If `webhook_secret` is set, the request includes:

```
X-Webhook-Signature: sha256=<hmac-sha256 hex of the rendered body>
X-Webhook-Signature-256: <same hex digest, without prefix>
```

**Verify (Python):**

```python
import hmac
import hashlib

def verify_webhook_signature(payload: str, signature: str, secret: str) -> bool:
    """Verify X-Webhook-Signature against the raw request body."""
    expected = hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature, f"sha256={expected}")
```

**Verify (JavaScript):**

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

Use the **raw request body** (before any JSON parsing) for verification.

### Test the Webhook

**Endpoint:** `POST /api/v1/admin/site-settings/test-webhook` (requires `admin:settings:update`)

```bash
curl -X POST "https://your-domain.com/api/v1/admin/site-settings/test-webhook" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

The server sends a test notification through the configured webhook and returns `{"code": 0, "msg": "Test webhook sent"}`.

### Retry and Delivery Records

- **Retries**: max 3, at 60s, 120s, 180s after each failure (`countdown = 60 * (retries + 1)`)
- **Delivery status**: `pending` → `sending` → `success` / `failed`, recorded per channel in the `notification_deliveries` table with `error_message`, `retry_count`, and `sent_at`
- There is no webhook delivery log API; inspect the database or admin notification views

## 2. Inbound Workflow Triggers

### Setup

1. Create a workflow and set its trigger type to **webhook**
2. Publish the workflow
3. Obtain its `webhook_token` (visible in the workflow settings; regenerate via `POST /api/v1/workflows/{workflow_id}/regenerate-webhook-token`)
4. Create an API key with access to the workflow (via `workflow_ids`)

### Trigger

**Endpoint:** `POST /api/v1/workflows/webhook/{webhook_token}`

**Request:**

```bash
curl -X POST "https://your-domain.com/api/v1/workflows/webhook/$WEBHOOK_TOKEN" \
  -H "Authorization: Bearer $CLOUISLE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"customer_email": "customer@example.com", "inquiry_text": "I need help with my order"}'
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

**Track the run:**

```bash
curl -N "https://your-domain.com/api/v1/workflows/runs/$RUN_ID/stream?from_sequence=0"
```

Webhook-triggered runs are streamable without authentication. Alternatively poll `GET /api/v1/workflows/runs/{run_id}`.

### Error Cases

| Situation | HTTP / Code |
|-----------|-------------|
| No `Authorization` header | 401, code `2000` |
| Token not a `clou_` API key | 401, code `2000` |
| API key invalid | 401, code `2000` |
| Unknown webhook token | 403, code `1004` |
| Workflow not published | 403, code `1004` |
| Trigger type is not `webhook` | 403, code `1004` |
| Key restricted to other workflows | 403, code `3000` |

## Example Receiver

**Python (Flask):**

```python
from flask import Flask, request, jsonify
import hmac
import hashlib

app = Flask(__name__)
WEBHOOK_SECRET = "your-configured-webhook-secret"

@app.route("/webhooks/clouisle", methods=["POST"])
def handle_webhook():
    payload = request.get_data(as_text=True)
    signature = request.headers.get("X-Webhook-Signature", "")

    expected = hmac.new(
        WEBHOOK_SECRET.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(signature, f"sha256={expected}"):
        return jsonify({"error": "Invalid signature"}), 401

    data = request.get_json(silent=True) or {"raw": payload}
    # Process the notification asynchronously
    print(f"Title: {data.get('title')}")
    print(f"Content: {data.get('content')}")
    print(f"Link: {data.get('link_url')}")
    return jsonify({"status": "success"}), 200
```

**Node.js (Express):**

```javascript
const express = require('express');
const crypto = require('crypto');

const app = express();
const WEBHOOK_SECRET = 'your-configured-webhook-secret';

app.post('/webhooks/clouisle', express.raw({ type: () => true }), (req, res) => {
  const payload = req.body.toString();
  const signature = req.headers['x-webhook-signature'] || '';

  const expected = crypto
    .createHmac('sha256', WEBHOOK_SECRET)
    .update(payload)
    .digest('hex');

  const ok = crypto.timingSafeEqual(
    Buffer.from(`sha256=${expected}`),
    Buffer.from(signature)
  );

  if (!ok) {
    return res.status(401).json({ error: 'Invalid signature' });
  }

  let data;
  try {
    data = JSON.parse(payload);
  } catch {
    data = { raw: payload };
  }
  console.log(`Title: ${data.title}`);
  console.log(`Content: ${data.content}`);
  res.status(200).json({ status: 'success' });
});
```

## Best Practices

**✅ Do:**
- Verify signatures with constant-time comparison against the raw body
- Respond 2xx quickly; treat delivery as asynchronous
- Make the receiver idempotent (initial attempt + up to 3 retries)
- Use a dedicated API key restricted to the target workflow for inbound triggers
- Test with `POST /api/v1/admin/site-settings/test-webhook` before relying on it

**❌ Don't:**
- Expect event-type subscription lists or per-webhook secrets — only the single site URL with one secret exists
- Use HTTP URLs
- Parse the body before verifying the signature
- Block the request handler on long processing

## Troubleshooting

### No Webhook Received

1. Confirm `webhook_enabled=true` and `webhook_url` set
2. Verify the notification includes the `webhook` channel
3. Run the test-webhook endpoint
4. Check `notification_deliveries` for status/error

### Signature Mismatch

1. Ensure both sides use the same `webhook_secret`
2. Sign the raw body string, not the parsed JSON
3. Note the two header forms: `sha256=<hex>` vs bare `<hex>`

### Deliveries Fail

1. Confirm your endpoint returns 2xx within 30s
2. Review `error_message` in `notification_deliveries`
3. Fix the receiver; new notifications will be attempted (3 retries: 60s/120s/180s)

## Related Documentation

- [Webhooks](./webhooks.md) - API reference for webhooks
- [SSE Streaming](./sse-streaming.md) - Streaming workflow runs
- [Workflows API](./endpoints/workflows.md) - Workflow endpoints
- [Authentication](./authentication.md) - API keys and tokens

---

**Last Updated**: 2026-08-14
