# Workflow Versions & Templates API

This document describes the API endpoints for workflow version control (history, diff, rollback, branching) and workflow template marketplace operations.

---

## 1. Workflow Version Management

**Base URL**: `/api/v1/workflow-versions`

### Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/workflow-versions` | Create a snapshot version of a workflow |
| `GET` | `/api/v1/workflow-versions/{workflow_id}/history` | List all historical versions of a workflow |
| `GET` | `/api/v1/workflow-versions/{workflow_id}/version/{version_id}` | Get detailed configuration of a specific version |
| `GET` | `/api/v1/workflow-versions/{workflow_id}/diff` | Compare graph and configuration differences between two versions |
| `POST` | `/api/v1/workflow-versions/{workflow_id}/rollback` | Roll back workflow graph to a previous version snapshot |
| `POST` | `/api/v1/workflow-versions/{workflow_id}/fork` | Fork a specific version into a new independent workflow |
| `GET` | `/api/v1/workflow-versions/{workflow_id}/stats` | Get version count and publishing statistics |

---

### Compare Versions (Diff)

```http
GET /api/v1/workflow-versions/{workflow_id}/diff?from_version_id=v1-uuid&to_version_id=v2-uuid HTTP/1.1
Authorization: Bearer <token>
```

#### Response (`200 OK`)

```json
{
  "code": 0,
  "data": {
    "workflow_id": "wf-uuid-1234",
    "from_version": "1.0.0",
    "to_version": "1.1.0",
    "added_nodes": ["node_llm_summarize"],
    "removed_nodes": [],
    "modified_nodes": [
      {
        "node_id": "node_http_query",
        "field_changes": {"timeout": {"before": 30, "after": 60}}
      }
    ],
    "added_edges": [{"from": "node_start", "to": "node_llm_summarize"}],
    "removed_edges": []
  },
  "msg": "success"
}
```

---

### Rollback to Version

```http
POST /api/v1/workflow-versions/{workflow_id}/rollback HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "target_version_id": "v1-uuid",
  "create_backup": true
}
```

---

## 2. Workflow Template Marketplace

**Base URL**: `/api/v1/workflow-templates`

### Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/workflow-templates` | List published workflow templates (optional category filter) |
| `GET` | `/api/v1/workflow-templates/featured` | List featured workflow templates |
| `GET` | `/api/v1/workflow-templates/search` | Search templates by keyword |
| `GET` | `/api/v1/workflow-templates/categories` | List available template categories |
| `GET` | `/api/v1/workflow-templates/{template_id}` | Get full template details and structure |
| `POST` | `/api/v1/workflow-templates` | Publish a workflow as a reusable template |
| `POST` | `/api/v1/workflow-templates/{template_id}/instantiate` | Create a new runnable workflow instance from a template |
| `POST` | `/api/v1/workflow-templates/{template_id}/rate` | Rate and review a template |
| `DELETE` | `/api/v1/workflow-templates/{template_id}` | Delete a template |

---

### Instantiate Template

```http
POST /api/v1/workflow-templates/{template_id}/instantiate HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "My Ingest Pipeline",
  "team_id": "team-uuid-1234",
  "description": "Created from Document Ingest & RAG template"
}
```

#### Response (`200 OK`)

```json
{
  "code": 0,
  "data": {
    "workflow_id": "new-wf-uuid",
    "name": "My Ingest Pipeline",
    "status": "draft"
  },
  "msg": "Workflow instantiated successfully"
}
```
