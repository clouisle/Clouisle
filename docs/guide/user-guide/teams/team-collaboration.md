# Team Collaboration

This guide explains how to collaborate with team members in Clouisle.

## Overview

Team collaboration enables you to:

- **Share resources**: Use team agents, workflows, and knowledge bases
- **Coordinate workflows**: Run team workflows together
- **Track activity**: Review workflow execution history
- **Stay informed**: Receive team notifications

> **Note:** Shared conversations, @mentions, team activity feeds, document comments, and in-app team messaging are **not implemented**. Collaboration happens through shared resources and team notifications.

## Shared Resources

### Accessing Team Resources

**Team resources are shared among members:**

1. **Agents**: Team agents available to members
2. **Workflows**: Shared workflows
3. **Knowledge Bases**: Team document repositories

**Resource visibility:**
```
┌─────────────────────────────────────────┐
│ Resources                    [Team ▼]   │
├─────────────────────────────────────────┤
│                                         │
│ 🤖 Agents (23)                          │
│    • Customer Support Agent (Team)     │
│    • Content Writer (Team)             │
│                                         │
│ ⚙️ Workflows (15)                       │
│    • Document Summarizer (Team)        │
│    • SEO Analysis (Team)               │
│                                         │
│ 📚 Knowledge Bases (8)                  │
│    • Product Documentation (Team)      │
│                                         │
└─────────────────────────────────────────┘
```

### Using Team Agents

1. Go to **Agents** section
2. Filter by the current team
3. Select a team agent
4. Start chatting
5. The agent can use only knowledge bases attached in its configuration

### Running Team Workflows

1. Go to **Workflows** section
2. Select a team workflow
3. Click **"Run"**
4. Provide inputs
5. Monitor the execution
6. View results

**Workflow execution history:**
- All team members can view the execution history (subject to role permissions)
- See who ran workflows and when
- Access execution results and node details

### Accessing Team Knowledge Bases

1. Go to **Knowledge Bases** section
2. Select a team knowledge base
3. Browse or search documents
4. View and download documents (permissions apply)

**Permissions:**
- View/search: Members and above (Viewer too)
- Upload: Members and above
- Delete: Members and above (role-based)

## Team Notifications

Team-related automatic notifications are delivered to the in-app notification center:

| Type | When |
|------|------|
| `team.member_added` | A member is added (notifies the new member and the team) |
| `team.member_removed` | A member is removed |
| `team.role_changed` | A member's role changes |
| `team.ownership_transferred` | Ownership is transferred |
| `team.model_granted` / `team.model_revoked` | Team model access changes |

These are global auto-notifications; delivery channels are configured by administrators (see [Notification Preferences](../settings/notification-preferences.md)).

> **Note:** There is no per-team notification configuration and no mention-based notifications.

## Collaborative Workflows

### Workflow Collaboration

**Work together on workflows:**

1. **Design**: Members with permission can edit workflows
2. **Test**: Run and debug together
3. **Execute**: Members can run workflows
4. **Monitor**: View the execution history
5. **Improve**: Iterate based on results

### Workflow Execution Tracking

**Monitor team workflow executions:**

1. Go to the workflow and open **Logs** (`/app/apps/workflow/{id}/logs`)
2. See the team's executions
3. Filter by status or date, or search by run ID
4. View execution details and node executions

**Execution history:**
```
┌─────────────────────────────────────────┐
│ Workflow Execution History              │
├─────────────────────────────────────────┤
│                                         │
│ ✅ Run #156 - Alice                     │
│    Completed • 1m 23s • 2 hours ago    │
│                                         │
│ ❌ Run #154 - Carol                     │
│    Failed • 0m 45s • Yesterday         │
│                                         │
└─────────────────────────────────────────┘
```

## Best Practices

### Effective Collaboration

**✅ Do:**
- Use descriptive names for shared resources
- Keep resources organized
- Document resource purpose
- Keep the team informed via notifications

**❌ Don't:**
- Create duplicate resources
- Delete shared resources without discussion

### Resource Management

**✅ Do:**
- Use descriptive names for resources
- Add clear descriptions
- Keep resources organized

**❌ Don't:**
- Create duplicate resources
- Hoard resources

## Troubleshooting

### Cannot Access Team Resource

**Problem**: Resource not visible or accessible

**Solutions:**
1. Check if you're in the correct team
2. Verify the resource is published
3. Check your role permissions
4. Refresh the page
5. Contact the team admin

### Not Receiving Team Notifications

**Problem**: No team notifications

**Solutions:**
1. Verify you're a member of the team
2. Check the notification center at `/app/notifications`
3. Ask the administrator whether the auto-notification type is enabled
4. Refresh the page

## Related Documentation

- [Joining Teams](./joining-teams.md) - How team membership works
- [Team Roles](./team-roles.md) - Understanding roles
- [Chatting with Agents](../chat/chatting-with-agents.md) - Chat features
- [Workflow History](../workflows/workflow-history.md) - Workflow tracking

## Getting Help

If you need assistance with team collaboration:

1. **Documentation**: Review this guide
2. **Team Members**: Ask your team members
3. **Team Admin**: Contact your team admin
4. **Administrator**: Reach out to your Clouisle administrator

---

**Last Updated**: 2026-02-11
