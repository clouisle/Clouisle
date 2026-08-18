# Agent Management

This guide covers how to manage AI agents as an administrator.

## Overview

As an administrator, you can:

- **View all agents**: Access all agents across teams
- **Create agents**: Set up new agents for teams
- **Configure agents**: Modify agent settings and capabilities
- **Monitor usage**: Track agent performance and usage
- **Manage lifecycle**: Publish and unpublish agents

## Accessing Agent Management

### Admin Dashboard

1. Log in as administrator
2. Navigate to **Apps** in the sidebar (**Resources** section)
3. View the agent management interface

### Agent List View

The agent list shows:

- **Agent name and description**
- **Team ownership**
- **Status** (Draft, Published)
- **Model** (LLM model used)
- **Usage statistics** (conversations, messages)
- **Created date**
- **Last activity**

**Filters:**
- Status (Draft, Published)
- Visibility (`private` or `team`; `public` is retained only for legacy records)
- Team
- Creator

**Search:**
- Search by agent name or description

## Creating Agents

### Create Agent for Team

1. Click **Create Agent** button
2. Fill in agent details:
   - **Name**: Agent display name
   - **Description**: Agent purpose and capabilities
   - **Team**: Select team owner
   - **Model**: Choose an LLM model (team-granted `TeamModel`)
   - **System Prompt**: Define agent behavior
   - **Max Iterations**: Limit tool-call iterations (1-200)

3. Configure capabilities:
   - **Knowledge Bases**: Attach knowledge bases with per-KB search settings
   - **Tools**: Enable tools (web search, calculator, etc.)
   - **RAG Mode**: Off, Auto, or Agentic
   - **Variables**: Define user-facing input variables

4. Set visibility:
   - **Visibility**: Private or Team

5. Click **Create Agent**

### Agent Configuration Options

**Basic Settings:**
```yaml
Name: Customer Support Agent
Description: Handles customer inquiries and support tickets
Team: Support Team
Model: GPT-4 Turbo (TeamModel grant)
Status: draft
```

**LLM Settings:**
```yaml
System Prompt: |
  You are a helpful customer support agent.
  Always be polite and professional.
  Use the knowledge base to answer questions.

Max Iterations: 5
Tools:
  - web_search
  - calculate
  - get_current_time
```

> **Note:** Agents do not expose per-agent sampling parameters (Temperature, Max Tokens, Top P, Frequency/Presence Penalty). LLM sampling defaults are configured on the model and stored in its `default_params`; agents configure `model_id`, `system_prompt`, `max_iterations`, tool sets, and knowledge base attachments instead.

**RAG Configuration:**
```yaml
RAG Mode: agentic        # off, auto, or agentic
Knowledge Bases:
  - Product Documentation
  - FAQ Database

Per-KB Search Settings:
  Search Mode: hybrid     # vector, fulltext, or hybrid
  Top K: 5
  Score Threshold: 0.0
  Rerank: enabled
```

**Tools:**
```yaml
Enabled Tools:
  - Web Search
  - Calculator
  - Date/Time
  - Unit Converter

Tool Settings:
  Max Tool Call Iterations: 5
  Tool Timeout: 30s
```

## Editing Agents

### Update Agent Settings

1. Find agent in list
2. Click **Edit** button
3. Modify settings:
   - Basic information
   - LLM configuration
   - Knowledge bases
   - Tools
   - Permissions

4. Click **Save Changes**

### Bulk Edit

> **Note:** Not implemented / Roadmap. There is no bulk edit for agents. Agents are updated individually via `PUT /api/v1/admin/agents/{agent_id}`; bulk lifecycle actions (publish, unpublish, duplicate, delete) are available per agent from the list.

## Agent Status Management

### Agent Statuses

**Draft:**
- Agent is being configured
- Cannot be used by users
- Only visible to editors

**Published:**
- Agent is operational
- Can receive messages
- Appears in the user interface

> **Note:** Not implemented / Roadmap: there is no `active`/`inactive` or `archived` agent status, and no archive/restore workflow. Agents have exactly two statuses: `draft` and `published`.

### Change Agent Status

**Publish Agent:**
```bash
1. Select agent
2. Click "Publish"
3. Confirm publication
4. Agent status becomes "published"
```

**Unpublish Agent:**
```bash
1. Select agent
2. Click "Unpublish"
3. Confirm unpublish
4. Agent status returns to "draft"
```

**Archive Agent:**
> **Note:** Not implemented / Roadmap. There is no archive function for agents. To remove an agent from use, unpublish it or delete it (`DELETE /api/v1/admin/agents/{agent_id}`).

## Monitoring Agent Usage

### Usage Statistics

The statistics endpoints (`GET /api/v1/agents/{agent_id}/stats`) expose per-agent metrics for a time period (`period`: `24h`, `7d`, `30d`, `all`):

- Total conversations and messages
- Active users
- Token usage (prompt, completion, and total tokens)
- Average response time
- Tool call count and tool usage (`GET /api/v1/agents/{agent_id}/stats/tool-usage`)
- Usage trends (`GET /api/v1/agents/{agent_id}/stats/trends`)
- Recent conversations (`GET /api/v1/agents/{agent_id}/stats/recent-conversations`)

The admin list/detail actions expose these metrics; there is no separate **Statistics** tab.

> **Note:** Not implemented / Roadmap: per-agent cost breakdowns, response-time percentiles (p50/p95/p99), export of statistics (CSV/PDF), and scheduled usage reports are not available. The statistics API returns the metrics listed above only.

## Knowledge Base Management

### Attach Knowledge Bases

1. Edit agent
2. Go to **Knowledge Bases** section
3. Click **Add Knowledge Base**
4. Configure per-KB search settings:
   - Search mode (`vector`, `fulltext`, or `hybrid`)
   - Top K results
   - Score threshold
   - Rerank enabled

5. Save changes

### Remove Knowledge Bases

1. Edit agent
2. Go to **Knowledge Bases** section
3. Find knowledge base
4. Click **Remove**
5. Confirm removal

### Knowledge Base Priority

Knowledge base order can be adjusted by editing the agent; the ordering is defined by the `knowledge_base_configs` list and is applied when the agent retrieves context.

## Tool Management

### Enable Tools

1. Edit agent
2. Go to **Tools** section
3. Browse available tools
4. Toggle tools on/off:
   - Web Search
   - Calculator
   - Date/Time
   - Unit Converter
   - Custom tools

5. Configure tool settings
6. Save changes

### Tool Configuration

**Web Search:**
```yaml
Enabled: true
Requires: TAVILY_API_KEY
```

Web Search is powered by Tavily. The API key is stored in the tool configuration (`TAVILY_API_KEY`); per-query parameters such as `max_results` are controlled by the agent at call time.

**Custom Tools:**
```yaml
Tool Name: CRM Lookup
Endpoint: https://api.example.com/crm
Auth: API Key
Timeout: 30s
```

Custom tools are created and tested in **Capabilities** (tool management), then enabled per agent.

## Agent Limits

> **Note:** Not implemented / Roadmap. There are no per-team or per-agent resource limits (max agents, max conversations, max tokens per day, cost caps, rate limits). Agents and their usage are not quota-gated.

## Agent Templates

> **Note:** Not implemented / Roadmap. There is no agent template library or "Save as Template" flow. To reuse an agent, duplicate it (`POST /api/v1/admin/agents/{agent_id}/duplicate`) and adjust the copy.

## Troubleshooting

### Agent Not Responding

**Symptoms:**
- Messages sent but no response
- Timeout errors

**Solutions:**

1. **Check agent status:**
   - Verify agent is published
   - Check model availability

2. **Check model configuration:**
   - Verify API key is valid
   - Test model connectivity
   - Check rate limits

3. **Check knowledge bases:**
   - Verify KBs are indexed
   - Check search is working

4. **Check audit logs:**
   ```bash
   Audit Logs → filter by resource type "agent" and resource ID
   Look for errors
   ```

### Poor Response Quality

**Symptoms:**
- Irrelevant responses
- Hallucinations
- Inconsistent behavior

**Solutions:**

1. **Review system prompt:**
   - Make instructions clearer
   - Add examples
   - Set boundaries

2. **Adjust temperature:**
   - Lower for more focused responses
   - Higher for more creative responses

3. **Improve knowledge base:**
   - Add more relevant documents
   - Update outdated content
   - Improve chunking strategy

4. **Enable RAG agentic mode:**
   - Agentic RAG lets the agent decide when to retrieve, improving factual grounding

### High Costs

**Symptoms:**
- Unexpected high token usage

**Solutions:**

1. **Review usage:**
   - Check per-agent statistics (`GET /api/v1/agents/{agent_id}/stats`) for token usage and conversation counts
   - Identify high-usage agents

2. **Optimize prompts:**
   - Shorter system prompts
   - Reduce context length
   - Use cheaper models for simple tasks

3. **Review usage patterns:**
   - Identify high-usage agents
   - Check for abuse
   - Optimize workflows

> **Note:** Not implemented / Roadmap: per-agent token limits, daily limits, and cost alerts are not available. Usage monitoring is read-only via the statistics endpoints.

## Best Practices

### Agent Design

**✅ Do:**
- Write clear, specific system prompts
- Test agents thoroughly before deployment
- Use appropriate models for tasks
- Enable RAG for factual accuracy
- Monitor usage via the statistics endpoints
- Collect user feedback
- Iterate based on performance

**❌ Don't:**
- Use vague system prompts
- Deploy untested agents
- Use expensive models for simple tasks
- Ignore error rates
- Set unlimited token usage
- Forget to monitor costs
- Ignore user complaints

### Security

**✅ Do:**
- Review agent permissions regularly
- Limit tool access appropriately
- Monitor for abuse
- Use team isolation
- Enable audit logging
- Rotate API keys regularly

**❌ Don't:**
- Grant excessive permissions
- Share admin credentials
- Ignore security alerts
- Allow unrestricted tool access
- Disable audit logs

### Performance

**✅ Do:**
- Use streaming for better UX
- Enable caching where possible
- Optimize knowledge base search
- Monitor response times
- Set appropriate timeouts
- Use async processing

**❌ Don't:**
- Use synchronous processing for long tasks
- Ignore performance metrics
- Overload agents with too many KBs
- Set very high max_tokens
- Forget to optimize queries

## Bulk Operations

### Bulk Actions

> **Note:** Not implemented / Roadmap. There are no bulk actions (activate/deactivate, change model, update team, archive, export configuration) for agents. Lifecycle operations are performed per agent: publish, unpublish, duplicate, and delete.

### Import/Export

> **Note:** Not implemented / Roadmap. There is no agent import/export (JSON/CSV).

## API Access

### Manage Agents via API

Admin agent endpoints live under `/api/v1/admin/agents` and require the `admin:app:*` permissions. See [Agents API](../../api-reference/endpoints/agents.md) for details.

**Common Operations:**
```python
# List all agents (admin) — filters: status, visibility, team_id, creator, search
agents = api.get("/api/v1/admin/agents", params={"status": ["published"]})

# Create agent for team
agent = api.post("/api/v1/admin/agents", json={
    "name": "Support Agent",
    "team_id": "team-123",
    "model_id": "model-456",  # TeamModel ID (a team-granted model)
    "system_prompt": "You are a helpful assistant.",
    "rag_mode": "agentic"
})

# Update agent (PUT, not PATCH)
agent = api.put(f"/api/v1/admin/agents/{agent_id}", json={
    "name": "Support Agent v2"
})

# Publish / unpublish / duplicate
api.post(f"/api/v1/admin/agents/{agent_id}/publish")
api.post(f"/api/v1/admin/agents/{agent_id}/unpublish")
api.post(f"/api/v1/admin/agents/{agent_id}/duplicate")

# Get agent statistics (period: 24h, 7d, 30d, all)
stats = api.get(f"/api/v1/agents/{agent_id}/stats", params={"period": "30d"})
```

## Related Documentation

- [Agents API](../../api-reference/endpoints/agents.md) - API reference
- [Agent Configuration](../../user-guide/agents/agent-configuration.md) - User guide
- [Model Management](../models/model-management.md) - Model admin
- [Team Management](../teams/team-management.md) - Team admin

---

**Last Updated**: 2026-02-11
