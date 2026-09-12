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

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_conversations_agent_user_updated_at
    ON conversations (agent_id, user_id, updated_at DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_messages_conversation_role_created_at
    ON messages (conversation_id, role, created_at);

-- ONE index serves both per-workflow helpers. `created_at` must be a key
-- column, not just an INCLUDE payload: workflow_run_overview reads
-- MAX(created_at), and an INCLUDE-only column cannot satisfy it (see below).
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_workflow_runs_workflow_created_covering
    ON workflow_runs (workflow_id, created_at)
    INCLUDE (status, total_duration_ms);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_agent_runs_agent_updated_at
    ON agent_runs (agent_id, updated_at);
```

| Index | Serves |
|---|---|
| `conversations (agent_id, created_at) INCLUDE (user_id)` | overview counts, distinct active users, trend buckets |
| `conversations (agent_id, user_id, updated_at DESC)` | `GET /agents/{agent_id}/conversations`, which filters on both `agent_id` and `user_id` and orders by `updated_at` |
| `messages (conversation_id, role, created_at)` | per-role counts, token sums, tool-call aggregation, first-token percentiles |
| `workflow_runs (workflow_id, created_at) INCLUDE (status, total_duration_ms)` | BOTH `workflow_run_overview` (needs `created_at` for `MAX`) and `workflow_trend_buckets` |
| `agent_runs (agent_id, updated_at)` | execution health and user-intervention counts |

`agent_run_inputs` already carries a `run_id` index, which covers the
intervention join; it needs no additional index.

## Why `created_at` must be a key column

`workflow_run_overview` (`stats_sql.py`) selects `MAX(created_at)` alongside
`status` and `total_duration_ms`. A covering index that holds `created_at` only
in the `INCLUDE` payload **cannot** produce an Index Only Scan, because
`MAX()` needs the key ordering. An earlier revision of this runbook specified
`(workflow_id) INCLUDE (status, total_duration_ms)`, which cannot serve that
query.

Measured on PostgreSQL 17 with 200k synthetic rows, 4000 belonging to the
probed workflow (matching the query the endpoint actually issues — `COUNT(*)
FILTER (…)` per status, `AVG(total_duration_ms)`, and `MAX(created_at)`):

| Index | Plan | Planner cost | Buffers | Heap fetches |
|---|---|---|---|---|
| `(workflow_id) INCLUDE (status, total_duration_ms)` | Bitmap Heap Scan + Bitmap Index Scan | 2312.68 | 69 (42 hit, 27 read) | 42 heap blocks |
| `(workflow_id, created_at) INCLUDE (status, total_duration_ms)` | **Index Only Scan** | **236.15** | **33** | **0** |

The merged index is read from the index alone; the `INCLUDE`-only variant is
forced to fetch 42 heap blocks for the same 4000 rows. Wall-clock time on a
fully cached table is close (0.43 ms vs 0.73 ms), but the buffer accounting and
the planner's ~10x cost gap are the durable signal: the gap widens with the
working set, and the heap fetch is the thing this index exists to remove.

Merging also means one index serves both helpers — the separate
`(workflow_id, created_at)` index would itself fail the overview query for want
of `status` and `total_duration_ms`.

### The `INCLUDE` payload is a hard contract

A plain `(workflow_id, status)` composite index was measured **slower than the
sequential scan** it replaced: the aggregate also reads `total_duration_ms`, so
every one of the 4000 matches required a heap fetch and the bitmap machinery was
pure overhead. Same effect on the agent side, counting conversations and
distinct users for one agent over 30 days across 200k rows:

| Plan | Buffers | Execution |
|---|---|---|
| Parallel Seq Scan | 2329 | 6.02 ms |
| `(agent_id, created_at) INCLUDE (user_id)` | 503 | 0.64 ms |

Any future change to the aggregation column list invalidates the `INCLUDE`
payload — re-measure rather than assuming the index still covers the query.

## Operating notes

- **One statement at a time.** `CONCURRENTLY` builds cannot be batched into a
  single script that runs in a transaction, and `VACUUM` / `ANALYZE` cannot run
  inside a transaction block at all.
- **A failed build leaves an `INVALID` index, and `IF NOT EXISTS` will then skip
  it.** `CONCURRENTLY` can fail partway and leave the index present but
  unusable; because the name now exists, replaying the statement is a no-op and
  the broken index stays. Always check first, and `DROP` before retrying:

  ```sql
  SELECT c.relname
  FROM pg_class c
  JOIN pg_index i ON i.indexrelid = c.oid
  WHERE NOT i.indisvalid;
  ```

  ```sql
  DROP INDEX CONCURRENTLY IF EXISTS idx_workflow_runs_workflow_created_covering;
  -- then re-run the CREATE INDEX CONCURRENTLY statement
  ```

- **`VACUUM (ANALYZE)`, not just `ANALYZE`, on every table you indexed.**
  `ANALYZE` refreshes the planner statistics that make an Index Only Scan
  *eligible*; the visibility map that lets it *skip the heap* is only built by
  `VACUUM`. Freshly created indexes on a table with no all-visible pages report
  `Heap Fetches` roughly equal to the row count and gain little.

  ```sql
  VACUUM (ANALYZE) conversations;
  VACUUM (ANALYZE) messages;
  VACUUM (ANALYZE) workflow_runs;
  VACUUM (ANALYZE) agent_runs;
  ```

## Verification

Confirm the planner actually uses them, rather than assuming. The statement must
reference **every** column of the production query — an `EXPLAIN` that omits
`AVG(total_duration_ms)` or `MAX(created_at)` will show an Index Only Scan that
the real query cannot get:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)                                     AS total_runs,
       COUNT(*) FILTER (WHERE status = 'success')   AS success_count,
       COUNT(*) FILTER (WHERE status = 'failed')    AS failed_count,
       COUNT(*) FILTER (WHERE status = 'timeout')   AS timeout_count,
       AVG(total_duration_ms) FILTER (WHERE total_duration_ms IS NOT NULL)
                                                    AS avg_duration_ms,
       MAX(created_at)                              AS last_run_at
FROM workflow_runs
WHERE workflow_id = '<id>'::uuid;
```

Expect an **Index Only Scan** with `Heap Fetches: 0`, not a bitmap index scan.
Note the expected node for this query is an Index Only Scan or, when the
planner has no reason to prefer it, a sequential scan — a *bitmap* plan here
means the index does not cover the query and something is missing from the
`INCLUDE` list or the key columns.

For the agent-side trend query, which is the other consumer of the merged index:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT date_trunc('day', created_at AT TIME ZONE 'Asia/Shanghai') AS bucket,
       COUNT(*)                                    AS runs,
       COUNT(*) FILTER (WHERE status = 'success')  AS success,
       AVG(total_duration_ms)                      AS avg_duration
FROM workflow_runs
WHERE workflow_id = '<id>'::uuid
  AND created_at >= now() - interval '30 days'
GROUP BY bucket;
```

If the planner keeps choosing a sequential scan on a small table, that is
genuinely the cheaper plan and no action is needed; the indexes exist for the
tables that grow.
