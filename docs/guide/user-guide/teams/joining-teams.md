# Joining Teams

This guide explains how team membership works in Clouisle.

## Overview

Teams in Clouisle allow you to:

- **Collaborate**: Work together with team members
- **Share resources**: Access shared agents, workflows, and knowledge bases
- **Organize work**: Group related projects and users
- **Control access**: Manage permissions and roles

## Understanding Teams

### What are Teams?

Teams are organizational units that group users and resources together.

**Key concepts:**
- **Team isolation**: Each team's resources are scoped to that team
- **Role-based access**: Different permission levels (Owner, Admin, Member, Viewer)
- **Resource sharing**: Shared agents, workflows, KBs

### Team Roles

| Role | Permissions |
|------|-------------|
| **Owner** | Full control, can delete team, transfer ownership |
| **Admin** | Manage members, resources, settings |
| **Member** | Create and use resources |
| **Viewer** | Read-only access + chat/run |

See [Team Roles](./team-roles.md) for detailed permissions.

## How Users Join Teams

> **Note:** There is no email-invitation flow, no "Accept/Decline invitation" action, and no join-request/approval flow. Members are added directly by user ID.

### Ways to become a member

1. **Added by an Owner/Admin**: A team Owner or Admin adds you by your user ID and assigns a role (Admin, Member, or Viewer)
2. **Default team**: If the administrator configured a default team, newly registered users are automatically added to it with the configured role (default `member`)
3. **Created as owner**: The user who creates a team becomes its Owner

### Member Notifications

When you are added to a team, you receive a team notification (`team.member_added`), and the team is notified as well. There is no accept/decline action — membership is active immediately.

## Viewing Your Teams

### Access Your Teams

1. Use the **team selector** in the navigation
2. View the list of all your teams
3. The current team is highlighted

**Team selector:**
```
┌─────────────────────────────────────────┐
│ Your Teams                              │
├─────────────────────────────────────────┤
│                                         │
│ ● Marketing Team (current)              │
│   Role: Member                          │
│                                         │
│ ○ Engineering Team                      │
│   Role: Admin                           │
│                                         │
│ [+ Create Team]                         │
│                                         │
└─────────────────────────────────────────┘
```

### Switching Between Teams

1. Click the **team selector**
2. Select a different team
3. The interface updates to show that team's resources

## Team Dashboard

### Accessing the Team

1. Select the team from the team selector
2. Open the team section to view members and resources

### Team Overview

```
┌─────────────────────────────────────────────────────┐
│ Marketing Team                          [Settings]  │
├─────────────────────────────────────────────────────┤
│                                                     │
│ Members: 12 • Agents: 23 • Workflows: 15           │
│ Knowledge Bases: 8                                  │
│                                                     │
│ Team Members                                        │
│ ─────────────────────────────────────────────────  │
│ 👤 Alice (Owner)                                    │
│ 👤 Bob (Admin)                                      │
│ 👤 Carol (Member)                                   │
│ ...                                                 │
│                                                     │
└─────────────────────────────────────────────────────┘
```

## Team Resources

### Accessing Resources

**Shared resources:**

1. **Agents**: Team agents available to members
2. **Workflows**: Shared workflows
3. **Knowledge Bases**: Team knowledge bases

**Resource access:**
- Based on your role
- Owners/Admins have full access; Members can create/use; Viewers have read/use-only access

## Leaving Teams

### Leave Team

**Steps:**

1. Open the team (team selector or team view)
2. Select **"Leave Team"**
3. Confirm leaving
4. You're removed from the team

**Note**: The team Owner cannot leave until ownership is transferred (see [Team Settings](../settings/team-settings.md)).

### After Leaving

**What happens:**
- You lose access to team resources
- Your conversations are preserved

## Best Practices

### Team Membership

**✅ Do:**
- Understand your role and permissions
- Review team resources
- Keep your team memberships current

**❌ Don't:**
- Keep memberships in teams you no longer need

## Troubleshooting

### Cannot Access Team

**Problem**: Team not visible or accessible

**Solutions:**
1. Check if you're a member of the team (ask the Owner/Admin to add you)
2. Refresh the page
3. Contact the team Owner/Admin

### Cannot Switch Teams

**Problem**: Team selector not working

**Solutions:**
1. Refresh the page
2. Check if you're still a member
3. Clear browser cache

## Related Documentation

- [Team Roles](./team-roles.md) - Understanding roles and permissions
- [Team Collaboration](./team-collaboration.md) - Working with teams
- [Team Settings](../settings/team-settings.md) - Team configuration

## Getting Help

If you need assistance with team membership:

1. **Documentation**: Review this guide
2. **Team Owner/Admin**: Contact your team leadership
3. **Support**: Contact your organization's support team

---

**Last Updated**: 2026-02-11
