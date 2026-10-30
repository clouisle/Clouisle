# System Settings

This guide covers how to configure system-wide settings as an administrator.

## Overview

As an administrator, you can configure:

- **General**: Site name, URL, description, default language, theming
- **Security**: Registration, password policy, sessions, model endpoint allowlist
- **Notifications**: Notification rules and automatic notification preferences
- **Integrations**: SSO login, outbound email, Webhook delivery, and Feishu (manual directory synchronization plus opt-in web sign-in)

## Accessing System Settings

### Admin Dashboard

1. Log in as administrator
2. Navigate to **Admin** → **Site Settings** (Settings section in the sidebar)
3. Choose a category from the settings sub-navigation

### Settings Categories

- **General** (`/site-settings`)
- **Security** (`/site-settings/security`)
- **Notifications** (`/site-settings/notifications`)
- **Integrations** (`/site-settings/integrations`)
- **Storage** (`/site-settings/storage`)
- **Memory** (`/site-settings/memory`)
- **Parsing** (`/site-settings/parsing`)

> General settings remain key-value SiteSettings, exposed through `/api/v1/admin/site-settings` with `admin:settings:read/update`. External services now use Integration records and `/api/v1/admin/integrations`. Login management requires `admin:integrations:login:read/update`; builtin configuration requires `admin:integrations:settings:read/update`. Feishu is one singleton integration declaring both `directory_sync` and `user_login`: its app ID, app secret, department scope, and directory sync are settings-domain, while the sign-in opt-in, button text, and sign-in enable/disable are login-domain. Update authorization on the generic `PUT /api/v1/admin/integrations/{id}` is decided per field, so a single card can require both domains. The global SSO policy (enable SSO, password login, auto-create users, approval, email matching) lives on **Security** but is authorized by the login domain. See [Integrations and SSO](SSO.md) for setup, domain permissions, credential handling, and migration/rollback cautions.

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
force_password_change_first_login: false
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

The **Restrict Model Endpoints to the Allowlist** switch (`model_endpoint_allowlist_enabled`) defaults to on. Turn it off and save to allow any structurally valid HTTP(S) endpoint, without Origin membership checks. Saved Origins are retained and enforced again when the switch is re-enabled and saved.

Before saving or testing a model with a new API endpoint:

1. Navigate to **Settings** → **Security**.
2. Add the endpoint Origin to **Model Endpoint Allowlist**, one per line.
3. Include only the scheme, hostname, and non-default port, for example `https://gateway.example.com` or `http://ollama.internal:11434`.
4. Save the Security settings, then save or test the model again.

> **Security:** Prefer HTTPS for remote endpoints. Use HTTP only for endpoints on a trusted private network because API keys and model traffic are otherwise sent without transport encryption.

Matching is exact. URL paths are ignored, but the scheme, hostname, and port must all match. Removing an Origin blocks subsequent model discovery, connection tests, and runtime requests without restarting the service.

### Sandbox Egress Allowlist

The **Restrict Sandbox Egress to the Allowlist** switch (`sandbox_network_allowlist_enabled`) defaults to on. Turning it off and saving allows new jobs to use the worker's network directly, including arbitrary destinations, protocols and ports. Filesystem isolation and resource limits remain enabled; host/container network policies still apply. The saved allowlist is retained. Switch changes apply to the next sandbox job, not jobs already running.

The sandbox egress proxy restricts isolated sandbox jobs to approved exact DNS hostnames. This policy is separate from the outbound SSRF exception list used by HTTP tools and URL imports.

1. Navigate to **Settings** → **Security**.
2. Locate **Sandbox Egress Allowlist**.
3. Enter one exact DNS hostname per line. The initial defaults are `pypi.org`, `files.pythonhosted.org`, `pypi.python.org`, and `registry.npmjs.org`.
4. Save the Security settings.

Wildcards and IP addresses are rejected. An empty list blocks all external hosts through the sandbox proxy. Custom package-index URLs must use HTTPS and their hostname must be listed. Each sandbox job reads the current saved policy, so changes apply to the next job without restarting workers.

### Outbound Network Allowlist (SSRF Exemption)

The **Enforce Outbound Network Protection (SSRF)** switch (`ssrf_protection_enabled`) defaults to on. Turning it off and saving disables destination restrictions for consumers of this policy, including private networks, loopback and cloud metadata addresses. HTTP(S) URL and database host/port syntax validation remains active. This can expose internal services and cloud credentials; prefer narrow exemptions with protection enabled. Saved exemptions are retained for re-enabling protection. Changes apply to subsequent policy checks without restarting services.

Clouisle protects against Server-Side Request Forgery (SSRF) across custom HTTP tools, workflow HTTP request nodes, knowledge base URL imports, and database tool connection tests. By default, requests to loopback addresses (`127.0.0.1`, `localhost`), link-local/cloud metadata services (`169.254.169.254`), and private networks (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`) are blocked.

If your deployment requires calling internal APIs, microservices, or intranet databases:

1. Navigate to **Settings** → **Security**.
2. Locate the **Outbound Network Allowlist (SSRF Exemption)** card.
3. Add approved internal targets, one per line:
   - **Single IP**: `192.168.1.50`, `10.20.1.10`
   - **CIDR subnet**: `10.10.0.0/16`, `172.20.0.0/24`, `192.168.0.0/16`
   - **Exact domain**: `oa.company.local`, `api.internal.service`
   - **Wildcard domain**: `*.corp.internal`, `*.internal.net`
4. Click **Save Changes**.

#### Targets That Cannot Be Added as Exemptions

With SSRF protection enabled, the following critical targets cannot be exempted. Disabling SSRF protection bypasses runtime destination checks entirely; the exemption editor still rejects unsafe or malformed rules:

- **Cloud metadata services**: `169.254.169.254`, `169.254.0.0/16`, `fe80::/10`, `metadata.google.internal` (prevents exfiltration of host IAM/cloud instance credentials).
- **Unspecified & multicast addresses**: `0.0.0.0`, `::`, `224.0.0.0/4` (prevents bypassing loopback checks).
- **Universal wildcards**: `*`, `0.0.0.0/0`, `::/0`. Use the explicit protection switch instead of wildcard rules.
- **Loopback addresses**: These are blocked by default but can be explicitly exempted, for example `127.0.0.1` or `localhost`. In containers, loopback refers to the calling container; use the host LAN IP or `host.docker.internal` to reach host services.

#### Transparent Proxy / TUN Mode Support

## Notification Settings

### Email (SMTP)

**Configuration:**
```yaml
# Enable the email Integration; SMTP settings below are its config.
smtp_host: smtp.gmail.com
smtp_port: 587
smtp_encryption: tls       # none, ssl, or tls
smtp_username: noreply@your-domain.com
# smtp_password is supplied separately as a credential, never returned.
email_from_name: Clouisle
email_from_address: noreply@your-domain.com
```

**Update SMTP Settings:**
1. Navigate to **Settings** → **Integrations** → **Email** (`/site-settings/integrations`)
2. Enter SMTP details
3. Set sender name and address
4. Click **Test** (POST `/api/v1/admin/integrations/email/test`)
5. Click **Save Changes**

Email and generic Webhook are the only external notification channels. Configure them under **Settings** → **Integrations** (`/site-settings/integrations`). Notification delivery settings are separate from the event/channel preferences on **Notifications** (`/site-settings/notifications`).

| Channel | Key settings | Test endpoint |
|---------|--------------|---------------|
| Email | SMTP server, sender, separate password credential | `/api/v1/admin/integrations/email/test` |
| Webhook | URL, method, body template; separate headers and HMAC credentials | `/api/v1/admin/integrations/webhook/test` |

### Feishu Directory Sync

Administrators can manually create or update Clouisle accounts from selected Feishu departments. This is a one-way sync: Clouisle does not update Feishu, and Feishu user departures or deactivations do not disable Clouisle accounts.

1. Create a Feishu custom app and grant it contact API access and data scope that includes the departments you need to browse. Reading the root department requires the app's contact scope to include all members.
2. Grant the app `tenant:tenant:readonly` to read the official company name, plus the directory fields needed by sync: user ID (`contact:user.employee_id:readonly`), user name/basic profile (`contact:user.base:readonly` or the applicable contact read scope), and email (`contact:user.email:readonly`) if you want to use real email addresses. Without email field access, users receive internal placeholder addresses.
3. In Clouisle, open **Settings** → **Integrations**, enable the Feishu integration, then open its card. Turn on the **Directory sync** switch and save the app ID and app secret there. The secret is encrypted at rest; a blank secret field preserves the saved secret. The capability switches are disabled until the integration itself is enabled.
4. Browse the department tree, select departments, and save the scope. The top-level **Company** node represents Feishu's root department (ID `0`); selecting it selects the whole organization. Selecting any other department selects only that department and its descendants. The tree only shows departments visible to the Feishu app.
5. Select **Sync selected department members** to import accounts and create/update the corresponding Clouisle teams, including the company team when the root department is selected. The result reports created, updated, skipped accounts, and new teams.

New accounts have no local password, receive the configured default role and default team membership/role, and use a deterministic `@accounts.clouisle.example` email if Feishu does not return an email. The `.example` TLD is reserved (RFC 6761) and is never deliverable, and the local part is derived from the Feishu user ID, so repeat syncs always produce the same address. Existing local accounts are never linked by email alone. Repeated syncs match by the stored Feishu user ID and update that account; email conflicts are skipped. Every selected Feishu department has a corresponding Clouisle team, and synchronized users are added to each selected department they belong to; users may belong to multiple department teams. Repeated syncs do not duplicate teams or memberships. Unselected department memberships are not changed.

> **Upgrading:** placeholder addresses created by earlier releases used the `.invalid` domain, which response validation rejects. On startup Clouisle rewrites Feishu-synced accounts from `@accounts.clouisle.invalid` to `@accounts.clouisle.example`; no manual data fix is required.

**App permissions and data scope.** The Feishu app needs the contact read scope plus a **contact data scope (通讯录权限范围)** that contains the departments *and* their members. Browsing the department tree can succeed while the sync still fails because the individual users are outside that scope.

**When the sync fails.** Clouisle returns Feishu's own rejection reason (error code and message) and logs the full response, so check the error shown in **Settings → Integrations** first. Common cases:

| Feishu error | Meaning | Fix |
|--------------|---------|-----|
| HTTP 400, code `41050` (no user authority) | A member is outside the app's contact data scope | Add the user (or the whole department) to the app's contact data scope in the Feishu developer console, then sync again |
| HTTP 403, code `40004` (no dept authority) | The department is outside the app's contact data scope | Add the department to the app's contact data scope |
| HTTP 400, code `40011` / `40012` | Invalid pagination parameters | Retry; report the error if it repeats |
| `Feishu returned users without user_id` | The app cannot read user IDs | Grant `contact:user.employee_id:readonly` (see step 2) |
| `Stored Feishu app secret cannot be decrypted` | The backend `SECRET_KEY` changed after the secret was saved | Re-save the app secret |

The relevant administrator APIs are `GET/PUT /api/v1/admin/integrations/feishu/config`, `GET /api/v1/admin/integrations/feishu/departments`, `PUT /api/v1/admin/integrations/feishu/department-scope`, and `POST /api/v1/admin/integrations/feishu/sync`. They require `admin:integrations:settings:read/update` as appropriate. Feishu does not provide Agent messaging.

### Feishu Sign-In

The Feishu integration also declares the `user_login` capability, so the same app that synchronizes the directory can sign users in — with the same app ID and app secret, without creating a second provider.

1. In the Feishu developer console, add the **Redirect URL** shown on the Feishu card — `https://<backend-host>/api/v1/sso/callback/<integration-name>`, for example `https://api.example.com/api/v1/sso/callback/feishu` — to the app's redirect-URI allowlist. The card displays the exact value with a copy button.
2. Grant the app the login scopes `contact:user.base:readonly contact:user.email:readonly`, in addition to the directory scopes above.
3. On the **Settings** → **Integrations** → **Feishu** card, turn on **Feishu sign-in** in the capability section and optionally set the button text; both switches are saved together. This writes `user_login` into the integration's `enabled_capabilities` through the generic `PUT /api/v1/admin/integrations/{id}` and requires `admin:integrations:login:update`.
4. Keep global SSO enabled on **Security**. The login page shows the Feishu button only when global SSO is enabled, the integration is enabled, and `user_login` is one of its enabled capabilities. Enabling the integration alone never starts sign-in, and disabling the integration stops both capabilities while preserving the opt-in. App credentials, the department scope, and directory sync stay on the settings domain.

The Feishu subject is the profile `union_id`, falling back to `open_id`, stored as the external identity key, so replacing the app inside the same developer account keeps existing connections. A Feishu account whose directory record carries no email gets the same deterministic placeholder address the directory sync uses (`feishu-<sha256(user_id)>@accounts.clouisle.example`), so sign-in and sync resolve to one local account instead of two; deriving that address needs the Feishu `user_id` (`contact:user.employee_id:readonly`), and without that scope the first sign-in of such an account is rejected.

### Auto Notifications

The **Auto Notifications** tab (GET/PUT `/api/v1/admin/site-settings/auto-notifications`) controls which event types create notifications and which external channels receive them. See [Auto Notifications](./AUTO_NOTIFICATIONS.md) for details.

### Email Templates

> **Note:** Not implemented / Roadmap. There is no email template editor. Notification messages are generated from built-in i18n translations (`app/core/i18n.py`).

## Background Memory Extraction Settings

The **Memory** category (`/site-settings/memory`) schedules extraction for pending user turns after the configured cooldown, or immediately when the pending-turn threshold is reached. The Agent must also have memory enabled; disabling either the Agent memory feature or the global switch prevents extraction tasks.

```yaml
memory_async_extraction_enabled: false
memory_extraction_model_id: ""
memory_extraction_cooldown_seconds: 180      # 10-3600
memory_extraction_max_pending_turns: 6      # 1-50
```

The extraction model falls back to the explicitly configured enabled model, the Agent's assigned model, the system default chat model, and then the first available chat model. The cooldown debounces extraction; reaching the pending-turn threshold queues it immediately.

## Document Image Parsing Settings

The **Parsing** category (`/site-settings/parsing`) controls optional image OCR and understanding for documents processed after the feature is enabled. It is **off by default**, and existing documents are not reprocessed automatically.

```yaml
kb_image_understanding_enabled: false
kb_image_understanding_model_id: ""            # enabled chat model with image input
kb_image_ocr_model_id: ""                      # optional OCR-only image chat model
kb_image_understanding_allow_external: false   # fetch external image URLs
kb_image_understanding_max_images: 8           # 1-20 per document
kb_image_understanding_max_image_bytes: 10485760   # 1-52428800
kb_image_understanding_max_image_pixels: 20000000  # 1-40000000
kb_image_understanding_concurrency: 2          # 1-8, per document
```

Enabling the feature requires at least one enabled chat model whose effective input capabilities include images: the vision model, the OCR model, or both. Model use still requires the model to be authorized for the owning team, and provider quota and usage accounting apply. Image content is sent to the configured provider, may leave the deployment, and may incur charges.

When `kb_image_ocr_model_id` is set, OCR text is extracted by that model and the vision model produces only the factual visual description; both calls run concurrently. When only the OCR model is configured, processing indexes the extracted text and omits the image description. Leave both empty only while the feature is disabled.

Processing extracts readable text and a separate factual description from supported embedded images, then indexes both with the surrounding text. Page, slide, or worksheet references are retained where available. Output is treated as untrusted content and is not executed.

`kb_image_understanding_allow_external` is a separate opt-in for fetching images referenced by external URLs; it only takes effect when image understanding is enabled. When disabled, external URLs are never fetched. When enabled, requests use the centralized SSRF protection, re-validate every redirect, pin validated DNS answers, ignore proxy and cookie settings, and enforce byte and pixel limits. The concurrency value bounds work within one document/process; it is not a cluster-wide rate limit.

For PDFs with both a text layer and visual content, a whole page may be sent to the vision model, so extracted text can overlap with the existing text layer. Complete deduplication is not guaranteed.

If the configured vision model endpoint is unreachable or its credentials are invalid, preview and document processing fail with an image-understanding error that asks you to check the model endpoint and credentials. The system does not silently index a document without its image content.

## Storage Settings

### File Storage

**Configuration:**
```yaml
upload_storage_backend: local   # local or object
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
3. Save Changes

**Last Updated**: 2026-10-30
