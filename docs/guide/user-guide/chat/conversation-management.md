# Conversation Management

This guide explains how to manage your chat conversations with AI agents.

## Overview

Conversations in Clouisle are persistent chat sessions with AI agents. You can:

- **Create new conversations**: Start fresh chats with agents
- **Continue conversations**: Resume previous chats
- **Organize conversations**: Rename, archive, and categorize
- **Search conversations**: Find past discussions
- **Share conversations**: Collaborate with team members
- **Delete conversations**: Remove unwanted chats

## Conversation List

### Accessing Conversations

**From Platform Interface:**

1. Navigate to **Chat** or **Conversations** section
2. View list of all your conversations
3. Click on a conversation to open it

**Conversation list view:**
```
┌─────────────────────────────────────────────────────┐
│ Conversations                          [+ New Chat] │
├─────────────────────────────────────────────────────┤
│                                                     │
│ 🤖 Product Analysis                                 │
│    Last message: "Thanks for the summary"          │
│    2 hours ago • 15 messages                       │
│                                                     │
│ 🤖 Code Review Assistant                            │
│    Last message: "The function looks good"         │
│    Yesterday • 8 messages                          │
│                                                     │
│ 🤖 Marketing Strategy                               │
│    Last message: "Let's focus on social media"     │
│    3 days ago • 23 messages                        │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### Conversation Information

Each conversation shows:

| Field | Description |
|-------|-------------|
| **Agent Name** | The AI agent you're chatting with |
| **Title** | Conversation title (auto-generated or custom) |
| **Last Message** | Preview of the most recent message |
| **Timestamp** | When the last message was sent |
| **Message Count** | Total number of messages |
| **Status** | Active, Archived, or Shared |

## Creating Conversations

### Starting a New Conversation

**Method 1: From Agent Page**

1. Navigate to **Agents** section
2. Click on an agent card
3. Click **"Start Chat"** or **"Chat"** button
4. New conversation opens
5. Send your first message

**Method 2: From Conversations List**

1. Go to **Conversations** section
2. Click **"+ New Chat"** button
3. Select an agent from the list
4. New conversation opens
5. Send your first message

**Method 3: Quick Chat**

1. Click the **chat icon** in the navigation bar
2. Select an agent
3. Start chatting immediately

### Conversation Titles

**Auto-generated titles:**
- First message is used as title (truncated if long)
- Example: "Help me analyze this data" → "Help me analyze this data"

**Custom titles:**
- You can rename conversations anytime
- See "Renaming Conversations" section below

## Managing Conversations

### Renaming Conversations

**Steps:**

1. Open the conversation
2. Click the **"..."** menu in the header
3. Select **"Rename"**
4. Enter new title
5. Click **"Save"** or press **Enter**

**Or from conversation list:**

1. Hover over a conversation
2. Click the **"..."** menu
3. Select **"Rename"**
4. Enter new title
5. Click **"Save"**

**Best practices for titles:**
- Use descriptive names: "Q3 Sales Analysis" instead of "Chat 1"
- Include date if relevant: "2026-02-11 Product Review"
- Keep it concise: 50 characters or less

### Archiving Conversations

**Why archive:**
- Keep conversation list clean
- Preserve old conversations without deleting
- Reduce clutter while maintaining history

**Steps:**

1. Open the conversation or hover in list
2. Click the **"..."** menu
3. Select **"Archive"**
4. Conversation moves to archive

**Viewing archived conversations:**

1. Go to **Conversations** section
2. Click **"Archived"** tab or filter
3. View all archived conversations

**Unarchiving:**

1. Open archived conversation
2. Click **"..."** menu
3. Select **"Unarchive"**
4. Conversation returns to main list

### Deleting Conversations

**Warning**: Deleted conversations cannot be recovered.

**Steps:**

1. Open the conversation or hover in list
2. Click the **"..."** menu
3. Select **"Delete"**
4. Confirm deletion in dialog
5. Conversation is permanently deleted

**What gets deleted:**
- All messages in the conversation
- Uploaded files
- Conversation metadata
- Cannot be undone

**Bulk delete:**

1. Go to **Conversations** section
2. Select multiple conversations (checkboxes)
3. Click **"Delete Selected"**
4. Confirm deletion
5. All selected conversations are deleted

## Searching Conversations

### Search Bar

**Basic search:**

1. Go to **Conversations** section
2. Enter search term in search bar
3. Results are filtered in real-time
4. Click on a result to open

**What you can search:**
- Conversation titles
- Message content
- Agent names
- File names

**Example searches:**
```
"sales report"     → Finds conversations mentioning sales reports
"Q3 2025"          → Finds conversations from Q3 2025
"Product Analysis" → Finds conversations with this title
```

### Advanced Search

**Filters:**

| Filter | Description |
|--------|-------------|
| **Agent** | Filter by specific agent |
| **Date Range** | Filter by date (today, this week, this month, custom) |
| **Status** | Active, Archived, Shared |
| **Has Files** | Conversations with file uploads |

**Using filters:**

1. Click **"Filters"** button
2. Select filter criteria
3. Apply filters
4. Results update automatically

**Example:**
```
Agent: "Code Review Assistant"
Date: "Last 7 days"
Has Files: Yes

→ Shows all conversations with Code Review Assistant
  from the past week that contain file uploads
```

## Conversation Settings

### Accessing Settings

**Steps:**

1. Open a conversation
2. Click the **"..."** menu in header
3. Select **"Settings"**
4. Settings panel opens

### Available Settings

**Conversation settings:**

| Setting | Description |
|---------|-------------|
| **Title** | Rename conversation |
| **Agent** | View agent details (cannot change) |
| **Notifications** | Enable/disable notifications for this conversation |
| **Auto-save** | Automatically save conversation (default: on) |
| **Context Window** | Number of messages to include in context |

**Context window:**
- Controls how many previous messages the agent remembers
- Default: 20 messages
- Range: 5-100 messages
- Higher = more context but slower responses

**Example:**
```
Context Window: 20 messages

Agent remembers the last 20 messages when responding.
Older messages are not included in the context.
```

## Sharing Conversations

### Sharing with Team Members

**Steps:**

1. Open the conversation
2. Click **"Share"** button in header
3. Select team members to share with
4. Choose permission level:
   - **View**: Can read messages only
   - **Comment**: Can read and add comments
   - **Edit**: Can send messages
5. Click **"Share"**
6. Team members receive notification

**Shared conversation indicator:**
```
┌─────────────────────────────────────────┐
│ 👥 Shared with 3 team members           │
│                                         │
│ • Alice (Edit)                          │
│ • Bob (View)                            │
│ • Carol (Comment)                       │
└─────────────────────────────────────────┘
```

### Collaboration Features

**When conversation is shared:**

- All participants see the same messages
- Real-time updates when someone sends a message
- Typing indicators show who's typing
- Message attribution shows who sent each message

**Example:**
```
You: "Can you analyze this data?"

Agent: "Sure! I'll analyze the data..."

Alice: "Great analysis! Can we also look at trends?"

Agent: "Of course! Here are the trends..."
```

### Unsharing

**Steps:**

1. Open shared conversation
2. Click **"Share"** button
3. Click **"X"** next to team member's name
4. Confirm removal
5. Team member loses access

**Note**: Original creator always retains access.

## Conversation History

### Viewing History

**Message history:**
- All messages are preserved in chronological order
- Scroll up to view older messages
- Infinite scroll loads more messages automatically

**Message metadata:**
```
┌─────────────────────────────────────────┐
│ You                        2026/02/11 10:00 │
│ Can you help me with this?              │
│                                         │
│ Agent                      2026/02/11 10:01 │
│ Of course! What do you need help with?  │
│ ✓ Read                                  │
└─────────────────────────────────────────┘
```

### Exporting Conversations

**Export formats:**
- **Markdown**: Plain text with formatting
- **PDF**: Formatted document
- **JSON**: Structured data

**Steps:**

1. Open the conversation
2. Click **"..."** menu
3. Select **"Export"**
4. Choose format
5. Click **"Download"**
6. File is downloaded to your computer

**Example export (Markdown):**
```markdown
# Product Analysis
Date: 2026-02-11

## Conversation

**You** (10:00):
Can you analyze this sales data?

**Agent** (10:01):
Sure! Here's my analysis:
- Revenue increased 15% YoY
- Top product: Widget A
- Growth trend: Positive
```

### Printing Conversations

**Steps:**

1. Open the conversation
2. Click **"..."** menu
3. Select **"Print"**
4. Print dialog opens
5. Configure print settings
6. Click **"Print"**

## Conversation Organization

### Folders (If Available)

**Creating folders:**

1. Go to **Conversations** section
2. Click **"+ New Folder"**
3. Enter folder name
4. Click **"Create"**

**Moving conversations to folders:**

1. Drag and drop conversation onto folder
2. Or right-click conversation → **"Move to Folder"**
3. Select folder
4. Click **"Move"**

**Folder structure:**
```
📁 Work Projects
   └─ Product Analysis
   └─ Code Reviews
   └─ Team Meetings

📁 Personal
   └─ Learning Notes
   └─ Ideas

📁 Archive
   └─ Old Conversations
```

### Tags (If Available)

**Adding tags:**

1. Open conversation
2. Click **"Add Tag"** button
3. Enter tag name or select existing
4. Press **Enter**
5. Tag is added

**Filtering by tags:**

1. Go to **Conversations** section
2. Click on a tag in the sidebar
3. View all conversations with that tag

**Example tags:**
```
#urgent #sales #q3-2026 #review #follow-up
```

## Conversation Limits

### Storage Limits

**Default limits:**
- Maximum 1000 conversations per user
- Maximum 10,000 messages per conversation
- Maximum 100 MB of files per conversation

**Exceeding limits:**
```
⚠️ Warning: Approaching conversation limit
   You have 950 out of 1000 conversations.

   Consider archiving or deleting old conversations.
```

### Performance

**Large conversations:**
- Conversations with >1000 messages may load slowly
- Consider starting a new conversation for better performance
- Export and archive very long conversations

## Best Practices

### Organizing Conversations

**✅ Do:**
- Use descriptive titles
- Archive old conversations regularly
- Use folders or tags for organization
- Delete unnecessary conversations
- Export important conversations for backup

**❌ Don't:**
- Leave conversations with generic titles
- Keep hundreds of active conversations
- Forget to archive completed projects
- Delete conversations without exporting first

### Conversation Hygiene

**✅ Do:**
- Review and clean up conversations monthly
- Archive completed projects
- Delete test conversations
- Export important conversations
- Share relevant conversations with team

**❌ Don't:**
- Let conversations accumulate indefinitely
- Keep duplicate conversations
- Share sensitive conversations publicly
- Forget to unshare when project ends

### Performance Tips

**✅ Do:**
- Start new conversations for new topics
- Keep conversations focused on one topic
- Archive long conversations
- Limit context window for faster responses

**❌ Don't:**
- Use one conversation for everything
- Let conversations grow to thousands of messages
- Keep all conversations active
- Use maximum context window unnecessarily

## Troubleshooting

### Conversation Not Loading

**Problem**: Conversation won't open or loads slowly

**Solutions:**
1. Refresh the page
2. Check your internet connection
3. Clear browser cache
4. Try a different browser
5. Conversation may be very large (wait longer)
6. Contact administrator

### Messages Not Syncing

**Problem**: New messages don't appear in shared conversation

**Solutions:**
1. Refresh the page
2. Check if you're still connected (network icon)
3. Check if conversation is still shared with you
4. Try logging out and back in
5. Contact administrator

### Cannot Delete Conversation

**Problem**: Delete option is grayed out or fails

**Solutions:**
1. Check if you have permission to delete
2. Check if conversation is shared (may need to unshare first)
3. Try archiving instead
4. Contact conversation owner
5. Contact administrator

### Search Not Working

**Problem**: Search doesn't return expected results

**Solutions:**
1. Check spelling
2. Try different search terms
3. Clear search filters
4. Refresh the page
5. Try advanced search with filters
6. Contact administrator

## Related Documentation

- [Chatting with Agents](./chatting-with-agents.md) - Chat basics
- [File Uploads](./file-uploads.md) - Uploading files in chat
- [Agent Capabilities](../../concepts/agents.md) - What agents can do
- [Team Collaboration](../teams/team-collaboration.md) - Working with teams

## Getting Help

If you need assistance with conversation management:

1. **Documentation**: Review this guide
2. **Search**: Use the search feature to find conversations
3. **Support**: Contact your organization's support team
4. **Administrator**: Reach out to your Clouisle administrator

---

**Last Updated**: 2026-02-11
