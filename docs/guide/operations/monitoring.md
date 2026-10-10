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

Run summaries are stored for 30 days in compact indexed records. Only allowlisted timing, status, model name, token-count, resource/team identifiers and error codes are recorded; prompts, message bodies, tool arguments/results, credentials, and tracebacks are not stored. Historical runs without submission timestamps are not backfilled. New agent records include model aggregates and a safe root run span; tool/retrieval child spans and their aggregates are not captured and are marked unavailable rather than inferred. Alert rules are evaluated on alert reads; evaluation therefore depends on the API being reachable, and the scheduled retention task uses the existing `default` Celery queue.

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
