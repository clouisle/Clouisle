# Workflows API

This document describes the API endpoints for managing and executing workflows.

## Overview

The Workflows API allows you to:

- **List workflows**: Get all available workflows
- **Get workflow details**: Retrieve workflow information
- **Create workflows**: Create new workflows (admin only)
- **Update workflows**: Modify workflow configuration (admin only)
- **Delete workflows**: Remove workflows (admin only)
- **Execute workflows**: Run workflows with inputs
- **Get execution status**: Check workflow run status
- **List executions**: View workflow execution history

**Base URL**: `/api/v1/workflows`

## Authentication

All endpoints require authentication via JWT token or API key.

**Required scopes:**
- `workflow:read` - List and view workflows
- `workflow:create` - Create workflows
- `workflow:update` - Update workflows
- `workflow:delete` - Delete workflows
- `workflow:run` - Execute workflows

## List Workflows

Get a list of all workflows you have access to.

### Endpoint

```
GET /api/v1/workflows
```

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `page` | integer | No | 1 | Page number |
| `page_size` | integer | No | 20 | Items per page (max: 100) |
| `team_id` | string | No | - | Filter by team ID |
| `status` | string | No | - | Filter by status: `draft`, `published` |
| `search` | string | No | - | Search by name or description |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/workflows?page=1&page_size=20" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "Document Summarizer",
        "description": "Summarizes documents automatically",
        "status": "published",
        "team_id": "team-123",
        "team_name": "Content Team",
        "version": 2,
        "nodes": 6,
        "triggers": ["manual", "webhook"],
        "created_at": "2026-02-11T10:00:00Z",
        "updated_at": "2026-02-11T15:30:00Z",
        "created_by": "user-001",
        "stats": {
          "total_runs": 156,
          "success_rate": 0.942,
          "avg_duration": 83
        }
      }
    ],
    "total": 42,
    "page": 1,
    "page_size": 20,
    "total_pages": 3
  },
  "msg": "success"
}
```

## Get Workflow

Get details of a specific workflow.

### Endpoint

```
GET /api/v1/workflows/{workflow_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `workflow_id` | string | Yes | Workflow UUID |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/workflows/550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Document Summarizer",
    "description": "Summarizes documents automatically",
    "status": "published",
    "team_id": "team-123",
    "team_name": "Content Team",
    "version": 2,
    "definition": {
      "nodes": [
        {
          "id": "node-1",
          "type": "start",
          "position": {"x": 100, "y": 100}
        },
        {
          "id": "node-2",
          "type": "http_request",
          "config": {
            "url": "{{input.document_url}}",
            "method": "GET"
          },
          "position": {"x": 300, "y": 100}
        }
      ],
      "edges": [
        {
          "id": "edge-1",
          "source": "node-1",
          "target": "node-2"
        }
      ]
    },
    "input_schema": {
      "type": "object",
      "properties": {
        "document_url": {
          "type": "string",
          "description": "URL of document to summarize"
        },
        "summary_length": {
          "type": "string",
          "enum": ["short", "medium", "long"],
          "default": "medium"
        }
      },
      "required": ["document_url"]
    },
    "triggers": ["manual", "webhook"],
    "webhook_url": "https://your-domain.com/api/v1/workflows/550e8400.../webhook",
    "created_at": "2026-02-11T10:00:00Z",
    "updated_at": "2026-02-11T15:30:00Z",
    "created_by": "user-001",
    "stats": {
      "total_runs": 156,
      "success_rate": 0.942,
      "avg_duration": 83,
      "last_run": "2026-02-11T14:30:00Z"
    }
  },
  "msg": "success"
}
```

## Create Workflow

Create a new workflow.

### Endpoint

```
POST /api/v1/workflows
```

### Request Body

```json
{
  "name": "Document Summarizer",
  "description": "Summarizes documents automatically",
  "team_id": "team-123",
  "definition": {
    "nodes": [
      {
        "id": "node-1",
        "type": "start",
        "position": {"x": 100, "y": 100}
      },
      {
        "id": "node-2",
        "type": "http_request",
        "config": {
          "url": "{{input.document_url}}",
          "method": "GET"
        },
        "position": {"x": 300, "y": 100}
      },
      {
        "id": "node-3",
        "type": "llm",
        "config": {
          "model_id": "model-456",
          "prompt": "Summarize this document: {{node-2.output.text}}"
        },
        "position": {"x": 500, "y": 100}
      },
      {
        "id": "node-4",
        "type": "end",
        "position": {"x": 700, "y": 100}
      }
    ],
    "edges": [
      {"source": "node-1", "target": "node-2"},
      {"source": "node-2", "target": "node-3"},
      {"source": "node-3", "target": "node-4"}
    ]
  },
  "input_schema": {
    "type": "object",
    "properties": {
      "document_url": {
        "type": "string",
        "description": "URL of document to summarize"
      }
    },
    "required": ["document_url"]
  },
  "triggers": ["manual", "webhook"]
}
```

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/workflows" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Document Summarizer",
    "description": "Summarizes documents automatically",
    "team_id": "team-123",
    "definition": {...},
    "input_schema": {...}
  }'
```

### Response

**Success (201 Created):**

```json
{
  "code": 0,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Document Summarizer",
    "status": "draft",
    "version": 1,
    "created_at": "2026-02-11T10:00:00Z"
  },
  "msg": "Workflow created successfully"
}
```

## Update Workflow

Update an existing workflow.

### Endpoint

```
PATCH /api/v1/workflows/{workflow_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `workflow_id` | string | Yes | Workflow UUID |

### Request Body

All fields are optional. Only include fields you want to update.

```json
{
  "name": "Updated Workflow Name",
  "description": "Updated description",
  "definition": {...},
  "input_schema": {...}
}
```

### Request Example

```bash
curl -X PATCH "https://your-domain.com/api/v1/workflows/550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Updated Workflow Name",
    "description": "Updated description"
  }'
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Updated Workflow Name",
    "version": 3,
    "updated_at": "2026-02-11T16:00:00Z"
  },
  "msg": "Workflow updated successfully"
}
```

## Delete Workflow

Delete a workflow permanently.

### Endpoint

```
DELETE /api/v1/workflows/{workflow_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `workflow_id` | string | Yes | Workflow UUID |

### Request Example

```bash
curl -X DELETE "https://your-domain.com/api/v1/workflows/550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": null,
  "msg": "Workflow deleted successfully"
}
```

## Execute Workflow

Run a workflow with input parameters.

### Endpoint

```
POST /api/v1/workflows/{workflow_id}/run
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `workflow_id` | string | Yes | Workflow UUID |

### Request Body

```json
{
  "inputs": {
    "document_url": "https://example.com/document.pdf",
    "summary_length": "short"
  },
  "async": false,
  "webhook_url": "https://your-app.com/webhook"
}
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `inputs` | object | Yes | Input variables for workflow |
| `async` | boolean | No | Run asynchronously (default: false) |
| `webhook_url` | string | No | Callback URL for async execution |

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/workflows/550e8400-e29b-41d4-a716-446655440000/run" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": {
      "document_url": "https://example.com/document.pdf",
      "summary_length": "short"
    }
  }'
```

### Response (Synchronous)

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "run_id": "run-789",
    "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "completed",
    "started_at": "2026-02-11T14:30:00Z",
    "completed_at": "2026-02-11T14:31:23Z",
    "duration": 83,
    "output": {
      "summary": "The document discusses...",
      "word_count": 1234,
      "key_points": ["Point 1", "Point 2", "Point 3"]
    },
    "nodes_executed": 6,
    "nodes_total": 6
  },
  "msg": "Workflow executed successfully"
}
```

### Response (Asynchronous)

**Success (202 Accepted):**

```json
{
  "code": 0,
  "data": {
    "run_id": "run-789",
    "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "running",
    "started_at": "2026-02-11T14:30:00Z",
    "status_url": "/api/v1/workflows/550e8400.../runs/run-789"
  },
  "msg": "Workflow execution started"
}
```

## Get Execution Status

Check the status of a workflow execution.

### Endpoint

```
GET /api/v1/workflows/{workflow_id}/runs/{run_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `workflow_id` | string | Yes | Workflow UUID |
| `run_id` | string | Yes | Run UUID |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/workflows/550e8400-e29b-41d4-a716-446655440000/runs/run-789" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "run_id": "run-789",
    "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "completed",
    "started_at": "2026-02-11T14:30:00Z",
    "completed_at": "2026-02-11T14:31:23Z",
    "duration": 83,
    "triggered_by": "user-001",
    "trigger_type": "manual",
    "inputs": {
      "document_url": "https://example.com/document.pdf",
      "summary_length": "short"
    },
    "output": {
      "summary": "The document discusses...",
      "word_count": 1234,
      "key_points": ["Point 1", "Point 2", "Point 3"]
    },
    "nodes_executed": 6,
    "nodes_total": 6,
    "execution_log": [
      {
        "node_id": "node-1",
        "node_type": "start",
        "status": "completed",
        "started_at": "2026-02-11T14:30:00Z",
        "completed_at": "2026-02-11T14:30:01Z",
        "duration": 1
      },
      {
        "node_id": "node-2",
        "node_type": "http_request",
        "status": "completed",
        "started_at": "2026-02-11T14:30:01Z",
        "completed_at": "2026-02-11T14:30:46Z",
        "duration": 45,
        "output": {
          "text": "Document content..."
        }
      }
    ]
  },
  "msg": "success"
}
```

## List Executions

Get execution history for a workflow.

### Endpoint

```
GET /api/v1/workflows/{workflow_id}/runs
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `workflow_id` | string | Yes | Workflow UUID |

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `page` | integer | No | 1 | Page number |
| `page_size` | integer | No | 20 | Items per page (max: 100) |
| `status` | string | No | - | Filter by status: `running`, `completed`, `failed` |
| `start_date` | string | No | - | Filter by start date (ISO 8601) |
| `end_date` | string | No | - | Filter by end date (ISO 8601) |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/workflows/550e8400-e29b-41d4-a716-446655440000/runs?page=1&page_size=20&status=completed" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "run_id": "run-789",
        "status": "completed",
        "started_at": "2026-02-11T14:30:00Z",
        "completed_at": "2026-02-11T14:31:23Z",
        "duration": 83,
        "triggered_by": "user-001",
        "trigger_type": "manual",
        "success": true
      },
      {
        "run_id": "run-788",
        "status": "failed",
        "started_at": "2026-02-11T10:15:00Z",
        "completed_at": "2026-02-11T10:15:45Z",
        "duration": 45,
        "triggered_by": "webhook",
        "trigger_type": "webhook",
        "success": false,
        "error": "API call timeout"
      }
    ],
    "total": 156,
    "page": 1,
    "page_size": 20,
    "total_pages": 8
  },
  "msg": "success"
}
```

## Stop Execution

Stop a running workflow execution.

### Endpoint

```
POST /api/v1/workflows/{workflow_id}/runs/{run_id}/stop
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `workflow_id` | string | Yes | Workflow UUID |
| `run_id` | string | Yes | Run UUID |

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/workflows/550e8400-e29b-41d4-a716-446655440000/runs/run-789/stop" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "run_id": "run-789",
    "status": "stopped",
    "stopped_at": "2026-02-11T14:30:45Z"
  },
  "msg": "Workflow execution stopped"
}
```

## Webhook Trigger

Trigger a workflow via webhook.

### Endpoint

```
POST /api/v1/workflows/{workflow_id}/webhook
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `workflow_id` | string | Yes | Workflow UUID |

### Authentication

Use webhook token in header:

```
Authorization: Bearer {webhook_token}
```

Or use API key with `workflow:run` scope.

### Request Body

```json
{
  "document_url": "https://example.com/document.pdf",
  "summary_length": "short"
}
```

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/workflows/550e8400-e29b-41d4-a716-446655440000/webhook" \
  -H "Authorization: Bearer WEBHOOK_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "document_url": "https://example.com/document.pdf",
    "summary_length": "short"
  }'
```

### Response

**Success (202 Accepted):**

```json
{
  "code": 0,
  "data": {
    "run_id": "run-789",
    "status": "running"
  },
  "msg": "Workflow execution started"
}
```

## Get Workflow Statistics

Get usage statistics for a workflow.

### Endpoint

```
GET /api/v1/workflows/{workflow_id}/stats
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `workflow_id` | string | Yes | Workflow UUID |

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `start_date` | string | No | 30 days ago | Start date (ISO 8601) |
| `end_date` | string | No | Now | End date (ISO 8601) |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/workflows/550e8400-e29b-41d4-a716-446655440000/stats?start_date=2026-01-01T00:00:00Z" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "total_runs": 156,
    "successful_runs": 147,
    "failed_runs": 9,
    "success_rate": 0.942,
    "avg_duration": 83,
    "total_duration": 12948,
    "daily_stats": [
      {
        "date": "2026-02-11",
        "runs": 12,
        "successful": 11,
        "failed": 1,
        "avg_duration": 85
      }
    ]
  },
  "msg": "success"
}
```

## Error Codes

| Code | Message | Description |
|------|---------|-------------|
| `4000` | Workflow not found | Workflow does not exist |
| `4000` | Run not found | Execution does not exist |
| `3000` | Permission denied | Insufficient permissions |
| `1001` | Validation failed | Invalid request data |
| `5100` | Name already exists | Workflow name is taken |

## Rate Limits

| Endpoint | Limit |
|----------|-------|
| `GET /api/v1/workflows` | 100/minute |
| `GET /api/v1/workflows/{id}` | 100/minute |
| `POST /api/v1/workflows` | 10/minute |
| `PATCH /api/v1/workflows/{id}` | 30/minute |
| `DELETE /api/v1/workflows/{id}` | 10/minute |
| `POST /api/v1/workflows/{id}/run` | 30/minute |
| `POST /api/v1/workflows/{id}/webhook` | 60/minute |

## Related Documentation

- [API Overview](../overview.md) - API introduction
- [Authentication](../authentication.md) - Authentication methods
- [Rate Limiting](../rate-limiting.md) - Rate limit details
- [Agents API](./agents.md) - Agents endpoints
- [Workflow Concepts](../../concepts/workflows.md) - Understanding workflows

---

**Last Updated**: 2026-02-11
