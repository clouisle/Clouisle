# External Notification Integrations

This note records the current boundary of outbound notification integrations. It does not cover identity-provider protocols, the Feishu integration, or other administrative connectors.

## Supported channels

- **Email** — SMTP delivery through the notification dispatcher.
- **Webhook** — administrator-configured HTTP delivery through the notification dispatcher.

Generic notification channels and delivery configuration live under **Admin → Site Settings → Integrations** and **Notifications** settings. Integration/channel identifiers are registered in `backend/app/integrations/factory.py`; adding a channel requires implementing its dispatch behavior and updating the channel schema/validation, not just adding an identifier.

## Directory sync is separate

Feishu directory synchronization is a separate administrator-managed feature, not a notification channel. It reads a selected department scope from Feishu and creates or updates local user accounts on manual request. It neither sends outbound notifications nor registers a Feishu notification channel. See [System Settings — Feishu Directory Sync](../../../guide/admin-guide/settings/system-settings.md#feishu-directory-sync) for app setup, account behavior, and the admin API routes.

The same Feishu integration also declares an opt-in `user_login` capability: when an administrator enables it, the one Feishu app (same app ID and app secret) also signs users in through the standard `/api/v1/sso/*` endpoints. That is a sign-in concern rather than a notification one — login sends no outbound notifications either — but both Feishu capabilities stay out of the notification surface described above.

## Security and account-linking invariants

- Store the app secret encrypted as an integration credential; never return the secret to the browser or include it in logs/audit records.
- Require `admin:integrations:settings:read` for configuration and department browsing; require `admin:integrations:settings:update` for saving or syncing. Enabling Feishu sign-in is a `user_login` opt-in written through the generic `PUT /api/v1/admin/integrations/{id}` and requires the login domain (`admin:integrations:login:update`).
- Match existing accounts using the stored Feishu user ID, not email. A matching email alone is not proof of identity.
- Assign the default local role and configured default team/role only when creating a new account; preserve existing local credentials and role/team memberships during repeat syncs.
- A Feishu departure, disabled account, or removal from the configured department scope never disables or deletes a Clouisle account automatically.
- Keep directory synchronization and the sign-in capability out of notification enums, schemas, factories, and delivery dispatch paths.

## Verification

Backend account synchronization behavior is covered by `backend/tests/services/test_feishu_directory.py`. Feishu HTTP request parameters, error surfacing, and displayability limits are covered by `backend/tests/services/test_feishu_client.py`; the administrator endpoint error mapping is covered by `backend/tests/api/test_admin_feishu.py`. Feishu web sign-in — authorization URL and PKCE defaults, callback identity, `union_id`/`open_id` fallback, the directory placeholder fallback, and failure surfacing — is covered by `backend/tests/test_sso_providers_feishu.py`. The startup rewrite of legacy placeholder addresses is covered by `backend/tests/test_init_data_routines.py`. Frontend integration-card configuration and permission behavior is covered by the site-settings integrations page tests.

Feishu failures must stay diagnosable: the client raises `FeishuAPIError` carrying a short, UI-displayable message (Feishu's own error code and message) plus a log-only `detail` with the raw response. Never place the app secret in either field.

## Placeholder email addresses

Accounts created without a Feishu email address get a deterministic placeholder (`feishu-<sha256 of user_id>@accounts.clouisle.example`). Two rules keep it safe:

- The domain must satisfy pydantic's `EmailStr`, which rejects RFC 2606/6761 special-use names such as `.invalid`; `.example` is reserved too but accepted. A rejected domain breaks every response model that serializes the user (`app.schemas.user.User`), returning HTTP 500 from the admin user list.
- Only the reserved domain is synthetic — the local part is derived from the Feishu user ID, so `sync_directory_users` can tell a placeholder from a real address (see `is_placeholder_email`) and replace it when Feishu starts returning an email.
