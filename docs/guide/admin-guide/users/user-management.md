# User Management

This guide explains how to manage users in Clouisle as an administrator.

## Overview

User management allows administrators to:

- **Create users**: Add new users to the system
- **Manage accounts**: Update user information and settings
- **Control access**: Activate, deactivate, and delete users
- **Assign roles**: Set user roles and team memberships
- **Enforce policies**: Apply password and security policies
- **Communicate**: Send emails to users

## Accessing User Management

### From Admin Dashboard

**Steps:**

1. Log in as administrator
2. Go to **Admin** section
3. Click **"Users"** in sidebar
4. View user management interface

**Or:**

- Navigate directly to `/users`

### User List

**User list view:**
```
┌─────────────────────────────────────────────────────┐
│ Users (156)                    [+ Create User] [⚙️]  │
├─────────────────────────────────────────────────────┤
│                                                     │
│ Search: [________________] [Filters ▼]              │
│                                                     │
│ 👤 Alice Johnson (alice@example.com)                │
│    Status: Active • Role: Admin                    │
│    Teams: 3 • Last login: 2 hours ago              │
│    [View] [Edit] [...]                             │
│                                                     │
│ 👤 Bob Smith (bob@example.com)                      │
│    Status: Active • Role: Member                   │
│    Teams: 2 • Last login: Yesterday                │
│    [View] [Edit] [...]                             │
│                                                     │
│ 👤 Carol Davis (carol@example.com)                  │
│    Status: Inactive • Role: Viewer                 │
│    Teams: 1 • Last login: 30 days ago              │
│    [View] [Edit] [...]                             │
│                                                     │
└─────────────────────────────────────────────────────┘
```

## Creating Users

### Manual User Creation

**Steps:**

1. Click **"+ Create User"** button
2. Fill in user information:
   - **Email**: User's email address
   - **Username**: Unique username
   - **Full Name**: User's full name
   - **Password**: Initial password (or auto-generate)
   - **Role**: Global role (Super Admin, Admin, Member, Viewer)
   - **Teams**: Assign to teams (optional)
3. Click **"Create User"**
4. User is created

**Create user form:**
```
┌─────────────────────────────────────────┐
│ Create User                             │
├─────────────────────────────────────────┤
│                                         │
│ Email: *                                │
│ [alice@example.com__________]           │
│                                         │
│ Username: *                             │
│ [alice___________________]              │
│                                         │
│ Full Name: *                            │
│ [Alice Johnson___________]              │
│                                         │
│ Password: *                             │
│ [••••••••••] [Generate] [Show]          │
│                                         │
│ Global Role:                            │
│ ○ Super Admin                           │
│ ○ Admin                                 │
│ ● Member                                │
│ ○ Viewer                                │
│                                         │
│ Teams: (optional)                       │
│ [Select teams...________] [+ Add]       │
│                                         │
│ [Cancel]  [Create User]                 │
│                                         │
└─────────────────────────────────────────┘
```

### Bulk User Import

> **Note:** Not implemented / Roadmap. There is no CSV user import with preview. Users are created one at a time (`POST /api/v1/admin/users`) or provisioned automatically through SSO when `sso_auto_create_users` is enabled.

### SSO User Provisioning

**Automatic user creation via SSO:**

1. Configure SSO provider
2. Enable `sso_auto_create_users` in the SSO settings
3. Users log in via SSO
4. Accounts created automatically
5. Assigned to the default role and default team (if configured)

**Auto-provisioning settings (Site Settings → Security/SSO):**
```
┌─────────────────────────────────────────┐
│ SSO Auto-Provisioning                   │
├─────────────────────────────────────────┤
│                                         │
│ ☑ Enable auto-provisioning              │
│    (sso_auto_create_users)              │
│                                         │
│ Default Role:                           │
│ (default_role_id — Viewer by default)   │
│                                         │
│ Default Team:                           │
│ (default_team_id + default_team_role)   │
│                                         │
│ ☑ Match by email                        │
│    (sso_match_by_email)                 │
│ ☐ Require approval                      │
│    (sso_require_approval)               │
│                                         │
│ [Save Settings]                         │
│                                         │
└─────────────────────────────────────────┘
```

> **Note:** Not implemented / Roadmap: email-domain restrictions for SSO provisioning are not available.

## Viewing User Details

### User Profile

**View complete user information:**

1. Click on user in list
2. User details panel opens
3. View all user information

**User details:**
```
┌─────────────────────────────────────────┐
│ Alice Johnson                    [Edit] │
├─────────────────────────────────────────┤
│                                         │
│ 👤 alice@example.com                    │
│    Username: alice                      │
│    Status: ✅ Active                    │
│    Global Role: Admin                   │
│                                         │
│ Account Information:                    │
│ • Created: 2026-01-15 10:00:00         │
│ • Last Login: 2 hours ago              │
│ • Login Count: 234                     │
│ • Failed Logins: 0                     │
│ • Password Expiration: exempt/expiring │
│                                         │
│ Teams (3):                              │
│ • Marketing Team (Owner)               │
│ • Sales Team (Admin)                   │
│ • Support Team (Member)                │
│                                         │
│ Security:                               │
│ • 2FA: ✅ Enabled (admin status)        │
│ • SSO: ✅ Google                        │
│ • Last Password Change: 30 days ago    │
│                                         │
│ [Force Password Change] [Deactivate]    │
│ [Delete]                                │
│                                         │
└─────────────────────────────────────────┘
```

### User Activity

> **Note:** Not implemented / Roadmap. There is no per-user activity view inside user management. User actions can be reviewed through **Audit Logs** filtered by the user.

## Editing Users

### Update User Information

**Steps:**

1. Open user details
2. Click **"Edit"** button
3. Update fields:
   - Full name
   - Email (if allowed)
   - Username (if allowed)
   - Role
   - Status
4. Click **"Save Changes"**

**Edit user form:**
```
┌─────────────────────────────────────────┐
│ Edit User - Alice Johnson               │
├─────────────────────────────────────────┤
│                                         │
│ Full Name:                              │
│ [Alice Johnson___________]              │
│                                         │
│ Email:                                  │
│ [alice@example.com__________]           │
│                                         │
│ Username:                               │
│ [alice___________________]              │
│ (Cannot be changed)                     │
│                                         │
│ Global Role:                            │
│ ○ Super Admin                           │
│ ● Admin                                 │
│ ○ Member                                │
│ ○ Viewer                                │
│                                         │
│ Status:                                 │
│ ● Active                                │
│ ○ Inactive                              │
│                                         │
│ [Cancel]  [Save Changes]                │
│                                         │
└─────────────────────────────────────────┘
```

### Password Policies (Admin)

There is no "reset password to a temporary password" flow. Administrators manage password policy per user instead:

- **Force password change**: `POST /api/v1/admin/users/{user_id}/force-password-change` — requires the user to set a new password
- **Reset password expiration**: `POST /api/v1/admin/users/{user_id}/reset-password-expiration` — restarts the expiration timer
- **Exempt from expiration**: `POST /api/v1/admin/users/{user_id}/exempt-password-expiration`
- **Bulk force password change**: `POST /api/v1/admin/users/bulk-force-password-change`
- **Password expiration overview**: `GET /api/v1/admin/users/password-expiration-stats` and `GET /api/v1/admin/users/expiring-passwords`

> **Note:** Not implemented / Roadmap: generating a temporary password or sending a reset email from the admin panel is not available.

### Manage Team Memberships

**View user's teams:**

1. Open user details
2. View the user's teams and roles

**Team management:**
```
┌─────────────────────────────────────────┐
│ Team Memberships - Alice Johnson        │
├─────────────────────────────────────────┤
│                                         │
│ Current Teams (3):                      │
│                                         │
│ Marketing Team                          │
│ Role: Owner                             │
│ Joined: 2026-01-15                     │
│                                         │
│ Sales Team                              │
│ Role: Admin                             │
│ Joined: 2026-01-20                     │
│                                         │
│ Support Team                            │
│ Role: Member                            │
│ Joined: 2026-02-01                     │
│                                         │
└─────────────────────────────────────────┘
```

> **Note:** Adding/removing users and changing team roles is done from the **Teams** page (Add Member, Change Role, Remove Member, Transfer Ownership), not from the user detail view.

## User Status Management

### Activating Users

**Activate inactive user:**

1. Find inactive user
2. Click **"..."** menu
3. Select **"Activate"**
4. Confirm activation
5. User can log in again

**What happens:**
- User can log in
- Access to resources restored
- Team memberships active
- API keys enabled

### Deactivating Users

**Temporarily disable user access:**

1. Open user details
2. Click **"Deactivate"** button
3. Provide reason (optional)
4. Confirm deactivation
5. User is deactivated

**Deactivation confirmation:**
```
┌─────────────────────────────────────────┐
│ ⚠️ Deactivate User?                     │
├─────────────────────────────────────────┤
│                                         │
│ User: Alice Johnson                     │
│ Email: alice@example.com                │
│                                         │
│ What happens:                           │
│ • User cannot log in                    │
│ • API keys are disabled                 │
│ • Resources are preserved               │
│ • Can be reactivated later              │
│                                         │
│ Reason: (optional)                      │
│ [Employee on leave__________]           │
│                                         │
│ [Cancel]  [Deactivate User]             │
│                                         │
└─────────────────────────────────────────┘
```

**What happens:**
- User cannot log in
- API keys disabled
- Resources preserved
- Team memberships preserved
- Can be reactivated

### Deleting Users

**Permanently delete user:**

1. Open user details
2. Click **"Delete"** button
3. Review what will be deleted
4. Type username to confirm
5. Click **"Delete Permanently"**

**Delete confirmation:**
```
┌─────────────────────────────────────────┐
│ ⚠️ Delete User Permanently?             │
├─────────────────────────────────────────┤
│                                         │
│ User: Alice Johnson                     │
│ Email: alice@example.com                │
│                                         │
│ ⚠️ This action cannot be undone!        │
│                                         │
│ What will be deleted:                   │
│ • User account and profile              │
│ • Personal conversations                │
│ • API keys                              │
│ • Personal resources (if no team)       │
│                                         │
│ What will be preserved:                 │
│ • Team resources (transferred to team)  │
│ • Audit logs (for compliance)           │
│ • Team memberships (removed)            │
│                                         │
│ Type username to confirm:               │
│ [________________]                      │
│                                         │
│ [Cancel]  [Delete Permanently]          │
│                                         │
└─────────────────────────────────────────┘
```

## Bulk Operations

### Bulk Actions

**Available bulk actions:**

- **Bulk force password change**: `POST /api/v1/admin/users/bulk-force-password-change` — force selected users to change their password
- **Send email**: `POST /api/v1/admin/users/send-email` — send an email to selected users

> **Note:** Not implemented / Roadmap: bulk activate/deactivate, bulk add/remove from teams, bulk export, and bulk delete are not available.

### Bulk Import/Export

> **Note:** Not implemented / Roadmap. There is no user export (CSV/JSON/Excel) and no user import.

## User Permissions

### System Roles

**Available global roles:**

| Role | Permissions |
|------|-------------|
| **Super Admin** | All permissions (`*`) |
| **Admin** | Dashboard access, system read visibility, team-scoped resource management |
| **Member** | Daily resource creation and editing without dashboard access |
| **Viewer** | Default read-only role with chat/run/execute permissions |

**Changing user role:**

1. Open user details
2. Edit user
3. Change **Global Role**
4. Save changes
5. User permissions updated

### Team Roles

**Users can have different roles in different teams:**

- Owner: Full team control
- Admin: Manage team members and resources
- Member: Create and use resources
- Viewer: Read-only access

See [Team Roles](../../user-guide/teams/team-roles.md) for details.

## Security Features

### Account Security

**Security settings per user:**

1. **Password Policy**: Enforced globally (Site Settings → Security)
2. **2FA (TOTP)**: Check status and disable per user (admin endpoints)
3. **Password Expiration**: Force change, reset expiration, or exempt per user

**Security settings:**
```
┌─────────────────────────────────────────┐
│ Security Settings - Alice Johnson       │
├─────────────────────────────────────────┤
│                                         │
│ Password:                               │
│ • Last Changed: 30 days ago            │
│ • Expiration: exempt/expiring          │
│ [Force Password Change]                 │
│ [Reset Password Expiration]             │
│ [Exempt from Expiration]                │
│                                         │
│ Two-Factor Authentication:              │
│ • Status: ✅ Enabled                    │
│ • Method: Authenticator App            │
│ [Disable 2FA]                           │
│                                         │
└─────────────────────────────────────────┘
```

> **Note:** Admin TOTP endpoints are `GET /api/v1/admin/totp/users/{user_id}/status` and `POST /api/v1/admin/totp/users/{user_id}/disable` (superuser only).
>
> Not implemented / Roadmap: per-user session management (active sessions list, revoke sessions) and login history views are not available in user management. Account lockout is enforced by the global login policy (`max_login_attempts`, `lockout_duration_minutes`).

### Audit Logging

**Track user actions:**

1. All user actions are logged
2. Review audit logs filtered by user (Audit Logs page)
3. Export logs for compliance (CSV/JSON from Audit Logs)

## Best Practices

### User Management

**✅ Do:**
- Review user accounts regularly
- Deactivate inactive users
- Enforce strong password policies
- Enable 2FA for privileged accounts
- Monitor failed login attempts
- Document user changes

**❌ Don't:**
- Create unnecessary admin accounts
- Share user credentials
- Skip deactivation when users leave
- Ignore security alerts
- Forget to transfer ownership
- Allow weak passwords

### Security

**✅ Do:**
- Require 2FA for admins
- Monitor audit logs
- Set password expiration
- Lock accounts after failed attempts
- Regular security audits

**❌ Don't:**
- Disable security features
- Ignore suspicious activity
- Allow unlimited login attempts
- Skip audit log reviews
- Share admin credentials

## Troubleshooting

### Cannot Create User

**Problem**: User creation fails

**Solutions:**
1. Check email is unique
2. Verify username is unique
3. Check email format
4. Verify password meets requirements
5. Review error message
6. Contact support

### User Cannot Log In

**Problem**: User reports login issues

**Solutions:**
1. Check account is active
2. Verify password is correct
3. Check if account is locked
4. Review failed login attempts
5. Reset password
6. Check 2FA settings
7. Review audit logs

### Cannot Delete User

**Problem**: Delete option disabled

**Solutions:**
1. Check if user is team owner
2. Transfer team ownership first
3. Check if user has active resources
4. Deactivate user instead
5. Contact support

## Related Documentation

- [Team Management](./team-management.md) - Managing teams
- [System Settings](../settings/system-settings.md) - Security configuration
- [Audit Logs](../audit-logs/audit-log-management.md) - Viewing audit logs
- [SSO Configuration](../settings/SSO.md) - SSO setup

## Getting Help

If you need assistance with user management:

1. **Documentation**: Review this guide
2. **Admin Help**: Click **?** icon in admin interface
3. **Support**: Contact Clouisle support
4. **Community**: Visit community forums

---

**Last Updated**: 2026-02-11
