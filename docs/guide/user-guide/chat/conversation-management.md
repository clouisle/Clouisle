# Conversation Management

This guide explains how to manage your chat conversations with AI agents.

## Overview

Conversations in Clouisle are persistent chat sessions with AI agents. You can:

- **Create new conversations**: Start fresh chats with agents
- **Continue conversations**: Resume previous chats
- **Rename conversations**: Give conversations a custom title
- **Search conversations**: Find past discussions by title or ID
- **Delete conversations**: Remove unwanted chats

> **Note:** Archiving, sharing, exporting, folders, and tags for conversations are **not implemented**.

## Conversation List

### Accessing Conversations

**From Platform Interface:**

1. Navigate to **Chat** or **Conversations** section
2. View the list of your conversations
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

### Conversation Titles

**Auto-generated titles:**
- The first message is used as the title (truncated if long)

**Custom titles:**
- You can rename conversations anytime
- See "Renaming Conversations" below

## Managing Conversations

### Renaming Conversations

**Steps:**

1. Open the conversation
2. Click the **"..."** menu in the header
3. Select **"Rename"**
4. Enter the new title (max 200 chars)
5. Click **"Save"** or press **Enter**

### Deleting Conversations

**Warning**: Deleted conversations cannot be recovered.

**Steps:**

1. Open the conversation or hover in the list
2. Click the **"..."** menu
3. Select **"Delete"**
4. Confirm deletion in the dialog
5. The conversation is permanently deleted

**What gets deleted:**
- All messages in the conversation
- Conversation metadata
- Cannot be undone

**Bulk delete** is available to administrators only (admin dashboard conversations page).

## Searching Conversations

### Search Bar

**Basic search:**

1. Go to **Conversations** section
2. Enter a search term in the search bar
3. Results are filtered
4. Click on a result to open

**What you can search:**
- Conversation titles
- Conversation IDs

> **Note:** Searching by message content is not supported. Conversations are matched by title or ID only.

## Conversation Settings

A conversation's only editable setting is its **title** (rename). There are no per-conversation notification, auto-save, or context-window settings.

## Best Practices

### Organizing Conversations

**✅ Do:**
- Use descriptive titles
- Delete unnecessary conversations

**❌ Don't:**
- Leave conversations with generic titles
- Keep hundreds of active conversations

### Conversation Hygiene

**✅ Do:**
- Review and clean up conversations periodically
- Delete test conversations

**❌ Don't:**
- Let conversations accumulate indefinitely
- Keep duplicate conversations

## Troubleshooting

### Conversation Not Loading

**Problem**: Conversation won't open or loads slowly

**Solutions:**
1. Refresh the page
2. Check your internet connection
3. Clear browser cache
4. Try a different browser
5. Contact the administrator

### Cannot Delete Conversation

**Problem**: Delete option is grayed out or fails

**Solutions:**
1. Check if you have permission to delete
2. Refresh the page
3. Contact the administrator

### Search Not Working

**Problem**: Search doesn't return expected results

**Solutions:**
1. Check spelling
2. Try different search terms
3. Note that only titles/IDs are searched (not message content)
4. Refresh the page

## Related Documentation

- [Chatting with Agents](./chatting-with-agents.md) - Chat basics
- [File Uploads](./file-uploads.md) - Uploading files in chat

## Getting Help

If you need assistance with conversation management:

1. **Documentation**: Review this guide
2. **Support**: Contact your organization's support team
3. **Administrator**: Reach out to your Clouisle administrator

---

**Last Updated**: 2026-02-11
