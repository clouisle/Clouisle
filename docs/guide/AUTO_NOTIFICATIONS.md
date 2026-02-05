# Auto Notifications

The auto notification feature allows administrators to configure automatic notifications when specific events occur.

## Overview

- **In-app Notifications**: All enabled auto notifications create in-app notifications
- **External Channels**: Can be configured to send via email, DingTalk, WeChat Work, Feishu, Slack, Webhook
- **Global Configuration**: External channels are globally configured and apply to all enabled notification types

## Notification Types

### Team Related

| Type | Description | Recipients |
|------|-------------|------------|
| `team.member_added` | Member added to team | Added user |
| `team.member_removed` | Member removed from team | Removed user |
| `team.role_changed` | Member role changed | User whose role changed |
| `team.ownership_transferred` | Team ownership transferred | New owner |
| `team.model_granted` | Model granted to team | Team members |
| `team.model_revoked` | Model access revoked | Team members |

### User Related

| Type | Description | Recipients |
|------|-------------|------------|
| `user.activated` | User account activated | Activated user |
| `user.deactivated` | User account deactivated | Deactivated user |
| `user.password_reset` | User password reset | User whose password was reset |
| `user.pending_approval` | New user registration pending approval | All super admins |

### Knowledge Base Related

| Type | Description | Recipients |
|------|-------------|------------|
| `kb.doc_indexed` | Document indexing completed | Document's team |
| `kb.doc_failed` | Document processing failed | Document's team |

### Workflow Related

| Type | Description | Recipients |
|------|-------------|------------|
| `workflow.run_success` | Workflow run succeeded | Trigger user |
| `workflow.run_failed` | Workflow run failed | Trigger user |

### Agent Related

| Type | Description | Recipients |
|------|-------------|------------|
| `agent.published` | Agent published | Agent's team |
| `agent.unpublished` | Agent unpublished | Agent's team |

### API Key Related

| Type | Description | Recipients |
|------|-------------|------------|
| `apikey.expiring` | API Key expiring soon | API Key owner |
| `apikey.expired` | API Key expired | API Key owner |

**Note**:
- API Key expiration check runs via Celery Beat scheduled task daily at 09:00
- Expiration reminders are sent 7 days, 3 days, and 1 day before expiration

### Security Related

| Type | Description | Recipients |
|------|-------------|------------|
| `security.login_anomaly` | Anomalous login detected | Logged in user |
| `security.account_locked` | Account locked | Locked user |
| `security.password_changed` | Password changed | User who changed password |

**Login Anomaly Detection**:
- System records user's recent login IP addresses and device info (User-Agent)
- When user logs in from new IP or device, anomaly notification is triggered
- Login history retained for 30 days, max 10 IPs and 10 devices per user

## Configuration

### Admin Dashboard Configuration

1. Go to **Site Settings** → **Notification Settings** → **Auto Notifications** tab
2. Check notification types to enable
3. Select external notification channels (must be enabled in respective channel settings first)
4. Save configuration

### API Configuration

**Get Configuration**

```http
GET /api/v1/site-settings/auto-notifications
```

Response example:
```json
{
  "code": 0,
  "data": {
    "enabled_types": [
      "team.member_added",
      "team.member_removed",
      "user.activated",
      "security.login_anomaly"
    ],
    "channels": ["email", "dingtalk"]
  },
  "msg": "success"
}
```

**Update Configuration**

```http
PUT /api/v1/site-settings/auto-notifications
Content-Type: application/json

{
  "enabled_types": [
    "team.member_added",
    "team.member_removed",
    "user.activated",
    "security.login_anomaly"
  ],
  "channels": ["email"]
}
```

## External Channels

Auto notifications support the following external channels:

| Channel | Configuration | Description |
|---------|---------------|-------------|
| `email` | SMTP settings | Email notifications |
| `dingtalk` | DingTalk robot Webhook | DingTalk group notifications |
| `wechat` | WeChat Work robot Webhook | WeChat Work group notifications |
| `feishu` | Feishu robot Webhook | Feishu group notifications |
| `slack` | Slack Webhook | Slack channel notifications |
| `webhook` | Custom Webhook URL | Generic HTTP callback |

**Note**: External channels must be configured and enabled in their respective settings pages before they can be used in auto notifications.

## Notification Content

### Message Format

- **Title**: Contains site name and notification type
- **Content**: Supports Markdown format
- **Context**:
  - Team notifications include team name
  - User notifications include username

### Examples

**Team Member Added Notification**:
```
Title: [Clouisle] [Dev Team] You have joined a team
Content:
**Team**: Dev Team

You have been added to team **Dev Team** as **Member**.
```

**Login Anomaly Notification**:
```
Title: [Clouisle] [@admin] Anomalous login detected
Content:
**User**: admin

An anomalous login to your account was detected.

- **IP Address**: 192.168.1.100
- **Time**: 2026-02-04T10:30:00+08:00
- **Device Info**: Mozilla/5.0 (Windows NT 10.0; Win64; x64) ...

If this was not you, please change your password immediately.
```

## Technical Implementation

### Architecture

```
Business Module → AutoNotificationService → In-app Notification
                                         ↓
                                  External Channel Task (Celery)
                                         ↓
                           Email/DingTalk/WeChat/Feishu/Slack/Webhook
```

### Core Components

| Component | Path | Description |
|-----------|------|-------------|
| Notification Type Enum | `app/models/notification.py` | `AutoNotificationType` |
| Auto Notification Service | `app/services/auto_notification.py` | `AutoNotificationService` |
| Configuration Storage | `app/models/site_setting.py` | `auto_notification_config` |
| API Endpoint | `app/api/v1/endpoints/site_settings.py` | `/auto-notifications` |
| Login Anomaly Detection | `app/core/login_anomaly.py` | Login pattern analysis |
| API Key Check | `app/tasks/api_key.py` | Scheduled task |

### Usage Example

```python
from app.services.auto_notification import AutoNotificationService
from app.models.notification import AutoNotificationType, NotificationLevel
from app.core.i18n import t

# Send user-level notification
await AutoNotificationService.send_to_user(
    notification_type=AutoNotificationType.USER_ACTIVATED,
    user_id=user.id,
    title=t("notify_user_activated_title"),
    content=t("notify_user_activated_content", username=user.username),
    level=NotificationLevel.MEDIUM,
)

# Send team-level notification
await AutoNotificationService.send_to_team(
    notification_type=AutoNotificationType.TEAM_MEMBER_ADDED,
    team_id=team.id,
    title=t("notify_team_member_added_team_title"),
    content=t("notify_team_member_added_team_content",
              username=user.username,
              team_name=team.name),
    level=NotificationLevel.LOW,
)

# Send global notification
await AutoNotificationService.send_global(
    notification_type=AutoNotificationType.USER_PENDING_APPROVAL,
    title=t("notify_user_pending_approval_title"),
    content=t("notify_user_pending_approval_content", username=user.username),
    level=NotificationLevel.HIGH,
)
```

## Scheduled Tasks

### API Key Expiration Check

- **Task Name**: `tasks.check_api_key_expiration`
- **Schedule**: Daily at 09:00
- **Functions**:
  - Check API Keys expiring within 7 days, send reminders on day 7, 3, and 1
  - Check API Keys expired in past 24 hours, send expiration notification

### Configuration

In `app/core/celery.py`:

```python
celery_app.conf.beat_schedule = {
    "check-api-key-expiration": {
        "task": "tasks.check_api_key_expiration",
        "schedule": crontab(hour=9, minute=0),
    },
}
```

## Internationalization

All notification messages support multiple languages, translations defined in `app/core/i18n.py`:

```python
TRANSLATIONS = {
    "notify_team_member_added_title": {
        "en": "You have joined a team",
        "zh": "您已加入团队",
    },
    "notify_team_member_added_content": {
        "en": "You have been added to team **{team_name}** as **{role}**.",
        "zh": "您已被添加到团队 **{team_name}**，角色为 **{role}**。",
    },
    # ... more translations
}
```

## Default Configuration

The following notification types are enabled by default:

- `team.member_added`
- `team.member_removed`
- `team.role_changed`
- `team.ownership_transferred`
- `team.model_granted`
- `team.model_revoked`
- `user.activated`
- `user.deactivated`
- `user.password_reset`
- `user.pending_approval`
- `kb.doc_indexed`
- `kb.doc_failed`
- `workflow.run_failed`
- `apikey.expiring`
- `apikey.expired`
- `security.login_anomaly`
- `security.account_locked`
- `security.password_changed`

External channels are not enabled by default and require manual configuration by administrators.
