# Notifications

This guide explains how to manage and configure notifications in Clouisle.

## Overview

Notifications keep you informed about:

- **Messages**: New chat messages and mentions
- **Workflows**: Workflow execution results
- **Teams**: Team invitations and updates
- **Documents**: Document processing status
- **System**: Important system announcements
- **Security**: Login alerts and security events

## Notification Types

### In-App Notifications

**Displayed in the application:**
- Bell icon in navigation bar
- Badge shows unread count
- Real-time updates
- Persistent until dismissed

**Notification center:**
```
┌─────────────────────────────────────────┐
│ 🔔 Notifications (5)        [Mark All] │
├─────────────────────────────────────────┤
│                                         │
│ 🤖 New message from Support Agent      │
│    "Your request has been processed"   │
│    2 minutes ago                        │
│    [View] [Dismiss]                     │
│                                         │
│ ✅ Workflow completed                   │
│    "Document Summarizer" finished      │
│    1 hour ago                           │
│    [View Results] [Dismiss]             │
│                                         │
│ 👥 Team invitation                      │
│    Alice invited you to "Marketing"    │
│    3 hours ago                          │
│    [Accept] [Decline]                   │
│                                         │
│ 📄 Document processed                   │
│    "sales_report.pdf" is ready         │
│    Yesterday                            │
│    [View] [Dismiss]                     │
│                                         │
│ 🔒 New login detected                   │
│    From New York, NY                    │
│    2 days ago                           │
│    [Review] [Dismiss]                   │
│                                         │
│ [View All Notifications]                │
│                                         │
└─────────────────────────────────────────┘
```

### Email Notifications

**Sent to your email address:**
- Configurable frequency
- Digest options available
- Unsubscribe links included
- HTML and plain text formats

**Email example:**
```
Subject: New message from Support Agent

Hello John,

You have a new message from Support Agent:

"Your request has been processed. The document is now
available in your knowledge base."

View Message: [Click Here]

---
Clouisle Notifications
Manage preferences: [Settings]
```

### Push Notifications

**For mobile devices (if app installed):**
- Real-time alerts
- Lock screen notifications
- Badge updates
- Sound and vibration

### Desktop Notifications

**Browser notifications:**
- Appear on desktop
- Require permission
- Can be disabled per site
- Work when browser is open

**Desktop notification:**
```
┌─────────────────────────────────────────┐
│ Clouisle                                │
├─────────────────────────────────────────┤
│                                         │
│ 🤖 New message from Support Agent      │
│                                         │
│ "Your request has been processed"      │
│                                         │
│ [View] [Dismiss]                        │
│                                         │
└─────────────────────────────────────────┘
```

## Accessing Notifications

### Notification Center

**Steps:**

1. Click the **bell icon** (🔔) in navigation bar
2. Notification panel opens
3. View all recent notifications
4. Click on notification to view details

**Badge indicator:**
- Red badge shows unread count
- Disappears when all read
- Updates in real-time

### Notification List

**View all notifications:**

1. Click **"View All Notifications"** in panel
2. Full notification page opens
3. View complete history
4. Filter and search notifications

**Or:**

- Navigate directly to `/notifications`

## Managing Notifications

### Reading Notifications

**Mark as read:**

1. Click on notification
2. Automatically marked as read
3. Badge count decreases

**Mark all as read:**

1. Click **"Mark All Read"** button
2. All notifications marked as read
3. Badge disappears

### Dismissing Notifications

**Dismiss single notification:**

1. Hover over notification
2. Click **"Dismiss"** or **"X"** button
3. Notification is removed

**Dismiss all:**

1. Click **"..."** menu
2. Select **"Dismiss All"**
3. All notifications are removed

**Note**: Dismissed notifications can be viewed in history.

### Notification Actions

**Quick actions:**

| Notification Type | Actions |
|-------------------|---------|
| **Message** | View, Reply, Dismiss |
| **Workflow** | View Results, Replay, Dismiss |
| **Team Invitation** | Accept, Decline |
| **Document** | View, Download, Dismiss |
| **Security Alert** | Review, Dismiss |

## Notification Settings

### Accessing Settings

**Steps:**

1. Go to **Profile Settings** → **Notifications** tab
2. Or click **"Settings"** in notification panel
3. Configure notification preferences

**Or:**

- Navigate directly to `/settings/notifications`

### Email Notifications

**Configure email preferences:**

```
┌─────────────────────────────────────────┐
│ Email Notifications                     │
├─────────────────────────────────────────┤
│                                         │
│ ☑ Enable email notifications            │
│                                         │
│ Notification Types:                     │
│ ☑ New messages                          │
│ ☑ Mentions and replies                  │
│ ☑ Workflow completions                  │
│ ☑ Workflow failures                     │
│ ☑ Team invitations                      │
│ ☑ Document processing                   │
│ ☑ Security alerts                       │
│ ☐ Marketing emails                      │
│ ☐ Product updates                       │
│                                         │
│ Frequency:                              │
│ ● Real-time (immediate)                 │
│ ○ Hourly digest                         │
│ ○ Daily digest (9:00 AM)                │
│ ○ Weekly digest (Monday 9:00 AM)        │
│                                         │
│ [Save Preferences]                      │
│                                         │
└─────────────────────────────────────────┘
```

### In-App Notifications

**Configure in-app preferences:**

```
┌─────────────────────────────────────────┐
│ In-App Notifications                    │
├─────────────────────────────────────────┤
│                                         │
│ ☑ Enable in-app notifications           │
│                                         │
│ Notification Types:                     │
│ ☑ New messages                          │
│ ☑ Mentions                              │
│ ☑ Workflow updates                      │
│ ☑ Team updates                          │
│ ☑ Document updates                      │
│ ☑ System alerts                         │
│                                         │
│ Display:                                │
│ ☑ Show badge on bell icon               │
│ ☑ Play sound                            │
│ ☑ Show preview in notification          │
│                                         │
│ [Save Preferences]                      │
│                                         │
└─────────────────────────────────────────┘
```

### Desktop Notifications

**Enable desktop notifications:**

1. Go to **Notifications Settings**
2. Find **"Desktop Notifications"** section
3. Click **"Enable Desktop Notifications"**
4. Browser asks for permission
5. Click **"Allow"**

**Desktop notification settings:**

```
┌─────────────────────────────────────────┐
│ Desktop Notifications                   │
├─────────────────────────────────────────┤
│                                         │
│ Status: ✅ Enabled                      │
│                                         │
│ ☑ New messages                          │
│ ☑ Mentions                              │
│ ☑ Workflow completions                  │
│ ☐ All notifications                     │
│                                         │
│ Options:                                │
│ ☑ Play sound                            │
│ ☑ Show preview                          │
│                                         │
│ [Disable] [Test Notification]           │
│                                         │
└─────────────────────────────────────────┘
```

### Push Notifications

**For mobile app:**

1. Install Clouisle mobile app
2. Open app settings
3. Enable push notifications
4. Grant permission when prompted
5. Configure notification types

**Push notification settings:**

```
┌─────────────────────────────────────────┐
│ Push Notifications                      │
├─────────────────────────────────────────┤
│                                         │
│ Status: ✅ Enabled                      │
│                                         │
│ ☑ New messages                          │
│ ☑ Mentions                              │
│ ☑ Workflow updates                      │
│ ☑ Team invitations                      │
│ ☑ Security alerts                       │
│                                         │
│ Options:                                │
│ ☑ Sound                                 │
│ ☑ Vibration                             │
│ ☑ Badge                                 │
│                                         │
│ Quiet Hours:                            │
│ ☑ Enable quiet hours                    │
│   From: [22:00] To: [08:00]            │
│                                         │
│ [Save Settings]                         │
│                                         │
└─────────────────────────────────────────┘
```

## Notification Categories

### Message Notifications

**When you receive:**
- New chat messages
- Mentions (@username)
- Replies to your messages
- Direct messages

**Settings:**
- Enable/disable per conversation
- Mute specific conversations
- Customize mention notifications

### Workflow Notifications

**When workflows:**
- Complete successfully
- Fail with errors
- Are manually stopped
- Reach specific milestones

**Settings:**
- Enable/disable per workflow
- Only notify on failures
- Include execution details

### Team Notifications

**When:**
- Invited to team
- Team member joins/leaves
- Role changes
- Team settings updated

**Settings:**
- Enable/disable per team
- Only important updates
- Digest mode available

### Document Notifications

**When documents:**
- Finish processing
- Fail to process
- Are shared with you
- Are updated

**Settings:**
- Enable/disable per knowledge base
- Only notify on failures
- Batch notifications

### Security Notifications

**When:**
- New login detected
- Login from new location
- Password changed
- API key created/revoked
- Suspicious activity detected

**Settings:**
- Always enabled (cannot disable)
- Email always sent
- Immediate delivery

## Notification Preferences

### Per-Conversation Settings

**Mute conversations:**

1. Open conversation
2. Click **"..."** menu
3. Select **"Mute Notifications"**
4. Choose duration:
   - 1 hour
   - 8 hours
   - 24 hours
   - Until I unmute
5. Notifications are muted

**Unmute:**

1. Open conversation
2. Click **"..."** menu
3. Select **"Unmute Notifications"**

### Per-Workflow Settings

**Configure workflow notifications:**

1. Open workflow
2. Go to **Settings** tab
3. Find **"Notifications"** section
4. Configure:
   - Notify on completion
   - Notify on failure
   - Notify specific users
   - Include execution details
5. Save settings

### Per-Team Settings

**Configure team notifications:**

1. Go to team settings
2. Find **"Notifications"** section
3. Configure:
   - Member changes
   - Role changes
   - Team updates
4. Save settings

## Notification History

### Viewing History

**Access notification history:**

1. Go to **Notifications** page
2. Click **"History"** tab
3. View all past notifications

**History view:**

```
┌─────────────────────────────────────────┐
│ Notification History        [Filters ▼] │
├─────────────────────────────────────────┤
│                                         │
│ Today                                   │
│ ─────────────────────────────────────  │
│ 🤖 New message from Support Agent      │
│    2 hours ago • Read                   │
│                                         │
│ ✅ Workflow completed                   │
│    5 hours ago • Read                   │
│                                         │
│ Yesterday                               │
│ ─────────────────────────────────────  │
│ 📄 Document processed                   │
│    Yesterday • Read                     │
│                                         │
│ 👥 Team invitation                      │
│    Yesterday • Accepted                 │
│                                         │
│ This Week                               │
│ ─────────────────────────────────────  │
│ 🔒 New login detected                   │
│    3 days ago • Reviewed                │
│                                         │
│ [Load More]                             │
│                                         │
└─────────────────────────────────────────┘
```

### Filtering History

**Filter options:**

| Filter | Options |
|--------|---------|
| **Type** | Messages, Workflows, Teams, Documents, Security |
| **Status** | Unread, Read, Dismissed |
| **Date** | Today, This week, This month, Custom |
| **Action** | Pending, Completed, Dismissed |

### Searching History

**Search notifications:**

1. Enter search term in search bar
2. Search by:
   - Content
   - Sender
   - Type
   - Date
3. Results update in real-time

## Quiet Hours

### Setting Quiet Hours

**Configure do-not-disturb:**

1. Go to **Notifications Settings**
2. Find **"Quiet Hours"** section
3. Enable quiet hours
4. Set time range
5. Select notification types to silence
6. Save settings

**Quiet hours settings:**

```
┌─────────────────────────────────────────┐
│ Quiet Hours                             │
├─────────────────────────────────────────┤
│                                         │
│ ☑ Enable quiet hours                    │
│                                         │
│ Time Range:                             │
│ From: [22:00] To: [08:00]              │
│                                         │
│ Days:                                   │
│ ☑ Monday - Friday                       │
│ ☑ Saturday - Sunday                     │
│                                         │
│ Silence:                                │
│ ☑ Desktop notifications                 │
│ ☑ Push notifications                    │
│ ☑ Sounds                                │
│ ☐ Email notifications                   │
│                                         │
│ Exceptions:                             │
│ ☑ Security alerts (always notify)       │
│ ☑ Critical workflow failures            │
│                                         │
│ [Save Settings]                         │
│                                         │
└─────────────────────────────────────────┘
```

### Manual Do Not Disturb

**Temporarily silence notifications:**

1. Click bell icon
2. Click **"Do Not Disturb"** button
3. Select duration:
   - 30 minutes
   - 1 hour
   - 4 hours
   - Until tomorrow
   - Custom
4. Notifications are silenced

**DND indicator:**

```
🔕 Do Not Disturb (2 hours remaining)
```

## Best Practices

### Managing Notifications

**✅ Do:**
- Configure preferences early
- Use quiet hours for focus time
- Mute non-urgent conversations
- Review security alerts immediately
- Keep email notifications for important events
- Use digest mode for less urgent updates

**❌ Don't:**
- Disable all notifications
- Ignore security alerts
- Leave all conversations unmuted
- Forget to check notification center
- Dismiss without reading
- Disable email for critical events

### Staying Organized

**✅ Do:**
- Mark notifications as read regularly
- Dismiss processed notifications
- Use filters to find specific notifications
- Set up quiet hours
- Configure per-conversation settings
- Review notification history periodically

**❌ Don't:**
- Let notifications accumulate
- Ignore unread badge
- Keep all notifications forever
- Use same settings for all conversations
- Forget to update preferences

## Troubleshooting

### Not Receiving Notifications

**Problem**: No notifications appearing

**Solutions:**
1. Check notification settings are enabled
2. Verify email address is correct
3. Check spam/junk folder for emails
4. Verify browser permissions for desktop notifications
5. Check quiet hours settings
6. Refresh the page
7. Contact administrator

### Desktop Notifications Not Working

**Problem**: Browser notifications don't appear

**Solutions:**
1. Check browser permissions
2. Enable notifications in browser settings
3. Check system notification settings
4. Verify Clouisle has permission
5. Test with test notification button
6. Try different browser
7. Check if blocked by browser extension

### Too Many Notifications

**Problem**: Overwhelmed by notifications

**Solutions:**
1. Enable digest mode for emails
2. Mute non-urgent conversations
3. Disable less important notification types
4. Use quiet hours
5. Configure per-conversation settings
6. Adjust notification frequency

### Email Notifications Delayed

**Problem**: Emails arrive late

**Solutions:**
1. Check email provider's spam filters
2. Verify email address is correct
3. Check digest settings (may be batched)
4. Contact administrator
5. Check email server status

## Related Documentation

- [Profile Settings](../profile/profile-settings.md) - Account settings
- [Chatting with Agents](../chat/chatting-with-agents.md) - Chat notifications
- [Workflow History](../workflows/workflow-history.md) - Workflow notifications
- [Team Collaboration](../teams/team-collaboration.md) - Team notifications

## Getting Help

If you need assistance with notifications:

1. **Documentation**: Review this guide
2. **Settings Help**: Click **?** icon in notification settings
3. **Support**: Contact your organization's support team
4. **Administrator**: Reach out to your Clouisle administrator

---

**Last Updated**: 2026-02-11
