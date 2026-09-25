# Notifications API

The Notifications API exposes the in-app notification inbox for the authenticated user, plus the admin-scoped routes used to publish and remove notifications.

**Base URL**: `/api/v1/notifications`

---

## Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/notifications` | List notifications visible to the caller |
| `GET` | `/api/v1/notifications/unread-count` | Count the caller's unread notifications |
| `POST` | `/api/v1/notifications/read` | Mark specific notifications (or all of them) as read |
| `GET` | `/api/v1/admin/notifications` | Admin: list notifications across scopes |
| `POST` | `/api/v1/admin/notifications` | Admin: create and dispatch a notification |
| `DELETE` | `/api/v1/admin/notifications/{notification_id}` | Admin: delete a notification |

All routes require a bearer token (`Authorization: Bearer <token>`). The admin routes additionally require admin permissions — see [Admin notifications](#4-admin-notifications).

### Visibility

A caller sees a notification when:

- its scope is `global`, or
- its scope is `user` and `user_id` is the caller, or
- its scope is `team` and `team_id` is one of the teams the caller belongs to.

Expired notifications (`expires_at` in the past) are excluded from listing and from the unread count.

### Notification object

| Field | Type | Description |
|---|---|---|
| `id` | string (UUID) | Notification identifier |
| `scope` | string | `global`, `team`, or `user` |
| `team_id` | string (UUID) \| null | Target team (for `team` scope) |
| `user_id` | string (UUID) \| null | Target user (for `user` scope) |
| `type` | string | Notification type key |
| `source` | string | `system`, `user`, or `biz` |
| `title` | string | Notification title |
| `content` | string | Notification body |
| `level` | string | `low`, `medium`, or `high` |
| `data` | object \| null | Arbitrary payload attached to the notification |
| `link_url` | string \| null | Optional in-app link to open |
| `status` | string | `active` |
| `expires_at` | string (ISO 8601) \| null | Expiry timestamp |
| `created_at` | string (ISO 8601) | Creation timestamp |
| `updated_at` | string (ISO 8601) | Last update timestamp |
| `is_read` | boolean | Whether the caller has read it |
| `read_at` | string (ISO 8601) \| null | When the caller read it |
| `deliveries` | array | Per-channel delivery records (`channel`, `status`, `error_message`, `retry_count`, `sent_at`, `created_at`, `updated_at`) |

---

## 1. List Notifications

```http
GET /api/v1/notifications?unread_only=true&page=1&page_size=20 HTTP/1.1
Authorization: Bearer <token>
```

### Query Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `scope` | string | — | Filter by scope: `global`, `team`, or `user` |
| `type` | string | — | Filter by notification type key |
| `level` | string | — | Filter by level: `low`, `medium`, or `high` |
| `search` | string | — | Case-insensitive match on `title`, `content`, or `type` |
| `unread_only` | boolean | `false` | Only return notifications the caller has not read |
| `created_from` | string | — | Lower bound on `created_at` |
| `created_to` | string | — | Upper bound on `created_at` |
| `page` | integer | `1` | Page number (≥ 1) |
| `page_size` | integer | `20` | Page size (1–100) |

Results are ordered by `created_at` descending.

### Response (`200 OK`)

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
        "scope": "team",
        "team_id": "550e8400-e29b-41d4-a716-446655440000",
        "user_id": null,
        "type": "team_agent_published",
        "source": "system",
        "title": "Agent published",
        "content": "Support Assistant is now available to the team.",
        "level": "medium",
        "data": {"agent_id": "1c2f1a2e-0f4e-4a8f-9d4a-2b0d7b3dcb6d"},
        "link_url": "/app/apps/1c2f1a2e-0f4e-4a8f-9d4a-2b0d7b3dcb6d",
        "status": "active",
        "expires_at": null,
        "created_at": "2026-09-26T08:15:00Z",
        "updated_at": "2026-09-26T08:15:00Z",
        "is_read": false,
        "read_at": null,
        "deliveries": []
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

## 2. Get Unread Count

```http
GET /api/v1/notifications/unread-count HTTP/1.1
Authorization: Bearer <token>
```

### Response (`200 OK`)

```json
{
  "code": 0,
  "data": {
    "total": 3
  },
  "msg": "success"
}
```

---

## 3. Mark Notifications as Read

Pass explicit notification IDs, or `mark_all` to mark every currently visible notification as read.

```http
POST /api/v1/notifications/read HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "notification_ids": ["9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d"],
  "mark_all": false
}
```

### Request Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `notification_ids` | array of string (UUID) | No | Notifications to mark as read |
| `mark_all` | boolean | No | Mark all visible notifications as read (default: `false`) |

At least one of `notification_ids` or `mark_all` must be provided, otherwise the request fails with `400` (`validation_error`).

### Response (`200 OK`)

```json
{
  "code": 0,
  "data": {
    "updated": 1
  },
  "msg": "Notification read status updated"
}
```

---

## 4. Admin Notifications

These routes are mounted under `/api/v1/admin/notifications` and are **admin-only**. See the Admin Guide's notification settings for the operational workflow.

### List Notifications (Admin)

```http
GET /api/v1/admin/notifications?scope=global&page=1&page_size=20 HTTP/1.1
Authorization: Bearer <token>
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `scope` | repeatable string | — | Filter by one or more scopes: `global`, `team`, `user` |
| `team_id` | string (UUID) | — | Filter by team |
| `user_id` | string (UUID) | — | Filter by target user |
| `type` | string | — | Filter by notification type key |
| `level` | repeatable string | — | Filter by one or more levels |
| `search` | string | — | Case-insensitive match on `title`, `content`, or `type` |
| `include_expired` | boolean | `false` | Include notifications whose `expires_at` has passed |
| `page` | integer | `1` | Page number (≥ 1) |
| `page_size` | integer | `20` | Page size (1–100) |

Returns the same `{items, total, page, page_size}` envelope as the user-facing list. `items[].is_read` and `items[].read_at` are always `false`/`null` on this route (read state is per-user), while `items[].deliveries` is populated.

Callers without global admin access (`admin:dashboard:access`) must pass a `team_id` for a team they administer; requesting `global` scope or omitting `team_id` then fails with `403`/`400`.

### Create Notification (Admin)

```http
POST /api/v1/admin/notifications HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "scope": "team",
  "team_id": "550e8400-e29b-41d4-a716-446655440000",
  "type": "maintenance_notice",
  "source": "system",
  "title": "Scheduled maintenance",
  "content": "The platform will be unavailable on Sunday 02:00–04:00 UTC.",
  "level": "high",
  "link_url": "/status",
  "notify_channels": ["email", "webhook"]
}
```

Requires the `admin:notification:create` permission.

| Field | Type | Required | Description |
|---|---|---|---|
| `scope` | string | Yes | `global`, `team`, or `user` |
| `team_id` | string (UUID) | Conditional | Required when `scope` is `team` |
| `user_id` | string (UUID) | Conditional | Target user for `user` scope |
| `user_ids` | array of string (UUID) | Conditional | Batch-target multiple users for `user` scope |
| `type` | string | Yes | Notification type key (1–100 chars) |
| `source` | string | No | `system`, `user`, or `biz` (default: `system`) |
| `title` | string | Yes | Title (1–255 chars) |
| `content` | string | Yes | Body text |
| `level` | string | No | `low`, `medium`, or `high` (default: `medium`) |
| `data` | object | No | Arbitrary payload |
| `link_url` | string | No | Optional in-app link |
| `expires_at` | string (ISO 8601) | No | Expiry timestamp |
| `notify_channels` | array of string | No | Delivery channels: `email`, `dingtalk`, `wechat`, `feishu`, `webhook`, `slack` |

Returns the created notification object (`200 OK`).

### Delete Notification (Admin)

```http
DELETE /api/v1/admin/notifications/9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d HTTP/1.1
Authorization: Bearer <token>
```

Requires the `admin:notification:delete` permission. Returns `404` (`notification_not_found`) if the notification does not exist, and `403` when a non-global admin tries to delete a `global` or `user` scoped notification.

```json
{
  "code": 0,
  "data": {
    "id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d"
  },
  "msg": "Notification deleted successfully"
}
```

---

## Related

- [SSE Streaming](../sse-streaming.md) — real-time event transport
- [Webhooks](../webhooks.md) — the `webhook` delivery channel
- [SDK Examples](../sdk-examples.md)
