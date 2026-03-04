# API Key Scopes

This document provides a detailed reference of all available API key scopes in Clouisle.

## Overview

Scopes control what an API key can access. Understanding scopes helps you:

- **Secure access**: Grant only necessary permissions
- **Organize keys**: Create purpose-specific keys
- **Audit usage**: Track what keys can do
- **Comply with policies**: Follow security requirements
- **Troubleshoot issues**: Identify permission problems

## Scope Format

### Naming Convention

Scopes follow the pattern: `resource:action`

**Examples:**
- `agent:read` - Read agents
- `agent:create` - Create agents
- `workflow:run` - Execute workflows

### Wildcard Scope

**All permissions:**
- `*` - Grants all permissions
- **Use with extreme caution**
- Only for trusted applications
- Should be time-limited

## Agent Scopes

### agent:read

**Description**: View agents and their details

**Allows:**
- List all accessible agents
- Get agent details
- View agent configuration
- View agent statistics

**Does not allow:**
- Create agents
- Update agents
- Delete agents
- Chat with agents

**Example usage:**
```bash
curl -X GET "https://your-domain.com/api/v1/agents" \
  -H "Authorization: Bearer API_KEY_WITH_AGENT_READ"
```

### agent:create

**Description**: Create new agents

**Allows:**
- Create new agents
- Set initial configuration
- Assign to teams

**Does not allow:**
- Update existing agents
- Delete agents
- Publish agents

**Example usage:**
```bash
curl -X POST "https://your-domain.com/api/v1/agents" \
  -H "Authorization: Bearer API_KEY_WITH_AGENT_CREATE" \
  -d '{"name": "New Agent", ...}'
```

### agent:update

**Description**: Update existing agents

**Allows:**
- Update agent configuration
- Modify system prompts
- Change agent settings
- Update metadata

**Does not allow:**
- Create agents
- Delete agents
- Publish/unpublish agents

**Example usage:**
```bash
curl -X PATCH "https://your-domain.com/api/v1/agents/{id}" \
  -H "Authorization: Bearer API_KEY_WITH_AGENT_UPDATE" \
  -d '{"name": "Updated Name"}'
```

### agent:delete

**Description**: Delete agents

**Allows:**
- Delete agents permanently
- Remove agent resources

**Does not allow:**
- Create agents
- Update agents

**Example usage:**
```bash
curl -X DELETE "https://your-domain.com/api/v1/agents/{id}" \
  -H "Authorization: Bearer API_KEY_WITH_AGENT_DELETE"
```

### agent:chat

**Description**: Chat with agents

**Allows:**
- Send messages to agents
- Receive responses
- Stream responses
- Access conversation history

**Does not allow:**
- Create agents
- Update agents
- Delete agents

**Example usage:**
```bash
curl -X POST "https://your-domain.com/api/v1/agents/{id}/chat" \
  -H "Authorization: Bearer API_KEY_WITH_AGENT_CHAT" \
  -d '{"message": "Hello"}'
```

## Workflow Scopes

### workflow:read

**Description**: View workflows and their details

**Allows:**
- List all accessible workflows
- Get workflow details
- View workflow definition
- View execution history

**Does not allow:**
- Create workflows
- Update workflows
- Delete workflows
- Execute workflows

**Example usage:**
```bash
curl -X GET "https://your-domain.com/api/v1/workflows" \
  -H "Authorization: Bearer API_KEY_WITH_WORKFLOW_READ"
```

### workflow:create

**Description**: Create new workflows

**Allows:**
- Create new workflows
- Set workflow definition
- Configure triggers

**Does not allow:**
- Update existing workflows
- Delete workflows
- Execute workflows

### workflow:update

**Description**: Update existing workflows

**Allows:**
- Update workflow definition
- Modify workflow settings
- Change triggers
- Update metadata

**Does not allow:**
- Create workflows
- Delete workflows
- Execute workflows

### workflow:delete

**Description**: Delete workflows

**Allows:**
- Delete workflows permanently
- Remove workflow resources

**Does not allow:**
- Create workflows
- Update workflows
- Execute workflows

### workflow:run

**Description**: Execute workflows

**Allows:**
- Run workflows with inputs
- Check execution status
- View execution results
- Stop running workflows

**Does not allow:**
- Create workflows
- Update workflows
- Delete workflows

**Example usage:**
```bash
curl -X POST "https://your-domain.com/api/v1/workflows/{id}/run" \
  -H "Authorization: Bearer API_KEY_WITH_WORKFLOW_RUN" \
  -d '{"inputs": {...}}'
```

## Knowledge Base Scopes

### kb:read

**Description**: View knowledge bases and documents

**Allows:**
- List knowledge bases
- Get KB details
- List documents
- Search documents
- Download documents

**Does not allow:**
- Create knowledge bases
- Upload documents
- Update documents
- Delete documents

**Example usage:**
```bash
curl -X GET "https://your-domain.com/api/v1/kb" \
  -H "Authorization: Bearer API_KEY_WITH_KB_READ"
```

### kb:create

**Description**: Create knowledge bases

**Allows:**
- Create new knowledge bases
- Set KB configuration
- Configure chunking strategy

**Does not allow:**
- Update existing KBs
- Delete KBs
- Upload documents

### kb:update

**Description**: Update knowledge bases and documents

**Allows:**
- Update KB settings
- Upload documents
- Update document metadata
- Reprocess documents

**Does not allow:**
- Create knowledge bases
- Delete knowledge bases
- Delete documents

**Example usage:**
```bash
curl -X POST "https://your-domain.com/api/v1/kb/{id}/documents" \
  -H "Authorization: Bearer API_KEY_WITH_KB_UPDATE" \
  -F "file=@document.pdf"
```

### kb:delete

**Description**: Delete knowledge bases and documents

**Allows:**
- Delete knowledge bases
- Delete documents
- Remove KB resources

**Does not allow:**
- Create knowledge bases
- Update knowledge bases
- Upload documents

## Team Scopes

### team:read

**Description**: View team information

**Allows:**
- List teams
- Get team details
- View team members
- View team resources

**Does not allow:**
- Create teams
- Update teams
- Manage members

**Example usage:**
```bash
curl -X GET "https://your-domain.com/api/v1/teams" \
  -H "Authorization: Bearer API_KEY_WITH_TEAM_READ"
```

### team:manage

**Description**: Manage team settings and members

**Allows:**
- Update team settings
- Invite members
- Remove members
- Change member roles

**Does not allow:**
- Create teams
- Delete teams

## User Scopes

### user:read

**Description**: View user information

**Allows:**
- Get current user info
- View user profile
- List users (if permitted)

**Does not allow:**
- Update user info
- Create users
- Delete users

**Example usage:**
```bash
curl -X GET "https://your-domain.com/api/v1/users/me" \
  -H "Authorization: Bearer API_KEY_WITH_USER_READ"
```

### user:update

**Description**: Update user information

**Allows:**
- Update user profile
- Change user settings
- Update preferences

**Does not allow:**
- Create users
- Delete users
- Change passwords

## Model Scopes

### model:read

**Description**: View available models

**Allows:**
- List available models
- Get model details
- View model capabilities

**Does not allow:**
- Create models
- Update models
- Delete models

### model:use

**Description**: Use models for inference

**Allows:**
- Call model APIs
- Generate completions
- Use model features

**Does not allow:**
- Create models
- Update models
- Delete models

## Tool Scopes

### tool:read

**Description**: View available tools

**Allows:**
- List available tools
- Get tool details
- View tool schemas

**Does not allow:**
- Create tools
- Update tools
- Execute tools directly

### tool:use

**Description**: Use tools in workflows and agents

**Allows:**
- Execute tools
- Pass tool parameters
- Receive tool results

**Does not allow:**
- Create tools
- Update tools
- Delete tools

## Scope Combinations

### Common Combinations

**Read-only access:**
```json
{
  "scopes": [
    "agent:read",
    "workflow:read",
    "kb:read",
    "team:read",
    "user:read"
  ]
}
```

**Chat-only access:**
```json
{
  "scopes": [
    "agent:read",
    "agent:chat"
  ]
}
```

**Workflow execution:**
```json
{
  "scopes": [
    "workflow:read",
    "workflow:run"
  ]
}
```

**Content management:**
```json
{
  "scopes": [
    "kb:read",
    "kb:update",
    "agent:read",
    "agent:update"
  ]
}
```

**Full agent management:**
```json
{
  "scopes": [
    "agent:read",
    "agent:create",
    "agent:update",
    "agent:delete",
    "agent:chat"
  ]
}
```

**Admin access:**
```json
{
  "scopes": [
    "agent:*",
    "workflow:*",
    "kb:*",
    "team:manage",
    "user:read"
  ]
}
```

## Scope Validation

### Checking Scopes

**API returns error if scope is missing:**

```json
{
  "code": 3000,
  "data": {
    "required_scope": "agent:create",
    "provided_scopes": ["agent:read", "agent:chat"]
  },
  "msg": "Permission denied: Missing required scope 'agent:create'"
}
```

### Testing Scopes

**Test if key has required scope:**

```bash
# This will succeed if key has agent:read
curl -X GET "https://your-domain.com/api/v1/agents" \
  -H "Authorization: Bearer YOUR_API_KEY"

# This will fail if key doesn't have agent:create
curl -X POST "https://your-domain.com/api/v1/agents" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{"name": "Test"}'
```

## Best Practices

### Scope Selection

**✅ Do:**
- Use principle of least privilege
- Grant only necessary scopes
- Create separate keys for different purposes
- Document why each scope is needed
- Review scopes regularly
- Remove unused scopes

**❌ Don't:**
- Grant `*` (all) scope unless absolutely necessary
- Use same key for all applications
- Grant more scopes than needed
- Forget to document scope usage
- Keep unused scopes active

### Scope Organization

**✅ Do:**
- Group related scopes together
- Use descriptive key names
- Create purpose-specific keys
- Separate read and write operations
- Use different keys per environment

**❌ Don't:**
- Mix unrelated scopes
- Use generic key names
- Share keys between applications
- Use production keys in development

### Security

**✅ Do:**
- Audit scope usage regularly
- Monitor for scope violations
- Rotate keys with sensitive scopes
- Limit scope lifetime
- Use time-limited keys for sensitive operations

**❌ Don't:**
- Grant admin scopes to untrusted applications
- Ignore scope violation alerts
- Use permanent keys with write scopes
- Share keys with sensitive scopes

## Scope Reference Table

### Quick Reference

| Scope | Read | Create | Update | Delete | Execute |
|-------|------|--------|--------|--------|---------|
| `agent:read` | ✅ | ❌ | ❌ | ❌ | ❌ |
| `agent:create` | ❌ | ✅ | ❌ | ❌ | ❌ |
| `agent:update` | ❌ | ❌ | ✅ | ❌ | ❌ |
| `agent:delete` | ❌ | ❌ | ❌ | ✅ | ❌ |
| `agent:chat` | ❌ | ❌ | ❌ | ❌ | ✅ |
| `workflow:read` | ✅ | ❌ | ❌ | ❌ | ❌ |
| `workflow:create` | ❌ | ✅ | ❌ | ❌ | ❌ |
| `workflow:update` | ❌ | ❌ | ✅ | ❌ | ❌ |
| `workflow:delete` | ❌ | ❌ | ❌ | ✅ | ❌ |
| `workflow:run` | ❌ | ❌ | ❌ | ❌ | ✅ |
| `kb:read` | ✅ | ❌ | ❌ | ❌ | ❌ |
| `kb:create` | ❌ | ✅ | ❌ | ❌ | ❌ |
| `kb:update` | ❌ | ❌ | ✅ | ❌ | ❌ |
| `kb:delete` | ❌ | ❌ | ❌ | ✅ | ❌ |

## Troubleshooting

### Permission Denied

**Problem**: API returns permission denied error

**Solutions:**
1. Check API key has required scope
2. Verify scope spelling
3. Check if scope is active
4. Review API key details
5. Create new key with correct scopes
6. Contact administrator

### Scope Not Working

**Problem**: Have scope but still get permission denied

**Solutions:**
1. Check if key is expired
2. Verify key is not revoked
3. Check team permissions
4. Verify resource ownership
5. Review audit logs
6. Contact administrator

### Cannot Add Scope

**Problem**: Cannot add scope to existing key

**Solutions:**
1. Scopes cannot be removed, only added
2. Create new key with desired scopes
3. Revoke old key
4. Update applications to use new key
5. Contact administrator for help

## Related Documentation

- [Managing API Keys](../user-guide/api-keys/managing-api-keys.md) - API key management
- [Authentication](./authentication.md) - Authentication methods
- [Agents API](./endpoints/agents.md) - Agent endpoints
- [Workflows API](./endpoints/workflows.md) - Workflow endpoints

---

**Last Updated**: 2026-02-11
