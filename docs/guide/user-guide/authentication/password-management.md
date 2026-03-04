# Password Management

This guide explains how to manage your password in Clouisle.

## Changing Your Password

### From Profile Settings

1. Click your profile icon in the top-right corner
2. Select **"Profile Settings"** or **"Settings"**
3. Navigate to **"Security"** tab
4. Find the **"Change Password"** section
5. Fill in the form:
   - **Current Password**: Your existing password
   - **New Password**: Your new password
   - **Confirm New Password**: Re-enter new password
6. Click **"Change Password"**
7. You'll see a success message

### Password Requirements

Your new password must meet these requirements:

| Requirement | Description |
|-------------|-------------|
| **Minimum Length** | 8 characters (configurable by admin) |
| **Uppercase** | At least one uppercase letter (A-Z) |
| **Lowercase** | At least one lowercase letter (a-z) |
| **Number** | At least one digit (0-9) |
| **Special Character** | At least one symbol (!@#$%^&*) |
| **No Common Passwords** | Not in dictionary of common passwords |
| **No Recent Reuse** | Cannot reuse last 3 passwords (if enabled) |

**Example of strong password:**
```
MySecure#Pass2026!
```

**Examples of weak passwords:**
```
❌ password123    (too common)
❌ 12345678       (no letters)
❌ abcdefgh       (no numbers/symbols)
❌ Pass123        (too short)
```

### Password Strength Indicator

As you type, a strength indicator shows:

- 🔴 **Weak**: Does not meet requirements
- 🟡 **Fair**: Meets minimum requirements
- 🟢 **Good**: Strong password
- 🟢 **Excellent**: Very strong password

**Tips for strong passwords:**
- Use a mix of character types
- Make it at least 12 characters long
- Avoid personal information (name, birthday)
- Use a passphrase: "Coffee@Morning#2026"
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
- Reset link (valid for 1 hour)
- Instructions

**Email example:**
```
Hello,

You requested to reset your password for Clouisle.

Click the link below to reset your password:
[Reset Password]

This link will expire in 1 hour.

If you didn't request this, please ignore this email.
```

### Step 3: Reset Password

1. Click the reset link in the email
2. You'll be redirected to the reset password page
3. Enter your **new password**
4. Confirm your **new password**
5. Click **"Reset Password"**
6. You'll see a success message
7. Log in with your new password

### Troubleshooting Password Reset

**Email not received:**
1. Check spam/junk folder
2. Wait a few minutes (email may be delayed)
3. Verify email address is correct
4. Click **"Resend Reset Link"**
5. Contact administrator if still not received

**Reset link expired:**
1. Links expire after 1 hour
2. Request a new reset link
3. Complete reset process quickly

**Reset link invalid:**
1. Link may have been used already
2. Request a new reset link
3. Don't click the link multiple times

## Password Security

### Best Practices

**✅ Do:**
- Use a unique password for Clouisle
- Use a password manager
- Enable two-factor authentication (if available)
- Change password if compromised
- Use a strong, complex password
- Keep password confidential

**❌ Don't:**
- Share your password with anyone
- Use the same password as other services
- Write password on paper/sticky notes
- Use personal information in password
- Use simple or common passwords
- Save password in browser on shared computers

### Password Manager Recommendations

Consider using a password manager:

| Password Manager | Platform | Features |
|-----------------|----------|----------|
| **1Password** | All platforms | Family sharing, secure notes |
| **Bitwarden** | All platforms | Open source, free tier |
| **LastPass** | All platforms | Auto-fill, password generator |
| **Dashlane** | All platforms | Dark web monitoring |
| **KeePass** | Windows, Linux | Offline, open source |

### Two-Factor Authentication (2FA)

If your organization enables 2FA:

**Setting up 2FA:**
1. Go to **Profile Settings** → **Security**
2. Click **"Enable Two-Factor Authentication"**
3. Scan QR code with authenticator app:
   - Google Authenticator
   - Authy
   - Microsoft Authenticator
4. Enter verification code
5. Save backup codes securely
6. Click **"Enable"**

**Logging in with 2FA:**
1. Enter username and password
2. Enter 6-digit code from authenticator app
3. Click **"Verify"**

**Backup codes:**
- Save backup codes in a safe place
- Use if you lose access to authenticator
- Each code can only be used once

## Password Expiration

Some organizations require regular password changes:

### Expiration Policy

If enabled by your administrator:
- Password expires after X days (e.g., 90 days)
- You'll receive reminders before expiration:
  - 7 days before
  - 3 days before
  - 1 day before
- After expiration, you must change password to log in

### Changing Expired Password

1. Try to log in
2. You'll see "Password expired" message
3. Click **"Change Password"**
4. Enter current password
5. Enter new password
6. Confirm new password
7. Click **"Update Password"**
8. Log in with new password

## Account Security

### Login Security Features

**Account Lockout:**
- After 5 failed login attempts (configurable)
- Account locked for 15 minutes
- Prevents brute-force attacks

**Login Anomaly Detection:**
- System tracks your usual login locations
- Notifies you of logins from new locations
- Check notifications if you see alerts

**Session Management:**
- Sessions expire after inactivity (default: 30 minutes)
- Single session mode (if enabled): only one active session
- Log out from all devices option

### Security Notifications

You'll receive notifications for:
- Password changed successfully
- Failed login attempts
- Login from new location/device
- Account locked due to failed attempts
- Password expiration reminders

**Check notifications regularly** to detect unauthorized access.

### If Your Account is Compromised

If you suspect unauthorized access:

1. **Change password immediately**
2. **Log out from all devices**:
   - Go to **Profile Settings** → **Security**
   - Click **"Log Out All Sessions"**
3. **Review login history**:
   - Check recent login locations
   - Look for suspicious activity
4. **Enable 2FA** (if not already enabled)
5. **Contact administrator** to report the incident
6. **Review account activity** for unauthorized changes

## Admin Password Reset

Administrators can reset your password:

### When Admin Resets Your Password

1. Administrator resets your password
2. You receive an email with temporary password
3. Log in with temporary password
4. You'll be prompted to change password
5. Enter new password
6. Confirm new password
7. Click **"Update Password"**

**Note**: Temporary passwords expire after first use or 24 hours.

## Password Policy

Your organization's password policy may include:

| Policy | Description |
|--------|-------------|
| **Minimum Length** | 8-16 characters |
| **Complexity** | Uppercase, lowercase, numbers, symbols |
| **Expiration** | 30-90 days |
| **History** | Cannot reuse last 3-5 passwords |
| **Lockout** | 5 failed attempts = 15 minute lockout |
| **2FA** | Required or optional |

**Check with your administrator** for your organization's specific policy.

## Troubleshooting

### Cannot Change Password

**Problem**: "Current password incorrect" error

**Solutions:**
1. Verify you're entering correct current password
2. Check Caps Lock is off
3. Try password reset if you forgot current password
4. Contact administrator if account is locked

### New Password Rejected

**Problem**: "Password does not meet requirements" error

**Solutions:**
1. Check password meets all requirements:
   - Minimum length
   - Uppercase, lowercase, numbers, symbols
   - Not a common password
2. Try a different password
3. Use password generator
4. Contact administrator for policy details

### Password Reset Email Not Received

**Problem**: Didn't receive reset email

**Solutions:**
1. Check spam/junk folder
2. Wait 5-10 minutes
3. Verify email address is correct
4. Click "Resend Reset Link"
5. Contact administrator

### Reset Link Doesn't Work

**Problem**: Reset link shows error

**Solutions:**
1. Check if link expired (1 hour validity)
2. Request new reset link
3. Copy full URL (don't let it wrap)
4. Try different browser
5. Contact administrator

## Related Documentation

- [Login and Registration](./login-register.md) - Login guide
- [SSO User Guide](./sso-user-guide.md) - Single Sign-On
- [Profile Settings](../profile/profile-settings.md) - Profile management
- [Security Checklist](../../operations/security-checklist.md) - Security best practices

## Getting Help

If you need assistance with password issues:

1. **Self-Service**: Use password reset feature
2. **Documentation**: Review this guide
3. **Support**: Contact your organization's support team
4. **Administrator**: Reach out to your Clouisle administrator

---

**Last Updated**: 2026-02-11
