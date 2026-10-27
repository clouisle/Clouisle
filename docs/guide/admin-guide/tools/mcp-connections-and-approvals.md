# MCP Connections and Approvals

This guide is for team administrators and operators who configure saved MCP
servers and review the identities and approvals used to call them. It covers
connections, OAuth, approvals, resources, prompts and live resource
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
| `selectable` | Defaults to the invoking user's personal account; authors may explicitly choose a fixed personal or team connection |

Connections have one scope:

| Scope | Owner | Notes |
|-------|-------|-------|
| `user` | Individual user | Isolated per team; only the owner can use it interactively |
| `team` | Team | Shared account; team membership is required |
| `site` | Site administrator | Global account; cannot be overridden by tool editors |

A tool that needs an identity but has no connection fails explicitly with a
configuration/login prompt. A selected account requiring authorization reports
reconnection instead of falling back to another account.

For an unbound personal/selectable tool, interactive calls and manual workflow
runs resolve the invoking user's connection in the consuming team: the explicit
default first, otherwise the sole non-revoked personal connection. Multiple
connections without a default require setting a default or selecting a fixed
connection. An inactive default or sole connection must be reconnected; no
other user, team account or different team is tried. MCP tool discovery uses
this same connection identity before the model can call the tools.

## Connecting an account

Users can prepare and review their own connections in the active team without
editing a tool: open your avatar menu → Settings → **Tool Connections**. The tab
lists every connection available to you in the active team with its tool, account
label, scope, default flag and status, and offers add, set-default,
re-authenticate and delete actions. Adding a connection starts from the tool, so
only tools that accept an identity are offered; declared fields and OAuth are
handled the same way as in a tool's connection manager. Switching teams in the app
changes the list; the dialog does not have its own team switcher.

1. Open the tool's connection manager and choose scope (`personal` or `team`;
   site scope is administrator-only).
2. Fill only the fields the tool declares. Values are write-only and encrypted;
   the API returns field names, an optional account label and a secret version.
3. Choose whether this is the default connection for that scope and service.
4. Rotate or remove secrets with `config_set` / `config_remove`; send
   `expected_secret_version` to avoid overwriting a concurrent change.

Revoking a connection is terminal. To use a different external account, create
a new connection; do not expect an old approval to transfer to it — approvals
are bound to the connection version.

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

## Connection bindings and shared execution

Agent tools and workflow tool nodes offer **Automatic (current user)** by
default for personal/selectable tools. This stores no author account: each
runner supplies their own connection. Authors need not configure an account
merely to attach the tool. Users add or authorize their account in the tool's
connection manager; multiple accounts need a default.

Selecting a concrete connection explicitly pins that external identity and
authorizes the saved definition to use it. No separate delegation step exists.
API-key, embed, channel and scheduled entrypoints require a fixed connection;
they never automatically adopt a background actor's personal default.

- Personal connections can only be selected by their owner; administrators
  cannot bind another user's personal account.
- Binding is validated when the Agent or workflow is created, updated,
  duplicated, restored from a version or imported from a package. Imported
  definitions drop environment-specific connection ids so they are chosen again.
- With a fixed connection, the binding belongs to the definition. Any user
  authorized to run that Agent or workflow (including a shared workflow,
  schedule, API key, channel or embed) uses the saved external identity.
- Execution re-checks that the connection still exists, is active, belongs to
  the consuming team and matches the tool. A revoked or unusable connection
  fails closed; it never falls back to another account.
- Callers cannot obtain credentials: connection secrets remain write-only for
  management and are never returned by run events or API responses.

Changing a fixed identity requires selecting another connection and a new
approval. Once a call is awaiting approval, changing the user's default does
not change the account or connection version bound to that execution.

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
resumable `next_cursor` except when a page was cut mid-page. Listing and other
direct capability-browser operations do not request tool-execution approval.
Authorization and connection identity checks still apply.

## Approvals

Tool-execution approval applies only to interactive Agent chat, never to tool
discovery, direct testing, workflows (including workflow Agent nodes), or
background entrypoints.

Enable **Require Confirmation** on the Agent's MCP server binding to confirm
every child call. To require approval for selected children, configure an exact
operation override such as `tool:delete_task` on the saved MCP definition. An
explicit child policy is evaluated during chat even when the Agent-wide switch
is off; an `allow` override cannot relax an enabled Agent confirmation switch.
An empty saved policy does not implicitly require approval.

Chat pauses before invoking the external tool and shows the approval card above
the composer. Approve to resume the original call once, or reject to cancel it.
Parameters, identity, connection version and tool definition are bound to the
approval. Rejection, expiry, revocation and stopped runs never become approvals.

MCP call names, inputs and results remain inside the expandable thought trace.
The active header does not cycle through MCP identifiers, and partial streamed
MCP names are not published as tool calls.

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
`Accept: text/event-stream`. Authorization and connection checks precede opening
the stream; this direct capability-browser operation does not request execution approval.

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
| `409 tool_connection_required` | Configure an account or sign in through the connection manager; background origins need a fixed connection |
| `409 tool_connection_default_required` (6403) | Multiple personal accounts without a default; set one or pin an account explicitly |
| `409 tool_connection_inactive` | Connection is revoked or requires re-authentication; reconnect before retrying |
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
