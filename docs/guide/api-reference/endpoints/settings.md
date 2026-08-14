# Settings API

This document describes the API endpoints for managing site settings.

## Overview

The Settings API allows you to:

- **Read site settings**: Get all settings (optionally filtered by category)
- **Update settings**: Update a single setting or bulk-update many at once
- **Reset settings**: Reset settings to defaults
- **Read public settings**: Get the public (unauthenticated) subset of settings
- **Test notification channels**: Send test emails/notifications

There are no team settings or per-user preference endpoints in this API. Team settings are managed through the Teams API (`/api/v1/teams`), and user preferences are managed through the Users API (`/api/v1/users/me`).

**Base URLs**:
- Admin: `/api/v1/admin/site-settings`
- Public: `/api/v1/site-settings/public`

## Authentication

Admin endpoints require authentication with the `admin:settings:read` / `admin:settings:update` scope. The public endpoint requires no authentication.

**Required scopes (admin):**
- `admin:settings:read` - Read settings
- `admin:settings:update` - Update and reset settings

Settings are stored as key-value pairs, each with a `value_type`, `category`, `description`, and `is_public` flag. There are no fixed categories; each setting belongs to a category key such as `general`, `authentication`, `email`, `storage`, `security`, `features`, `notification`, etc.

## Get All Settings (admin)

Get all settings, optionally filtered by category.

### Endpoint

```
GET /api/v1/admin/site-settings
```

### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `category` | string | No | Filter by category (e.g. `general`, `email`, `storage`) |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/admin/site-settings?category=general" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "settings": {
      "site_name": "Clouisle",
      "site_description": "AI platform",
      "site_url": "https://your-domain.com",
      "site_icon": ""
    }
  },
  "msg": "success"
}
```

The `settings` object maps setting keys to their current values. Without a `category` filter, all settings are returned.

## Get Setting (admin)

Get a single setting by key.

### Endpoint

```
GET /api/v1/admin/site-settings/{key}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `key` | string | Yes | Setting key (e.g. `site_name`) |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/admin/site-settings/site_name" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "key": "site_name",
    "value": "Clouisle",
    "value_type": "string",
    "category": "general",
    "description": "Site name",
    "is_public": true
  },
  "msg": "success"
}
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `key` | string | Setting key |
| `value` | any | Current value |
| `value_type` | string | Value type (`string`, `integer`, `boolean`, `json`, etc.) |
| `category` | string | Setting category |
| `description` | string | Setting description |
| `is_public` | boolean | Whether the value is exposed via the public endpoint |

## Update Setting (admin)

Update a single setting by key.

### Endpoint

```
PUT /api/v1/admin/site-settings/{key}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `key` | string | Yes | Setting key |

### Request Body

```json
{
  "value": "My Clouisle Instance"
}
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `value` | any | Yes | New value (validated against the setting's type/constraints) |

### Request Example

```bash
curl -X PUT "https://your-domain.com/api/v1/admin/site-settings/site_name" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "value": "My Clouisle Instance"
  }'
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "key": "site_name",
    "value": "My Clouisle Instance",
    "value_type": "string",
    "category": "general",
    "description": "Site name",
    "is_public": true
  },
  "msg": "Setting updated successfully"
}
```

## Bulk Update Settings (admin)

Update multiple settings in a single request.

### Endpoint

```
PUT /api/v1/admin/site-settings
```

### Request Body

```json
{
  "settings": {
    "site_name": "My Clouisle Instance",
    "smtp_enabled": true,
    "max_file_size_mb": 100
  }
}
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `settings` | object | Yes | Map of setting keys to new values |

### Request Example

```bash
curl -X PUT "https://your-domain.com/api/v1/admin/site-settings" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "settings": {
      "site_name": "My Clouisle Instance",
      "smtp_enabled": true
    }
  }'
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "settings": {
      "site_name": "My Clouisle Instance",
      "smtp_enabled": true
    }
  },
  "msg": "Settings updated successfully"
}
```

**Note:** Updating storage settings (`upload_storage_backend`, `object_storage_*`) triggers backend validation to ensure the selected storage configuration is consistent. Updating `sso_allow_password_login` to `false` requires at least one superadmin with a bound SSO connection.

## Reset Settings (admin)

Reset settings (optionally within one category) to their default values.

### Endpoint

```
POST /api/v1/admin/site-settings/reset
```

### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `category` | string | No | Only reset settings in this category |

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/admin/site-settings/reset?category=general" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "settings": {
      "site_name": "Clouisle",
      "site_description": "",
      "site_url": ""
    }
  },
  "msg": "Settings reset successfully"
}
```

## Get Public Settings

Get the public subset of settings (those with `is_public: true`). No authentication required.

### Endpoint

```
GET /api/v1/site-settings/public
```

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/site-settings/public"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "site_name": "Clouisle",
    "site_description": "AI platform",
    "site_url": "https://your-domain.com",
    "site_icon": "",
    "auth_page_layout": "centered",
    "theme_mode": "system",
    "theme_primary_color": "",
    "theme_primary_foreground_color": "",
    "theme_background_color": "",
    "theme_foreground_color": "",
    "theme_card_color": "",
    "theme_card_foreground_color": "",
    "theme_border_color": "",
    "theme_ring_color": "",
    "theme_sidebar_color": "",
    "theme_sidebar_foreground_color": "",
    "theme_sidebar_primary_color": "",
    "theme_sidebar_primary_foreground_color": "",
    "theme_sidebar_accent_color": "",
    "theme_sidebar_accent_foreground_color": "",
    "theme_sidebar_border_color": "",
    "theme_navbar_color": "",
    "theme_navbar_foreground_color": "",
    "theme_navbar_hover_color": "",
    "theme_navbar_hover_foreground_color": "",
    "theme_accent_color": "",
    "theme_accent_foreground_color": "",
    "theme_muted_color": "",
    "theme_muted_foreground_color": ""
  },
  "msg": "success"
}
```

## Auto Notifications Config

Get or update the global auto-notification configuration.

### Endpoints

```
GET /api/v1/admin/site-settings/auto-notifications
PUT /api/v1/admin/site-settings/auto-notifications
```

### Request Body (PUT)

```json
{
  "channels": ["email", "dingtalk", "wechat", "feishu", "webhook", "slack"]
}
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "channels": ["email", "dingtalk", "wechat"]
  },
  "msg": "success"
}
```

## Test Notification Channels (admin)

Send test notifications through the configured channels.

### Endpoints

```
POST /api/v1/admin/site-settings/test-email
POST /api/v1/admin/site-settings/test-dingtalk
POST /api/v1/admin/site-settings/test-wechat
POST /api/v1/admin/site-settings/test-feishu
POST /api/v1/admin/site-settings/test-webhook
POST /api/v1/admin/site-settings/test-slack
```

`test-email` accepts a body with the target recipient:

```json
{
  "to_email": "admin@example.com"
}
```

The other endpoints take no body.

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/admin/site-settings/test-email" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "to_email": "admin@example.com"
  }'
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": null,
  "msg": "Test email sent successfully"
}
```

## Archive Audit Logs (admin)

Trigger a background archive of old audit logs, and poll its status.

### Endpoints

```
POST /api/v1/admin/site-settings/archive-audit-logs
GET  /api/v1/admin/site-settings/archive-audit-logs/{task_id}
```

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/admin/site-settings/archive-audit-logs" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "task_id": "celery-task-uuid"
  },
  "msg": "success"
}
```

## Error Codes

| Code | Message | Description |
|------|---------|-------------|
| `1000` | Unknown error | General error |
| `1001` | Validation failed | Setting value invalid |
| `3000` | Permission denied | Insufficient permissions |
| `4000` | Not found | Setting key not found |

> **Note:** No per-endpoint rate limits are implemented. There is no rate-limit middleware on these endpoints.

## Best Practices

### Settings Management

**✅ Do:**
- Validate settings before updating
- Use bulk updates for multiple changes
- Test settings in staging

**❌ Don't:**
- Update settings without validation
- Make changes directly in production without testing
- Skip testing

### Security

**✅ Do:**
- Encrypt sensitive settings
- Restrict access to admin settings
- Use secure defaults
- Validate all inputs

**❌ Don't:**
- Store passwords in plain text
- Allow public access to non-public settings
- Use insecure defaults
- Trust user input

## Related Documentation

- [System Settings](../../admin-guide/settings/system-settings.md) - System configuration
- [Authentication](./authentication.md) - Authentication guide

---

**Last Updated**: 2026-02-11
