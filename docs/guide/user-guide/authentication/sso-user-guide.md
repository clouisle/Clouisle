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
3. Available providers are displayed as buttons:

```
┌─────────────────────────────────────┐
│         Login to Clouisle           │
├─────────────────────────────────────┤
│                                     │
│  Email: [________________]          │
│  Password: [________________]       │
│                                     │
│  [Login]                            │
│                                     │
│  ─────────── OR ───────────         │
│                                     │
│  [🔵 Continue with Google]          │
│  [⚫ Continue with GitHub]          │
│  [🔷 Continue with Microsoft]       │
│                                     │
└─────────────────────────────────────┘
```

**Note**: SSO providers are configured by your administrator. If you don't see SSO options, contact your administrator.

## Logging In with SSO

### First-Time SSO Login

**Steps:**

1. Click the SSO provider button (e.g., "Continue with Google")
2. You'll be redirected to the provider's login page
3. Enter your credentials on the provider's page
4. Grant permission for Clouisle to access your profile
5. You'll be redirected back to Clouisle
6. Your account is automatically created
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

### Linking SSO to Existing Account

If you already have a Clouisle account with password authentication:

**Steps:**

1. Log in with your username and password
2. Go to **Profile Settings** → **Security**
3. Find **"Connected Accounts"** section
4. Click **"Connect"** next to the SSO provider
5. You'll be redirected to the provider
6. Authorize the connection
7. You're redirected back to Clouisle
8. SSO provider is now linked to your account

**Example:**
```
Connected Accounts:
┌─────────────────────────────────────┐
│ Google:     [Connect]               │
│ GitHub:     [Connect]               │
│ Microsoft:  [Connect]               │
└─────────────────────────────────────┘
```

### Unlinking SSO Provider

**Steps:**

1. Go to **Profile Settings** → **Security**
2. Find **"Connected Accounts"** section
3. Click **"Disconnect"** next to the provider
4. Confirm disconnection
5. Provider is unlinked

**Warning**: If you unlink all SSO providers and don't have a password set, you won't be able to log in. Set a password first.

## SSO Providers

### Google OAuth

**What you need:**
- Google account (Gmail or Google Workspace)

**Permissions requested:**
- Email address
- Profile information (name, avatar)

**Login flow:**
1. Click "Continue with Google"
2. Select your Google account
3. Click "Allow"
4. Logged in to Clouisle

### GitHub OAuth

**What you need:**
- GitHub account

**Permissions requested:**
- Email address
- Profile information (username, avatar)

**Login flow:**
1. Click "Continue with GitHub"
2. Enter GitHub credentials (if not logged in)
3. Click "Authorize"
4. Logged in to Clouisle

### Microsoft OAuth

**What you need:**
- Microsoft account (Outlook, Office 365, Azure AD)

**Permissions requested:**
- Email address
- Profile information (name, avatar)

**Login flow:**
1. Click "Continue with Microsoft"
2. Enter Microsoft credentials
3. Click "Accept"
4. Logged in to Clouisle

### SAML

**What you need:**
- SAML identity provider configured by your organization

**Login flow:**
1. Click "Continue with SAML" or your organization's SSO button
2. Redirected to your organization's login page
3. Enter your organizational credentials
4. Logged in to Clouisle

**Note**: SAML configuration is managed by your administrator.

### CAS

**What you need:**
- CAS server configured by your organization

**Login flow:**
1. Click "Continue with CAS"
2. Redirected to CAS login page
3. Enter your credentials
4. Logged in to Clouisle

## Account Provisioning

### Automatic Account Creation

When you log in with SSO for the first time:

**What happens:**
1. Clouisle receives your profile information from the provider
2. A new account is created automatically
3. Your email, name, and avatar are populated
4. You're assigned to the default team (if configured)
5. You're logged in immediately

**Account details:**
- **Email**: From SSO provider (cannot be changed)
- **Username**: Generated from email or name
- **Name**: From SSO provider (can be changed later)
- **Avatar**: From SSO provider (can be changed later)

### Email Verification

**SSO accounts are automatically verified:**
- No email verification required
- Email is trusted from the SSO provider
- You can start using Clouisle immediately

## Security

### SSO Security Features

**Benefits:**
- **No password storage**: Clouisle doesn't store your password
- **Provider security**: Leverages provider's security features (2FA, etc.)
- **Centralized control**: Administrator can disable access from provider
- **Session management**: Single logout from provider logs you out everywhere

### Session Management

**SSO sessions:**
- Session lifetime: 30 minutes of inactivity (default)
- Refresh: Activity extends the session
- Logout: Logs you out of Clouisle only (not the provider)

**To log out from both:**
1. Log out from Clouisle
2. Log out from the SSO provider (Google, GitHub, etc.)

### Two-Factor Authentication (2FA)

**SSO with 2FA:**
- If your SSO provider has 2FA enabled, it applies to Clouisle login
- Clouisle's built-in 2FA is not used for SSO accounts
- Configure 2FA in your SSO provider settings

**Example - Google 2FA:**
1. Enable 2FA in your Google account
2. When logging in to Clouisle via Google:
   - Enter Google password
   - Enter 2FA code from Google Authenticator
   - Logged in to Clouisle

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
1. Log in with your existing username and password
2. Link the SSO provider in Profile Settings
3. Or contact administrator to merge accounts

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
1. Your account may have been deactivated by administrator
2. Contact administrator to reactivate your account
3. Check if your organization has access policies

## Best Practices

### Using SSO

**✅ Do:**
- Use SSO when available for easier login
- Enable 2FA on your SSO provider account
- Keep your SSO provider account secure
- Link multiple SSO providers for backup access
- Log out when using shared computers

**❌ Don't:**
- Share your SSO provider credentials
- Use SSO on untrusted devices
- Ignore security warnings from provider
- Leave sessions active on public computers

### Account Security

**✅ Do:**
- Set a backup password even if using SSO
- Link multiple authentication methods
- Review connected accounts regularly
- Monitor login notifications
- Report suspicious activity immediately

**❌ Don't:**
- Rely solely on one SSO provider
- Ignore security notifications
- Share your account with others
- Use SSO on public/shared computers without logging out

## Switching Between SSO and Password

### From SSO to Password

If you want to use password authentication instead of SSO:

**Steps:**
1. Log in with SSO
2. Go to **Profile Settings** → **Security**
3. Click **"Set Password"**
4. Enter a new password
5. Confirm password
6. Click **"Save"**
7. You can now log in with either SSO or password

### From Password to SSO

If you want to use SSO instead of password:

**Steps:**
1. Log in with password
2. Go to **Profile Settings** → **Security**
3. Link your SSO provider (see "Linking SSO to Existing Account")
4. You can now log in with either method

**Optional**: Remove password to use SSO only (not recommended)

## Administrator Configuration

### For Administrators

If you're an administrator setting up SSO:

**See:**
- [SSO Configuration](../../admin-guide/settings/sso-configuration.md) - Configure SSO providers
- [User Management](../../admin-guide/users/user-management.md) - Manage SSO users
- [Security Settings](../../admin-guide/settings/security-settings.md) - SSO security options

## Related Documentation

- [Login and Registration](./login-register.md) - Standard login guide
- [Password Management](./password-management.md) - Password security
- [Profile Settings](../profile/profile-settings.md) - Account settings
- [SSO Configuration](../../admin-guide/settings/sso-configuration.md) - Admin guide

## Getting Help

If you need assistance with SSO:

1. **Provider Help**: Check your SSO provider's documentation
2. **Documentation**: Review this guide
3. **IT Department**: Contact your organization's IT support
4. **Administrator**: Reach out to your Clouisle administrator
5. **Support**: Contact Clouisle support team

---

**Last Updated**: 2026-02-11
