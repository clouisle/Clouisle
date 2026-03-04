# Team Collaboration

This guide explains how to collaborate effectively with team members in Clouisle.

## Overview

Team collaboration enables you to:

- **Work together**: Collaborate on shared resources
- **Share knowledge**: Access team knowledge bases
- **Coordinate workflows**: Run team workflows together
- **Communicate**: Mention and notify team members
- **Track activity**: Monitor team progress
- **Organize work**: Structure team projects

## Shared Resources

### Accessing Team Resources

**Team resources are shared among all members:**

1. **Agents**: Team agents available to all
2. **Workflows**: Shared workflows
3. **Knowledge Bases**: Team document repositories
4. **Conversations**: Shared chat conversations
5. **API Keys**: Team API keys (if permitted)

**Resource visibility:**
```
┌─────────────────────────────────────────┐
│ Resources                    [Team ▼]   │
├─────────────────────────────────────────┤
│                                         │
│ 🤖 Agents (23)                          │
│    • Customer Support Agent (Team)     │
│    • Content Writer (Team)             │
│    • My Personal Agent (Personal)      │
│                                         │
│ ⚙️ Workflows (15)                       │
│    • Document Summarizer (Team)        │
│    • SEO Analysis (Team)               │
│                                         │
│ 📚 Knowledge Bases (8)                  │
│    • Product Documentation (Team)      │
│    • Marketing Materials (Team)        │
│                                         │
└─────────────────────────────────────────┘
```

### Using Team Agents

**Chat with team agents:**

1. Go to **Agents** section
2. Filter by current team
3. Select team agent
4. Start chatting
5. Agent has access to team knowledge bases

**Team agent indicator:**
```
┌─────────────────────────────────────────┐
│ 🤖 Customer Support Agent               │
│ Team: Marketing Team                    │
│ Created by: Alice                       │
│ Status: Published                       │
│                                         │
│ This agent helps with customer support │
│ inquiries and has access to our        │
│ product documentation.                  │
│                                         │
│ [Start Chat] [View Details]             │
└─────────────────────────────────────────┘
```

### Running Team Workflows

**Execute team workflows:**

1. Go to **Workflows** section
2. Select team workflow
3. Click **"Run"**
4. Provide inputs
5. Monitor execution
6. View results

**Workflow execution history:**
- All team members can view execution history
- See who ran workflows and when
- Access execution results
- Replay previous runs

### Accessing Team Knowledge Bases

**Browse team documents:**

1. Go to **Knowledge Bases** section
2. Select team knowledge base
3. Browse or search documents
4. View and download documents
5. Upload new documents (if permitted)

**Permissions:**
- View: All team members
- Upload: Members and above
- Delete: Admins and Owners

## Shared Conversations

### Creating Shared Conversations

**Share conversations with team:**

1. Open a conversation
2. Click **"Share"** button
3. Select team members
4. Choose permission level:
   - **View**: Read-only
   - **Comment**: Can add comments
   - **Edit**: Can send messages
5. Click **"Share"**

**Share dialog:**
```
┌─────────────────────────────────────────┐
│ Share Conversation                      │
├─────────────────────────────────────────┤
│                                         │
│ Share with:                             │
│ [Search team members...________]        │
│                                         │
│ Selected Members:                       │
│ • Alice (Edit)           [Remove]       │
│ • Bob (View)             [Remove]       │
│                                         │
│ Or share with entire team:              │
│ ☐ Share with all team members           │
│                                         │
│ Permissions:                            │
│ ○ View only                             │
│ ○ Can comment                           │
│ ● Can edit (send messages)              │
│                                         │
│ [Cancel]  [Share]                       │
│                                         │
└─────────────────────────────────────────┘
```

### Collaborating in Conversations

**Real-time collaboration:**

- See who's viewing the conversation
- Typing indicators show who's typing
- Messages appear in real-time
- Notifications for new messages

**Collaboration features:**
```
┌─────────────────────────────────────────┐
│ Product Analysis                 [👥 3] │
├─────────────────────────────────────────┤
│                                         │
│ You: Can you analyze this data?         │
│ 10:00 AM                                │
│                                         │
│ Agent: Sure! Here's my analysis...      │
│ 10:01 AM                                │
│                                         │
│ Alice: Great insights! Can we also...   │
│ 10:02 AM                                │
│                                         │
│ Bob is typing...                        │
│                                         │
│ [Type your message...___________] [Send]│
│                                         │
└─────────────────────────────────────────┘
```

## Mentions and Notifications

### Mentioning Team Members

**Tag team members in conversations:**

1. Type `@` in message
2. Select team member from list
3. Member receives notification
4. Member can click to view conversation

**Mention syntax:**
```
@alice Can you review this analysis?

@bob @carol Please check the workflow results
```

**Mention notification:**
```
📢 Alice mentioned you

In conversation: Product Analysis

"@alice Can you review this analysis?"

[View Conversation]
```

### Notification Settings

**Configure team notifications:**

1. Go to **Profile Settings** → **Notifications**
2. Configure team notification preferences:
   - Mentions
   - Team updates
   - Resource changes
   - Workflow completions
3. Save settings

**Team notification options:**
```
┌─────────────────────────────────────────┐
│ Team Notifications                      │
├─────────────────────────────────────────┤
│                                         │
│ ☑ Mentions in conversations             │
│ ☑ Team member joins/leaves              │
│ ☑ New team resources                    │
│ ☑ Workflow completions                  │
│ ☑ Document uploads                      │
│ ☐ All team activity                     │
│                                         │
│ Frequency:                              │
│ ● Real-time                             │
│ ○ Hourly digest                         │
│ ○ Daily digest                          │
│                                         │
│ [Save Preferences]                      │
│                                         │
└─────────────────────────────────────────┘
```

## Team Activity Feed

### Viewing Team Activity

**Monitor team activity:**

1. Go to team dashboard
2. View **Activity Feed** section
3. See recent team actions

**Activity feed:**
```
┌─────────────────────────────────────────┐
│ Team Activity                           │
├─────────────────────────────────────────┤
│                                         │
│ Today                                   │
│ ─────────────────────────────────────  │
│ 🤖 Alice created "Content Writer" agent │
│    2 hours ago                          │
│                                         │
│ ⚙️ Bob ran "SEO Analysis" workflow      │
│    3 hours ago                          │
│                                         │
│ 📄 Carol uploaded "Q3 Report.pdf"       │
│    5 hours ago                          │
│                                         │
│ Yesterday                               │
│ ─────────────────────────────────────  │
│ 👤 David joined the team                │
│    Yesterday at 2:30 PM                 │
│                                         │
│ 🤖 Alice updated "Support Agent"        │
│    Yesterday at 10:00 AM                │
│                                         │
│ [Load More Activity]                    │
│                                         │
└─────────────────────────────────────────┘
```

### Activity Types

**Tracked activities:**

| Activity | Description |
|----------|-------------|
| **Agent** | Created, updated, deleted, published |
| **Workflow** | Created, updated, executed, deleted |
| **Document** | Uploaded, updated, deleted |
| **Member** | Joined, left, role changed |
| **Team** | Settings updated, name changed |
| **Conversation** | Shared, unshared |

### Filtering Activity

**Filter activity feed:**

1. Click **"Filters"** button
2. Select activity types
3. Select date range
4. Select team members
5. Apply filters

**Filter options:**
```
┌─────────────────────────────────────────┐
│ Activity Filters                        │
├─────────────────────────────────────────┤
│                                         │
│ Activity Type:                          │
│ ☑ Agents                                │
│ ☑ Workflows                             │
│ ☑ Documents                             │
│ ☑ Members                               │
│ ☐ Settings                              │
│                                         │
│ Date Range:                             │
│ ● Today                                 │
│ ○ Last 7 days                           │
│ ○ Last 30 days                          │
│ ○ Custom                                │
│                                         │
│ Team Members:                           │
│ ☑ All members                           │
│ ☐ Specific members                      │
│                                         │
│ [Clear]  [Apply]                        │
│                                         │
└─────────────────────────────────────────┘
```

## Collaborative Workflows

### Workflow Collaboration

**Work together on workflows:**

1. **Design**: Multiple members can edit workflow
2. **Test**: Run and debug together
3. **Execute**: Any member can run workflow
4. **Monitor**: View execution history
5. **Improve**: Iterate based on results

**Workflow collaboration features:**
- Real-time editing (if supported)
- Version history
- Execution history
- Comments and notes
- Shared results

### Workflow Execution Tracking

**Monitor team workflow executions:**

1. Go to workflow
2. View **History** tab
3. See all team executions
4. Filter by team member
5. View execution details

**Execution history:**
```
┌─────────────────────────────────────────┐
│ Workflow Execution History              │
├─────────────────────────────────────────┤
│                                         │
│ ✅ Run #156 - Alice                     │
│    Completed • 1m 23s • 2 hours ago    │
│                                         │
│ ✅ Run #155 - Bob                       │
│    Completed • 2m 10s • 5 hours ago    │
│                                         │
│ ❌ Run #154 - Carol                     │
│    Failed • 0m 45s • Yesterday         │
│                                         │
│ ✅ Run #153 - You                       │
│    Completed • 1m 45s • 2 days ago     │
│                                         │
└─────────────────────────────────────────┘
```

## Document Collaboration

### Collaborative Document Management

**Work together on documents:**

1. **Upload**: Any member can upload
2. **Organize**: Categorize and tag together
3. **Search**: Everyone can search
4. **Update**: Update metadata collaboratively
5. **Review**: Review and approve documents

### Document Comments

**Add comments to documents:**

1. Open document
2. Click **"Add Comment"** button
3. Enter comment
4. Mention team members if needed
5. Submit comment

**Document comments:**
```
┌─────────────────────────────────────────┐
│ Sales Report Q3 2026.pdf                │
├─────────────────────────────────────────┤
│                                         │
│ Comments (3)                            │
│ ─────────────────────────────────────  │
│                                         │
│ Alice • 2 hours ago                     │
│ Great analysis! @bob can you review    │
│ the revenue projections?               │
│                                         │
│ Bob • 1 hour ago                        │
│ Looks good. I'll add more details      │
│ about Q4 forecast.                     │
│                                         │
│ You • 30 minutes ago                    │
│ Thanks everyone! Let's discuss in      │
│ tomorrow's meeting.                    │
│                                         │
│ [Add Comment...___________] [Post]      │
│                                         │
└─────────────────────────────────────────┘
```

## Team Communication

### In-App Messaging

**Direct messages with team members:**

1. Click on team member
2. Select **"Send Message"**
3. Type message
4. Send

**Note**: Some organizations may use external chat tools (Slack, Teams).

### Team Announcements

**Important team updates:**

1. Admins/Owners can post announcements
2. Announcements appear in team dashboard
3. All members receive notifications

**Announcement:**
```
┌─────────────────────────────────────────┐
│ 📢 Team Announcement                    │
├─────────────────────────────────────────┤
│                                         │
│ Posted by: Alice (Owner)                │
│ Date: 2026-02-11 10:00 AM               │
│                                         │
│ Team Meeting Tomorrow                   │
│                                         │
│ We'll have a team meeting tomorrow at  │
│ 2 PM to discuss Q1 goals and review    │
│ our progress on the content strategy.  │
│                                         │
│ Please review the Q4 report before     │
│ the meeting.                           │
│                                         │
│ [Acknowledge] [Add to Calendar]         │
│                                         │
└─────────────────────────────────────────┘
```

## Best Practices

### Effective Collaboration

**✅ Do:**
- Communicate clearly with team
- Use mentions to notify relevant members
- Share useful resources
- Document your work
- Provide context in conversations
- Respond to mentions promptly
- Keep team informed of progress

**❌ Don't:**
- Work in isolation
- Ignore team notifications
- Forget to share important findings
- Modify others' work without discussion
- Delete shared resources without notice
- Spam team with unnecessary notifications

### Resource Management

**✅ Do:**
- Use descriptive names for resources
- Add clear descriptions
- Tag resources appropriately
- Keep resources organized
- Archive old resources
- Document resource purpose

**❌ Don't:**
- Create duplicate resources
- Use generic names
- Leave resources undocumented
- Forget to clean up
- Hoard resources

### Communication

**✅ Do:**
- Be clear and concise
- Use mentions appropriately
- Respond in timely manner
- Provide context
- Ask questions when unsure
- Share knowledge

**❌ Don't:**
- Overuse mentions
- Ignore messages
- Assume everyone knows context
- Be vague
- Keep information to yourself

## Troubleshooting

### Cannot Access Team Resource

**Problem**: Resource not visible or accessible

**Solutions:**
1. Check if you're in correct team
2. Verify resource is published
3. Check your role permissions
4. Refresh the page
5. Contact team admin
6. Verify resource wasn't deleted

### Mentions Not Working

**Problem**: Team member not receiving mentions

**Solutions:**
1. Check spelling of username
2. Verify member is in team
3. Check member's notification settings
4. Try mentioning again
5. Use direct message instead
6. Contact administrator

### Cannot Share Conversation

**Problem**: Share button is disabled

**Solutions:**
1. Check if you have permission
2. Verify conversation is not private
3. Check if team allows sharing
4. Try different browser
5. Contact administrator

### Activity Feed Not Updating

**Problem**: Recent activity not showing

**Solutions:**
1. Refresh the page
2. Check date range filter
3. Check activity type filter
4. Clear browser cache
5. Try different browser
6. Contact administrator

## Related Documentation

- [Joining Teams](./joining-teams.md) - How to join teams
- [Team Roles](./team-roles.md) - Understanding roles
- [Chatting with Agents](../chat/chatting-with-agents.md) - Chat features
- [Workflow History](../workflows/workflow-history.md) - Workflow tracking

## Getting Help

If you need assistance with team collaboration:

1. **Documentation**: Review this guide
2. **Team Members**: Ask your team members
3. **Team Admin**: Contact your team admin
4. **Support**: Contact your organization's support team
5. **Administrator**: Reach out to your Clouisle administrator

---

**Last Updated**: 2026-02-11
