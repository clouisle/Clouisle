# Settings API

This document describes the Settings API endpoints for managing system and team settings.

## Overview

The Settings API allows you to manage system-wide settings, team settings, and user preferences programmatically.

## Endpoints

### System Settings

#### Get System Settings

Get all system settings or specific setting.

**Endpoint:**
```
GET /api/v1/settings/system
GET /api/v1/settings/system/{key}
```

**Authentication:** Required (Admin only)

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `category` | string | Filter by category (optional) |

**Response:**
```json
{
  "code": 0,
  "data": {
    "general": {
      "site_name": "Clouisle",
      "site_url": "https://your-domain.com",
      "support_email": "support@example.com"
    },
    "authentication": {
      "allow_registration": true,
      "require_email_verification": true,
      "session_timeout": 1800
    },
    "email": {
      "smtp_host": "smtp.example.com",
      "smtp_port": 587,
      "smtp_user": "noreply@example.com",
      "from_email": "noreply@example.com",
      "from_name": "Clouisle"
    }
  },
  "msg": "success"
}
```

**Example (Python):**
```python
# Get all system settings
settings = api.get('/api/v1/settings/system')

# Get specific setting
site_name = api.get('/api/v1/settings/system/general.site_name')
print(f"Site name: {site_name['data']['value']}")

# Get settings by category
auth_settings = api.get('/api/v1/settings/system', params={
    'category': 'authentication'
})
```

**Example (JavaScript):**
```javascript
// Get all system settings
const settings = await api.get('/api/v1/settings/system');

// Get specific setting
const siteName = await api.get('/api/v1/settings/system/general.site_name');
console.log(`Site name: ${siteName.data.value}`);

// Get settings by category
const authSettings = await api.get('/api/v1/settings/system', {
  params: { category: 'authentication' }
});
```

#### Update System Settings

Update system settings.

**Endpoint:**
```
PATCH /api/v1/settings/system
PATCH /api/v1/settings/system/{key}
```

**Authentication:** Required (Admin only)

**Request Body:**
```json
{
  "general": {
    "site_name": "My Clouisle Instance",
    "support_email": "support@mycompany.com"
  },
  "authentication": {
    "session_timeout": 3600
  }
}
```

**Response:**
```json
{
  "code": 0,
  "data": {
    "updated": [
      "general.site_name",
      "general.support_email",
      "authentication.session_timeout"
    ]
  },
  "msg": "success"
}
```

**Example (Python):**
```python
# Update multiple settings
result = api.patch('/api/v1/settings/system', json={
    'general': {
        'site_name': 'My Clouisle Instance',
        'support_email': 'support@mycompany.com'
    },
    'authentication': {
        'session_timeout': 3600
    }
})

# Update single setting
result = api.patch('/api/v1/settings/system/general.site_name', json={
    'value': 'My Clouisle Instance'
})
```

**Example (JavaScript):**
```javascript
// Update multiple settings
const result = await api.patch('/api/v1/settings/system', {
  general: {
    site_name: 'My Clouisle Instance',
    support_email: 'support@mycompany.com'
  },
  authentication: {
    session_timeout: 3600
  }
});

// Update single setting
const result = await api.patch('/api/v1/settings/system/general.site_name', {
  value: 'My Clouisle Instance'
});
```

#### Reset System Settings

Reset settings to default values.

**Endpoint:**
```
POST /api/v1/settings/system/reset
```

**Authentication:** Required (Admin only)

**Request Body:**
```json
{
  "keys": ["general.site_name", "authentication.session_timeout"],
  "category": "authentication"
}
```

**Response:**
```json
{
  "code": 0,
  "data": {
    "reset": [
      "general.site_name",
      "authentication.session_timeout"
    ]
  },
  "msg": "success"
}
```

### Team Settings

#### Get Team Settings

Get team settings.

**Endpoint:**
```
GET /api/v1/teams/{team_id}/settings
GET /api/v1/teams/{team_id}/settings/{key}
```

**Authentication:** Required (Team member)

**Response:**
```json
{
  "code": 0,
  "data": {
    "general": {
      "name": "Engineering Team",
      "description": "Product engineering team",
      "visibility": "internal"
    },
    "limits": {
      "max_agents": 50,
      "max_knowledge_bases": 20,
      "max_workflows": 100
    },
    "security": {
      "require_2fa": true,
      "session_timeout": 1800,
      "allowed_ips": ["192.168.1.0/24"]
    }
  },
  "msg": "success"
}
```

**Example (Python):**
```python
# Get all team settings
settings = api.get(f'/api/v1/teams/{team_id}/settings')

# Get specific setting
max_agents = api.get(f'/api/v1/teams/{team_id}/settings/limits.max_agents')
print(f"Max agents: {max_agents['data']['value']}")
```

**Example (JavaScript):**
```javascript
// Get all team settings
const settings = await api.get(`/api/v1/teams/${teamId}/settings`);

// Get specific setting
const maxAgents = await api.get(
  `/api/v1/teams/${teamId}/settings/limits.max_agents`
);
console.log(`Max agents: ${maxAgents.data.value}`);
```

#### Update Team Settings

Update team settings.

**Endpoint:**
```
PATCH /api/v1/teams/{team_id}/settings
PATCH /api/v1/teams/{team_id}/settings/{key}
```

**Authentication:** Required (Team admin)

**Request Body:**
```json
{
  "general": {
    "name": "Updated Team Name",
    "description": "Updated description"
  },
  "security": {
    "require_2fa": true
  }
}
```

**Response:**
```json
{
  "code": 0,
  "data": {
    "updated": [
      "general.name",
      "general.description",
      "security.require_2fa"
    ]
  },
  "msg": "success"
}
```

**Example (Python):**
```python
# Update team settings
result = api.patch(f'/api/v1/teams/{team_id}/settings', json={
    'general': {
        'name': 'Updated Team Name',
        'description': 'Updated description'
    },
    'security': {
        'require_2fa': True
    }
})
```

**Example (JavaScript):**
```javascript
// Update team settings
const result = await api.patch(`/api/v1/teams/${teamId}/settings`, {
  general: {
    name: 'Updated Team Name',
    description: 'Updated description'
  },
  security: {
    require_2fa: true
  }
});
```

### User Preferences

#### Get User Preferences

Get user preferences.

**Endpoint:**
```
GET /api/v1/users/me/preferences
GET /api/v1/users/me/preferences/{key}
```

**Authentication:** Required

**Response:**
```json
{
  "code": 0,
  "data": {
    "notifications": {
      "email_enabled": true,
      "email_frequency": "immediate",
      "push_enabled": true
    },
    "ui": {
      "theme": "light",
      "language": "en",
      "timezone": "America/New_York"
    },
    "privacy": {
      "show_online_status": true,
      "allow_mentions": true
    }
  },
  "msg": "success"
}
```

**Example (Python):**
```python
# Get all preferences
prefs = api.get('/api/v1/users/me/preferences')

# Get specific preference
theme = api.get('/api/v1/users/me/preferences/ui.theme')
print(f"Theme: {theme['data']['value']}")
```

**Example (JavaScript):**
```javascript
// Get all preferences
const prefs = await api.get('/api/v1/users/me/preferences');

// Get specific preference
const theme = await api.get('/api/v1/users/me/preferences/ui.theme');
console.log(`Theme: ${theme.data.value}`);
```

#### Update User Preferences

Update user preferences.

**Endpoint:**
```
PATCH /api/v1/users/me/preferences
PATCH /api/v1/users/me/preferences/{key}
```

**Authentication:** Required

**Request Body:**
```json
{
  "notifications": {
    "email_frequency": "daily"
  },
  "ui": {
    "theme": "dark",
    "language": "zh"
  }
}
```

**Response:**
```json
{
  "code": 0,
  "data": {
    "updated": [
      "notifications.email_frequency",
      "ui.theme",
      "ui.language"
    ]
  },
  "msg": "success"
}
```

**Example (Python):**
```python
# Update preferences
result = api.patch('/api/v1/users/me/preferences', json={
    'notifications': {
        'email_frequency': 'daily'
    },
    'ui': {
        'theme': 'dark',
        'language': 'zh'
    }
})
```

**Example (JavaScript):**
```javascript
// Update preferences
const result = await api.patch('/api/v1/users/me/preferences', {
  notifications: {
    email_frequency: 'daily'
  },
  ui: {
    theme: 'dark',
    language: 'zh'
  }
});
```

## Setting Categories

### System Settings Categories

**General:**
- `site_name`: Site name
- `site_url`: Site URL
- `support_email`: Support email
- `logo_url`: Logo URL

**Authentication:**
- `allow_registration`: Allow user registration
- `require_email_verification`: Require email verification
- `session_timeout`: Session timeout (seconds)
- `max_login_attempts`: Max failed login attempts
- `lockout_duration`: Account lockout duration (seconds)

**Email:**
- `smtp_host`: SMTP server host
- `smtp_port`: SMTP server port
- `smtp_user`: SMTP username
- `smtp_password`: SMTP password (encrypted)
- `from_email`: From email address
- `from_name`: From name

**Storage:**
- `storage_provider`: Storage provider (local, s3, azure)
- `max_file_size`: Max file size (bytes)
- `allowed_file_types`: Allowed file types

**Security:**
- `require_https`: Require HTTPS
- `enable_cors`: Enable CORS
- `allowed_origins`: Allowed CORS origins
- `rate_limit_enabled`: Enable rate limiting
- `rate_limit_requests`: Requests per minute

**Features:**
- `enable_registration`: Enable user registration
- `enable_sso`: Enable SSO
- `enable_api`: Enable API access
- `enable_webhooks`: Enable webhooks

### Team Settings Categories

**General:**
- `name`: Team name
- `slug`: Team slug
- `description`: Team description
- `visibility`: Team visibility

**Limits:**
- `max_members`: Maximum members
- `max_agents`: Maximum agents
- `max_knowledge_bases`: Maximum knowledge bases
- `max_workflows`: Maximum workflows
- `max_storage`: Maximum storage (bytes)

**Security:**
- `require_2fa`: Require 2FA
- `session_timeout`: Session timeout
- `allowed_ips`: Allowed IP addresses
- `allowed_domains`: Allowed email domains

**API:**
- `api_enabled`: Enable API access
- `rate_limit_per_minute`: Rate limit per minute
- `rate_limit_per_hour`: Rate limit per hour
- `max_api_keys`: Maximum API keys per user

### User Preferences Categories

**Notifications:**
- `email_enabled`: Enable email notifications
- `email_frequency`: Email frequency (immediate, hourly, daily, weekly)
- `push_enabled`: Enable push notifications
- `in_app_enabled`: Enable in-app notifications

**UI:**
- `theme`: UI theme (light, dark, auto)
- `language`: Interface language
- `timezone`: User timezone
- `date_format`: Date format
- `time_format`: Time format (12h, 24h)

**Privacy:**
- `show_online_status`: Show online status
- `allow_mentions`: Allow mentions
- `show_email`: Show email to team members

## Validation Rules

### Setting Validation

**Type Validation:**
```python
{
  "session_timeout": {
    "type": "integer",
    "min": 300,
    "max": 86400
  },
  "site_name": {
    "type": "string",
    "min_length": 3,
    "max_length": 100
  },
  "require_2fa": {
    "type": "boolean"
  }
}
```

**Custom Validation:**
```python
def validate_setting(key, value):
    """Validate setting value."""
    if key == 'session_timeout':
        if not 300 <= value <= 86400:
            raise ValueError('Session timeout must be between 300 and 86400 seconds')

    elif key == 'site_url':
        if not value.startswith(('http://', 'https://')):
            raise ValueError('Site URL must start with http:// or https://')

    elif key == 'smtp_port':
        if value not in [25, 465, 587, 2525]:
            raise ValueError('Invalid SMTP port')

    return True
```

## Bulk Operations

### Bulk Update Settings

**Update Multiple Settings:**
```python
# Bulk update system settings
result = api.patch('/api/v1/settings/system/bulk', json={
    'settings': [
        {'key': 'general.site_name', 'value': 'My Site'},
        {'key': 'authentication.session_timeout', 'value': 3600},
        {'key': 'email.from_email', 'value': 'noreply@example.com'}
    ]
})

# Response
{
    "code": 0,
    "data": {
        "success": [
            "general.site_name",
            "authentication.session_timeout",
            "email.from_email"
        ],
        "failed": []
    },
    "msg": "success"
}
```

### Export Settings

**Export Settings to JSON:**
```python
# Export system settings
settings = api.get('/api/v1/settings/system/export')

# Save to file
import json
with open('settings.json', 'w') as f:
    json.dump(settings['data'], f, indent=2)
```

### Import Settings

**Import Settings from JSON:**
```python
# Load from file
import json
with open('settings.json', 'r') as f:
    settings = json.load(f)

# Import settings
result = api.post('/api/v1/settings/system/import', json={
    'settings': settings,
    'overwrite': True
})
```

## Setting History

### Get Setting History

**View Setting Changes:**
```python
# Get history for specific setting
history = api.get('/api/v1/settings/system/general.site_name/history')

# Response
{
    "code": 0,
    "data": {
        "items": [
            {
                "id": "hist-123",
                "key": "general.site_name",
                "old_value": "Clouisle",
                "new_value": "My Clouisle",
                "changed_by": "user-123",
                "changed_at": "2026-02-11T16:00:00Z"
            }
        ],
        "total": 1
    },
    "msg": "success"
}
```

### Revert Setting

**Revert to Previous Value:**
```python
# Revert to specific version
result = api.post('/api/v1/settings/system/general.site_name/revert', json={
    'history_id': 'hist-123'
})
```

## Best Practices

### Settings Management

**✅ Do:**
- Validate settings before updating
- Use bulk operations for multiple changes
- Export settings before major changes
- Track setting changes
- Document custom settings
- Test settings in staging
- Use environment-specific settings

**❌ Don't:**
- Update settings without validation
- Make changes directly in production
- Skip backups
- Ignore setting history
- Use hardcoded values
- Skip testing
- Use same settings everywhere

### Security

**✅ Do:**
- Encrypt sensitive settings
- Restrict access to admin settings
- Audit setting changes
- Use secure defaults
- Validate all inputs
- Log security-related changes
- Review settings regularly

**❌ Don't:**
- Store passwords in plain text
- Allow public access to settings
- Skip audit logging
- Use insecure defaults
- Trust user input
- Ignore security settings
- Never review settings

## Error Codes

| Code | Message | Description |
|------|---------|-------------|
| 1001 | Validation failed | Setting value invalid |
| 3000 | Permission denied | Insufficient permissions |
| 4000 | Setting not found | Setting key not found |
| 1000 | Invalid setting key | Setting key format invalid |

## Related Documentation

- [System Settings](../admin-guide/settings/system-settings.md) - System configuration
- [Team Settings](../user-guide/settings/team-settings.md) - Team configuration
- [User Preferences](../user-guide/settings/notification-preferences.md) - User preferences
- [Authentication](./authentication.md) - Authentication guide

---

**Last Updated**: 2026-02-11
