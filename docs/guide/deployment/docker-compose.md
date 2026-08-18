# Docker Deployment

This guide explains how to deploy Clouisle using Docker and Docker Compose.

> **Note**: The example snippets below are representative summaries. The authoritative files are `deploy/docker-compose.yml` (production) and `deploy/docker-compose.dev.yml` (local development) — always use those when in doubt.

## Overview

Docker deployment provides:

- **Easy setup**: Quick installation with minimal configuration
- **Consistency**: Same environment across development and production
- **Isolation**: Containerized services
- **Scalability**: Easy to scale services
- **Portability**: Deploy anywhere Docker runs

## Prerequisites

### System Requirements

**Planning baseline only (not a product guarantee):**
The following starting point is an estimate for a small deployment. Validate CPU, memory, and storage with a representative load test for your workload before production use.
- CPU: 4 cores
- RAM: 8 GB
- Storage: 50 GB
- OS: Linux, macOS, or Windows with WSL2

**Example production starting point (also load-test-required):**
- CPU: 8+ cores
- RAM: 16+ GB
- Storage: 100+ GB SSD
- OS: Linux (Ubuntu 22.04 LTS or similar)

### Required Software

**Install Docker:**

```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Verify installation
docker --version
```

**Install Docker Compose:**

```bash
# Docker Compose v2 (recommended)
sudo apt-get update
sudo apt-get install docker-compose-plugin

# Verify installation
docker compose version
```

## Quick Start

### Guided Installation

```bash
curl -fsSL https://raw.githubusercontent.com/clouisle/Clouisle/main/deploy/install.sh | bash
```

Choose Docker Compose when prompted. The installer downloads the current deployment files into an installation directory (default `/opt/clouisle`), generates required secrets, validates the configuration, pulls images, and starts the services. For non-interactive installation:

```bash
curl -fsSL https://raw.githubusercontent.com/clouisle/Clouisle/main/deploy/install.sh | \
  CLOUISLE_DEPLOYMENT=docker CLOUISLE_YES=1 bash
```

### Manual Installation from Source

```bash
git clone https://github.com/clouisle/Clouisle.git
cd Clouisle/deploy
```

### Configure Environment

**Copy environment template:**

```bash
cp .env.example .env
```

**Edit `.env` file** (see [Environment Variables](./environment-variables.md) for the full reference):

```bash
# General
SECRET_KEY=generate-a-secure-random-key-here
TIMEZONE=Asia/Shanghai

# Internal service URLs (keep these on the private Compose network)
API_BASE_URL=http://api:8000
API_INTERNAL_BASE_URL=http://api:8000

# Public/browser origins (set these to the deployed public origin)
PUBLIC_API_URL=
FRONTEND_URL=http://localhost:3000
BACKEND_CORS_ORIGINS=["http://localhost:3000"]

# Worker -> API internal file gateway (required)
INTERNAL_API_TOKEN=generate-a-secure-random-token

# Database
POSTGRES_SERVER=db
POSTGRES_PORT=5432
POSTGRES_DB=clouisle
POSTGRES_USER=postgres
POSTGRES_PASSWORD=change-this-password

# Redis
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=change-this-password

# Qdrant (Vector Database)
VECTOR_BACKEND=qdrant
QDRANT_URL=http://qdrant:6333
QDRANT_API_KEY=

# Sandbox artifact upload (optional auth key)
SANDBOX_ARTIFACT_UPLOAD_BASE_URL=http://api:8000
SANDBOX_ARTIFACT_UPLOAD_API_KEY=

# External APIs (optional)
TAVILY_API_KEY=
```

**Generate the required token and keys:**

```bash
# Generate SECRET_KEY
openssl rand -base64 32

# Generate INTERNAL_API_TOKEN (required by docker-compose.yml)
openssl rand -hex 32
```

### Start Services

**Start all services:**

```bash
docker compose up -d
```

**Check service status:**

```bash
docker compose ps
```

**Expected services** (8 total — 5 application + 3 infrastructure):

```
NAME                     COMMAND                             SERVICE          STATUS
clouisle-db-1            "postgres -c shared_…"              db               Up (healthy)
clouisle-redis-1         "docker-entrypoint.s…"              redis            Up (healthy)
clouisle-qdrant-1        "/qdrant/qdrant"                    qdrant           Up (healthy)
clouisle-api-1           "python main.py server…"            api              Up (healthy)
clouisle-worker-1        "python main.py worker…"            worker           Up
clouisle-sandbox-worker-1 "python main.py sandbox…"          sandbox-worker   Up
clouisle-beat-1          "python main.py beat"               beat             Up
clouisle-frontend-1      "node server.js"                    frontend         Up
```

### Initialize Database

No migration step is required — Clouisle uses Tortoise ORM and creates/updates tables automatically at startup (there is no Alembic). No admin seeding is needed either: **the first registered user automatically becomes a superuser** (bypasses registration restrictions and is assigned the Super Admin role).

### Access Application

**Open browser:**

```
http://localhost:3000
```

Register the first account to create the initial superuser, then configure LLM providers and site settings through the admin UI.

## Docker Compose Configuration

### docker-compose.yml

The production Compose file (`deploy/docker-compose.yml`) defines these services:

| Service | Image | Command | Ports |
|---------|-------|---------|-------|
| `db` | `registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-postgres-pg-search:0.24.3-pg17-alpine1` | `postgres -c shared_preload_libraries=pg_search,pg_stat_statements` | 5432 |
| `redis` | `redis:7-alpine` | `redis-server --requirepass …` (when password set) | 6379 |
| `qdrant` | `qdrant/qdrant:v1.18.3` | default | 6333 |
| `api` | `registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-backend:latest` | `python main.py server -H 0.0.0.0 -w 4 --no-reload` | 8000 |
| `worker` | `registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-backend:latest` | `python main.py worker -c 4 -Q default,knowledge,workflow` | — |
| `sandbox-worker` | `registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-sandbox-worker:latest` | `python main.py sandbox-worker -c ${SANDBOX_WORKER_CONCURRENCY:-1}` | — |
| `beat` | `registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-backend:latest` | `python main.py beat` | — |
| `frontend` | `registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-frontend:latest` | `node server.js` (image default) | 3000 |

There is **no `nginx` service** in Compose. The frontend container runs the Next.js standalone server and proxies `/api/*` to the backend via Next.js rewrites (`BACKEND_INTERNAL_URL`).

Representative excerpt (condensed; see `deploy/docker-compose.yml` for the full file):

```yaml
services:
  db:
    image: registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-postgres-pg-search:0.24.3-pg17-alpine1
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-postgres}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}
      POSTGRES_DB: ${POSTGRES_DB:-clouisle}
    command: ["postgres", "-c", "shared_preload_libraries=pg_search,pg_stat_statements", "-c", "pg_stat_statements.track=all"]
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-postgres}"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    command: >
      sh -c '
        if [ -n "$REDIS_PASSWORD" ]; then
          redis-server --requirepass "$REDIS_PASSWORD"
        else
          redis-server
        fi
      '
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"

  qdrant:
    image: qdrant/qdrant:v1.18.3
    environment:
      QDRANT__SERVICE__API_KEY: ${QDRANT_API_KEY:-}
    volumes:
      - qdrant_data:/qdrant/storage
    ports:
      - "6333:6333"
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://localhost:6333/healthz || exit 1"]

  api:
    image: registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-backend:latest
    command: ["python", "main.py", "server", "-H", "0.0.0.0", "-w", "4", "--no-reload"]
    env_file: .env
    environment:
      API_BASE_URL: http://api:8000
      POSTGRES_SERVER: db
      REDIS_HOST: redis
      QDRANT_URL: http://qdrant:6333
      INTERNAL_API_TOKEN: ${INTERNAL_API_TOKEN:?INTERNAL_API_TOKEN is required}
    volumes:
      - uploads_data:/app/uploads
    ports:
      - "8000:8000"
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')"]
      interval: 10s
      timeout: 5s
      retries: 12
    depends_on:
      db: { condition: service_healthy }
      redis: { condition: service_healthy }
      qdrant: { condition: service_healthy }

  worker:
    image: registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-backend:latest
    command: ["python", "main.py", "worker", "-c", "4", "-Q", "default,knowledge,workflow"]
    env_file: .env
    environment:
      UPLOAD_STORAGE_MODE: remote
      API_INTERNAL_BASE_URL: ${API_INTERNAL_BASE_URL:-http://api:8000}
      INTERNAL_API_TOKEN: ${INTERNAL_API_TOKEN:?INTERNAL_API_TOKEN is required}
    # no uploads volume — files are fetched through the API gateway
    depends_on:
      db: { condition: service_healthy }
      api: { condition: service_healthy }

  sandbox-worker:
    image: registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-sandbox-worker:latest
    command: ["python", "main.py", "sandbox-worker", "-c", "${SANDBOX_WORKER_CONCURRENCY:-1}"]
    user: "0"
    security_opt:
      - no-new-privileges:true
      - seccomp=unconfined
    cap_add:
      - SYS_ADMIN
    environment:
      UPLOAD_STORAGE_MODE: remote
      API_INTERNAL_BASE_URL: ${API_INTERNAL_BASE_URL:-http://api:8000}
      INTERNAL_API_TOKEN: ${INTERNAL_API_TOKEN:?INTERNAL_API_TOKEN is required}
    depends_on:
      db: { condition: service_healthy }
      api: { condition: service_healthy }

  beat:
    image: registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-backend:latest
    command: ["python", "main.py", "beat"]
    env_file: .env
    depends_on:
      db: { condition: service_healthy }
      api: { condition: service_started }

  frontend:
    image: registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-frontend:latest
    environment:
      BACKEND_INTERNAL_URL: ${BACKEND_INTERNAL_URL:-http://api:8000}
    ports:
      - "3000:3000"
    depends_on:
      api: { condition: service_started }

volumes:
  postgres_data:
  redis_data:
  qdrant_data:
  uploads_data:
```

### Development Configuration

`deploy/docker-compose.dev.yml` (local development infrastructure):

```yaml
services:
  db:
    image: registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-postgres-pg-search:0.24.3-pg17-alpine1
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: password
      POSTGRES_DB: clouisle
    ports:
      - "5432:5432"
    command: ["postgres", "-c", "shared_preload_libraries=pg_search,pg_stat_statements", "-c", "pg_stat_statements.track=all"]
    volumes:
      - postgres17_data:/var/lib/postgresql/data

  redis:
    image: redis:alpine
    ports:
      - "6379:6379"
    command: ["redis-server", "--requirepass", "clouisle-redis-cbd3c07d"]
    volumes:
      - redis_data:/data

  qdrant:
    image: qdrant/qdrant:v1.18.3
    ports:
      - "6333:6333"
      - "6334:6334"
    environment:
      QDRANT__SERVICE__API_KEY: ${QDRANT_API_KEY:?QDRANT_API_KEY is required}
    volumes:
      - qdrant_data:/qdrant/storage

volumes:
  postgres17_data:
  redis_data:
  qdrant_data:
```

**Start development services (Qdrant requires a non-empty API key):**

```bash
export QDRANT_API_KEY="replace-with-a-development-key"
: "${QDRANT_API_KEY:?QDRANT_API_KEY must be non-empty}"
docker compose -f docker-compose.dev.yml up -d
```

## Service Management

### Starting Services

**Start all services:**

```bash
docker compose up -d
```

**Start specific service:**

```bash
docker compose up -d api
```

**Start with logs:**

```bash
docker compose up
```

### Stopping Services

**Stop all services:**

```bash
docker compose down
```

**Stop and remove volumes (DESTROYS DATA):**

```bash
docker compose down -v
```

**Stop specific service:**

```bash
docker compose stop api
```

### Restarting Services

> `docker compose restart` stops and starts the selected containers and can cause downtime. It is not a zero-downtime restart.

**Restart all services:**

```bash
docker compose restart
```

**Restart specific service:**

```bash
docker compose restart api
```

### Viewing Logs

**View all logs:**

```bash
docker compose logs
```

**Follow logs:**

```bash
docker compose logs -f
```

**View specific service logs:**

```bash
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f sandbox-worker
docker compose logs -f beat
docker compose logs -f frontend
```

**View last 100 lines:**

```bash
docker compose logs --tail=100 api
```

## Updating Deployment

### Update Application

```bash
# Pull latest images and restart
docker compose pull
docker compose up -d
```

No manual migration step is needed — schema updates run automatically at backend startup (Tortoise ORM; no Alembic).

### Scaling

```bash
# Scale Celery workers (safe to run multiple)
docker compose up -d --scale worker=4

# Before scaling the API, remove the api service's host port mapping
# ("8000:8000") from the Compose file; one host port cannot be shared by
# multiple API replicas. The frontend proxy uses the internal service name.
# Then scale API replicas:
docker compose up -d --scale api=2

# Scale sandbox workers
docker compose up -d --scale sandbox-worker=2

# NEVER scale beat beyond 1
# docker compose up -d --scale beat=2  ← DO NOT DO THIS
```

## Backup and Restore

### Database Backup

**Create backup:**

```bash
docker compose exec -T db pg_dump -U postgres -Fc clouisle > backup_$(date +%Y%m%d_%H%M%S).dump
```

**Automated backup script:**

```bash
#!/bin/bash
# backup.sh

BACKUP_DIR="/backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/clouisle_$DATE.dump"

# Create a custom-format backup
docker compose exec -T db pg_dump -U postgres -Fc clouisle > "$BACKUP_FILE"

# Compress backup
gzip "$BACKUP_FILE"

# Keep only last 7 days
find "$BACKUP_DIR" -name "clouisle_*.dump.gz" -mtime +7 -delete

echo "Backup completed: $BACKUP_FILE.gz"
```

**Schedule with cron:**

```bash
# Add to crontab
0 2 * * * /path/to/backup.sh
```

### Database Restore

**Restore from backup:**

```bash
# Stop services
docker compose down

# Start only database
docker compose up -d db

# Wait for database to be ready
sleep 10

# Restore the custom-format backup
gunzip -c backup_20260211_020000.dump.gz | \
  docker compose exec -T db pg_restore -U postgres -d clouisle --clean --if-exists

# Start all services
docker compose up -d
```

### Uploads Backup

Do not hard-code Compose project-prefixed volume names; the prefix changes with the Compose project name. Use a logical PostgreSQL dump and archive uploads through the API container instead:

```bash
# PostgreSQL backup (the supported database backup method)
docker compose exec -T db pg_dump -U postgres -Fc -d clouisle > postgres_$(date +%Y%m%d_%H%M%S).dump

# Uploads backup (uploads are mounted by api only)
docker compose exec -T api tar czf - -C /app uploads > uploads_$(date +%Y%m%d_%H%M%S).tar.gz
```

Keep these files outside the Compose project directory and protect them as sensitive backups.

See [Backup & Recovery](./backup-recovery.md) for the full backup/restore procedures.

## Monitoring

### Health Checks

**Check service health:**

```bash
docker compose ps
```

**Check backend health:**

```bash
curl http://localhost:8000/api/v1/health
```

**Expected response:**

```json
{"code": 0, "data": {"status": "healthy"}, "msg": "success"}
```

Qdrant exposes its own health endpoint at `http://localhost:6333/healthz`.

### Resource Usage

**View resource usage:**

```bash
docker stats
```

**View specific service:**

```bash
docker stats clouisle-api-1
```

### Logs Monitoring

**Monitor logs in real-time:**

```bash
docker compose logs -f --tail=100
```

**Search logs:**

```bash
docker compose logs | grep ERROR
```

## Troubleshooting

### Services Not Starting

**Problem**: Services fail to start

**Solutions:**

1. **Check logs:**
```bash
docker compose logs
```

2. **Check port conflicts:**
```bash
sudo lsof -i :8000
sudo lsof -i :3000
```

3. **Check environment variables:**
```bash
docker compose config
```

4. **Rebuild images:**
```bash
docker compose pull
docker compose up -d
```

### Database Connection Issues

**Problem**: Cannot connect to database

**Solutions:**

1. **Check database is running:**
```bash
docker compose ps db
```

2. **Check database logs:**
```bash
docker compose logs db
```

3. **Test connection:**
```bash
docker compose exec db psql -U postgres -d clouisle -c "SELECT 1"
```

4. **Verify credentials:**
```bash
docker compose exec api env | grep POSTGRES
```

### Out of Memory

**Problem**: Services crashing due to memory

**Solutions:**

1. **Check memory usage:**
```bash
docker stats
```

2. **Restart Docker:**
```bash
sudo systemctl restart docker
```

### Disk Space Issues

**Problem**: Running out of disk space

**Solutions:**

1. **Check disk usage:**
```bash
docker system df
```

2. **Clean up:**
```bash
# Remove unused images
docker image prune -a

# Remove unused volumes
docker volume prune

# Remove everything unused
docker system prune -a --volumes
```

3. **Check volume sizes:**
```bash
docker volume ls
docker volume inspect deploy_postgres_data
```

## Best Practices

### Security

**✅ Do:**
- Use strong passwords
- Enable HTTPS
- Keep Docker updated
- Use secrets management
- Limit container privileges
- Regular security updates
- Monitor logs

**❌ Don't:**
- Use default passwords
- Expose unnecessary ports (remove the db/redis/qdrant/api port mappings in production)
- Commit secrets to git
- Skip security updates

### Performance

**✅ Do:**
- Use volume mounts for data
- Enable health checks
- Monitor resource usage
- Use caching

**❌ Don't:**
- Skip health checks
- Ignore resource limits
- Rebuild unnecessarily

### Maintenance

**✅ Do:**
- Regular backups
- Monitor logs
- Update regularly
- Test updates in staging
- Document changes
- Keep backups offsite

**❌ Don't:**
- Skip backups
- Ignore errors
- Update without testing
- Delete old backups immediately

## Related Documentation

- [Environment Variables](./environment-variables.md) - Configuration reference
- [Deployment Guide](./DEPLOYMENT.md) - Full deployment guide
- [Kubernetes Deployment](./kubernetes.md) - K8s deployment
- [Troubleshooting](./troubleshooting.md) - Common issues
- [Backup & Recovery](./backup-recovery.md) - Backup procedures

---

**Last Updated**: 2026-08-14
