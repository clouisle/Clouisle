# Conversation Management

This guide explains how to manage your chat conversations with AI agents.

## Overview

Conversations in Clouisle are persistent chat sessions with AI agents. You can:

- **Create new conversations**: Start fresh chats with agents
- **Continue conversations**: Resume previous chats
- **Rename conversations**: Give conversations a custom title
- **Delete conversations**: Remove unwanted chats

> **Note:** Archiving, sharing, exporting, folders, and tags for conversations are **not implemented**.

## Conversations within an agent chat

### Accessing recent conversations

There is no global **Chat** or **Conversations** section. Conversations are scoped to the agent you are chatting with.

1. Open **Apps** (`/app/apps`).
2. Select the **Agent** tab.
3. Open an agent card's menu and choose **Chat**.
4. In `/chat/{agent_id}`, use that agent's conversation controls to open a recent conversation or start a new one.

The recent-conversation view is for the current agent; it does not combine conversations from other agents.

### Conversation information

Recent conversations can show:

| Field | Description |
|-------|-------------|
| **Agent** | The agent associated with the conversation (the current agent page) |
| **Title** | Conversation title |
| **Last message** | Preview of the most recent message |
| **Timestamp** | When the conversation was last updated |

## Creating Conversations

Start a conversation from the current agent's chat page. There is no global **New Chat** picker.

## Managing Conversations

### Renaming Conversations

Open a conversation in the agent chat and use its **...** menu to rename it when the rename action is available. The title is the only editable conversation setting.

### Deleting Conversations

Open the conversation's **...** menu, choose **Delete**, and confirm. Deletion removes the conversation and its messages and cannot be undone.

## Searching Conversations

An agent's chat page has **no conversation search** — its sidebar lists that agent's recent conversations without a filter box.

Conversation search is available in two other places, and both match the conversation **title or ID** only (message content is never searched):

- **Agent Logs** (`/app/apps/{agent_id}/logs`) — the current user's own conversations with that agent (`GET /api/v1/agents/{agent_id}/conversations` requires `conversation:read`; it also supports `created_after`/`created_before` and `sort_by`).
- **Activities** (`/activities` → **Conversations**, administrator console) — conversations of the agents you can access (agents in your teams; all agents for a superuser), and only **your own** conversations unless you hold `admin:dashboard:access`. Requires the `admin:conversation:read` permission (the route guard also accepts `workflow:read`).

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

### Cannot Find a Past Conversation

**Problem**: No search box is available on the agent chat page

**Solutions:**
1. Reopen the conversation from that agent's recent-conversation list
2. Rename conversations with descriptive titles so they are easy to spot
3. Search by title or ID on the agent's **Logs** page (`/app/apps/{agent_id}/logs`); the **Activities** page (`/activities`) additionally searches the agents you can access, but returns only your own conversations unless you hold `admin:dashboard:access`

## Related Documentation

- [Chatting with Agents](./chatting-with-agents.md) - Chat basics
- [File Uploads](./file-uploads.md) - Uploading files in chat

## Getting Help

If you need assistance with conversation management:

1. **Documentation**: Review this guide
2. **Support**: Contact your organization's support team
3. **Administrator**: Reach out to your Clouisle administrator

---

**Last Updated**: 2026-09-26
