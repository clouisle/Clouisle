# Workflow Management

This guide covers how to manage workflows as an administrator.

## Overview

As an administrator, you can:

- **View all workflows**: Access workflows across all teams
- **Create workflows**: Set up workflows for teams
- **Monitor execution**: Track workflow runs
- **Manage triggers**: Configure manual and webhook triggers
- **Troubleshoot**: Debug failed executions

## Accessing Workflow Management

### Admin Dashboard

1. Log in as administrator
2. Navigate to **Apps** in the sidebar (**Resources** section)
3. View the workflow management interface

### Workflow List View

The workflow list shows:

- **Workflow name and description**
- **Team ownership**
- **Status** (Draft, Published, Archived)
- **Trigger type** (Manual, Webhook, Cron; wire value `cron`)
- **Execution count**
- **Last execution**
- **Created date**

**Filters:**
- Team
- Status (Draft, Published, Archived)
- Trigger type

**Search:**
- Search by workflow name or description

## Creating Workflows

### Create Workflow for Team

1. Click **Create Workflow** button
2. Fill in workflow details:
   - **Name**: Workflow display name
   - **Description**: Workflow purpose
   - **Team**: Select team owner
   - **Trigger**: Manual, Webhook, or Cron (`cron` on the API)

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

The editor provides these node types:

- **LLM** (`llm`): Call a language model
- **Media Generation** (`media_generation`): Generate media with a compatible model
- **Condition** (`condition`): Branch on a condition
- **Question Classifier** (`question_classifier`): Classify input questions
- **Iteration** (`iteration`): Iterate over items
- **Loop** (`loop`): Repeat a branch
- **Pause** (`pause`): Wait for approval or variable input
- **Code** (`code`): Execute custom code
- **Template** (`template`): Render a template
- **File to URL** (`file_to_url`): Convert a file asset to a URL
- **Variable Aggregator** (`variable_aggregator`): Combine variables
- **Variable Assignment** (`variable_assignment`): Assign variables
- **Parameter Extractor** (`parameter_extractor`): Extract structured parameters
- **Sub-workflow** (`sub_workflow`): Invoke another workflow
- **Agent** (`agent`): Invoke an agent
- **Tool** (`tool`): Execute a tool
- **Knowledge Retrieval** (`knowledge_retrieval`): Retrieve knowledge-base content
- **Answer** (`answer`): Return the workflow answer

## Workflow Configuration

### Basic Settings

```yaml
Name: Customer Inquiry Processing
Description: Process and route customer inquiries
Team: Support Team
Status: draft            # draft, published, or archived
Version: 1.2.0
```

### Trigger Configuration

**Manual Trigger:**
```yaml
Type: manual
Requires Input: true
```

**Webhook Trigger:**
```yaml
Type: webhook
Endpoint: POST /api/v1/workflows/webhook/{webhook_token}
Authentication: Required `Bearer clou_...` API key in Authorization header
```

**Cron Trigger:**
```yaml
Type: cron
Cron: "0 9 * * 1-5"  # 9 AM weekdays
```

The `workflow.check_scheduled` task implements cron evaluation for published workflows. It is not included in the supplied Celery Beat schedule by default, so operators who need cron execution must schedule this task (for example every minute) in their deployment. A stored `trigger_type: cron` alone does not run a workflow.

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

> **Note:** Not implemented / Roadmap: there is no real-time execution dashboard (running/queued executions, success rate, average execution time, cost). Run statistics are available via `GET /api/v1/workflows/runs/stats` (team-filterable) and `GET /api/v1/workflows/{workflow_id}/stats` (+ `/stats/trends`).

### View Execution History

1. Select workflow
2. Click **Execution History** tab
3. View run list:
   - Run ID
   - Status (`running`, `success`, `failed`, etc.)
   - Start time
   - Duration
   - Trigger source
   - Input/Output

Run history endpoints: `GET /api/v1/workflows/runs`, `GET /api/v1/workflows/{workflow_id}/runs`, and `GET /api/v1/workflows/{workflow_id}/runs/mine` (own runs).

4. Click a run to view details

### Execution Details

**Execution Information:**
```yaml
Run ID: run-789
Workflow: Customer Inquiry Processing
Status: success
Started: 2026-02-11 14:30:00
Completed: 2026-02-11 14:30:45
Duration: 45 seconds
Trigger: webhook
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

Run details are available via `GET /api/v1/workflows/runs/{run_id}` (with `GET /runs/{run_id}/nodes` for node-level execution); streamed node events via `GET /api/v1/workflows/runs/{run_id}/stream`.

## Workflow Status Management

### Workflow Statuses

**Draft:**
- Workflow is being edited
- Cannot be triggered
- Only visible to editors

**Published:**
- Workflow is operational
- Can be triggered
- Appears in user interface

**Archived:**
- Workflow is archived
- Not visible in normal lists
- Configuration preserved

### Change Workflow Status

**Publish Workflow:**
```bash
1. Select workflow
2. Click "Publish"
3. Confirm publication
4. Workflow status becomes "published"
```

**Unpublish Workflow:**
```bash
1. Select workflow
2. Click "Unpublish"
3. Confirm unpublish
4. Workflow status returns to "draft"
```

> **Note:** There is no active/inactive status. Archiving is a model-level status (`archived`) applied via updates; publish/unpublish are the admin lifecycle actions (`POST /api/v1/admin/workflows/{id}/publish` and `/unpublish`).

## Webhook Management

### View Webhooks

A workflow with trigger type `webhook` gets a webhook token. The endpoint is:

```
POST /api/v1/workflows/webhook/{webhook_token}
```

### Create or Regenerate a Webhook Token

1. Edit workflow
2. Set trigger type to **Webhook**
3. Save — a `webhook_token` is generated
4. Regenerate the token anytime via `POST /api/v1/workflows/{workflow_id}/regenerate-webhook-token`

### Webhook Configuration

```yaml
Endpoint: POST /api/v1/workflows/webhook/{webhook_token}
Authentication: Required API key in the Authorization header
Payload: workflow inputs (raw JSON or {"inputs": {...}})
```

Requests must present a valid `clou_` API key in the `Authorization` header; the webhook token is matched with constant-time comparison.

> **Note:** Not implemented / Roadmap: `wh_...`/`whsec_...` credential pairs, IP allowlists, per-webhook rate limits, retry policies, and webhook request logs are not available.

### Test Webhook

```bash
curl -X POST "https://your-domain.com/api/v1/workflows/webhook/TOKEN" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_email": "test@example.com",
    "inquiry_text": "Test inquiry",
    "priority": "low"
  }'
```

### Webhook Logs

> **Note:** Not implemented / Roadmap. There is no per-webhook request log view. Triggered runs appear in the workflow run history (`GET /api/v1/workflows/runs`).

## Schedule Management

### View Schedules

There is no schedule-management UI or next-run listing. Cron configuration is stored in the workflow's `trigger_config`; operators must ensure `workflow.check_scheduled` is dispatched periodically.

## Workflow Limits

### Set Team Limits

> **Note:** Not implemented / Roadmap. There are no per-team workflow quotas (max workflows, max executions per day, concurrency, execution time, cost caps) and no resource/execution/cost limit configuration.

## Troubleshooting

### Workflow Execution Failed

**Symptoms:**
- Run status is "failed"
- Error message in run details

**Solutions:**

1. **Check run details:**
   - Open the failed run in **Execution History**
   - Review node executions and error details

2. **Common errors:**
   - **Node timeout**: Increase timeout or optimize node
   - **Invalid input**: Validate input schema
   - **API error**: Check API credentials and connectivity
   - **LLM error**: Verify model availability and API key
   - **Tool error**: Check tool configuration

3. **Re-run:**
   - Trigger the workflow again (`POST /api/v1/workflows/{workflow_id}/run`) with corrected input

### Webhook Not Triggering

**Symptoms:**
- Webhook requests not received
- No runs triggered

**Solutions:**

1. **Verify webhook endpoint:**
   - Confirm the workflow's trigger type is `webhook`
   - POST to `/api/v1/workflows/webhook/{webhook_token}`; test with curl

2. **Check authentication:**
   - If the trigger config defines an API key, verify it is sent in the `Authorization` header

3. **Check the workflow status:**
   - The workflow must be published; unpublished workflows reject webhook triggers

### Schedule Not Running

**Symptoms:**
- Scheduled workflow not executing
- Missed executions

**Solutions:**
1. Confirm the workflow is `published` and `trigger_type` is `cron`.
2. Confirm `trigger_config.cron` contains a valid cron expression.
3. Confirm Celery Beat or another scheduler dispatches `workflow.check_scheduled` periodically; the supplied Beat schedule does not add it automatically.

### High Execution Time

**Symptoms:**
- Workflows taking too long
- Timeouts

**Solutions:**

1. **Optimize nodes:**
   - Reduce LLM max_tokens
   - Use faster models
   - Optimize tool calls

2. **Use parallel execution:**
   - Identify independent nodes
   - Use Parallel node
   - Execute concurrently

3. **Add timeouts:**
   - Set node timeouts
   - Handle timeout gracefully

4. **Monitor performance:**
   - Review run duration in run history (`GET /api/v1/workflows/runs/stats`, `GET /api/v1/workflows/{workflow_id}/stats`)

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
- Use webhook authentication (API key in Authorization header)
- Regenerate webhook tokens when compromised
- Enable audit logging
- Monitor for abuse

**❌ Don't:**
- Trust input blindly
- Use static tokens forever
- Disable audit logs
- Ignore suspicious activity

> **Note:** Not implemented / Roadmap: webhook IP allowlists and rate limits are not available.

## Bulk Operations

### Bulk Actions

> **Note:** Not implemented / Roadmap. There are no bulk workflow actions (activate/deactivate, change team, archive, delete, export configuration). Lifecycle operations are performed per workflow: publish, unpublish, duplicate, and delete.

### Import/Export

> **Note:** Not implemented / Roadmap. There is no workflow import/export (JSON/YAML).

## API Access

### Manage Workflows via API

Admin workflow endpoints live under `/api/v1/admin/workflows` and require `admin:app:*` permissions. See [Workflows API](../../api-reference/endpoints/workflows.md) for details.

**Common Operations:**
```python
# List workflows (admin) — no all_teams parameter
workflows = api.get("/api/v1/admin/workflows", params={"page": 1, "page_size": 20})

# Create workflow for team
workflow = api.post("/api/v1/admin/workflows", json={
    "name": "Customer Processing",
    "team_id": "team-123",
    "definition": {...}
})

# Run workflow (runs, not /execute)
run = api.post(f"/api/v1/workflows/{workflow_id}/run", json={
    "input": {"customer_email": "test@example.com"}
})

# Get run status
status = api.get(f"/api/v1/workflows/runs/{run_id}")
# or for the current user's own runs:
status = api.get(f"/api/v1/workflows/{workflow_id}/runs/mine/{run_id}")
```

## Related Documentation

- [Workflows API](../../api-reference/endpoints/workflows.md) - API reference
- [Running Workflows](../../user-guide/workflows/running-workflows.md) - User guide
- [Workflow History](../../user-guide/workflows/workflow-history.md) - User guide
- [Team Management](../teams/team-management.md) - Team admin

---

**Last Updated**: 2026-02-11
