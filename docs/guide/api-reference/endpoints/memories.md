# Memories API

The Memories API exposes the authenticated user's long-term memory graph: the entities extracted from their agent conversations and the typed relations between them. Every endpoint is scoped to the calling user — there is no `team_id` parameter, and one user can never read or modify another user's entities or relations.

Base URL: `/api/v1/memories`. All endpoints require an authenticated JWT user session (`Authorization: Bearer <token>`); API-key authentication is not accepted.

---

## Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/memories/entities` | List the caller's memory entities |
| `POST` | `/api/v1/memories/entities` | Create a memory entity manually |
| `GET` | `/api/v1/memories/entities/{entity_id}` | Get an entity with its outgoing and incoming relations |
| `PUT` | `/api/v1/memories/entities/{entity_id}` | Update an entity |
| `DELETE` | `/api/v1/memories/entities/{entity_id}` | Delete an entity and its relations |
| `GET` | `/api/v1/memories/relations` | List the caller's memory relations |
| `POST` | `/api/v1/memories/relations` | Create a memory relation manually |
| `DELETE` | `/api/v1/memories/relations/{relation_id}` | Delete a relation |
| `GET` | `/api/v1/memories/graph` | Get the caller's memory graph for visualization |

All responses use the standard envelope `{"code": 0, "data": ..., "msg": "success"}`.

---

## Entity Object

| Field | Type | Description |
|---|---|---|
| `id` | `string` (UUID) | Entity ID |
| `user_id` | `string` (UUID) | Owning user |
| `name` | `string` | Entity name (max 255 characters) |
| `entity_type` | `string` | Entity type (see below) |
| `description` | `string \| null` | Detailed description |
| `properties` | `object` | Free-form properties, e.g. `{"level": "expert"}` |
| `source_conversation_id` | `string \| null` | Conversation the entity was extracted from, if any |
| `source_message_id` | `string \| null` | Message the entity was extracted from, if any |
| `access_count` | `integer` | Number of times the entity was recalled |
| `last_accessed_at` | `string \| null` | Last recall timestamp |
| `created_at` | `string` | Creation timestamp |
| `updated_at` | `string` | Last update timestamp |

`entity_type` is one of: `person`, `preference`, `skill`, `project`, `goal`, `fact`, `concept`, `organization`, `location`, `custom`.

## Relation Object

| Field | Type | Description |
|---|---|---|
| `id` | `string` (UUID) | Relation ID |
| `user_id` | `string` (UUID) | Owning user |
| `source_entity_id` | `string` (UUID) | Source entity |
| `target_entity_id` | `string` (UUID) | Target entity |
| `relation_type` | `string` | Relation type (see below) |
| `description` | `string \| null` | Relation description |
| `properties` | `object` | Free-form properties, e.g. `{"since": "2024"}` |
| `source_conversation_id` | `string \| null` | Conversation the relation was extracted from, if any |
| `source_message_id` | `string \| null` | Message the relation was extracted from, if any |
| `created_at` | `string` | Creation timestamp |
| `updated_at` | `string` | Last update timestamp |

`relation_type` is one of: `prefers`, `works_on`, `knows`, `uses`, `works_at`, `located_in`, `has_goal`, `related_to`, `part_of`.

---

## List Entities

```http
GET /api/v1/memories/entities?entity_type=preference&page=1&page_size=20 HTTP/1.1
Authorization: Bearer <token>
```

### Query Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `entity_type` | `string` | No | - | Filter by entity type |
| `page` | `integer` | No | 1 | Page number (min: 1) |
| `page_size` | `integer` | No | 20 | Items per page (min: 1, max: 100) |

### Response (`200 OK`)

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "8f14e45f-ceea-467a-9c1c-1b0c1a2d3e4f",
        "user_id": "3d1f7a92-5b6c-4f8e-9a01-2c3d4e5f6a7b",
        "name": "Python",
        "entity_type": "preference",
        "description": "Prefers concise Python snippets using async/await syntax.",
        "properties": {"level": "expert"},
        "source_conversation_id": "0b2c3d4e-5f60-4a71-8b92-c3d4e5f60718",
        "source_message_id": null,
        "access_count": 4,
        "last_accessed_at": "2026-09-20T10:15:00Z",
        "created_at": "2026-03-02T08:30:00Z",
        "updated_at": "2026-09-20T10:15:00Z"
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20
  },
  "msg": "success"
}
```

---

## Create Entity

```http
POST /api/v1/memories/entities HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "Python",
  "entity_type": "preference",
  "description": "Prefers concise Python snippets using async/await syntax.",
  "properties": {"level": "expert"}
}
```

### Request Body

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | `string` | Yes | Entity name (max 255 characters) |
| `entity_type` | `string` | Yes | Entity type |
| `description` | `string \| null` | No | Entity description |
| `properties` | `object` | No | Additional properties (default: `{}`) |

### Response (`200 OK`)

`data` is the created [Entity Object](#entity-object).

### Errors

| HTTP | `code` | Meaning |
|---|---|---|
| `400` | `1003` | Entity could not be created |

---

## Get Entity

Returns the entity together with every relation where it is the source (`outgoing_relations`) or the target (`incoming_relations`).

```http
GET /api/v1/memories/entities/8f14e45f-ceea-467a-9c1c-1b0c1a2d3e4f HTTP/1.1
Authorization: Bearer <token>
```

### Response (`200 OK`)

```json
{
  "code": 0,
  "data": {
    "entity": {
      "id": "8f14e45f-ceea-467a-9c1c-1b0c1a2d3e4f",
      "user_id": "3d1f7a92-5b6c-4f8e-9a01-2c3d4e5f6a7b",
      "name": "Python",
      "entity_type": "preference",
      "description": "Prefers concise Python snippets using async/await syntax.",
      "properties": {"level": "expert"},
      "source_conversation_id": null,
      "source_message_id": null,
      "access_count": 4,
      "last_accessed_at": "2026-09-20T10:15:00Z",
      "created_at": "2026-03-02T08:30:00Z",
      "updated_at": "2026-09-20T10:15:00Z"
    },
    "outgoing_relations": [
      {
        "id": "c6d5e4f3-a2b1-4c0d-9e8f-7a6b5c4d3e2f",
        "user_id": "3d1f7a92-5b6c-4f8e-9a01-2c3d4e5f6a7b",
        "source_entity_id": "8f14e45f-ceea-467a-9c1c-1b0c1a2d3e4f",
        "target_entity_id": "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d",
        "relation_type": "uses",
        "description": null,
        "properties": {},
        "source_conversation_id": null,
        "source_message_id": null,
        "created_at": "2026-03-02T08:31:00Z",
        "updated_at": "2026-03-02T08:31:00Z"
      }
    ],
    "incoming_relations": []
  },
  "msg": "success"
}
```

### Errors

| HTTP | `code` | Meaning |
|---|---|---|
| `400` | `4000` | `memory_entity_not_found` — unknown ID or not owned by the caller |

---

## Update Entity

```http
PUT /api/v1/memories/entities/8f14e45f-ceea-467a-9c1c-1b0c1a2d3e4f HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "Python 3.13",
  "description": "Prefers concise Python snippets using async/await syntax.",
  "properties": {"level": "expert", "years": 5}
}
```

### Request Body

All fields are optional. A field that is omitted or sent as `null` is left untouched, so `description` cannot be cleared through this endpoint.

| Field | Type | Description |
|---|---|---|
| `name` | `string \| null` | New entity name (max 255 characters) |
| `description` | `string \| null` | New entity description |
| `properties` | `object \| null` | Properties merged into the existing `properties` map (existing keys are kept unless overwritten) |

### Response (`200 OK`)

`data` is the updated [Entity Object](#entity-object). Changing `name` or `description` also refreshes the entity's vector embedding.

### Errors

| HTTP | `code` | Meaning |
|---|---|---|
| `400` | `4000` | `memory_entity_not_found` |
| `400` | `1003` | Entity could not be updated |

---

## Delete Entity

Deletes the entity together with every relation that references it.

```http
DELETE /api/v1/memories/entities/8f14e45f-ceea-467a-9c1c-1b0c1a2d3e4f HTTP/1.1
Authorization: Bearer <token>
```

### Response (`200 OK`)

```json
{
  "code": 0,
  "data": {
    "message": "Memory entity deleted successfully"
  },
  "msg": "Memory entity deleted successfully"
}
```

### Errors

| HTTP | `code` | Meaning |
|---|---|---|
| `400` | `4000` | `memory_entity_not_found` |
| `400` | `1003` | Entity could not be deleted |

---

## List Relations

```http
GET /api/v1/memories/relations?entity_id=8f14e45f-ceea-467a-9c1c-1b0c1a2d3e4f&relation_type=uses&page=1&page_size=20 HTTP/1.1
Authorization: Bearer <token>
```

### Query Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `entity_id` | `string` (UUID) | No | - | Filter by entity ID; matches relations where the entity is either the source or the target |
| `relation_type` | `string` | No | - | Filter by relation type |
| `page` | `integer` | No | 1 | Page number (min: 1) |
| `page_size` | `integer` | No | 20 | Items per page (min: 1, max: 100) |

### Response (`200 OK`)

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "c6d5e4f3-a2b1-4c0d-9e8f-7a6b5c4d3e2f",
        "user_id": "3d1f7a92-5b6c-4f8e-9a01-2c3d4e5f6a7b",
        "source_entity_id": "8f14e45f-ceea-467a-9c1c-1b0c1a2d3e4f",
        "target_entity_id": "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d",
        "relation_type": "uses",
        "description": null,
        "properties": {},
        "source_conversation_id": null,
        "source_message_id": null,
        "created_at": "2026-03-02T08:31:00Z",
        "updated_at": "2026-03-02T08:31:00Z"
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20
  },
  "msg": "success"
}
```

---

## Create Relation

Both entities must already belong to the calling user.

```http
POST /api/v1/memories/relations HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "source_entity_id": "8f14e45f-ceea-467a-9c1c-1b0c1a2d3e4f",
  "target_entity_id": "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d",
  "relation_type": "uses",
  "description": "Uses Python for data analysis",
  "properties": {"since": "2024"}
}
```

### Request Body

| Field | Type | Required | Description |
|---|---|---|---|
| `source_entity_id` | `string` (UUID) | Yes | Source entity ID |
| `target_entity_id` | `string` (UUID) | Yes | Target entity ID |
| `relation_type` | `string` | Yes | Relation type |
| `description` | `string \| null` | No | Relation description |
| `properties` | `object` | No | Additional properties (default: `{}`) |

### Response (`200 OK`)

`data` is the created [Relation Object](#relation-object).

### Errors

| HTTP | `code` | Meaning |
|---|---|---|
| `400` | `1002` | `memory_source_entity_not_found` or `memory_target_entity_not_found` |
| `400` | `1002` | `memory_relation_create_failed` |
| `400` | `1003` | Relation could not be created |

---

## Delete Relation

```http
DELETE /api/v1/memories/relations/c6d5e4f3-a2b1-4c0d-9e8f-7a6b5c4d3e2f HTTP/1.1
Authorization: Bearer <token>
```

### Response (`200 OK`)

```json
{
  "code": 0,
  "data": {
    "message": "Memory relation deleted successfully"
  },
  "msg": "Memory relation deleted successfully"
}
```

### Errors

| HTTP | `code` | Meaning |
|---|---|---|
| `400` | `4000` | `memory_relation_not_found` |
| `400` | `1003` | Relation could not be deleted |

---

## Get Memory Graph

Returns the entities and relations that make up the memory graph, for visualization.

```http
GET /api/v1/memories/graph?entity_ids=8f14e45f-ceea-467a-9c1c-1b0c1a2d3e4f&entity_ids=1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d&max_depth=2 HTTP/1.1
Authorization: Bearer <token>
```

### Query Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `entity_ids` | `array` of UUIDs | No | - | Repeat the parameter to limit the graph to the subgraph around these entities |
| `max_depth` | `integer` | No | 1 | Subgraph traversal depth (min: 1, max: 3) |

When `entity_ids` is omitted, the full graph of the calling user is returned.

### Response (`200 OK`)

```json
{
  "code": 0,
  "data": {
    "entities": [
      {
        "id": "8f14e45f-ceea-467a-9c1c-1b0c1a2d3e4f",
        "user_id": "3d1f7a92-5b6c-4f8e-9a01-2c3d4e5f6a7b",
        "name": "Python",
        "entity_type": "preference",
        "description": "Prefers concise Python snippets using async/await syntax.",
        "properties": {"level": "expert"},
        "source_conversation_id": null,
        "source_message_id": null,
        "access_count": 4,
        "last_accessed_at": "2026-09-20T10:15:00Z",
        "created_at": "2026-03-02T08:30:00Z",
        "updated_at": "2026-09-20T10:15:00Z"
      }
    ],
    "relations": [
      {
        "id": "c6d5e4f3-a2b1-4c0d-9e8f-7a6b5c4d3e2f",
        "user_id": "3d1f7a92-5b6c-4f8e-9a01-2c3d4e5f6a7b",
        "source_entity_id": "8f14e45f-ceea-467a-9c1c-1b0c1a2d3e4f",
        "target_entity_id": "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d",
        "relation_type": "uses",
        "description": null,
        "properties": {},
        "source_conversation_id": null,
        "source_message_id": null,
        "created_at": "2026-03-02T08:31:00Z",
        "updated_at": "2026-03-02T08:31:00Z"
      }
    ]
  },
  "msg": "success"
}
```

---

## Validation Errors

FastAPI request validation failures (bad UUID format, unknown `entity_type` / `relation_type`, `page_size` over 100, …) return HTTP `422` with the standard error envelope:

```json
{
  "code": 1001,
  "data": {
    "errors": {
      "page_size": ["Validation error"]
    }
  },
  "msg": "Validation error"
}
```
