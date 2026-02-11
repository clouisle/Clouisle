# Team Settings

This guide explains how to configure team settings and manage team preferences.

## Overview

Team settings control team-wide configurations, member permissions, resource limits, and collaboration features. Proper configuration ensures smooth team operations and security.

## Accessing Team Settings

1. Click **Team** in sidebar
2. Select **Settings** tab
3. Choose settings category

**Required Permission:** Team Admin or Owner

## General Settings

### Team Information

**Team Name:**
- Display name for your team
- Must be unique
- 3-50 characters
- Can include spaces and special characters

**Team Slug:**
- URL-friendly identifier
- Lowercase letters, numbers, hyphens
- Cannot be changed after creation
- Used in URLs: `your-domain.com/team/team-slug`

**Description:**
- Optional team description
- Helps members understand team purpose
- Supports markdown formatting
- Max 500 characters

**Avatar:**
- Team profile image
- Recommended: 200x200px
- Max size: 2 MB
- Formats: JPG, PNG, GIF

**Example:**
```yaml
Team Name: Engineering Team
Team Slug: engineering
Description: Product engineering and development team
Avatar: team-avatar.png
```

### Team Visibility

**Private:**
- Only invited members can see team
- Team not listed in directory
- Resources not discoverable

**Internal:**
- All organization users can see team
- Team listed in directory
- Resources visible to organization

**Public:**
- Anyone can see team (if enabled)
- Team listed publicly
- Resources may be public

**Configuration:**
```yaml
Visibility: Internal
Allow Discovery: true
Show in Directory: true
```

## Member Management

### Default Role

**New Member Role:**
- Role assigned to new members
- Options: Member, Viewer
- Can be changed per invitation

**Recommended:**
- Use **Member** for active contributors
- Use **Viewer** for read-only access

### Invitation Settings

**Invitation Expiry:**
- How long invitations remain valid
- Range: 1-30 days
- Default: 7 days

**Require Approval:**
- Admin approval for join requests
- Recommended for public teams
- Disabled for private teams

**Email Domains:**
- Restrict by email domain
- Example: `@company.com`
- Multiple domains supported

**Configuration:**
```yaml
Default Role: Member
Invitation Expiry: 7 days
Require Approval: false
Allowed Domains:
  - company.com
  - partner.com
```

### Member Limits

**Maximum Members:**
- Set team size limit
- Range: 1-1000
- Based on plan

**Active Members:**
- Current member count
- Excludes pending invitations
- Includes all roles

## Resource Limits

### Agents

**Agent Limits:**
- Maximum agents per team
- Based on plan
- Default: 10 (Starter), 50 (Pro), Unlimited (Enterprise)

**Agent Settings:**
- Default model
- Default temperature
- Default max tokens

**Configuration:**
```yaml
Max Agents: 50
Default Model: gpt-4-turbo
Default Temperature: 0.7
Default Max Tokens: 2000
```

### Knowledge Bases

**KB Limits:**
- Maximum knowledge bases
- Maximum documents per KB
- Maximum storage

**Storage Allocation:**
- Total storage: Based on plan
- Per KB limit: Optional
- Auto-cleanup: Optional

**Configuration:**
```yaml
Max Knowledge Bases: 20
Max Documents per KB: 10000
Total Storage: 100 GB
Storage per KB: 5 GB
Auto Cleanup: Enabled
Cleanup After: 90 days (inactive)
```

### Workflows

**Workflow Limits:**
- Maximum workflows
- Maximum executions per month
- Execution timeout

**Configuration:**
```yaml
Max Workflows: 100
Max Executions: 10000/month
Execution Timeout: 300 seconds
Max Nodes per Workflow: 100
```

### Conversations

**Conversation Limits:**
- Maximum active conversations
- Message retention period
- Auto-archive settings

**Configuration:**
```yaml
Max Active Conversations: 1000
Message Retention: 90 days
Auto Archive: Enabled
Archive After: 30 days (inactive)
```

## Security Settings

### Authentication

**Password Policy:**
- Minimum length: 8-20 characters
- Require uppercase: Yes/No
- Require numbers: Yes/No
- Require special characters: Yes/No
- Password expiry: 30-365 days

**Two-Factor Authentication:**
- Require 2FA: Yes/No
- 2FA methods: TOTP, SMS, Email
- Grace period: 7-30 days

**Configuration:**
```yaml
Password Policy:
  Min Length: 12
  Require Uppercase: true
  Require Numbers: true
  Require Special: true
  Expiry Days: 90

Two-Factor Auth:
  Required: true
  Methods: [TOTP, Email]
  Grace Period: 14 days
```

### Session Management

**Session Settings:**
- Session timeout: 15-1440 minutes
- Remember me: Yes/No
- Max concurrent sessions: 1-10

**Configuration:**
```yaml
Session Timeout: 30 minutes
Remember Me: Enabled
Remember Duration: 30 days
Max Concurrent Sessions: 3
```

### IP Restrictions

**Allowed IP Ranges:**
- Restrict access by IP
- CIDR notation supported
- Multiple ranges allowed

**Example:**
```yaml
IP Restrictions: Enabled
Allowed IPs:
  - 192.168.1.0/24
  - 10.0.0.0/8
  - 203.0.113.0/24
```

## API Settings

### API Access

**Enable API:**
- Allow API access for team
- Required for integrations
- Can be disabled for security

**API Rate Limits:**
- Requests per minute
- Requests per hour
- Requests per day

**Configuration:**
```yaml
API Enabled: true
Rate Limits:
  Per Minute: 60
  Per Hour: 1000
  Per Day: 10000
```

### API Keys

**Key Settings:**
- Allow API key creation
- Key expiration policy
- Maximum keys per user

**Configuration:**
```yaml
Allow API Keys: true
Key Expiry: 90 days
Max Keys per User: 5
Auto Rotate: Enabled
Rotation Period: 30 days
```

### Webhooks

**Webhook Settings:**
- Allow webhook creation
- Maximum webhooks
- Retry policy

**Configuration:**
```yaml
Allow Webhooks: true
Max Webhooks: 20
Retry Attempts: 5
Retry Delay: 1m, 5m, 15m, 1h, 6h
Timeout: 30 seconds
```

## Notification Settings

### Email Notifications

**Team Notifications:**
- New member joined
- Member removed
- Role changed
- Resource limits reached
- Security alerts

**Frequency:**
- Immediate
- Daily digest
- Weekly digest
- Disabled

**Configuration:**
```yaml
Email Notifications:
  New Member: Immediate
  Member Removed: Immediate
  Role Changed: Immediate
  Resource Limits: Daily
  Security Alerts: Immediate
```

### Webhook Notifications

**Event Types:**
- Team events
- Member events
- Resource events
- Security events

**Configuration:**
```yaml
Webhook URL: https://your-domain.com/webhooks/team
Events:
  - team.member_added
  - team.member_removed
  - team.resource_limit_reached
  - team.security_alert
```

## Billing Settings

### Plan Information

**Current Plan:**
- Plan name
- Billing cycle
- Next billing date
- Amount

**Usage:**
- Current usage
- Plan limits
- Overage charges

### Payment Method

**Payment Details:**
- Credit card
- Bank account
- Invoice

**Billing Contact:**
- Billing email
- Billing address
- Tax ID

## Integration Settings

### SSO Configuration

**SSO Provider:**
- OAuth2
- OIDC
- SAML
- CAS

**Configuration:**
```yaml
SSO Enabled: true
Provider: OIDC
Provider Name: Okta
Client ID: your-client-id
Client Secret: ***
Authorization URL: https://okta.com/oauth2/authorize
Token URL: https://okta.com/oauth2/token
User Info URL: https://okta.com/oauth2/userinfo
```

### Third-Party Integrations

**Available Integrations:**
- Slack
- Microsoft Teams
- Discord
- Email
- Webhooks

**Slack Integration:**
```yaml
Slack Enabled: true
Workspace: your-workspace
Channel: #notifications
Events:
  - agent.created
  - workflow.completed
  - error.occurred
```

## Data Management

### Data Retention

**Retention Policies:**
- Conversations: 90 days
- Audit logs: 365 days
- Workflow executions: 30 days
- API logs: 7 days

**Configuration:**
```yaml
Retention Policies:
  Conversations: 90 days
  Audit Logs: 365 days
  Workflow Executions: 30 days
  API Logs: 7 days
  Auto Delete: Enabled
```

### Data Export

**Export Settings:**
- Allow data export
- Export format: JSON, CSV
- Include attachments: Yes/No

**Configuration:**
```yaml
Allow Export: true
Export Formats: [JSON, CSV]
Include Attachments: true
Max Export Size: 1 GB
```

### Data Deletion

**Deletion Policy:**
- Soft delete: 30 days
- Hard delete: After 30 days
- Immediate deletion: Admin only

**Configuration:**
```yaml
Soft Delete Period: 30 days
Allow Immediate Delete: Admins only
Require Confirmation: true
```

## Audit Settings

### Audit Logging

**Log Events:**
- User actions
- Admin actions
- API calls
- Security events

**Configuration:**
```yaml
Audit Logging: Enabled
Log Events:
  - user.login
  - user.logout
  - admin.action
  - api.call
  - security.alert
Retention: 365 days
```

### Audit Alerts

**Alert Conditions:**
- Failed login attempts
- Permission changes
- Resource deletion
- API abuse

**Configuration:**
```yaml
Audit Alerts:
  Failed Logins:
    Threshold: 5 attempts
    Window: 15 minutes
    Action: Lock account
  Permission Changes:
    Alert: Immediate
    Notify: Admins
  Resource Deletion:
    Require: Confirmation
    Notify: Owners
```

## Advanced Settings

### Custom Domain

**Domain Configuration:**
- Custom domain: `team.your-domain.com`
- SSL certificate: Auto or custom
- DNS configuration

**Setup:**
1. Add DNS records
2. Verify domain
3. Enable SSL
4. Update team settings

### Branding

**Custom Branding:**
- Logo
- Colors
- Fonts
- Email templates

**Configuration:**
```yaml
Branding:
  Logo: team-logo.png
  Primary Color: #0066cc
  Secondary Color: #00cc66
  Font: Inter
  Custom CSS: Enabled
```

### API Customization

**Custom Endpoints:**
- Custom base URL
- API versioning
- Custom headers

**Configuration:**
```yaml
API Customization:
  Base URL: api.your-domain.com
  Version: v1
  Custom Headers:
    X-Team-ID: team-123
    X-Environment: production
```

## Best Practices

### Security

**✅ Do:**
- Enable 2FA for all members
- Set strong password policy
- Restrict IP access if possible
- Review audit logs regularly
- Rotate API keys periodically
- Use SSO for enterprise
- Monitor security alerts

**❌ Don't:**
- Disable security features
- Use weak passwords
- Share API keys
- Ignore security alerts
- Skip audit reviews
- Allow unlimited access
- Forget to rotate keys

### Resource Management

**✅ Do:**
- Set appropriate limits
- Monitor usage regularly
- Enable auto-cleanup
- Archive inactive resources
- Review resource allocation
- Plan for growth
- Optimize costs

**❌ Don't:**
- Set unlimited limits
- Ignore usage patterns
- Keep all resources forever
- Let resources accumulate
- Skip capacity planning
- Overprovision resources
- Ignore cost optimization

### Team Collaboration

**✅ Do:**
- Set clear roles
- Document team processes
- Use consistent naming
- Enable notifications
- Train new members
- Review settings regularly
- Communicate changes

**❌ Don't:**
- Give everyone admin access
- Skip documentation
- Use inconsistent naming
- Disable all notifications
- Assume members know settings
- Never review settings
- Make changes without notice

## Troubleshooting

### Cannot Change Settings

**Problem:** Settings changes not saving

**Solutions:**
1. Check user permissions (need Admin/Owner)
2. Verify no validation errors
3. Check browser console for errors
4. Try different browser
5. Contact support

### Members Cannot Join

**Problem:** Invitations not working

**Solutions:**
1. Check invitation expiry
2. Verify email domain restrictions
3. Check member limit
4. Review approval settings
5. Check spam folder

### API Access Issues

**Problem:** API calls failing

**Solutions:**
1. Verify API is enabled
2. Check rate limits
3. Verify API key validity
4. Check IP restrictions
5. Review API logs

## Related Documentation

- [User Management](../../admin-guide/users/user-management.md) - User administration
- [Permissions](../../admin-guide/permissions/permission-management.md) - Permission management
- [Security Settings](../../admin-guide/settings/system-settings.md) - System security
- [Audit Logs](../../admin-guide/audit-logs/audit-log-management.md) - Audit logging

---

**Last Updated**: 2026-02-11
