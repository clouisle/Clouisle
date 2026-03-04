# Workflow History

This guide explains how to view and manage workflow execution history.

## Overview

Workflow history allows you to:

- **Track executions**: View all workflow runs
- **Monitor performance**: Analyze execution metrics
- **Debug issues**: Investigate failed runs
- **Audit activity**: Review who ran workflows and when
- **Replay workflows**: Re-run with same inputs

## Accessing Workflow History

### From Workflow Page

**Steps:**

1. Navigate to **Workflows** section
2. Click on a workflow to open it
3. Go to **History** tab
4. View all execution history

**Or:**

- Navigate directly to `/workflows/{workflow_id}/history`

### History List

**List view:**
```
┌─────────────────────────────────────────────────────┐
│ Workflow History                        [Export ▼]  │
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
│    [View Details] [Retry]                          │
│                                                     │
│ ✅ Run #154 - Completed                             │
│    Started: 2026-02-10 16:20:00                    │
│    Duration: 2m 10s                                │
│    Triggered by: Schedule                          │
│    [View Details] [Replay]                         │
│                                                     │
│ [Load More]                                        │
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
| **Triggered By** | User, Webhook, Schedule, API |
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
2. Execution details page opens
3. View complete execution information

**Details page:**
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
│ ─────────────────────────────────────────────────  │
│                                                     │
│ Input Variables:                                   │
│ • document_url: https://example.com/doc.pdf        │
│ • summary_length: short                            │
│ • language: en                                     │
│                                                     │
│ Output:                                            │
│ • summary: "The document discusses..."             │
│ • word_count: 1234                                 │
│ • key_points: ["Point 1", "Point 2", "Point 3"]   │
│                                                     │
│ Nodes Executed: 6/6                                │
│                                                     │
│ [View Execution Flow] [Download Results]           │
│ [Replay] [Share]                                   │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### Execution Flow

**View node-by-node execution:**

1. Click **"View Execution Flow"**
2. Visual workflow diagram opens
3. Each node shows execution status
4. Click nodes to see details

**Flow diagram:**
```
┌─────────────────────────────────────────┐
│ Execution Flow                          │
├─────────────────────────────────────────┤
│                                         │
│  ✅ Start                               │
│   ↓                                     │
│  ✅ Fetch Document (12s)                │
│   ↓                                     │
│  ✅ Extract Text (45s)                  │
│   ↓                                     │
│  ✅ Summarize Text (23s)                │
│   ↓                                     │
│  ✅ Format Output (3s)                  │
│   ↓                                     │
│  ✅ End                                 │
│                                         │
│ Total: 1m 23s                           │
│                                         │
└─────────────────────────────────────────┘
```

### Node Details

**Click on a node to see:**

```
┌─────────────────────────────────────────┐
│ Node: Extract Text                      │
├─────────────────────────────────────────┤
│                                         │
│ Status: ✅ Completed                    │
│ Duration: 45s                           │
│ Started: 14:30:12                       │
│ Completed: 14:30:57                     │
│                                         │
│ Input:                                  │
│ {                                       │
│   "url": "https://example.com/doc.pdf", │
│   "format": "text"                      │
│ }                                       │
│                                         │
│ Output:                                 │
│ {                                       │
│   "text": "Document content...",        │
│   "pages": 15,                          │
│   "word_count": 1234                    │
│ }                                       │
│                                         │
│ Logs:                                   │
│ [14:30:12] Starting text extraction     │
│ [14:30:15] Downloaded document (2.5 MB) │
│ [14:30:18] Extracting text from 15 pages│
│ [14:30:57] Extraction complete          │
│                                         │
│ [Close]                                 │
│                                         │
└─────────────────────────────────────────┘
```

## Filtering History

### Filter Options

**Available filters:**

| Filter | Options |
|--------|---------|
| **Status** | Completed, Failed, Running, Stopped |
| **Trigger** | Manual, Webhook, Schedule, API |
| **Date Range** | Today, Last 7 days, Last 30 days, Custom |
| **User** | Specific user who triggered |
| **Duration** | Less than 1m, 1-5m, 5-10m, More than 10m |

**Filter panel:**
```
┌─────────────────────────────────────────┐
│ Filters                                 │
├─────────────────────────────────────────┤
│                                         │
│ Status:                                 │
│ ☑ Completed                             │
│ ☑ Failed                                │
│ ☐ Running                               │
│ ☐ Stopped                               │
│                                         │
│ Triggered By:                           │
│ ☑ Manual                                │
│ ☑ Webhook                               │
│ ☑ Schedule                              │
│ ☑ API                                   │
│                                         │
│ Date Range:                             │
│ ○ Today                                 │
│ ● Last 7 days                           │
│ ○ Last 30 days                          │
│ ○ Custom: [____] to [____]             │
│                                         │
│ User:                                   │
│ [All Users ▼]                           │
│                                         │
│ [Clear All]  [Apply]                    │
│                                         │
└─────────────────────────────────────────┘
```

### Searching History

**Search executions:**

1. Enter search term in search bar
2. Search by:
   - Run ID
   - Input values
   - Output values
   - Error messages
3. Results update in real-time

**Example searches:**
```
"#156"           → Find run #156
"timeout"        → Find runs with timeout errors
"john@example"   → Find runs with this input
```

## Execution Statistics

### Overview Stats

**Summary metrics:**

```
┌─────────────────────────────────────────┐
│ Execution Statistics (Last 30 Days)    │
├─────────────────────────────────────────┤
│                                         │
│ Total Runs:        156                  │
│ Success Rate:      94.2% (147/156)      │
│ Failed Runs:       9                    │
│ Avg Duration:      1m 45s               │
│ Total Runtime:     4h 32m               │
│                                         │
│ Triggers:                               │
│ • Manual:    89 (57%)                   │
│ • Webhook:   45 (29%)                   │
│ • Schedule:  22 (14%)                   │
│                                         │
│ [View Detailed Analytics]               │
│                                         │
└─────────────────────────────────────────┘
```

### Performance Trends

**View trends over time:**

1. Click **"View Detailed Analytics"**
2. View charts and graphs:
   - Execution count over time
   - Success rate trend
   - Average duration trend
   - Error rate by type

**Charts:**
```
Executions per Day
│
│     ▄▄
│   ▄▄██▄▄
│ ▄▄██████▄▄
│████████████
└─────────────────
 Mon Tue Wed Thu Fri

Success Rate
│ 100% ─────────────
│  95% ─────▄▄▄▄────
│  90% ───▄▄████▄▄──
│  85% ─▄▄████████▄▄
└─────────────────
```

## Replaying Workflows

### Replay Execution

**Re-run with same inputs:**

1. Find execution in history
2. Click **"Replay"** button
3. Review input variables
4. Optionally modify inputs
5. Click **"Run"**
6. New execution starts

**Replay dialog:**
```
┌─────────────────────────────────────────┐
│ Replay Workflow                         │
├─────────────────────────────────────────┤
│                                         │
│ Replaying Run #156                      │
│                                         │
│ Original Input:                         │
│ • document_url: https://example.com/... │
│ • summary_length: short                 │
│ • language: en                          │
│                                         │
│ Modify Input: (optional)                │
│ [Edit Input Variables]                  │
│                                         │
│ [Cancel]  [Run Workflow]                │
│                                         │
└─────────────────────────────────────────┘
```

### Retry Failed Runs

**For failed executions:**

1. Click **"Retry"** on failed run
2. Workflow retries from failed node
3. Or retry from beginning
4. Monitor new execution

**Retry options:**
```
┌─────────────────────────────────────────┐
│ Retry Failed Workflow                   │
├─────────────────────────────────────────┤
│                                         │
│ Run #155 failed at: Extract Text        │
│ Error: API call timeout                 │
│                                         │
│ Retry Options:                          │
│ ○ Retry from failed node                │
│ ● Retry from beginning                  │
│                                         │
│ [Cancel]  [Retry]                       │
│                                         │
└─────────────────────────────────────────┘
```

## Exporting History

### Export Options

**Export execution history:**

1. Click **"Export"** dropdown
2. Select format:
   - **CSV**: Spreadsheet
   - **JSON**: Structured data
   - **PDF**: Report
3. Select date range
4. Click **"Export"**
5. File is downloaded

**CSV export:**
```csv
Run ID,Status,Started,Duration,Triggered By,Input,Output
156,Completed,2026-02-11 14:30:00,1m 23s,John Doe,"{...}","{...}"
155,Failed,2026-02-11 10:15:00,0m 45s,Webhook,"{...}","Error: ..."
154,Completed,2026-02-10 16:20:00,2m 10s,Schedule,"{...}","{...}"
```

### Downloading Results

**Download execution output:**

1. Open execution details
2. Click **"Download Results"**
3. Select format:
   - JSON
   - CSV (if tabular data)
   - Text
4. File is downloaded

**JSON output:**
```json
{
  "run_id": "156",
  "workflow_id": "workflow-123",
  "status": "completed",
  "started_at": "2026-02-11T14:30:00Z",
  "completed_at": "2026-02-11T14:31:23Z",
  "duration": 83,
  "input": {
    "document_url": "https://example.com/doc.pdf",
    "summary_length": "short",
    "language": "en"
  },
  "output": {
    "summary": "The document discusses...",
    "word_count": 1234,
    "key_points": ["Point 1", "Point 2", "Point 3"]
  }
}
```

## Comparing Executions

### Side-by-Side Comparison

**Compare two runs:**

1. Select first execution (checkbox)
2. Select second execution (checkbox)
3. Click **"Compare"** button
4. Comparison view opens

**Comparison view:**
```
┌─────────────────────────────────────────────────────┐
│ Compare Executions                                  │
├─────────────────────────────────────────────────────┤
│                                                     │
│           Run #156          │      Run #154         │
│ ─────────────────────────────────────────────────  │
│ Status:   ✅ Completed      │  ✅ Completed         │
│ Duration: 1m 23s            │  2m 10s               │
│ Nodes:    6/6               │  6/6                  │
│                                                     │
│ Input Differences:                                  │
│ • summary_length: short     │  long                 │
│                                                     │
│ Output Differences:                                 │
│ • word_count: 1234          │  2345                 │
│                                                     │
│ Performance:                                        │
│ • Extract Text: 45s         │  67s (+49%)           │
│ • Summarize: 23s            │  48s (+109%)          │
│                                                     │
└─────────────────────────────────────────────────────┘
```

## Deleting History

### Delete Single Execution

**Steps:**

1. Find execution in history
2. Click **"..."** menu
3. Select **"Delete"**
4. Confirm deletion
5. Execution is removed

**Warning**: Deleted executions cannot be recovered.

### Bulk Delete

**Delete multiple executions:**

1. Select executions (checkboxes)
2. Click **"Delete Selected"**
3. Confirm deletion
4. All selected executions are removed

### Auto-Cleanup

**Automatic history cleanup:**

- Executions older than retention period are auto-deleted
- Default retention: 90 days
- Configurable by administrator

**Retention settings:**
```
┌─────────────────────────────────────────┐
│ History Retention                       │
├─────────────────────────────────────────┤
│                                         │
│ Keep execution history for:             │
│ ○ 30 days                               │
│ ● 90 days                               │
│ ○ 1 year                                │
│ ○ Forever                               │
│                                         │
│ Current usage: 1.2 GB                   │
│                                         │
│ [Save Settings]                         │
│                                         │
└─────────────────────────────────────────┘
```

## Best Practices

### Monitoring Workflows

**✅ Do:**
- Review history regularly
- Monitor success rates
- Investigate failures promptly
- Track performance trends
- Set up alerts for failures
- Export important results

**❌ Don't:**
- Ignore failed executions
- Let history accumulate indefinitely
- Delete history without backup
- Overlook performance degradation
- Skip error analysis

### Troubleshooting

**✅ Do:**
- Check execution logs
- Compare successful and failed runs
- Review input/output data
- Test with replay feature
- Document recurring issues
- Contact support if needed

**❌ Don't:**
- Retry without investigating
- Ignore error patterns
- Skip log review
- Assume transient failures
- Delete failed runs immediately

## Troubleshooting

### Cannot View History

**Problem**: History tab is empty or not loading

**Solutions:**
1. Refresh the page
2. Check if you have permission
3. Verify workflow has been executed
4. Check date range filter
5. Clear browser cache
6. Contact administrator

### Missing Executions

**Problem**: Some executions don't appear in history

**Solutions:**
1. Check filters (may be hiding results)
2. Verify date range
3. Check if executions were deleted
4. Verify retention policy
5. Contact administrator

### Cannot Replay

**Problem**: Replay button is disabled

**Solutions:**
1. Check if you have permission to run workflow
2. Verify workflow is published
3. Check if workflow has been modified
4. Try creating new execution manually
5. Contact administrator

### Export Fails

**Problem**: Cannot export history

**Solutions:**
1. Check internet connection
2. Try smaller date range
3. Try different format
4. Check browser download settings
5. Contact administrator

## Related Documentation

- [Running Workflows](./running-workflows.md) - Executing workflows
- [Workflow Builder](../../admin-guide/workflows/workflow-builder.md) - Creating workflows
- [Webhook Triggers](../../admin-guide/workflows/webhook-triggers.md) - Webhook setup
- [Workflow Concepts](../../concepts/workflows.md) - Understanding workflows

## Getting Help

If you need assistance with workflow history:

1. **Documentation**: Review this guide
2. **History Help**: Click **?** icon in history interface
3. **Support**: Contact your organization's support team
4. **Administrator**: Reach out to your Clouisle administrator

---

**Last Updated**: 2026-02-11
