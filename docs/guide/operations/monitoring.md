# Monitoring and Observability

Monitoring setup for Clouisle.

## Health Check Endpoints

- `/api/v1/health` - Basic health check (no authentication; used by container healthchecks)
- `/api/v1/admin/observability/system/health` - Detailed system health: CPU, memory, disk, database, Redis, and Celery workers (requires `admin:dashboard:access`)

## Admin Observability

> **Note:** Clouisle has no Prometheus-style `/metrics` endpoint. Observability data is provided by the admin observability API under `/api/v1/admin/observability/*` and the frontend Observability dashboard (`/dashboard/observability`). All endpoints require the `admin:dashboard:access` permission and accept a `time_range` of `7d`, `30d`, `90d`, or `all`.

- `/overview` - Summary statistics for the selected time range
- `/agents`, `/agent/{agent_id}` - Agent request counts, latency percentiles (p50/p95), success rate, token usage
- `/workflows`, `/workflow/{workflow_id}` - Workflow run statistics, failure rates, token usage
- `/timeouts`, `/throughput`, `/tokens` - Timeout events, request throughput, token consumption by model
- `/system/health`, `/system/trend`, `/system/slow-queries`, `/system/workers` - System health snapshots, Celery queue lengths and worker statistics, slow database queries

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
