# Clouisle Resource Packages & Sandbox API

The Packages API provides endpoints for exporting, previewing, and importing bundled Clouisle resources (Agents, Workflows, Knowledge Bases, Tools) as well as managing sandbox package dependencies.

---

## Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/packages/{resource_type}/{resource_id}/export` | Export a resource as a `.clouisle` package bundle |
| `POST` | `/api/v1/packages/import/preview` | Upload and preview a `.clouisle` package |
| `POST` | `/api/v1/packages/import/{session_id}/install` | Install/apply resources from an import preview session |

---

## Export Package

Export an agent, workflow, knowledge base, or tool with its dependent metadata into a downloadable package.

```http
GET /api/v1/packages/agent/550e8400-e29b-41d4-a716-446655440000/export HTTP/1.1
Authorization: Bearer <token>
```

---

## Preview Package Import

Upload a `.clouisle` archive file to inspect the contained resources and validate dependencies before installation.

```http
POST /api/v1/packages/import/preview HTTP/1.1
Authorization: Bearer <token>
Content-Type: multipart/form-data; boundary=----WebKitFormBoundary7MA4YWxkTrZu0gW

------WebKitFormBoundary7MA4YWxkTrZu0gW
Content-Disposition: form-data; name="team_id"

team_123
------WebKitFormBoundary7MA4YWxkTrZu0gW
Content-Disposition: form-data; name="file"; filename="assistant.clouisle"
Content-Type: application/octet-stream

<binary payload>
------WebKitFormBoundary7MA4YWxkTrZu0gW--
```

### Response (`200 OK`)

```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "session_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "resources": [
      {
        "type": "agent",
        "name": "Support Assistant",
        "version": "1.0.0"
      }
    ]
  }
}
```

---

## Install Package Import

Apply and persist the resources analyzed during the preview session into the target team.

```http
POST /api/v1/packages/import/9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d/install HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "conflict_strategy": "rename"
}
```

### Response (`200 OK`)

```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "installed": [
      {
        "type": "agent",
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "Support Assistant (Imported)"
      }
    ],
    "updated": [],
    "skipped": [],
    "errors": [],
    "warnings": []
  }
}
```
