# SSO User Guide

This guide explains how to use Single Sign-On (SSO) to access Clouisle.

## Overview

Single Sign-On (SSO) allows you to log in to Clouisle using your existing organizational credentials from identity providers like:

- **OAuth2/OIDC**: Google, GitHub, Microsoft, Okta
- **SAML**: Enterprise identity providers
- **CAS**: Central Authentication Service

**Benefits:**
- No need to remember separate passwords
- Faster login process
- Enhanced security through centralized authentication
- Automatic account provisioning

## Checking SSO Availability

### From Login Page

1. Go to the Clouisle login page
2. Look for SSO login buttons below the standard login form
3. Available providers are displayed as buttons

**Note**: SSO providers are configured by your administrator. If you don't see SSO options, contact your administrator.

## Logging In with SSO

### First-Time SSO Login

**Steps:**

1. Click the SSO provider button (e.g., "Continue with Google")
2. You'll be redirected to the provider's login page
3. Enter your credentials on the provider's page
4. Grant permission for Clouisle to access your profile
5. You'll be redirected back to Clouisle
6. Your account is automatically created (if `sso_auto_create_users` is enabled)
7. You're logged in and redirected to the platform

**Example - Google SSO:**
```
1. Click "Continue with Google"
2. Google login page opens
3. Enter your Google email and password
4. Click "Allow" to grant permissions
5. Redirected to Clouisle
6. Account created with your Google email
7. Logged in successfully
```

### Subsequent SSO Logins

**Steps:**

1. Click the SSO provider button
2. If already logged in to the provider, you're automatically redirected
3. If not logged in, enter your provider credentials
4. You're logged in to Clouisle

**Note**: Subsequent logins are usually faster as you may already be authenticated with the provider.

## SSO Account Linking

### Linking SSO to an Existing Account

There is **no user-side "Connect" action** for SSO providers. Instead, linking happens automatically during login:

- When you log in with an SSO provider whose email matches an existing Clouisle account, the SSO connection is linked to that account (email matching `sso_match_by_email` is enabled by default)
- If no matching account exists, a new account is created automatically (when `sso_auto_create_users` is enabled)

If you have an existing account and want SSO login to apply to it, log in with the provider that uses the same email address.

### Disconnecting an SSO Provider

**Steps:**

1. Open **Profile Settings** → **Account** tab
2. Find the **"Connected Accounts"** section
3. Click **"Disconnect"** next to the provider
4. Confirm disconnection
5. Provider is unlinked

**Note**: If you disconnect all SSO providers, you can still log in with your username/password (local accounts remain usable unless password login is disabled by policy).

## SSO Providers

### Google OAuth

**What you need:**
- Google account (Gmail or Google Workspace)

**Permissions requested:**
- Email address
- Profile information (name, avatar)

### GitHub OAuth

**What you need:**
- GitHub account

**Permissions requested:**
- Email address
- Profile information (username, avatar)

### Microsoft OAuth

**What you need:**
- Microsoft account (Outlook, Office 365, Azure AD)

**Permissions requested:**
- Email address
- Profile information (name, avatar)

### SAML

**What you need:**
- SAML identity provider configured by your organization

**Note**: SAML configuration is managed by your administrator.

### CAS

**What you need:**
- CAS server configured by your organization

## Account Provisioning

### Automatic Account Creation

When you log in with SSO for the first time (and automatic creation is enabled):

**What happens:**
1. Clouisle receives your profile information from the provider
2. A new account is created automatically
3. Your email, name, and avatar are populated
4. You're logged in immediately

**Account details:**
- **Email**: From SSO provider
- **Username**: Generated from email or name
- **Avatar**: From SSO provider (can be changed later)

### Email Verification

**SSO accounts are automatically verified:**
- No email verification required
- Email is trusted from the SSO provider
- You can start using Clouisle immediately

## Security

### SSO Security Features

**Benefits:**
- **No password storage**: Clouisle doesn't store a password for SSO-only accounts
- **Provider security**: Leverages provider's security features (2FA, etc.)
- **Centralized control**: Administrator can disable access from the provider

### Session Management

**SSO sessions:**
- Session lifetime: same as normal sessions — the configured session timeout (default 30 days)
- Logout: Logs you out of Clouisle only (not the provider)

**To log out from both:**
1. Log out from Clouisle
2. Log out from the SSO provider (Google, GitHub, etc.)

### Two-Factor Authentication (2FA)

**SSO with 2FA:**
- If your SSO provider has 2FA enabled, it applies to your Clouisle login
- Clouisle's built-in TOTP 2FA can additionally be enabled on your account from Profile Settings

## Troubleshooting

### Cannot See SSO Options

**Problem**: No SSO buttons on login page

**Solutions:**
1. Check if SSO is enabled by your administrator
2. Clear browser cache and reload page
3. Try a different browser
4. Contact administrator to enable SSO

### SSO Login Fails

**Problem**: Error when trying to log in with SSO

**Solutions:**
1. Check if you're using the correct provider account
2. Verify your account is active with the provider
3. Clear browser cookies and try again
4. Check if your organization has disabled your access
5. Contact administrator

### "Email Already Exists" Error

**Problem**: Cannot create account because email is already registered

**Solutions:**
1. Log in with the SSO provider matching the existing account's email (the connection links automatically)
2. Or contact your administrator to merge accounts

### Redirected to Wrong Page

**Problem**: After SSO login, redirected to unexpected page

**Solutions:**
1. Clear browser cache and cookies
2. Try logging in again
3. Check if you have permission to access the intended page
4. Contact administrator

### SSO Provider Not Responding

**Problem**: Stuck on provider's login page or error

**Solutions:**
1. Check if the provider's service is operational
2. Try logging in to the provider directly (e.g., gmail.com)
3. Clear browser cache and cookies
4. Try a different browser
5. Contact your IT department

### Account Locked After SSO Login

**Problem**: Account is locked after successful SSO authentication

**Solutions:**
1. Your account may have been deactivated by an administrator
2. Contact administrator to reactivate your account
3. Check if your organization has access policies

## Best Practices

### Using SSO

**✅ Do:**
- Use SSO when available for easier login
- Enable 2FA on your SSO provider account
- Keep your SSO provider account secure
- Log out when using shared computers

**❌ Don't:**
- Share your SSO provider credentials
- Use SSO on untrusted devices
- Ignore security warnings from the provider
- Leave sessions active on public computers

### Account Security

**✅ Do:**
- Keep a local password if your organization allows password login as a fallback
- Review connected accounts regularly
- Monitor login notifications
- Report suspicious activity immediately

**❌ Don't:**
- Rely solely on one SSO provider
- Ignore security notifications
- Share your account with others

## Switching Between SSO and Password

### From SSO to Password

For an SSO-only account, open **Account** and choose **Set Password**; no current password is required. Once set, use **Change Password** for later updates. If the organization disables password login, contact an administrator instead.

### From Password to SSO

1. Log in with the SSO provider that uses the same email as your account
2. The SSO connection is linked automatically
3. You can now log in with either method

## Administrator Configuration

### For Administrators

If you're an administrator setting up SSO:

**See:**
- [SSO Configuration](../../admin-guide/settings/SSO.md) - Configure SSO providers
- [User Management](../../admin-guide/users/user-management.md) - Manage SSO users
- [System Settings](../../admin-guide/settings/system-settings.md) - Related security settings

## Related Documentation

- [Login and Registration](./login-register.md) - Standard login guide
- [Password Management](./password-management.md) - Password security
- [Profile Settings](../profile/profile-settings.md) - Account settings

## Getting Help

If you need assistance with SSO:

1. **Provider Help**: Check your SSO provider's documentation
2. **Documentation**: Review this guide
3. **IT Department**: Contact your organization's IT support
4. **Administrator**: Reach out to your Clouisle administrator

---

**Last Updated**: 2026-02-11
