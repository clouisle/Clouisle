# Monitoring and Observability

Monitoring setup for Clouisle.

## Key Metrics

- **Request rate**: Requests per second
- **Response time**: p50, p95, p99 latency
- **Error rate**: 4xx and 5xx errors
- **Database performance**: Query time, connection pool
- **Celery tasks**: Queue length, execution time
- **Resource usage**: CPU, memory, disk

## Health Check Endpoints

- `/api/v1/health` - Basic health check
- `/api/v1/health/db` - Database connectivity
- `/api/v1/health/redis` - Redis connectivity
- `/api/v1/health/qdrant` - Qdrant connectivity

## Logging

### Application Logs

```bash
# Docker Compose
docker compose logs -f backend
docker compose logs -f worker

# Kubernetes
kubectl logs -f deployment/backend
kubectl logs -f deployment/worker
```

### Access Logs

- Nginx access logs (frontend)
- Gunicorn access logs (backend)

## Integration with Monitoring Tools

- **Prometheus**: Metrics collection
- **Grafana**: Visualization
- **Datadog**: Full-stack monitoring
- **ELK Stack**: Log aggregation

---

**Note**: This is a placeholder document. Please update with detailed content.

For more information, see the [main documentation](../README.md).
