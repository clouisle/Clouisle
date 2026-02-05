# Clouisle Deployment Guide

This document provides a complete deployment guide for the Clouisle platform, including detailed instructions for three deployment options.

## Table of Contents

- [System Requirements](#system-requirements)
- [Deployment Options Overview](#deployment-options-overview)
- [Option 1: All-in-One Deployment](#option-1-all-in-one-deployment)
- [Option 2: App Deployment](#option-2-app-deployment)
- [Option 3: Microservices Deployment](#option-3-microservices-deployment)
- [Environment Variables](#environment-variables)
- [Reverse Proxy Configuration](#reverse-proxy-configuration)
- [SSL/HTTPS Configuration](#sslhttps-configuration)
- [Backup and Recovery](#backup-and-recovery)
- [Monitoring and Logs](#monitoring-and-logs)
- [FAQ](#faq)
- [Upgrade Guide](#upgrade-guide)

---

## System Requirements

### Hardware Requirements

| Deployment Option | CPU | Memory | Disk |
|-------------------|-----|--------|------|
| All-in-One | 2+ cores | 4 GB+ | 20 GB+ |
| App | 2+ cores | 4 GB+ | 20 GB+ |
| Microservices | 4+ cores | 8 GB+ | 40 GB+ |

### Software Requirements

- Docker 20.10+
- Docker Compose 2.0+
- (Optional) Nginx for reverse proxy

### Network Requirements

| Port | Purpose | Deployment Option |
|------|---------|-------------------|
| 80 | HTTP access | All-in-One |
| 443 | HTTPS access | All (via reverse proxy) |
| 3000 | Frontend service | App / Microservices |
| 8000 | Backend API | App / Microservices |

---

## Deployment Options Overview

Clouisle offers three deployment options for different scenarios:

| Option | Containers | Use Case | Complexity |
|--------|------------|----------|------------|
| **All-in-One** | 1 | Development, testing, demos, small deployments | Low |
| **App** | 4 | Small to medium production environments | Medium |
| **Microservices** | 7 | Large production environments, independent scaling | High |

### Docker Images

All images are hosted on GitHub Container Registry:

```
ghcr.io/yunhai-dev/clouisle:all-in-one   # Full stack image (with databases)
ghcr.io/yunhai-dev/clouisle:app          # Application image (Frontend+Backend+Worker+Beat)
ghcr.io/yunhai-dev/clouisle:frontend     # Frontend image
ghcr.io/yunhai-dev/clouisle:backend      # Backend API image
ghcr.io/yunhai-dev/clouisle:worker       # Celery Worker image
ghcr.io/yunhai-dev/clouisle:beat         # Celery Beat image
```

---

## Option 1: All-in-One Deployment

Single container with all services: Frontend, Backend, Worker, Beat, PostgreSQL, Redis, Qdrant, Nginx.

**Pros**: Simple deployment, low resource usage, quick to get started
**Cons**: Not suitable for high availability, cannot scale independently

### 1.1 Quick Deployment

```bash
# Create deployment directory
mkdir -p /opt/clouisle && cd /opt/clouisle

# Download configuration files
curl -O https://raw.githubusercontent.com/yunhai-dev/Clouisle/main/deploy/docker-compose.all-in-one.yml
curl -O https://raw.githubusercontent.com/yunhai-dev/Clouisle/main/.env.example

# Create environment configuration
cp .env.example .env

# Edit configuration (at least change SECRET_KEY)
nano .env

# Start services
docker-compose -f docker-compose.all-in-one.yml up -d
```

### 1.2 Environment Configuration

Edit the `.env` file:

```bash
# Required changes
SECRET_KEY=your-secure-random-key-at-least-32-characters

# Optional changes
PROJECT_NAME=Clouisle
TIMEZONE=Asia/Shanghai
POSTGRES_PASSWORD=your-db-password
REDIS_PASSWORD=your-redis-password
QDRANT_API_KEY=your-qdrant-key
```

### 1.3 Access Services

After deployment, access `http://your-server-ip` to use the application.

### 1.4 Data Persistence

All-in-One mode uses the following Docker volumes:

| Volume | Purpose |
|--------|---------|
| `clouisle_postgres` | PostgreSQL data |
| `clouisle_redis` | Redis data |
| `clouisle_qdrant` | Qdrant vector data |
| `clouisle_uploads` | User uploaded files |
| `clouisle_logs` | Application logs |

---

## Option 2: App Deployment

Application container (Frontend + Backend + Worker + Beat) + separate database containers.

**Pros**: Independent database management, easier backup and maintenance
**Cons**: Cannot scale components independently

### 2.1 Quick Deployment

```bash
# Create deployment directory
mkdir -p /opt/clouisle && cd /opt/clouisle

# Download configuration files
curl -O https://raw.githubusercontent.com/yunhai-dev/Clouisle/main/deploy/docker-compose.app.yml
curl -O https://raw.githubusercontent.com/yunhai-dev/Clouisle/main/.env.example

# Create environment configuration
cp .env.example .env
nano .env

# Start services
docker-compose -f docker-compose.app.yml up -d
```

### 2.2 Service Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    docker-compose                        │
│  ┌─────────────────────────────────────────────────┐    │
│  │              clouisle-app (:3000, :8000)        │    │
│  │  ┌──────────┐ ┌──────────┐ ┌────────┐ ┌──────┐ │    │
│  │  │ Frontend │ │ Backend  │ │ Worker │ │ Beat │ │    │
│  │  └──────────┘ └──────────┘ └────────┘ └──────┘ │    │
│  └─────────────────────────────────────────────────┘    │
│                          │                               │
│         ┌────────────────┼────────────────┐             │
│         ▼                ▼                ▼             │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐        │
│  │ PostgreSQL │  │   Redis    │  │   Qdrant   │        │
│  │  (db)      │  │  (redis)   │  │  (qdrant)  │        │
│  └────────────┘  └────────────┘  └────────────┘        │
└─────────────────────────────────────────────────────────┘
```

### 2.3 Access Services

- Frontend: `http://your-server-ip:3000`
- API: `http://your-server-ip:8000`
- API Docs: `http://your-server-ip:8000/docs`

### 2.4 Using External Databases

If you already have PostgreSQL, Redis, and Qdrant services, modify `docker-compose.app.yml`:

```yaml
services:
  app:
    image: ghcr.io/yunhai-dev/clouisle:app
    ports:
      - "3000:3000"
      - "8000:8000"
    environment:
      # Point to external databases
      POSTGRES_SERVER: your-postgres-host
      POSTGRES_PORT: 5432
      POSTGRES_USER: your-user
      POSTGRES_PASSWORD: your-password
      POSTGRES_DB: clouisle
      REDIS_HOST: your-redis-host
      REDIS_PORT: 6379
      REDIS_PASSWORD: your-redis-password
      QDRANT_URL: http://your-qdrant-host:6333
      QDRANT_API_KEY: your-qdrant-key
      # ... other configuration
    volumes:
      - uploads_data:/app/uploads
      - logs_data:/var/log/supervisor

volumes:
  uploads_data:
  logs_data:
```

---

## Option 3: Microservices Deployment

Independent containers for each component, supporting independent scaling.

**Pros**: High availability, independent scaling, fault isolation
**Cons**: Complex configuration, higher resource usage

### 3.1 Quick Deployment

```bash
# Create deployment directory
mkdir -p /opt/clouisle && cd /opt/clouisle

# Download configuration files
curl -O https://raw.githubusercontent.com/yunhai-dev/Clouisle/main/deploy/docker-compose.microservices.yml
curl -O https://raw.githubusercontent.com/yunhai-dev/Clouisle/main/.env.example

# Create environment configuration
cp .env.example .env
nano .env

# Start services
docker-compose -f docker-compose.microservices.yml up -d
```

### 3.2 Service Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                      docker-compose                           │
│                                                               │
│  ┌──────────────┐  ┌──────────────┐                          │
│  │   frontend   │  │   backend    │                          │
│  │   (:3000)    │  │   (:8000)    │                          │
│  └──────────────┘  └──────────────┘                          │
│                           │                                   │
│         ┌─────────────────┼─────────────────┐                │
│         ▼                 ▼                 ▼                │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐             │
│  │   worker   │  │    beat    │  │   qdrant   │             │
│  └────────────┘  └────────────┘  └────────────┘             │
│         │                 │                                   │
│         └────────┬────────┘                                  │
│                  ▼                                            │
│  ┌────────────────────────────────────────────┐              │
│  │              PostgreSQL + Redis             │              │
│  └────────────────────────────────────────────┘              │
└──────────────────────────────────────────────────────────────┘
```

### 3.3 Scaling Workers

Scale Worker count based on load:

```bash
# Scale to 3 Worker instances
docker-compose -f docker-compose.microservices.yml up -d --scale worker=3
```

### 3.4 Access Services

- Frontend: `http://your-server-ip:3000`
- API: `http://your-server-ip:8000`
- API Docs: `http://your-server-ip:8000/docs`

---

## Environment Variables

### Complete Configuration Reference

```bash
# =============================================================================
# Application Configuration
# =============================================================================
PROJECT_NAME=Clouisle                    # Project name
SECRET_KEY=your-secret-key               # JWT signing key (must change!)
TIMEZONE=Asia/Shanghai                   # Timezone

# URL Configuration (modify based on actual deployment address)
API_BASE_URL=http://localhost:8000       # Backend API address
FRONTEND_URL=http://localhost:3000       # Frontend address

# =============================================================================
# PostgreSQL Database
# =============================================================================
POSTGRES_SERVER=localhost                # Database host
POSTGRES_PORT=5432                       # Database port
POSTGRES_USER=postgres                   # Database user
POSTGRES_PASSWORD=password               # Database password (must change for production!)
POSTGRES_DB=clouisle                     # Database name

# Or use full DSN (higher priority)
# DATABASE_URL=postgres://user:pass@host:5432/dbname

# =============================================================================
# Redis Cache/Message Queue
# =============================================================================
REDIS_HOST=localhost                     # Redis host
REDIS_PORT=6379                          # Redis port
REDIS_PASSWORD=your-redis-password       # Redis password

# =============================================================================
# Qdrant Vector Database
# =============================================================================
VECTOR_BACKEND=qdrant                    # Vector database type
QDRANT_URL=http://localhost:6333         # Qdrant address
QDRANT_API_KEY=your-qdrant-key           # Qdrant API key
QDRANT_COLLECTION_PREFIX=kb_dim          # Collection prefix
QDRANT_DISTANCE=Cosine                   # Distance calculation method

# =============================================================================
# External APIs (Optional)
# =============================================================================
TAVILY_API_KEY=                          # Tavily search API key

# =============================================================================
# Frontend Configuration
# =============================================================================
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1  # API URL for frontend
```

### Generate Secure Key

```bash
# Using openssl
openssl rand -hex 32

# Or using Python
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## Reverse Proxy Configuration

For production environments, we recommend using Nginx as a reverse proxy for unified entry and SSL termination.

### Nginx Configuration Example

Create `/etc/nginx/sites-available/clouisle`:

```nginx
# HTTP redirect to HTTPS
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

# HTTPS configuration
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    # SSL certificates
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers off;

    # Upload file size limit
    client_max_body_size 100M;

    # API requests proxy to backend
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE/Streaming support
        proxy_set_header Connection '';
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 86400s;
    }

    # API documentation
    location ~ ^/(docs|openapi.json|redoc) {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # Frontend requests
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

Enable configuration:

```bash
ln -s /etc/nginx/sites-available/clouisle /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx
```

---

## SSL/HTTPS Configuration

### Using Let's Encrypt (Recommended)

```bash
# Install Certbot
apt install certbot python3-certbot-nginx

# Obtain certificate
certbot --nginx -d your-domain.com

# Auto-renewal (Certbot configures this automatically)
certbot renew --dry-run
```

### Using Self-Signed Certificate (Testing)

```bash
# Generate self-signed certificate
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/ssl/private/clouisle.key \
  -out /etc/ssl/certs/clouisle.crt
```

---

## Backup and Recovery

### PostgreSQL Backup

```bash
# Backup database
docker exec clouisle-db pg_dump -U postgres clouisle > backup_$(date +%Y%m%d).sql

# Compressed backup
docker exec clouisle-db pg_dump -U postgres clouisle | gzip > backup_$(date +%Y%m%d).sql.gz
```

### PostgreSQL Recovery

```bash
# Restore database
cat backup_20240101.sql | docker exec -i clouisle-db psql -U postgres clouisle

# Restore from compressed file
gunzip -c backup_20240101.sql.gz | docker exec -i clouisle-db psql -U postgres clouisle
```

### Qdrant Backup

```bash
# Create snapshot
curl -X POST "http://localhost:6333/collections/kb_dim_*/snapshots" \
  -H "api-key: your-qdrant-key"

# Backup snapshot directory
docker cp clouisle-qdrant:/qdrant/storage/snapshots ./qdrant_backup
```

### Complete Backup Script

Create `/opt/clouisle/backup.sh`:

```bash
#!/bin/bash
set -e

BACKUP_DIR="/opt/clouisle/backups"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

echo "Backing up PostgreSQL..."
docker exec clouisle-db pg_dump -U postgres clouisle | gzip > $BACKUP_DIR/postgres_$DATE.sql.gz

echo "Backing up uploads..."
docker cp clouisle-app:/app/uploads $BACKUP_DIR/uploads_$DATE 2>/dev/null || \
docker cp clouisle-backend:/app/uploads $BACKUP_DIR/uploads_$DATE 2>/dev/null || \
docker cp clouisle-all-in-one:/app/uploads $BACKUP_DIR/uploads_$DATE

echo "Backing up Qdrant..."
docker cp clouisle-qdrant:/qdrant/storage $BACKUP_DIR/qdrant_$DATE

echo "Cleaning old backups (keep 7 days)..."
find $BACKUP_DIR -type f -mtime +7 -delete
find $BACKUP_DIR -type d -empty -delete

echo "Backup completed: $BACKUP_DIR"
```

Set up scheduled task:

```bash
chmod +x /opt/clouisle/backup.sh

# Run backup daily at 2 AM
crontab -e
# Add: 0 2 * * * /opt/clouisle/backup.sh >> /var/log/clouisle-backup.log 2>&1
```

---

## Monitoring and Logs

### View Logs

```bash
# All-in-One mode
docker logs clouisle-all-in-one -f

# View supervisor-managed service logs
docker exec clouisle-all-in-one tail -f /var/log/supervisor/backend.log
docker exec clouisle-all-in-one tail -f /var/log/supervisor/worker.log
docker exec clouisle-all-in-one tail -f /var/log/supervisor/frontend.log

# App mode
docker logs clouisle-app -f

# Microservices mode
docker logs clouisle-backend -f
docker logs clouisle-worker -f
docker logs clouisle-beat -f
docker logs clouisle-frontend -f
```

### View Service Status

```bash
# View all container status
docker-compose -f docker-compose.xxx.yml ps

# View resource usage
docker stats
```

### Health Checks

```bash
# Check backend API
curl http://localhost:8000/

# Check frontend
curl http://localhost:3000/

# Check database connection
docker exec clouisle-db pg_isready -U postgres

# Check Redis
docker exec clouisle-redis redis-cli -a your-password ping

# Check Qdrant
curl http://localhost:6333/collections -H "api-key: your-key"
```

---

## FAQ

### Q1: Container fails to start with database connection error

**Cause**: Database container not ready yet

**Solution**:
```bash
# Check database container status
docker-compose -f docker-compose.xxx.yml ps

# Restart app after database is ready
docker-compose -f docker-compose.xxx.yml restart app
# or
docker-compose -f docker-compose.xxx.yml restart backend
```

### Q2: Frontend cannot access backend API

**Cause**: `NEXT_PUBLIC_API_URL` misconfigured

**Solution**:
1. Check `NEXT_PUBLIC_API_URL` in `.env`
2. Ensure backend service is running
3. Check firewall allows relevant ports

### Q3: File upload fails

**Cause**: Upload directory permission issues or size limit

**Solution**:
```bash
# Check uploads directory
docker exec clouisle-app ls -la /app/uploads

# If using Nginx, check client_max_body_size configuration
```

### Q4: Worker not processing tasks

**Cause**: Redis connection issues or queue misconfiguration

**Solution**:
```bash
# Check Worker logs
docker logs clouisle-worker

# Check Redis connection
docker exec clouisle-redis redis-cli -a your-password ping

# Check tasks in queue
docker exec clouisle-redis redis-cli -a your-password llen celery
```

### Q5: Out of memory

**Cause**: Insufficient server resources

**Solution**:
```bash
# View memory usage
docker stats --no-stream

# Limit container memory (add to docker-compose.yml)
services:
  app:
    deploy:
      resources:
        limits:
          memory: 2G
```

### Q6: How to reset admin password

```bash
# Enter backend container
docker exec -it clouisle-backend bash
# or
docker exec -it clouisle-app bash

# Reset password using Python
cd /app/backend
python -c "
import asyncio
from app.models import User
from app.core.security import get_password_hash
from tortoise import Tortoise
from app.core.config import settings

async def reset_password():
    await Tortoise.init(db_url=settings.DATABASE_URL, modules={'models': ['app.models']})
    user = await User.get(username='admin')
    user.hashed_password = get_password_hash('new-password')
    await user.save()
    print('Password reset successfully')
    await Tortoise.close_connections()

asyncio.run(reset_password())
"
```

---

## Upgrade Guide

### Upgrade Steps

```bash
cd /opt/clouisle

# 1. Backup data
./backup.sh

# 2. Pull latest images
docker-compose -f docker-compose.xxx.yml pull

# 3. Stop services
docker-compose -f docker-compose.xxx.yml down

# 4. Start new version
docker-compose -f docker-compose.xxx.yml up -d

# 5. Check service status
docker-compose -f docker-compose.xxx.yml ps
docker-compose -f docker-compose.xxx.yml logs -f
```

### Rollback

If issues occur after upgrade:

```bash
# Stop services
docker-compose -f docker-compose.xxx.yml down

# Use specific version image
# Edit docker-compose.xxx.yml, change image tag to previous version
# e.g.: ghcr.io/yunhai-dev/clouisle:backend-v1.0.0

# Restart
docker-compose -f docker-compose.xxx.yml up -d

# Restore database if needed
cat backup_xxx.sql | docker exec -i clouisle-db psql -U postgres clouisle
```

---

## Production Checklist

Before deploying to production, confirm the following:

- [ ] Change `SECRET_KEY` to a secure random string
- [ ] Change all default passwords (PostgreSQL, Redis, Qdrant)
- [ ] Configure HTTPS/SSL certificates
- [ ] Configure firewall to only allow necessary ports
- [ ] Set up scheduled data backup
- [ ] Configure log rotation
- [ ] Set up monitoring and alerts
- [ ] Test backup and recovery process
- [ ] Document all configurations and passwords in a secure location

---

## Getting Help

- GitHub Issues: https://github.com/yunhai-dev/Clouisle/issues
- Documentation: https://github.com/yunhai-dev/Clouisle/docs
