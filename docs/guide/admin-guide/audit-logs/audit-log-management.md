# Audit Log Management

This guide covers how to manage and analyze audit logs as an administrator.

## Overview

As an administrator, you can:

- **View audit logs**: Access all system activity logs
- **Search logs**: Find specific events and actions
- **Filter logs**: Narrow down logs by criteria
- **Export logs**: Download logs for analysis (CSV or JSON)
- **Archive logs**: Manage log retention
- **Monitor activity**: Track user and system actions
- **Inspect changes**: Review field-level before/after changes with sensitive data redacted

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
    role: Member
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
    role: Member
    is_active: true
  after:
    role: Admin
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
    max_iterations: 5
    system_prompt: "You are a helpful assistant."
  after:
    max_iterations: 8
    system_prompt: "You are a helpful customer support agent."
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
    - chat
  agent_count: 2
  workflow_count: 1
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

The audit log list endpoint (`GET /api/v1/admin/audit-logs`) supports the following query parameters:

| Parameter | Description |
|-----------|-------------|
| `user_id` | Filter by user UUID |
| `team_id` | Filter by team UUID |
| `action` | Filter by exact action values; the API applies an `action__in` match for repeated values (wildcards are not supported) |
| `resource_type` | Filter by resource type (user, team, agent, workflow, etc.) |
| `resource_id` | Filter by resource UUID |
| `status` | Filter by status (`success`, `failed`, etc.) |
| `start_date` / `end_date` | Filter by time period |
| `search` | Case-insensitive substring (`icontains`) search over resource name, resource ID, and IP address |

**Search Example:**
```bash
1. Navigate to Audit Logs
2. Enter search criteria:
   - User: john.doe@example.com
   - Action: delete_agent
   - Date Range: Last 7 days
3. Click "Search"
4. View filtered results
```

> **Note:** There is no dedicated IP address filter parameter. The `search` field performs a case-insensitive substring match; it does not interpret `*` or other glob patterns.

### Advanced Filters

**Filter by Multiple Criteria:**
```yaml
Filters:
  User: john.doe@example.com OR jane.smith@example.com
  Action: create_agent OR update_agent OR delete_agent
  Resource Type: agent
  Status: success
  Date Range: 2026-02-01 to 2026-02-11
  Search: 192.168.1.
```

**Filter by Changes:**
> **Note:** Not implemented / Roadmap. Audit logs cannot be filtered by changed field, before value, or after value. The field-level `changes` payload is visible in log details and exports only.

### Saved Searches

> **Note:** Not implemented / Roadmap. There is no saved-search feature. Re-run the filters you need; there are no named, persisted search configurations.

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
  Auth Method: password

Changes:
  before:
    name: Customer Support Agent
    max_iterations: 5
    system_prompt: "You are a helpful assistant."
  after:
    name: Customer Support Agent
    max_iterations: 8
    system_prompt: "You are a helpful customer support agent."

Metadata:
  team_id: team-456
  team_name: Support Team
  model: gpt-4-turbo
  duration: 1.2s
```

### Sensitive Data Redaction

When an entry records field-level changes, the `before` / `after` payloads are processed by `AuditLogService.sanitize_changes` before storage:

- **Sensitive fields are redacted**: keys containing `password`, `hashed_password`, `api_key`, `secret_key`, `access_token`, `refresh_token`, `private_key`, `secret`, or `token` are masked. String values longer than 8 characters show only the first 8 characters followed by `***`; other values are replaced with `***`.
- **Email addresses are partially masked** (e.g. `a***e@example.com`).
- **Nested dictionaries are processed recursively**.
- **Values are truncated** to a maximum field length (500 characters), and oversized structures are replaced with a preview string.

Because of this redaction, raw secrets never appear in audit logs.

### Related Logs

> **Note:** Not implemented / Roadmap. There is no "Related Logs" view. To find related entries, filter by the same `user_id`, `resource_id`, or time range.

## Exporting Audit Logs

### Export Options

**Export Formats:**
- CSV
- JSON

The export endpoint (`GET /api/v1/admin/audit-logs/export?format=csv|json`) accepts the same filters as the list endpoint and returns up to 10,000 matching logs. CSV columns are: ID, Time, User, Action, Resource Type, Resource Name, Operation, Status, IP Address, Error Message. JSON exports the full serialized entries (including `changes`).

**Export Logs:**
1. Apply filters (optional)
2. Click **Export**
3. Select format (CSV or JSON)
4. Click **Download**

**CSV Export Example:**
```csv
ID,Time,User,Action,Resource Type,Resource Name,Operation,Status,IP Address,Error Message
log-12345,2026-02-11T14:30:00Z,john.doe@example.com,update_agent,agent,Customer Support Agent,update,success,192.168.1.100,
log-12346,2026-02-11T14:25:00Z,jane.smith@example.com,create_workflow,workflow,Customer Processing,create,success,192.168.1.101,
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
…
]
```

### Scheduled Exports

> **Note:** Not implemented / Roadmap. There is no scheduled export (daily/weekly/monthly) and no delivery to email or S3. Exports are manual only.

## Audit Reports

### Report Types

> **Note:** Not implemented / Roadmap. There is no report generator (user activity, admin actions, security events, resource changes, failed operations, or custom reports). The following statistics endpoints provide the available aggregates instead:
>
> - `GET /api/v1/admin/audit-logs/stats` — total logs, today's logs, failed logs, active users (last 7 days), top 5 actions, top 5 users
> - `GET /api/v1/admin/audit-logs/stats/retention` — configured retention days, cutoff date, logs to archive, oldest log, next archive time

## Log Retention and Archival

### Retention Policy

**Default Retention:**
```yaml
Retention Policy:
  Audit Log Retention: 365 days
```

The retention period is stored in the site setting `audit_log_retention_days` (default **365** days, range 30-3650).

**Configure Retention:**
1. Navigate to **Admin** → **Site Settings** → **Storage**
2. Set **Audit log retention (days)**
3. Set the **Archive file storage path** (default `/var/log/clouisle/audit_archives`)
4. Save settings

### Archive Logs

**Manual Archive:**
1. Navigate to **Audit Logs** → **Archive**
2. Click **Archive**
3. The archiving task runs asynchronously (requires `audit:export`); track its status via the returned task ID

**How Archiving Works:**
- The archive task (`tasks.archive_old_audit_logs`) selects logs older than the retention cutoff
- Logs are exported to local JSON files grouped by month, e.g. `/var/log/clouisle/audit_archives/audit_logs_202602.json` (existing monthly files are appended to)
- Archived logs are then deleted from the database

**Trigger Archive:**
```yaml
Action: trigger_audit_log_archive
User: admin@example.com
Timestamp: 2026-02-11 10:00:00
Status: pending
Metadata:
  task_id: <celery-task-id>
```

> **Note:** Archiving is manual only — there is no scheduled (e.g. daily 2 AM) automatic archive, and no S3/Azure/Blob archive destinations. Archive output is written to the local path configured in `audit_log_archive_path`.

### Restore Archived Logs

> **Note:** Not implemented / Roadmap. There is no restore workflow for archived logs. Monthly JSON archive files under the archive path remain available for manual inspection.

## Monitoring and Alerts

### Real-time Monitoring

> **Note:** Not implemented / Roadmap. There is no real-time monitoring dashboard for audit logs. Aggregate counters are available through the statistics endpoints (`GET /api/v1/admin/audit-logs/stats` and `/stats/retention`).

### Configure Alerts

> **Note:** Not implemented / Roadmap. There is no alert engine for audit logs. Site settings such as `audit_alert_enabled`, `audit_alert_webhook`, and the failed-login thresholds exist as dormant configuration but are not consumed by any monitoring or notification code.

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
- [Security Checklist](../../operations/security-checklist.md) - Security guidance
- [User Management](../users/user-management.md) - User admin
- [Compliance operations](../../operations/backup-restore.md) - Backup and retention guidance

---

**Last Updated**: 2026-02-11
