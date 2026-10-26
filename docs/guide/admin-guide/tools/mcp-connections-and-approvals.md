# MCP Connections and Approvals

This guide is for team administrators and operators who configure saved MCP
servers and review the identities and approvals used to call them. It covers
connections, delegation, OAuth, approvals, resources, prompts and live resource
subscriptions. For request/response fields, see the [Tools API](../../api-reference/endpoints/tools.md#saved-mcp-server-protocol).

## Saved servers, not client credentials

A saved MCP tool stores its transport, URL/command and header/environment
templates in the tool definition. When an agent, workflow or the tool panel uses
that server, the backend resolves a connection for the current identity and
injects only the declared fields. Callers select **which identity** to use;
they never send `mcp_config`, headers or credential values. Responses and run
events never contain secret values or the rendered server configuration.

The raw `POST /tools/mcp/list-tools` and its admin equivalent are scratch
diagnostics for unsaved definitions and are scheduled for removal from saved
tool dialogs. Use the saved-server endpoints (`/tools/{tool_id}/mcp/...`) for
anything already stored.

## Identity types

Each tool declares an identity policy:

| Policy | Meaning |
|--------|---------|
| `none` | No external identity; no connection is required or accepted |
| `team_only` | A team-scoped connection is used |
| `personal_only` | The acting user's personal connection is used |
| `selectable` | The caller must choose `personal` or `team` per request |

Connections have one scope:

| Scope | Owner | Notes |
|-------|-------|-------|
| `user` | Individual user | Isolated per team; only the owner can use it interactively |
| `team` | Team | Shared account; team membership is required |
| `site` | Site administrator | Global account; cannot be overridden by tool editors |

A tool that needs an identity but has no usable connection fails explicitly
(`tool_connection_required`, `tool_connection_inactive`) instead of falling back
to a team or global plaintext credential. A connection marked as default is used
only when the caller did not pin one and the entrypoint is interactive.

## Connecting an account

1. Open the tool's connection manager and choose scope (`personal` or `team`;
   site scope is administrator-only).
2. Fill only the fields the tool declares. Values are write-only and encrypted;
   the API returns field names, an optional account label and a secret version.
3. Choose whether this is the default connection for that scope and service.
4. Rotate or remove secrets with `config_set` / `config_remove`; send
   `expected_secret_version` to avoid overwriting a concurrent change.

Revoking a connection is terminal and also revokes its grants. To use a
different external account, create a new connection; do not expect an old
approval to transfer to it — approvals are bound to the connection version.

## MCP OAuth

If the server definition enables `mcp_config.oauth`, the connection must be
authorized before use:

1. `POST /tool-connections/{id}/oauth/start` returns an authorization URL and a
   one-time state. A client secret, when required, is write-only and requires
   tool write access.
2. The browser completes the provider flow and returns to the exact allowlisted
   frontend path; the callback exchanges the code.
3. `GET /tool-connections/{id}/oauth` shows authorization state, scopes and
   expiry without returning tokens.
4. Disconnecting clears local tokens and attempts provider revocation
   best-effort; remote failure is reported but never blocks the local revoke.

The flow uses PKCE S256, one-time state, exact callback matching, minimal scopes
and refresh rotation. Discovery and token endpoints follow the central SSRF
policy and HTTPS is required. An `invalid_grant` response marks the connection
`reauth_required`; the operator must run the flow again. Compliant providers
should work, but specific third-party interoperability is not claimed.

## Delegating a personal connection

Background or non-interactive entrypoints (agent runs, workflows, API keys,
schedules, channels, embeds) cannot prompt a user. The personal connection's
owner may grant one entrypoint explicit use:

- Entrypoint types: `agent`, `workflow`, `api_key`, `schedule`, `channel`,
  `embed`.
- `allowed_operations` lists exact operation keys such as `tool:query_orders`,
  `read:resource`, `prompt:summarize`, `list:tools`, or `*`.
- Grants can expire and are revoked with the connection or individually.

Administrators cannot delegate another user's personal account, and a team or
site connection cannot consume a personal grant. Changing the entrypoint owner
or the connection identity requires a new grant and approval.

## Using server capabilities

Saved MCP servers expose:

- **Tools**: call with arguments; results preserve content blocks, structured
  content and error state.
- **Resources**: list and read by URI. Treat resource text and links as
  untrusted context; links are not downloaded by the backend.
- **Resource templates**: listed separately; expand the URI and read it.
- **Prompts**: list and render with arguments. Preview messages; they are not
  system instructions automatically.
- **Completion**: complete prompt or template arguments under the same identity
  and approvals.
- **Subscriptions**: stream resource-change notifications for one URI.

Listing results are bounded, report `truncated`/`truncation_reason`, and expose a
resumable `next_cursor` except when a page was cut mid-page. Metadata defaults
to allowed even for tools whose operation default is deny; an explicit
`list:<kind>` override is honored, and site/team/entrypoint policy layers still
apply. Page size and cursor are part of the approval binding: after approving a
listing you cannot change page scope.

## Approvals

Policy is composed from site, team and entrypoint layers plus the tool's own
policy. `deny` wins, approval requirements union, and lower layers never relax a
higher layer. Gates can target:

- the caller (interactive entrypoints only; the caller must be a team member),
- specific users,
- team roles (self-approval only when explicitly allowed).

When an operation requires approval, the API returns a durable pending
reference instead of a result. Approve or reject in the approval inbox, then
repeat the same request with `execution_id`. Changing parameters, identity,
page scope, connection version or tool definition invalidates the request.
Decisions are idempotent and never edit bound parameters. Rejection, expiry,
revocation and stopped runs are terminal and never become approvals.

**Uncertain outcomes are not retried.** If an external side effect may have
happened but the outcome is unknown (crash, lost connection), the execution is
marked `outcome_unknown`. Check the external system and start a new request;
the platform never silently replays the call.

Server-initiated sampling and elicitation also wait for a human: only the
explicit audience can accept/decline, form content is schema-validated and may
not collect credentials, URL elicitation only allows configured hosts, and
losing the session marks the interaction `connection_lost` without replaying the
outer call.

## Resource subscriptions

Open `GET /tools/{tool_id}/mcp/resources/subscribe?team_id=…&uri=…` with
`Accept: text/event-stream`. Approval happens first: before approval the route
returns the normal JSON pending envelope, and replaying with `execution_id`
opens the stream.

- Events: `subscription_opened`, `resource_updated`, `subscription_closed`.
- Close reasons: `client_disconnected`, `ttl_expired`, `connection_lost`,
  `capability_unavailable`.
- The subscription is request-scoped. There is no background listener or durable
  subscription: disconnecting or restarting the process ends it, and updates
  are not replayed.
- At most 100 updates are queued; a slow client drops the oldest update.
- Lifetime is bounded by `MCP_SUBSCRIPTION_TTL_SECONDS` (default 300 s, max
  3600 s).

## Limits and operations

| Setting | Default | Range | Purpose |
|---------|---------|-------|---------|
| `MCP_SUBSCRIPTION_TTL_SECONDS` | 300 | 10–3600 | Maximum live subscription lifetime |
| `MCP_INTERACTION_TTL_SECONDS` | 300 | 10–900 | Maximum wait for sampling/elicitation and cap for the MCP callback window |

Server-side protocol budgets are fixed for callers: 10 s connect, 20 s metadata
listing/capabilities, 30 s resource read and prompt fetch. Tool calls use at
least 60 s and grow with the server's configured
`mcp_config.callback_timeout_seconds` (default 120 s, bounded by the interaction
TTL). Content limits default to 1,000,000 bytes per block and 4,000,000 bytes
total.

## Troubleshooting

| Symptom / code | Meaning |
|----------------|---------|
| `403 tool_access_denied` | No access to the consuming team, or a private tool cannot be shared |
| `403 tool_connection_required` | Tool needs an identity; no usable/default connection was resolved |
| `409 tool_connection_inactive` | Connection or grant is revoked/inactive |
| `409 tool_connection_grant_required` | A non-interactive entrypoint lacks a delegation grant |
| `409 mcp_capability_unavailable` | Server did not advertise the requested capability |
| `504 mcp_request_timeout` | Protocol budget expired |
| `413 mcp_content_too_large` | Resource/prompt/result exceeded byte budgets |
| `409 tool_execution_not_ready` | Pending execution was denied, expired, or already completed |
| `6504 tool_approval_not_authorized` | Caller is not in the gate's audience (caller gates require team membership) |
| `409 6510` | Approval policy is malformed; an administrator must fix it |
| `6434 tool_oauth_reauth_required` | OAuth tokens are no longer usable; run the authorization flow again |

## Related Documentation

- [Tools API](../../api-reference/endpoints/tools.md#saved-mcp-server-protocol) - Exact routes, DTOs and envelopes
- [Tools Guide](TOOLS.md) - Tool types and configuration
- [Tool Management](tool-management.md) - Administrator workflows
