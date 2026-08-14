# Login and Registration

This guide explains how to access Clouisle through login and registration.

## Registration Methods

Clouisle supports self-registration when it is enabled by administrators.

### Self-Registration

**Steps:**

1. Navigate to the login page: `https://your-domain.com`
2. Click **"Sign Up"** or **"Register"**
3. Fill in the registration form:
   - **Username**: Unique identifier (max 50 characters)
   - **Email**: Valid email address
   - **Password**: Strong password (8+ characters, see Password Requirements below)
   - **Confirm Password**: Re-enter password
4. If human verification is shown, click **"Click to verify you are human"**
5. Click **"Register"**
6. Check your email for the verification link/code (if email verification is enabled)
7. Verify your email to activate your account
8. Log in with your credentials

**Note**: The first registered user is automatically promoted to Super Admin. If admin approval is required (`require_approval`), you'll see a message that your account is pending approval, and administrators receive a global notification. New users may be automatically added to the configured default team.

> **Note:** There is no invitation-based registration flow. Users are created via self-registration, by administrators (admin user management), or automatically through SSO (when `sso_auto_create_users` is enabled).

## Login Methods

### Password-Based Login

**Steps:**

1. Navigate to the login page
2. Enter your **username** or **email**
3. Enter your **password**
4. If human verification is shown, click **"Click to verify you are human"**
5. Click **"Log In"**

**Security Features:**
- Account lockout after multiple failed attempts (default 5 attempts, 15 minutes)
- CAPTCHA verification (if enabled)
- Session timeout for security
- 2FA via TOTP (if enabled)

### SSO (Single Sign-On) Login

If your organization has configured SSO, you can log in with your corporate credentials.

**Steps:**

1. Navigate to the login page
2. Click the SSO provider button (e.g., "Continue with Google", "Continue with GitHub")
3. Authenticate with your SSO provider
4. You'll be redirected back to Clouisle and logged in automatically

**First-time SSO login:**
- If your email matches an existing account, the SSO connection is linked to it (email matching is enabled by default)
- If no account exists, a new account is created automatically (if `sso_auto_create_users` is enabled)

**Supported SSO Providers:**
- OAuth2/OIDC (Google, GitHub, GitLab, etc.)
- SAML 2.0 (Azure AD, Okta, OneLogin)
- CAS (University systems)

For SSO configuration, see [SSO User Guide](./sso-user-guide.md).

## First-Time Login

After your first successful login:

1. **Welcome Screen**: You'll see a welcome message
2. **Profile Setup**: Complete your profile information (optional)
3. **Team Assignment**: You may be assigned to the default team (if configured) or added to a team by an administrator
4. **Dashboard Access**:
   - Regular users see the platform interface
   - Administrators see the admin dashboard

## Session Management

### Session Duration

- Sessions last until the configured **session timeout** (`session_timeout_days`, in days, default 30) — there is no "Remember Me" option and no inactivity-based logout
- **Single Session Mode**: Only one active session per user (if enabled by admin) — logging in elsewhere invalidates the previous session

### Logging Out

**Manual Logout:**
1. Click your profile icon in the top-right corner
2. Select **"Logout"**
3. You'll be redirected to the login page

## Account Security

### Password Requirements

Clouisle enforces password policies (configurable by administrators):

- **Minimum length**: 8 characters (configurable)
- **Uppercase letter**: Required by default
- **Number**: Required by default
- **Special character**: Not required by default
- **No reuse**: Cannot reuse a recent password (default: last 5 passwords)
- There is **no** dictionary/weak-password check

### Login Security Features

**Account Lockout:**
- After 5 failed login attempts (configurable)
- Account locked for 15 minutes (configurable)
- Contact administrator if locked out repeatedly

**Human Verification:**
- Required on login and self-registration when enabled by administrators (except the first bootstrap user)
- Complete it by clicking the verification control before submitting
- If it fails, expires, or cannot load, retry the verification control

**Login Anomaly Detection:**
- System tracks your usual login locations and devices
- Notifies you of logins from new locations (security notification)
- Check notifications if you see anomaly alerts

### Two-Factor Authentication (2FA)

If enabled by your organization:

1. Enter username and password
2. Enter the 6-digit code from your authenticator app (TOTP)
3. Click **"Verify"**

**Setting up 2FA:**
1. Open **Profile Settings** (profile menu) → **Account** tab
2. Click **"Enable Two-Factor Authentication"**
3. Scan the QR code with an authenticator app (Google Authenticator, Authy, etc.)
4. Enter the verification code to confirm
5. Save the backup codes in a safe place

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
3. Check your email for the reset link
4. Click the link and enter a new password
5. Log in with your new password

See [Password Management](./password-management.md) for details.

### Account Locked

**Problem**: "Account locked" message after failed login attempts

**Solutions:**
1. Wait for the automatic unlock (15 minutes by default)
2. Contact administrator for immediate unlock
3. Use password reset if you forgot your password

### Email Verification Not Received

**Problem**: Didn't receive verification email

**Solutions:**
1. Check spam/junk folder
2. Wait a few minutes (email may be delayed)
3. Click **"Resend Verification Email"**
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
- Wait for an administrator to activate your account
- You'll receive an email when approved
- Contact administrator if waiting too long

### Session Expired

**Problem**: "Session expired" message during use

**Solutions:**
1. Log in again
2. Contact administrator to adjust the session timeout
3. Check if you're logged in on another device (single session mode)

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

### Account Management

**Regular Tasks:**
- Update your password when required
- Review login notifications for suspicious activity
- Keep profile information current

## Related Documentation

- [Password Management](./password-management.md) - Change and reset passwords
- [SSO User Guide](./sso-user-guide.md) - Single Sign-On details
- [Profile Settings](../profile/profile-settings.md) - Manage your profile

## Getting Help

If you continue to experience login issues:

1. **Check System Status**: Verify Clouisle is operational
2. **Contact Support**: Reach out to your organization's support team
3. **Administrator**: Contact your Clouisle administrator
4. **Documentation**: Review [Troubleshooting Guide](../../deployment/DEPLOYMENT.md#troubleshooting)

---

**Last Updated**: 2026-02-11
