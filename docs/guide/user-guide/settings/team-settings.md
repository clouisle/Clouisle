# Team Management

This guide explains the team management controls available in Clouisle. Teams group users and resources (agents, workflows, and knowledge bases).

> **Note:** Team slugs, visibility, invitation flows, join requests, member limits, per-team resource limits, per-team security/API settings, billing, data retention, custom domains, and branding are **not implemented**.

## Accessing Team Management

1. Open the platform **Team switcher**.
2. Choose **Manage Teams**.
3. The team management page opens at `/teams`.
4. Select a team to view its **Members** tab or, for authorized managers, its **Model Authorization** tab.

**Required Permission:** Team Admin or Owner (for editing and member/model management).

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

Team admins and owners can manage which enabled models the team may use:

1. Open **Manage Teams** (`/teams`) and select a team.
2. Open **Model Authorization**.
3. Choose **Authorize Model** and select an enabled model, or revoke an existing authorization.
4. Save the authorization change.

Authorized models become available for the team's agents and knowledge bases when their configuration requires a model.

## Member Management

Members must already have Clouisle accounts; there is no email-invitation or join-request flow.

### Adding Members

1. Open **Manage Teams** (`/teams`) and select a team.
2. Open the **Members** tab.
3. Click **Add Member**.
4. Choose an existing user and a role (Admin, Member, or Viewer — Owner cannot be assigned here).
5. Confirm.

Only the team Owner or Admin can add members. The Owner cannot add another member as Owner.
### Changing Member Roles

1. Find the member in the member list
2. Choose **"Change Role"**
3. Select the new role (Admin, Member, or Viewer)

Only the team Owner can change member roles (except for the Owner themselves).

### Removing Members

1. Find the member in the member list
2. Click **"Remove"**
3. Confirm

The Owner cannot be removed by other members.

### Leaving a Team

1. Open **Manage Teams** (`/teams`) and select the team.
2. Open **Members**.
3. Confirm

The Owner cannot leave until ownership is transferred.

### Transferring Ownership

1. Open **Manage Teams** (`/teams`) and select the team.
2. Open **Members**.
3. Confirm the transfer

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

**Last Updated**: 2026-02-11
