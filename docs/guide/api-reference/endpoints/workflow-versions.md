# Workflow Versions API

This document describes the API endpoints for workflow version control (history, diff, publish, archive, rollback, branching).

---

## 1. Workflow Version Management

**Base URL**: `/api/v1/workflow-versions`

### Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/workflow-versions` | Create a snapshot version of a workflow |
| `GET` | `/api/v1/workflow-versions/{workflow_id}/history` | List all historical versions of a workflow |
| `GET` | `/api/v1/workflow-versions/{workflow_id}/version/{version_id}` | Get detailed configuration of a specific version |
| `POST` | `/api/v1/workflow-versions/{workflow_id}/version/{version_id}/publish` | Publish a version (requires the `workflow:publish` permission) |
| `POST` | `/api/v1/workflow-versions/{workflow_id}/version/{version_id}/archive` | Archive a version |
| `GET` | `/api/v1/workflow-versions/{workflow_id}/diff` | Compare graph and configuration differences between two versions |
| `POST` | `/api/v1/workflow-versions/{workflow_id}/rollback` | Roll back workflow graph to a previous version snapshot |
| `POST` | `/api/v1/workflow-versions/{workflow_id}/fork` | Fork a specific version into a new independent workflow |
| `GET` | `/api/v1/workflow-versions/{workflow_id}/stats` | Get version count and publishing statistics |

**Query parameters**: `GET .../history` accepts `limit` (1–100, default `20`), `offset` (default `0`), and `status` (`draft`, `published`, `archived`, or `deprecated`). `GET .../diff` requires `from_version` and `to_version` (both version IDs).

**Response format**: unlike most Clouisle endpoints, the routes in this module return their payload directly — there is no `{ code, data, msg }` envelope on success. Errors still use the standard envelope.

> **Warning:** This module is backed by an **in-process, in-memory** version store (`WorkflowVersionManager._versions` in `backend/app/services/workflow/versioning.py`) — versions are not written to PostgreSQL and are lost on process restart, and each API worker holds its own copy. It is a separate store from the workflow's DB-level version history (`GET /api/v1/workflows/{workflow_id}/versions`, which is what the editor's version panel reads). Use the DB-backed routes for production history and treat these endpoints as a preview surface.

---

### Compare Versions (Diff)

`from_version` and `to_version` are required query parameters and are version IDs (not semantic version names).

```http
GET /api/v1/workflow-versions/{workflow_id}/diff?from_version=v1-uuid&to_version=v2-uuid HTTP/1.1
Authorization: Bearer <token>
```

#### Response (`200 OK`)

The payload is returned directly (no `code`/`data`/`msg` envelope):

```json
{
  "from_version": "v1-uuid",
  "to_version": "v2-uuid",
  "diff": {
    "from_version": "v1-uuid",
    "to_version": "v2-uuid",
    "nodes_added": [
      {"id": "node_llm_summarize", "type": "llm", "label": "Summarize"}
    ],
    "nodes_removed": [],
    "nodes_modified": [
      {
        "id": "node_http_query",
        "type": "http",
        "changes": [
          {"field": "data.timeout", "from": 30, "to": 60},
          {"field": "position", "type": "moved"}
        ]
      }
    ],
    "edges_added": [
      {"source": "node_start", "target": "node_llm_summarize", "sourceHandle": null}
    ],
    "edges_removed": [],
    "config_changes": {},
    "has_changes": true,
    "change_summary": "+1 nodes, ~1 nodes modified, +1 edges"
  }
}
```

---

### Publish a Version

Requires the `workflow:publish` team permission in addition to write access to the workflow.

```http
POST /api/v1/workflow-versions/{workflow_id}/version/{version_id}/publish HTTP/1.1
Authorization: Bearer <token>
```

#### Response (`200 OK`)

```json
{
  "success": true,
  "status": "published"
}
```

---

### Archive a Version

```http
POST /api/v1/workflow-versions/{workflow_id}/version/{version_id}/archive HTTP/1.1
Authorization: Bearer <token>
```

#### Response (`200 OK`)

```json
{
  "success": true,
  "status": "archived"
}
```

---

### Rollback to Version

```http
POST /api/v1/workflow-versions/{workflow_id}/rollback HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "version_id": "v1-uuid",
  "create_backup": true
}
```

#### Response (`200 OK`)

```json
{
  "success": true,
  "new_version_id": "v3-uuid",
  "backup_version_id": null
}
```

---

### Fork a Version

Forking copies a version's definition into a **different, existing** workflow. Both `version_id` (the source version) and `new_workflow_id` (the destination workflow) are required.

```http
POST /api/v1/workflow-versions/{workflow_id}/fork HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "version_id": "v1-uuid",
  "new_workflow_id": "wf-uuid-5678",
  "new_name": "Forked Workflow"
}
```

#### Response (`200 OK`)

```json
{
  "success": true,
  "new_version_id": "v1-uuid-fork"
}
```

---

### Version Statistics

`GET /api/v1/workflow-versions/{workflow_id}/stats` (write access required) returns:

```json
{
  "total_versions": 4,
  "published_versions": 2,
  "draft_versions": 1,
  "archived_versions": 1,
  "first_version_date": "2026-01-04T10:15:00",
  "latest_version_date": "2026-02-11T09:02:31"
}
```

---

## 2. Workflow Version Snapshots

**Base URL**: `/api/v1/workflows`

These four routes belong to the [Workflows API](./workflows.md) router (path `/{workflow_id}/versions`), and manage integer-numbered snapshots of a single workflow. They are **separate** from the `/api/v1/workflow-versions/...` routes in section 1 and, unlike those, use the standard `{ code, data, msg }` envelope.

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/workflows/{workflow_id}/versions` | List version snapshots (paginated) |
| `GET` | `/api/v1/workflows/{workflow_id}/versions/{version}` | Get a snapshot by its integer version number |
| `POST` | `/api/v1/workflows/{workflow_id}/versions` | Snapshot the workflow's current state |
| `POST` | `/api/v1/workflows/{workflow_id}/versions/{version}/restore` | Restore the workflow to a snapshot |

`{version}` is an integer (the workflow's `version` counter), not a UUID. List/get require the `workflow:read` permission plus access to the workflow; create and restore require write access to the workflow and the `workflow:update` permission.

### List Version Snapshots

`page` (default `1`) and `page_size` (default `20`) are query parameters; snapshots are returned newest first.

```http
GET /api/v1/workflows/{workflow_id}/versions?page=1&page_size=20 HTTP/1.1
Authorization: Bearer <token>
```

#### Response (`200 OK`)

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "snapshot-uuid",
        "workflow_id": "wf-uuid-1234",
        "version": 3,
        "description": "Before refactor",
        "created_by_id": "user-uuid",
        "created_at": "2026-02-11T09:02:31"
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20
  },
  "msg": "success"
}
```

### Get a Version Snapshot

```http
GET /api/v1/workflows/{workflow_id}/versions/3 HTTP/1.1
Authorization: Bearer <token>
```

#### Response (`200 OK`)

`data` is a full snapshot: `id`, `workflow_id`, `version`, `definition`, `variables`, `trigger_type`, `trigger_config`, `description`, `created_by_id`, and `created_at`.

### Create a Version Snapshot

Snapshots the workflow's current state at its current `version` number (the counter is not incremented).

```http
POST /api/v1/workflows/{workflow_id}/versions HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "description": "Before refactor"
}
```

#### Response (`200 OK`)

`data` is the created snapshot (`WorkflowVersionOut`, same fields as [Get a Version Snapshot](#get-a-version-snapshot)); `msg` carries the `workflow_version_created` message.

### Restore a Version Snapshot

Restores the workflow definition/variables/triggers from the given snapshot. The current state is first saved as an automatic backup snapshot, the workflow's `version` counter is incremented, and a new snapshot record is created for the restored state.

```http
POST /api/v1/workflows/{workflow_id}/versions/3/restore HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "description": "Restored after bad edit"
}
```

`description` is optional; when omitted, a default localized description is generated.

#### Response (`200 OK`)

`data` is the updated workflow (`WorkflowOut`); `msg` carries the `workflow_version_restored` message.

---

## 3. Workflow Template Marketplace

> **Note:** Not implemented / Roadmap. There is no workflow template marketplace HTTP API. A template manager exists in code (`backend/app/services/workflow/templates.py`) and is unit-tested, but no router mounts it, so `/api/v1/workflow-templates` and all of the endpoints previously listed here (list, featured, search, categories, detail, publish, instantiate, rate, delete) are **not implemented**.
