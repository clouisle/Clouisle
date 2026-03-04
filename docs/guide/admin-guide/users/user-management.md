# User Management

This guide explains how to manage users in Clouisle as an administrator.

## Overview

User management allows administrators to:

- **Create users**: Add new users to the system
- **Manage accounts**: Update user information and settings
- **Control access**: Activate, deactivate, and delete users
- **Assign roles**: Set user permissions and team memberships
- **Monitor activity**: Track user actions and usage
- **Enforce policies**: Apply security and compliance rules

## Accessing User Management

### From Admin Dashboard

**Steps:**

1. Log in as administrator
2. Go to **Admin** section
3. Click **"Users"** in sidebar
4. View user management interface

**Or:**

- Navigate directly to `/admin/users`

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
│    Status: Active • Role: User                     │
│    Teams: 2 • Last login: Yesterday                │
│    [View] [Edit] [...]                             │
│                                                     │
│ 👤 Carol Davis (carol@example.com)                  │
│    Status: Inactive • Role: User                   │
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
   - **Role**: System role (Admin, User)
   - **Teams**: Assign to teams (optional)
3. Click **"Create User"**
4. User receives welcome email

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
│ System Role:                            │
│ ○ Admin                                 │
│ ● User                                  │
│                                         │
│ Teams: (optional)                       │
│ [Select teams...________] [+ Add]       │
│                                         │
│ ☑ Send welcome email                    │
│ ☑ Require password change on first login│
│                                         │
│ [Cancel]  [Create User]                 │
│                                         │
└─────────────────────────────────────────┘
```

### Bulk User Import

**Import multiple users from CSV:**

1. Click **"Import Users"** button
2. Download CSV template
3. Fill in user information
4. Upload CSV file
5. Review import preview
6. Confirm import
7. Users are created

**CSV format:**
```csv
email,username,full_name,role,teams
alice@example.com,alice,Alice Johnson,user,"Marketing,Sales"
bob@example.com,bob,Bob Smith,user,Engineering
carol@example.com,carol,Carol Davis,admin,""
```

**Import preview:**
```
┌─────────────────────────────────────────┐
│ Import Preview (3 users)                │
├─────────────────────────────────────────┤
│                                         │
│ ✅ alice@example.com                    │
│    Username: alice                      │
│    Teams: Marketing, Sales              │
│                                         │
│ ✅ bob@example.com                      │
│    Username: bob                        │
│    Teams: Engineering                   │
│                                         │
│ ⚠️ carol@example.com                    │
│    Warning: Email already exists        │
│    Action: Skip                         │
│                                         │
│ Summary:                                │
│ • 2 users will be created               │
│ • 1 user will be skipped                │
│                                         │
│ [Cancel]  [Import Users]                │
│                                         │
└─────────────────────────────────────────┘
```

### SSO User Provisioning

**Automatic user creation via SSO:**

1. Configure SSO provider
2. Enable auto-provisioning
3. Users log in via SSO
4. Accounts created automatically
5. Assigned to default team (if configured)

**Auto-provisioning settings:**
```
┌─────────────────────────────────────────┐
│ SSO Auto-Provisioning                   │
├─────────────────────────────────────────┤
│                                         │
│ ☑ Enable auto-provisioning              │
│                                         │
│ Default Role:                           │
│ ● User                                  │
│ ○ Admin                                 │
│                                         │
│ Default Team:                           │
│ [Select team...________] (optional)     │
│                                         │
│ Email Domain Restrictions:              │
│ [example.com________] [+ Add]           │
│                                         │
│ ☑ Require email verification            │
│ ☑ Send welcome email                    │
│                                         │
│ [Save Settings]                         │
│                                         │
└─────────────────────────────────────────┘
```

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
│    Role: Admin                          │
│                                         │
│ Account Information:                    │
│ • Created: 2026-01-15 10:00:00         │
│ • Last Login: 2 hours ago              │
│ • Login Count: 234                     │
│ • Failed Logins: 0                     │
│                                         │
│ Teams (3):                              │
│ • Marketing Team (Owner)               │
│ • Sales Team (Admin)                   │
│ • Support Team (Member)                │
│                                         │
│ Resources:                              │
│ • Agents: 12                           │
│ • Workflows: 8                         │
│ • Conversations: 45                    │
│ • API Keys: 3                          │
│                                         │
│ Security:                               │
│ • 2FA: ✅ Enabled                       │
│ • SSO: ✅ Google                        │
│ • Last Password Change: 30 days ago    │
│                                         │
│ [View Activity] [Reset Password]        │
│ [Deactivate] [Delete]                  │
│                                         │
└─────────────────────────────────────────┘
```

### User Activity

**View user activity log:**

1. Open user details
2. Click **"View Activity"** tab
3. See recent actions

**Activity log:**
```
┌─────────────────────────────────────────┐
│ User Activity - Alice Johnson           │
├─────────────────────────────────────────┤
│                                         │
│ Today                                   │
│ ─────────────────────────────────────  │
│ 14:30 • Created agent "Content Writer" │
│ 12:15 • Ran workflow "SEO Analysis"    │
│ 10:00 • Logged in from 192.168.1.100   │
│                                         │
│ Yesterday                               │
│ ─────────────────────────────────────  │
│ 16:45 • Uploaded document to KB        │
│ 14:20 • Updated agent "Support Bot"    │
│ 09:30 • Logged in from 192.168.1.100   │
│                                         │
│ [Load More Activity]                    │
│                                         │
└─────────────────────────────────────────┘
```

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
│ System Role:                            │
│ ● Admin                                 │
│ ○ User                                  │
│                                         │
│ Status:                                 │
│ ● Active                                │
│ ○ Inactive                              │
│                                         │
│ [Cancel]  [Save Changes]                │
│                                         │
└─────────────────────────────────────────┘
```

### Reset Password

**Reset user password:**

1. Open user details
2. Click **"Reset Password"**
3. Choose method:
   - **Generate temporary password**
   - **Send reset email**
4. Confirm action
5. User receives new password or reset link

**Reset password dialog:**
```
┌─────────────────────────────────────────┐
│ Reset Password - Alice Johnson          │
├─────────────────────────────────────────┤
│                                         │
│ Choose reset method:                    │
│                                         │
│ ● Generate temporary password           │
│   User will receive email with          │
│   temporary password and must change    │
│   it on first login.                    │
│                                         │
│ ○ Send password reset link              │
│   User will receive email with link     │
│   to reset their password.              │
│                                         │
│ [Cancel]  [Reset Password]              │
│                                         │
└─────────────────────────────────────────┘
```

### Manage Team Memberships

**Add/remove user from teams:**

1. Open user details
2. Go to **"Teams"** tab
3. Click **"Add to Team"** or **"Remove from Team"**
4. Select team
5. Choose role (for adding)
6. Confirm action

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
│ [Change Role] [Remove]                  │
│                                         │
│ Sales Team                              │
│ Role: Admin                             │
│ Joined: 2026-01-20                     │
│ [Change Role] [Remove]                  │
│                                         │
│ Support Team                            │
│ Role: Member                            │
│ Joined: 2026-02-01                     │
│ [Change Role] [Remove]                  │
│                                         │
│ [+ Add to Team]                         │
│                                         │
└─────────────────────────────────────────┘
```

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

**Perform actions on multiple users:**

1. Select users (checkboxes)
2. Click **"Bulk Actions"** dropdown
3. Choose action:
   - Activate
   - Deactivate
   - Add to team
   - Remove from team
   - Export data
   - Delete
4. Confirm action
5. Action applied to all selected users

**Bulk actions toolbar:**
```
┌─────────────────────────────────────────┐
│ 5 users selected                        │
│ [Bulk Actions ▼] [Clear Selection]     │
│                                         │
│ • Activate                              │
│ • Deactivate                            │
│ • Add to Team                           │
│ • Remove from Team                      │
│ • Export Data                           │
│ • Delete                                │
└─────────────────────────────────────────┘
```

### Bulk Import/Export

**Export user data:**

1. Click **"Export"** button
2. Select export format:
   - CSV
   - JSON
   - Excel
3. Choose fields to export
4. Click **"Export"**
5. File is downloaded

**Export options:**
```
┌─────────────────────────────────────────┐
│ Export Users                            │
├─────────────────────────────────────────┤
│                                         │
│ Format:                                 │
│ ● CSV                                   │
│ ○ JSON                                  │
│ ○ Excel                                 │
│                                         │
│ Fields:                                 │
│ ☑ Email                                 │
│ ☑ Username                              │
│ ☑ Full Name                             │
│ ☑ Status                                │
│ ☑ Role                                  │
│ ☑ Teams                                 │
│ ☑ Created Date                          │
│ ☑ Last Login                            │
│                                         │
│ Filters:                                │
│ Status: [All ▼]                         │
│ Role: [All ▼]                           │
│                                         │
│ [Cancel]  [Export]                      │
│                                         │
└─────────────────────────────────────────┘
```

## User Permissions

### System Roles

**Available system roles:**

| Role | Permissions |
|------|-------------|
| **Admin** | Full system access, user management, settings |
| **User** | Standard user access, create resources |

**Changing user role:**

1. Open user details
2. Edit user
3. Change **System Role**
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

1. **Password Policy**: Enforce strong passwords
2. **2FA**: Require two-factor authentication
3. **Session Management**: Control active sessions
4. **Login Restrictions**: IP whitelist, time-based access
5. **Account Lockout**: Auto-lock after failed attempts

**Security settings:**
```
┌─────────────────────────────────────────┐
│ Security Settings - Alice Johnson       │
├─────────────────────────────────────────┤
│                                         │
│ Password:                               │
│ • Last Changed: 30 days ago            │
│ • Strength: Strong                     │
│ [Force Password Change]                 │
│                                         │
│ Two-Factor Authentication:              │
│ • Status: ✅ Enabled                    │
│ • Method: Authenticator App            │
│ [Disable 2FA] [Reset 2FA]              │
│                                         │
│ Active Sessions (2):                    │
│ • Chrome on macOS (current)            │
│ • Safari on iOS                        │
│ [Revoke All Sessions]                   │
│                                         │
│ Login History:                          │
│ • Last Login: 2 hours ago              │
│ • Failed Attempts: 0                   │
│ • Account Locked: No                   │
│ [View Full History]                     │
│                                         │
└─────────────────────────────────────────┘
```

### Audit Logging

**Track user actions:**

1. All user actions are logged
2. View audit logs per user
3. Export logs for compliance
4. Monitor suspicious activity

**Audit log:**
```
┌─────────────────────────────────────────┐
│ Audit Log - Alice Johnson               │
├─────────────────────────────────────────┤
│                                         │
│ 2026-02-11 14:30:00                     │
│ Action: create_agent                    │
│ Resource: Content Writer                │
│ IP: 192.168.1.100                      │
│ Status: Success                         │
│                                         │
│ 2026-02-11 12:15:00                     │
│ Action: run_workflow                    │
│ Resource: SEO Analysis                  │
│ IP: 192.168.1.100                      │
│ Status: Success                         │
│                                         │
│ [Export Logs] [Filter]                  │
│                                         │
└─────────────────────────────────────────┘
```

## Best Practices

### User Management

**✅ Do:**
- Review user accounts regularly
- Deactivate inactive users
- Enforce strong password policies
- Enable 2FA for all users
- Monitor failed login attempts
- Document user changes
- Use bulk operations for efficiency
- Export user data for backup

**❌ Don't:**
- Create unnecessary admin accounts
- Share user credentials
- Skip deactivation when users leave
- Ignore security alerts
- Delete users without backup
- Forget to transfer ownership
- Allow weak passwords

### Security

**✅ Do:**
- Require 2FA for admins
- Monitor audit logs
- Set password expiration
- Lock accounts after failed attempts
- Review active sessions
- Enforce IP restrictions (if needed)
- Regular security audits

**❌ Don't:**
- Disable security features
- Ignore suspicious activity
- Allow unlimited login attempts
- Skip audit log reviews
- Share admin credentials
- Forget to revoke access

## Troubleshooting

### Cannot Create User

**Problem**: User creation fails

**Solutions:**
1. Check email is unique
2. Verify username is unique
3. Check email format
4. Verify password meets requirements
5. Check user limit not reached
6. Review error message
7. Contact support

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
- [Security Settings](../settings/security-settings.md) - Security configuration
- [Audit Logs](../audit-logs/viewing-logs.md) - Viewing audit logs
- [SSO Configuration](../settings/sso-configuration.md) - SSO setup

## Getting Help

If you need assistance with user management:

1. **Documentation**: Review this guide
2. **Admin Help**: Click **?** icon in admin interface
3. **Support**: Contact Clouisle support
4. **Community**: Visit community forums

---

**Last Updated**: 2026-02-11
