# Statistics aggregation: index rollout

Companion to the statistics aggregation pushdown in
`backend/app/services/stats_sql.py`. The pushdown is already deployed and is
correct without these indexes; they reduce the remaining sequential scans.

## Why these are not startup migrations

`backend/app/core/init_data.py` runs DDL through
`execute_startup_migration_query`, which sets `lock_timeout = '2s'` and wraps
the statement in a 3-second `asyncio.wait_for`. That is deliberate: a slow DDL
statement during startup would block the application from becoming ready.

Building these indexes on a populated `messages` or `workflow_runs` table takes
far longer than 3 seconds, and a plain `CREATE INDEX` holds a lock that blocks
writes for the whole build. The safe form, `CREATE INDEX CONCURRENTLY`, cannot
run inside a transaction block and is expected to take minutes.

Those two facts are incompatible with the startup path, so the indexes are
applied as an operational step during a maintenance window instead.

## Statements

Run against the application database, one at a time, as a superuser or the
table owner:

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_conversations_agent_created_user
    ON conversations (agent_id, created_at) INCLUDE (user_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_conversations_agent_updated_at
    ON conversations (agent_id, updated_at DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_messages_conversation_role_created_at
    ON messages (conversation_id, role, created_at);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_workflow_runs_workflow_created_at
    ON workflow_runs (workflow_id, created_at);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_workflow_runs_workflow_covering
    ON workflow_runs (workflow_id) INCLUDE (status, total_duration_ms);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_agent_runs_agent_updated_at
    ON agent_runs (agent_id, updated_at);
```

| Index | Serves |
|---|---|
| `conversations (agent_id, created_at) INCLUDE (user_id)` | overview counts, distinct active users, trend buckets |
| `conversations (agent_id, updated_at DESC)` | `GET /agents/{id}/stats/recent-conversations` |
| `messages (conversation_id, role, created_at)` | per-role counts, token sums, tool-call aggregation, first-token percentiles |
| `workflow_runs (workflow_id, created_at)` | per-workflow trends |
| `workflow_runs (workflow_id) INCLUDE (status, total_duration_ms)` | per-workflow overview, global run stats |
| `agent_runs (agent_id, updated_at)` | execution health and user-intervention counts |

`agent_run_inputs` already carries a `run_id` index, which covers the
intervention join; it needs no additional index.

## Why `INCLUDE` rather than plain composite indexes

Measured on PostgreSQL 17 against 200k synthetic rows (50 workflows, 4000 runs
for the probed id), aggregating `count(*) FILTER (...)` plus
`AVG(total_duration_ms)` for one workflow:

| Plan | Buffers | Execution |
|---|---|---|
| Seq Scan (no index) | 2470 | 6.05 ms |
| Bitmap scan on `(workflow_id, status)` | 2476 | 8.69 ms |
| Index Only Scan on `(workflow_id) INCLUDE (status, total_duration_ms)` | 28 | 0.28 ms |

A plain `(workflow_id, status)` index was **slower than the sequential scan**:
the aggregate also reads `total_duration_ms`, so every one of the 4000 matches
required a heap fetch, and the bitmap machinery was pure overhead. Only when
the index covers every referenced column does the planner choose an Index Only
Scan and skip the heap entirely.

The same effect on the agent side, counting conversations and distinct users
for one agent over 30 days across 200k rows:

| Plan | Buffers | Execution |
|---|---|---|
| Parallel Seq Scan | 2329 | 6.02 ms |
| `(agent_id, created_at) INCLUDE (user_id)` | 503 | 0.64 ms |

Any future change to the aggregation column list invalidates the `INCLUDE`
payload — re-measure rather than assuming the index still covers the query.

## Operating notes

- **One statement at a time.** `CONCURRENTLY` builds cannot be batched into a
  single script that runs in a transaction.
- **A failed build leaves an `INVALID` index.** Verify afterwards and drop any
  invalid leftovers before retrying:

  ```sql
  SELECT c.relname
  FROM pg_class c
  JOIN pg_index i ON i.indexrelid = c.oid
  WHERE NOT i.indisvalid;
  ```

- **`IF NOT EXISTS` makes reruns safe**, so the sequence can be replayed.
- Re-run `ANALYZE conversations; ANALYZE messages; ANALYZE workflow_runs;`
  afterwards so the planner sees the new indexes.

## Verification

Confirm the planner actually uses them, rather than assuming:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT count(*) FILTER (WHERE status = 'success')
FROM workflow_runs
WHERE workflow_id = '<id>'::uuid;
```

Expect an **Index Only Scan**, not merely a bitmap index scan: as measured
above, a bitmap scan that still fetches heap rows can be slower than the
sequential scan it replaced. If the planner keeps choosing a sequential scan,
the table is small enough that it is genuinely the cheaper plan and no action
is needed.
