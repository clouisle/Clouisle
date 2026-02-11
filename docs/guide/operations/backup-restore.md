# Backup and Restore

Backup and restore procedures for Clouisle.

## What to Backup

1. **PostgreSQL**: All application data
2. **Qdrant**: Vector embeddings
3. **Uploads**: User-uploaded files
4. **Redis**: Optional (cache and queue state)

## Backup Procedures

### PostgreSQL Backup

```bash
# Docker Compose
docker compose exec db pg_dump -U postgres clouisle > backup.sql

# Kubernetes
kubectl exec statefulset/postgres -- pg_dump -U postgres clouisle > backup.sql
```

### Qdrant Backup

```bash
# Backup the volume
docker run --rm -v qdrant_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/qdrant_backup.tar.gz -C /data .
```

### Uploads Backup

```bash
# Backup uploads directory
docker run --rm -v uploads_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/uploads_backup.tar.gz -C /data .
```

## Restore Procedures

### PostgreSQL Restore

```bash
# Docker Compose
docker compose exec -T db psql -U postgres clouisle < backup.sql

# Kubernetes
kubectl exec -i statefulset/postgres -- psql -U postgres clouisle < backup.sql
```

## Automated Backups

Set up daily backups with cron or Kubernetes CronJob.

See [Deployment Guide](../deployment/DEPLOYMENT.md) for detailed examples.

---

**Note**: This is a placeholder document. Please update with detailed content.

For more information, see the [main documentation](../README.md).
