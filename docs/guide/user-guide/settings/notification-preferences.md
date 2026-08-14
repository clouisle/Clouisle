# Notification Preferences

This guide explains how notification preferences work in Clouisle.

## Overview

Notification delivery in Clouisle is configured **globally by administrators** — there is no per-user notification preference system. Individual users receive notifications in the in-app notification center and (optionally) through the external channels enabled by the administrator for automatic notification types.

> **Note:** Per-user preferences (email frequency/digests, per-type toggles, quiet hours / do-not-disturb, push notifications, notification grouping, priority levels, custom rules, and user webhook endpoints) are **not implemented**. Regular users cannot customize which notifications they receive.

## How Notifications Are Delivered

### In-App Notifications

Every user sees their notifications in the notification center and at `/app/notifications`. Notifications are scoped as:

- **global**: visible to all users
- **team**: visible to members of the target team
- **user**: visible to a specific user

### External Channels (Admin-Configured)

Administrators configure external delivery channels globally for automatic notification types. Available channels:

- **Email** (requires SMTP configuration)
- **DingTalk**
- **WeChat**
- **Feishu**
- **Webhook** (generic webhook)
- **Slack**

A channel only sends notifications when it is both selected in the global config and enabled/configured by the administrator. If no channels are configured, notifications stay in-app only.

## What Administrators Can Configure

### Auto Notification Types

Administrators choose which automatic event types are enabled (`enabled_types`). By default the following types are enabled:

| Type | Event |
|------|-------|
| `team.member_added` / `team.member_removed` | Team membership changes |
| `team.role_changed` / `team.ownership_transferred` | Role / ownership changes |
| `team.model_granted` / `team.model_revoked` | Team model access changes |
| `user.activated` / `user.deactivated` | Account status changes |
| `user.password_reset` | Administrator resets a password |
| `user.pending_approval` | New registration awaiting approval |
| `kb.doc_indexed` / `kb.doc_failed` | Knowledge base document processing |
| `workflow.run_failed` | Workflow execution failures |
| `apikey.expiring` / `apikey.expired` | API key lifecycle |
| `security.login_anomaly` | Login from a new location/device |
| `security.account_locked` | Account locked after failed attempts |
| `security.password_changed` | Password changed |

Additional types (e.g. `workflow.run_success`, `agent.published`, `agent.unpublished`, `password.expiring`) exist and can be enabled.

### Configuration Location

Admins configure this under **Admin Dashboard → Site Settings → Notifications → Auto Notifications** (and the corresponding channel tabs: Email, DingTalk, WeChat, Feishu, Webhook, Slack).

## What Users Can Do

As a user you can:

- View notifications in the notification center and at `/app/notifications`
- Mark individual notifications as read
- Mark all notifications as read
- Filter the notification list (by type, level, scope, unread, and search)

See [Notifications](../profile/notifications.md) for details.

## Notification API

- `GET /api/v1/notifications` — list visible notifications (filters: scope, type, level, unread, search)
- `GET /api/v1/notifications/unread-count` — unread count
- `POST /api/v1/notifications/read` — mark notifications read (`notification_ids` or `mark_all`)
- Admin endpoints (`/api/v1/admin/notifications`) — create/delete notifications, manage auto-notification config

> **Note:** There is no `PATCH /api/v1/notifications/{id}` or user-level `DELETE /api/v1/notifications/{id}` — reading is a bulk action and deletion is admin-only.

## Best Practices

**For users:**
- Check the notification center regularly
- Review security notifications immediately

**For administrators:**
- Enable external channels only after configuring them (SMTP, DingTalk, etc.)
- Choose enabled types deliberately to avoid notification noise

## Related Documentation

- [Notifications](../profile/notifications.md) - Viewing notifications
- [Team Settings](./team-settings.md) - Team configuration

---

**Last Updated**: 2026-02-11
