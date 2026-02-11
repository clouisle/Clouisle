# Team Management

This guide explains how to manage teams in Clouisle as an administrator.

## Overview

Team management allows administrators to:

- **Create teams**: Set up new teams
- **Configure teams**: Update team settings
- **Manage members**: Add, remove, and assign roles
- **Monitor activity**: Track team usage and resources
- **Control access**: Set team permissions and policies
- **Delete teams**: Remove teams when needed

## Accessing Team Management

### From Admin Dashboard

**Steps:**

1. Log in as administrator
2. Go to **Admin** section
3. Click **"Teams"** in sidebar
4. View team management interface

**Or:**

- Navigate directly to `/admin/teams`

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
   - **Description**: Team description
   - **Owner**: Assign team owner
   - **Members**: Add initial members (optional)
   - **Settings**: Configure team settings
3. Click **"Create Team"**
4. Team is created

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
│ Owner: *                                │
│ [Search users...________] [Select]      │
│ Selected: Alice Johnson                 │
│                                         │
│ Initial Members: (optional)             │
│ [Search users...________] [+ Add]       │
│ • Bob Smith (Admin)      [Remove]       │
│ • Carol Davis (Member)   [Remove]       │
│                                         │
│ Settings:                               │
│ ☑ Allow members to invite others        │
│ ☑ Allow public join requests            │
│ ☐ Require admin approval for joins      │
│                                         │
│ Resource Limits:                        │
│ Max Agents: [100_____]                  │
│ Max Workflows: [50______]               │
│ Max Storage: [10 GB___]                 │
│                                         │
│ [Cancel]  [Create Team]                 │
│                                         │
└─────────────────────────────────────────┘
```

### Team Settings

**Configurable settings:**

| Setting | Description | Default |
|---------|-------------|---------|
| **Allow member invites** | Members can invite others | Enabled |
| **Public join requests** | Allow join requests | Disabled |
| **Require approval** | Admin approval for joins | Enabled |
| **Max agents** | Maximum number of agents | 100 |
| **Max workflows** | Maximum number of workflows | 50 |
| **Max storage** | Maximum storage (GB) | 10 |
| **Enable API keys** | Allow team API keys | Enabled |

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
│ Resources:                              │
│ • Agents: 23 / 100                     │
│ • Workflows: 15 / 50                   │
│ • Knowledge Bases: 8                   │
│ • Storage: 2.3 GB / 10 GB              │
│                                         │
│ Activity (Last 30 Days):                │
│ • Total Conversations: 1,234           │
│ • Workflow Executions: 456             │
│ • Documents Uploaded: 89               │
│ • API Calls: 12,345                    │
│                                         │
│ Settings:                               │
│ • Member Invites: ✅ Enabled            │
│ • Join Requests: ❌ Disabled            │
│ • API Keys: ✅ Enabled                  │
│                                         │
│ Created: 2026-01-15 10:00:00           │
│ Updated: 2026-02-11 15:30:00           │
│                                         │
│ [View Members] [View Resources]         │
│ [View Activity] [Delete Team]           │
│                                         │
└─────────────────────────────────────────┘
```

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
   - Settings
   - Resource limits
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
│ Settings:                               │
│ ☑ Allow members to invite others        │
│ ☑ Allow public join requests            │
│ ☐ Require admin approval for joins      │
│                                         │
│ Resource Limits:                        │
│ Max Agents: [100_____]                  │
│ Max Workflows: [50______]               │
│ Max Storage: [10 GB___]                 │
│                                         │
│ [Cancel]  [Save Changes]                │
│                                         │
└─────────────────────────────────────────┘
```

## Monitoring Teams

### Team Activity

**View team activity:**

1. Open team details
2. Click **"View Activity"** tab
3. See recent team actions

**Activity log:**
```
┌─────────────────────────────────────────┐
│ Team Activity - Marketing Team          │
├─────────────────────────────────────────┤
│                                         │
│ Today                                   │
│ ─────────────────────────────────────  │
│ 14:30 • Alice created agent            │
│ 12:15 • Bob ran workflow               │
│ 10:00 • Carol uploaded document        │
│                                         │
│ Yesterday                               │
│ ─────────────────────────────────────  │
│ 16:45 • David joined team              │
│ 14:20 • Alice updated agent            │
│ 09:30 • Bob created workflow           │
│                                         │
│ [Load More Activity] [Export]           │
│                                         │
└─────────────────────────────────────────┘
```

### Team Analytics

**View team analytics:**

1. Open team details
2. Click **"Analytics"** tab
3. View usage statistics

**Analytics dashboard:**
```
┌─────────────────────────────────────────┐
│ Team Analytics - Last 30 Days           │
├─────────────────────────────────────────┤
│                                         │
│ Usage Summary:                          │
│ • Total Conversations: 1,234           │
│ • Workflow Executions: 456             │
│ • Documents Uploaded: 89               │
│ • API Calls: 12,345                    │
│                                         │
│ Resource Usage:                         │
│ • Agents: 23 / 100 (23%)               │
│ • Workflows: 15 / 50 (30%)             │
│ • Storage: 2.3 GB / 10 GB (23%)        │
│                                         │
│ Top Contributors:                       │
│ 1. Alice Johnson - 456 actions         │
│ 2. Bob Smith - 234 actions             │
│ 3. Carol Davis - 123 actions           │
│                                         │
│ [View Detailed Report] [Export]         │
│                                         │
└─────────────────────────────────────────┘
```

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

**Perform actions on multiple teams:**

1. Select teams (checkboxes)
2. Click **"Bulk Actions"** dropdown
3. Choose action:
   - Export data
   - Update settings
   - Send announcement
4. Confirm action

**Bulk actions toolbar:**
```
┌─────────────────────────────────────────┐
│ 3 teams selected                        │
│ [Bulk Actions ▼] [Clear Selection]     │
│                                         │
│ • Export Team Data                      │
│ • Update Settings                       │
│ • Send Announcement                     │
│ • Generate Report                       │
└─────────────────────────────────────────┘
```

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
2. Verify owner is valid user
3. Check team limit not reached
4. Review error message
5. Contact support

### Cannot Add Member

**Problem**: Cannot add user to team

**Solutions:**
1. Check user exists
2. Verify user not already member
3. Check team member limit
4. Verify permissions
5. Try different role

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
- [Security Settings](../settings/security-settings.md) - Security configuration
- [Audit Logs](../audit-logs/viewing-logs.md) - Viewing audit logs

## Getting Help

If you need assistance with team management:

1. **Documentation**: Review this guide
2. **Admin Help**: Click **?** icon in admin interface
3. **Support**: Contact Clouisle support
4. **Community**: Visit community forums

---

**Last Updated**: 2026-02-11
