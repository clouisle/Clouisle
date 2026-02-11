# Audit Log Management

This guide covers how to manage and analyze audit logs as an administrator.

## Overview

As an administrator, you can:

- **View audit logs**: Access all system activity logs
- **Search logs**: Find specific events and actions
- **Filter logs**: Narrow down logs by criteria
- **Export logs**: Download logs for analysis
- **Archive logs**: Manage log retention
- **Monitor activity**: Track user and system actions
- **Generate reports**: Create audit reports

## Accessing Audit Logs

### Admin Dashboard

1. Log in as administrator
2. Navigate to **Admin** → **Audit Logs**
3. View audit log interface

### Audit Log View

The audit log shows:

- **Timestamp**: When action occurred
- **User**: Who performed the action
- **Action**: What was done
- **Resource Type**: Type of resource (user, agent, team, etc.)
- **Resource Name**: Name of affected resource
- **Operation**: Create, read, update, delete
- **Status**: Success or failure
- **IP Address**: Source IP
- **Details**: Additional information

## Audit Log Events

### Authentication Events

**Login Events:**
```yaml
Action: login_success
User: john.doe@example.com
Timestamp: 2026-02-11 14:30:00
IP Address: 192.168.1.100
User Agent: Mozilla/5.0...
Details:
  method: password
  2fa_used: true
```

```yaml
Action: login_failed
User: john.doe@example.com
Timestamp: 2026-02-11 14:29:55
IP Address: 192.168.1.100
Details:
  reason: invalid_password
  attempt: 1
```

**Logout Events:**
```yaml
Action: logout
User: john.doe@example.com
Timestamp: 2026-02-11 18:00:00
IP Address: 192.168.1.100
Details:
  session_duration: 3h 30m
```

**Registration Events:**
```yaml
Action: register
User: new.user@example.com
Timestamp: 2026-02-11 10:00:00
IP Address: 203.0.113.45
Details:
  method: email
  email_verified: false
```

### User Management Events

**User Creation:**
```yaml
Action: create_user
User: admin@example.com
Timestamp: 2026-02-11 11:00:00
Resource Type: user
Resource ID: user-789
Resource Name: alice.smith@example.com
Operation: create
Status: success
Changes:
  after:
    email: alice.smith@example.com
    full_name: Alice Smith
    role: user
    is_active: true
```

**User Update:**
```yaml
Action: update_user
User: admin@example.com
Timestamp: 2026-02-11 12:00:00
Resource Type: user
Resource ID: user-789
Resource Name: alice.smith@example.com
Operation: update
Status: success
Changes:
  before:
    role: user
    is_active: true
  after:
    role: admin
    is_active: true
```

**User Deletion:**
```yaml
Action: delete_user
User: admin@example.com
Timestamp: 2026-02-11 13:00:00
Resource Type: user
Resource ID: user-789
Resource Name: alice.smith@example.com
Operation: delete
Status: success
```

### Team Management Events

**Team Creation:**
```yaml
Action: create_team
User: admin@example.com
Timestamp: 2026-02-11 09:00:00
Resource Type: team
Resource ID: team-456
Resource Name: Engineering Team
Operation: create
Status: success
Changes:
  after:
    name: Engineering Team
    description: Engineering team
    owner_id: user-123
```

**Add Team Member:**
```yaml
Action: add_team_member
User: owner@example.com
Timestamp: 2026-02-11 10:00:00
Resource Type: team
Resource ID: team-456
Resource Name: Engineering Team
Operation: update
Status: success
Metadata:
  member_id: user-789
  member_email: alice.smith@example.com
  role: member
```

**Remove Team Member:**
```yaml
Action: remove_team_member
User: owner@example.com
Timestamp: 2026-02-11 11:00:00
Resource Type: team
Resource ID: team-456
Resource Name: Engineering Team
Operation: update
Status: success
Metadata:
  member_id: user-789
  member_email: alice.smith@example.com
  reason: Left company
```

### Agent Events

**Agent Creation:**
```yaml
Action: create_agent
User: john.doe@example.com
Timestamp: 2026-02-11 14:00:00
Resource Type: agent
Resource ID: agent-123
Resource Name: Customer Support Agent
Operation: create
Status: success
Metadata:
  team_id: team-456
  model: gpt-4-turbo
```

**Agent Update:**
```yaml
Action: update_agent
User: john.doe@example.com
Timestamp: 2026-02-11 15:00:00
Resource Type: agent
Resource ID: agent-123
Resource Name: Customer Support Agent
Operation: update
Status: success
Changes:
  before:
    temperature: 0.7
    max_tokens: 2048
  after:
    temperature: 0.8
    max_tokens: 4096
```

**Agent Publish:**
```yaml
Action: publish_agent
User: john.doe@example.com
Timestamp: 2026-02-11 16:00:00
Resource Type: agent
Resource ID: agent-123
Resource Name: Customer Support Agent
Operation: update
Status: success
Metadata:
  visibility: public
  marketplace: true
```

**Agent Deletion:**
```yaml
Action: delete_agent
User: john.doe@example.com
Timestamp: 2026-02-11 17:00:00
Resource Type: agent
Resource ID: agent-123
Resource Name: Customer Support Agent
Operation: delete
Status: success
```

### API Key Events

**API Key Creation:**
```yaml
Action: create_api_key
User: john.doe@example.com
Timestamp: 2026-02-11 10:00:00
Resource Type: api_key
Resource ID: key-789
Resource Name: Production API Key
Operation: create
Status: success
Metadata:
  scopes:
    - agent:read
    - agent:chat
    - workflow:execute
  expires_at: 2027-02-11
```

**API Key Activation:**
```yaml
Action: activate_api_key
User: john.doe@example.com
Timestamp: 2026-02-11 11:00:00
Resource Type: api_key
Resource ID: key-789
Resource Name: Production API Key
Operation: update
Status: success
```

**API Key Deactivation:**
```yaml
Action: deactivate_api_key
User: john.doe@example.com
Timestamp: 2026-02-11 12:00:00
Resource Type: api_key
Resource ID: key-789
Resource Name: Production API Key
Operation: update
Status: success
Metadata:
  reason: Security rotation
```

### System Settings Events

**Update Setting:**
```yaml
Action: update_site_setting
User: admin@example.com
Timestamp: 2026-02-11 09:00:00
Resource Type: setting
Resource Name: site_name
Operation: update
Status: success
Changes:
  before: Clouisle
  after: Clouisle Enterprise
```

**Bulk Update Settings:**
```yaml
Action: bulk_update_site_settings
User: admin@example.com
Timestamp: 2026-02-11 10:00:00
Resource Type: setting
Operation: update
Status: success
Metadata:
  settings_count: 5
  settings:
    - site_name
    - site_url
    - admin_email
    - support_email
    - default_language
```

**Reset Settings:**
```yaml
Action: reset_site_settings
User: admin@example.com
Timestamp: 2026-02-11 11:00:00
Resource Type: setting
Operation: update
Status: success
Metadata:
  category: email
  settings_reset: 8
```

### Security Events

**Password Change:**
```yaml
Action: change_password
User: john.doe@example.com
Timestamp: 2026-02-11 14:00:00
Resource Type: user
Resource ID: user-123
Operation: update
Status: success
IP Address: 192.168.1.100
```

**Password Reset:**
```yaml
Action: reset_password
User: john.doe@example.com
Timestamp: 2026-02-11 15:00:00
Resource Type: user
Resource ID: user-123
Operation: update
Status: success
Metadata:
  method: email_link
  initiated_by: user
```

**Account Activation:**
```yaml
Action: activate_user
User: admin@example.com
Timestamp: 2026-02-11 10:00:00
Resource Type: user
Resource ID: user-789
Resource Name: alice.smith@example.com
Operation: update
Status: success
```

**Account Deactivation:**
```yaml
Action: deactivate_user
User: admin@example.com
Timestamp: 2026-02-11 11:00:00
Resource Type: user
Resource ID: user-789
Resource Name: alice.smith@example.com
Operation: update
Status: success
Metadata:
  reason: Policy violation
```

## Searching and Filtering

### Search Audit Logs

**Search Options:**
- **Text Search**: Search in all fields
- **User**: Filter by user email
- **Action**: Filter by action type
- **Resource Type**: Filter by resource
- **Status**: Success or failure
- **Date Range**: Filter by time period
- **IP Address**: Filter by source IP

**Search Example:**
```bash
1. Navigate to Audit Logs
2. Enter search criteria:
   - User: john.doe@example.com
   - Action: delete_*
   - Date Range: Last 7 days
3. Click "Search"
4. View filtered results
```

### Advanced Filters

**Filter by Multiple Criteria:**
```yaml
Filters:
  User: john.doe@example.com OR jane.smith@example.com
  Action: create_agent OR update_agent OR delete_agent
  Resource Type: agent
  Status: success
  Date Range: 2026-02-01 to 2026-02-11
  IP Address: 192.168.1.*
```

**Filter by Changes:**
```yaml
Filters:
  Changed Field: role
  Before Value: user
  After Value: admin
  Date Range: Last 30 days
```

### Saved Searches

**Save Search:**
1. Configure search filters
2. Click **Save Search**
3. Enter search name
4. Save search

**Use Saved Search:**
1. Click **Saved Searches**
2. Select saved search
3. View results

**Saved Search Examples:**
- Failed login attempts
- Admin actions
- User deletions
- Permission changes
- High-value operations

## Viewing Audit Log Details

### Log Entry Details

**Click log entry to view full details:**

```yaml
Audit Log Entry: #12345

Basic Information:
  ID: log-12345
  Timestamp: 2026-02-11 14:30:00 UTC
  User: john.doe@example.com
  User ID: user-123
  Action: update_agent
  Status: success

Resource Information:
  Resource Type: agent
  Resource ID: agent-456
  Resource Name: Customer Support Agent
  Operation: update

Request Information:
  IP Address: 192.168.1.100
  User Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)
  Request ID: req-789
  Session ID: sess-012

Changes:
  before:
    temperature: 0.7
    max_tokens: 2048
    system_prompt: "You are a helpful assistant."
  after:
    temperature: 0.8
    max_tokens: 4096
    system_prompt: "You are a helpful customer support agent."

Metadata:
  team_id: team-456
  team_name: Support Team
  model: gpt-4-turbo
  duration: 1.2s
```

### Related Logs

View related audit logs:

1. Click log entry
2. Click **Related Logs** tab
3. View logs related to:
   - Same user
   - Same resource
   - Same session
   - Same time period

## Exporting Audit Logs

### Export Options

**Export Formats:**
- CSV
- JSON
- PDF (report format)
- Excel

**Export Logs:**
1. Apply filters (optional)
2. Click **Export**
3. Select format
4. Choose fields to include
5. Click **Download**

**CSV Export Example:**
```csv
timestamp,user,action,resource_type,resource_name,status,ip_address
2026-02-11 14:30:00,john.doe@example.com,update_agent,agent,Customer Support Agent,success,192.168.1.100
2026-02-11 14:25:00,jane.smith@example.com,create_workflow,workflow,Customer Processing,success,192.168.1.101
```

**JSON Export Example:**
```json
[
  {
    "id": "log-12345",
    "timestamp": "2026-02-11T14:30:00Z",
    "user": "john.doe@example.com",
    "user_id": "user-123",
    "action": "update_agent",
    "resource_type": "agent",
    "resource_id": "agent-456",
    "resource_name": "Customer Support Agent",
    "operation": "update",
    "status": "success",
    "ip_address": "192.168.1.100",
    "changes": {
      "before": {"temperature": 0.7},
      "after": {"temperature": 0.8}
    }
  }
]
```

### Scheduled Exports

**Create Scheduled Export:**
1. Navigate to **Audit Logs** → **Exports**
2. Click **Schedule Export**
3. Configure:
   - Export name
   - Filters
   - Format
   - Schedule (daily, weekly, monthly)
   - Delivery method (email, S3, etc.)
4. Save schedule

**Scheduled Export Example:**
```yaml
Export Name: Weekly Admin Actions
Filters:
  Action: create_user, update_user, delete_user, update_site_setting
  Date Range: Last 7 days
Format: CSV
Schedule: Every Monday at 9 AM
Delivery: Email to admin@example.com
```

## Audit Reports

### Generate Report

**Report Types:**
- User activity report
- Admin actions report
- Security events report
- Resource changes report
- Failed operations report
- Custom report

**Generate Report:**
1. Navigate to **Audit Logs** → **Reports**
2. Select report type
3. Configure parameters:
   - Date range
   - Users (optional)
   - Actions (optional)
   - Resource types (optional)
4. Click **Generate Report**
5. View or download report

### User Activity Report

**Report Contents:**
```yaml
Report: User Activity Report
Period: 2026-02-01 to 2026-02-11
Generated: 2026-02-11 16:00:00

Summary:
  Total Users: 45
  Active Users: 38
  Total Actions: 12,345
  Failed Actions: 23

Top Users by Activity:
  1. john.doe@example.com: 1,234 actions
  2. jane.smith@example.com: 987 actions
  3. bob.wilson@example.com: 765 actions

Actions by Type:
  agent:chat: 5,678 (46%)
  kb:search: 2,345 (19%)
  workflow:execute: 1,234 (10%)
  agent:update: 987 (8%)
  Other: 2,101 (17%)

Actions by Day:
  2026-02-11: 1,456
  2026-02-10: 1,234
  2026-02-09: 1,123
  ...
```

### Security Events Report

**Report Contents:**
```yaml
Report: Security Events Report
Period: 2026-02-01 to 2026-02-11

Failed Login Attempts:
  Total: 45
  Unique Users: 12
  Unique IPs: 8

Top Failed Logins:
  john.doe@example.com: 15 attempts
  jane.smith@example.com: 10 attempts

Password Changes:
  Total: 23
  User-initiated: 20
  Admin-initiated: 3

Permission Changes:
  Total: 15
  Granted: 10
  Revoked: 5

Account Status Changes:
  Activated: 5
  Deactivated: 2
  Locked: 1
```

## Log Retention and Archival

### Retention Policy

**Default Retention:**
```yaml
Retention Policy:
  Active Logs: 90 days
  Archived Logs: 7 years
  Compliance Logs: Indefinite
```

**Configure Retention:**
1. Navigate to **Admin** → **Settings** → **Audit Logs**
2. Configure retention:
   - Active log retention (days)
   - Archive retention (years)
   - Compliance log retention
3. Save settings

### Archive Logs

**Manual Archive:**
1. Navigate to **Audit Logs** → **Archive**
2. Select date range to archive
3. Choose archive location:
   - Local storage
   - S3
   - Azure Blob
4. Click **Archive**

**Automatic Archive:**
```yaml
Archive Schedule: Daily at 2 AM
Archive Logs Older Than: 90 days
Archive Location: S3
Bucket: clouisle-audit-logs
Compression: gzip
Encryption: AES-256
```

**Trigger Archive:**
```yaml
Action: trigger_audit_log_archive
User: admin@example.com
Timestamp: 2026-02-11 02:00:00
Status: success
Metadata:
  logs_archived: 45,678
  date_range: 2025-11-01 to 2026-01-31
  archive_size: 125 MB
  archive_location: s3://clouisle-audit-logs/2026-02/archive-20260211.gz
```

### Restore Archived Logs

**Restore Logs:**
1. Navigate to **Audit Logs** → **Archive**
2. Select archive to restore
3. Choose date range
4. Click **Restore**
5. Wait for restoration
6. View restored logs

## Monitoring and Alerts

### Real-time Monitoring

**Monitor Dashboard:**
- Recent activity (last 5 minutes)
- Failed operations
- Security events
- Admin actions
- High-value operations

**Real-time Alerts:**
```yaml
Alert: Multiple Failed Login Attempts
User: john.doe@example.com
Count: 5 attempts in 2 minutes
IP Address: 203.0.113.45
Action: Account locked
Notification: Email sent to admin
```

### Configure Alerts

**Alert Types:**
- Failed login threshold
- Admin action performed
- User deleted
- Permission changed
- High-value operation
- Unusual activity pattern

**Create Alert:**
1. Navigate to **Audit Logs** → **Alerts**
2. Click **Create Alert**
3. Configure:
   - Alert name
   - Trigger conditions
   - Threshold
   - Notification method
   - Recipients
4. Save alert

**Alert Example:**
```yaml
Alert Name: Failed Login Threshold
Trigger: login_failed
Condition: Count > 5 in 5 minutes
Notification: Email, Slack
Recipients:
  - admin@example.com
  - security@example.com
Action: Lock account after 5 attempts
```

## Best Practices

### Audit Logging

**✅ Do:**
- Enable audit logging for all actions
- Log both successes and failures
- Include sufficient context
- Protect log integrity
- Review logs regularly
- Archive logs appropriately
- Monitor for anomalies
- Set up alerts for critical events

**❌ Don't:**
- Disable audit logging
- Log only failures
- Skip important context
- Allow log tampering
- Ignore logs
- Delete logs prematurely
- Miss anomalies
- Forget to set alerts

### Log Analysis

**✅ Do:**
- Review logs regularly
- Look for patterns
- Investigate anomalies
- Generate regular reports
- Share findings with team
- Document incidents
- Use logs for compliance

**❌ Don't:**
- Ignore logs
- Miss patterns
- Dismiss anomalies
- Skip reports
- Keep findings private
- Forget to document
- Neglect compliance

### Security

**✅ Do:**
- Restrict log access
- Encrypt archived logs
- Use secure storage
- Monitor log access
- Audit the auditors
- Maintain log integrity
- Comply with regulations

**❌ Don't:**
- Allow unrestricted access
- Store logs unencrypted
- Use insecure storage
- Ignore log access
- Skip auditor auditing
- Allow log tampering
- Ignore regulations

## Related Documentation

- [Permission Management](../permissions/permission-management.md) - Permission admin
- [Security Best Practices](../../best-practices/security.md) - Security guide
- [User Management](../users/user-management.md) - User admin
- [Compliance](../../best-practices/compliance.md) - Compliance guide

---

**Last Updated**: 2026-02-11
