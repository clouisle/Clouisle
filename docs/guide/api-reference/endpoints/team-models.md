# Team Models API

The Team Models API manages which models a team is authorized to use, including per-team quota limits and current usage. These routes are mounted under the team prefix, so all paths start with `/api/v1/teams/{team_id}`.

**Base URL**: `/api/v1/teams/{team_id}`

---

## Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/teams/{team_id}/models` | List the team's model authorizations |
| `POST` | `/api/v1/teams/{team_id}/models` | Authorize a model for the team (superuser) |
| `PUT` | `/api/v1/teams/{team_id}/models/{model_id}` | Update an authorization's limits/status (superuser) |
| `DELETE` | `/api/v1/teams/{team_id}/models/{model_id}` | Revoke a model authorization (superuser) |
| `POST` | `/api/v1/teams/{team_id}/models/batch` | Authorize multiple models at once (superuser) |
| `DELETE` | `/api/v1/teams/{team_id}/models/batch` | Revoke multiple authorizations at once (superuser) |
| `GET` | `/api/v1/teams/{team_id}/available-models` | List the enabled models available to the team |
| `GET` | `/api/v1/teams/{team_id}/models/quota` | Report quota usage per authorized model |

### Authorization

| Route group | Required access |
|---|---|
| `GET` list, `available-models`, `quota` | Any authenticated user; non-superusers must be a member of the team (`403 not_team_member` otherwise) |
| `POST` / `PUT` / `DELETE` (including batch) | Superuser only |

### Model authorization object

| Field | Type | Description |
|---|---|---|
| `id` | string (UUID) | Authorization identifier |
| `team_id` | string (UUID) | Team the model is authorized for |
| `model_id` | string (UUID) | Model identifier |
| `model` | object | Model brief: `id`, `name`, `provider`, `provider_display_name`, `model_id`, `model_type`, `capabilities` |
| `daily_token_limit` | integer \| null | Daily token quota (`null` = unlimited) |
| `monthly_token_limit` | integer \| null | Monthly token quota (`null` = unlimited) |
| `daily_request_limit` | integer \| null | Daily request quota (`null` = unlimited) |
| `monthly_request_limit` | integer \| null | Monthly request quota (`null` = unlimited) |
| `daily_tokens_used` | integer | Tokens consumed today |
| `monthly_tokens_used` | integer | Tokens consumed this month |
| `daily_requests_used` | integer | Requests made today |
| `monthly_requests_used` | integer | Requests made this month |
| `is_enabled` | boolean | Whether the authorization is active |
| `priority` | integer | Selection priority among the team's models |
| `created_at` | string (ISO 8601) | Creation timestamp |
| `updated_at` | string (ISO 8601) | Last update timestamp |

---

## 1. List Team Models

```http
GET /api/v1/teams/550e8400-e29b-41d4-a716-446655440000/models HTTP/1.1
Authorization: Bearer <token>
```

### Query Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `model_type` | string | No | Filter by model type (e.g. `llm`, `embedding`) |

### Response (`200 OK`)

```json
{
  "code": 0,
  "data": [
    {
      "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
      "team_id": "550e8400-e29b-41d4-a716-446655440000",
      "model_id": "6f1c2a3b-4d5e-4f6a-8b9c-0d1e2f3a4b5c",
      "model": {
        "id": "6f1c2a3b-4d5e-4f6a-8b9c-0d1e2f3a4b5c",
        "name": "GPT-4o",
        "provider": "openai",
        "provider_display_name": "OpenAI",
        "model_id": "gpt-4o",
        "model_type": "llm",
        "capabilities": {"chat": true, "vision": true}
      },
      "daily_token_limit": 1000000,
      "monthly_token_limit": 20000000,
      "daily_request_limit": null,
      "monthly_request_limit": null,
      "daily_tokens_used": 122880,
      "monthly_tokens_used": 1980420,
      "daily_requests_used": 412,
      "monthly_requests_used": 6031,
      "is_enabled": true,
      "priority": 0,
      "created_at": "2026-09-01T09:00:00Z",
      "updated_at": "2026-09-20T11:30:00Z"
    }
  ],
  "msg": "success"
}
```

---

## 2. Authorize a Model

```http
POST /api/v1/teams/550e8400-e29b-41d4-a716-446655440000/models HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "model_id": "6f1c2a3b-4d5e-4f6a-8b9c-0d1e2f3a4b5c",
  "daily_token_limit": 1000000,
  "monthly_token_limit": 20000000,
  "is_enabled": true,
  "priority": 0
}
```

### Request Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `model_id` | string (UUID) | Yes | Model to authorize |
| `daily_token_limit` | integer \| null | No | Daily token quota (≥ 0, `null` = unlimited) |
| `monthly_token_limit` | integer \| null | No | Monthly token quota (≥ 0, `null` = unlimited) |
| `daily_request_limit` | integer \| null | No | Daily request quota (≥ 0, `null` = unlimited) |
| `monthly_request_limit` | integer \| null | No | Monthly request quota (≥ 0, `null` = unlimited) |
| `is_enabled` | boolean | No | Whether the authorization is active (default: `true`) |
| `priority` | integer | No | Selection priority (default: `0`) |

Returns the created authorization object. Repeating an existing authorization fails with `team_model_already_authorized`.

---

## 3. Update an Authorization

```http
PUT /api/v1/teams/550e8400-e29b-41d4-a716-446655440000/models/6f1c2a3b-4d5e-4f6a-8b9c-0d1e2f3a4b5c HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "daily_token_limit": 2000000,
  "is_enabled": false
}
```

All fields are optional; only the supplied ones are updated. Accepts the same limit fields as `POST`, plus `is_enabled` and `priority`. Returns the updated authorization object. Fails with `404 team_model_not_found` if the team is not authorized for that model.

---

## 4. Revoke an Authorization

```http
DELETE /api/v1/teams/550e8400-e29b-41d4-a716-446655440000/models/6f1c2a3b-4d5e-4f6a-8b9c-0d1e2f3a4b5c HTTP/1.1
Authorization: Bearer <token>
```

### Response (`200 OK`)

```json
{
  "code": 0,
  "data": {
    "team_id": "550e8400-e29b-41d4-a716-446655440000",
    "model_id": "6f1c2a3b-4d5e-4f6a-8b9c-0d1e2f3a4b5c"
  },
  "msg": "Model authorization revoked successfully"
}
```

Fails with `404 team_model_not_found` when no such authorization exists.

---

## 5. Batch Authorize Models

```http
POST /api/v1/teams/550e8400-e29b-41d4-a716-446655440000/models/batch HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "model_ids": [
    "6f1c2a3b-4d5e-4f6a-8b9c-0d1e2f3a4b5c",
    "8a7b6c5d-4e3f-4a2b-9c8d-7e6f5a4b3c2d"
  ],
  "monthly_token_limit": 5000000
}
```

### Request Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `model_ids` | array of string (UUID) | Yes | Models to authorize (at least one) |
| `daily_token_limit` | integer \| null | No | Daily token quota applied to each new authorization |
| `monthly_token_limit` | integer \| null | No | Monthly token quota applied to each new authorization |
| `daily_request_limit` | integer \| null | No | Daily request quota applied to each new authorization |
| `monthly_request_limit` | integer \| null | No | Monthly request quota applied to each new authorization |

Returns the list of newly created authorization objects (`200 OK`); already-authorized models are skipped. An empty `model_ids` array fails request validation (`422`, code `1001`).

---

## 6. Batch Revoke Authorizations

```http
DELETE /api/v1/teams/550e8400-e29b-41d4-a716-446655440000/models/batch HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "model_ids": ["6f1c2a3b-4d5e-4f6a-8b9c-0d1e2f3a4b5c"]
}
```

### Response (`200 OK`)

```json
{
  "code": 0,
  "data": {
    "deleted_count": 1
  },
  "msg": "Model authorizations revoked successfully"
}
```

---

## 7. List Available Models

Returns only the models that are both authorized for the team and enabled (and whose model record is enabled).

```http
GET /api/v1/teams/550e8400-e29b-41d4-a716-446655440000/available-models?model_type=llm HTTP/1.1
Authorization: Bearer <token>
```

### Query Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `model_type` | string | No | Filter by model type |

### Response (`200 OK`)

`data` is an array of model briefs (`id`, `name`, `provider`, `provider_display_name`, `model_id`, `model_type`, `capabilities`), ordered by authorization priority descending.

---

## 8. Get Quota Usage

```http
GET /api/v1/teams/550e8400-e29b-41d4-a716-446655440000/models/quota HTTP/1.1
Authorization: Bearer <token>
```

### Response (`200 OK`)

```json
{
  "code": 0,
  "data": [
    {
      "model_id": "6f1c2a3b-4d5e-4f6a-8b9c-0d1e2f3a4b5c",
      "model_name": "GPT-4o",
      "model_type": "llm",
      "daily_token_limit": 1000000,
      "daily_tokens_used": 122880,
      "daily_token_percent": 12.29,
      "monthly_token_limit": 20000000,
      "monthly_tokens_used": 1980420,
      "monthly_token_percent": 9.9,
      "is_enabled": true,
      "is_quota_exceeded": false
    }
  ],
  "msg": "success"
}
```

`daily_token_percent` / `monthly_token_percent` are `null` when the corresponding limit is `null`. `is_quota_exceeded` is `true` once a token allowance is fully consumed.

---

## Related

- [Models](./models.md) — model catalog management
- [Teams](./teams.md) — team and membership management
- [Batch Operations](../batch-operations.md) — batch team-model authorization patterns
