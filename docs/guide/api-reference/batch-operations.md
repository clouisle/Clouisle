# Batch Operations Guide

This guide explains how to perform batch operations with the Clouisle API.

## Overview

Batch operations allow you to perform multiple actions in a single API request, improving efficiency and reducing network overhead.

## Supported Operations

### Batch Create

Create multiple resources at once.

**Endpoints:**
- `POST /api/v1/agents/batch` - Create multiple agents
- `POST /api/v1/users/batch` - Create multiple users
- `POST /api/v1/kb/documents/batch` - Upload multiple documents

**Request Format:**

```json
{
  "items": [
    {
      "name": "Agent 1",
      "model": "gpt-4-turbo",
      ...
    },
    {
      "name": "Agent 2",
      "model": "claude-3-5-sonnet",
      ...
    }
  ]
}
```

**Response Format:**

```json
{
  "code": 0,
  "data": {
    "success": [
      {
        "index": 0,
        "id": "agent-123",
        "name": "Agent 1"
      }
    ],
    "failed": [
      {
        "index": 1,
        "error": "Invalid model",
        "item": {...}
      }
    ],
    "summary": {
      "total": 2,
      "success_count": 1,
      "failed_count": 1
    }
  },
  "msg": "success"
}
```

### Batch Update

Update multiple resources at once.

**Endpoints:**
- `PATCH /api/v1/agents/batch` - Update multiple agents
- `PATCH /api/v1/users/batch` - Update multiple users

**Request Format:**

```json
{
  "items": [
    {
      "id": "agent-123",
      "status": "active"
    },
    {
      "id": "agent-456",
      "status": "inactive"
    }
  ]
}
```

### Batch Delete

Delete multiple resources at once.

**Endpoints:**
- `DELETE /api/v1/agents/batch` - Delete multiple agents
- `DELETE /api/v1/users/batch` - Delete multiple users
- `DELETE /api/v1/kb/documents/batch` - Delete multiple documents

**Request Format:**

```json
{
  "ids": ["agent-123", "agent-456", "agent-789"]
}
```

**Response Format:**

```json
{
  "code": 0,
  "data": {
    "success": ["agent-123", "agent-789"],
    "failed": [
      {
        "id": "agent-456",
        "error": "Agent not found"
      }
    ],
    "summary": {
      "total": 3,
      "success_count": 2,
      "failed_count": 1
    }
  },
  "msg": "success"
}
```

## Batch Limits

**Per Request:**
- Max items: 100
- Max request size: 10 MB
- Timeout: 60 seconds

**Rate Limiting:**
- Batch operations count as multiple requests
- Each item counts toward rate limit
- Example: Batch of 10 items = 10 requests

## Python Examples

### Batch Create Agents

```python
def batch_create_agents(agents_data):
    """Create multiple agents in one request."""
    response = api.post('/api/v1/agents/batch', json={
        'items': agents_data
    })

    return response['data']

# Usage
agents = [
    {
        'name': 'Customer Support Agent',
        'model': 'gpt-4-turbo',
        'system_prompt': 'You are a helpful customer support agent.',
        'team_id': 'team-123'
    },
    {
        'name': 'Sales Agent',
        'model': 'claude-3-5-sonnet',
        'system_prompt': 'You are a sales assistant.',
        'team_id': 'team-123'
    },
    {
        'name': 'Technical Support Agent',
        'model': 'gpt-4-turbo',
        'system_prompt': 'You are a technical support specialist.',
        'team_id': 'team-123'
    }
]

result = batch_create_agents(agents)
print(f"Created {result['summary']['success_count']} agents")
print(f"Failed {result['summary']['failed_count']} agents")

# Handle failures
for failure in result['failed']:
    print(f"Failed to create agent at index {failure['index']}: {failure['error']}")
```

### Batch Update with Error Handling

```python
def batch_update_agents(updates):
    """Update multiple agents with error handling."""
    try:
        response = api.patch('/api/v1/agents/batch', json={
            'items': updates
        })

        result = response['data']

        # Log successes
        for success in result['success']:
            print(f"Updated agent {success['id']}")

        # Handle failures
        for failure in result['failed']:
            print(f"Failed to update {failure['id']}: {failure['error']}")

        return result

    except ApiError as e:
        print(f"Batch update failed: {e.message}")
        raise

# Usage
updates = [
    {'id': 'agent-123', 'status': 'active'},
    {'id': 'agent-456', 'status': 'inactive'},
    {'id': 'agent-789', 'is_published': True}
]

result = batch_update_agents(updates)
```

### Batch Delete with Confirmation

```python
def batch_delete_agents(agent_ids, confirm=False):
    """Delete multiple agents with confirmation."""
    if not confirm:
        print(f"Warning: This will delete {len(agent_ids)} agents")
        response = input("Type 'yes' to confirm: ")
        if response.lower() != 'yes':
            print("Deletion cancelled")
            return None

    response = api.delete('/api/v1/agents/batch', json={
        'ids': agent_ids
    })

    result = response['data']
    print(f"Deleted {result['summary']['success_count']} agents")

    return result

# Usage
agent_ids = ['agent-123', 'agent-456', 'agent-789']
result = batch_delete_agents(agent_ids)
```

### Batch Operations with Progress

```python
from typing import List, Dict, Any
import time

def batch_create_with_progress(items: List[Dict], batch_size: int = 50):
    """Create items in batches with progress tracking."""
    total = len(items)
    results = {
        'success': [],
        'failed': [],
        'summary': {
            'total': total,
            'success_count': 0,
            'failed_count': 0
        }
    }

    # Process in chunks
    for i in range(0, total, batch_size):
        batch = items[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (total + batch_size - 1) // batch_size

        print(f"Processing batch {batch_num}/{total_batches} ({len(batch)} items)...")

        try:
            response = api.post('/api/v1/agents/batch', json={
                'items': batch
            })

            batch_result = response['data']

            # Aggregate results
            results['success'].extend(batch_result['success'])
            results['failed'].extend(batch_result['failed'])
            results['summary']['success_count'] += batch_result['summary']['success_count']
            results['summary']['failed_count'] += batch_result['summary']['failed_count']

            print(f"Batch {batch_num} complete: {batch_result['summary']['success_count']} success, {batch_result['summary']['failed_count']} failed")

        except ApiError as e:
            print(f"Batch {batch_num} failed: {e.message}")
            # Mark all items in this batch as failed
            for j, item in enumerate(batch):
                results['failed'].append({
                    'index': i + j,
                    'error': str(e),
                    'item': item
                })
            results['summary']['failed_count'] += len(batch)

        # Rate limiting delay
        if i + batch_size < total:
            time.sleep(0.5)

    return results

# Usage
agents = [...]  # Large list of agents
result = batch_create_with_progress(agents, batch_size=50)
print(f"\nTotal: {result['summary']['total']}")
print(f"Success: {result['summary']['success_count']}")
print(f"Failed: {result['summary']['failed_count']}")
```

## JavaScript Examples

### Batch Create

```javascript
async function batchCreateAgents(agentsData) {
  const response = await api.post('/api/v1/agents/batch', {
    items: agentsData
  });

  return response.data;
}

// Usage
const agents = [
  {
    name: 'Customer Support Agent',
    model: 'gpt-4-turbo',
    system_prompt: 'You are a helpful customer support agent.',
    team_id: 'team-123'
  },
  {
    name: 'Sales Agent',
    model: 'claude-3-5-sonnet',
    system_prompt: 'You are a sales assistant.',
    team_id: 'team-123'
  }
];

const result = await batchCreateAgents(agents);
console.log(`Created ${result.summary.success_count} agents`);
console.log(`Failed ${result.summary.failed_count} agents`);
```

### Batch Update

```javascript
async function batchUpdateAgents(updates) {
  try {
    const response = await api.patch('/api/v1/agents/batch', {
      items: updates
    });

    const result = response.data;

    // Log successes
    result.success.forEach(success => {
      console.log(`Updated agent ${success.id}`);
    });

    // Handle failures
    result.failed.forEach(failure => {
      console.error(`Failed to update ${failure.id}: ${failure.error}`);
    });

    return result;

  } catch (error) {
    console.error('Batch update failed:', error.message);
    throw error;
  }
}

// Usage
const updates = [
  { id: 'agent-123', status: 'active' },
  { id: 'agent-456', status: 'inactive' },
  { id: 'agent-789', is_published: true }
];

const result = await batchUpdateAgents(updates);
```

### Batch Delete

```javascript
async function batchDeleteAgents(agentIds, confirm = false) {
  if (!confirm) {
    const response = window.confirm(
      `This will delete ${agentIds.length} agents. Continue?`
    );
    if (!response) {
      console.log('Deletion cancelled');
      return null;
    }
  }

  const response = await api.delete('/api/v1/agents/batch', {
    ids: agentIds
  });

  const result = response.data;
  console.log(`Deleted ${result.summary.success_count} agents`);

  return result;
}

// Usage
const agentIds = ['agent-123', 'agent-456', 'agent-789'];
const result = await batchDeleteAgents(agentIds);
```

### Batch Operations with Progress

```javascript
async function batchCreateWithProgress(items, batchSize = 50) {
  const total = items.length;
  const results = {
    success: [],
    failed: [],
    summary: {
      total,
      success_count: 0,
      failed_count: 0
    }
  };

  // Process in chunks
  for (let i = 0; i < total; i += batchSize) {
    const batch = items.slice(i, i + batchSize);
    const batchNum = Math.floor(i / batchSize) + 1;
    const totalBatches = Math.ceil(total / batchSize);

    console.log(`Processing batch ${batchNum}/${totalBatches} (${batch.length} items)...`);

    try {
      const response = await api.post('/api/v1/agents/batch', {
        items: batch
      });

      const batchResult = response.data;

      // Aggregate results
      results.success.push(...batchResult.success);
      results.failed.push(...batchResult.failed);
      results.summary.success_count += batchResult.summary.success_count;
      results.summary.failed_count += batchResult.summary.failed_count;

      console.log(`Batch ${batchNum} complete: ${batchResult.summary.success_count} success, ${batchResult.summary.failed_count} failed`);

    } catch (error) {
      console.error(`Batch ${batchNum} failed:`, error.message);
      // Mark all items in this batch as failed
      batch.forEach((item, j) => {
        results.failed.push({
          index: i + j,
          error: error.message,
          item
        });
      });
      results.summary.failed_count += batch.length;
    }

    // Rate limiting delay
    if (i + batchSize < total) {
      await new Promise(resolve => setTimeout(resolve, 500));
    }
  }

  return results;
}

// Usage
const agents = [...];  // Large array of agents
const result = await batchCreateWithProgress(agents, 50);
console.log(`\nTotal: ${result.summary.total}`);
console.log(`Success: ${result.summary.success_count}`);
console.log(`Failed: ${result.summary.failed_count}`);
```

## UI Implementation

### React Batch Operations Component

```jsx
import { useState } from 'react';
import { toast } from 'sonner';

function BatchOperations({ items, onComplete }) {
  const [processing, setProcessing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [results, setResults] = useState(null);

  const handleBatchCreate = async () => {
    setProcessing(true);
    setProgress(0);

    const batchSize = 50;
    const total = items.length;
    const allResults = {
      success: [],
      failed: [],
      summary: {
        total,
        success_count: 0,
        failed_count: 0
      }
    };

    try {
      for (let i = 0; i < total; i += batchSize) {
        const batch = items.slice(i, i + batchSize);

        const response = await api.post('/api/v1/agents/batch', {
          items: batch
        });

        const batchResult = response.data;

        // Aggregate results
        allResults.success.push(...batchResult.success);
        allResults.failed.push(...batchResult.failed);
        allResults.summary.success_count += batchResult.summary.success_count;
        allResults.summary.failed_count += batchResult.summary.failed_count;

        // Update progress
        setProgress(Math.min(100, ((i + batch.length) / total) * 100));

        // Rate limiting delay
        if (i + batchSize < total) {
          await new Promise(resolve => setTimeout(resolve, 500));
        }
      }

      setResults(allResults);
      toast.success(`Created ${allResults.summary.success_count} agents`);

      if (allResults.summary.failed_count > 0) {
        toast.warning(`${allResults.summary.failed_count} agents failed`);
      }

      onComplete(allResults);

    } catch (error) {
      toast.error(`Batch operation failed: ${error.message}`);
    } finally {
      setProcessing(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-medium">Batch Create Agents</h3>
          <p className="text-sm text-muted-foreground">
            {items.length} agents ready to create
          </p>
        </div>

        <button
          onClick={handleBatchCreate}
          disabled={processing || items.length === 0}
          className="px-4 py-2 bg-primary text-white rounded disabled:opacity-50"
        >
          {processing ? 'Processing...' : 'Create All'}
        </button>
      </div>

      {processing && (
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span>Progress</span>
            <span>{Math.round(progress)}%</span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div
              className="bg-primary h-2 rounded-full transition-all"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      )}

      {results && (
        <div className="border rounded-lg p-4 space-y-2">
          <h4 className="font-medium">Results</h4>
          <div className="grid grid-cols-3 gap-4 text-sm">
            <div>
              <div className="text-muted-foreground">Total</div>
              <div className="text-lg font-semibold">{results.summary.total}</div>
            </div>
            <div>
              <div className="text-muted-foreground">Success</div>
              <div className="text-lg font-semibold text-green-600">
                {results.summary.success_count}
              </div>
            </div>
            <div>
              <div className="text-muted-foreground">Failed</div>
              <div className="text-lg font-semibold text-red-600">
                {results.summary.failed_count}
              </div>
            </div>
          </div>

          {results.failed.length > 0 && (
            <div className="mt-4">
              <h5 className="text-sm font-medium mb-2">Failed Items:</h5>
              <div className="space-y-1 max-h-40 overflow-y-auto">
                {results.failed.map((failure, index) => (
                  <div key={index} className="text-sm text-red-600">
                    Index {failure.index}: {failure.error}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

### Batch Delete with Confirmation

```jsx
import { useState } from 'react';
import { AlertDialog } from '@/components/ui/alert-dialog';

function BatchDelete({ selectedIds, onComplete }) {
  const [showConfirm, setShowConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const handleDelete = async () => {
    setDeleting(true);

    try {
      const response = await api.delete('/api/v1/agents/batch', {
        ids: selectedIds
      });

      const result = response.data;

      toast.success(`Deleted ${result.summary.success_count} agents`);

      if (result.summary.failed_count > 0) {
        toast.warning(`${result.summary.failed_count} agents could not be deleted`);
      }

      onComplete(result);
      setShowConfirm(false);

    } catch (error) {
      toast.error(`Batch delete failed: ${error.message}`);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <>
      <button
        onClick={() => setShowConfirm(true)}
        disabled={selectedIds.length === 0}
        className="px-4 py-2 bg-red-600 text-white rounded disabled:opacity-50"
      >
        Delete Selected ({selectedIds.length})
      </button>

      <AlertDialog
        open={showConfirm}
        onOpenChange={setShowConfirm}
        title="Delete Agents"
        description={`Are you sure you want to delete ${selectedIds.length} agents? This action cannot be undone.`}
        onConfirm={handleDelete}
        confirmText={deleting ? 'Deleting...' : 'Delete'}
        confirmDisabled={deleting}
      />
    </>
  );
}
```

## Best Practices

### Batch Operations

**✅ Do:**
- Use batch operations for bulk actions
- Process in chunks (50-100 items)
- Handle partial failures gracefully
- Show progress for long operations
- Validate items before sending
- Log all failures for review
- Implement retry logic for failures
- Add confirmation for destructive operations

**❌ Don't:**
- Send too many items at once (>100)
- Ignore failed items
- Block UI during processing
- Skip validation
- Retry entire batch on partial failure
- Forget rate limiting delays
- Skip error logging

### Performance

**✅ Do:**
- Use appropriate batch sizes
- Add delays between batches
- Process asynchronously
- Cache validation results
- Use parallel processing when possible
- Monitor memory usage
- Implement timeouts

**❌ Don't:**
- Send all items in one request
- Ignore rate limits
- Block on each batch
- Validate repeatedly
- Process sequentially when parallel is possible
- Load all data into memory
- Use infinite timeouts

### Error Handling

**✅ Do:**
- Handle partial failures
- Provide detailed error messages
- Log all failures
- Offer retry options
- Show which items failed
- Preserve failed items for review
- Implement rollback when needed

**❌ Don't:**
- Fail entire batch on one error
- Show generic error messages
- Skip error logging
- Lose failed items
- Hide failure details
- Retry without fixing issues
- Leave partial state

## Troubleshooting

### Batch Too Large

**Problem:** Request rejected due to size

**Solutions:**
1. Reduce batch size (try 50 items)
2. Split into smaller batches
3. Remove unnecessary fields
4. Compress request data

### Partial Failures

**Problem:** Some items succeed, others fail

**Solutions:**
1. Review failed items
2. Fix validation errors
3. Retry failed items only
4. Check permissions
5. Verify data format

### Timeout Errors

**Problem:** Batch operation times out

**Solutions:**
1. Reduce batch size
2. Optimize item data
3. Increase timeout (if possible)
4. Process in smaller chunks
5. Use async processing

### Rate Limit Exceeded

**Problem:** Too many requests

**Solutions:**
1. Add delays between batches
2. Reduce batch frequency
3. Use smaller batches
4. Implement exponential backoff
5. Check rate limit headers

## Related Documentation

- [Error Handling](./error-handling.md) - Error handling patterns
- [Rate Limiting](./rate-limiting.md) - Rate limit details
- [Pagination](./pagination.md) - Paginating results
- [API Reference](./endpoints/) - Endpoint documentation

---

**Last Updated**: 2026-02-11
