# System Settings

This guide covers how to configure system-wide settings as an administrator.

## Overview

As an administrator, you can configure:

- **General**: Site name, URL, description, default language, theming
- **Security**: Registration, password policy, sessions, model endpoint allowlist
- **Notifications**: SMTP/email, DingTalk, WeChat Work, Feishu, Slack, webhook, auto notifications
- **Storage**: Upload storage backend (local or S3-compatible object storage), KB upload size, audit log retention and archive path
- **SSO**: SSO providers and global SSO behavior

## Accessing System Settings

### Admin Dashboard

1. Log in as administrator
2. Navigate to **Admin** → **Site Settings** (Settings section in the sidebar)
3. Choose a category from the settings sub-navigation

### Settings Categories

- **General** (`/site-settings`)
- **Security** (`/site-settings/security`)
- **Notifications** (`/site-settings/notifications`)
- **Storage** (`/site-settings/storage`)
- **SSO** (`/site-settings/sso`)

> **Note:** Settings are stored as key-value site settings and exposed through `GET /api/v1/admin/site-settings` (single key: `GET/PUT /api/v1/admin/site-settings/{key}`, bulk update: `PUT /api/v1/admin/site-settings`). Viewing requires `admin:settings:read`; updating requires `admin:settings:update`.

## General Settings

### Site Information

**Configuration:**
```yaml
site_name: Clouisle
site_url: https://your-domain.com
site_description: Enterprise AI Agent Platform
site_icon: https://your-domain.com/icon.png
default_language: en        # en or zh
auth_page_layout: centered  # centered or split
```

**Update Site Information:**
1. Navigate to **Settings** → **General**
2. Update fields:
   - Site name
   - Site URL
   - Site description
   - Site icon URL
   - Default language
3. Click **Save Changes**

### Branding

**Theme:**
```yaml
theme_mode: light          # light, dark, or system
theme_primary_color: #3B82F6
theme_branding_display: full   # full, name_only, icon_only, or hidden
```

Additional theme tokens (primary foreground, background, foreground, card, sidebar, navbar, accent, chart colors, etc.) can be customized per color token.

**Update Branding:**
1. Navigate to **Settings** → **General**
2. Adjust theme mode and color tokens
3. Click **Save Changes**

### Legal & Compliance

```yaml
icp_record_number: ""       # ICP record number
icp_record_url: ""
terms_enabled: false
terms_url: ""
terms_text: ""              # Markdown text used when no URL is provided
privacy_enabled: false
privacy_url: ""
privacy_text: ""            # Markdown text used when no URL is provided
require_terms_acceptance_on_register: false
```

Terms and privacy entries are shown only when enabled and a URL or text is provided. Registration acceptance is enforced only when `require_terms_acceptance_on_register` is true.

## Security Settings

### Registration

**Configuration:**
```yaml
allow_registration: true
require_approval: true     # admin approval for new users
email_verification: true
allow_account_deletion: true
default_role_id: <Viewer role>    # set automatically at initialization
default_team_id: ""
default_team_role: member         # viewer, member, or admin
```

### Password Policy

**Configuration:**
```yaml
min_password_length: 8
require_uppercase: true
require_number: true
require_special_char: false
```

> **Note:** There is no `require_lowercase` setting.

**Password Expiration:**
```yaml
password_expiration_enabled: false
password_expiration_days: 90
password_expiration_warning_days: 7
password_history_count: 5
password_min_age_days: 0
force_password_change_on_first_login: false
```

### Session Settings

**Configuration:**
```yaml
session_timeout_days: 30
single_session: false      # allow only a single session per user
max_login_attempts: 5      # before account lockout
lockout_duration_minutes: 15
enable_captcha: false
```

> **Note:** There is no "max concurrent sessions" counter. The relevant control is the `single_session` boolean, and the session lifetime is `session_timeout_days` (default 30 days).

### Two-Factor Authentication

```yaml
require_totp: false        # require all users to enable TOTP
```

Admin TOTP statistics and per-user status/disable endpoints are available under `/api/v1/admin/totp`.

### Model Endpoint Allowlist

Before saving or testing a model with a new API endpoint:

1. Navigate to **Settings** → **Security**.
2. Add the endpoint Origin to **Model Endpoint Allowlist**, one per line.
3. Include only the scheme, hostname, and non-default port, for example `https://gateway.example.com` or `http://ollama.internal:11434`.
4. Save the Security settings, then save or test the model again.

> **Security:** Prefer HTTPS for remote endpoints. Use HTTP only for endpoints on a trusted private network because API keys and model traffic are otherwise sent without transport encryption.

Matching is exact. URL paths are ignored, but the scheme, hostname, and port must all match. Removing an Origin blocks subsequent model discovery, connection tests, and runtime requests without restarting the service.

## Notification Settings

### SMTP (Email)

**Configuration:**
```yaml
smtp_enabled: true
smtp_host: smtp.gmail.com
smtp_port: 587
smtp_encryption: tls       # none, ssl, or tls
smtp_username: noreply@your-domain.com
smtp_password: ********
email_sender_name: Clouisle
email_sender_address: noreply@your-domain.com
```

**Update SMTP Settings:**
1. Navigate to **Settings** → **Notifications**
2. Enter SMTP details
3. Set sender name and address
4. Click **Test** (POST `/api/v1/admin/site-settings/test-email`)
5. Click **Save Changes**

### External Notification Channels

The following channels can be enabled and configured (each with its own settings page section and a test endpoint):

| Channel | Key settings | Test endpoint |
|---------|--------------|---------------|
| DingTalk | `dingtalk_enabled`, type (`webhook` or `app`), webhook URL/secret or app key/secret/agent ID | `/test-dingtalk` |
| WeChat Work | `wechat_enabled`, type (`webhook` or `app`), webhook URL or corp ID/agent ID/app secret | `/test-wechat` |
| Feishu | `feishu_enabled`, type (`webhook` or `app`), webhook URL/secret or app ID/secret | `/test-feishu` |
| Slack | `slack_enabled`, incoming webhook URL | `/test-slack` |
| Webhook | `webhook_enabled`, URL, method, custom headers, body template, HMAC secret | `/test-webhook` |

### Auto Notifications

The **Auto Notifications** tab (GET/PUT `/api/v1/admin/site-settings/auto-notifications`) controls which event types create notifications and which external channels receive them. See [Auto Notifications](./AUTO_NOTIFICATIONS.md) for details.

### Email Templates

> **Note:** Not implemented / Roadmap. There is no email template editor. Notification messages are generated from built-in i18n translations (`app/core/i18n.py`).

## Storage Settings

### File Storage

**Configuration:**
```yaml
upload_storage_backend: local   # local or object (S3-compatible)
kb_document_max_upload_size_mb: (1-1024)
```

**Update Storage Settings:**
1. Navigate to **Settings** → **Storage**
2. Configure storage:
   - Storage backend (`local` or `object` — S3-compatible object storage)
   - Max KB document upload size
3. Click **Save Changes**

> **Note:** Azure Blob storage is not supported. There is no public object-storage URL setting and no storage cleanup feature.

### Object Storage (S3-compatible)

**Configuration:**
```yaml
upload_storage_backend: object
object_storage_endpoint: https://s3.amazonaws.com
object_storage_bucket: clouisle-uploads
object_storage_region: us-east-1
object_storage_access_key: AKIA...
object_storage_secret_key: ********
object_storage_force_path_style: true
object_storage_secure: true
```

**Configure Object Storage:**
1. Navigate to **Settings** → **Storage**
2. Enter the endpoint, bucket, region, access key, and secret key
3. Configure path-style URLs and HTTPS options
4. Click **Save Changes**

### Audit Log Retention

```yaml
audit_log_retention_days: 365     # 30-3650
audit_log_archive_path: /var/log/clouisle/audit_archives
```

Logs older than the retention period are archived (manually triggered) to monthly JSON files under the archive path and then deleted. See [Audit Log Management](../audit-logs/audit-log-management.md) for details.

## SSO Settings

### Global SSO Behavior

Configured in **Settings** → **Security** (SSO section) or **Settings** → **SSO**:

```yaml
sso_enabled: false
sso_allow_password_login: true
sso_auto_create_users: true
sso_require_approval: false
sso_match_by_email: true
```

### SSO Providers

SSO providers are managed in **Settings** → **SSO**. Providers are created generically with a name and protocol — there is no preset picker (Google, GitHub, Azure AD, etc.); each provider's configuration and attribute mapping are entered manually. See [SSO Configuration](./SSO.md) for the full guide.

## Feature Flags and Other Settings

> **Note:** Not implemented / Roadmap. The following are **not** configurable system settings:
>
> - Feature flags (enabling/disabling agents, workflows, KBs, etc.)
> - Email templates
> - Security headers (HSTS, CSP, X-Frame-Options)
> - CORS configuration
> - IP whitelisting
> - API rate limiting
> - Webhook configuration as a general system feature
> - Third-party integrations (Salesforce, HubSpot, Slack apps, analytics like Google Analytics/Mixpanel)
> - Maintenance mode
> - Database pool / cache settings
> - Settings export/import and reset-to-defaults workflows
>
> Model endpoints are restricted via the **Model Endpoint Allowlist** (Security) instead of a global integration registry.

## Related Documentation

- [Environment Variables](../../deployment/environment-variables.md) - Environment config
- [Security Checklist](../../operations/security-checklist.md) - Security guidance
- [Auto Notifications](./AUTO_NOTIFICATIONS.md) - Notification types and channels
- [SSO Configuration](./SSO.md) - Single sign-on setup
- [User Management](../users/user-management.md) - User admin

---

**Last Updated**: 2026-02-11
