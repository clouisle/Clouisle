# Running Workflows

This guide explains how to run and execute workflows in Clouisle.

## Overview

Workflows in Clouisle are automated processes that can:
- Execute multiple steps in sequence
- Make decisions based on conditions
- Call APIs and use tools
- Process data and generate outputs
- Run manually or via webhook triggers

## Accessing Workflows

### From Platform Interface

1. Navigate to **Apps** or **Workflows** section
2. Browse available workflows
3. Click on a workflow card to open it
4. Click **"Run"** button

### Workflow List

The list shows:

| Column | Description |
|--------|-------------|
| **Name** | Workflow name |
| **Team** | Team that owns the workflow |
| **Status** | Draft or Published |
| **Last Run** | Last execution time |
| **Actions** | Run, View, Edit |

## Running a Workflow

### Manual Execution

**Steps:**

1. Open the workflow
2. Click **"Run"** button
3. If the workflow has input variables:
   - Fill in required inputs
   - Review optional inputs
   - Click **"Start"**
4. Watch the execution in real-time
5. View the results when complete

### Input Variables

Workflows may require inputs:

**Example Input Form:**
```
Workflow: Document Summarizer

Required Inputs:
┌─────────────────────────────────────┐
│ Document URL: [________________]    │
└─────────────────────────────────────┘

Optional Inputs:
┌─────────────────────────────────────┐
│ Language: [English ▼]              │
└─────────────────────────────────────┘

[Cancel]  [Run Workflow]
```

**Input Types:**
- **Text**: Free-form text input
- **Number**: Numeric values
- **Select**: Dropdown options
- **Boolean**: Yes/No checkbox

## Watching Execution

### Real-Time Progress

**Execution View:**
```
┌─────────────────────────────────────────┐
│ Document Summarizer                      │
│ Status: Running... ⏳                    │
│ Started: 2026-02-11 10:00:00            │
├─────────────────────────────────────────┤
│                                         │
│ ✅ Start                                │
│ ✅ Fetch Document                       │
│ ⏳ Extract Text (in progress...)        │
│ ⏸️  End                                 │
│                                         │
├─────────────────────────────────────────┤
│ [Stop Execution]                        │
└─────────────────────────────────────────┘
```

**Node Status Icons:**
- ⏸️ **Pending**: Not started yet
- ⏳ **Running**: Currently executing
- ✅ **Success**: Completed successfully
- ❌ **Failed**: Execution failed
- ⏭️ **Skipped**: Skipped (conditional)

### Execution Details

Click on a node to see details:

**Node Details Panel:**
```
Node: Extract Text
Status: Running ⏳
Duration: 12s

Input:
{
  "url": "https://example.com/doc.pdf",
  "format": "text"
}

Output:
(waiting for completion...)
```

### Streaming Output

LLM nodes stream their output in real-time; the execution view shows partial content while running.

## Execution Results

### Success

**Result View:**
```
┌─────────────────────────────────────────┐
│ Execution Completed ✅                   │
│                                         │
│ Duration: 1m 23s                        │
│ Nodes Executed: 6/6                    │
│ Status: Success                         │
├─────────────────────────────────────────┤
│ Output:                                 │
│ Summary: The document provides...      │
│                                         │
└─────────────────────────────────────────┘
```

### Failure

**Error View:**
```
┌─────────────────────────────────────────┐
│ Execution Failed ❌                      │
│                                         │
│ Duration: 0m 45s                        │
│ Failed at: Extract Text (Node 3)       │
├─────────────────────────────────────────┤
│ Error:                                  │
│ Failed to extract text from document   │
│                                         │
└─────────────────────────────────────────┘
```

**Common Errors:**
- Invalid input format
- API call failed
- Timeout exceeded
- Resource not found
- Permission denied

## Stopping Execution

### Manual Stop

**During execution:**
1. Click **"Stop Execution"** button
2. Confirm the stop action
3. The workflow stops at the current node

## Workflow Triggers

### Manual Trigger

Run the workflow manually from the UI or API:

```bash
curl -X POST "https://your-domain.com/api/v1/workflows/{id}/run" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": {
      "var1": "value1",
      "var2": "value2"
    }
  }'
```

### Webhook Trigger

Run the workflow via HTTP request:

**Webhook URL:**
```
POST https://your-domain.com/api/v1/workflows/webhook/{webhook_token}
Content-Type: application/json

{
  "input_var1": "value1",
  "input_var2": "value2"
}
```

The webhook token is generated per workflow (regenerable via `POST /api/v1/workflows/{id}/regenerate-webhook-token`). The workflow must have a webhook trigger type enabled, and the request body (or a nested `{"inputs": {...}}` payload) becomes the workflow's input variables.

**Response:**
```json
{
  "code": 0,
  "data": {
    "run_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "running"
  },
  "msg": "..."
}
```

### Scheduled Trigger

> **Note:** `trigger_type` supports a cron value, but **no scheduler is implemented** — scheduled executions are **not available** in the current version (Roadmap).

## Workflow Variables

### Input Variables

Provided when starting the workflow:

**Example:**
```json
{
  "document_url": "https://example.com/doc.pdf",
  "summary_length": "short",
  "language": "en"
}
```

### Output Variables

Generated during execution (from the end node / node outputs).

## Best Practices

### Providing Inputs

**✅ Do:**
- Provide all required inputs
- Use correct data types
- Test with sample data first

**❌ Don't:**
- Leave required fields empty
- Use invalid formats

### Monitoring Execution

**✅ Do:**
- Watch the execution progress
- Check node outputs
- Stop if behavior is unexpected

**❌ Don't:**
- Ignore error messages
- Skip result verification

### Handling Errors

**✅ Do:**
- Read error messages carefully
- Check input values
- Review node configuration
- Try again with corrected inputs

**❌ Don't:**
- Ignore errors and retry blindly
- Skip error logs

## Troubleshooting

### Workflow Won't Start

**Problem**: Cannot start workflow execution

**Solutions:**
1. Check if the workflow is published
2. Verify you have permission to run
3. Ensure all required inputs are provided
4. Refresh the page and try again

### Execution Stuck

**Problem**: Workflow execution not progressing

**Solutions:**
1. Check if a node is waiting for an external response
2. Verify API endpoints are accessible
3. Stop and restart the execution
4. Contact the administrator

### Execution Failed

**Problem**: Workflow execution failed with an error

**Solutions:**
1. Read the error message carefully
2. Check the failed node's configuration
3. Verify input data format
4. Test with simpler inputs
5. Review the execution logs

## Related Documentation

- [Workflow History](./workflow-history.md) - View past executions
- [Workflow Builder](./workflow-builder.md) - Create workflows
- [Workflow Nodes](./workflow-nodes.md) - Available nodes

## Getting Help

If you need assistance:

1. **Documentation**: Review this guide
2. **Support**: Contact your organization's support team
3. **Creator**: Reach out to the workflow creator
4. **Administrator**: Contact your Clouisle administrator

---

**Last Updated**: 2026-02-11
