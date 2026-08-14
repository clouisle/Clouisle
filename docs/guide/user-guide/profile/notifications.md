# Notifications

This guide explains how to view and manage notifications in Clouisle.

## Overview

Notifications keep you informed about:

- **Teams**: Member added/removed, role changes, ownership transfer
- **Users**: Account activated/deactivated, pending approval, password reset
- **Knowledge bases**: Document indexed or failed
- **Workflows**: Run success or failure
- **Agents**: Published or unpublished
- **API keys**: Expiring or expired
- **Security**: Login anomaly, account locked, password changed
- **Password expiry**: Expiring, expired, forced change
- **Admin announcements**: Global notifications created by administrators

## Notification Types

### In-App Notifications

**Displayed in the application:**
- Bell icon in the navigation bar
- Badge shows the unread count
- Persistent until marked as read

**Notification center:**
```
┌─────────────────────────────────────────┐
│ 🔔 Notifications (5)        [Mark All] │
├─────────────────────────────────────────┤
│                                         │
│ ✅ Workflow completed                   │
│    "Document Summarizer" finished      │
│    1 hour ago                           │
│    [View]                               │
│                                         │
│ 📄 Document processed                   │
│    "sales_report.pdf" is ready         │
│    Yesterday                            │
│    [View]                               │
│                                         │
│ 🔒 New login detected                   │
│    From a new location                  │
│    2 days ago                           │
│    [View]                               │
│                                         │
│ [View All Notifications]                │
│                                         │
└─────────────────────────────────────────┘
```

> **Note:** Per-user notification preferences (email digests, per-type toggles, quiet hours, push notifications) are **not implemented**. Notification configuration is global and managed by administrators (see [Notification Preferences](../settings/notification-preferences.md)).

## Accessing Notifications

### Notification Center

**Steps:**

1. Click the **bell icon** (🔔) in the navigation bar
2. The notification panel opens
3. View recent notifications
4. Click a notification to view details

**Badge indicator:**
- The badge shows the unread count
- Disappears when everything is read

### Notification Page

**View all notifications:**

1. Click **"View All Notifications"** in the panel
2. The full notification page opens
3. View the complete list
4. Filter and search notifications

**Or:**

- Navigate directly to `/app/notifications`

## Managing Notifications

### Reading Notifications

**Mark as read:**

1. Click on a notification
2. It is marked as read
3. The badge count decreases

**Mark all as read:**

1. Click **"Mark All Read"** button
2. All notifications are marked as read
3. The badge disappears

> **Note:** Dismissing/deleting individual notifications is an admin action (admin notifications page). Regular users mark notifications as read.

### Notification Filters

The notifications page supports filtering and search:

| Filter | Description |
|--------|-------------|
| **Type** | Notification type (workflow, kb, security, etc.) |
| **Level** | low, medium, high |
| **Scope** | global, team, user |
| **Unread** | Show only unread notifications |
| **Search** | Search by title/content |

### Desktop Notifications

The browser asks for permission to show desktop notifications. If granted, clicking a desktop notification opens `/app/notifications`.

## Notification Types Reference

Automatic notifications (with admin-controlled delivery channels):

| Type | When |
|------|------|
| `team.member_added` / `team.member_removed` | Team membership changes |
| `team.role_changed` / `team.ownership_transferred` | Role / ownership changes |
| `team.model_granted` / `team.model_revoked` | Team model access changes |
| `user.activated` / `user.deactivated` | Account status changes |
| `user.password_reset` | Administrator resets a password |
| `user.pending_approval` | New registration awaiting approval |
| `kb.doc_indexed` / `kb.doc_failed` | Knowledge base document processing results |
| `workflow.run_success` / `workflow.run_failed` | Workflow execution results |
| `agent.published` / `agent.unpublished` | Agent publish state changes |
| `apikey.expiring` / `apikey.expired` | API key lifecycle |
| `security.login_anomaly` | Login from a new location/device |
| `security.account_locked` | Account locked after failed attempts |
| `security.password_changed` | Password changed |
| `password.expiring` / `password.expired` / `password.force_change` | Password policy events |

## Best Practices

**✅ Do:**
- Mark notifications as read regularly
- Review security alerts immediately

**❌ Don't:**
- Ignore security alerts
- Let notifications accumulate

## Troubleshooting

### Not Receiving Notifications

**Problem**: No notifications appearing

**Solutions:**
1. Check that notifications exist (admin creates/auto-generates them)
2. Verify the notification scope includes you (global/team/user)
3. Refresh the page
4. Contact the administrator

### Desktop Notifications Not Working

**Problem**: Browser notifications don't appear

**Solutions:**
1. Check browser permissions
2. Enable notifications in browser settings
3. Check system notification settings
4. Verify Clouisle has permission

## Related Documentation

- [Notification Preferences](../settings/notification-preferences.md) - Notification configuration
- [Profile Settings](./profile-settings.md) - Account settings
- [Workflow History](../workflows/workflow-history.md) - Workflow notifications

## Getting Help

If you need assistance with notifications:

1. **Documentation**: Review this guide
2. **Support**: Contact your organization's support team
3. **Administrator**: Reach out to your Clouisle administrator

---

**Last Updated**: 2026-02-11
