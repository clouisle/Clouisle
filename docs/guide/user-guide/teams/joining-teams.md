# Joining Teams

This guide explains how to join teams and collaborate with others in Clouisle.

## Overview

Teams in Clouisle allow you to:

- **Collaborate**: Work together with team members
- **Share resources**: Access shared agents, workflows, and knowledge bases
- **Organize work**: Group related projects and users
- **Control access**: Manage permissions and roles
- **Track activity**: Monitor team usage and activity

## Understanding Teams

### What are Teams?

Teams are organizational units that group users and resources together.

**Key concepts:**
- **Multi-tenancy**: Each team has isolated resources
- **Role-based access**: Different permission levels
- **Resource sharing**: Shared agents, workflows, KBs
- **Team ownership**: Each team has an owner

### Team Roles

| Role | Permissions |
|------|-------------|
| **Owner** | Full control, can delete team |
| **Admin** | Manage members, resources, settings |
| **Member** | Create and use resources |
| **Viewer** | Read-only access |

See [Team Roles](./team-roles.md) for detailed permissions.

## Joining Teams

### Via Invitation

**When invited to a team:**

1. You receive an email invitation
2. Click **"Accept Invitation"** link in email
3. Or log in to Clouisle
4. Go to **Notifications**
5. Find team invitation
6. Click **"Accept"** or **"Decline"**

**Email invitation:**
```
Subject: You've been invited to join "Marketing Team"

Hello John,

Alice has invited you to join the "Marketing Team" on Clouisle.

Team: Marketing Team
Role: Member
Invited by: Alice (alice@example.com)

[Accept Invitation] [Decline]

This invitation expires in 7 days.
```

**In-app notification:**
```
┌─────────────────────────────────────────┐
│ 👥 Team Invitation                      │
├─────────────────────────────────────────┤
│                                         │
│ Alice invited you to join:             │
│                                         │
│ Marketing Team                          │
│ Role: Member                            │
│                                         │
│ Team Description:                       │
│ Marketing and content creation team    │
│                                         │
│ Members: 12                             │
│ Resources: 23 agents, 15 workflows     │
│                                         │
│ [Accept] [Decline]                      │
│                                         │
└─────────────────────────────────────────┘
```

### Accepting Invitation

**Steps:**

1. Click **"Accept"** button
2. Review team information
3. Confirm acceptance
4. You're added to the team
5. Access team resources immediately

**Confirmation:**
```
┌─────────────────────────────────────────┐
│ ✅ Welcome to Marketing Team!           │
├─────────────────────────────────────────┤
│                                         │
│ You've successfully joined the team.   │
│                                         │
│ What you can do now:                   │
│ • Access shared agents                 │
│ • Use team workflows                   │
│ • Browse team knowledge bases          │
│ • Collaborate with 12 team members     │
│                                         │
│ [Go to Team Dashboard]                 │
│                                         │
└─────────────────────────────────────────┘
```

### Declining Invitation

**Steps:**

1. Click **"Decline"** button
2. Optionally provide reason
3. Confirm decline
4. Invitation is removed

**Note**: You can be re-invited later if needed.

### Invitation Expiration

**Invitations expire after:**
- Default: 7 days
- Configurable by administrator

**Expired invitation:**
```
⚠️ This invitation has expired.

Please contact the team owner to request a new invitation.
```

## Requesting to Join

### Public Teams

**If team allows join requests:**

1. Go to **Teams** section
2. Browse public teams
3. Find team you want to join
4. Click **"Request to Join"**
5. Provide reason (optional)
6. Submit request
7. Wait for approval

**Join request form:**
```
┌─────────────────────────────────────────┐
│ Request to Join Team                    │
├─────────────────────────────────────────┤
│                                         │
│ Team: Marketing Team                    │
│                                         │
│ Why do you want to join? (optional)    │
│ [I work in the marketing department_]   │
│ [and would like to collaborate with_]   │
│ [the team on content creation.______]   │
│                                         │
│ [Cancel]  [Send Request]                │
│                                         │
└─────────────────────────────────────────┘
```

**Request submitted:**
```
✅ Join request sent!

Your request to join "Marketing Team" has been sent to the team admins.

You'll be notified when your request is reviewed.
```

### Request Approval

**When your request is approved:**

1. You receive notification
2. You're automatically added to team
3. Access team resources

**Approval notification:**
```
✅ Join request approved!

Your request to join "Marketing Team" has been approved by Alice.

You can now access team resources.

[Go to Team Dashboard]
```

### Request Rejection

**If request is declined:**

1. You receive notification
2. Optionally includes reason
3. Can request again later

**Rejection notification:**
```
❌ Join request declined

Your request to join "Marketing Team" was declined.

Reason: Team is currently at capacity.

You can contact the team owner for more information.
```

## Switching Teams

### Viewing Your Teams

**Access your teams:**

1. Click **team selector** in navigation
2. View list of all your teams
3. Current team is highlighted

**Team selector:**
```
┌─────────────────────────────────────────┐
│ Your Teams                              │
├─────────────────────────────────────────┤
│                                         │
│ ● Marketing Team (current)              │
│   Role: Member • 12 members             │
│                                         │
│ ○ Engineering Team                      │
│   Role: Admin • 25 members              │
│                                         │
│ ○ Personal Workspace                    │
│   Role: Owner • 1 member                │
│                                         │
│ [+ Create Team]                         │
│                                         │
└─────────────────────────────────────────┘
```

### Switching Between Teams

**Steps:**

1. Click **team selector**
2. Select different team
3. Interface updates to show team resources
4. All actions now apply to selected team

**What changes:**
- Available agents
- Workflows
- Knowledge bases
- Team members
- Settings access

## Team Dashboard

### Accessing Dashboard

**Steps:**

1. Select team from team selector
2. Go to **Team** section
3. View team dashboard

**Or:**

- Navigate directly to `/teams/{team_id}`

### Dashboard Overview

**Dashboard sections:**

```
┌─────────────────────────────────────────────────────┐
│ Marketing Team                          [Settings]  │
├─────────────────────────────────────────────────────┤
│                                                     │
│ Overview                                            │
│ ─────────────────────────────────────────────────  │
│ Members: 12 • Agents: 23 • Workflows: 15           │
│ Knowledge Bases: 8 • Storage: 2.3 GB / 10 GB      │
│                                                     │
│ Recent Activity                                     │
│ ─────────────────────────────────────────────────  │
│ • Alice created "Content Writer" agent             │
│ • Bob ran "SEO Analysis" workflow                  │
│ • Carol uploaded document to "Marketing KB"        │
│                                                     │
│ Team Members                                        │
│ ─────────────────────────────────────────────────  │
│ 👤 Alice (Owner)                                    │
│ 👤 Bob (Admin)                                      │
│ 👤 Carol (Member)                                   │
│ 👤 You (Member)                                     │
│ ... and 8 more                                      │
│                                                     │
│ [View All Members] [View Resources]                │
│                                                     │
└─────────────────────────────────────────────────────┘
```

## Team Resources

### Accessing Resources

**Shared resources:**

1. **Agents**: Team agents available to all members
2. **Workflows**: Shared workflows
3. **Knowledge Bases**: Team knowledge bases
4. **API Keys**: Team API keys (if permitted)

**Resource access:**
- Based on your role
- Some resources may be restricted
- Owners/Admins have full access

### Using Team Resources

**Example - Using team agent:**

1. Go to **Agents** section
2. Filter by current team
3. Select agent
4. Start chatting
5. Agent has access to team knowledge bases

**Team resource indicator:**
```
┌─────────────────────────────────────────┐
│ 🤖 Content Writer                       │
│ Team: Marketing Team                    │
│ Created by: Alice                       │
│ Status: Published                       │
│                                         │
│ [Start Chat] [View Details]             │
└─────────────────────────────────────────┘
```

## Team Collaboration

### Working with Team Members

**Collaboration features:**

1. **Shared conversations**: Chat with team agents
2. **Workflow execution**: Run team workflows
3. **Document sharing**: Access team knowledge bases
4. **Activity feed**: See what team members are doing
5. **Mentions**: Tag team members in conversations

### Team Activity

**View team activity:**

1. Go to team dashboard
2. View **Recent Activity** section
3. See what team members are doing

**Activity types:**
- Agent created/updated
- Workflow executed
- Document uploaded
- Member joined/left
- Settings changed

## Leaving Teams

### Leave Team

**Steps:**

1. Go to team dashboard
2. Click **"..."** menu
3. Select **"Leave Team"**
4. Confirm leaving
5. You're removed from team

**Leave confirmation:**
```
┌─────────────────────────────────────────┐
│ ⚠️ Leave Team?                          │
├─────────────────────────────────────────┤
│                                         │
│ Are you sure you want to leave:        │
│                                         │
│ Marketing Team                          │
│                                         │
│ What happens:                           │
│ • You'll lose access to team resources │
│ • Your conversations will be preserved │
│ • You can be re-invited later          │
│                                         │
│ [Cancel]  [Leave Team]                  │
│                                         │
└─────────────────────────────────────────┘
```

**Note**: Team owners cannot leave until they transfer ownership.

### After Leaving

**What happens:**
- Lose access to team resources
- Your created resources remain (if any)
- Your conversations are preserved
- Can be re-invited later

## Personal Workspace

### Default Team

**Every user has a personal workspace:**

- Created automatically on signup
- You are the owner
- Private resources
- Cannot be deleted
- Cannot invite others (unless upgraded)

**Personal workspace:**
```
┌─────────────────────────────────────────┐
│ Personal Workspace                      │
├─────────────────────────────────────────┤
│                                         │
│ Your private workspace for personal    │
│ projects and experiments.              │
│                                         │
│ Members: 1 (you)                        │
│ Agents: 5                               │
│ Workflows: 3                            │
│ Knowledge Bases: 2                      │
│                                         │
└─────────────────────────────────────────┘
```

## Best Practices

### Joining Teams

**✅ Do:**
- Read team description before joining
- Understand your role and permissions
- Review team resources
- Introduce yourself to team
- Follow team guidelines
- Ask questions if unsure

**❌ Don't:**
- Join teams you don't need access to
- Accept invitations without reviewing
- Ignore team guidelines
- Request access without reason
- Leave teams without notice

### Team Collaboration

**✅ Do:**
- Communicate with team members
- Share useful resources
- Follow naming conventions
- Document your work
- Respect team resources
- Report issues promptly

**❌ Don't:**
- Modify others' resources without permission
- Delete shared resources
- Ignore team activity
- Work in isolation
- Forget to update team

## Troubleshooting

### Cannot Accept Invitation

**Problem**: Accept button is disabled or fails

**Solutions:**
1. Check if invitation expired
2. Verify you're logged in
3. Check if you're already a member
4. Refresh the page
5. Try different browser
6. Contact team owner

### Not Receiving Invitations

**Problem**: Invitation email not received

**Solutions:**
1. Check spam/junk folder
2. Verify email address is correct
3. Check email settings
4. Ask team owner to resend
5. Check in-app notifications
6. Contact administrator

### Cannot Switch Teams

**Problem**: Team selector not working

**Solutions:**
1. Refresh the page
2. Check if you're still a member
3. Verify team still exists
4. Clear browser cache
5. Try different browser
6. Contact administrator

### Lost Access to Team

**Problem**: Suddenly cannot access team resources

**Solutions:**
1. Check if you're still a member
2. Verify team wasn't deleted
3. Check if your role changed
4. Contact team owner/admin
5. Check notifications for removal notice
6. Contact administrator

## Related Documentation

- [Team Roles](./team-roles.md) - Understanding roles and permissions
- [Team Collaboration](./team-collaboration.md) - Working with teams
- [Creating Teams](../../admin-guide/teams/creating-teams.md) - Admin guide
- [Team Management](../../admin-guide/teams/team-management.md) - Admin guide

## Getting Help

If you need assistance with joining teams:

1. **Documentation**: Review this guide
2. **Team Owner**: Contact the team owner
3. **Support**: Contact your organization's support team
4. **Administrator**: Reach out to your Clouisle administrator

---

**Last Updated**: 2026-02-11
