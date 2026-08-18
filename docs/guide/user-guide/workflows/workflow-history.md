# Workflow Logs

This guide explains how to view workflow execution logs and monitor runs.

## Overview

Workflow history allows you to:

- **Track executions**: View all workflow runs
- **Monitor performance**: Analyze execution metrics
- **Debug issues**: Investigate failed runs
- **Audit activity**: Review who ran workflows and when

> **Note:** Retrying from a failed node, exporting history (CSV/JSON/PDF), comparing executions, and bulk deletion are **not implemented**. A `workflow.cleanup_old_runs` task exists, but it is not automatically scheduled by the application; run approved cleanup explicitly.

## Accessing Workflow Logs

Workflow execution history is available from the workflow's **Logs** view at `/app/apps/workflow/{id}/logs`. Open **Apps** → **Workflow**, select the workflow, then choose **Logs** from its workflow menu.

1. Navigate to **Apps** (`/app/apps`) and open the **Workflow** tab.
2. Open a workflow and choose **Logs**.
3. Select a run to inspect its details and node executions.

There is no separate **Workflows → History** tab.

### History List

**List view:**
```
┌─────────────────────────────────────────────────────┐
│ Workflow History                                    │
├─────────────────────────────────────────────────────┤
│                                                     │
│ ✅ Run #156 - Completed                            │
│    Started: 2026-02-11 14:30:00                    │
│    Duration: 1m 23s                                │
│    Triggered by: John Doe (Manual)                 │
│    [View Details]                                  │
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
| **Status** | The Logs UI displays Completed (API `success`), Failed, Running, Pending, Cancelled, or Timeout. Raw API `waiting` runs currently fall back to the Pending badge in both the list and run-detail drawer; Cancelled and Timeout have dedicated badges but no filter controls. |
| **Started** | Execution start time |
| **Duration** | Total execution time |
| **Triggered By** | User or Webhook |
| **Input** | Input variables provided |
| **Output** | Execution results |
| **Nodes Executed** | Number of nodes run |
| **Error** | Error message (if failed) |

### Status Icons

| Badge | Logs label | API status | Description |
|------|------------|------------|-------------|
| ✅ | **Completed** | `success` | Successfully finished |
| ❌ | **Failed** | `failed` | Execution failed |
| ⏳ | **Running** | `running` | Currently executing |
| ⏳ | **Pending** | `pending` | Queued before execution |
| ⏳ | **Pending** | `waiting` | This raw status currently has no dedicated Logs badge or filter and falls back to Pending. |
| ⏹️ | **Cancelled** | `cancelled` | Stopped or cancelled; no dedicated filter control is currently available. |
| ⏱️ | **Timeout** | `timeout` | Exceeded the execution timeout; no dedicated filter control is currently available. |

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

| Filter | Options |
|--------|---------|
| **Status** | All Status, Completed, Failed, Running, Pending |
| **Date Range** | All Time, Last 7 Days, Last 30 Days, Last 90 Days |
| **Run ID** | Exact run UUID |

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

## Starting Another Run

The Logs view has no **Replay** control and does not retry from a failed node. To run a workflow again:

1. Return to the workflow page
2. Choose **Run**
3. Provide the required inputs
4. Start a new execution

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
- Start a fresh test run from the workflow page when needed
- Document recurring issues

**❌ Don't:**
- Retry without investigating
- Ignore error patterns

## Troubleshooting

### Cannot View History

**Problem**: The Logs view is empty or not loading

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

### Cannot Start a New Run

**Problem**: The workflow cannot be run

**Solutions:**
1. Check that you have permission to run the workflow
2. Verify the workflow is published
3. Start a new execution from the workflow page

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
