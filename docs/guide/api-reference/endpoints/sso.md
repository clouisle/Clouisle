# SSO and Integrations API

The SSO API retains browser login and identity disconnection. Management uses unified integrations — see [Admin Integrations](#admin-integrations). Feishu signs users in through these same protocol endpoints; its `user_login` capability is an explicit opt-in on the Feishu integration.

**Base URL**: `/api/v1/sso`

---

## Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/sso/integrations` | List enabled login integrations (public) |
| `GET` | `/api/v1/sso/login/{provider_name}` | Begin SSO login; redirects the browser to the identity provider |
| `GET` | `/api/v1/sso/callback/{provider_name}` | Identity-provider callback; redirects the browser back to the frontend |
| `GET` | `/api/v1/sso/links/integrations` | List enabled Feishu sign-in integrations the caller can link |
| `POST` | `/api/v1/sso/links?provider_name={name}` | Start linking Feishu to the authenticated account |
| `POST` | `/api/v1/sso/links/complete` | Confirm the staged identity as the original authenticated caller |
| `DELETE` | `/api/v1/sso/connections/{connection_id}` | Disconnect one of the caller's SSO connections |

> `login` and `callback` return HTTP redirects, not the JSON envelope. Login results arrive at `/sso-callback`; Feishu account-link results arrive at `/sso-link-callback` without issuing a login token.

---

## 1. List Enabled Login Integrations

Public endpoint used by the login page to render SSO buttons.

```http
GET /api/v1/sso/integrations HTTP/1.1
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
      "provider_type": "oauth2"
    }
  ],
  "msg": "success"
}
```

Returns an empty `data` array when SSO is disabled globally (`sso_enabled` site setting is off), even if providers are configured. An integration is listed only when it is enabled **and** `user_login` is one of its enabled capabilities, so an enabled Feishu integration that has not opted in to sign-in stays hidden. `provider_type` may be `oauth2`, `oidc`, `saml2`, `cas`, or `feishu`.

---

## 2. Begin SSO Login

```http
GET /api/v1/sso/login/github?redirect=/dashboard HTTP/1.1
```

### Query Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `redirect` | string | No | Same-origin frontend path (e.g. `/app/kb`) to land on after login. Non-relative or external values are ignored, and `/app` is used instead — for every role |

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
| `oauth2` / `oidc` / `feishu` | `code`, `state` |
| `cas` | `ticket` (and `state`) |
| `saml2` | `SAMLResponse`, `RelayState` |

Register this URL with the identity provider as `https://<backend-host>/api/v1/sso/callback/{name}`. For Feishu, the app also needs the login scopes `contact:user.base:readonly contact:user.email:readonly`; the callback exchanges the code with PKCE and stores the profile `union_id` (falling back to `open_id`) as `provider_user_id`.

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

### Linking Feishu to the current account

All three `/links` endpoints require `Authorization: Bearer <token>`. They do not create a user, run automatic email matching, or replace the caller's login session.

1. `GET /api/v1/sso/links/integrations` returns the same public integration fields as login discovery, restricted to enabled Feishu sign-in integrations not already linked by the caller. Global SSO must be enabled.
2. `POST /api/v1/sso/links?provider_name=feishu` returns `{"code":0,"data":{"authorization_url":"https://…","session_id":"…"},"msg":"…"}`. Store the pending session in the current tab before navigating to the authorization URL. The session expires after 10 minutes and reuses the registered `/sso/callback/{name}` URL.
3. Successful provider authorization stages the identity and returns HTTP `303` to `{frontend}/sso-link-callback?session_id=…`. Rejection returns to that route with `error=sso_provider_not_found`, `sso_session_expired`, or `sso_login_failed`. The browser checks its pending state and requires explicit confirmation.
4. `POST /api/v1/sso/links/complete` with `{"session_id":"…"}` binds the staged identity to its original authenticated owner and consumes the session. Success returns `{"code":0,"data":null,"msg":"…"}`. Unverified, expired, consumed, disabled-provider, and other-owner sessions cannot complete. Existing OAuth/directory identity conflicts or a provider email owned by another account are rejected with business code `5001`; configuration errors at initiation use `6304`.

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

## Admin Integrations

Management base: `/api/v1/admin/integrations`. Login-domain operations require `admin:integrations:login:read/update`; builtin configuration requires `admin:integrations:settings:read/update`. Catalog/list accepts either read domain, and the list filters instances to authorized domains. Unrelated site settings retain their existing permission namespace.

| Method | Relative path | Description |
|---|---|---|
| GET | `/types` | Static provider types, capabilities, singleton flags |
| GET | base | Domain-filtered integration list |
| POST | base | Create a non-singleton login integration |
| PUT / DELETE | `/{id}` | Update an authorized integration, field by field (domains below); delete login integrations only, never a singleton |
| POST | `/{id}/test` | Test login configuration |
| DELETE | `/connections/{connection_id}` | Disconnect any user's identity; requires `admin:integrations:login:update` |
| GET / PUT | `/login-settings` | Global login settings (existing SSOSettings keys); UI entry is **Site Settings → Security** |
| GET / PUT | `/email`, `/webhook` | Builtin notification configuration |
| POST | `/email/test`, `/webhook/test` | Test notification delivery |
| GET / PUT | `/feishu/config` | Feishu configuration |
| GET | `/feishu/departments` | Browse departments |
| PUT | `/feishu/department-scope` | Save sync scope |
| POST | `/feishu/sync` | Manual directory synchronization |

Configuration test responses omit authorization URLs to avoid exposing query parameters or credentials.

Create/update fields: `name`, `provider_type`, `display_name`, `icon_url`, `button_text`, `is_enabled`, `enabled_capabilities`, `config`, `attribute_mapping`, `credentials`, and `login_config`. Signup policy (`allow_signup`, `require_approval`, `default_role_id`) belongs in `login_config`. Secrets are plaintext input only in `credentials`, encrypted at rest, and never returned. Empty secret inputs preserve stored values.

```json
{
  "name": "github",
  "provider_type": "oauth2",
  "display_name": "GitHub",
  "is_enabled": true,
  "enabled_capabilities": ["user_login"],
  "config": {
    "client_id": "client-id",
    "authorization_url": "https://github.com/login/oauth/authorize",
    "token_url": "https://github.com/login/oauth/access_token",
    "userinfo_url": "https://api.github.com/user",
    "scopes": "read:user user:email"
  },
  "credentials": {"client_secret": "client-secret"},
  "attribute_mapping": {"email": "email", "username": "login", "avatar_url": "avatar_url"},
  "login_config": {"allow_signup": true, "require_approval": false}
}
```

Admin output omits `credentials` entirely and exposes `credentials_configured` and `supported_capabilities`. The registry statically supports login for OAuth2/OIDC/SAML2/CAS, notification for email/Webhook, and both directory sync and login for Feishu, where login stays an explicit opt-in through `enabled_capabilities`. Builtins are singletons and use their specialized configuration endpoints; because Feishu is a singleton, it never appears in the protocol list for creating a new login integration.

`PUT /{id}` authorizes per field, not per instance: `enabled_capabilities` and `is_enabled` are charged to the domain of the capabilities involved (`user_login` → login, `directory_sync` → settings); a builtin's `config` and `credentials` to settings; and `button_text`, `display_name`, `icon_url`, `login_config`, and `attribute_mapping` to login when the integration type is login-capable (otherwise settings). The same field set covers Feishu, so opting in to Feishu sign-in is `{"enabled_capabilities": ["directory_sync", "user_login"], "is_enabled": true}` on the generic endpoint and requires `admin:integrations:login:update`. The `/feishu/*` endpoints below remain on the settings domain.

The old management namespace and `/sso/providers` discovery endpoint are removed. Login/callback URLs stay unchanged; migration preserves UUIDs and bound identities. User connection fields are now `integration_id`, `integration_name`, `integration_display_name`, `integration_icon_url`; `provider_user_id` remains the external identity key. See the [upgrade and rollback cautions](../../admin-guide/settings/SSO.md#upgrading-existing-installations).

See the [integration administration guide](../../admin-guide/settings/SSO.md) for protocol setup and the `config`, `attribute_mapping`, `credentials`, and `login_config` boundaries.

## Feishu Knowledge Synchronization

Base: `/api/v1/admin/integrations/feishu/knowledge`. **All endpoints require an active system superuser**, not delegated integration-management permissions. Responses use the standard `code`, `data`, `msg` envelope.

| Method | Relative path | Data / behavior |
|---|---|---|
| GET | `/spaces` | App-visible Wiki spaces (`space_id`, `name`) |
| GET | `/targets` | Active knowledge bases in non-deleted teams (`id`, `name`, `team_name`) |
| GET | `/sources` | Configured sources and their latest results |
| POST | `/sources` | Create a source after validating the selected space and destination |
| PUT | `/sources/{source_id}` | Change `name`, `interval_minutes`, or `is_enabled`; destination and space are immutable |
| POST | `/sources/{source_id}/sync` | Queue synchronization; response is source state, not completed indexing |
| DELETE | `/sources/{source_id}` | Remove imported documents/indexes and source; returns `{ "id": "<source_id>" }` |

Create body:

```json
{
  "knowledge_base_id": "<uuid>",
  "space_id": "<feishu-space-id>",
  "name": "Team documentation",
  "interval_minutes": 60,
  "is_enabled": true
}
```

`name` is nonblank and at most 100 characters; `space_id` is nonblank and at most 255. Intervals are 1–43,200 minutes (default 60). Unknown create/update fields are rejected. A duplicate destination/space source returns HTTP 409, as does a conflicting operation on a busy source. Disabled sources must be enabled before synchronization.

Source output includes `id`, `knowledge_base_id`, `knowledge_base_name`, `space_id`, `space_name` (when recorded), `name`, `interval_minutes`, `is_enabled`, `status`, `last_synced_at`, `last_error`, `last_result`, `created_at`, and `updated_at`. Run results report `scan_complete`, `scanned`, `indexed`, `unchanged`, `removed`, `failed`, `unsupported`, `errors`, `skipped`, and `warnings`; they describe the latest run, not a history endpoint. Unsupported content is counted in `unsupported` and listed in `skipped` with `node_token`, `node_title`, `type`, and `reason`, not in `errors`. Only actual failures mark a completed scan as `error`; unsupported-only runs are `success` with `last_error=null`.

Source types `docx`, `doc`, `sheet`, `bitable`, and supported `file` formats are imported using tenant-token access. Mindnote has no supported public content API and is reported under `unsupported`, as are unsupported file formats. Images and parseable embedded attachments are included; unextractable blocks/media produce conversion warnings. This does not mirror Feishu user permissions; local team/knowledge-base authorization applies. See [the format matrix, setup, and failure/deletion behavior](../../admin-guide/settings/SSO.md#synchronize-feishu-knowledge).

---

## Related

- [Authentication](../authentication.md) — password login, JWT tokens, and `POST /api/v1/login/verify-totp`
- [Users](./users.md) — account management
