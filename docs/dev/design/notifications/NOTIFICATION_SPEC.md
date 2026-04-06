# Notification Center Spec

## Status
- Draft
- Date: 2026-02-02

## Scope
This document defines the notification center design for Clouisle, covering data model, API, permissions, delivery flow, UI placement, i18n rules, and audit requirements. Implementation is not included.

## Goals
- Provide unified notifications for **global**, **team**, and **user** scopes.
- Support system notifications, user messages, and business reminders.
- Provide best-practice read/unread behavior, frequency control, and UI display.
- Ensure auditability and extensibility for external delivery channels.

## Non-Goals
- Do not implement message content i18n (only UI fixed text is i18n).
- Do not define new business modules beyond notification integration points.
- Do not implement external push providers in this phase; reserve interfaces only.

## Definitions
- **Global**: visible to all users in the system.
- **Team**: visible to members of a specific team.
- **User**: visible only to a specific user.
- **Notification**: a persistent record rendered in notification center.
- **Delivery**: the act of distributing a notification to in-app list or external channels.

## Requirements Summary
- Scopes: global, team, user.
- Visibility:
  - Global: all users.
  - Team: members of target team.
  - User: target user only.
- Priority: required (high/medium/low).
- Read status: best-practice behavior, supports bulk read, optional auto-read on detail.
- Retention: no archive in this phase.
- Channels: in-app required; reserve external push channels.
- Frequency: best-practice de-duplication and aggregation.
- UI: best-practice notification center display.
- Audit: required for create/deliver/read.

## Architecture Overview
```
Event -> Notification Builder -> Delivery Queue -> Notification Store
                               -> External Channel (reserved)

UI: Notification Center -> Fetch list -> Mark read -> Unread count
```

## Data Model (Proposed)

### notification
Stores the notification itself.

| Field | Type | Notes |
| --- | --- | --- |
| id | uuid | PK |
| scope | enum | global/team/user |
| team_id | uuid? | required when scope=team |
| user_id | uuid? | required when scope=user |
| type | string | notification type key |
| source | enum | system/user/biz |
| title | string | short title |
| content | text | main body |
| level | enum | low/medium/high |
| data | jsonb | extra structured data |
| link_url | string? | optional deep link |
| status | enum | active (reserved for future) |
| expires_at | datetime? | optional TTL |
| created_at | datetime | |
| updated_at | datetime | |

Indexes
- (scope, created_at)
- (team_id, created_at)
- (user_id, created_at)
- (type, created_at) optional

### notification_read
Tracks per-user read state for any visible notification.

| Field | Type | Notes |
| --- | --- | --- |
| id | uuid | PK |
| notification_id | uuid | FK -> notification.id |
| user_id | uuid | viewer user |
| read_at | datetime | read timestamp |

Constraints
- Unique (notification_id, user_id)

Indexes
- (user_id, read_at)
- (notification_id, user_id)

### notification_audit
Audit events for creation, delivery, read, and deletion.

| Field | Type | Notes |
| --- | --- | --- |
| id | uuid | PK |
| notification_id | uuid | FK -> notification.id |
| user_id | uuid? | actor or recipient |
| action | enum | create/deliver/read/delete |
| meta | jsonb | context |
| created_at | datetime | |

Indexes
- (notification_id, created_at)
- (user_id, created_at)

## Permission Rules
- Read access:
  - Global: all users
  - Team: members of the team
  - User: only the target user
- Write access:
  - Global: admin only
  - Team: admin (or team owner/admin) only
  - User: system services or owner operations

## Notification Types (Initial Set)
Use `type` as a stable key for rendering and filtering.

Suggested keys
- `team.invite`
- `team.role_changed`
- `kb.doc_indexed`
- `kb.doc_failed`
- `workflow.run_failed`
- `app.publish`
- `app.unpublish`
- `model.test_failed`
- `quota.near_limit`
- `quota.exceeded`
- `security.login_anomaly`
- `user.mention`
- `user.assigned`

## Delivery Flow
1. **Event** occurs (business module emits event).
2. **Builder** normalizes event -> notification payload (type, scope, target, level, content, data).
3. **De-dup / aggregation** within time window (10-15 min) for noisy events.
4. **Queue** via Celery to write notification + audit.
5. **Store** in DB; update unread counters cache (Redis).
6. **External channels** reserved: create outbox record for future delivery.

## Read / Unread Best Practices
- Default: notifications are unread.
- Mark read:
  - Single item read
  - Bulk read (all or filtered)
  - Optional auto-read when opening detail
- Unread count:
  - Cached per user (Redis) with periodic reconciliation

## Frequency Control (Best Practice)
- De-dup key: (type, scope, target, hash(data)) within time window.
- Aggregation: merge similar notifications into a summary when count >= N.
- Example: "10 minutes: 3 workflow failures".

## API Design (Proposed)
All responses use unified format `{code, data, msg}`.

### List notifications
- `GET /api/v1/notifications`

Query
- `page`, `page_size`
- `scope` (optional)
- `type` (optional)
- `level` (optional)
- `unread_only` (optional)
- `created_from`, `created_to` (optional)

Response `PageData[NotificationOut]`

### Unread count
- `GET /api/v1/notifications/unread-count`

Response
- `{ total: number }`

### Mark read
- `POST /api/v1/notifications/read`

Body
- `notification_ids?: string[]`
- `mark_all?: boolean`

Response
- `{ updated: number }`

### Admin list
- `GET /api/v1/admin/notifications`

### Admin create
- `POST /api/v1/admin/notifications`

Body (example)
```
{
  "scope": "global",
  "level": "high",
  "type": "system.announcement",
  "title": "Maintenance",
  "content": "System maintenance at 01:00 UTC",
  "link_url": "/status",
  "expires_at": "2026-03-01T00:00:00Z"
}
```

### Admin delete
- `DELETE /api/v1/admin/notifications/{id}`

## Frontend Placement
- **Platform** `(platform)`
  - Notification center list
  - Unread badge in header
  - Detail view (drawer or modal)
- **Dashboard** `(dashboard)`
  - Notification management list
  - Create global/team notification

## i18n Rules
- Fixed UI text must use `next-intl`.
- Notification content is not translated in this phase.

## Audit
- Create audit for create/deliver/read/delete actions.
- Provide queryable audit trail for admin.

## Performance & Scaling
- Indexing on scope/team/user/time
- Read path uses pagination + caching for unread count
- Write path uses async queue
- Optional monthly partitioning for `notification` table if volume grows

## Open Questions
- Thresholds for aggregation (N, time window)
- Per-type priority defaults
- Whether to allow user dismissal without read

