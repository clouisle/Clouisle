# Webhooks

This document explains how to use webhooks to receive real-time notifications from Clouisle.

## Overview

Webhooks allow you to:

- **Receive notifications**: Get real-time updates about events
- **Automate workflows**: Trigger actions based on events
- **Integrate systems**: Connect Clouisle with external services
- **Monitor activity**: Track important events
- **Build integrations**: Create custom integrations

## What are Webhooks?

Webhooks are HTTP callbacks that send event data to your specified URL when events occur.

**How it works:**
1. You configure a webhook URL
2. Event occurs in Clouisle (e.g., workflow completes)
3. Clouisle sends HTTP POST request to your URL
4. Your server receives and processes the event

**Use cases:**
- Notify external systems when workflows complete
- Trigger workflows from external events
- Sync data with other applications
- Send notifications to chat platforms (Slack, Teams)
- Log events to monitoring systems

## Webhook Events

### Available Events

| Event Type | Description |
|------------|-------------|
| `workflow.started` | Workflow execution started |
| `workflow.completed` | Workflow execution completed successfully |
| `workflow.failed` | Workflow execution failed |
| `workflow.stopped` | Workflow execution stopped manually |
| `agent.created` | Agent created |
| `agent.updated` | Agent updated |
| `agent.deleted` | Agent deleted |
| `agent.published` | Agent published |
| `document.uploaded` | Document uploaded to KB |
| `document.processed` | Document processing completed |
| `document.failed` | Document processing failed |
| `team.member_added` | Member added to team |
| `team.member_removed` | Member removed from team |

### Event Payload Structure

**All webhook payloads follow this structure:**

```json
{
  "event": "workflow.completed",
  "timestamp": "2026-02-11T14:31:23Z",
  "data": {
    // Event-specific data
  },
  "webhook_id": "webhook-123",
  "delivery_id": "delivery-456"
}
```

## Creating Webhooks

### Via Web Interface

**Steps:**

1. Go to **Settings** → **Webhooks**
2. Click **"Create Webhook"**
3. Configure webhook:
   - **URL**: Your endpoint URL
   - **Events**: Select events to subscribe to
   - **Secret**: Optional signing secret
   - **Active**: Enable/disable webhook
4. Click **"Create"**
5. Test webhook
6. Save configuration

**Webhook form:**
```
┌─────────────────────────────────────────┐
│ Create Webhook                          │
├─────────────────────────────────────────┤
│                                         │
│ Name:                                   │
│ [Production Webhook_________]           │
│                                         │
│ URL: *                                  │
│ [https://api.example.com/webhooks]      │
│                                         │
│ Events: *                               │
│ ☑ workflow.completed                    │
│ ☑ workflow.failed                       │
│ ☐ agent.created                         │
│ ☐ document.processed                    │
│ [Select All] [Select None]              │
│                                         │
│ Secret: (optional)                      │
│ [Generate Secret] [_______________]     │
│                                         │
│ ☑ Active                                │
│                                         │
│ [Cancel]  [Create Webhook]              │
│                                         │
└─────────────────────────────────────────┘
```

### Via API

**Endpoint**: `POST /api/v1/webhooks`

**Request:**
```bash
curl -X POST "https://your-domain.com/api/v1/webhooks" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Production Webhook",
    "url": "https://api.example.com/webhooks",
    "events": ["workflow.completed", "workflow.failed"],
    "secret": "your-secret-key",
    "active": true
  }'
```

**Response:**
```json
{
  "code": 0,
  "data": {
    "id": "webhook-123",
    "name": "Production Webhook",
    "url": "https://api.example.com/webhooks",
    "events": ["workflow.completed", "workflow.failed"],
    "active": true,
    "created_at": "2026-02-11T10:00:00Z"
  },
  "msg": "Webhook created successfully"
}
```

## Event Payloads

### workflow.completed

**Sent when a workflow execution completes successfully.**

```json
{
  "event": "workflow.completed",
  "timestamp": "2026-02-11T14:31:23Z",
  "data": {
    "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
    "workflow_name": "Document Summarizer",
    "run_id": "run-789",
    "status": "completed",
    "started_at": "2026-02-11T14:30:00Z",
    "completed_at": "2026-02-11T14:31:23Z",
    "duration": 83,
    "triggered_by": "user-001",
    "trigger_type": "manual",
    "inputs": {
      "document_url": "https://example.com/document.pdf"
    },
    "output": {
      "summary": "The document discusses...",
      "word_count": 1234
    },
    "nodes_executed": 6,
    "nodes_total": 6
  },
  "webhook_id": "webhook-123",
  "delivery_id": "delivery-456"
}
```

### workflow.failed

**Sent when a workflow execution fails.**

```json
{
  "event": "workflow.failed",
  "timestamp": "2026-02-11T10:15:45Z",
  "data": {
    "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
    "workflow_name": "Document Summarizer",
    "run_id": "run-788",
    "status": "failed",
    "started_at": "2026-02-11T10:15:00Z",
    "failed_at": "2026-02-11T10:15:45Z",
    "duration": 45,
    "triggered_by": "webhook",
    "trigger_type": "webhook",
    "error": {
      "node_id": "node-2",
      "node_type": "http_request",
      "message": "API call timeout",
      "details": "Connection timeout after 30 seconds"
    },
    "nodes_executed": 2,
    "nodes_total": 6
  },
  "webhook_id": "webhook-123",
  "delivery_id": "delivery-457"
}
```

### document.processed

**Sent when a document finishes processing.**

```json
{
  "event": "document.processed",
  "timestamp": "2026-02-11T10:01:23Z",
  "data": {
    "kb_id": "550e8400-e29b-41d4-a716-446655440000",
    "kb_name": "Product Documentation",
    "document_id": "doc-789",
    "document_title": "Sales Report Q3 2026",
    "filename": "document.pdf",
    "file_type": "pdf",
    "file_size": 2345678,
    "status": "completed",
    "page_count": 15,
    "word_count": 3450,
    "chunk_count": 45,
    "processing_time": 83,
    "uploaded_by": "user-001"
  },
  "webhook_id": "webhook-123",
  "delivery_id": "delivery-458"
}
```

### agent.published

**Sent when an agent is published.**

```json
{
  "event": "agent.published",
  "timestamp": "2026-02-11T16:00:00Z",
  "data": {
    "agent_id": "550e8400-e29b-41d4-a716-446655440000",
    "agent_name": "Customer Support Agent",
    "team_id": "team-123",
    "team_name": "Support Team",
    "version": 2,
    "published_by": "user-001"
  },
  "webhook_id": "webhook-123",
  "delivery_id": "delivery-459"
}
```

## Receiving Webhooks

### Endpoint Requirements

**Your webhook endpoint must:**
- Accept HTTP POST requests
- Return 2xx status code (200-299) for success
- Respond within 30 seconds
- Use HTTPS (recommended)
- Handle duplicate deliveries (idempotent)

### Example Implementations

**Python (Flask):**

```python
from flask import Flask, request, jsonify
import hmac
import hashlib

app = Flask(__name__)

WEBHOOK_SECRET = "your-secret-key"

@app.route('/webhooks', methods=['POST'])
def handle_webhook():
    # Verify signature
    signature = request.headers.get('X-Clouisle-Signature')
    if not verify_signature(request.data, signature):
        return jsonify({"error": "Invalid signature"}), 401

    # Parse payload
    payload = request.json
    event = payload['event']
    data = payload['data']

    # Handle event
    if event == 'workflow.completed':
        handle_workflow_completed(data)
    elif event == 'workflow.failed':
        handle_workflow_failed(data)
    elif event == 'document.processed':
        handle_document_processed(data)

    return jsonify({"status": "success"}), 200

def verify_signature(payload, signature):
    expected = hmac.new(
        WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected)

def handle_workflow_completed(data):
    print(f"Workflow {data['workflow_name']} completed")
    # Your logic here

def handle_workflow_failed(data):
    print(f"Workflow {data['workflow_name']} failed: {data['error']['message']}")
    # Your logic here

def handle_document_processed(data):
    print(f"Document {data['document_title']} processed")
    # Your logic here

if __name__ == '__main__':
    app.run(port=5000)
```

**Node.js (Express):**

```javascript
const express = require('express');
const crypto = require('crypto');

const app = express();
app.use(express.json());

const WEBHOOK_SECRET = 'your-secret-key';

app.post('/webhooks', (req, res) => {
  // Verify signature
  const signature = req.headers['x-clouisle-signature'];
  if (!verifySignature(req.body, signature)) {
    return res.status(401).json({ error: 'Invalid signature' });
  }

  // Parse payload
  const { event, data } = req.body;

  // Handle event
  switch (event) {
    case 'workflow.completed':
      handleWorkflowCompleted(data);
      break;
    case 'workflow.failed':
      handleWorkflowFailed(data);
      break;
    case 'document.processed':
      handleDocumentProcessed(data);
      break;
  }

  res.status(200).json({ status: 'success' });
});

function verifySignature(payload, signature) {
  const expected = crypto
    .createHmac('sha256', WEBHOOK_SECRET)
    .update(JSON.stringify(payload))
    .digest('hex');
  return crypto.timingSafeEqual(
    Buffer.from(signature),
    Buffer.from(expected)
  );
}

function handleWorkflowCompleted(data) {
  console.log(`Workflow ${data.workflow_name} completed`);
  // Your logic here
}

function handleWorkflowFailed(data) {
  console.log(`Workflow ${data.workflow_name} failed: ${data.error.message}`);
  // Your logic here
}

function handleDocumentProcessed(data) {
  console.log(`Document ${data.document_title} processed`);
  // Your logic here
}

app.listen(5000, () => {
  console.log('Webhook server listening on port 5000');
});
```

## Security

### Signature Verification

**Clouisle signs all webhook payloads using HMAC-SHA256.**

**Headers:**
```
X-Clouisle-Signature: <hmac_sha256_signature>
X-Clouisle-Delivery: <delivery_id>
X-Clouisle-Event: <event_type>
```

**Verification steps:**

1. Get signature from `X-Clouisle-Signature` header
2. Compute HMAC-SHA256 of raw request body using your secret
3. Compare computed signature with received signature
4. Use constant-time comparison to prevent timing attacks

**Python example:**
```python
import hmac
import hashlib

def verify_signature(payload, signature, secret):
    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected)
```

**Node.js example:**
```javascript
const crypto = require('crypto');

function verifySignature(payload, signature, secret) {
  const expected = crypto
    .createHmac('sha256', secret)
    .update(payload)
    .digest('hex');
  return crypto.timingSafeEqual(
    Buffer.from(signature),
    Buffer.from(expected)
  );
}
```

### Best Practices

**✅ Do:**
- Always verify signatures
- Use HTTPS for webhook URLs
- Validate event types
- Handle duplicate deliveries
- Log webhook events
- Implement retry logic
- Use secrets for each webhook
- Rotate secrets regularly

**❌ Don't:**
- Skip signature verification
- Use HTTP (unencrypted)
- Trust payload without validation
- Process events synchronously
- Expose webhook URLs publicly
- Hardcode secrets
- Ignore failed deliveries

## Testing Webhooks

### Test Webhook

**Send test event to webhook:**

1. Go to **Settings** → **Webhooks**
2. Select webhook
3. Click **"Send Test Event"**
4. Choose event type
5. Click **"Send"**
6. View delivery result

**Test event payload:**
```json
{
  "event": "test.event",
  "timestamp": "2026-02-11T16:00:00Z",
  "data": {
    "message": "This is a test event"
  },
  "webhook_id": "webhook-123",
  "delivery_id": "delivery-test-001"
}
```

### Local Testing

**Use ngrok for local testing:**

```bash
# Start ngrok
ngrok http 5000

# Use ngrok URL as webhook URL
https://abc123.ngrok.io/webhooks
```

**Or use webhook.site:**
1. Go to https://webhook.site
2. Copy unique URL
3. Use as webhook URL
4. View received webhooks in browser

## Webhook Deliveries

### Viewing Deliveries

**Check webhook delivery history:**

1. Go to **Settings** → **Webhooks**
2. Select webhook
3. View **Deliveries** tab
4. See all delivery attempts

**Delivery list:**
```
┌─────────────────────────────────────────────────────┐
│ Webhook Deliveries                                  │
├─────────────────────────────────────────────────────┤
│                                                     │
│ ✅ workflow.completed                               │
│    2026-02-11 14:31:23 • 200 OK • 45ms             │
│    [View Details] [Redeliver]                      │
│                                                     │
│ ✅ workflow.failed                                  │
│    2026-02-11 10:15:45 • 200 OK • 52ms             │
│    [View Details] [Redeliver]                      │
│                                                     │
│ ❌ document.processed                               │
│    2026-02-11 10:01:23 • 500 Error • Timeout       │
│    [View Details] [Redeliver]                      │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### Delivery Details

**View delivery information:**

```
┌─────────────────────────────────────────┐
│ Delivery Details                        │
├─────────────────────────────────────────┤
│                                         │
│ Delivery ID: delivery-456               │
│ Event: workflow.completed               │
│ Status: ✅ Success (200 OK)             │
│ Timestamp: 2026-02-11 14:31:23          │
│ Response Time: 45ms                     │
│                                         │
│ Request:                                │
│ POST https://api.example.com/webhooks   │
│ Headers:                                │
│   X-Clouisle-Signature: abc123...       │
│   X-Clouisle-Delivery: delivery-456     │
│   X-Clouisle-Event: workflow.completed  │
│                                         │
│ Payload:                                │
│ {                                       │
│   "event": "workflow.completed",        │
│   "timestamp": "2026-02-11T14:31:23Z",  │
│   ...                                   │
│ }                                       │
│                                         │
│ Response:                               │
│ Status: 200 OK                          │
│ Body: {"status": "success"}             │
│                                         │
│ [Redeliver] [Close]                     │
│                                         │
└─────────────────────────────────────────┘
```

### Redelivery

**Manually redeliver failed webhooks:**

1. Find failed delivery
2. Click **"Redeliver"**
3. Confirm redelivery
4. Webhook is sent again

**Automatic retries:**
- Failed deliveries are retried automatically
- Retry schedule: 1m, 5m, 15m, 1h, 6h
- Maximum 5 retry attempts
- Exponential backoff

## Managing Webhooks

### List Webhooks

**Endpoint**: `GET /api/v1/webhooks`

**Response:**
```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "webhook-123",
        "name": "Production Webhook",
        "url": "https://api.example.com/webhooks",
        "events": ["workflow.completed", "workflow.failed"],
        "active": true,
        "created_at": "2026-02-11T10:00:00Z",
        "last_delivery": "2026-02-11T14:31:23Z",
        "success_rate": 0.98
      }
    ],
    "total": 3
  },
  "msg": "success"
}
```

### Update Webhook

**Endpoint**: `PATCH /api/v1/webhooks/{webhook_id}`

**Request:**
```bash
curl -X PATCH "https://your-domain.com/api/v1/webhooks/webhook-123" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://api.example.com/new-webhooks",
    "events": ["workflow.completed", "workflow.failed", "document.processed"]
  }'
```

### Delete Webhook

**Endpoint**: `DELETE /api/v1/webhooks/{webhook_id}`

**Request:**
```bash
curl -X DELETE "https://your-domain.com/api/v1/webhooks/webhook-123" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Troubleshooting

### Webhook Not Receiving Events

**Problem**: No webhook deliveries

**Solutions:**
1. Check webhook is active
2. Verify URL is correct and accessible
3. Check event subscriptions
4. Test with test event
5. Check firewall/network settings
6. Review webhook logs

### Signature Verification Failing

**Problem**: Signature mismatch

**Solutions:**
1. Verify secret is correct
2. Use raw request body (not parsed JSON)
3. Check signature header name
4. Use constant-time comparison
5. Check HMAC algorithm (SHA256)
6. Review implementation code

### Deliveries Failing

**Problem**: Webhook returns errors

**Solutions:**
1. Check endpoint is responding
2. Verify endpoint returns 2xx status
3. Check response time (<30s)
4. Review endpoint logs
5. Test endpoint manually
6. Check for rate limiting

### Duplicate Events

**Problem**: Receiving same event multiple times

**Solutions:**
1. Implement idempotency using delivery_id
2. Store processed delivery IDs
3. Check for duplicate processing
4. Use database transactions
5. Handle retries gracefully

## Related Documentation

- [API Overview](../overview.md) - API introduction
- [Authentication](../authentication.md) - Authentication methods
- [Workflows API](./endpoints/workflows.md) - Workflow endpoints
- [Agents API](./endpoints/agents.md) - Agent endpoints

---

**Last Updated**: 2026-02-11
