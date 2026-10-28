# Team Management

This guide explains the team management controls available in Clouisle. Teams group users and resources (agents, workflows, and knowledge bases).

> **Note:** Team slugs, visibility, invitation flows, join requests, member limits, per-team resource limits, per-team security/API settings, billing, data retention, custom domains, and branding are **not implemented**.

## Accessing Team Management

There are two separate surfaces:

1. **Manage the current team** — open the platform **Team switcher** and choose **Manage Current Team**. This opens `/app/team` for the team you are currently switched to, with **Members**, **Models** (read-only), **Tool Approvals**, and **Settings** tabs.
2. **Administrator team console** — the switcher's **Manage All Teams (Admin)** entry opens the administrator team list at `/teams`. That console requires the global `admin:team:read` permission; authorizing models there additionally requires `admin:model:update` (or superuser).

**Required Permission:** editing team settings on `/app/team` requires being that team's Owner or Admin; the `/teams` console requires the corresponding global `admin:*` permissions. Tool approval policies follow the tool-edit permissions described under [Tool Approvals](#tool-approvals), so a Member can change a policy on their own tool.

## General Settings

### Team Information

Only three fields can be edited:

| Field | Description |
|-------|-------------|
| **Name** | Team display name (required) |
| **Description** | Optional description (max 500 chars) |
| **Avatar URL** | Optional avatar image URL |

> **Note:** There is no team slug — teams are identified by ID and referenced by name in the UI.

## Model Authorization

Model authorization is a **platform administrator** action, not a team-level one:

1. A platform administrator opens the administrator team console (**Manage All Teams (Admin)** → `/teams`) and selects the team.
2. The administrator authorizes, updates, or revokes models on the team's **Model Authorization** tab (requires the global `admin:model:update` permission or superuser).
3. Team admins, owners, and members see the result on the platform **Team** page: `/app/team` → **Models** shows the team's authorized models and quota usage **read-only**, with no authorize or revoke controls.

Authorized models become available for the team's agents and knowledge bases when their configuration requires a model.

## Tool Approvals

The **Tool Approvals** tab (`/app/team?tab=approvals`) is the central place to review and change the approval policy of every tool available to the current team. It edits each tool's own stored policy through the normal tool-update path. It does **not** create a team-level approval policy, and it does not affect workflows. It also does not change tool definitions, connections, credentials, or API keys; use the tool editor or the user's **Tool Connections** settings for those.

### What the tab lists

The tab lists the current team's built-in tool definitions, custom tools (HTTP or code), MCP tools, and tools shared into the team. A tool row shows its name, type and visibility (**Private**, **Team**, or **Shared**), its current default decision, and an **Edit policy** action. Use the search box to filter by display name or internal name.

| Badge | Meaning |
|-------|---------|
| **Private** | Visible only to its creator (and platform superusers) |
| **Team** | Visible to the whole team |
| **Shared** | Shared into this team by another team; read-only here |

Another member's private tool is never listed. Your own private tool is listed and can be edited by you.

### Who can change a policy

Opening and reading the tab requires membership in the current team plus the `tool:read` permission. Without that permission the tab shows a permission message and loads no tools.

Saving requires `tool:update` and the same write access used by the tool editor:

| Tool | Who can edit (`tool:update` required) |
|------|--------------|
| Private tool | Its creator (platform superusers can edit any tool) |
| Non-private team tool, including per-team built-in and MCP definitions | Its creator, or a team Owner/Admin |
| Tool shared into this team | Nobody in the receiving team; only the owning team or a platform superuser |

Viewers can read policies but cannot save changes. A read-only row states the reason instead of showing the edit action: shared tools show “Managed by the team that shared this tool” without revealing the owning team's name or id; other reasons are missing update permission, viewer role, private-tool ownership, or creator/team-admin restriction.

### What a policy controls

Each policy has one default decision:

| Decision | Effect |
|----------|--------|
| **Run without confirmation** | Allowed operations run immediately, subject to other access and security checks |
| **Always deny** | The operation is blocked; deny wins over allow |
| **Require caller confirmation** | The person who triggered the call must approve or reject it in the current conversation |

For MCP tools, and for any tool that already has saved overrides, the editor also supports per-operation overrides keyed by the exact internal operation name (for example `tool:search_issues`). An operation without an override inherits the default decision. Enter the exact name: the page does not connect to the MCP server to discover operations. **Inherit default** removes an override.

A legacy policy that still names specific users or team roles shows a **Legacy approvers** badge. Its editor lists the affected default and per-operation scopes, and saving stays blocked until you explicitly choose **Replace with caller confirmation**. That reset removes every saved user and team-role approver, including inside operation overrides, and cannot be undone. Legacy approvers are never converted silently, and they never act as an allow.

### Runtime boundaries

Approval remains caller-only. A signed-in user confirms their own Agent call; an Agent run started with an API key pauses for that same key, and no other key, teammate, or administrator can decide it. Follow-up chat and channel behavior is described in [MCP Connections and Approvals](../../admin-guide/tools/mcp-connections-and-approvals.md#approvals).

This page never adds an approval step for workflows: workflow tool calls, including API-key and nested workflow runs, do not create or wait for approval gates. Embed widgets, legacy channels, and scheduled entrypoints still fail closed when a tool requires confirmation instead of waiting.

Saving a policy counts as a tool definition change. Pending approvals bound to the previous definition can no longer run and fail closed rather than being approved.

Every policy change and every approval decision is recorded in the audit log. Decision entries include the actor, tool and execution identifiers, operation, entrypoint and outcome; policy-change entries include the tool, team, definition version, and before/after policy. Tool call parameters, credentials, and the reviewer's reason text are never recorded. See [Audit Log Management](../../admin-guide/audit-logs/audit-log-management.md#tool-approval-events).

## Member Management

Members must already have Clouisle accounts; there is no email-invitation or join-request flow.

### Adding Members

1. Open the current team's management page (**Team switcher** → **Manage Current Team**, `/app/team`).
2. Open the **Members** tab.
3. Click **Add Member**.
4. Enter the user's exact **username or email address** and choose a role (Admin, Member, or Viewer — Owner cannot be assigned here).
5. Confirm.

Only the team Owner or Admin can add members. The Owner cannot add another member as Owner.

### Changing Member Roles

1. Find the member in the member list
2. Choose **"Change Role"**
3. Select the new role (Admin, Member, or Viewer)

Only the team Owner can change member roles (except for the Owner themselves).

### Removing Members

1. Open `/app/team` → **Members** and find the member.
2. Choose **"Remove"**.
3. Confirm.

The Owner cannot be removed by other members.

### Leaving a Team

1. Open **Team switcher** → **Manage Current Team** (`/app/team`) and select the team.
2. Open **Members**.
3. Click **"Leave Team"** and confirm.

The Owner cannot leave until ownership is transferred.

### Transferring Ownership

1. Open **Team switcher** → **Manage Current Team** (`/app/team`) and open **Members**.
2. In the target member's **"..."** menu, choose **"Transfer Ownership"**.
3. Confirm in the dialog (**Cancel** / **Confirm**); it warns that you will lose owner privileges.

The previous owner becomes an Admin, and the new owner gains full control.

### Team Roles

Roles are fixed: **Owner**, **Admin**, **Member**, **Viewer**. There are no per-team custom roles. See [Team Roles](../teams/team-roles.md) for the full permission matrix.

## What Does NOT Exist

The following team-level features are **not implemented**:

- Team slug / custom URL
- Team visibility (private/internal/public) and discovery
- Invitation expiry, require-approval, allowed email domains
- Member limits
- Resource limits (agents, KBs, workflows, conversations)
- Per-team password/2FA/session/IP policies
- Team-level, site-level, or entrypoint approval policies (approval is configured per tool on the **Tool Approvals** tab)
- Workflow approval steps (workflow tool calls never wait for approval)
- Team API settings, API key policies, rate limits
- Billing / subscriptions / payment methods
- Data retention / export / deletion policies
- Audit alerts, custom domain, branding

## Related Documentation

- [Team Roles](../teams/team-roles.md) - Roles and permissions
- [Joining Teams](../teams/joining-teams.md) - Team membership
- [Team Collaboration](../teams/team-collaboration.md) - Working with teams

---

**Last Updated**: 2026-10-28
