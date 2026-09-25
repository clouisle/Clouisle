# SSO API

The SSO API drives the browser-based single sign-on flow (OAuth2 / OIDC, SAML2, and CAS) and lets a signed-in user disconnect their own SSO identities. Provider configuration is an admin concern — see [Admin SSO](#admin-sso).

**Base URL**: `/api/v1/sso`

---

## Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/sso/providers` | List enabled SSO providers (public, no authentication) |
| `GET` | `/api/v1/sso/login/{provider_name}` | Begin SSO login; redirects the browser to the identity provider |
| `GET` | `/api/v1/sso/callback/{provider_name}` | Identity-provider callback; redirects the browser back to the frontend |
| `DELETE` | `/api/v1/sso/connections/{connection_id}` | Disconnect one of the caller's SSO connections |

> `login` and `callback` return HTTP redirects, not the JSON envelope. The frontend receives the result on its `/sso-callback` route.

---

## 1. List Enabled Providers

Public endpoint used by the login page to render SSO buttons.

```http
GET /api/v1/sso/providers HTTP/1.1
```

### Response (`200 OK`)

```json
{
  "code": 0,
  "data": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "github",
      "display_name": "GitHub",
      "icon_url": "https://cdn.example.com/github.svg",
      "button_text": "Continue with GitHub",
      "protocol": "oauth2"
    }
  ],
  "msg": "success"
}
```

Returns an empty `data` array when SSO is disabled globally (`sso_enabled` site setting is off), even if providers are configured.

---

## 2. Begin SSO Login

```http
GET /api/v1/sso/login/github?redirect=/dashboard HTTP/1.1
```

### Query Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `redirect` | string | No | Same-origin frontend path (e.g. `/dashboard`) to land on after login. Non-relative or external values are ignored and `/dashboard` is used instead |

### Response (`307 Temporary Redirect`)

Redirects the browser to the identity provider's authorization URL. A temporary SSO session (valid for 10 minutes) is created to hold the protocol state (PKCE verifier, nonce, or relay state).

### Failure

Unknown or disabled providers, and configuration or initiation errors, redirect to the frontend instead:

```
{frontend}/sso-callback?error=<error_code>&redirect=<path>
```

| `error` value | Meaning |
|---|---|
| `sso_provider_not_found` | No enabled provider with that name |
| `sso_login_failed` | Provider initialization failed |

---

## 3. Identity-Provider Callback

The identity provider redirects the browser here after authentication. The parameters depend on the provider protocol:

| Protocol | Parameters |
|---|---|
| `oauth2` / `oidc` | `code`, `state` |
| `cas` | `ticket` (and `state`) |
| `saml2` | `SAMLResponse`, `RelayState` |

```http
GET /api/v1/sso/callback/github?code=abc123&state=session-token HTTP/1.1
```

### Response (`307 Temporary Redirect`)

On success the browser is redirected to:

```
{frontend}/sso-callback?token=<access_token>&redirect=<path>
```

The token is a standard JWT access token (see [Authentication](../authentication.md)). On failure (expired session, provider error, inactive or pending-approval account) the browser is redirected to:

```
{frontend}/sso-callback?error=<error_code>&redirect=<path>
```

Common `error` values: `sso_provider_not_found`, `sso_session_expired`, `sso_login_failed`, `pending_approval`, `inactive`.

---

## 4. Disconnect SSO Connection

```http
DELETE /api/v1/sso/connections/9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d HTTP/1.1
Authorization: Bearer <token>
```

Removes the caller's link to an SSO identity. Fails with `404` (`sso_connection_not_found`) if the connection does not belong to the caller, and with `403` (`cannot_disconnect_only_auth_method`) when the account has no password and this is its only remaining SSO connection.

### Response (`200 OK`)

```json
{
  "code": 0,
  "data": null,
  "msg": "success"
}
```

---

## Admin SSO

Provider CRUD and connection administration are mounted under `/api/v1/admin/sso`. Listing requires the `admin:sso:read` permission; creating, updating, deleting, testing providers, and disconnecting arbitrary user connections require `admin:sso:update`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/admin/sso/providers` | List all providers, including disabled ones |
| `POST` | `/api/v1/admin/sso/providers` | Create a provider |
| `PUT` | `/api/v1/admin/sso/providers/{provider_id}` | Update a provider |
| `DELETE` | `/api/v1/admin/sso/providers/{provider_id}` | Delete a provider |
| `POST` | `/api/v1/admin/sso/providers/{provider_id}/test` | Test provider connectivity |
| `DELETE` | `/api/v1/admin/sso/connections/{connection_id}` | Disconnect any user's SSO connection |

See the [SSO administration guide](../../admin-guide/settings/SSO.md) for configuration fields per protocol (`config`, `attribute_mapping`, `allow_signup`, `require_approval`, `default_role_id`).

---

## Related

- [Authentication](../authentication.md) — password login, JWT tokens, and `POST /api/v1/login/verify-totp`
- [Users](./users.md) — account management
