# Profile Settings

This guide explains how to manage your profile settings in Clouisle.

## Overview

Your profile contains:

- **Personal Information**: Username, email, avatar
- **Security Settings**: Password, 2FA, connected accounts
- **Preferences**: Language, theme
- **Account Management**: Delete account

> **Note:** Profile settings are shown in a **dialog** opened from the user menu — there is no dedicated `/settings` or `/profile` route. Timezones, active-session management, data export, and privacy toggles are **not implemented**.

## Accessing Profile Settings

**Steps:**

1. Click your **profile icon** or **avatar** in the top-right corner
2. Select **"Profile Settings"** or **"Settings"** from the dropdown
3. The settings dialog opens with two tabs: **Profile** and **Account**

## Profile Tab

### Personal Information

**Profile form fields:**

| Field | Description |
|-------|-------------|
| **Avatar** | Profile picture URL (upload via the avatar picker) |
| **Username** | Unique username (max 50 chars) |
| **Email** | Email address (changing it may require email verification) |

**Editing:**

1. Open **Profile Settings** → **Profile** tab
2. Update fields
3. Click **"Save"**

**Email verification:**
- If email verification is enabled, changing your email requires a verification code
- Click **"Send Email Verification"** to receive a 6-digit code at the new address
- Enter the code and save

## Account Tab

### Password Management

**Changing password:**

1. Open **Profile Settings** → **Account** tab
2. Find the **"Change Password"** section
3. Enter **current password**
4. Enter **new password**
5. Confirm **new password**
6. Click **"Change Password"**

See [Password Management](../authentication/password-management.md) for details.

### Two-Factor Authentication (2FA)

**Enabling 2FA (TOTP):**

1. Open **Profile Settings** → **Account** tab
2. Find the **"Two-Factor Authentication"** section
3. Click **"Enable"**
4. Scan the QR code with an authenticator app (Google Authenticator, Authy, etc.)
5. Enter the verification code from the app
6. Save the **backup codes** securely
7. Click **"Enable"**

**Backup codes:**
- Save these codes in a safe place
- Each code can only be used once
- Regenerate them if needed

**Disabling 2FA:**

1. Click **"Disable"** in the 2FA section
2. Confirm with your password / TOTP code

### Connected Accounts (SSO)

**Viewing connected SSO providers:**

1. Open **Profile Settings** → **Account** tab
2. Find the **"Connected Accounts"** section
3. Each provider shows its name and last login time

**Disconnecting:**

1. Click **"Disconnect"** next to a provider
2. Confirm disconnection
3. The provider is unlinked

> **Note:** There is no user-side "Connect" action — SSO connections are linked automatically during login when the provider email matches your account (see [SSO User Guide](../authentication/sso-user-guide.md)).

## Preferences

### Language

Switch the interface language (e.g., English / 中文) via the **language switcher** in the navigation bar. The change takes effect immediately.

### Theme

Switch the theme via the **theme toggle** in the navigation bar:

- **Light**
- **Dark**
- **System** (follow the system preference)

## API Keys

API keys are managed on a dedicated page, not in profile settings:

1. Open the user menu (profile icon)
2. Select **"API Keys"**
3. Or navigate directly to `/app/api-keys`

See [Managing API Keys](../api-keys/managing-api-keys.md) for details.

## Account Management

### Deleting Account

**Permanently delete (requires your password):**

1. Open **Profile Settings** → **Account** tab
2. Find the **"Delete Account"** section
3. Click **"Delete Account"**
4. Read the warning carefully
5. Enter your password to confirm
6. Click **"Permanently Delete"**

**Warning**: This action cannot be undone.

**What gets deleted:**
- Your profile and personal information
- Your conversations and messages
- Your API keys
- Your team memberships (if not owner)
- Your uploaded files

> **Note:** There is no temporary deactivation or reactivation flow — deleting the account is permanent. If you are a team owner, transfer ownership before deleting your account.

## Troubleshooting

### Cannot Update Profile

**Problem**: Changes don't save

**Solutions:**
1. Check your internet connection
2. Verify all required fields are filled
3. Check field validation errors
4. Try refreshing the page

### Email Verification Required

**Problem**: Cannot change email without verification

**Solutions:**
1. Click **"Send Email Verification"** to receive a code
2. Check your inbox (and spam/junk folder)
3. Enter the 6-digit code
4. Wait a minute and resend if needed

### 2FA Issues

**Problem**: Cannot enable 2FA or lost access

**Solutions:**
1. Use backup codes to log in
2. Contact the administrator to disable 2FA
3. Ensure the authenticator app's time is synced
4. Try a different authenticator app

## Best Practices

### Profile Security

**✅ Do:**
- Use a strong, unique password
- Enable 2FA
- Keep your email address up to date
- Review connected SSO accounts

**❌ Don't:**
- Share your password
- Disable 2FA on shared devices

## Related Documentation

- [Login and Registration](../authentication/login-register.md) - Account creation
- [Password Management](../authentication/password-management.md) - Password security
- [SSO User Guide](../authentication/sso-user-guide.md) - Single Sign-On
- [Managing API Keys](../api-keys/managing-api-keys.md) - API key management
- [Notifications](./notifications.md) - Notification center

## Getting Help

If you need assistance with profile settings:

1. **Documentation**: Review this guide
2. **Support**: Contact your organization's support team
3. **Administrator**: Reach out to your Clouisle administrator

---

**Last Updated**: 2026-02-11
