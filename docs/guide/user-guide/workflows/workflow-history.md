# Workflow History

This guide explains how to view workflow execution history.

## Overview

Workflow history allows you to:

- **Track executions**: View all workflow runs
- **Monitor performance**: Analyze execution metrics
- **Debug issues**: Investigate failed runs
- **Audit activity**: Review who ran workflows and when

> **Note:** Retrying failed runs from the failed node, exporting history (CSV/JSON/PDF), comparing executions, bulk deletion, and automatic retention/cleanup policies are **not implemented**.

## Accessing Workflow History

### From Workflow Page

**Steps:**

1. Navigate to **Workflows** section
2. Click on a workflow to open it
3. Go to **History** tab
4. View the execution history

### History List

**List view:**
```
┌─────────────────────────────────────────────────────┐
│ Workflow History                                    │
├─────────────────────────────────────────────────────┤
│                                                     │
│ ✅ Run #156 - Completed                             │
│    Started: 2026-02-11 14:30:00                    │
│    Duration: 1m 23s                                │
│    Triggered by: John Doe (Manual)                 │
│    [View Details] [Replay]                         │
│                                                     │
│ ❌ Run #155 - Failed                                │
│    Started: 2026-02-11 10:15:00                    │
│    Duration: 0m 45s                                │
│    Error: API call timeout                         │
│    Triggered by: Webhook                           │
│    [View Details]                                  │
│                                                     │
└─────────────────────────────────────────────────────┘
```

## Execution Information

### Run Details

Each execution shows:

| Field | Description |
|-------|-------------|
| **Run ID** | Unique execution identifier |
| **Status** | Completed, Failed, Running, Stopped |
| **Started** | Execution start time |
| **Duration** | Total execution time |
| **Triggered By** | User or Webhook |
| **Input** | Input variables provided |
| **Output** | Execution results |
| **Nodes Executed** | Number of nodes run |
| **Error** | Error message (if failed) |

### Status Icons

| Icon | Status | Description |
|------|--------|-------------|
| ✅ | **Completed** | Successfully finished |
| ❌ | **Failed** | Execution failed |
| ⏳ | **Running** | Currently executing |
| ⏹️ | **Stopped** | Manually stopped |
| ⏭️ | **Skipped** | Skipped (conditional) |

## Viewing Execution Details

### Opening Run Details

**Steps:**

1. Click **"View Details"** on a run
2. The execution details view opens
3. Review the complete execution information

**Details:**
```
┌─────────────────────────────────────────────────────┐
│ Run #156 - Document Summarizer          [✕]        │
├─────────────────────────────────────────────────────┤
│                                                     │
│ Status: ✅ Completed                                │
│ Started: 2026-02-11 14:30:00                       │
│ Completed: 2026-02-11 14:31:23                     │
│ Duration: 1m 23s                                   │
│ Triggered by: John Doe (Manual)                    │
│                                                     │
│ Input Variables:                                   │
│ • document_url: https://example.com/doc.pdf        │
│ • summary_length: short                            │
│                                                     │
│ Output:                                            │
│ • summary: "The document discusses..."             │
│                                                     │
│ Nodes Executed: 6/6                                │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### Node Execution Details

View the node-by-node execution:

1. Open the run's **node executions**
2. Each node shows its status, duration, input, output, and error (if any)

**Node detail:**
```
┌─────────────────────────────────────────┐
│ Node: Extract Text                      │
├─────────────────────────────────────────┤
│                                         │
│ Status: ✅ Completed                    │
│ Duration: 45s                           │
│                                         │
│ Input:                                  │
│ { "url": "https://example.com/doc.pdf" }│
│                                         │
│ Output:                                 │
│ { "text": "Document content...",        │
│   "pages": 15 }                         │
│                                         │
└─────────────────────────────────────────┘
```

### Streaming

Runs stream events in real-time (`GET /api/v1/workflows/runs/{run_id}/stream`), including node status updates and LLM token output.

## Filtering History

### Filter Options

**Available filters:**

| Filter | Options |
|--------|---------|
| **Status** | Completed, Failed, Running, Stopped |
| **Date Range** | Custom date range |
| **User** | Specific user who triggered |

## Execution Statistics

### Overview Stats

**Summary metrics (per workflow or system-wide):**

```
┌─────────────────────────────────────────┐
│ Execution Statistics                    │
├─────────────────────────────────────────┤
│                                         │
│ Total Runs:        156                  │
│ Success Rate:      94.2% (147/156)      │
│ Failed Runs:       9                    │
│ Avg Duration:      1m 45s               │
│                                         │
└─────────────────────────────────────────┘
```

## Replaying Workflows

### Replay Execution

**Re-run with the same inputs:**

1. Find the execution in the history
2. Click **"Replay"** button
3. Review the input variables
4. Optionally modify the inputs
5. Click **"Run"**
6. A new execution starts

> **Note:** There is no "retry from failed node" option — replay always starts a fresh run.

## Deleting History

### Delete Single Execution

**Steps:**

1. Find the execution in the history
2. Click the **"..."** menu
3. Select **"Delete"**
4. Confirm deletion
5. The execution is removed

**Warning**: Deleted executions cannot be recovered.

> **Note:** Bulk deletion is **not implemented**, and there is no automatic retention/cleanup policy setting.

## Best Practices

### Monitoring Workflows

**✅ Do:**
- Review history regularly
- Monitor success rates
- Investigate failures promptly

**❌ Don't:**
- Ignore failed executions
- Delete history without reason

### Troubleshooting

**✅ Do:**
- Check node execution details
- Review input/output data
- Replay with test inputs
- Document recurring issues

**❌ Don't:**
- Retry without investigating
- Ignore error patterns

## Troubleshooting

### Cannot View History

**Problem**: History tab is empty or not loading

**Solutions:**
1. Refresh the page
2. Check if you have permission
3. Verify the workflow has been executed
4. Check the date-range filter
5. Contact the administrator

### Missing Executions

**Problem**: Some executions don't appear in the history

**Solutions:**
1. Check filters (may be hiding results)
2. Verify the date range
3. Check if executions were deleted

### Cannot Replay

**Problem**: Replay button is disabled

**Solutions:**
1. Check if you have permission to run the workflow
2. Verify the workflow is published
3. Try creating a new execution manually

## Related Documentation

- [Running Workflows](./running-workflows.md) - Executing workflows
- [Workflow Builder](./workflow-builder.md) - Creating workflows

## Getting Help

If you need assistance with workflow history:

1. **Documentation**: Review this guide
2. **Support**: Contact your organization's support team
3. **Administrator**: Reach out to your Clouisle administrator

---

**Last Updated**: 2026-02-11
