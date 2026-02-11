# Webhooks Guide

This guide explains how to use webhooks in Clouisle to receive real-time notifications about events.

## Overview

Webhooks allow you to receive HTTP callbacks when specific events occur in Clouisle. Instead of polling for changes, your application receives instant notifications.

## How Webhooks Work

1. **Configure Webhook**: Register a webhook URL and select events
2. **Event Occurs**: An event happens in Clouisle (e.g., agent created)
3. **HTTP Request**: Clouisle sends POST request to your URL
4. **Process Event**: Your application processes the webhook payload
5. **Respond**: Your endpoint returns 200 OK

## Webhook Events

### Agent Events

- `agent.created` - Agent created
- `agent.updated` - Agent updated
- `agent.deleted` - Agent deleted
- `agent.published` - Agent published
- `agent.unpublished` - Agent unpublished

### Conversation Events

- `conversation.created` - Conversation started
- `conversation.updated` - Conversation updated
- `conversation.completed` - Conversation ended
- `message.created` - Message sent
- `message.updated` - Message updated

### Workflow Events

- `workflow.created` - Workflow created
- `workflow.updated` - Workflow updated
- `workflow.deleted` - Workflow deleted
- `workflow.started` - Workflow execution started
- `workflow.completed` - Workflow execution completed
- `workflow.failed` - Workflow execution failed

### Knowledge Base Events

- `kb.created` - Knowledge base created
- `kb.updated` - Knowledge base updated
- `kb.deleted` - Knowledge base deleted
- `document.created` - Document uploaded
- `document.processed` - Document processing completed
- `document.failed` - Document processing failed

### User Events

- `user.created` - User registered
- `user.updated` - User updated
- `user.deleted` - User deleted
- `user.login` - User logged in
- `user.logout` - User logged out

### Team Events

- `team.created` - Team created
- `team.updated` - Team updated
- `team.deleted` - Team deleted
- `team.member_added` - Member added to team
- `team.member_removed` - Member removed from team

## Webhook Payload

### Standard Format

All webhook payloads follow this structure:

```json
{
  "id": "evt_123456",
  "event": "agent.created",
  "timestamp": "2026-02-11T16:00:00Z",
  "data": {
    "id": "agent-123",
    "name": "Customer Support Agent",
    "model": "gpt-4-turbo",
    "team_id": "team-123",
    "created_at": "2026-02-11T16:00:00Z"
  },
  "metadata": {
    "user_id": "user-456",
    "ip_address": "192.168.1.1",
    "user_agent": "Mozilla/5.0..."
  }
}
```

**Payload Fields:**

- `id`: Unique event ID
- `event`: Event type
- `timestamp`: Event timestamp (ISO 8601)
- `data`: Event-specific data
- `metadata`: Additional context

### Event-Specific Payloads

**Agent Created:**
```json
{
  "id": "evt_123456",
  "event": "agent.created",
  "timestamp": "2026-02-11T16:00:00Z",
  "data": {
    "id": "agent-123",
    "name": "Customer Support Agent",
    "model": "gpt-4-turbo",
    "system_prompt": "You are a helpful assistant.",
    "team_id": "team-123",
    "created_by": "user-456",
    "created_at": "2026-02-11T16:00:00Z"
  }
}
```

**Conversation Completed:**
```json
{
  "id": "evt_123457",
  "event": "conversation.completed",
  "timestamp": "2026-02-11T16:05:00Z",
  "data": {
    "id": "conv-789",
    "agent_id": "agent-123",
    "user_id": "user-456",
    "message_count": 10,
    "duration": 300,
    "status": "completed",
    "completed_at": "2026-02-11T16:05:00Z"
  }
}
```

**Workflow Completed:**
```json
{
  "id": "evt_123458",
  "event": "workflow.completed",
  "timestamp": "2026-02-11T16:10:00Z",
  "data": {
    "id": "wf-exec-456",
    "workflow_id": "wf-123",
    "status": "success",
    "duration": 45,
    "input": {...},
    "output": {...},
    "completed_at": "2026-02-11T16:10:00Z"
  }
}
```

**Document Processed:**
```json
{
  "id": "evt_123459",
  "event": "document.processed",
  "timestamp": "2026-02-11T16:15:00Z",
  "data": {
    "id": "doc-789",
    "kb_id": "kb-123",
    "filename": "manual.pdf",
    "status": "processed",
    "chunk_count": 150,
    "processed_at": "2026-02-11T16:15:00Z"
  }
}
```

## Webhook Configuration

### Create Webhook

**Endpoint:**
```
POST /api/v1/webhooks
```

**Request:**
```json
{
  "url": "https://your-domain.com/webhooks/clouisle",
  "events": [
    "agent.created",
    "conversation.completed",
    "workflow.completed"
  ],
  "secret": "your-webhook-secret",
  "active": true,
  "description": "Production webhook"
}
```

**Response:**
```json
{
  "code": 0,
  "data": {
    "id": "webhook-123",
    "url": "https://your-domain.com/webhooks/clouisle",
    "events": ["agent.created", "conversation.completed", "workflow.completed"],
    "active": true,
    "created_at": "2026-02-11T16:00:00Z"
  },
  "msg": "success"
}
```

### Update Webhook

**Endpoint:**
```
PATCH /api/v1/webhooks/{webhook_id}
```

**Request:**
```json
{
  "events": [
    "agent.created",
    "agent.updated",
    "conversation.completed"
  ],
  "active": true
}
```

### Delete Webhook

**Endpoint:**
```
DELETE /api/v1/webhooks/{webhook_id}
```

### List Webhooks

**Endpoint:**
```
GET /api/v1/webhooks
```

**Response:**
```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "webhook-123",
        "url": "https://your-domain.com/webhooks/clouisle",
        "events": ["agent.created"],
        "active": true,
        "created_at": "2026-02-11T16:00:00Z"
      }
    ],
    "total": 1
  },
  "msg": "success"
}
```

## Security

### Webhook Signatures

Clouisle signs all webhook requests using HMAC-SHA256. Verify signatures to ensure requests are authentic.

**Signature Header:**
```
X-Clouisle-Signature: sha256=abc123...
```

**Signature Calculation:**
```
HMAC-SHA256(webhook_secret, request_body)
```

### Verify Signature (Python)

```python
import hmac
import hashlib

def verify_webhook_signature(payload, signature, secret):
    """Verify webhook signature."""
    expected_signature = hmac.new(
        secret.encode('utf-8'),
        payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    expected = f"sha256={expected_signature}"
    return hmac.compare_digest(expected, signature)

# Usage in Flask
from flask import request, abort

@app.route('/webhooks/clouisle', methods=['POST'])
def handle_webhook():
    signature = request.headers.get('X-Clouisle-Signature')
    payload = request.get_data(as_text=True)

    if not verify_webhook_signature(payload, signature, WEBHOOK_SECRET):
        abort(401, 'Invalid signature')

    event = request.json
    # Process event
    return '', 200
```

### Verify Signature (JavaScript)

```javascript
const crypto = require('crypto');

function verifyWebhookSignature(payload, signature, secret) {
  const expectedSignature = crypto
    .createHmac('sha256', secret)
    .update(payload)
    .digest('hex');

  const expected = `sha256=${expectedSignature}`;
  return crypto.timingSafeEqual(
    Buffer.from(expected),
    Buffer.from(signature)
  );
}

// Usage in Express
app.post('/webhooks/clouisle', express.raw({ type: 'application/json' }), (req, res) => {
  const signature = req.headers['x-clouisle-signature'];
  const payload = req.body.toString();

  if (!verifyWebhookSignature(payload, signature, WEBHOOK_SECRET)) {
    return res.status(401).send('Invalid signature');
  }

  const event = JSON.parse(payload);
  // Process event
  res.status(200).send('OK');
});
```

## Webhook Handlers

### Python Flask Example

```python
from flask import Flask, request, jsonify
import hmac
import hashlib

app = Flask(__name__)
WEBHOOK_SECRET = 'your-webhook-secret'

def verify_signature(payload, signature):
    """Verify webhook signature."""
    expected = hmac.new(
        WEBHOOK_SECRET.encode('utf-8'),
        payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)

@app.route('/webhooks/clouisle', methods=['POST'])
def handle_webhook():
    """Handle Clouisle webhook."""
    # Verify signature
    signature = request.headers.get('X-Clouisle-Signature')
    payload = request.get_data(as_text=True)

    if not verify_signature(payload, signature):
        return jsonify({'error': 'Invalid signature'}), 401

    # Parse event
    event = request.json
    event_type = event['event']
    event_data = event['data']

    # Handle different event types
    if event_type == 'agent.created':
        handle_agent_created(event_data)
    elif event_type == 'conversation.completed':
        handle_conversation_completed(event_data)
    elif event_type == 'workflow.completed':
        handle_workflow_completed(event_data)
    else:
        print(f"Unhandled event type: {event_type}")

    return jsonify({'status': 'success'}), 200

def handle_agent_created(data):
    """Handle agent created event."""
    print(f"Agent created: {data['id']} - {data['name']}")
    # Your logic here

def handle_conversation_completed(data):
    """Handle conversation completed event."""
    print(f"Conversation completed: {data['id']}")
    # Your logic here

def handle_workflow_completed(data):
    """Handle workflow completed event."""
    print(f"Workflow completed: {data['id']}")
    # Your logic here

if __name__ == '__main__':
    app.run(port=5000)
```

### Node.js Express Example

```javascript
const express = require('express');
const crypto = require('crypto');

const app = express();
const WEBHOOK_SECRET = 'your-webhook-secret';

// Use raw body parser for signature verification
app.use('/webhooks/clouisle', express.raw({ type: 'application/json' }));

function verifySignature(payload, signature) {
  const expected = crypto
    .createHmac('sha256', WEBHOOK_SECRET)
    .update(payload)
    .digest('hex');

  return crypto.timingSafeEqual(
    Buffer.from(`sha256=${expected}`),
    Buffer.from(signature)
  );
}

app.post('/webhooks/clouisle', (req, res) => {
  // Verify signature
  const signature = req.headers['x-clouisle-signature'];
  const payload = req.body.toString();

  if (!verifySignature(payload, signature)) {
    return res.status(401).json({ error: 'Invalid signature' });
  }

  // Parse event
  const event = JSON.parse(payload);
  const eventType = event.event;
  const eventData = event.data;

  // Handle different event types
  switch (eventType) {
    case 'agent.created':
      handleAgentCreated(eventData);
      break;
    case 'conversation.completed':
      handleConversationCompleted(eventData);
      break;
    case 'workflow.completed':
      handleWorkflowCompleted(eventData);
      break;
    default:
      console.log(`Unhandled event type: ${eventType}`);
  }

  res.status(200).json({ status: 'success' });
});

function handleAgentCreated(data) {
  console.log(`Agent created: ${data.id} - ${data.name}`);
  // Your logic here
}

function handleConversationCompleted(data) {
  console.log(`Conversation completed: ${data.id}`);
  // Your logic here
}

function handleWorkflowCompleted(data) {
  console.log(`Workflow completed: ${data.id}`);
  // Your logic here
}

app.listen(3000, () => {
  console.log('Webhook server listening on port 3000');
});
```

### Async Processing

```python
from celery import Celery
from flask import Flask, request, jsonify

app = Flask(__name__)
celery = Celery('webhooks', broker='redis://localhost:6379/0')

@app.route('/webhooks/clouisle', methods=['POST'])
def handle_webhook():
    """Handle webhook and queue for async processing."""
    # Verify signature
    signature = request.headers.get('X-Clouisle-Signature')
    payload = request.get_data(as_text=True)

    if not verify_signature(payload, signature):
        return jsonify({'error': 'Invalid signature'}), 401

    # Queue for async processing
    event = request.json
    process_webhook.delay(event)

    return jsonify({'status': 'queued'}), 200

@celery.task
def process_webhook(event):
    """Process webhook asynchronously."""
    event_type = event['event']
    event_data = event['data']

    try:
        if event_type == 'agent.created':
            handle_agent_created(event_data)
        elif event_type == 'conversation.completed':
            handle_conversation_completed(event_data)
        # ... handle other events

    except Exception as e:
        print(f"Error processing webhook: {e}")
        # Optionally retry or log error
```

## Retry Logic

### Webhook Delivery

Clouisle automatically retries failed webhook deliveries:

- **Retry Schedule**: 1m, 5m, 15m, 1h, 6h
- **Max Retries**: 5 attempts
- **Success Criteria**: HTTP 2xx response
- **Timeout**: 30 seconds per request

### Idempotency

Handle duplicate webhook deliveries using event IDs:

```python
# Store processed event IDs
processed_events = set()

@app.route('/webhooks/clouisle', methods=['POST'])
def handle_webhook():
    event = request.json
    event_id = event['id']

    # Check if already processed
    if event_id in processed_events:
        return jsonify({'status': 'already_processed'}), 200

    # Process event
    process_event(event)

    # Mark as processed
    processed_events.add(event_id)

    return jsonify({'status': 'success'}), 200
```

### Database-Based Idempotency

```python
from sqlalchemy import create_engine, Column, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

Base = declarative_base()

class ProcessedEvent(Base):
    __tablename__ = 'processed_events'
    event_id = Column(String, primary_key=True)
    processed_at = Column(DateTime, default=datetime.utcnow)

engine = create_engine('postgresql://...')
Session = sessionmaker(bind=engine)

@app.route('/webhooks/clouisle', methods=['POST'])
def handle_webhook():
    event = request.json
    event_id = event['id']

    session = Session()

    # Check if already processed
    existing = session.query(ProcessedEvent).filter_by(event_id=event_id).first()
    if existing:
        session.close()
        return jsonify({'status': 'already_processed'}), 200

    # Process event
    try:
        process_event(event)

        # Mark as processed
        session.add(ProcessedEvent(event_id=event_id))
        session.commit()

        return jsonify({'status': 'success'}), 200

    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()
```

## Testing Webhooks

### Test Webhook Endpoint

**Endpoint:**
```
POST /api/v1/webhooks/{webhook_id}/test
```

**Request:**
```json
{
  "event": "agent.created"
}
```

**Response:**
```json
{
  "code": 0,
  "data": {
    "status": "success",
    "response_code": 200,
    "response_time": 150
  },
  "msg": "success"
}
```

### Local Testing with ngrok

```bash
# Install ngrok
brew install ngrok

# Start your local server
python webhook_server.py

# Expose local server
ngrok http 5000

# Use ngrok URL in webhook configuration
# https://abc123.ngrok.io/webhooks/clouisle
```

### Mock Webhook Events

```python
import requests

def send_test_webhook(url, secret):
    """Send test webhook event."""
    payload = {
        "id": "evt_test_123",
        "event": "agent.created",
        "timestamp": "2026-02-11T16:00:00Z",
        "data": {
            "id": "agent-test-123",
            "name": "Test Agent",
            "model": "gpt-4-turbo"
        }
    }

    # Calculate signature
    import hmac
    import hashlib
    import json

    payload_str = json.dumps(payload)
    signature = hmac.new(
        secret.encode('utf-8'),
        payload_str.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    # Send request
    response = requests.post(
        url,
        json=payload,
        headers={
            'X-Clouisle-Signature': f'sha256={signature}',
            'Content-Type': 'application/json'
        }
    )

    return response

# Usage
response = send_test_webhook(
    'http://localhost:5000/webhooks/clouisle',
    'your-webhook-secret'
)
print(f"Status: {response.status_code}")
```

## Monitoring

### Webhook Logs

**Endpoint:**
```
GET /api/v1/webhooks/{webhook_id}/logs
```

**Response:**
```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "log-123",
        "event_id": "evt_123456",
        "event": "agent.created",
        "status": "success",
        "response_code": 200,
        "response_time": 150,
        "attempt": 1,
        "created_at": "2026-02-11T16:00:00Z"
      }
    ],
    "total": 100
  },
  "msg": "success"
}
```

### Webhook Statistics

**Endpoint:**
```
GET /api/v1/webhooks/{webhook_id}/stats
```

**Response:**
```json
{
  "code": 0,
  "data": {
    "total_deliveries": 1000,
    "successful_deliveries": 980,
    "failed_deliveries": 20,
    "success_rate": 98.0,
    "avg_response_time": 150,
    "last_delivery": "2026-02-11T16:00:00Z"
  },
  "msg": "success"
}
```

## Best Practices

### Webhook Handlers

**✅ Do:**
- Verify webhook signatures
- Respond quickly (< 5 seconds)
- Process events asynchronously
- Handle duplicate events (idempotency)
- Log all webhook events
- Return 2xx for success
- Implement retry logic
- Monitor webhook health

**❌ Don't:**
- Skip signature verification
- Block on long operations
- Process synchronously
- Ignore duplicate events
- Skip logging
- Return non-2xx for success
- Give up on first failure
- Ignore monitoring

### Security

**✅ Do:**
- Use HTTPS for webhook URLs
- Verify signatures on every request
- Use strong webhook secrets
- Rotate secrets periodically
- Validate event data
- Rate limit webhook endpoints
- Log security events

**❌ Don't:**
- Use HTTP URLs
- Skip signature verification
- Use weak secrets
- Never rotate secrets
- Trust event data blindly
- Allow unlimited requests
- Skip security logging

### Performance

**✅ Do:**
- Process events asynchronously
- Use message queues
- Implement connection pooling
- Cache frequently accessed data
- Monitor response times
- Scale horizontally
- Use database indexes

**❌ Don't:**
- Process synchronously
- Block on I/O operations
- Create new connections per request
- Query database repeatedly
- Ignore performance metrics
- Run single instance only
- Skip database optimization

## Troubleshooting

### Webhook Not Received

**Problem:** Webhook events not arriving

**Solutions:**
1. Check webhook is active
2. Verify URL is accessible
3. Check firewall rules
4. Review webhook logs
5. Test with ngrok

### Signature Verification Failed

**Problem:** Signature validation fails

**Solutions:**
1. Check webhook secret is correct
2. Verify signature calculation
3. Use raw request body
4. Check header name
5. Review signature format

### Duplicate Events

**Problem:** Receiving duplicate webhook events

**Solutions:**
1. Implement idempotency using event IDs
2. Store processed event IDs
3. Use database transactions
4. Check retry logic
5. Review webhook logs

### Slow Processing

**Problem:** Webhook processing is slow

**Solutions:**
1. Process asynchronously
2. Use message queues
3. Optimize database queries
4. Add caching
5. Scale horizontally

## Related Documentation

- [API Reference](./endpoints/) - API endpoints
- [Error Handling](./error-handling.md) - Error handling
- [Security](../best-practices/security.md) - Security best practices
- [Monitoring](../operations/monitoring.md) - Monitoring guide

---

**Last Updated**: 2026-02-11
