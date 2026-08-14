# Team Settings

This guide explains the team settings available in Clouisle.

## Overview

Team settings cover the team's basic information and member management. Teams in Clouisle are organizational units that group users and resources (agents, workflows, knowledge bases) together.

> **Note:** Team slugs, visibility, invitation flows, join requests, member limits, per-team resource limits, per-team security/API settings, billing, data retention, custom domains, and branding are **not implemented**. Team settings are limited to name, description, and avatar, plus member management.

## Accessing Team Settings

1. Open the team view (team selector)
2. Select **Team Settings**
3. Choose the settings section

**Required Permission:** Team Admin or Owner (for editing and member management).

## General Settings

### Team Information

Only three fields can be edited:

| Field | Description |
|-------|-------------|
| **Name** | Team display name (required) |
| **Description** | Optional description (max 500 chars) |
| **Avatar URL** | Optional avatar image URL |

**Example:**
```yaml
Name: Engineering Team
Description: Product engineering and development team
Avatar URL: https://example.com/team-avatar.png
```

> **Note:** There is no team slug — teams are identified by ID and referenced by name in the UI.

## Member Management

Members are added directly by user ID (the user must already have a Clouisle account). There is no email-invitation or join-request flow.

### Adding Members

**Steps:**

1. Open team settings → **Members**
2. Click **"Add Member"**
3. Enter the user's ID and choose a role (Admin, Member, or Viewer — Owner cannot be assigned via this action)
4. Confirm

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

1. Open team settings → **Members**
2. Click **"Leave Team"**
3. Confirm

The Owner cannot leave until ownership is transferred.

### Transferring Ownership

1. Open team settings → **Members**
2. Click **"Transfer Ownership"** next to a member
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
