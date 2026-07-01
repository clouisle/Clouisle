# Team Roles

This guide explains the different roles and permissions in Clouisle teams.

## Overview

Team roles control what members can do within a team. They are separate from global system roles. Global roles provide system-wide capabilities; team roles are mirrored into team-scoped role assignments that apply only inside that team. Team roles do not grant admin dashboard (`admin:*`) permissions.

Understanding roles helps you:

- **Manage access**: Control who can do what
- **Delegate responsibilities**: Assign appropriate permissions
- **Maintain security**: Protect sensitive resources
- **Organize teams**: Structure team hierarchy
- **Audit activity**: Track who performed actions

## Role Types

### Role Hierarchy

```
Owner (highest permissions)
  ↓
Admin
  ↓
Member
  ↓
Viewer (lowest permissions)
```

### Role Comparison

### Team Management

| Permission | Owner | Admin | Member | Viewer |
|------------|-------|-------|--------|--------|
| Delete team | ✅ | ❌ | ❌ | ❌ |
| Update team settings | ✅ | ✅ | ❌ | ❌ |
| Transfer ownership | ✅ | ❌ | ❌ | ❌ |

### Member Management

| Permission | Owner | Admin | Member | Viewer |
|------------|-------|-------|--------|--------|
| Invite members | ✅ | ✅ | ❌ | ❌ |
| Remove members | ✅ | ✅ | ❌ | ❌ |
| Change member roles | ✅ | ❌ | ❌ | ❌ |

### Agents

| Permission | Owner | Admin | Member | Viewer |
|------------|-------|-------|--------|--------|
| Create agents | ✅ | ✅ | ✅ | ❌ |
| Save team agents | ✅ | ✅ | ✅ | ❌ |
| Delete agents | ✅ | ✅ | ❌ | ❌ |
| Chat with agents | ✅ | ✅ | ✅ | ✅ |

### Workflows

| Permission | Owner | Admin | Member | Viewer |
|------------|-------|-------|--------|--------|
| Create workflows | ✅ | ✅ | ✅ | ❌ |
| Save team workflows | ✅ | ✅ | ✅ | ❌ |
| Delete workflows | ✅ | ✅ | ❌ | ❌ |
| Run workflows | ✅ | ✅ | ✅ | ✅ |

### Tools & Skills

| Permission | Owner | Admin | Member | Viewer |
|------------|-------|-------|--------|--------|
| Create/edit/delete tools | ✅ | ✅ | ❌ | ❌ |
| Create/edit/delete skills | ✅ | ✅ | ❌ | ❌ |
| Execute approved tools | ✅ | ✅ | ✅ | ✅ |
| Execute approved skills | ✅ | ✅ | ✅ | ✅ |

### Knowledge Bases

| Permission | Owner | Admin | Member | Viewer |
|------------|-------|-------|--------|--------|
| Create knowledge bases | ✅ | ✅ | ✅ | ❌ |
| Upload documents | ✅ | ✅ | ✅ | ❌ |
| Update own documents | ✅ | ✅ | ✅ | ❌ |
| Update others' documents | ✅ | ✅ | ❌ | ❌ |
| Delete own documents | ✅ | ✅ | ✅ | ❌ |
| Delete others' documents | ✅ | ✅ | ❌ | ❌ |
| Search documents | ✅ | ✅ | ✅ | ✅ |

### API Keys

| Permission | Owner | Admin | Member | Viewer |
|------------|-------|-------|--------|--------|
| Create API keys | ✅ | ✅ | ✅ | ❌ |
| View own API keys | ✅ | ✅ | ✅ | ❌ |
| View all API keys | ✅ | ✅ | ❌ | ❌ |
| Revoke own API keys | ✅ | ✅ | ✅ | ❌ |
| Revoke others' API keys | ✅ | ✅ | ❌ | ❌ |

### Audit & Analytics

| Permission | Owner | Admin | Member | Viewer |
|------------|-------|-------|--------|--------|
| View team analytics | ✅ | ✅ | ❌ | ❌ |
| View audit logs | ✅ | ✅ | ❌ | ❌ |
| Export data | ✅ | ✅ | ❌ | ❌ |

## Scope Boundary

Team roles only apply inside the team where they are assigned. A team Admin can manage resources in that team, but does not gain admin dashboard permissions unless a global role separately grants `admin:*` permissions.

## Owner Role

### Responsibilities

**The Owner has complete control over the team:**

- Full administrative access
- Can delete the team
- Can transfer ownership
- Manages billing (if applicable)
- Final authority on all decisions

### Owner Permissions

**Exclusive permissions:**
- Delete team
- Transfer ownership to another member
- Access billing information
- Configure payment methods
- Manage subscription

**Shared with Admin:**
- Invite/remove members
- Update team settings
- View audit logs

### Owner Limitations

**Restrictions:**
- Only one owner per team
- Cannot leave team without transferring ownership
- Cannot be removed by others
- Cannot downgrade own role (must transfer first)

### Transferring Ownership

**Steps:**

1. Go to **Team Settings** → **Members**
2. Find member to transfer to
3. Click **"..."** menu
4. Select **"Transfer Ownership"**
5. Confirm transfer
6. You become Admin
7. New owner has full control

**Transfer confirmation:**
```
┌─────────────────────────────────────────┐
│ ⚠️ Transfer Ownership?                  │
├─────────────────────────────────────────┤
│                                         │
│ Transfer ownership to:                  │
│ Alice (alice@example.com)               │
│                                         │
│ What happens:                           │
│ • Alice becomes team Owner              │
│ • You become team Admin                 │
│ • Alice gains full control              │
│ • This cannot be undone                 │
│                                         │
│ Type "TRANSFER" to confirm:             │
│ [________________]                      │
│                                         │
│ [Cancel]  [Transfer Ownership]          │
│                                         │
└─────────────────────────────────────────┘
```

## Admin Role

### Responsibilities

**Admins help manage the team:**

- Manage team members
- Configure team settings
- Oversee resources
- Monitor team activity
- Support team members

### Admin Permissions

**Member management:**
- Invite new members
- Remove members (except Owner)
- Approve join requests
- View member activity

**Resource management:**
- Create/update/delete team resources allowed by team-scoped RBAC
- Manage agents, workflows, knowledge bases
- Configure resource settings
- Monitor resource usage

**Team settings:**
- Update team name and description
- Configure team preferences
- Manage integrations
- Set team policies

**Monitoring:**
- View team analytics
- Access audit logs
- Export team data
- Generate reports

### Admin Limitations

**Cannot:**
- Delete the team
- Transfer ownership
- Remove or demote Owner
- Access billing (unless Owner grants access)
- Change own role to Owner

## Member Role

### Responsibilities

**Members are regular team users:**

- Create and use resources
- Collaborate with team
- Manage own resources
- Follow team guidelines

### Member Permissions

**Resource creation:**
- Create agents
- Create workflows
- Create knowledge bases
- Upload documents
- Create API keys

**App collaboration:**
- Save team agents
- Save team workflows
- Use team agents and workflows

**Resource usage:**
- Chat with all team agents
- Run all team workflows
- Search all team knowledge bases
- Use team tools

**Own resource management:**
- Manage own API keys
- Update own knowledge base documents

**Safety boundary:**
- Creating, editing, or deleting tools requires team Owner/Admin because tools can call external systems or execute code
- Creating, editing, or deleting skills requires team Owner/Admin because skills can execute automation and affect shared runtime behavior

### Member Limitations

**Cannot:**
- Manage team settings
- Invite or remove members
- Change member roles
- Delete or publish agents and workflows
- Update others' resources
- Delete others' resources
- View audit logs
- Access team analytics

## Viewer Role

### Responsibilities

**Viewers have view/use-only access:**

- View team resources
- Use agents and workflows
- Search knowledge bases
- Monitor team activity

### Viewer Permissions

**Read access:**
- View all team agents
- View all team workflows
- View all team knowledge bases
- View team members

**Limited usage:**
- Chat with agents
- Run workflows
- Search documents
- Download documents (if permitted)

### Viewer Limitations

**Cannot:**
- Create any resources
- Update any resources
- Delete any resources
- Manage team settings
- Invite members
- Upload documents
- Create API keys

**Use case:**
- External consultants
- Temporary access
- Read-only auditors
- Stakeholders

## Default Team Role

When a default team is configured, new users can be added automatically as `viewer`, `member`, or `admin`. If no role is configured, the default is `member`. `owner` is never assigned automatically.

## Custom Roles (If Available)

### Creating Custom Roles

**If your organization supports custom roles:**

1. Go to **Team Settings** → **Roles**
2. Click **"Create Custom Role"**
3. Enter role name
4. Select permissions
5. Save role
6. Assign to members

**Custom role example:**
```
┌─────────────────────────────────────────┐
│ Create Custom Role                      │
├─────────────────────────────────────────┤
│                                         │
│ Role Name:                              │
│ [Content Creator___________]            │
│                                         │
│ Permissions:                            │
│ ☑ Create agents                         │
│ ☑ Update own agents                     │
│ ☑ Upload documents                      │
│ ☑ Update own documents                  │
│ ☐ Delete others' resources              │
│ ☐ Manage team settings                  │
│                                         │
│ [Cancel]  [Create Role]                 │
│                                         │
└─────────────────────────────────────────┘
```

## Changing Member Roles

### Assigning Roles

**Steps (Owner only):**

1. Go to **Team Settings** → **Members**
2. Find member
3. Click **"..."** menu
4. Select **"Change Role"**
5. Choose new role
6. Confirm change
7. Member is notified

**Role change:**
```
┌─────────────────────────────────────────┐
│ Change Role                             │
├─────────────────────────────────────────┤
│                                         │
│ Member: Bob (bob@example.com)           │
│ Current Role: Member                    │
│                                         │
│ New Role:                               │
│ ○ Owner                                 │
│ ● Admin                                 │
│ ○ Member                                │
│ ○ Viewer                                │
│                                         │
│ [Cancel]  [Change Role]                 │
│                                         │
└─────────────────────────────────────────┘
```

### Role Change Notification

**Member receives notification:**
```
📢 Your role has changed

Your role in "Marketing Team" has been changed from Member to Admin by Alice.

You now have additional permissions:
• Manage team members
• Update team settings
• View audit logs

[View New Permissions]
```

## Viewing Your Role

### Check Your Role

**View your current role:**

1. Go to team dashboard
2. Your role is displayed under team name
3. Or go to **Team Settings** → **Members**
4. Find yourself in member list

**Role display:**
```
┌─────────────────────────────────────────┐
│ Marketing Team                          │
│ Your Role: Member                       │
├─────────────────────────────────────────┤
│                                         │
│ What you can do:                        │
│ • Create agents and workflows           │
│ • Upload documents                      │
│ • Chat with team agents                 │
│ • Run team workflows                    │
│                                         │
│ [View Full Permissions]                 │
│                                         │
└─────────────────────────────────────────┘
```

### Permission Details

**View detailed permissions:**

1. Click **"View Full Permissions"**
2. See complete list of what you can do
3. Compare with other roles

## Best Practices

### Assigning Roles

**✅ Do:**
- Follow principle of least privilege
- Assign roles based on responsibilities
- Review roles regularly
- Document role assignments
- Communicate role changes
- Train members on their permissions

**❌ Don't:**
- Give everyone Admin access
- Assign Owner role unnecessarily
- Change roles without notice
- Forget to review permissions
- Ignore role-based security

### Role Management

**✅ Do:**
- Have at least 2 Admins
- Plan for Owner succession
- Document role responsibilities
- Review member roles quarterly
- Remove access when members leave
- Use Viewer role for external access

**❌ Don't:**
- Have only one Admin
- Keep inactive members as Admins
- Forget to update roles
- Give permanent Admin access
- Ignore role changes

### Security

**✅ Do:**
- Limit Owner and Admin roles
- Use Viewer role for view/use-only access
- Review audit logs regularly
- Monitor role changes
- Require approval for role changes
- Document role change reasons

**❌ Don't:**
- Share Owner credentials
- Allow unauthorized role changes
- Ignore suspicious activity
- Skip role reviews
- Forget to audit permissions

## Troubleshooting

### Cannot Perform Action

**Problem**: Action is disabled or fails

**Solutions:**
1. Check your current role
2. Verify required permissions
3. Contact team Admin/Owner
4. Request role change if needed
5. Check if resource is locked

### Role Change Not Applied

**Problem**: Role changed but permissions unchanged

**Solutions:**
1. Log out and log back in
2. Refresh the page
3. Clear browser cache
4. Check if change was saved
5. Contact administrator

### Cannot Change Role

**Problem**: Change role option is disabled

**Solutions:**
1. Verify you're Owner or Admin
2. Check if target is Owner (cannot change)
3. Verify member is still in team
4. Refresh the page
5. Contact administrator

### Lost Admin Access

**Problem**: Accidentally lost Admin permissions

**Solutions:**
1. Contact team Owner
2. Request role restoration
3. Explain what happened
4. Owner can restore your role
5. Contact administrator if Owner unavailable

## Related Documentation

- [Joining Teams](./joining-teams.md) - How to join teams
- [Team Collaboration](./team-collaboration.md) - Working with teams
- [Team Management](../../admin-guide/teams/team-management.md) - Admin guide
- [Permissions System](../../concepts/permissions.md) - Understanding permissions

## Getting Help

If you need assistance with team roles:

1. **Documentation**: Review this guide
2. **Team Owner/Admin**: Contact your team leadership
3. **Support**: Contact your organization's support team
4. **Administrator**: Reach out to your Clouisle administrator

---

**Last Updated**: 2026-02-11
