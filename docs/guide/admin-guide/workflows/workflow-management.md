# Workflow Management

This guide covers how to manage workflows as an administrator.

## Overview

As an administrator, you can:

- **View all workflows**: Access workflows across all teams
- **Create workflows**: Set up workflows for teams
- **Monitor execution**: Track workflow runs and performance
- **Manage triggers**: Configure webhook and schedule triggers
- **Set limits**: Control workflow resource usage
- **Troubleshoot**: Debug failed executions

## Accessing Workflow Management

### Admin Dashboard

1. Log in as administrator
2. Navigate to **Admin** → **Workflows**
3. View workflow management interface

### Workflow List View

The workflow list shows:

- **Workflow name and description**
- **Team ownership**
- **Status** (Active, Inactive, Draft)
- **Trigger type** (Manual, Webhook, Schedule)
- **Execution count**
- **Success rate**
- **Last execution**
- **Created date**

**Filters:**
- Team
- Status (Active, Inactive, Draft)
- Trigger type
- Date range
- Success/failure status

**Search:**
- Search by workflow name or description

## Creating Workflows

### Create Workflow for Team

1. Click **Create Workflow** button
2. Fill in workflow details:
   - **Name**: Workflow display name
   - **Description**: Workflow purpose
   - **Team**: Select team owner
   - **Trigger**: Manual, Webhook, or Schedule

3. Design workflow:
   - Add nodes (Start, LLM, Tool, Condition, etc.)
   - Connect nodes
   - Configure node settings
   - Set variables

4. Configure triggers:
   - **Manual**: No additional config
   - **Webhook**: Generate webhook URL
   - **Schedule**: Set cron expression

5. Test workflow
6. Click **Save Workflow**

### Workflow Node Types

**Input/Output Nodes:**
- **Start**: Workflow entry point
- **End**: Workflow exit point
- **Input**: Accept external input
- **Output**: Return results

**Processing Nodes:**
- **LLM**: Call language model
- **Tool**: Execute tool (web search, calculator, etc.)
- **HTTP**: Make HTTP requests
- **Transform**: Transform data
- **Code**: Execute custom code

**Control Flow:**
- **Condition**: Branch based on condition
- **Loop**: Iterate over items
- **Parallel**: Execute nodes in parallel
- **Wait**: Delay execution

**Integration:**
- **Database**: Query database
- **API**: Call external API
- **Email**: Send email
- **Webhook**: Trigger webhook

## Workflow Configuration

### Basic Settings

```yaml
Name: Customer Inquiry Processing
Description: Process and route customer inquiries
Team: Support Team
Status: Active
Version: 1.2.0
```

### Trigger Configuration

**Manual Trigger:**
```yaml
Type: Manual
Requires Input: true
Input Schema:
  customer_email: string
  inquiry_text: string
  priority: enum [low, medium, high]
```

**Webhook Trigger:**
```yaml
Type: Webhook
URL: https://your-domain.com/api/v1/workflows/wf-123/trigger
Method: POST
Authentication: API Key
Headers:
  X-Webhook-Secret: secret-key
```

**Schedule Trigger:**
```yaml
Type: Schedule
Cron: "0 9 * * 1-5"  # 9 AM weekdays
Timezone: America/New_York
Enabled: true
```

### Node Configuration Example

**LLM Node:**
```yaml
Node ID: llm-001
Type: LLM
Name: Analyze Inquiry
Model: GPT-4 Turbo
Prompt: |
  Analyze the following customer inquiry:
  {{inquiry_text}}

  Classify the inquiry type and urgency.
Temperature: 0.3
Max Tokens: 500
Output Variable: analysis_result
```

**Condition Node:**
```yaml
Node ID: condition-001
Type: Condition
Name: Check Priority
Condition: analysis_result.urgency == "high"
True Branch: notify-manager
False Branch: assign-agent
```

**Tool Node:**
```yaml
Node ID: tool-001
Type: Tool
Name: Search Knowledge Base
Tool: kb_search
Parameters:
  query: "{{inquiry_text}}"
  kb_id: "kb-456"
  top_k: 3
Output Variable: kb_results
```

## Monitoring Workflows

### Execution Dashboard

**Overview Metrics:**
- Total executions (24h, 7d, 30d)
- Success rate
- Average execution time
- Active workflows
- Failed executions
- Cost

**Real-time Monitoring:**
- Currently running workflows
- Queued executions
- Recent completions
- Recent failures

### View Execution History

1. Select workflow
2. Click **Execution History** tab
3. View execution list:
   - Execution ID
   - Status (Running, Completed, Failed)
   - Start time
   - Duration
   - Trigger source
   - Input/Output

4. Filter by:
   - Status
   - Date range
   - Trigger type

5. Click execution to view details

### Execution Details

**Execution Information:**
```yaml
Execution ID: exec-789
Workflow: Customer Inquiry Processing
Status: Completed
Started: 2026-02-11 14:30:00
Completed: 2026-02-11 14:30:45
Duration: 45 seconds
Trigger: Webhook
```

**Node Execution Timeline:**
```
[Start] → 0s
[LLM: Analyze] → 2s (completed in 3s)
[Condition: Check Priority] → 5s (completed in 0.1s)
[Tool: Search KB] → 5.1s (completed in 2s)
[LLM: Generate Response] → 7.1s (completed in 4s)
[End] → 11.1s
```

**Input/Output:**
```json
Input:
{
  "customer_email": "customer@example.com",
  "inquiry_text": "How do I reset my password?",
  "priority": "medium"
}

Output:
{
  "response": "To reset your password, visit...",
  "kb_articles": ["article-123", "article-456"],
  "assigned_agent": "agent-789"
}
```

**Logs:**
```
[14:30:00] Workflow started
[14:30:02] LLM node: Analyzing inquiry
[14:30:05] LLM node: Analysis complete
[14:30:05] Condition node: Priority is medium
[14:30:05] Tool node: Searching knowledge base
[14:30:07] Tool node: Found 3 articles
[14:30:07] LLM node: Generating response
[14:30:11] LLM node: Response generated
[14:30:11] Workflow completed successfully
```

## Workflow Status Management

### Workflow Statuses

**Active:**
- Workflow is operational
- Can be triggered
- Appears in user interface

**Inactive:**
- Workflow is disabled
- Cannot be triggered
- Hidden from users
- Preserves configuration

**Draft:**
- Workflow is being edited
- Cannot be triggered
- Only visible to editors

### Change Workflow Status

**Activate Workflow:**
```bash
1. Select workflow
2. Click "Activate"
3. Verify configuration
4. Confirm activation
```

**Deactivate Workflow:**
```bash
1. Select workflow
2. Click "Deactivate"
3. Optionally stop running executions
4. Confirm deactivation
```

## Webhook Management

### View Webhooks

1. Navigate to **Webhooks** tab
2. View webhook list:
   - Webhook URL
   - Workflow name
   - Status (Active, Inactive)
   - Request count
   - Last triggered
   - Success rate

### Create Webhook

1. Edit workflow
2. Set trigger type to **Webhook**
3. Click **Generate Webhook URL**
4. Configure webhook:
   - Authentication method
   - Secret key
   - Allowed IPs
   - Rate limit

5. Save webhook

### Webhook Configuration

```yaml
Webhook URL: https://your-domain.com/api/v1/workflows/wf-123/trigger
Authentication: API Key
API Key: wh_abc123...
Secret: whsec_xyz789...
Allowed IPs:
  - 192.168.1.0/24
  - 10.0.0.0/8
Rate Limit: 100 requests/minute
Retry Policy:
  Max Retries: 3
  Backoff: Exponential
```

### Test Webhook

```bash
curl -X POST "https://your-domain.com/api/v1/workflows/wf-123/trigger" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "X-Webhook-Secret: whsec_xyz789..." \
  -H "Content-Type: application/json" \
  -d '{
    "customer_email": "test@example.com",
    "inquiry_text": "Test inquiry",
    "priority": "low"
  }'
```

### Webhook Logs

View webhook request logs:

1. Select webhook
2. Click **Logs** tab
3. View request history:
   - Timestamp
   - Source IP
   - Request payload
   - Response status
   - Execution ID
   - Error (if any)

## Schedule Management

### View Schedules

1. Navigate to **Schedules** tab
2. View schedule list:
   - Workflow name
   - Cron expression
   - Next run time
   - Last run time
   - Status (Active, Paused)
   - Success rate

### Create Schedule

1. Edit workflow
2. Set trigger type to **Schedule**
3. Configure schedule:
   - Cron expression
   - Timezone
   - Start date (optional)
   - End date (optional)

4. Test cron expression
5. Save schedule

### Schedule Configuration

```yaml
Cron Expression: "0 9 * * 1-5"
Description: Every weekday at 9 AM
Timezone: America/New_York
Start Date: 2026-02-01
End Date: 2026-12-31
Enabled: true
```

**Common Cron Patterns:**
```
Every hour:        0 * * * *
Every day at 9 AM: 0 9 * * *
Every Monday:      0 0 * * 1
Every 15 minutes:  */15 * * * *
First of month:    0 0 1 * *
```

### Pause/Resume Schedule

**Pause Schedule:**
```bash
1. Select schedule
2. Click "Pause"
3. Confirm pause
```

**Resume Schedule:**
```bash
1. Select paused schedule
2. Click "Resume"
3. Confirm resume
```

## Workflow Limits

### Set Team Limits

1. Navigate to **Teams** → Select team
2. Go to **Limits** tab
3. Configure workflow limits:
   - Max workflows per team
   - Max executions per day
   - Max concurrent executions
   - Max execution time
   - Max cost per month

4. Save limits

### Limit Types

**Resource Limits:**
```yaml
Max Workflows: 50
Max Nodes per Workflow: 100
Max Webhooks: 20
Max Schedules: 10
```

**Execution Limits:**
```yaml
Max Executions per Day: 10000
Max Concurrent Executions: 50
Max Execution Time: 300 seconds
Max Retries: 3
```

**Cost Limits:**
```yaml
Max LLM Calls per Execution: 10
Max Tokens per Execution: 10000
Max Cost per Month: $1000
```

## Troubleshooting

### Workflow Execution Failed

**Symptoms:**
- Execution status is "Failed"
- Error message in logs

**Solutions:**

1. **Check execution logs:**
   ```bash
   Admin → Workflows → Select workflow
   Execution History → Select failed execution
   View logs and error details
   ```

2. **Common errors:**
   - **Node timeout**: Increase timeout or optimize node
   - **Invalid input**: Validate input schema
   - **API error**: Check API credentials and connectivity
   - **LLM error**: Verify model availability and API key
   - **Tool error**: Check tool configuration

3. **Retry execution:**
   ```bash
   Select failed execution
   Click "Retry"
   Optionally modify input
   Confirm retry
   ```

### Webhook Not Triggering

**Symptoms:**
- Webhook requests not received
- No executions triggered

**Solutions:**

1. **Verify webhook URL:**
   - Check URL is correct
   - Test with curl

2. **Check authentication:**
   - Verify API key is valid
   - Check secret matches

3. **Check IP whitelist:**
   - Verify source IP is allowed
   - Add IP to whitelist if needed

4. **Check webhook logs:**
   ```bash
   Admin → Webhooks → Select webhook
   Logs → View recent requests
   Check for errors
   ```

### Schedule Not Running

**Symptoms:**
- Scheduled workflow not executing
- Missed executions

**Solutions:**

1. **Check schedule status:**
   - Verify schedule is active
   - Check cron expression is valid

2. **Check timezone:**
   - Verify timezone is correct
   - Account for DST changes

3. **Check execution limits:**
   - Verify not hitting daily limit
   - Check concurrent execution limit

4. **Check schedule logs:**
   ```bash
   Admin → Schedules → Select schedule
   Execution History → View recent runs
   ```

### High Execution Time

**Symptoms:**
- Workflows taking too long
- Timeouts

**Solutions:**

1. **Optimize nodes:**
   - Reduce LLM max_tokens
   - Use faster models
   - Optimize tool calls
   - Add caching

2. **Use parallel execution:**
   - Identify independent nodes
   - Use Parallel node
   - Execute concurrently

3. **Add timeouts:**
   - Set node timeouts
   - Handle timeout gracefully
   - Add retry logic

4. **Monitor performance:**
   ```bash
   Admin → Workflows → Select workflow
   Statistics → View performance metrics
   Identify slow nodes
   ```

## Best Practices

### Workflow Design

**✅ Do:**
- Keep workflows simple and focused
- Use descriptive node names
- Add error handling
- Test thoroughly before activation
- Document workflow purpose
- Use variables for reusability
- Add logging for debugging
- Set appropriate timeouts

**❌ Don't:**
- Create overly complex workflows
- Use vague node names
- Ignore error cases
- Deploy untested workflows
- Hardcode values
- Skip documentation
- Forget to add logging
- Set unlimited timeouts

### Performance

**✅ Do:**
- Use parallel execution where possible
- Cache repeated operations
- Optimize LLM prompts
- Use appropriate models
- Set reasonable timeouts
- Monitor execution times
- Optimize tool calls

**❌ Don't:**
- Execute everything sequentially
- Repeat expensive operations
- Use verbose prompts
- Use expensive models for simple tasks
- Set very long timeouts
- Ignore performance metrics

### Security

**✅ Do:**
- Use webhook authentication
- Validate input data
- Limit webhook IPs
- Rotate secrets regularly
- Enable audit logging
- Monitor for abuse
- Set rate limits

**❌ Don't:**
- Allow unauthenticated webhooks
- Trust input blindly
- Allow all IPs
- Use static secrets forever
- Disable audit logs
- Ignore suspicious activity
- Allow unlimited requests

## Bulk Operations

### Bulk Actions

**Available Actions:**
- Activate/Deactivate
- Change team
- Archive
- Delete
- Export configuration

**Perform Bulk Action:**
```bash
1. Select workflows (checkbox)
2. Click "Bulk Actions"
3. Choose action
4. Configure options
5. Review changes
6. Confirm execution
```

### Import/Export

**Export Workflows:**
```bash
1. Select workflows
2. Click "Export"
3. Choose format (JSON, YAML)
4. Download file
```

**Import Workflows:**
```bash
1. Click "Import"
2. Upload file (JSON/YAML)
3. Review workflows
4. Map teams
5. Confirm import
```

## API Access

### Manage Workflows via API

See [Workflows API](../../api-reference/endpoints/workflows.md) for details.

**Common Operations:**
```python
# List all workflows (admin)
workflows = api.get("/api/v1/workflows", params={"all_teams": True})

# Create workflow for team
workflow = api.post("/api/v1/workflows", json={
    "name": "Customer Processing",
    "team_id": "team-123",
    "definition": {...}
})

# Execute workflow
execution = api.post(f"/api/v1/workflows/{workflow_id}/execute", json={
    "input": {"customer_email": "test@example.com"}
})

# Get execution status
status = api.get(f"/api/v1/workflows/executions/{execution_id}")
```

## Related Documentation

- [Workflows API](../../api-reference/endpoints/workflows.md) - API reference
- [Running Workflows](../../user-guide/workflows/running-workflows.md) - User guide
- [Workflow History](../../user-guide/workflows/workflow-history.md) - User guide
- [Team Management](../teams/team-management.md) - Team admin

---

**Last Updated**: 2026-02-11
