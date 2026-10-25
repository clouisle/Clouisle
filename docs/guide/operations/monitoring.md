# Monitoring and Observability

Monitoring setup for Clouisle.

## Health Check Endpoints

- `/api/v1/health` — basic health check (no authentication; used by container health checks).
- `/api/v1/admin/observability/infrastructure` — bounded infrastructure snapshot, dependency health, and safe `pg_stat_statements` query display (requires `admin:dashboard:access`). Missing probes are reported as `unknown`; unavailable statistics are not shown as zero.

## Admin Observability

The observability API is rooted at `/api/v1/admin/observability`. Read endpoints require `admin:dashboard:access`; alert acknowledgement, silence, and rule updates require `admin:observability:manage`.

- `GET /summary?period=15m|1h|24h|7d&team_id=...` — compact run rollups and trends. Percentiles and success rates are `null` when samples are insufficient.
- `GET /runs` — summary-only keyset-paginated run list (`limit` 1–50); run detail is fetched separately from `GET /runs/{agent|workflow}/{run_id}`.
- `GET /dependencies` — model, tool, and retrieval aggregates when supported by recorded telemetry.
- `GET /queues` and `GET /infrastructure` — bounded current queue and infrastructure snapshots.
- `GET /alerts`, `GET /alerts/rules`; `POST /alerts/{id}/acknowledge`, `POST /alerts/{id}/silence?duration_seconds=...`; `PUT /alerts/rules/{id}`.

Run summaries are stored for 30 days in compact indexed records, separately from large diagnostic payloads. Summary list queries do not load message bodies. Tool/retrieval spans and on-demand tool results are available when captured; historical missing data is not reconstructed from current resource configuration. Diagnostic payloads may contain user messages, retrieved documents and tool results: treat `admin:dashboard:access` as privileged access to potentially sensitive runtime content, not merely aggregate metrics. Alert rules are evaluated on alert reads, and API maintenance performs bounded retention cleanup.

### Execution trajectory

Open a run from **Runs** to inspect `/dashboard/observability/runs/{agent|workflow}/{run_id}`. The timeline and ordered step list share a selection; the inspector provides summary, preview and raw data without losing the execution position. Use search, step type and failure filters to narrow an execution.
Steps occupy the full content row until a step is clicked, opening its detail on the right. Click the selected step again to collapse the detail. The page scrolls naturally; steps and detail share a 640px height capped at 70% of the viewport, with aligned top and bottom edges. Headers and filters stay fixed while each panel body scrolls independently.
The run list reuses the shared faceted-filter component: run ID searches query after 300ms without typing, while source/status selections apply immediately without an Apply button. Debouncing uses the shared useDebounce hook in this page only; generic controls are unchanged. Source and status each remain single-valued; clearing a selection removes that restriction. Filter by failed status and inspect the run record or detail for error information.

`GET /runs/{source}/{run_id}` includes lightweight `trajectory` entries. `GET /runs/{source}/{run_id}/trajectory/{entry_id}` loads the selected entry's input/output; entry lookup is scoped to that run and source. Both endpoints require the same operator read permission. The existing `/runs/{source}/{run_id}/tools/{tool_call_id}` endpoint still serves recorded model/display tool-result pairs.

New durable Agent runs capture application-normalized model messages, tool definitions and allowlisted inference settings before invocation, then actual responses and tool-call identities. These are not byte-exact provider HTTP requests: adapters can transform messages and add parameters. Tool steps link to the requesting model call. Workflow steps expose recorded node inputs, configuration and outputs, not invented conversation roles. Only reasoning actually returned by a provider can be displayed.

Model input and output snapshots are each limited to 256 KiB; oversized content is omitted and marked partial rather than silently presented as complete. Persistence is best effort with a 100 ms timeout per write, so a missing snapshot does not fail the Agent run. Payloads follow the 30-day telemetry retention window. Transport credentials and headers are not captured, but there is no automatic redaction of secrets embedded in user content or tool results. Historical missing context is shown as unrecorded; recording starts only after deployment.

## Integration schedules

The existing Beat process uses `app.core.integration_scheduler:IntegrationScheduler`. It reads administrator settings directly from the database, normally every two seconds; there is no separate synchronization task or Redis copy of the switches. Restart Beat once when upgrading to load this scheduler. Later feature/source changes apply without a restart.

- WeChat polling runs while either platform feature is enabled. Its dispatcher and batches use `default`, consumed by ordinary workers alongside their other queues. Durable claims still bound global backlog and preserve oldest-due fairness; polling now shares execution slots with other work. See [polling limits](../deployment/environment-variables.md#wechat-polling-limits) and [upgrade/index instructions](upgrading.md#wechat-polling-cutover).
- Feishu Agent recovery follows `agent_chat`. Login, notification and manual directory synchronization do not create periodic recovery tasks.
- Feishu Wiki dispatch is independent of these capabilities: it requires an enabled integration and at least one enabled source. Disable the sources to pause Wiki synchronization.

After reconciliation, disabled entries are absent from Beat's active schedule and no longer produce `Task ... succeeded` idle messages. Already queued tasks may still appear; workers recheck feature availability, and already-started operations may finish. If settings cannot be read, Beat pauses integration dispatch and logs `Integration schedule refresh failed; pausing integration tasks`; unrelated maintenance continues. Restore database access to resume enabled schedules. Keep exactly one Beat replica.

## Logging

### Application Logs

```bash
# Docker Compose
docker compose logs -f api
docker compose logs -f worker

# Kubernetes
kubectl logs -f deployment/api
kubectl logs -f deployment/worker
```

### Access Logs

- Gunicorn access logs (api)
- The frontend container runs `node server.js` directly; nginx is not part of the deployment. If you need reverse-proxy access logs, run nginx externally in front of the frontend.

## Integration with Monitoring Tools

> **Note:** Not implemented / Roadmap. Clouisle ships no `/metrics` endpoint and no built-in Prometheus, Grafana, Datadog, or ELK integration. For external monitoring, collect the application and access logs and poll the health endpoints and admin observability API.
