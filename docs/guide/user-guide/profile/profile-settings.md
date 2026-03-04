# Profile Settings

This guide explains how to manage your profile settings in Clouisle.

## Overview

Your profile contains:

- **Personal Information**: Name, email, avatar
- **Security Settings**: Password, 2FA, connected accounts
- **Preferences**: Language, timezone, notifications
- **API Keys**: Manage API access
- **Session Management**: Active sessions and devices

## Accessing Profile Settings

**Steps:**

1. Click your **profile icon** or **avatar** in the top-right corner
2. Select **"Profile Settings"** or **"Settings"** from dropdown
3. Profile settings page opens

**Or:**

- Navigate directly to `/settings` or `/profile`

## Personal Information

### Viewing Your Profile

**Profile overview:**
```
┌─────────────────────────────────────────┐
│ Profile                                 │
├─────────────────────────────────────────┤
│                                         │
│  [Avatar Image]                         │
│                                         │
│  Name:     John Doe                     │
│  Email:    john.doe@example.com         │
│  Username: johndoe                      │
│  Role:     Team Member                  │
│  Joined:   2026-01-15                   │
│                                         │
│  [Edit Profile]                         │
│                                         │
└─────────────────────────────────────────┘
```

### Editing Profile

**Steps:**

1. Go to **Profile Settings** → **Profile** tab
2. Click **"Edit Profile"** button
3. Update fields:
   - **Name**: Your display name
   - **Email**: Your email address (may be read-only for SSO)
   - **Avatar**: Upload new profile picture
   - **Bio**: Short description (optional)
4. Click **"Save Changes"**
5. Changes are saved immediately

**Profile fields:**

| Field | Editable | Description |
|-------|----------|-------------|
| **Name** | Yes | Display name shown to others |
| **Email** | Depends | Read-only for SSO accounts |
| **Username** | No | Cannot be changed after creation |
| **Avatar** | Yes | Profile picture (max 5 MB) |
| **Bio** | Yes | Short description (max 500 chars) |

### Changing Avatar

**Method 1: Upload Image**

1. Click on avatar or **"Change Avatar"**
2. Click **"Upload Image"**
3. Select image file (JPG, PNG, GIF)
4. Crop/resize if needed
5. Click **"Save"**

**Method 2: Use Gravatar**

1. Click **"Use Gravatar"**
2. Your Gravatar is automatically loaded
3. Based on your email address

**Method 3: Remove Avatar**

1. Click **"Remove Avatar"**
2. Confirm removal
3. Default avatar is used

**Avatar requirements:**
- Formats: JPG, PNG, GIF
- Max size: 5 MB
- Recommended: 256x256 pixels or larger
- Square images work best

## Security Settings

### Password Management

**Changing password:**

1. Go to **Profile Settings** → **Security** tab
2. Find **"Change Password"** section
3. Enter **current password**
4. Enter **new password**
5. Confirm **new password**
6. Click **"Change Password"**
7. Success message appears

**Password requirements:**
- Minimum 8 characters
- At least one uppercase letter
- At least one lowercase letter
- At least one number
- At least one special character

See [Password Management](../authentication/password-management.md) for details.

### Two-Factor Authentication (2FA)

**Enabling 2FA:**

1. Go to **Profile Settings** → **Security** tab
2. Find **"Two-Factor Authentication"** section
3. Click **"Enable 2FA"**
4. Scan QR code with authenticator app:
   - Google Authenticator
   - Authy
   - Microsoft Authenticator
5. Enter verification code from app
6. Save backup codes securely
7. Click **"Enable"**

**Backup codes:**
```
┌─────────────────────────────────────────┐
│ Backup Codes                            │
│                                         │
│ Save these codes in a safe place.      │
│ Each code can only be used once.       │
│                                         │
│  1. ABCD-1234-EFGH-5678                │
│  2. IJKL-9012-MNOP-3456                │
│  3. QRST-7890-UVWX-1234                │
│  4. YZAB-5678-CDEF-9012                │
│  5. GHIJ-3456-KLMN-7890                │
│                                         │
│  [Download]  [Print]  [Copy]           │
└─────────────────────────────────────────┘
```

**Disabling 2FA:**

1. Go to **Profile Settings** → **Security**
2. Click **"Disable 2FA"**
3. Enter current password
4. Enter 2FA code
5. Confirm disabling
6. 2FA is disabled

### Connected Accounts

**Linking SSO providers:**

1. Go to **Profile Settings** → **Security**
2. Find **"Connected Accounts"** section
3. Click **"Connect"** next to provider
4. Authorize connection
5. Provider is linked

**Connected accounts:**
```
┌─────────────────────────────────────────┐
│ Connected Accounts                      │
├─────────────────────────────────────────┤
│                                         │
│ Google:     ✓ Connected                 │
│             john.doe@gmail.com          │
│             [Disconnect]                │
│                                         │
│ GitHub:     [Connect]                   │
│                                         │
│ Microsoft:  [Connect]                   │
│                                         │
└─────────────────────────────────────────┘
```

**Unlinking accounts:**

1. Click **"Disconnect"** next to provider
2. Confirm disconnection
3. Provider is unlinked

**Warning**: Don't unlink all providers if you don't have a password set.

### Session Management

**Viewing active sessions:**

1. Go to **Profile Settings** → **Security**
2. Find **"Active Sessions"** section
3. View all logged-in devices

**Session information:**
```
┌─────────────────────────────────────────┐
│ Active Sessions                         │
├─────────────────────────────────────────┤
│                                         │
│ 💻 Current Session                      │
│    Chrome on macOS                      │
│    San Francisco, CA                    │
│    Last active: Just now                │
│                                         │
│ 📱 iPhone                               │
│    Safari on iOS                        │
│    San Francisco, CA                    │
│    Last active: 2 hours ago             │
│    [Revoke]                             │
│                                         │
│ 💻 Work Laptop                          │
│    Firefox on Windows                   │
│    New York, NY                         │
│    Last active: Yesterday               │
│    [Revoke]                             │
│                                         │
│ [Log Out All Other Sessions]           │
│                                         │
└─────────────────────────────────────────┘
```

**Revoking sessions:**

1. Click **"Revoke"** next to a session
2. Confirm revocation
3. Session is terminated

**Log out all sessions:**

1. Click **"Log Out All Other Sessions"**
2. Confirm action
3. All other sessions are terminated
4. Current session remains active

## Preferences

### Language Settings

**Changing language:**

1. Go to **Profile Settings** → **Preferences** tab
2. Find **"Language"** section
3. Select language from dropdown:
   - English
   - 中文 (Chinese)
4. Click **"Save"**
5. Interface updates immediately

### Timezone Settings

**Setting timezone:**

1. Go to **Profile Settings** → **Preferences**
2. Find **"Timezone"** section
3. Select timezone from dropdown
4. Click **"Save"**
5. All timestamps update to your timezone

**Auto-detect timezone:**

1. Click **"Auto-detect"** button
2. Timezone is detected from browser
3. Click **"Save"**

### Theme Settings

**Changing theme:**

1. Go to **Profile Settings** → **Preferences**
2. Find **"Theme"** section
3. Select theme:
   - **Light**: Light mode
   - **Dark**: Dark mode
   - **System**: Follow system preference
4. Theme updates immediately

### Notification Preferences

**Configuring notifications:**

1. Go to **Profile Settings** → **Notifications** tab
2. Configure notification types:

**Email notifications:**
```
┌─────────────────────────────────────────┐
│ Email Notifications                     │
├─────────────────────────────────────────┤
│                                         │
│ ☑ New messages                          │
│ ☑ Mentions and replies                  │
│ ☑ Team invitations                      │
│ ☑ Workflow completions                  │
│ ☐ Marketing emails                      │
│                                         │
└─────────────────────────────────────────┘
```

**In-app notifications:**
```
┌─────────────────────────────────────────┐
│ In-App Notifications                    │
├─────────────────────────────────────────┤
│                                         │
│ ☑ New messages                          │
│ ☑ Mentions                              │
│ ☑ Team updates                          │
│ ☑ System alerts                         │
│                                         │
└─────────────────────────────────────────┘
```

**Notification frequency:**
- **Real-time**: Instant notifications
- **Hourly digest**: Batched every hour
- **Daily digest**: Once per day
- **Off**: No notifications

3. Click **"Save Preferences"**

## API Keys

### Managing API Keys

**Viewing API keys:**

1. Go to **Profile Settings** → **API Keys** tab
2. View all your API keys

**API key list:**
```
┌─────────────────────────────────────────┐
│ API Keys                    [+ Create]  │
├─────────────────────────────────────────┤
│                                         │
│ Production API Key                      │
│ clou_1234...                            │
│ Created: 2026-01-15                     │
│ Last used: 2 hours ago                  │
│ Scopes: agent:read, agent:chat          │
│ [View] [Revoke]                         │
│                                         │
│ Development API Key                     │
│ clou_5678...                            │
│ Created: 2026-02-01                     │
│ Last used: Never                        │
│ Scopes: agent:read                      │
│ [View] [Revoke]                         │
│                                         │
└─────────────────────────────────────────┘
```

**Creating API key:**

1. Click **"+ Create"** button
2. Enter key details:
   - **Name**: Descriptive name
   - **Scopes**: Select permissions
   - **Expiration**: Set expiry date (optional)
3. Click **"Create"**
4. **Copy the key immediately** (shown only once)
5. Store key securely

**Revoking API key:**

1. Click **"Revoke"** next to key
2. Confirm revocation
3. Key is permanently disabled

See [Managing API Keys](../api-keys/managing-api-keys.md) for details.

## Account Management

### Deactivating Account

**Temporarily deactivate:**

1. Go to **Profile Settings** → **Account** tab
2. Find **"Deactivate Account"** section
3. Click **"Deactivate Account"**
4. Enter password to confirm
5. Click **"Deactivate"**
6. Account is deactivated

**What happens:**
- You're logged out immediately
- Your profile is hidden
- Your data is preserved
- You can reactivate anytime

**Reactivating:**

1. Log in with your credentials
2. Click **"Reactivate Account"**
3. Account is reactivated

### Deleting Account

**Permanently delete:**

1. Go to **Profile Settings** → **Account** tab
2. Find **"Delete Account"** section
3. Click **"Delete Account"**
4. Read the warning carefully
5. Type your username to confirm
6. Enter password
7. Click **"Permanently Delete"**

**Warning**: This action cannot be undone.

**What gets deleted:**
- Your profile and personal information
- All your conversations and messages
- Your API keys
- Your team memberships (if not owner)
- All uploaded files

**What's preserved:**
- Audit logs (for compliance)
- Team data (if you're a team owner, transfer ownership first)

## Data Export

### Exporting Your Data

**Request data export:**

1. Go to **Profile Settings** → **Privacy** tab
2. Find **"Export Data"** section
3. Click **"Request Export"**
4. Select data to export:
   - Profile information
   - Conversations
   - Uploaded files
   - API keys (metadata only)
5. Click **"Request Export"**
6. You'll receive email when ready

**Export format:**
- ZIP file containing JSON and files
- Typically ready within 24 hours
- Download link valid for 7 days

**Export contents:**
```
export.zip
├── profile.json
├── conversations/
│   ├── conversation_1.json
│   ├── conversation_2.json
│   └── ...
├── files/
│   ├── document1.pdf
│   ├── image1.png
│   └── ...
└── api_keys.json
```

## Privacy Settings

### Data Sharing

**Configure data sharing:**

1. Go to **Profile Settings** → **Privacy** tab
2. Configure privacy options:

```
┌─────────────────────────────────────────┐
│ Privacy Settings                        │
├─────────────────────────────────────────┤
│                                         │
│ ☑ Show profile to team members          │
│ ☑ Allow others to mention me            │
│ ☐ Show online status                    │
│ ☐ Share usage analytics                 │
│                                         │
└─────────────────────────────────────────┘
```

3. Click **"Save Settings"**

### Activity Visibility

**Control who sees your activity:**

- **Public**: Everyone can see
- **Team**: Only team members can see
- **Private**: Only you can see

## Troubleshooting

### Cannot Update Profile

**Problem**: Changes don't save

**Solutions:**
1. Check internet connection
2. Verify all required fields are filled
3. Check field validation errors
4. Try refreshing the page
5. Clear browser cache
6. Contact administrator

### Email Verification Required

**Problem**: Cannot change email without verification

**Solutions:**
1. Check inbox for verification email
2. Check spam/junk folder
3. Click **"Resend Verification Email"**
4. Wait a few minutes
5. Contact administrator

### 2FA Issues

**Problem**: Cannot enable 2FA or lost access

**Solutions:**
1. Use backup codes to log in
2. Contact administrator to disable 2FA
3. Ensure authenticator app time is synced
4. Try different authenticator app
5. Check QR code scans correctly

### Session Expired

**Problem**: Logged out unexpectedly

**Solutions:**
1. Log in again
2. Check if session timeout is configured
3. Enable "Remember me" option
4. Check if administrator revoked session
5. Review active sessions for suspicious activity

## Best Practices

### Profile Security

**✅ Do:**
- Use strong, unique password
- Enable 2FA
- Review active sessions regularly
- Revoke unused API keys
- Keep email address up to date
- Use professional profile picture

**❌ Don't:**
- Share your password
- Disable 2FA on shared devices
- Leave sessions active on public computers
- Share API keys
- Use same password as other services

### Privacy

**✅ Do:**
- Review privacy settings regularly
- Limit data sharing to necessary
- Export your data periodically
- Monitor account activity
- Report suspicious activity

**❌ Don't:**
- Share personal information publicly
- Accept unknown team invitations
- Ignore security notifications
- Leave account unattended

## Related Documentation

- [Login and Registration](../authentication/login-register.md) - Account creation
- [Password Management](../authentication/password-management.md) - Password security
- [SSO User Guide](../authentication/sso-user-guide.md) - Single Sign-On
- [Managing API Keys](../api-keys/managing-api-keys.md) - API key management
- [Security Best Practices](../../best-practices/security.md) - Security guidelines

## Getting Help

If you need assistance with profile settings:

1. **Documentation**: Review this guide
2. **Settings Help**: Click **?** icon in settings page
3. **Support**: Contact your organization's support team
4. **Administrator**: Reach out to your Clouisle administrator

---

**Last Updated**: 2026-02-11
