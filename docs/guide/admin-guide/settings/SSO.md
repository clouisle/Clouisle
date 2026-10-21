# Integrations and SSO Configuration Guide

Manage external services in **Site Settings → Integrations** (`/site-settings/integrations`). Login providers, email, Webhook, Feishu and WeChat share one Integration model, with separate capabilities and permission domains. Builtins open their own pages (`/site-settings/integrations/email`, `/webhook`, `/feishu`, `/wechat`); login providers retain their list-page dialog.

## Supported capabilities

| Provider type | Supported capabilities | Management domain |
|---|---|---|
| `oauth2`, `oidc`, `saml2`, `cas` | `user_login` | Login |
| `email`, `webhook` | `notification` | Settings |
| `feishu` | `directory_sync`, `user_login`, `notification`, `agent_chat` | Settings (shared app credentials, transport, directory and notifications); Login (sign-in opt-in); personal settings (replying Agent) |
| `wechat` | `agent_chat`, `knowledge_collection` | Settings (platform feature availability); personal settings (each user's authorization and connection purpose) |

Capabilities are statically declared by the backend registry. Feishu and WeChat expose **feature switches, not an integration master switch**. Enable only the required capabilities; changing one does not grant another. Feishu remains a singleton app configured through **Site Settings → Integrations → Feishu**.

Feishu directory sync remains manual and one-way. The administrator selects departments and starts each sync; it creates or updates local users, binds each Feishu identity, and creates or updates department teams and memberships. Notifications remain a separate capability. Feishu Agent chat is another explicit capability and routes private text messages through Clouisle's durable AgentRun runtime; it does not run an Agent loop inside Feishu.

Each user selects their own replying Agent in **Personal settings → Feishu** or with `/use`. Candidates are published Agents their mapped Clouisle account can access. Selection is scoped per integration/user; conversations remain isolated per chat/user/Agent. Changes affect later messages only. Group chats and media are not supported.

## Configure Feishu Agent chat

Feishu Agent chat reuses the existing Feishu app integration and the durable Clouisle AgentRun runtime. It is an explicit `agent_chat` capability; enabling it does not broaden user access to Agents.

1. Enable the Feishu bot capability in the Feishu developer console. Grant `im:message.p2p_msg:readonly` (receive private messages), `im:message:send_as_bot` (send bot replies), and `contact:user.base:readonly` (user identity lookup). Subscribe to `im.message.receive_v1` (**Receive messages**). Publish the app version and complete any required administrator approval so the permissions take effect. Group-mention receive permissions do not permit private-message intake.
2. In **Site Settings → Integrations → Feishu → Agent chat**, choose **HTTP callback** or **Long connection (WebSocket)**. Existing configurations keep callback mode. Match the delivery mode in Feishu Open Platform's **Events & callbacks** settings.
3. Ask each user to link their identity through Feishu directory sync or sign-in and select an Agent in **Personal settings → Feishu**. There is no administrator-managed global Agent list.
4. Enable the `agent_chat` feature in **Integration configuration**. Run the existing API, Celery Beat, and an `agent`-queue worker; no new service or receiver command is required.

The **Agent chat** tab always displays the required app setup checklist, including before the capability or app credentials are configured. It is setup guidance, not an automatic check of granted Feishu permissions.

In **Personal settings → Feishu**, each user saves a replying Agent and turns on **Enable Agent chat**. This switch applies only to that user and saves immediately. Turning it off retains the choice/history and pauses intake, queued processing and unsent replies; already-started work may finish. The shared administrator capability must also remain enabled.

Personal settings show one setup hint at a time: channel availability, identity binding, selected Agent availability, then selection setup. Detailed pause/switch behavior is available under **How it works**.

On upgrade, existing users retain the Agent from their latest selected session; unused users must choose one. The old global list and per-chat selection marker are removed. Deploy matching API and worker versions and restart workers together after the schema cutover.

### Long connection: local or private-network deployments

Save **Long connection (WebSocket)** as the event delivery mode. It uses the saved App ID and App Secret; no public callback URL, Verification Token, or Encrypt Key is needed. In Feishu Open Platform, choose long connection event delivery and subscribe to `im.message.receive_v1`.

An existing Celery worker consuming `agent` automatically manages the receiver when Agent chat is enabled, long connection mode is saved, and app credentials are configured. Feature disable or callback mode stops it; credential changes replace it. Expiring Redis ownership elects one receiver with failover. The child stops when ownership is lost or its parent exits.

The Agent chat tab reports the saved receiver state: waiting for a worker, connecting, connected, reconnecting, unconfigured, disabled, or error. The SDK handles heartbeat/reconnection; terminal failures are restarted by the worker with backoff. Keep the API, worker, and Beat running with the same database, Redis, and `SECRET_KEY`. Use a dedicated Feishu app for local debugging to avoid sharing event delivery with production.

**Connected** confirms only the WebSocket connection, not message permissions or event subscriptions. If the bot does not reply and there are no inbound receipts, check that `im:message.p2p_msg:readonly` is granted in the published app version and that `im.message.receive_v1` is subscribed with long connection delivery. Send a new private message after the changes take effect; do not assume previously unreceived messages will replay.

### HTTP callback: publicly reachable deployments

Save **HTTP callback** as the delivery mode. Configure the matching Verification Token and Encrypt Key, then register `https://<backend-host>/api/v1/integrations/feishu/callback` in Feishu's encrypted event delivery settings. Feishu must be able to reach this URL. Secrets are encrypted at rest and never returned by the settings API. The callback endpoint rejects requests while long connection mode is selected; switching back to callbacks automatically stops the managed receiver.

### Bot commands

Users can message the bot only in private text chats. `/agents` lists the user's accessible published Agents and `/use <number>` shares the personal-settings selection. `/new` starts a fresh conversation after the active run finishes, `/status` reports progress, `/stop` stops the selected Agent's active run, and `/help` lists commands. Plain text resumes the selected Agent's waiting `ask_user` run.

The callback API is documented in [Feishu Agent Chat API](../../api-reference/endpoints/feishu-agent.md). Treat it as a Feishu provider callback, not a public application API.

## Configure WeChat features

Open **Site Settings → Integrations → WeChat iLink** and enable `agent_chat`, `knowledge_collection`, or both. Existing workers and Beat handle polling and processing; no receiver service or command is added. Fresh installations start with both features off. On first upgrade, active authorized personal connections preserve their current purposes as enabled platform features; subsequent administrator choices are not overwritten.

Users still authorize their own WeChat identity and select exactly one connection purpose in personal settings. Disabling a feature pauses its new intake, execution and replies without deleting personal credentials, history or pending records. Already-started operations may finish; re-enabling allows pending work to resume. Messages sent while polling is paused remain subject to WeChat's retention policy. See [Connect WeChat](../../user-guide/knowledge-base/wechat-collection.md).

Personal WeChat settings place authorization and refresh in the header, with compact connection cards and inline purpose actions. Configuration fields use two columns on wider screens and one on narrow screens. Hover over or focus the help icon beside the page title for usage guidance, or beside the image/video recognition model field for model guidance. The settings page does not display Agent activity or collection history; current Agent run status and stop controls remain on the connection card. Backend records are retained.



## Permissions

- `admin:integrations:login:read/update`: view/manage login integrations and the global SSO policy shown on **Site Settings → Security**.
- `admin:integrations:settings:read/update`: view/manage builtin email, Webhook, Feishu and WeChat feature settings, credentials, tests, synchronization, and Agent chat configuration.
- Either read domain permits access to the Integrations page and catalog. The instance list is filtered to the caller's domains; edit controls remain separate. Backend authorization is authoritative.
- Update authorization on the generic `PUT /api/v1/admin/integrations/{id}` is per field. `enabled_capabilities` and `is_enabled` are charged to the domain of the capabilities involved (`user_login` → login; Feishu `directory_sync`, `notification`, and `agent_chat` → settings). A builtin's `config` and `credentials` are charged to settings. Login-facing fields (`button_text`, `display_name`, `icon_url`, `login_config`, `attribute_mapping`) are charged to login whenever the integration type is login-capable. Feishu's specialized Agent-chat configuration API uses the settings domain; the app's existing login opt-in remains a separate login-domain capability.
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
3. In **Site Settings → Integrations → Feishu**, use the integration page's capability section and turn on **Feishu sign-in**, optionally setting the button text. Both capability switches (directory sync and sign-in) are saved together through the generic `PUT /api/v1/admin/integrations/{id}` as `enabled_capabilities`: opening the card requires the settings read domain, and changing the sign-in opt-in requires `admin:integrations:login:update`, so a role enabling it holds both domains (a superuser always can).
4. Save the app credentials on the same page if not configured yet. They are shared with directory sync; a blank secret field preserves the saved secret.

The login page advertises Feishu only when global SSO and the `user_login` feature are enabled. Disabling Feishu sign-in stops that feature without changing other enabled features; there is no integration master switch on this page.

The Feishu subject stored as the external identity `provider_user_id` is the profile `union_id`, falling back to `open_id` when `union_id` is absent, so replacing the app within the same developer account does not break existing connections.

A Feishu account whose directory record carries no email receives the same deterministic placeholder address the directory sync uses, `feishu-<sha256(user_id)>@accounts.clouisle.example`, so sign-in and sync converge on one local account instead of creating two. Deriving that address needs the Feishu `user_id`, which requires `contact:user.employee_id:readonly`; without that scope there is no `user_id` for such an account and its first sign-in is rejected rather than creating a placeholder identity.

### Link Feishu to an existing account

Sign in to the existing Clouisle account first. Open the avatar menu → **Profile → Account security → Connected Accounts**, then choose **Link Feishu**. Complete Feishu authorization in the same browser tab and confirm the binding. This keeps the current account, password, email, permissions, and login session; it does not create an account or use email matching.

The link action appears only when global SSO is enabled in **Site Settings → Security** and **Feishu sign-in** is enabled in **Site Settings → Integrations → Feishu**. It reuses the existing registered sign-in callback URL; no additional Feishu redirect URL is required. An identity linked to a different account is rejected rather than reassigned; ask an administrator to resolve an existing directory or account binding.

If the verified Feishu email already belongs to another local account, linking is also rejected even when the profile lacks a directory `user_id`. This is an ownership-conflict check, not automatic email matching or account merging.

Accounts linked through **Account security → Connected Accounts → Link Feishu** are excluded from directory synchronization. Their Feishu members count as skipped: sync does not create duplicate accounts, overwrite their local profile, or add department-team memberships. Existing memberships and the Feishu sign-in/bot link remain intact. Ordinary directory-managed users continue to sync. This ownership choice persists through later sign-ins and capability toggles. Upgrades recover prior manual links from retained successful `link_sso` audit events; records whose audit history was removed cannot be reliably classified retroactively.

The authenticated APIs are `GET /api/v1/sso/links/integrations`, `POST /api/v1/sso/links?provider_name=<name>` (returns an authorization URL and a short-lived session ID), and `POST /api/v1/sso/links/complete` with `{"session_id":"..."}`. The provider callback only stages the verified identity. Completion requires the original signed-in owner and consumes the session. The browser also checks its pending session before allowing confirmation.


## Synchronize Feishu knowledge

System superusers open **Site Settings → Integrations → Feishu** (`/site-settings/integrations/feishu`). The page has separate **Integration configuration**, **Directory sync**, **Notifications**, and **Feishu knowledge sync** tabs. Delegated integration permissions alone do not grant the knowledge tab or its API. Configure the Feishu app and the directory, sign-in, and notification capability switches in **Integration configuration**, where they share one save action; manage department scope and manual sync in **Directory sync**; check connectivity and send test messages in **Notifications**.

1. Save and enable the existing Feishu app integration. Knowledge sync reuses its app credentials and tenant access token; it does not use a signed-in user's token.
2. Grant Wiki space/node reads, Docx block reads, Sheets reads, Base table/field/record reads, document exports, and Drive file/media downloads as needed. File metadata uses `drive:drive.metadata:readonly` (or broader Drive access); media downloads require `docs:document.media:download` or the relevant document/Sheets/Base scope. Also grant resource access to the selected space and documents: API scopes alone are insufficient.
3. Create a destination knowledge base in the intended team. If no embedding model is explicitly selected, imports use the system default embedding model, just like ordinary document processing; that default must exist and be enabled. Add a source, select a visible Feishu space and destination, and choose a sync interval (1–43,200 minutes).
4. Enable automatic sync or run **Sync now**. Automatic dispatch requires Celery Beat and a worker consuming the `knowledge` queue. Inspect each source's status, last sync time, result counts, errors, and conversion warnings.

The sync page displays Wiki space names and records node titles in new error/warning results. Click a node title to open its Feishu original in a new tab. Historical results without titles display a clickable node ID instead; Feishu still enforces the viewer's original access permissions.

Unsupported source types and file formats are skipped, not failed. Their titles, original-document links, types, and reasons appear under **Skipped (unsupported)** (`last_result.skipped`); `unsupported` remains their count. A run with no actual failures is successful and clears `last_error`, even if it skips unsupported documents. Real read, conversion, or indexing errors still count as failures.

**Permission boundary:** this imports team knowledge; it does not mirror Feishu user ACLs. Local team/knowledge-base permissions control reading, retrieval, citations, and sharing after import. Confirm the destination audience before enabling sync. Revocation takes effect locally only when a subsequent sync detects it.

Supported source types:

| Source | Import behavior |
|---|---|
| Modern document (`docx`) | Rich text, headings, lists, code, quotes, todos, tables; authenticated image download and embedded attachment text extraction. Date reminders become text with a UTC event time, original millisecond timestamps, creator ID, and notification/all-day flags; they do not schedule local notifications. |
| Legacy document (`doc`) | Export to DOCX and parse through the existing document processor |
| Spreadsheet (`sheet`) | Read every grid worksheet in explicit row/column bands, preserving displayed values and source formulas |
| Base (`bitable`) | Read every accessible table, field definition, and paginated record; include attachment text/images where parseable |
| Drive file (`file`) | Download and parse PDF, DOC/DOCX, TXT, MD/Markdown, HTML/HTM, CSV, XLS/XLSX, JSON, and PPTX |
| Mindnote (`mindnote`) | Report unsupported: [Feishu's public API explicitly excludes Mindnote](https://open.feishu.cn/document/server-docs/docs/docs-overview). Export to a supported file and import that file instead. |

This is content ingestion, not a pixel-identical backup: Sheets floating images/charts and non-grid resources are not extracted; formulas are retained rather than calculated locally. Unsupported blocks, image/attachment formats, and extraction gaps produce warnings. Images remain local display assets, not OCR-derived searchable text. Downloads and generated content obey the configured knowledge-base upload limit; incomplete or oversized content fails without replacing the old version. Export failures (including partially unauthorized exports) are not promoted. Imported documents remain locally read-only, including chunk edits, deletion, and reprocessing.

Each run scans the whole space before removing missing documents. Content changes replace the local index after successful processing while preserving the document ID; unchanged content avoids re-embedding. Download, incomplete scan, or processing failures preserve the previous imported version. Confirmed access denial removes the affected local copy; transient or ambiguous errors do not count as deletion. Restored access permits reimport. Disabling a source stops synchronization but keeps imported documents; deleting a source removes its imported documents and indexes, not unrelated local uploads.

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
| POST | `/feishu/connection-check` | Validate saved app credentials by requesting a tenant token; no directory scope required |
| GET | `/feishu/test-recipients` | List up to 20 active local accounts linked to Feishu |
| POST | `/feishu/test-message` | Send a custom message to one explicitly selected linked account; requires Notifications capability |

See [SSO and Integrations API](../../api-reference/endpoints/sso.md) for request shapes. Both Feishu capability switches are saved through the generic `PUT /{id}` as `enabled_capabilities`, charged per capability that actually changes (sign-in on the login domain, directory sync on the settings domain), and the sign-in button text is a login-domain field. The `/feishu/*` endpoints stay on the settings domain and handle app credentials, department scope, directory sync, connection checks, and explicit single-recipient notification tests. Admin responses **never return credentials**, decrypted or encrypted. They expose only `credentials_configured` field names and `supported_capabilities`; do not treat a redacted response as a complete backup. Empty credential values preserve saved secrets. Secrets are Fernet-encrypted at rest.

The Feishu card exposes a connection check and a manual test-message form. A test message is sent only to the selected active account's existing Feishu binding; it does not broadcast and does not create a notification record.

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
- Feishu department browsing or sync reports that its feature is disabled: save the App ID and App Secret, then enable and save **Directory sync** in Integration configuration. No separate integration master switch is required.
- A `99991672` sync error lists the missing API scopes for the specific failed endpoint (for example, Bitable read permissions). Request those scopes under Feishu Open Platform → this app → Permissions, publish the app version, obtain administrator approval, and retry. Requirements differ by endpoint.
- Undecryptable credentials: restore the matching `SECRET_KEY` or re-save credentials using the relevant settings form.
- Cannot disconnect an identity: an account with no password cannot remove its only authentication method; establish another valid method first.
