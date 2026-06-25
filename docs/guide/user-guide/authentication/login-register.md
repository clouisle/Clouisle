# Login and Registration

This guide explains how to access Clouisle through login and registration.

## Registration Methods

Clouisle supports two registration methods:

### 1. Self-Registration

If enabled by administrators, you can create an account directly.

**Steps:**

1. Navigate to the login page: `https://your-domain.com`
2. Click **"Sign Up"** or **"Register"**
3. Fill in the registration form:
   - **Username**: Unique identifier (3-20 characters)
   - **Email**: Valid email address
   - **Password**: Strong password (8+ characters, mix of letters, numbers, symbols)
   - **Confirm Password**: Re-enter password
4. If human verification is shown, click **"Click to verify you are human"**
5. Click **"Register"**
6. Check your email for verification link (if email verification is enabled)
7. Click the verification link to activate your account
8. Log in with your credentials

**Note**: If admin approval is required, you'll see a message that your account is pending approval. Wait for an administrator to activate your account.

### 2. Invitation-Based Registration

Administrators can invite users via email.

**Steps:**

1. Receive invitation email from administrator
2. Click the invitation link in the email
3. Fill in your password and other required information
4. Click **"Complete Registration"**
5. Log in with your credentials

## Login Methods

### Password-Based Login

**Steps:**

1. Navigate to the login page
2. Enter your **username** or **email**
3. Enter your **password**
4. If human verification is shown, click **"Click to verify you are human"**
5. (Optional) Check **"Remember me"** to stay logged in
6. Click **"Log In"**

**Security Features:**
- Account lockout after multiple failed attempts
- CAPTCHA verification (if enabled)
- Session timeout for security

### SSO (Single Sign-On) Login

If your organization has configured SSO, you can log in with your corporate credentials.

**Steps:**

1. Navigate to the login page
2. Click the SSO provider button (e.g., "Sign in with Google", "Sign in with GitHub")
3. Authenticate with your SSO provider
4. You'll be redirected back to Clouisle and logged in automatically

**First-time SSO login:**
- If your email matches an existing account, the SSO connection will be linked
- If no account exists, a new account will be created automatically (if enabled)

**Supported SSO Providers:**
- OAuth2/OIDC (Google, GitHub, GitLab, etc.)
- SAML 2.0 (Azure AD, Okta, OneLogin)
- CAS (University systems)

For SSO configuration, see [SSO User Guide](./sso-user-guide.md).

## First-Time Login

After your first successful login:

1. **Welcome Screen**: You'll see a welcome message
2. **Profile Setup**: Complete your profile information (optional)
3. **Team Assignment**:
   - If invited to a team, you'll see it in your teams list
   - If no team assigned, you may need to create one or wait for invitation
4. **Dashboard Access**:
   - Regular users see the platform interface
   - Administrators see the admin dashboard

## Session Management

### Session Duration

- **Default**: 30 minutes of inactivity
- **Remember Me**: Extended session (configurable by admin)
- **Single Session Mode**: Only one active session per user (if enabled)

### Staying Logged In

**"Remember Me" option:**
- Keeps you logged in for extended period
- Useful for personal devices
- **Don't use on shared computers**

### Logging Out

**Manual Logout:**
1. Click your profile icon in the top-right corner
2. Select **"Logout"**
3. You'll be redirected to the login page

**Automatic Logout:**
- After session timeout (inactivity)
- When administrator deactivates your account
- When you log in from another device (if single session mode enabled)

## Account Security

### Password Requirements

Clouisle enforces strong password policies:

- **Minimum length**: 8 characters (configurable)
- **Complexity**: Mix of uppercase, lowercase, numbers, and symbols
- **No common passwords**: Dictionary words and common patterns are rejected
- **No reuse**: Can't reuse recent passwords (if enabled)

### Login Security Features

**Account Lockout:**
- After 5 failed login attempts (configurable)
- Account locked for 15 minutes
- Contact administrator if locked out repeatedly

**Human Verification:**
- Required on login and self-registration when enabled by administrators
- Complete it by clicking the verification control before submitting
- If it fails, expires, or cannot load, use the refresh button and click again
- Works with existing account lockout and login anomaly controls as the risk-control fallback

**Login Anomaly Detection:**
- System tracks your usual login locations and devices
- Notifies you of logins from new locations
- Check notifications if you see anomaly alerts

### Two-Factor Authentication (2FA)

If enabled by your organization:

1. Enter username and password
2. Enter verification code from:
   - Authenticator app (Google Authenticator, Authy)
   - SMS (if configured)
   - Email (if configured)
3. Click **"Verify"**

**Setting up 2FA:**
1. Go to **Profile Settings** → **Security**
2. Click **"Enable Two-Factor Authentication"**
3. Scan QR code with authenticator app
4. Enter verification code to confirm
5. Save backup codes in a safe place

## Troubleshooting

### Cannot Access Login Page

**Problem**: Login page doesn't load

**Solutions:**
1. Check your internet connection
2. Verify the URL is correct
3. Try a different browser
4. Clear browser cache and cookies
5. Contact your IT administrator

### Forgot Password

**Problem**: Can't remember your password

**Solution:**
1. Click **"Forgot Password?"** on login page
2. Enter your email address
3. Check your email for reset link
4. Click the link and enter new password
5. Log in with new password

See [Password Management](./password-management.md) for details.

### Account Locked

**Problem**: "Account locked" message after failed login attempts

**Solutions:**
1. Wait 15 minutes for automatic unlock
2. Contact administrator for immediate unlock
3. Use password reset if you forgot password

### Email Verification Not Received

**Problem**: Didn't receive verification email

**Solutions:**
1. Check spam/junk folder
2. Wait a few minutes (email may be delayed)
3. Click **"Resend Verification Email"** on login page
4. Verify email address is correct
5. Contact administrator if still not received

### SSO Login Fails

**Problem**: Error when logging in with SSO

**Solutions:**
1. Verify you're using the correct SSO provider
2. Check if your SSO account is active
3. Clear browser cookies and try again
4. Contact your SSO administrator
5. Try password login if available

See [SSO User Guide](./sso-user-guide.md) for SSO-specific troubleshooting.

### "Account Pending Approval" Message

**Problem**: Can't log in, account pending approval

**Solution:**
- Your account requires administrator approval
- Wait for administrator to activate your account
- You'll receive an email when approved
- Contact administrator if waiting too long

### Session Expired

**Problem**: "Session expired" message during use

**Solutions:**
1. Log in again
2. Enable "Remember Me" for longer sessions
3. Contact administrator to adjust session timeout
4. Check if you're logged in on another device (single session mode)

## Best Practices

### Security Recommendations

**✅ Do:**
- Use a strong, unique password
- Enable two-factor authentication
- Log out when using shared computers
- Keep your email address up to date
- Review login notifications regularly
- Use SSO if available (more secure)

**❌ Don't:**
- Share your password with others
- Use the same password as other services
- Stay logged in on public computers
- Ignore login anomaly notifications
- Use simple or common passwords

### Account Management

**Regular Tasks:**
- Update password every 90 days (if required)
- Review active sessions periodically
- Check login history for suspicious activity
- Keep profile information current
- Update notification preferences

## Related Documentation

- [Password Management](./password-management.md) - Change and reset passwords
- [SSO User Guide](./sso-user-guide.md) - Single Sign-On details
- [Profile Settings](../profile/profile-settings.md) - Manage your profile
- [Security Best Practices](../../operations/security-checklist.md) - Security guidelines

## Getting Help

If you continue to experience login issues:

1. **Check System Status**: Verify Clouisle is operational
2. **Contact Support**: Reach out to your organization's support team
3. **Administrator**: Contact your Clouisle administrator
4. **Documentation**: Review [Troubleshooting Guide](../../deployment/DEPLOYMENT.md#troubleshooting)

---

**Last Updated**: 2026-02-11
