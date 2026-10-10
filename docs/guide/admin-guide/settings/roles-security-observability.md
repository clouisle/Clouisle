# Role Management Admin Guide

Clouisle provides fine-grained Role-Based Access Control (RBAC) allowing workspace administrators to create custom roles and assign precise permission scopes.

---

## 1. Managing Roles

Navigate to **System Settings > Roles** (`/roles`):

1. **System Built-in Roles**:
   - `Super Admin`: Full system control with wildcard (`*`) bypass permissions.
   - `Admin`: Workspace-level administration (`admin:dashboard:access`, system read access, and team-scoped resource management).
   - `Team Admin`: Team administrator role with all Member permissions plus `team:update` and `team:manage` capabilities.
   - `Member`: Standard collaborative user who can create, edit, and execute team resources without dashboard access.
   - `Viewer`: Default read-only role with execute permissions (`agent:chat`, `workflow:run`, `tool:execute`, `skill:execute`, `conversation:read`).
2. **Creating Custom Roles**:
   - Click **Create Role**, provide a unique code and display name.
   - Select individual permissions across scopes (`agent:*`, `workflow:*`, `kb:*`, `tool:*`, `model:*`, `audit:*`).
3. **Assigning Roles**:
   - Assign roles to users during creation or edit existing user permissions under **User Management**.

---

# Security & Observability Admin Guide

## 1. Security Settings (`/site-settings/security`)

- **SSRF Outbound Network Allowlist**: Restrict HTTP request nodes, Webhook triggers, and document URL importers to prevent Server-Side Request Forgery against private subnets.
- **Enable Human Verification**: A single `enable_captcha` switch that shows human verification on the login and registration pages to defend against automated brute-force attacks. There is no separate verification threshold to configure.

## 2. System Observability (`/dashboard/observability`)

The console has six views. Use them to move from an overall signal to the run or dependency that needs attention:

- **Overview**: Agent and workflow throughput, success rates, latency, tokens, and recent trends.
- **Runs**: Filter run summaries and load a trace only when a run is opened. Agent traces include tool and knowledge retrieval calls; workflow traces include recorded node executions.
- **Dependencies**: Compare model, tool, and retrieval request counts, success rates, and latency percentiles. Model rows include first-token latency and token totals; tool and retrieval token counts are unavailable and display as `—`.
- **Queues**: Inspect worker activity, active queues, pending depth, and oldest wait time.
- **Infrastructure**: Review API container/Pod identities with explicitly host-scoped CPU and memory samples, dependency health, and available PostgreSQL slow-query statistics.
- **Alerts**: Tune evaluation and recovery windows, acknowledge events, and silence a rule for a bounded duration.

The time-range button opens a two-month calendar. Select a start and end date, then choose **Apply**; both dates include their whole local day in the browser's time zone, including daylight-saving transitions. Draft selection, dismissal, and **Cancel** leave the applied interval unchanged. The button displays the applied dates, and URL parameters preserve the interval across reloads, tab changes, refresh, and run pagination. **Quick ranges** at the bottom of the popover apply the last 15 minutes, last hour, or last 24 hours immediately and clear custom endpoints; these presets remain rolling intervals rather than whole calendar days.

Custom filtering applies to Overview, Runs, and Dependencies. Their `GET /api/v1/admin/observability/{summary,runs,dependencies}` endpoints accept `period=custom` with timezone-aware ISO 8601 `start_time` and `end_time`; both endpoints are inclusive and normalized to UTC. Missing, naive, equal, or reversed custom bounds, or explicit bounds combined with a preset, return HTTP 422. Queues, Infrastructure, and Alerts keep their existing live snapshots and event filters. Telemetry retention remains 30 days; choosing an older interval does not restore expired samples.

Model cards display the configured model name and provider label, preferring a custom provider/gateway display name when configured. UUID-based samples are resolved in a single batch without rewriting stored telemetry; aggregation remains scoped to each model UUID, so same-named configurations stay separate. Deleted or unresolved UUIDs display as unavailable while retaining their metrics. Legacy samples containing a model name keep that name without guessing a provider.

Queue snapshots collect active tasks, reserved tasks, scheduled tasks, and active queues concurrently using separate Celery inspectors. Each inspection has a 0.5-second reply collection timeout; the inspection phase retains a 2.2-second overall deadline. Redis queue lengths are read concurrently afterward. Snapshots retain the existing five-second per-API-process cache and are collected on demand, not by a new background task.

Infrastructure snapshots read the shared API instance registry alongside concurrent PostgreSQL/Redis health, Celery worker status, Qdrant connectivity, and slow-query statistics. Primary health sampling, registry reads, and slow-query statistics each have a two-second deadline; Celery uses a 0.5-second reply collection timeout within its existing 1.5-second deadline. Celery latency includes reply collection, not just worker response time. Failures in instance discovery or slow-query statistics do not suppress dependency health; discovery failure returns no instances and partial metadata rather than a fabricated local-only list. Request snapshots keep the five-second per-API-process cache and the page's 30-second refresh interval.

Each API identity reports its latest resource sample to shared Redis every ten seconds. A renewable, owner-checked lease elects one reporter across that identity's Gunicorn processes. Redis server time determines freshness: samples up to 30 seconds old retain their measured health state, samples over 30 seconds are `stale`, and samples over 60 seconds are `offline`. Last values and timestamps stay visible, marked as retained rather than current; records disappear after five minutes without a successful publication. Graceful shutdown releases only that reporter's lease and leaves its last sample to age, allowing another process of the same identity to take over.

Identity defaults to hostname, hashed for `instance_id`; display name defaults to hostname. Set `OBSERVABILITY_INSTANCE_ID` when multiple API deployments share a hostname, using a different value for each container/Pod and the same value for its Gunicorn processes. `OBSERVABILITY_INSTANCE_NAME` provides a readable label. All instances must use the same deployment Redis. Restart API processes after changing these settings. CPU and memory come from host-level `psutil` measurements (`metric_scope: host`), not container cgroup limits or API-process resource usage. This registry does not collect historical curves or Celery/Sandbox resource metrics.

`GET /api/v1/admin/observability/infrastructure` requires `admin:dashboard:access`. Its `instances` array now contains `instance_id`, `name`, `role: api`, `metric_scope: host`, nullable `cpu_percent`/`memory_percent`, `observed_at`, and `state` (`healthy`, `warning`, `unavailable`, `stale`, or `offline`). Missing metrics remain unavailable, never fabricated as zero; fresh CPU at least 70% or memory at least 80% marks the instance as warning.

Agent tool and retrieval spans are collected for durable AgentRuns after this instrumentation is deployed. Each run retains at most 128 dependency spans; the run detail marks traces that exceed the cap. This data is not backfilled for older runs. Workflow detail is bounded to 100 node spans and reports when the trace is incomplete.

Run summaries are best-effort telemetry, while AgentRun records are authoritative. If a terminal AgentRun still appears active in Runs, API maintenance reconciles its summary every minute in batches of at most 100. Runs become eligible 60 seconds after their recorded finish time and only within the 30-day telemetry retention window. Reconciliation restores status, timing, model, and token fields from the run and its final message, preserving captured dependency spans. It does not change active AgentRuns or replay model/tool calls. A larger backlog can take multiple maintenance cycles to clear; missing or expired historical summary rows are not recreated.

## 3. Dashboard Date Ranges (`/dashboard`)

The dashboard uses a two-month calendar popover. Select both dates and choose **Apply** to query whole local days, or use the bottom shortcuts for the last 7, 30, or 90 days or all time. Cancelling or dismissing the popover keeps the applied range. The URL preserves the range when reloading or switching between Overview, Models & Usage, and Analytics.

The selected interval filters trends, Agent rankings, team usage, model distribution, and workflow summaries. Overview conversation/token summaries, Models & Usage message/token summaries and averages, and Analytics message/average summaries also reflect the selected interval. Bounded Agent/team rankings use dated conversation and message records rather than lifetime counters; custom model distributions use historical messages rather than current quota counters. User/team/resource counts, DAU/WAU/MAU, fixed 30-day growth, password-expiration indicators, and TOTP statistics retain their existing definitions.

The five statistics endpoints under `/api/v1/admin/dashboard/stats` accept `start_time` and `end_time` as timezone-aware ISO 8601 timestamps with `period=custom` for `/trends`, or `time_range=custom` for `/agents/top`, `/teams/token-usage`, `/models/distribution`, and `/workflows/summary`. Bounds are inclusive and normalized to UTC. Both custom endpoints are required, start must precede end, and explicit endpoints cannot accompany a preset.
