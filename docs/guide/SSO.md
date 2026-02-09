# SSO Configuration Guide

This guide explains how to configure Single Sign-On (SSO) in Clouisle, with GitHub as a step-by-step example.

---

## Table of Contents

- [Overview](#overview)
- [Supported Protocols](#supported-protocols)
- [Prerequisites](#prerequisites)
- [Step 1: Enable SSO](#step-1-enable-sso)
- [Step 2: Create an SSO Provider](#step-2-create-an-sso-provider)
  - [Example: GitHub OAuth](#example-github-oauth)
- [Step 3: Test the Connection](#step-3-test-the-connection)
- [Step 4: Verify Login](#step-4-verify-login)
- [Provider Configuration Reference](#provider-configuration-reference)
  - [OAuth2 / OIDC](#oauth2--oidc)
  - [SAML 2.0](#saml-20)
  - [CAS](#cas)
- [Attribute Mapping](#attribute-mapping)
  - [Dot Notation](#dot-notation)
  - [JSONPath](#jsonpath)
- [Site Settings](#site-settings)
- [API Reference](#api-reference)
- [Troubleshooting](#troubleshooting)

---

## Overview

Clouisle supports SSO authentication, allowing users to log in with external identity providers such as GitHub, Google, Azure AD, Okta, and others. SSO can be used alongside password-based login or as the sole authentication method.

The login flow works as follows:

1. User clicks an SSO provider button on the login page
2. Browser redirects to the provider's authorization page
3. User authenticates at the provider
4. Provider redirects back to Clouisle with an authorization code
5. Clouisle exchanges the code for user information
6. User is logged in (or a new account is created automatically)

## Supported Protocols

| Protocol | Use Case | Examples |
|----------|----------|---------|
| OAuth2 / OIDC | Most modern providers | GitHub, Google, Azure AD, Okta, Auth0 |
| SAML 2.0 | Enterprise identity providers | Azure AD, Okta, OneLogin, ADFS |
| CAS | University / institutional SSO | Apereo CAS |

## Prerequisites

- Clouisle deployed and accessible via a public URL (SSO requires callback URLs reachable by the provider)
- `API_BASE_URL` and `FRONTEND_URL` environment variables set to your actual domain (e.g., `https://example.com`)
- Admin account with superuser privileges

---

## Step 1: Enable SSO

1. Log in as an admin and navigate to **Site Settings** -> **Security**
2. In the **SSO Settings** section, toggle **Enable SSO** to on
3. Configure the global SSO behavior:

| Setting | Default | Description |
|---------|---------|-------------|
| Allow Password Login | On | Keep password login available alongside SSO |
| Auto Create Users | On | Automatically create accounts on first SSO login |
| Require Approval | Off | Require admin approval for new SSO users |
| Match by Email | On | Link SSO accounts to existing users by email |

4. Click **Save**

**Note**: If you disable **Allow Password Login**, at least one superuser must have an SSO connection bound to their account. This prevents locking all admins out of the system.

---

## Step 2: Create an SSO Provider

### Example: GitHub OAuth

#### 2.1 Register an OAuth App on GitHub

1. Go to GitHub: **Settings** -> **Developer settings** -> **OAuth Apps** -> **New OAuth App**
2. Fill in the form:

| Field | Value |
|-------|-------|
| Application name | `Clouisle` (or any name you prefer) |
| Homepage URL | `https://your-domain.com` |
| Authorization callback URL | `https://your-domain.com/api/v1/sso/callback/github` |

> The callback URL format is `{API_BASE_URL}/api/v1/sso/callback/{provider_name}`. The `provider_name` must match the name you set in Clouisle (next step).

3. Click **Register application**
4. Copy the **Client ID**
5. Click **Generate a new client secret** and copy the **Client Secret**

#### 2.2 Add the Provider in Clouisle

1. Navigate to **Site Settings** -> **SSO**
2. Click **Add Provider**
3. Fill in the **Basic Info** tab:

| Field | Value |
|-------|-------|
| Provider Name | `github` |
| Protocol | `OAuth2/OIDC` |
| Display Name | `GitHub` |
| Button Text | `Sign in with GitHub` |
| Icon URL | `https://github.githubassets.com/favicons/favicon-dark.svg` |
| Enabled | On |
| Allow Signup | On |

4. Switch to the **Configuration** tab and enter:

```json
{
  "client_id": "your-github-client-id",
  "client_secret": "your-github-client-secret",
  "authorization_url": "https://github.com/login/oauth/authorize",
  "token_url": "https://github.com/login/oauth/access_token",
  "userinfo_url": "https://api.github.com/user",
  "scopes": "read:user user:email"
}
```

5. Switch to the **Attribute Mapping** tab and enter:

```json
{
  "email": "email",
  "username": "login",
  "avatar_url": "avatar_url"
}
```

> GitHub returns `login` as the username field and `avatar_url` for the profile picture. The default mapping uses `name` and `picture` (OIDC standard claims), which don't match GitHub's response format.

6. Click **Save**

---

## Step 3: Test the Connection

1. On the **SSO** settings page, find the GitHub provider in the list
2. Click the **Test Connection** button (flask icon)
3. A success message confirms the configuration is valid

The test verifies that Clouisle can construct a valid authorization URL with the provided configuration. It does not perform a full login flow.

---

## Step 4: Verify Login

1. Open a new browser or incognito window
2. Navigate to the login page
3. You should see a **Sign in with GitHub** button below the password form
4. Click the button and complete the GitHub authorization
5. You will be redirected back to Clouisle and logged in

If **Auto Create Users** is enabled, a new user account is created automatically on first login. If **Match by Email** is enabled and a user with the same email already exists, the SSO account is linked to the existing user.

---

## Provider Configuration Reference

### OAuth2 / OIDC

| Field | Required | Description |
|-------|----------|-------------|
| `client_id` | Yes | OAuth2 Client ID from the provider |
| `client_secret` | Yes | OAuth2 Client Secret from the provider |
| `authorization_url` | Yes | Provider's authorization endpoint |
| `token_url` | Yes | Provider's token exchange endpoint |
| `userinfo_url` | Yes | Provider's user info endpoint |
| `scopes` | No | Space-separated scopes (default: `openid email profile`) |

**Common provider URLs:**

| Provider | authorization_url | token_url | userinfo_url |
|----------|-------------------|-----------|--------------|
| GitHub | `https://github.com/login/oauth/authorize` | `https://github.com/login/oauth/access_token` | `https://api.github.com/user` |
| Google | `https://accounts.google.com/o/oauth2/v2/auth` | `https://oauth2.googleapis.com/token` | `https://openidconnect.googleapis.com/v1/userinfo` |
| GitLab | `https://gitlab.com/oauth/authorize` | `https://gitlab.com/oauth/token` | `https://gitlab.com/api/v4/user` |

### SAML 2.0

| Field | Required | Description |
|-------|----------|-------------|
| `sp_entity_id` | Yes | Service Provider Entity ID (your Clouisle instance identifier) |
| `idp_entity_id` | Yes | Identity Provider Entity ID |
| `sso_url` | Yes | IdP Single Sign-On URL |
| `x509_cert` | Yes | IdP X.509 certificate (PEM format, without header/footer) |
| `acs_url` | Yes | Assertion Consumer Service URL (`{API_BASE_URL}/api/v1/sso/callback/{provider_name}`) |
| `slo_url` | No | SP Single Logout URL |
| `idp_slo_url` | No | IdP Single Logout URL |
| `name_id_format` | No | NameID format (default: `urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified`) |

### CAS

| Field | Required | Description |
|-------|----------|-------------|
| `server_url` | Yes | CAS server base URL |
| `service_url` | Yes | Service URL for CAS validation |
| `version` | No | CAS protocol version: `1`, `2`, or `3` (default: `3`) |

---

## Attribute Mapping

Attribute mapping defines how provider user data fields map to Clouisle user fields. The supported Clouisle fields are:

| Clouisle Field | Description |
|----------------|-------------|
| `email` | User email address |
| `username` | Username |
| `avatar_url` | Profile picture URL |

### Dot Notation

For simple nested objects, use dot-separated paths:

```json
{
  "email": "email",
  "username": "profile.name",
  "avatar_url": "profile.picture"
}
```

This extracts `data["profile"]["name"]` from the provider response.

### JSONPath

For complex data structures (arrays, filters), use JSONPath expressions starting with `$`:

```json
{
  "email": "$.emails[0].value",
  "username": "$.name.givenName",
  "avatar_url": "$.photos[0].value"
}
```

JSONPath is useful when the provider returns data like:

```json
{
  "emails": [
    {"value": "user@example.com", "primary": true},
    {"value": "alias@example.com", "primary": false}
  ],
  "name": {"givenName": "John", "familyName": "Doe"},
  "photos": [{"value": "https://example.com/photo.jpg"}]
}
```

When a JSONPath expression matches multiple values, the first match is used.

**Note**: Paths that do not start with `$` are treated as dot notation for backward compatibility. Existing mappings like `{"email": "email"}` continue to work without changes.

---

## Site Settings

These global settings control SSO behavior across all providers. Configure them in **Site Settings** -> **Security**.

| Setting | Default | Description |
|---------|---------|-------------|
| `sso_enabled` | `false` | Master switch for SSO. When off, no SSO buttons appear on the login page. |
| `sso_allow_password_login` | `true` | Allow password login when SSO is enabled. Disabling this makes SSO the only login method. |
| `sso_auto_create_users` | `true` | Automatically create user accounts on first SSO login. |
| `sso_require_approval` | `false` | New SSO users require admin approval before they can access the system. |
| `sso_match_by_email` | `true` | Match SSO users to existing accounts by email address. |

Each provider also has its own **Allow Signup** and **Require Approval** settings that can override the global defaults.

---

## API Reference

### Public Endpoints

```http
GET /api/v1/sso/providers
```

Returns the list of enabled SSO providers (for rendering login buttons).

```http
GET /api/v1/sso/login/{provider_name}?redirect=/dashboard
```

Initiates the SSO login flow. Redirects the browser to the provider's authorization page.

```http
GET /api/v1/sso/callback/{provider_name}
```

Handles the provider callback. This URL is used as the redirect/callback URI when registering your app with the provider.

### Admin Endpoints

All admin endpoints require superuser authentication.

```http
GET    /api/v1/sso/admin/providers
POST   /api/v1/sso/admin/providers
PUT    /api/v1/sso/admin/providers/{provider_id}
DELETE /api/v1/sso/admin/providers/{provider_id}
POST   /api/v1/sso/admin/providers/{provider_id}/test
```

### Create Provider Example

```http
POST /api/v1/sso/admin/providers
Content-Type: application/json

{
  "name": "github",
  "protocol": "oidc",
  "display_name": "GitHub",
  "button_text": "Sign in with GitHub",
  "icon_url": "https://github.githubassets.com/favicons/favicon-dark.svg",
  "config": {
    "client_id": "your-client-id",
    "client_secret": "your-client-secret",
    "authorization_url": "https://github.com/login/oauth/authorize",
    "token_url": "https://github.com/login/oauth/access_token",
    "userinfo_url": "https://api.github.com/user",
    "scopes": "read:user user:email"
  },
  "attribute_mapping": {
    "email": "email",
    "username": "login",
    "avatar_url": "avatar_url"
  },
  "is_enabled": true,
  "allow_signup": true,
  "require_approval": false
}
```

Response:

```json
{
  "code": 0,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "github",
    "protocol": "oidc",
    "display_name": "GitHub",
    "is_enabled": true,
    "created_at": "2026/02/09 10:00"
  },
  "msg": "success"
}
```

---

## Troubleshooting

### SSO buttons not appearing on login page

- Verify **Enable SSO** is turned on in **Site Settings** -> **Security**
- Verify the provider's **Enabled** toggle is on
- Check that `FRONTEND_URL` and `API_BASE_URL` environment variables are set correctly

### Callback URL mismatch error

The callback URL registered with the provider must exactly match:

```
{API_BASE_URL}/api/v1/sso/callback/{provider_name}
```

- `API_BASE_URL` is the backend URL (e.g., `https://example.com` if the frontend proxies `/api/*` to the backend, or `https://api.example.com` if the backend has a separate domain)
- `provider_name` is the name you set when creating the provider in Clouisle (e.g., `github`)

### User redirected to error page after SSO login

Check the backend logs for details:

```bash
# Docker Compose
docker compose logs backend | grep sso

# Kubernetes
kubectl -n clouisle logs deployment/backend | grep sso
```

Common causes:
- **SSO session expired**: The user took longer than 10 minutes to complete authentication. Try again.
- **Invalid client secret**: The `client_secret` in the provider configuration is incorrect.
- **Scope not authorized**: The requested scopes are not enabled in the provider's OAuth app settings.

### User created but email is empty

The provider may not return the email in the expected field. Check the provider's API documentation and update the attribute mapping. For GitHub, ensure the `read:user user:email` scopes are included, and note that GitHub may return `null` for email if the user has set their email to private.

### "Cannot disconnect the only authentication method"

Users who logged in via SSO without a password cannot disconnect their SSO connection, as it would leave them with no way to log in. Set a password first via the admin panel, then disconnect.
