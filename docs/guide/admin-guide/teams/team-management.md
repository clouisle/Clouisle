# Team Management

This guide explains how to manage teams in Clouisle as an administrator.

## Overview

Team management allows administrators to:

- **Create teams**: Set up new teams
- **Configure teams**: Update team settings
- **Manage members**: Add, remove, and assign roles
- **Transfer ownership**: Hand over team ownership
- **Delete teams**: Remove teams when needed

## Accessing Team Management

### From Admin Dashboard

**Steps:**

1. Log in as administrator
2. Go to **Admin** section
3. Click **"Teams"** in sidebar
4. View team management interface

**Or:**

- Navigate directly to `/teams`

### Team List

**Team list view:**
```
┌─────────────────────────────────────────────────────┐
│ Teams (23)                     [+ Create Team] [⚙️]  │
├─────────────────────────────────────────────────────┤
│                                                     │
│ Search: [________________] [Filters ▼]              │
│                                                     │
│ 👥 Marketing Team                                   │
│    Members: 12 • Owner: Alice Johnson              │
│    Resources: 23 agents, 15 workflows, 8 KBs       │
│    Created: 2026-01-15                             │
│    [View] [Edit] [...]                             │
│                                                     │
│ 👥 Engineering Team                                 │
│    Members: 25 • Owner: Bob Smith                  │
│    Resources: 45 agents, 32 workflows, 15 KBs      │
│    Created: 2026-01-10                             │
│    [View] [Edit] [...]                             │
│                                                     │
│ 👥 Sales Team                                       │
│    Members: 8 • Owner: Carol Davis                 │
│    Resources: 12 agents, 8 workflows, 5 KBs        │
│    Created: 2026-02-01                             │
│    [View] [Edit] [...]                             │
│                                                     │
└─────────────────────────────────────────────────────┘
```

## Creating Teams

### Create New Team

**Steps:**

1. Click **"+ Create Team"** button
2. Fill in team information:
   - **Name**: Team name
   - **Description**: Team description (optional)
   - **Avatar URL**: Team avatar (optional)
3. Click **"Create Team"**
4. Team is created; you become its owner

**Create team form:**
```
┌─────────────────────────────────────────┐
│ Create Team                             │
├─────────────────────────────────────────┤
│                                         │
│ Team Name: *                            │
│ [Marketing Team__________]              │
│                                         │
│ Description:                            │
│ [Marketing and content creation team_]  │
│ [_________________________________]     │
│                                         │
│ Avatar URL: (optional)                  │
│ [https://example.com/team.png______]    │
│                                         │
│ [Cancel]  [Create Team]                 │
│                                         │
└─────────────────────────────────────────┘
```

> **Note:** Not implemented / Roadmap: assigning an owner at creation, adding initial members, invite/join settings, and resource limits are not part of team creation. Team members are added after creation via **Add Member**; ownership is transferred via **Transfer Ownership**.

## Viewing Team Details

### Team Overview

**View complete team information:**

1. Click on team in list
2. Team details panel opens
3. View all team information

**Team details:**
```
┌─────────────────────────────────────────┐
│ Marketing Team                   [Edit] │
├─────────────────────────────────────────┤
│                                         │
│ 👥 12 Members                           │
│    Owner: Alice Johnson                 │
│    Admins: 2 • Members: 8 • Viewers: 1  │
│                                         │
│ Created: 2026-01-15 10:00:00           │
│ Updated: 2026-02-11 15:30:00           │
│                                         │
│ [View Members] [View Resources]         │
│ [Delete Team]                           │
│                                         │
└─────────────────────────────────────────┘
```

> **Note:** Not implemented / Roadmap: resource quotas (agents/workflows/storage limits), usage activity (conversations, executions, API calls), and team settings (member invites, join requests, API keys) are not displayed or configurable. Teams have no limit or invite settings.

### Team Members

**View and manage team members:**

1. Open team details
2. Click **"View Members"** tab
3. See all team members

**Members list:**
```
┌─────────────────────────────────────────┐
│ Team Members (12)          [+ Add Member]│
├─────────────────────────────────────────┤
│                                         │
│ 👤 Alice Johnson (Owner)                │
│    alice@example.com                    │
│    Joined: 2026-01-15                  │
│    [View Profile] [Transfer Ownership]  │
│                                         │
│ 👤 Bob Smith (Admin)                    │
│    bob@example.com                      │
│    Joined: 2026-01-16                  │
│    [View Profile] [Change Role] [Remove]│
│                                         │
│ 👤 Carol Davis (Member)                 │
│    carol@example.com                    │
│    Joined: 2026-01-20                  │
│    [View Profile] [Change Role] [Remove]│
│                                         │
│ ... and 9 more                          │
│                                         │
└─────────────────────────────────────────┘
```

### Team Resources

**View team resources:**

1. Open team details
2. Click **"View Resources"** tab
3. See all team resources

**Resources view:**
```
┌─────────────────────────────────────────┐
│ Team Resources                          │
├─────────────────────────────────────────┤
│                                         │
│ Agents (23):                            │
│ • Customer Support Agent (Published)   │
│ • Content Writer (Published)           │
│ • Code Reviewer (Draft)                │
│ ... and 20 more                         │
│                                         │
│ Workflows (15):                         │
│ • Document Summarizer (Published)      │
│ • SEO Analysis (Published)             │
│ • Data Processing (Draft)              │
│ ... and 12 more                         │
│                                         │
│ Knowledge Bases (8):                    │
│ • Product Documentation (156 docs)     │
│ • Marketing Materials (89 docs)        │
│ • Internal Wiki (234 docs)             │
│ ... and 5 more                          │
│                                         │
└─────────────────────────────────────────┘
```

## Managing Team Members

### Adding Members

**Add new members to team:**

1. Open team details
2. Click **"+ Add Member"** button
3. Search for user
4. Select role
5. Click **"Add"**

**Add member dialog:**
```
┌─────────────────────────────────────────┐
│ Add Team Member                         │
├─────────────────────────────────────────┤
│                                         │
│ Search User:                            │
│ [david@example.com______] [Search]      │
│                                         │
│ Selected User:                          │
│ David Wilson                            │
│ david@example.com                       │
│                                         │
│ Role:                                   │
│ ○ Owner                                 │
│ ○ Admin                                 │
│ ● Member                                │
│ ○ Viewer                                │
│                                         │
│ ☑ Send invitation email                 │
│                                         │
│ [Cancel]  [Add Member]                  │
│                                         │
└─────────────────────────────────────────┘
```

### Changing Member Roles

**Update member role:**

1. Find member in list
2. Click **"Change Role"**
3. Select new role
4. Confirm change
5. Member role updated

**Change role dialog:**
```
┌─────────────────────────────────────────┐
│ Change Member Role                      │
├─────────────────────────────────────────┤
│                                         │
│ Member: Bob Smith                       │
│ Current Role: Admin                     │
│                                         │
│ New Role:                               │
│ ○ Owner                                 │
│ ○ Admin                                 │
│ ● Member                                │
│ ○ Viewer                                │
│                                         │
│ [Cancel]  [Change Role]                 │
│                                         │
└─────────────────────────────────────────┘
```

### Removing Members

**Remove member from team:**

1. Find member in list
2. Click **"Remove"** button
3. Confirm removal
4. Member is removed

**Remove confirmation:**
```
┌─────────────────────────────────────────┐
│ ⚠️ Remove Team Member?                  │
├─────────────────────────────────────────┤
│                                         │
│ Member: Bob Smith                       │
│ Role: Admin                             │
│                                         │
│ What happens:                           │
│ • Member loses access to team resources │
│ • Personal resources are preserved      │
│ • Can be re-added later                 │
│                                         │
│ [Cancel]  [Remove Member]               │
│                                         │
└─────────────────────────────────────────┘
```

### Transferring Ownership

**Transfer team ownership:**

1. Open team details
2. Find new owner in members list
3. Click **"Transfer Ownership"**
4. Confirm transfer
5. Ownership transferred

**Transfer confirmation:**
```
┌─────────────────────────────────────────┐
│ ⚠️ Transfer Team Ownership?             │
├─────────────────────────────────────────┤
│                                         │
│ Current Owner: Alice Johnson            │
│ New Owner: Bob Smith                    │
│                                         │
│ What happens:                           │
│ • Bob becomes team Owner                │
│ • Alice becomes team Admin              │
│ • Bob gains full team control           │
│ • This cannot be undone                 │
│                                         │
│ Type "TRANSFER" to confirm:             │
│ [________________]                      │
│                                         │
│ [Cancel]  [Transfer Ownership]          │
│                                         │
└─────────────────────────────────────────┘
```

## Editing Teams

### Update Team Information

**Steps:**

1. Open team details
2. Click **"Edit"** button
3. Update fields:
   - Name
   - Description
   - Avatar URL
4. Click **"Save Changes"**

**Edit team form:**
```
┌─────────────────────────────────────────┐
│ Edit Team - Marketing Team              │
├─────────────────────────────────────────┤
│                                         │
│ Team Name:                              │
│ [Marketing Team__________]              │
│                                         │
│ Description:                            │
│ [Marketing and content creation team_]  │
│ [_________________________________]     │
│                                         │
│ Avatar URL: (optional)                  │
│ [https://example.com/team.png______]    │
│                                         │
│ [Cancel]  [Save Changes]                │
│                                         │
└─────────────────────────────────────────┘
```

## Monitoring Teams

### Team Activity

> **Note:** Not implemented / Roadmap. There is no per-team activity log view or export.

### Team Analytics

> **Note:** Not implemented / Roadmap. There is no team analytics dashboard (usage summaries, resource usage, top contributors, detailed reports). Team-level usage is not tracked per team in the UI.

## Deleting Teams

### Delete Team

**Permanently delete team:**

1. Open team details
2. Click **"Delete Team"** button
3. Review what will be deleted
4. Type team name to confirm
5. Click **"Delete Permanently"**

**Delete confirmation:**
```
┌─────────────────────────────────────────┐
│ ⚠️ Delete Team Permanently?             │
├─────────────────────────────────────────┤
│                                         │
│ Team: Marketing Team                    │
│ Members: 12                             │
│                                         │
│ ⚠️ This action cannot be undone!        │
│                                         │
│ What will be deleted:                   │
│ • All team resources (23 agents)       │
│ • All workflows (15)                   │
│ • All knowledge bases (8)              │
│ • All team data                        │
│                                         │
│ What will be preserved:                 │
│ • Member accounts                      │
│ • Audit logs (for compliance)          │
│                                         │
│ Type team name to confirm:              │
│ [________________]                      │
│                                         │
│ [Cancel]  [Delete Permanently]          │
│                                         │
└─────────────────────────────────────────┘
```

## Bulk Operations

### Bulk Team Actions

**Perform bulk delete:**

1. Select teams (checkboxes)
2. Click **"Bulk Actions"** dropdown
3. Choose **Delete**
4. Confirm deletion (each team is deleted via `DELETE /api/v1/admin/teams/{team_id}`)

**Bulk actions toolbar:**
```
┌─────────────────────────────────────────┐
│ 3 teams selected                        │
│ [Bulk Actions ▼] [Clear Selection]     │
│                                         │
│ • Delete                                │
└─────────────────────────────────────────┘
```

> **Note:** Not implemented / Roadmap: bulk export, bulk settings updates, announcements, and reports are not available. Bulk delete is the only bulk action.

## Best Practices

### Team Organization

**✅ Do:**
- Use descriptive team names
- Set appropriate resource limits
- Assign clear ownership
- Document team purpose
- Review teams regularly
- Monitor team activity
- Set up proper permissions

**❌ Don't:**
- Create too many teams
- Use generic names
- Skip resource limits
- Forget to assign owner
- Ignore inactive teams
- Allow unlimited resources

### Member Management

**✅ Do:**
- Assign appropriate roles
- Review memberships regularly
- Remove inactive members
- Document role changes
- Communicate changes
- Train team owners

**❌ Don't:**
- Give everyone admin access
- Forget to remove members
- Skip role reviews
- Change roles without notice
- Ignore member requests

### Security

**✅ Do:**
- Enforce team policies
- Monitor team activity
- Review audit logs
- Set resource limits
- Control API key access
- Regular security audits

**❌ Don't:**
- Skip security reviews
- Ignore suspicious activity
- Allow unlimited access
- Forget to audit
- Share team credentials

## Troubleshooting

### Cannot Create Team

**Problem**: Team creation fails

**Solutions:**
1. Check team name is unique
2. Verify you have `admin:team:create` permission
3. Review error message
4. Contact support

### Cannot Add Member

**Problem**: Cannot add user to team

**Solutions:**
1. Check user exists
2. Verify user not already member
3. Verify permissions
4. Try different role

### Cannot Delete Team

**Problem**: Delete option disabled

**Solutions:**
1. Check if you have permission
2. Verify team has no dependencies
3. Transfer resources first
4. Contact support

## Related Documentation

- [User Management](../users/user-management.md) - Managing users
- [Team Roles](../../user-guide/teams/team-roles.md) - Understanding roles
- [System Settings](../settings/system-settings.md) - System configuration
- [Audit Logs](../audit-logs/audit-log-management.md) - Viewing audit logs

## Getting Help

If you need assistance with team management:

1. **Documentation**: Review this guide
2. **Admin Help**: Click **?** icon in admin interface
3. **Support**: Contact Clouisle support
4. **Community**: Visit community forums

---

**Last Updated**: 2026-02-11
