# Workflows API

This document describes the API endpoints for managing and executing workflows.

## Overview

The Workflows API allows you to:

- **List workflows**: Get all available workflows
- **Get workflow details**: Retrieve workflow information
- **Create workflows**: Create new workflows
- **Update workflows**: Modify workflow configuration
- **Delete workflows**: Remove workflows
- **Execute workflows**: Run workflows with inputs
- **Get execution status**: Check workflow run status
- **List executions**: View workflow execution history

**Base URL**: `/api/v1/workflows`

## Authentication

Workflow management and user-initiated run/status routes require an authenticated JWT user session; API-key authentication is not accepted by those routes. The webhook trigger is the exception: `POST /api/v1/workflows/webhook/{webhook_token}` requires a `clou_` API key in its `Authorization` header.

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
| `page_size` | integer | No | 20 | Items per page |
| `team_id` | string | No | - | Filter by team ID |
| `status` | string | No | - | Filter by status: `draft`, `published`, `archived` |
| `trigger_type` | string | No | - | Filter by trigger type: `manual`, `cron`, `webhook` |
| `visibility` | string | No | - | Filter by visibility: `private`, `team`, `public` |
| `keyword` | string | No | - | Search by name or description |
| `own_only` | boolean | No | false | Only show workflows created by the current user |

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
        "icon": "📄",
        "status": "published",
        "visibility": "team",
        "trigger_type": "manual",
        "run_count": 156,
        "success_count": 147,
        "fail_count": 9,
        "created_by_id": "user-001",
        "created_by_name": "alice",
        "created_at": "2026-02-11T10:00:00Z",
        "updated_at": "2026-02-11T15:30:00Z"
      }
    ],
    "total": 42,
    "page": 1,
    "page_size": 20
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
    "team_id": "team-123",
    "name": "Document Summarizer",
    "description": "Summarizes documents automatically",
    "icon": "📄",
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
    "variables": [],
    "status": "published",
    "visibility": "team",
    "version": 2,
    "trigger_type": "manual",
    "trigger_config": {},
    "webhook_token": "wh_abc123...",
    "embed_config": {},
    "run_page_config": {
      "presentation_mode": "simple"
    },
    "run_count": 156,
    "success_count": 147,
    "fail_count": 9,
    "created_by_id": "user-001",
    "created_at": "2026-02-11T10:00:00Z",
    "updated_at": "2026-02-11T15:30:00Z"
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
  "team_id": "team-123",
  "name": "Document Summarizer",
  "description": "Summarizes documents automatically",
  "icon": "📄",
  "visibility": "private"
}
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `team_id` | string | Yes | Team UUID |
| `name` | string | Yes | Workflow name (max 100 chars) |
| `description` | string | No | Workflow description |
| `icon` | string | No | Icon |
| `visibility` | string | No | `private`, `team`, or `public` (default: `private`) |

**Note:** The workflow definition and variables are added later via `PUT /api/v1/workflows/{workflow_id}` and the versions endpoints.

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/workflows" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "team_id": "team-123",
    "name": "Document Summarizer",
    "description": "Summarizes documents automatically",
    "visibility": "private"
  }'
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "team_id": "team-123",
    "name": "Document Summarizer",
    "description": "Summarizes documents automatically",
    "icon": null,
    "definition": {
      "nodes": [{"id": "user_input-1", "type": "user_input"}],
      "edges": [],
      "viewport": {"x": 0, "y": 0, "zoom": 1}
    },
    "variables": [],
    "status": "draft",
    "visibility": "private",
    "version": 1,
    "trigger_type": "manual",
    "trigger_config": {},
    "webhook_token": null,
    "embed_config": {},
    "run_page_config": {
      "presentation_mode": "simple"
    },
    "run_count": 0,
    "success_count": 0,
    "fail_count": 0,
    "created_by_id": "user-001",
    "created_at": "2026-02-11T10:00:00Z",
    "updated_at": "2026-02-11T10:00:00Z"
  },
  "msg": "Workflow created successfully"
}
```

## Update Workflow

Update an existing workflow.

### Endpoint

```
PUT /api/v1/workflows/{workflow_id}
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
  "icon": "📄",
  "definition": {},
  "variables": [],
  "trigger_type": "manual",
  "trigger_config": {},
  "visibility": "team",
  "embed_config": {},
  "run_page_config": {
    "presentation_mode": "simple"
  }
}
```

### Request Example

```bash
curl -X PUT "https://your-domain.com/api/v1/workflows/550e8400-e29b-41d4-a716-446655440000" \
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
    "description": "Updated description",
    "status": "draft",
    "visibility": "private",
    "version": 2,
    "trigger_type": "manual",
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
  }
}
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `inputs` | object | No | Input variables for the workflow (default: `{}`) |

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

### Response

Execution is always asynchronous: the run is submitted to Celery and the endpoint returns immediately with the run ID and stream URL. The workflow must be published (`status: published`) before it can be run.

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "run_id": "run-789",
    "stream_url": "/api/v1/workflows/runs/run-789/stream"
  },
  "msg": "Workflow execution started"
}
```

Progress is available via `GET /api/v1/workflows/runs/{run_id}/stream` (SSE, optional `from_sequence` query parameter) and `GET /api/v1/workflows/runs/{run_id}`. The SSE stream requires an authenticated user with access to the workflow; a webhook token or stream URL is not a public authorization mechanism.

## Get Execution Status

Check the status of a workflow run.

### Endpoint

```
GET /api/v1/workflows/runs/{run_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `run_id` | string | Yes | Run UUID |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/workflows/runs/run-789" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "run-789",
    "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
    "trigger_type": "manual",
    "triggered_by_id": "user-001",
    "is_debug": false,
    "status": "success",
    "inputs": {
      "document_url": "https://example.com/document.pdf",
      "summary_length": "short"
    },
    "outputs": {
      "summary": "The document discusses...",
      "word_count": 1234,
      "key_points": ["Point 1", "Point 2", "Point 3"]
    },
    "parent_run_id": null,
    "root_run_id": "run-789",
    "depth": 0,
    "created_at": "2026-02-11T14:30:00Z",
    "started_at": "2026-02-11T14:30:00Z",
    "finished_at": "2026-02-11T14:31:23Z",
    "total_nodes": 6,
    "executed_nodes": 6,
    "failed_nodes": 0,
    "skipped_nodes": 0,
    "total_duration_ms": 83000,
    "total_token_usage": {},
    "error_message": null,
    "error_node_id": null
  },
  "msg": "success"
}
```

**Note:** A user's own published-workflow runs can also be retrieved via `GET /api/v1/workflows/{workflow_id}/runs/mine/{run_id}` (requires `workflow:run`). Node-level execution detail is available at `GET /api/v1/workflows/runs/{run_id}/nodes`.

**Run status values:** `pending`, `running`, `success`, `waiting`, `failed`, `cancelled`, `timeout`.

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
| `page_size` | integer | No | 20 | Items per page (maximum 100) |
| `status` | string | No | - | Filter by status: `pending`, `running`, `success`, `waiting`, `failed`, `cancelled`, `timeout` |
| `is_debug` | boolean | No | - | Filter by debug runs |
| `search` | string | No | - | Search runs |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/workflows/550e8400-e29b-41d4-a716-446655440000/runs?page=1&page_size=20&status=success" \
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
        "id": "run-789",
        "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
        "trigger_type": "manual",
        "triggered_by_id": "user-001",
        "is_debug": false,
        "status": "success",
        "inputs": {},
        "outputs": {},
        "parent_run_id": null,
        "root_run_id": "run-789",
        "depth": 0,
        "created_at": "2026-02-11T14:30:00Z",
        "started_at": "2026-02-11T14:30:00Z",
        "finished_at": "2026-02-11T14:31:23Z",
        "total_nodes": 6,
        "executed_nodes": 6,
        "failed_nodes": 0,
        "skipped_nodes": 0,
        "total_duration_ms": 83000,
        "total_token_usage": {},
        "error_message": null,
        "error_node_id": null,
        "execution_duration_ms": 83000,
        "config_snapshot": null,
        "model_used": null
      }
    ],
    "total": 156,
    "page": 1,
    "page_size": 20
  },
  "msg": "success"
}
```

## Cancel Execution

Cancel a running workflow execution.

### Endpoint

```
POST /api/v1/workflows/runs/{run_id}/cancel
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `run_id` | string | Yes | Run UUID |

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/workflows/runs/run-789/cancel" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "run_id": "run-789",
    "status": "cancelled"
  },
  "msg": "Workflow execution cancelled"
}
```

## Webhook Trigger

Trigger a workflow via webhook. The webhook token is in the URL path, and the request must additionally authenticate with an API key via the `Authorization` header (`Bearer clou_...`). The workflow must be published and its trigger type must be `webhook`. The API key must be allowed to access the workflow. The token and stream URL are not public/no-auth access; workflow access is still enforced.

### Endpoint

```
POST /api/v1/workflows/webhook/{webhook_token}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `webhook_token` | string | Yes | The workflow's webhook token |

### Authentication

```
Authorization: Bearer {api_key}
```

where `{api_key}` is an API key starting with `clou_`. The workflow's webhook token itself is not an authentication credential; the API key authenticates the caller, and the token selects the workflow.

### Request Body

Raw JSON object of workflow inputs:

```json
{
  "document_url": "https://example.com/document.pdf",
  "summary_length": "short"
}
```

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/workflows/webhook/wh_abc123" \
  -H "Authorization: Bearer clou_xxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "document_url": "https://example.com/document.pdf",
    "summary_length": "short"
  }'
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "run_id": "run-789",
    "status": "pending",
    "stream_url": "/api/v1/workflows/runs/run-789/stream"
  },
  "msg": "Workflow execution started"
}
```

**Note:** A new webhook token can be generated with `POST /api/v1/workflows/{workflow_id}/regenerate-webhook-token`.

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

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/workflows/550e8400-e29b-41d4-a716-446655440000/stats" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "total_runs": 156,
    "success_count": 147,
    "failed_count": 9,
    "timeout_count": 0,
    "avg_duration_ms": 83000,
    "last_run_at": "2026-02-11T14:30:00Z"
  },
  "msg": "success"
}
```

A trends endpoint is also available: `GET /api/v1/workflows/{workflow_id}/stats/trends?period=7d` (period: `7d`, `30d`).

## Error Codes

| Code | Message | Description |
|------|---------|-------------|
| `4000` | Not found | Workflow or run does not exist |
| `1004` | Forbidden | Workflow not published / webhook trigger disabled / invalid webhook token |
| `3000` | Permission denied | Insufficient permissions |
| `1001` | Validation failed | Invalid request data |
| `5104` | Duplicate name | Workflow name is taken |

> **Note:** No per-endpoint rate limits are implemented. There is no rate-limit middleware on these endpoints.

## Related Documentation

- [API Overview](../overview.md) - API introduction
- [Authentication](../authentication.md) - Authentication methods
- [Rate Limiting](../rate-limiting.md) - Rate limit details
- [Agents API](./agents.md) - Agents endpoints
- [Workflow User Guide](../../user-guide/workflows/workflow-builder.md) - Building workflows

---

**Last Updated**: 2026-02-11
