# Team Management

This guide explains the team management controls available in Clouisle. Teams group users and resources (agents, workflows, and knowledge bases).

> **Note:** Team slugs, visibility, invitation flows, join requests, member limits, per-team resource limits, per-team security/API settings, billing, data retention, custom domains, and branding are **not implemented**.

## Accessing Team Management

There are two separate surfaces:

1. **Manage the current team** — open the platform **Team switcher** and choose **Manage Current Team**. This opens `/app/team` for the team you are currently switched to, with **Members**, **Models** (read-only), and **Settings** tabs.
2. **Administrator team console** — the switcher's **Manage All Teams (Admin)** entry opens the administrator team list at `/teams`. That console requires the global `admin:team:read` permission; authorizing models there additionally requires `admin:model:update` (or superuser).

**Required Permission:** editing the current team on `/app/team` requires being that team's Owner or Admin; the `/teams` console requires the corresponding global `admin:*` permissions.

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
- Team API settings, API key policies, rate limits
- Billing / subscriptions / payment methods
- Data retention / export / deletion policies
- Audit alerts, custom domain, branding

## Related Documentation

- [Team Roles](../teams/team-roles.md) - Roles and permissions
- [Joining Teams](../teams/joining-teams.md) - Team membership
- [Team Collaboration](../teams/team-collaboration.md) - Working with teams

---

**Last Updated**: 2026-09-26
