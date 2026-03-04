# Running Workflows

This guide explains how to run and execute workflows in Clouisle.

## Overview

Workflows in Clouisle are automated processes that can:
- Execute multiple steps in sequence
- Make decisions based on conditions
- Call APIs and use tools
- Process data and generate outputs
- Run on schedule or via triggers

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
| **Success Rate** | Percentage of successful runs |
| **Actions** | Run, View, Edit |

## Running a Workflow

### Manual Execution

**Steps:**

1. Open the workflow
2. Click **"Run"** button
3. If workflow has input variables:
   - Fill in required inputs
   - Review optional inputs
   - Click **"Start"**
4. Watch execution in real-time
5. View results when complete

### Input Variables

Workflows may require inputs:

**Example Input Form:**
```
Workflow: Document Summarizer

Required Inputs:
┌─────────────────────────────────────┐
│ Document URL: [________________]    │
│ Summary Length: [Short ▼]          │
└─────────────────────────────────────┘

Optional Inputs:
┌─────────────────────────────────────┐
│ Language: [English ▼]              │
│ Format: [Bullet Points ▼]         │
└─────────────────────────────────────┘

[Cancel]  [Run Workflow]
```

**Input Types:**
- **Text**: Free-form text input
- **Number**: Numeric values
- **Select**: Dropdown options
- **Boolean**: Yes/No checkbox
- **File**: File upload
- **JSON**: Structured data

### Execution Modes

**Synchronous (Real-time):**
- Execution happens immediately
- You see progress in real-time
- Results displayed when complete
- Best for quick workflows (<2 minutes)

**Asynchronous (Background):**
- Execution happens in background
- You can close the page
- Notification when complete
- Best for long workflows (>2 minutes)

## Watching Execution

### Real-Time Progress

**Execution View:**
```
┌─────────────────────────────────────────┐
│ Document Summarizer                      │
│ Status: Running... ⏳                    │
│ Started: 2026-02-11 10:00:00            │
│ Duration: 00:00:45                      │
├─────────────────────────────────────────┤
│                                         │
│ ✅ Start                                │
│ ✅ Fetch Document                       │
│ ⏳ Extract Text (in progress...)        │
│ ⏸️  Summarize Text                      │
│ ⏸️  Format Output                       │
│ ⏸️  End                                 │
│                                         │
├─────────────────────────────────────────┤
│ [Stop Execution]  [View Logs]          │
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

Logs:
[10:00:12] Starting text extraction
[10:00:15] Downloaded document (2.5 MB)
[10:00:18] Extracting text from 15 pages...
```

### Streaming Output

Some workflows stream output in real-time:

```
Workflow Output:

Generating summary...

Key Points:
• Point 1: The document discusses...
• Point 2: Main findings include...
• Point 3: Recommendations are...

[Streaming in progress...]
```

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
│                                         │
│ Summary:                                │
│ The document provides an overview of... │
│                                         │
│ Key Points:                             │
│ • Point 1                               │
│ • Point 2                               │
│ • Point 3                               │
│                                         │
├─────────────────────────────────────────┤
│ [Download Results]  [Run Again]        │
│ [View Full Log]     [Share]            │
└─────────────────────────────────────────┘
```

**Actions:**
- **Download Results**: Save output as file
- **Run Again**: Execute with same inputs
- **View Full Log**: See detailed execution log
- **Share**: Share results with team

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
│ Details:                                │
│ Unsupported file format: .xyz          │
│                                         │
│ Suggestion:                             │
│ Please use PDF, DOCX, or TXT files     │
│                                         │
├─────────────────────────────────────────┤
│ [View Logs]  [Edit Workflow]           │
│ [Try Again]  [Report Issue]            │
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
2. Confirm stop action
3. Workflow stops at current node
4. Partial results may be available

**Note**: Some nodes cannot be interrupted (e.g., API calls in progress)

### Automatic Stop

Workflows stop automatically if:
- Timeout exceeded (default: 5 minutes)
- Error occurs (if not configured to continue)
- Resource limit reached
- User cancels execution

## Workflow Triggers

### Manual Trigger

Run workflow manually from UI:
- Click "Run" button
- Provide inputs
- Execute immediately

### Webhook Trigger

Run workflow via HTTP request:

**Webhook URL:**
```
POST https://your-domain.com/api/v1/workflows/{workflow_id}/webhook
Authorization: Bearer {webhook_token}
Content-Type: application/json

{
  "input_var1": "value1",
  "input_var2": "value2"
}
```

**Response:**
```json
{
  "code": 0,
  "data": {
    "run_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "running"
  },
  "msg": "Workflow execution started"
}
```

See [Webhook Triggers](../../admin-guide/workflows/webhook-triggers.md) for setup.

### Scheduled Trigger

Workflows can run on schedule:
- Daily at specific time
- Weekly on specific days
- Monthly on specific date
- Custom cron expression

**Note**: Scheduled execution is configured by administrators.

### API Trigger

Run workflow via API:

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

## Workflow Variables

### Input Variables

Provided when starting workflow:

**Example:**
```json
{
  "document_url": "https://example.com/doc.pdf",
  "summary_length": "short",
  "language": "en"
}
```

### Output Variables

Generated during execution:

**Example:**
```json
{
  "summary": "Document summary text...",
  "word_count": 1234,
  "key_points": ["Point 1", "Point 2", "Point 3"]
}
```

### Environment Variables

System-provided variables:

- `{{workflow.id}}` - Workflow ID
- `{{workflow.name}}` - Workflow name
- `{{run.id}}` - Current run ID
- `{{run.timestamp}}` - Execution timestamp
- `{{user.id}}` - User ID (if manual run)
- `{{user.email}}` - User email

## Best Practices

### Providing Inputs

**✅ Do:**
- Provide all required inputs
- Use correct data types
- Validate URLs and file paths
- Test with sample data first
- Review optional inputs

**❌ Don't:**
- Leave required fields empty
- Use invalid formats
- Provide sensitive data in plain text
- Skip input validation

### Monitoring Execution

**✅ Do:**
- Watch execution progress
- Check node outputs
- Review logs for errors
- Stop if unexpected behavior
- Save results when complete

**❌ Don't:**
- Close page during critical execution
- Ignore error messages
- Run multiple times simultaneously
- Skip result verification

### Handling Errors

**✅ Do:**
- Read error messages carefully
- Check input values
- Review node configuration
- Try again with corrected inputs
- Contact administrator if persistent

**❌ Don't:**
- Ignore errors and retry blindly
- Modify workflow without understanding
- Skip error logs
- Assume it's a system issue

## Troubleshooting

### Workflow Won't Start

**Problem**: Cannot start workflow execution

**Solutions:**
1. Check if workflow is published
2. Verify you have permission to run
3. Ensure all required inputs provided
4. Check if workflow is already running
5. Refresh page and try again

### Execution Stuck

**Problem**: Workflow execution not progressing

**Solutions:**
1. Check if node is waiting for external response
2. Verify API endpoints are accessible
3. Check timeout settings
4. Stop and restart execution
5. Contact administrator

### Execution Failed

**Problem**: Workflow execution failed with error

**Solutions:**
1. Read error message carefully
2. Check failed node configuration
3. Verify input data format
4. Test with simpler inputs
5. Review execution logs
6. Contact workflow creator

### Results Not as Expected

**Problem**: Workflow completed but results incorrect

**Solutions:**
1. Verify input values
2. Check node configurations
3. Review intermediate outputs
4. Test individual nodes
5. Contact workflow creator

## Related Documentation

- [Workflow History](./workflow-history.md) - View past executions
- [Workflow Builder](../../admin-guide/workflows/workflow-builder.md) - Create workflows
- [Node Types](../../admin-guide/workflows/node-types.md) - Available nodes
- [Webhook Triggers](../../admin-guide/workflows/webhook-triggers.md) - Webhook setup

## Getting Help

If you need assistance:

1. **Workflow Help**: Click **?** icon in workflow interface
2. **Documentation**: Review this guide
3. **Support**: Contact your organization's support team
4. **Creator**: Reach out to workflow creator
5. **Administrator**: Contact your Clouisle administrator

---

**Last Updated**: 2026-02-11
