# Notification Preferences

This guide explains how to configure notification preferences to stay informed about important events.

## Overview

Notification preferences control how and when you receive notifications about system events, team activities, and resource updates. Proper configuration ensures you stay informed without being overwhelmed.

## Accessing Notification Settings

1. Click your **Profile** icon
2. Select **Settings**
3. Go to **Notifications** tab

## Notification Channels

### Email Notifications

**Email Settings:**
- Primary email address
- Notification email (optional)
- Email frequency
- Email format (HTML/Plain text)

**Configuration:**
```yaml
Primary Email: user@example.com
Notification Email: notifications@example.com
Frequency: Immediate
Format: HTML
Unsubscribe Link: Enabled
```

### In-App Notifications

**Notification Center:**
- Real-time notifications
- Notification badge
- Sound alerts
- Desktop notifications

**Configuration:**
```yaml
In-App Enabled: true
Show Badge: true
Play Sound: true
Desktop Notifications: true
```

### Push Notifications

**Mobile/Desktop Push:**
- Browser push notifications
- Mobile app notifications
- Critical alerts only

**Configuration:**
```yaml
Push Enabled: true
Browser Push: true
Mobile Push: true
Critical Only: false
```

### Webhook Notifications

**Custom Webhooks:**
- Send notifications to external services
- Custom payload format
- Retry policy

**Configuration:**
```yaml
Webhook URL: https://your-domain.com/webhooks
Events: [agent.created, workflow.completed]
Retry: 3 attempts
Timeout: 30 seconds
```

## Notification Categories

### Agent Notifications

**Agent Events:**
- Agent created
- Agent updated
- Agent deleted
- Agent published
- Agent unpublished
- Agent error

**Configuration:**
```yaml
Agent Notifications:
  Created: Email + In-App
  Updated: In-App
  Deleted: Email + In-App
  Published: Email
  Unpublished: Email
  Error: Email + In-App + Push
```

### Conversation Notifications

**Conversation Events:**
- New conversation
- New message
- Conversation completed
- Mention in conversation
- Conversation assigned

**Configuration:**
```yaml
Conversation Notifications:
  New Conversation: In-App
  New Message: In-App
  Completed: Email (Daily Digest)
  Mentioned: Email + In-App + Push
  Assigned: Email + In-App
```

### Workflow Notifications

**Workflow Events:**
- Workflow created
- Workflow started
- Workflow completed
- Workflow failed
- Workflow timeout

**Configuration:**
```yaml
Workflow Notifications:
  Created: In-App
  Started: In-App
  Completed: Email + In-App
  Failed: Email + In-App + Push
  Timeout: Email + In-App + Push
```

### Knowledge Base Notifications

**KB Events:**
- Document uploaded
- Document processed
- Document failed
- KB updated
- Storage limit reached

**Configuration:**
```yaml
KB Notifications:
  Document Uploaded: In-App
  Document Processed: Email (Daily Digest)
  Document Failed: Email + In-App
  KB Updated: In-App
  Storage Limit: Email + Push
```

### Team Notifications

**Team Events:**
- Member joined
- Member left
- Role changed
- Team settings changed
- Invitation sent

**Configuration:**
```yaml
Team Notifications:
  Member Joined: Email + In-App
  Member Left: Email + In-App
  Role Changed: Email + In-App
  Settings Changed: Email
  Invitation Sent: In-App
```

### Security Notifications

**Security Events:**
- Login from new device
- Password changed
- 2FA enabled/disabled
- API key created
- Suspicious activity

**Configuration:**
```yaml
Security Notifications:
  New Device Login: Email + Push
  Password Changed: Email + Push
  2FA Changed: Email + Push
  API Key Created: Email
  Suspicious Activity: Email + Push
```

### System Notifications

**System Events:**
- Maintenance scheduled
- Service disruption
- Feature updates
- Plan changes
- Billing alerts

**Configuration:**
```yaml
System Notifications:
  Maintenance: Email + In-App
  Disruption: Email + In-App + Push
  Feature Updates: Email (Weekly)
  Plan Changes: Email
  Billing Alerts: Email + Push
```

## Notification Frequency

### Immediate

**Real-time notifications:**
- Sent as events occur
- Best for: Critical events
- Channels: All

**Use for:**
- Security alerts
- Workflow failures
- Mentions
- Assignments

### Hourly Digest

**Batched notifications:**
- Sent every hour
- Best for: Moderate activity
- Channels: Email, In-App

**Use for:**
- New messages
- Document processing
- Minor updates

### Daily Digest

**Daily summary:**
- Sent once per day
- Best for: Low priority events
- Channels: Email

**Time:** 9:00 AM (configurable)

**Use for:**
- Conversation summaries
- Usage statistics
- Non-critical updates

### Weekly Digest

**Weekly summary:**
- Sent once per week
- Best for: Informational updates
- Channels: Email

**Day:** Monday (configurable)

**Use for:**
- Feature updates
- Team activity summary
- Usage reports

### Custom Schedule

**Custom timing:**
- Define your own schedule
- Multiple schedules per category
- Timezone-aware

**Example:**
```yaml
Custom Schedule:
  Workflow Reports:
    Frequency: Daily
    Time: "18:00"
    Timezone: America/New_York
    Days: [Monday, Wednesday, Friday]
```

## Notification Preferences

### Do Not Disturb

**Quiet Hours:**
- Disable notifications during specific hours
- Exceptions for critical alerts
- Timezone-aware

**Configuration:**
```yaml
Do Not Disturb:
  Enabled: true
  Start Time: "22:00"
  End Time: "08:00"
  Timezone: America/New_York
  Days: [Monday, Tuesday, Wednesday, Thursday, Friday]
  Exceptions:
    - Security alerts
    - Workflow failures
```

### Notification Grouping

**Group Similar Notifications:**
- Combine related notifications
- Reduce notification volume
- Configurable grouping window

**Configuration:**
```yaml
Grouping:
  Enabled: true
  Window: 5 minutes
  Max Group Size: 10
  Group By: [event_type, resource_id]
```

### Priority Levels

**Notification Priority:**
- Critical: Always notify
- High: Notify unless DND
- Medium: Respect all settings
- Low: Digest only

**Configuration:**
```yaml
Priority Levels:
  Security Alerts: Critical
  Workflow Failures: High
  New Messages: Medium
  Document Processed: Low
```

## Email Templates

### Customize Email Format

**Email Preferences:**
- HTML or plain text
- Include logo
- Custom footer
- Unsubscribe link

**Template Customization:**
```yaml
Email Template:
  Format: HTML
  Include Logo: true
  Header Color: #0066cc
  Footer Text: "Clouisle Team"
  Unsubscribe Link: true
  Social Links: true
```

### Email Content

**What to Include:**
- Event summary
- Action buttons
- Related resources
- Quick actions
- Unsubscribe link

**Example Email:**
```
Subject: Workflow "Customer Inquiry Handler" Failed

Hi John,

Your workflow "Customer Inquiry Handler" failed during execution.

Error: Connection timeout to external API
Execution ID: wf-exec-123
Started: 2026-02-11 16:00:00
Duration: 45 seconds

[View Details] [Retry Workflow] [View Logs]

---
Clouisle Team
[Unsubscribe] [Notification Settings]
```

## Mobile App Notifications

### Push Notification Settings

**Mobile Configuration:**
- Enable push notifications
- Notification sound
- Vibration
- Badge count

**Configuration:**
```yaml
Mobile Push:
  Enabled: true
  Sound: Default
  Vibration: true
  Badge: true
  Lock Screen: true
```

### Mobile Notification Categories

**Category Settings:**
- Critical: Always show
- Important: Show unless DND
- Normal: Respect settings
- Low: Silent notification

## Notification Management

### Notification History

**View Past Notifications:**
1. Click **Notifications** icon
2. View notification list
3. Filter by type/date
4. Mark as read/unread

**History Retention:**
- In-app: 30 days
- Email: Permanent (in inbox)
- Push: Device-dependent

### Mark as Read

**Bulk Actions:**
- Mark all as read
- Mark by category
- Mark by date range
- Delete notifications

### Notification Search

**Search Notifications:**
- By keyword
- By type
- By date
- By resource

## Advanced Settings

### Notification Rules

**Custom Rules:**
- Create conditional notifications
- Filter by metadata
- Custom actions

**Example Rule:**
```yaml
Rule: High Priority Workflows
Condition:
  Event: workflow.failed
  Metadata:
    priority: high
Action:
  Notify: Email + Push
  Escalate After: 5 minutes
  Escalate To: team-admins
```

### Notification Webhooks

**Custom Webhook Integration:**
```python
# Webhook payload
{
  "event": "workflow.failed",
  "timestamp": "2026-02-11T16:00:00Z",
  "data": {
    "workflow_id": "wf-123",
    "execution_id": "wf-exec-456",
    "error": "Connection timeout"
  },
  "user": {
    "id": "user-123",
    "email": "user@example.com"
  }
}
```

### Notification API

**Programmatic Access:**
```python
# Get notifications
notifications = api.get('/api/v1/notifications', params={
    'unread': True,
    'category': 'workflow',
    'page': 1,
    'page_size': 20
})

# Mark as read
api.patch('/api/v1/notifications/notif-123', json={
    'read': True
})

# Delete notification
api.delete('/api/v1/notifications/notif-123')
```

## Notification Best Practices

### Configuration

**✅ Do:**
- Enable critical notifications
- Use digest for low priority
- Set up Do Not Disturb
- Group similar notifications
- Test notification settings
- Review settings regularly
- Use appropriate channels

**❌ Don't:**
- Enable all notifications
- Use immediate for everything
- Skip Do Not Disturb
- Disable grouping
- Ignore notification settings
- Never review settings
- Use same channel for all

### Email Management

**✅ Do:**
- Use filters/labels
- Set up email rules
- Unsubscribe from unwanted
- Use digest for bulk
- Keep inbox organized
- Archive old notifications
- Use search effectively

**❌ Don't:**
- Let emails pile up
- Ignore all notifications
- Subscribe to everything
- Use immediate for all
- Delete without reading
- Keep all notifications
- Skip email organization

### Mobile Notifications

**✅ Do:**
- Enable critical only
- Use Do Not Disturb
- Customize sounds
- Group notifications
- Clear regularly
- Use quick actions
- Manage badge count

**❌ Don't:**
- Enable all notifications
- Ignore Do Not Disturb
- Use same sound for all
- Disable grouping
- Let notifications accumulate
- Ignore quick actions
- Keep all badges

## Notification Examples

### Critical Alert

```
🚨 CRITICAL: Workflow Failed

Workflow: Customer Inquiry Handler
Error: Database connection timeout
Impact: 15 pending inquiries
Action Required: Immediate

[View Details] [Retry] [Contact Support]
```

### Daily Digest

```
📊 Daily Summary - February 11, 2026

Conversations: 45 new messages
Workflows: 12 completed, 1 failed
Documents: 8 processed
Team: 2 new members

[View Dashboard] [Notification Settings]
```

### Mention Notification

```
💬 You were mentioned in a conversation

John Doe mentioned you in "Customer Support"
"@jane Can you help with this API integration issue?"

[View Conversation] [Reply]
```

## Troubleshooting

### Not Receiving Notifications

**Problem:** Notifications not arriving

**Solutions:**
1. Check notification settings enabled
2. Verify email address correct
3. Check spam/junk folder
4. Verify Do Not Disturb settings
5. Check browser permissions
6. Test with different channel

### Too Many Notifications

**Problem:** Overwhelmed by notifications

**Solutions:**
1. Enable Do Not Disturb
2. Use digest instead of immediate
3. Disable low priority notifications
4. Enable notification grouping
5. Unsubscribe from unwanted
6. Adjust priority levels

### Delayed Notifications

**Problem:** Notifications arrive late

**Solutions:**
1. Check internet connection
2. Verify email server not delayed
3. Check digest settings
4. Review notification queue
5. Contact support if persistent

## Related Documentation

- [Team Settings](./team-settings.md) - Team configuration
- [User Profile](./user-profile.md) - Profile settings
- [Security Settings](../../admin-guide/settings/system-settings.md) - Security configuration
- [Webhooks Guide](../../api-reference/webhooks-guide.md) - Webhook integration

---

**Last Updated**: 2026-02-11
