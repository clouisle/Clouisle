# Agent Management

This guide covers how to manage AI agents as an administrator.

## Overview

As an administrator, you can:

- **View all agents**: Access all agents across teams
- **Create agents**: Set up new agents for teams
- **Configure agents**: Modify agent settings and capabilities
- **Monitor usage**: Track agent performance and usage
- **Manage lifecycle**: Publish, unpublish, archive agents
- **Set limits**: Configure resource limits per team

## Accessing Agent Management

### Admin Dashboard

1. Log in as administrator
2. Navigate to **Admin** → **Agents**
3. View agent management interface

### Agent List View

The agent list shows:

- **Agent name and description**
- **Team ownership**
- **Status** (Active, Inactive, Published)
- **Model** (LLM model used)
- **Usage statistics** (conversations, messages)
- **Created date**
- **Last activity**

**Filters:**
- Team
- Status (Active, Inactive, Published)
- Model
- Date range

**Search:**
- Search by agent name or description

## Creating Agents

### Create Agent for Team

1. Click **Create Agent** button
2. Fill in agent details:
   - **Name**: Agent display name
   - **Description**: Agent purpose and capabilities
   - **Team**: Select team owner
   - **Model**: Choose LLM model
   - **System Prompt**: Define agent behavior
   - **Temperature**: Control randomness (0.0-1.0)
   - **Max Tokens**: Maximum response length

3. Configure capabilities:
   - **Knowledge Bases**: Attach knowledge bases
   - **Tools**: Enable tools (web search, calculator, etc.)
   - **RAG Mode**: Citation or Rewrite
   - **Streaming**: Enable real-time responses

4. Set permissions:
   - **Visibility**: Private (team only) or Public
   - **Allow sharing**: Enable conversation sharing

5. Click **Create Agent**

### Agent Configuration Options

**Basic Settings:**
```yaml
Name: Customer Support Agent
Description: Handles customer inquiries and support tickets
Team: Support Team
Model: GPT-4 Turbo
Status: Active
```

**LLM Settings:**
```yaml
System Prompt: |
  You are a helpful customer support agent.
  Always be polite and professional.
  Use the knowledge base to answer questions.

Temperature: 0.7
Max Tokens: 2048
Top P: 0.9
Frequency Penalty: 0.0
Presence Penalty: 0.0
```

**RAG Configuration:**
```yaml
RAG Mode: Citation
Knowledge Bases:
  - Product Documentation
  - FAQ Database
  - Support Tickets Archive

Search Settings:
  Top K: 5
  Score Threshold: 0.7
  Rerank: true
```

**Tools:**
```yaml
Enabled Tools:
  - Web Search
  - Calculator
  - Date/Time
  - Weather

Tool Settings:
  Max Tool Calls: 5
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

1. Select multiple agents (checkbox)
2. Click **Bulk Actions** → **Edit**
3. Choose fields to update:
   - Status
   - Model
   - Team
   - Visibility

4. Apply changes

## Agent Status Management

### Agent Statuses

**Active:**
- Agent is operational
- Can receive messages
- Appears in user interface

**Inactive:**
- Agent is disabled
- Cannot receive messages
- Hidden from users
- Preserves configuration

**Published:**
- Agent is in marketplace
- Available to all teams
- Read-only for non-owners

**Archived:**
- Agent is archived
- Cannot be used
- Preserves history
- Can be restored

### Change Agent Status

**Activate Agent:**
```bash
1. Select agent
2. Click "Activate"
3. Confirm activation
```

**Deactivate Agent:**
```bash
1. Select agent
2. Click "Deactivate"
3. Confirm deactivation
4. Optionally notify team
```

**Publish Agent:**
```bash
1. Select agent
2. Click "Publish"
3. Review agent details
4. Set marketplace visibility
5. Confirm publication
```

**Archive Agent:**
```bash
1. Select agent
2. Click "Archive"
3. Confirm archival
4. Agent moved to archive
```

## Monitoring Agent Usage

### Usage Statistics

**Overview Metrics:**
- Total conversations
- Total messages
- Active users
- Average response time
- Token usage
- Cost

**Time-based Metrics:**
- Daily/weekly/monthly trends
- Peak usage times
- Growth rate

**Performance Metrics:**
- Response time (avg, p50, p95, p99)
- Success rate
- Error rate
- Tool usage

### View Agent Statistics

1. Select agent
2. Click **Statistics** tab
3. View metrics:
   - **Usage**: Conversations, messages, users
   - **Performance**: Response time, success rate
   - **Costs**: Token usage, estimated cost
   - **Tools**: Tool call frequency
   - **Knowledge**: KB query stats

4. Filter by date range
5. Export statistics (CSV, PDF)

### Usage Reports

**Generate Report:**
```bash
1. Navigate to Reports
2. Select "Agent Usage Report"
3. Choose date range
4. Select agents (or all)
5. Choose metrics
6. Generate report
7. Download or email
```

**Report Contents:**
- Executive summary
- Usage trends
- Top agents by usage
- Cost analysis
- Performance metrics
- Recommendations

## Knowledge Base Management

### Attach Knowledge Bases

1. Edit agent
2. Go to **Knowledge Bases** section
3. Click **Add Knowledge Base**
4. Select knowledge bases
5. Configure search settings:
   - Top K results
   - Score threshold
   - Rerank enabled

6. Save changes

### Remove Knowledge Bases

1. Edit agent
2. Go to **Knowledge Bases** section
3. Find knowledge base
4. Click **Remove**
5. Confirm removal

### Knowledge Base Priority

Set priority for multiple knowledge bases:

1. Edit agent
2. Go to **Knowledge Bases** section
3. Drag to reorder (higher = higher priority)
4. Save changes

## Tool Management

### Enable Tools

1. Edit agent
2. Go to **Tools** section
3. Browse available tools
4. Toggle tools on/off:
   - Web Search
   - Calculator
   - Date/Time
   - Weather
   - Custom tools

5. Configure tool settings
6. Save changes

### Tool Configuration

**Web Search:**
```yaml
Enabled: true
Max Results: 5
Search Engine: Google
Safe Search: Moderate
```

**Calculator:**
```yaml
Enabled: true
Precision: 10 decimals
Allow Complex: true
```

**Custom Tools:**
```yaml
Tool Name: CRM Lookup
Endpoint: https://api.example.com/crm
Auth: API Key
Timeout: 30s
```

## Agent Limits

### Set Team Limits

1. Navigate to **Teams** → Select team
2. Go to **Limits** tab
3. Configure agent limits:
   - Max agents per team
   - Max conversations per agent
   - Max messages per conversation
   - Max tokens per day
   - Max cost per month

4. Save limits

### Limit Types

**Resource Limits:**
```yaml
Max Agents: 10
Max Knowledge Bases per Agent: 5
Max Tools per Agent: 10
Max Conversations: 1000
```

**Usage Limits:**
```yaml
Max Messages per Day: 10000
Max Tokens per Day: 1000000
Max Cost per Month: $500
```

**Rate Limits:**
```yaml
Messages per Minute: 60
Conversations per Hour: 100
```

## Agent Templates

### Create Template

1. Select well-configured agent
2. Click **Save as Template**
3. Enter template details:
   - Name
   - Description
   - Category
   - Visibility

4. Save template

### Use Template

1. Click **Create Agent**
2. Select **From Template**
3. Choose template
4. Customize settings
5. Create agent

### Template Categories

- **Customer Support**
- **Sales Assistant**
- **Technical Support**
- **Content Creation**
- **Data Analysis**
- **Code Assistant**
- **General Purpose**

## Troubleshooting

### Agent Not Responding

**Symptoms:**
- Messages sent but no response
- Timeout errors

**Solutions:**

1. **Check agent status:**
   - Verify agent is active
   - Check model availability

2. **Check model configuration:**
   - Verify API key is valid
   - Test model connectivity
   - Check rate limits

3. **Check knowledge bases:**
   - Verify KBs are indexed
   - Check search is working

4. **Check logs:**
   ```bash
   Admin → Logs → Agent Logs
   Filter by agent ID
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

4. **Enable RAG citation mode:**
   - Forces agent to cite sources
   - Reduces hallucinations

### High Costs

**Symptoms:**
- Unexpected high token usage
- Cost alerts triggered

**Solutions:**

1. **Set token limits:**
   - Reduce max_tokens
   - Set daily limits
   - Enable cost alerts

2. **Optimize prompts:**
   - Shorter system prompts
   - Reduce context length
   - Use cheaper models for simple tasks

3. **Review usage patterns:**
   - Identify high-usage agents
   - Check for abuse
   - Optimize workflows

4. **Use caching:**
   - Enable prompt caching
   - Cache knowledge base results

## Best Practices

### Agent Design

**✅ Do:**
- Write clear, specific system prompts
- Test agents thoroughly before deployment
- Use appropriate models for tasks
- Enable RAG for factual accuracy
- Set reasonable token limits
- Monitor usage and costs
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

**Available Actions:**
- Activate/Deactivate
- Change model
- Update team
- Archive
- Delete
- Export configuration

**Perform Bulk Action:**
```bash
1. Select agents (checkbox)
2. Click "Bulk Actions"
3. Choose action
4. Configure options
5. Review changes
6. Confirm execution
```

### Import/Export

**Export Agents:**
```bash
1. Select agents
2. Click "Export"
3. Choose format (JSON, CSV)
4. Download file
```

**Import Agents:**
```bash
1. Click "Import"
2. Upload file (JSON)
3. Review agents
4. Map teams
5. Confirm import
```

## API Access

### Manage Agents via API

See [Agents API](../../api-reference/endpoints/agents.md) for details.

**Common Operations:**
```python
# List all agents (admin)
agents = api.get("/api/v1/agents", params={"all_teams": True})

# Create agent for team
agent = api.post("/api/v1/agents", json={
    "name": "Support Agent",
    "team_id": "team-123",
    "model_id": "model-456"
})

# Update agent
api.patch(f"/api/v1/agents/{agent_id}", json={
    "is_active": True
})

# Get agent statistics
stats = api.get(f"/api/v1/agents/{agent_id}/stats")
```

## Related Documentation

- [Agents API](../../api-reference/endpoints/agents.md) - API reference
- [Agent Configuration](../../user-guide/agents/agent-configuration.md) - User guide
- [Model Management](../models/model-management.md) - Model admin
- [Team Management](../teams/team-management.md) - Team admin

---

**Last Updated**: 2026-02-11
