# System Settings

This guide covers how to configure system-wide settings as an administrator.

## Overview

As an administrator, you can configure:

- **General settings**: Site name, URL, branding
- **Authentication**: Login methods, SSO, security
- **Email**: SMTP configuration, templates
- **Storage**: File storage, limits, cleanup
- **Features**: Enable/disable features
- **Security**: Password policies, session settings
- **API**: Rate limits, CORS, webhooks
- **Integrations**: Third-party services

## Accessing System Settings

### Admin Dashboard

1. Log in as administrator
2. Navigate to **Admin** → **Settings**
3. View settings categories

### Settings Categories

- **General**: Basic site configuration
- **Authentication**: Login and security
- **Email**: Email server and templates
- **Storage**: File storage configuration
- **Features**: Feature flags
- **Security**: Security policies
- **API**: API configuration
- **Integrations**: External services
- **Advanced**: Advanced options

## General Settings

### Site Information

**Configuration:**
```yaml
Site Name: Clouisle
Site URL: https://your-domain.com
Site Description: Enterprise AI Agent Platform
Admin Email: admin@your-domain.com
Support Email: support@your-domain.com
```

**Update Site Information:**
1. Navigate to **Settings** → **General**
2. Update fields:
   - Site name
   - Site URL
   - Description
   - Contact emails
3. Click **Save Changes**

### Branding

**Logo and Favicon:**
```yaml
Logo: /uploads/logo.png
Logo (Dark Mode): /uploads/logo-dark.png
Favicon: /uploads/favicon.ico
Primary Color: #3B82F6
Secondary Color: #10B981
```

**Update Branding:**
1. Navigate to **Settings** → **General** → **Branding**
2. Upload logo files:
   - Logo (light mode)
   - Logo (dark mode)
   - Favicon
3. Set brand colors:
   - Primary color
   - Secondary color
4. Click **Save Changes**

### Localization

**Configuration:**
```yaml
Default Language: English
Available Languages:
  - English (en)
  - Chinese (zh)
Default Timezone: UTC
Date Format: YYYY/MM/DD
Time Format: 24-hour
```

**Update Localization:**
1. Navigate to **Settings** → **General** → **Localization**
2. Configure:
   - Default language
   - Available languages
   - Default timezone
   - Date/time formats
3. Click **Save Changes**

## Authentication Settings

### Login Methods

**Configuration:**
```yaml
Email/Password: Enabled
SSO: Enabled
API Keys: Enabled
Registration: Enabled
Email Verification: Required
```

**Update Login Methods:**
1. Navigate to **Settings** → **Authentication**
2. Toggle login methods:
   - Email/Password login
   - SSO login
   - API key authentication
3. Configure registration:
   - Allow registration
   - Require email verification
   - Auto-approve accounts
4. Click **Save Changes**

### SSO Configuration

**Supported Providers:**
- Google OAuth
- GitHub OAuth
- Microsoft Azure AD
- SAML 2.0
- CAS
- Custom OIDC

**Configure SSO Provider:**
1. Navigate to **Settings** → **Authentication** → **SSO**
2. Click **Add Provider**
3. Select provider type
4. Enter configuration:
   - Client ID
   - Client Secret
   - Callback URL
   - Scopes
5. Test connection
6. Enable provider
7. Click **Save**

**Google OAuth Example:**
```yaml
Provider: Google
Client ID: 123456789.apps.googleusercontent.com
Client Secret: GOCSPX-...
Callback URL: https://your-domain.com/api/v1/auth/sso/google/callback
Scopes:
  - openid
  - email
  - profile
Enabled: true
```

**SAML Configuration Example:**
```yaml
Provider: SAML
Entity ID: https://your-domain.com
SSO URL: https://idp.example.com/sso
SLO URL: https://idp.example.com/slo
Certificate: |
  -----BEGIN CERTIFICATE-----
  ...
  -----END CERTIFICATE-----
Attribute Mapping:
  email: http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress
  name: http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name
Enabled: true
```

### Password Policy

**Configuration:**
```yaml
Minimum Length: 8
Require Uppercase: true
Require Lowercase: true
Require Numbers: true
Require Special Characters: true
Password Expiry: 90 days
Password History: 5 passwords
Max Login Attempts: 5
Lockout Duration: 30 minutes
```

**Update Password Policy:**
1. Navigate to **Settings** → **Authentication** → **Password Policy**
2. Configure requirements:
   - Minimum length
   - Character requirements
   - Expiry settings
   - History settings
3. Configure lockout:
   - Max login attempts
   - Lockout duration
4. Click **Save Changes**

### Session Settings

**Configuration:**
```yaml
Session Timeout: 30 minutes
Remember Me Duration: 30 days
Max Concurrent Sessions: 5
Force Logout on Password Change: true
```

**Update Session Settings:**
1. Navigate to **Settings** → **Authentication** → **Sessions**
2. Configure:
   - Session timeout
   - Remember me duration
   - Max concurrent sessions
   - Force logout options
3. Click **Save Changes**

## Email Settings

### SMTP Configuration

**Configuration:**
```yaml
SMTP Host: smtp.gmail.com
SMTP Port: 587
SMTP Security: TLS
SMTP Username: noreply@your-domain.com
SMTP Password: ********
From Email: noreply@your-domain.com
From Name: Clouisle
```

**Update SMTP Settings:**
1. Navigate to **Settings** → **Email** → **SMTP**
2. Enter SMTP details:
   - Host
   - Port
   - Security (TLS/SSL)
   - Username
   - Password
3. Set from address:
   - From email
   - From name
4. Click **Test Connection**
5. Click **Save Changes**

### Email Templates

**Available Templates:**
- Welcome email
- Email verification
- Password reset
- Password changed
- Account locked
- Team invitation
- Workflow notification
- Agent response

**Edit Email Template:**
1. Navigate to **Settings** → **Email** → **Templates**
2. Select template
3. Edit template:
   - Subject
   - Body (HTML/Text)
   - Variables
4. Preview template
5. Click **Save Changes**

**Template Variables:**
```
{{user_name}}        - User's full name
{{user_email}}       - User's email
{{site_name}}        - Site name
{{site_url}}         - Site URL
{{verification_url}} - Email verification URL
{{reset_url}}        - Password reset URL
{{team_name}}        - Team name
{{invitation_url}}   - Team invitation URL
```

**Example Template:**
```html
Subject: Welcome to {{site_name}}!

Body:
<html>
<body>
  <h1>Welcome, {{user_name}}!</h1>
  <p>Thank you for joining {{site_name}}.</p>
  <p>To get started, please verify your email address:</p>
  <a href="{{verification_url}}">Verify Email</a>
  <p>If you have any questions, contact us at {{support_email}}.</p>
</body>
</html>
```

## Storage Settings

### File Storage

**Configuration:**
```yaml
Storage Backend: Local
Storage Path: /app/uploads
Max Upload Size: 100 MB
Allowed File Types:
  - PDF
  - DOCX
  - XLSX
  - TXT
  - MD
  - CSV
  - JSON
  - Images (PNG, JPG, GIF)
```

**Update Storage Settings:**
1. Navigate to **Settings** → **Storage**
2. Configure storage:
   - Storage backend (Local, S3, Azure)
   - Storage path/bucket
   - Max upload size
   - Allowed file types
3. Click **Save Changes**

### S3 Configuration

**Configuration:**
```yaml
Storage Backend: S3
S3 Bucket: clouisle-uploads
S3 Region: us-east-1
S3 Access Key: AKIA...
S3 Secret Key: ********
S3 Endpoint: https://s3.amazonaws.com
S3 Public URL: https://cdn.your-domain.com
```

**Configure S3:**
1. Navigate to **Settings** → **Storage** → **S3**
2. Enter S3 details:
   - Bucket name
   - Region
   - Access key
   - Secret key
   - Endpoint (optional)
   - Public URL (optional)
3. Click **Test Connection**
4. Click **Save Changes**

### Storage Cleanup

**Configuration:**
```yaml
Auto Cleanup: Enabled
Cleanup Schedule: Daily at 2 AM
Delete Orphaned Files: After 7 days
Delete Temp Files: After 1 day
Archive Old Files: After 90 days
```

**Update Cleanup Settings:**
1. Navigate to **Settings** → **Storage** → **Cleanup**
2. Configure cleanup:
   - Enable auto cleanup
   - Cleanup schedule
   - Retention periods
3. Click **Save Changes**

## Feature Settings

### Feature Flags

**Available Features:**
```yaml
Agents: Enabled
Workflows: Enabled
Knowledge Bases: Enabled
API Keys: Enabled
Teams: Enabled
SSO: Enabled
Webhooks: Enabled
Audit Logs: Enabled
Analytics: Enabled
Marketplace: Disabled
```

**Toggle Features:**
1. Navigate to **Settings** → **Features**
2. Toggle features on/off
3. Click **Save Changes**

**Note:** Disabling features will hide them from users but preserve data.

### Registration Settings

**Configuration:**
```yaml
Allow Registration: true
Require Email Verification: true
Auto-Approve Accounts: false
Default Role: User
Default Team: None
Max Users: Unlimited
```

**Update Registration:**
1. Navigate to **Settings** → **Features** → **Registration**
2. Configure:
   - Allow registration
   - Email verification
   - Auto-approval
   - Default role
   - Default team
   - User limit
3. Click **Save Changes**

## Security Settings

### Security Headers

**Configuration:**
```yaml
HSTS: Enabled
HSTS Max Age: 31536000
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block
Content-Security-Policy: default-src 'self'
```

**Update Security Headers:**
1. Navigate to **Settings** → **Security** → **Headers**
2. Configure headers:
   - HSTS
   - X-Frame-Options
   - CSP
3. Click **Save Changes**

### CORS Settings

**Configuration:**
```yaml
CORS Enabled: true
Allowed Origins:
  - https://your-domain.com
  - https://app.your-domain.com
Allowed Methods:
  - GET
  - POST
  - PUT
  - PATCH
  - DELETE
Allowed Headers:
  - Authorization
  - Content-Type
Allow Credentials: true
Max Age: 3600
```

**Update CORS:**
1. Navigate to **Settings** → **Security** → **CORS**
2. Configure CORS:
   - Enable CORS
   - Allowed origins
   - Allowed methods
   - Allowed headers
3. Click **Save Changes**

### IP Whitelist

**Configuration:**
```yaml
IP Whitelist Enabled: false
Allowed IPs:
  - 192.168.1.0/24
  - 10.0.0.0/8
Whitelist Admin Only: true
```

**Update IP Whitelist:**
1. Navigate to **Settings** → **Security** → **IP Whitelist**
2. Enable IP whitelist
3. Add allowed IPs/ranges
4. Configure scope (all users or admin only)
5. Click **Save Changes**

## API Settings

### Rate Limiting

**Configuration:**
```yaml
Rate Limiting Enabled: true
Default Limit: 100 requests/minute
Burst Limit: 200 requests
Anonymous Limit: 10 requests/minute
Admin Limit: 1000 requests/minute
```

**Update Rate Limits:**
1. Navigate to **Settings** → **API** → **Rate Limiting**
2. Configure limits:
   - Enable rate limiting
   - Default limit
   - Burst limit
   - Anonymous limit
   - Admin limit
3. Click **Save Changes**

### API Keys

**Configuration:**
```yaml
API Keys Enabled: true
Max Keys per User: 10
Key Expiry: 365 days
Require Key Rotation: true
Rotation Period: 90 days
```

**Update API Key Settings:**
1. Navigate to **Settings** → **API** → **API Keys**
2. Configure:
   - Enable API keys
   - Max keys per user
   - Key expiry
   - Rotation requirements
3. Click **Save Changes**

### Webhooks

**Configuration:**
```yaml
Webhooks Enabled: true
Max Webhooks per Team: 20
Webhook Timeout: 30 seconds
Max Retries: 3
Retry Backoff: Exponential
```

**Update Webhook Settings:**
1. Navigate to **Settings** → **API** → **Webhooks**
2. Configure:
   - Enable webhooks
   - Max webhooks per team
   - Timeout
   - Retry policy
3. Click **Save Changes**

## Integration Settings

### LLM Providers

**Configuration:**
```yaml
OpenAI:
  Enabled: true
  API Key: sk-...
  Organization: org-...

Anthropic:
  Enabled: true
  API Key: sk-ant-...

Azure OpenAI:
  Enabled: false
  API Key: ...
  Endpoint: https://your-resource.openai.azure.com
  API Version: 2024-02-15-preview
```

**Update LLM Providers:**
1. Navigate to **Settings** → **Integrations** → **LLM Providers**
2. Configure each provider:
   - Enable/disable
   - API key
   - Additional settings
3. Test connection
4. Click **Save Changes**

### Analytics

**Configuration:**
```yaml
Analytics Enabled: true
Google Analytics: UA-...
Mixpanel: ...
Custom Analytics: Enabled
```

**Update Analytics:**
1. Navigate to **Settings** → **Integrations** → **Analytics**
2. Configure analytics:
   - Enable analytics
   - Google Analytics ID
   - Mixpanel token
   - Custom analytics
3. Click **Save Changes**

## Advanced Settings

### Maintenance Mode

**Configuration:**
```yaml
Maintenance Mode: Disabled
Maintenance Message: "System maintenance in progress"
Allow Admin Access: true
Scheduled Maintenance: None
```

**Enable Maintenance Mode:**
1. Navigate to **Settings** → **Advanced** → **Maintenance**
2. Enable maintenance mode
3. Set maintenance message
4. Configure admin access
5. Click **Save Changes**

### Database

**Configuration:**
```yaml
Database Pool Size: 20
Max Connections: 100
Connection Timeout: 30 seconds
Query Timeout: 60 seconds
```

**Update Database Settings:**
1. Navigate to **Settings** → **Advanced** → **Database**
2. Configure:
   - Pool size
   - Max connections
   - Timeouts
3. Click **Save Changes**
4. Restart application

### Cache

**Configuration:**
```yaml
Cache Enabled: true
Cache Backend: Redis
Cache TTL: 300 seconds
Cache Prefix: clouisle:
```

**Update Cache Settings:**
1. Navigate to **Settings** → **Advanced** → **Cache**
2. Configure:
   - Enable cache
   - Cache backend
   - TTL
   - Prefix
3. Click **Save Changes**

## Backup and Restore

### Backup Settings

**Export Settings:**
1. Navigate to **Settings** → **Backup**
2. Click **Export Settings**
3. Download JSON file

**Import Settings:**
1. Navigate to **Settings** → **Backup**
2. Click **Import Settings**
3. Upload JSON file
4. Review changes
5. Confirm import

### Reset Settings

**Reset to Defaults:**
1. Navigate to **Settings** → **Advanced** → **Reset**
2. Select settings to reset:
   - All settings
   - Specific category
3. Confirm reset
4. Settings restored to defaults

## Best Practices

### Configuration

**✅ Do:**
- Document all configuration changes
- Test settings in staging first
- Backup settings before major changes
- Use environment variables for secrets
- Review settings regularly
- Monitor system after changes
- Keep settings organized

**❌ Don't:**
- Change multiple settings at once
- Skip testing
- Forget to backup
- Hardcode secrets
- Ignore warnings
- Make changes during peak hours

### Security

**✅ Do:**
- Use strong password policies
- Enable 2FA for admins
- Rotate API keys regularly
- Use HTTPS everywhere
- Enable security headers
- Monitor audit logs
- Restrict admin access

**❌ Don't:**
- Use weak passwords
- Disable security features
- Share admin credentials
- Allow HTTP
- Ignore security warnings
- Skip audit logs
- Grant unnecessary permissions

## Related Documentation

- [Environment Variables](../../deployment/environment-variables.md) - Environment config
- [Security Best Practices](../../best-practices/security.md) - Security guide
- [User Management](../users/user-management.md) - User admin
- [Team Management](../teams/team-management.md) - Team admin

---

**Last Updated**: 2026-02-11
