# Password Management

This guide explains how to manage your password in Clouisle.

## Changing Your Password

### From Profile Settings

1. Open **Profile Settings** (profile menu) → **Account** tab
2. Find the **"Change Password"** section
3. Fill in the form:
   - **Current Password**: Your existing password
   - **New Password**: Your new password
   - **Confirm New Password**: Re-enter new password
4. Click **"Change Password"**
5. You'll see a success message

### Password Requirements

Your new password must meet the configured policy:

| Requirement | Default |
|-------------|---------|
| **Minimum Length** | 8 characters (configurable) |
| **Uppercase** | At least one uppercase letter (A-Z) |
| **Number** | At least one digit (0-9) |
| **Special Character** | Not required by default |
| **No Recent Reuse** | Cannot reuse the last 5 passwords (configurable) |

**Example of a valid password:**
```
MySecure#Pass2026!
```

**Examples of weak passwords:**
```
❌ 12345678       (no letters/uppercase)
❌ abcdefgh       (no numbers)
❌ Pass123        (too short)
```

> **Note:** There is no dictionary / weak-password check.

### Password Strength Indicator

As you type, the UI shows a strength indicator (weak / fair / good / strong).

**Tips for strong passwords:**
- Use a mix of character types
- Make it at least 12 characters long
- Avoid personal information (name, birthday)
- Consider using a password manager

## Resetting Forgotten Password

If you forgot your password:

### Step 1: Request Password Reset

1. Go to the login page
2. Click **"Forgot Password?"** link
3. Enter your **email address**
4. Click **"Send Reset Link"**
5. Check your email inbox

### Step 2: Check Your Email

You'll receive an email with:
- Subject: "Password Reset Request - Clouisle"
- Reset link with a verification code (valid for **10 minutes**)
- Instructions

### Step 3: Reset Password

1. Click the reset link / enter the code from the email
2. You'll be redirected to the reset password page
3. Enter your **new password**
4. Confirm your **new password**
5. Click **"Reset Password"**
6. You'll see a success message
7. Log in with your new password

### Troubleshooting Password Reset

**Email not received:**
1. Check spam/junk folder
2. Wait a few minutes (email may be delayed; resend is rate-limited to 60 seconds)
3. Verify email address is correct
4. Click **"Resend Reset Link"**
5. Contact administrator if still not received

**Reset link expired:**
1. Links/codes expire after 10 minutes
2. Request a new reset link
3. Complete the reset quickly

**Reset link invalid:**
1. The link may have been used already
2. Request a new reset link
3. Don't click the link multiple times

## Password Security

### Best Practices

**✅ Do:**
- Use a unique password for Clouisle
- Use a password manager
- Enable two-factor authentication (if available)
- Change your password if compromised
- Keep your password confidential

**❌ Don't:**
- Share your password with anyone
- Use the same password as other services
- Write your password down
- Use personal information in your password

### Password Manager Recommendations

Consider using a password manager:

| Password Manager | Platform | Features |
|-----------------|----------|----------|
| **1Password** | All platforms | Family sharing, secure notes |
| **Bitwarden** | All platforms | Open source, free tier |
| **KeePass** | Windows, Linux | Offline, open source |

### Two-Factor Authentication (2FA)

If your organization enables 2FA:

**Setting up 2FA:**
1. Open **Profile Settings** → **Account** tab
2. Click **"Enable Two-Factor Authentication"**
3. Scan the QR code with an authenticator app (Google Authenticator, Authy, etc.)
4. Enter the verification code
5. Save the backup codes securely
6. Click **"Enable"**

**Logging in with 2FA:**
1. Enter username and password
2. Enter the 6-digit code from your authenticator app
3. Click **"Verify"**

**Backup codes:**
- Save backup codes in a safe place
- Use a backup code if you lose access to your authenticator
- Each code can only be used once

## Password Expiration

Some organizations require regular password changes:

### Expiration Policy

If enabled by your administrator:
- Password expires after a configured number of days (e.g., 90)
- You'll receive reminders before expiration (default: warning starting 7 days before)
- After expiration, you must change your password to log in

### Changing Expired Password

1. Try to log in
2. You'll see "Password expired" / "Change password required" message
3. Enter your new password (the current password is required to authenticate first)
4. Log in with the new password

## Account Security

### Login Security Features

**Account Lockout:**
- After 5 failed login attempts (configurable)
- Account locked for 15 minutes (configurable)
- Prevents brute-force attacks

**Login Anomaly Detection:**
- System tracks your usual login locations
- Notifies you of logins from new locations (security notification)

**Session Management:**
- Sessions expire after the configured session timeout (default 30 days)
- Single session mode (if enabled): only one active session per user
- Logging out only invalidates the current session/token

### Security Notifications

You'll receive notifications for:
- Password changed successfully
- Failed login attempts / account locked
- Login from a new location/device
- Password expiration reminders

**Check notifications regularly** to detect unauthorized access.

### If Your Account is Compromised

If you suspect unauthorized access:

1. **Change your password immediately**
2. **Enable 2FA** (if not already enabled)
3. **Review login notifications** for suspicious activity
4. **Contact your administrator** to report the incident

## Admin Password Reset

Administrators can reset your password from the admin user management:

1. Administrator resets your password
2. You receive an email with a temporary password
3. Log in with the temporary password
4. Change your password

## Password Policy

Your organization's password policy may include:

| Policy | Default |
|--------|---------|
| **Minimum Length** | 8 characters |
| **Uppercase** | Required |
| **Number** | Required |
| **Special character** | Not required |
| **Expiration** | Disabled unless enabled by admin |
| **History** | Cannot reuse last 5 passwords |
| **Lockout** | 5 failed attempts = 15 minute lockout |

**Check with your administrator** for your organization's specific policy.

## Troubleshooting

### Cannot Change Password

**Problem**: "Current password incorrect" error

**Solutions:**
1. Verify you're entering the correct current password
2. Check Caps Lock is off
3. Use password reset if you forgot your current password
4. Contact administrator if the account is locked

### New Password Rejected

**Problem**: "Password does not meet requirements" error

**Solutions:**
1. Check the password meets the configured requirements (minimum length, uppercase, number)
2. Make sure the password isn't one of the recent passwords
3. Try a different password
4. Contact the administrator for policy details

### Password Reset Email Not Received

**Problem**: Didn't receive reset email

**Solutions:**
1. Check spam/junk folder
2. Wait a few minutes
3. Verify the email address is correct
4. Click "Resend Reset Link" (rate-limited to 60 seconds)
5. Contact administrator

### Reset Link Doesn't Work

**Problem**: Reset link shows error

**Solutions:**
1. Check if the link expired (10 minute validity)
2. Request a new reset link
3. Copy the full URL (don't let it wrap)
4. Try a different browser
5. Contact administrator

## Related Documentation

- [Login and Registration](./login-register.md) - Login guide
- [SSO User Guide](./sso-user-guide.md) - Single Sign-On
- [Profile Settings](../profile/profile-settings.md) - Profile management

## Getting Help

If you need assistance with password issues:

1. **Self-Service**: Use the password reset feature
2. **Documentation**: Review this guide
3. **Support**: Contact your organization's support team
4. **Administrator**: Reach out to your Clouisle administrator

---

**Last Updated**: 2026-02-11
