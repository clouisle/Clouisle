# Integrations and SSO Configuration Guide

Manage external services in **Site Settings → Integrations** (`/site-settings/integrations`). Login providers, outbound email, Webhook delivery, and manual Feishu directory sync share one Integration model, but their capabilities and permissions remain separate.

## Supported capabilities

| Provider type | Supported capabilities | Management domain |
|---|---|---|
| `oauth2`, `oidc`, `saml2`, `cas` | `user_login` | Login |
| `email`, `webhook` | `notification` | Settings |
| `feishu` | `directory_sync`, `user_login` | Settings (app ID/app secret, department scope, directory sync) and Login (sign-in opt-in, button text, sign-in enable/disable) |

Capabilities are statically declared by the backend registry. Enabling an integration does not grant it additional capabilities. Email, Webhook, and Feishu are singleton integrations configured through their specialized forms. **Feishu does not provide Agent messaging in this implementation.**

Feishu is a single integration built from one Feishu app (app ID and app secret) that declares both `directory_sync` and `user_login`. Enabling the Feishu integration never grants sign-in by itself: web login is an explicit opt-in on the same integration. Turning the integration off stops both directory sync and sign-in while preserving the opt-in. See [System settings](system-settings.md) for its directory synchronization behavior.

## Permissions

- `admin:integrations:login:read/update`: view/manage login integrations and the global SSO policy shown on **Site Settings → Security**.
- `admin:integrations:settings:read/update`: view/manage builtin email, Webhook, and Feishu configuration, credentials, tests, and synchronization.
- Either read domain permits access to the Integrations page and catalog. The instance list is filtered to the caller's domains; edit controls remain separate. Backend authorization is authoritative.
- Update authorization on the generic `PUT /api/v1/admin/integrations/{id}` is per field. `enabled_capabilities` and `is_enabled` are charged to the domain of the capabilities involved (`user_login` → login, `directory_sync` → settings). A builtin's `config` and `credentials` are charged to settings. Login-facing fields (`button_text`, `display_name`, `icon_url`, `login_config`, `attribute_mapping`) are charged to login whenever the integration type is login-capable. Because Feishu is both a builtin and login-capable, two fields of the same card can require different domains.
- `admin:settings:read/update` still governs unrelated site settings; it is not a replacement for integration permissions.

## Configure GitHub login

1. Deploy Clouisle with an externally reachable backend/proxy URL and a correct `FRONTEND_URL`. Keep a working administrator login available.
2. In **Site Settings → Security**, configure the global SSO settings: enable SSO, allow password login, automatic account creation, approval, and email matching as appropriate. Their existing `sso_*` setting keys and authentication behavior are unchanged.
3. Register a GitHub OAuth App under **GitHub Settings → Developer settings → OAuth Apps**. Use `https://your-domain.com/api/v1/sso/callback/github` as its authorization callback URL.
4. Add a login integration named `github`, with provider type `oauth2`, display name `GitHub`, the `user_login` capability, and the desired button text/icon. Set its enabled state and its own `login_config` (signup, approval, default role).
5. Enter this non-secret configuration:

```json
{
  "client_id": "your-github-client-id",
  "authorization_url": "https://github.com/login/oauth/authorize",
  "token_url": "https://github.com/login/oauth/access_token",
  "userinfo_url": "https://api.github.com/user",
  "scopes": "read:user user:email"
}
```

Set the integration's separate `attribute_mapping` field to `{"email":"email","username":"login","avatar_url":"avatar_url"}`.

6. Supply the client secret through the credential field (`credentials.client_secret` in the API), not `config`. Save, test, and complete a real login in a separate browser session; the configuration test is not a full login.

**Existing callback URLs remain unchanged:** `/api/v1/sso/login/{name}` and `/api/v1/sso/callback/{name}`. The frontend receives the result at `/sso-callback`. Use the externally reachable backend origin, or frontend origin when it proxies `/api/*`; `API_BASE_URL` is internal and does not select that origin. Keep the integration name stable because it is the registered URL slug.

## Configure Feishu sign-in

Feishu web sign-in is an opt-in capability of the Feishu integration. It uses the same app ID and app secret as directory sync; you do not create a second provider.

1. In the Feishu developer console, add the card's **Redirect URL** — `https://<backend-host>/api/v1/sso/callback/<integration-name>`, for example `…/api/v1/sso/callback/feishu` — to the app's redirect-URI allowlist. The Feishu card shows this exact value with a copy button; `<backend-host>` is the externally reachable backend/proxy origin, the same origin used for every provider's SSO callback.
2. Grant the app the login scopes `contact:user.base:readonly contact:user.email:readonly`. Identity comes from the signed-in user's profile and needs no scope, but the email field requires `contact:user.email:readonly`.
3. In **Site Settings → Integrations → Feishu**, open the card's capability section and turn on **Feishu sign-in**, optionally setting the button text. Both capability switches (directory sync and sign-in) are saved together through the generic `PUT /api/v1/admin/integrations/{id}` as `enabled_capabilities`: opening the card requires the settings read domain, and changing the sign-in opt-in requires `admin:integrations:login:update`, so a role enabling it holds both domains (a superuser always can).
4. Save the app credentials on the same card if they are not configured yet. They are shared with directory sync, and a blank secret field preserves the saved secret. Leave the integration enabled.

Sign-in is advertised on the login page only when global SSO is enabled, the integration is enabled, and `user_login` is one of its enabled capabilities. Without the opt-in, the integration keeps serving directory sync only and no Feishu login button appears. Turning the integration off stops both capabilities while preserving the opt-in.

The Feishu subject stored as the external identity `provider_user_id` is the profile `union_id`, falling back to `open_id` when `union_id` is absent, so replacing the app within the same developer account does not break existing connections.

A Feishu account whose directory record carries no email receives the same deterministic placeholder address the directory sync uses, `feishu-<sha256(user_id)>@accounts.clouisle.example`, so sign-in and sync converge on one local account instead of creating two. Deriving that address needs the Feishu `user_id`, which requires `contact:user.employee_id:readonly`; without that scope there is no `user_id` for such an account and its first sign-in is rejected rather than creating a placeholder identity.

## Protocol configuration

OAuth2/OIDC retains client IDs, endpoints, scopes, and mapping; SAML2 retains entity IDs, SSO URL, certificate and ACS URL (`/sso/callback/{name}`); CAS retains server URL, service URL and version.

Attribute mapping supports dot paths such as `profile.name` and JSONPath expressions such as `$.emails[0].value`; the first matching value is used. GitHub's username and avatar fields are `login` and `avatar_url` rather than OIDC's usual `name` and `picture`.

Login-specific `allow_signup`, `require_approval`, and `default_role_id` are stored in `login_config`, not at the top level. Existing automatic registration, approval, and email-matching behavior is preserved. Disabling password login still requires at least one superuser with a bound identity connection.

## API reference

Public discovery is `GET /api/v1/sso/integrations`; the removed `/sso/providers` endpoint has no compatibility alias. Only enabled login-capable integrations appear, and discovery returns an empty list when global SSO is disabled. Users disconnect their own identities through `DELETE /api/v1/sso/connections/{id}`.

Management uses `/api/v1/admin/integrations`:

| Method | Relative path | Purpose |
|---|---|---|
| GET | `/types` | Static provider/capability catalog |
| GET | base path | Domain-filtered instances |
| POST | base path | Create a non-singleton login integration |
| PUT / DELETE | `/{id}` | Update an authorized instance; delete login integrations only (singleton deletion forbidden) |
| POST | `/{id}/test` | Test login integration configuration |
| GET / PUT | `/login-settings` | Global login policy; existing SSOSettings wire keys (UI: **Site Settings → Security**) |
| GET / PUT | `/email`, `/webhook` | Builtin configuration |
| POST | `/email/test`, `/webhook/test` | Builtin delivery tests |
| GET / PUT | `/feishu/config` | Feishu app configuration |
| GET | `/feishu/departments` | Browse visible departments |
| PUT | `/feishu/department-scope` | Save selected departments |
| POST | `/feishu/sync` | Run manual directory sync |

See [SSO and Integrations API](../../api-reference/endpoints/sso.md) for request shapes. Both Feishu capability switches are saved through the generic `PUT /{id}` as `enabled_capabilities`, charged per capability that actually changes (sign-in on the login domain, directory sync on the settings domain), and the sign-in button text is a login-domain field. The `/feishu/*` endpoints stay on the settings domain and only carry app ID, app secret, department scope, and sync. Admin responses **never return credentials**, decrypted or encrypted. They expose only `credentials_configured` field names and `supported_capabilities`; do not treat a redacted response as a complete backup. Empty credential values preserve saved secrets. Secrets are Fernet-encrypted at rest and decrypted only for runtime consumers.

## Upgrading existing installations

**Back up the database and retain the matching backend `SECRET_KEY` before deploying.** Stop all old-version API processes and workers before schema migration. Perform the cutover, then start API processes and workers using the same new version. **Mixed-version rolling deployment is not supported:** old and new binaries use different table and column names. Transactional/advisory-lock migration protection does not make old processes compatible with the migrated schema.

Before schema generation, the idempotent migration renames `sso_providers` to `integrations` and `protocol` to `provider_type`, moves signup policy into `login_config`, adds `user_login`, and separates/encrypts secret configuration. Session and user identity relation columns change from `provider_id` to `integration_id`, while their authentication table names and the external identity field `provider_user_id` remain unchanged.

**Integration UUIDs, identity connections, external identity IDs, and foreign-key relationships are preserved.** Users do not need to reconnect their identities, and identity providers do not need new callback URLs. Connection response fields become `integration_id`, `integration_name`, `integration_display_name`, and `integration_icon_url`; update API clients previously reading `provider_*` fields.

Email, Webhook, and Feishu settings are imported into singleton Integration records once. Migrated legacy per-service SiteSetting keys are removed only after persistence; runtime consumers no longer fall back to those keys. Global `sso_*` login policy remains, under the integration category.

Role grants migrate from `admin:sso:read/update` to `admin:integrations:login:read/update`. Existing `admin:settings:read/update` grants additionally receive the corresponding integration settings-domain grant while retaining unrelated settings access. This does not grant login administrators builtin credential access, or vice versa.

Permission grants migrate once; the completion marker prevents a restart from restoring new-domain permissions deliberately revoked by an administrator. Generic `PUT /{id}` for a builtin also requires settings-domain update permission; singleton deletion is forbidden.

**Rollback requires restoring the pre-cutover database with the matching application version and encryption key.** Do not simply downgrade binaries against the migrated schema, change `SECRET_KEY`, or attempt to reconstruct credentials from admin responses. If startup migration fails, resolve the reported cause before resuming service; do not manually seed duplicate providers or discard identity rows.

## Troubleshooting

- Missing login buttons: check global SSO enablement, integration enablement, and the `user_login` capability. For Feishu this is an explicit opt-in, so an enabled integration whose `enabled_capabilities` omit `user_login` shows no button.
- Feishu callback rejected or no account created: confirm the app registered `https://<backend-host>/api/v1/sso/callback/<integration-name>`, that the login scopes include `contact:user.email:readonly`, and — for accounts without a directory email — `contact:user.employee_id:readonly`, without which there is no `user_id` to derive the placeholder address and the first sign-in is rejected.
- Callback mismatch: confirm the registered name and externally reachable URL/proxy headers. Do not register a new integrations callback route.
- Missing configuration controls: check the relevant login or settings permission domain.
- Feishu department browsing or sync reports that the integration must be enabled: save the app ID and app secret first, then enable the Feishu integration and turn on the **Directory sync** switch in its card. The department section is only shown while the integration is enabled and directory sync is saved on, and the API replies with that same guidance otherwise.
- Undecryptable credentials: restore the matching `SECRET_KEY` or re-save credentials using the relevant settings form.
- Cannot disconnect an identity: an account with no password cannot remove its only authentication method; establish another valid method first.
