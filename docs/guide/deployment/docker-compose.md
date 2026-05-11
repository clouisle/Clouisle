# Docker Deployment

This guide explains how to deploy Clouisle using Docker and Docker Compose.

## Overview

Docker deployment provides:

- **Easy setup**: Quick installation with minimal configuration
- **Consistency**: Same environment across development and production
- **Isolation**: Containerized services
- **Scalability**: Easy to scale services
- **Portability**: Deploy anywhere Docker runs

## Prerequisites

### System Requirements

**Minimum requirements:**
- CPU: 4 cores
- RAM: 8 GB
- Storage: 50 GB
- OS: Linux, macOS, or Windows with WSL2

**Recommended for production:**
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

### Clone Repository

```bash
git clone https://github.com/your-org/clouisle.git
cd clouisle
```

### Configure Environment

**Copy environment template:**

```bash
cp .env.example .env
```

**Edit `.env` file:**

```bash
# Basic Configuration
SITE_URL=https://your-domain.com
FRONTEND_URL=https://your-domain.com

# Database
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=clouisle
POSTGRES_USER=clouisle
POSTGRES_PASSWORD=change-this-password

# Redis
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=change-this-password

# Qdrant (Vector Database)
QDRANT_HOST=qdrant
QDRANT_PORT=6333

# Security
SECRET_KEY=generate-a-secure-random-key-here
JWT_SECRET=generate-another-secure-key-here

# Email (Optional)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password

# LLM Provider (Required)
OPENAI_API_KEY=your-openai-api-key
```

**Generate secure keys:**

```bash
# Generate SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Generate JWT_SECRET
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
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

**Expected output:**
```
NAME                COMMAND                  SERVICE    STATUS
clouisle-backend    "uvicorn app.main:ap…"   backend    Up
clouisle-frontend   "docker-entrypoint.s…"   frontend   Up
clouisle-postgres   "docker-entrypoint.s…"   postgres   Up
clouisle-redis      "docker-entrypoint.s…"   redis      Up
clouisle-qdrant     "/qdrant/qdrant"         qdrant     Up
clouisle-celery     "celery -A app.core.…"   celery     Up
```

### Initialize Database

**Run database migrations:**

```bash
docker compose exec api alembic upgrade head
```

**Create initial admin user:**

```bash
docker compose exec api python -m app.scripts.create_admin \
  --email admin@example.com \
  --password your-secure-password
```

### Access Application

**Open browser:**

```
http://localhost:3000
```

**Login with admin credentials:**
- Email: admin@example.com
- Password: your-secure-password

## Docker Compose Configuration

### docker-compose.yml

**Production configuration:**

```yaml
version: '3.8'

services:
  # PostgreSQL Database
  postgres:
    image: postgres:15-alpine
    container_name: clouisle-postgres
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  # Redis Cache
  redis:
    image: redis:7-alpine
    container_name: clouisle-redis
    command: redis-server --requirepass ${REDIS_PASSWORD}
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  # Qdrant Vector Database
  qdrant:
    image: qdrant/qdrant:latest
    container_name: clouisle-qdrant
    volumes:
      - qdrant_data:/qdrant/storage
    ports:
      - "6333:6333"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:6333/health"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  # Backend API
  api:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: clouisle-backend
    environment:
      - DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
      - REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
      - QDRANT_URL=http://qdrant:6333
      - SECRET_KEY=${SECRET_KEY}
      - JWT_SECRET=${JWT_SECRET}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    volumes:
      - ./api:/app
      - backend_uploads:/app/uploads
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      qdrant:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped

  # Celery Worker
  celery:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: clouisle-celery
    command: celery -A app.core.celery worker --loglevel=info
    environment:
      - DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
      - REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
      - QDRANT_URL=http://qdrant:6333
      - SECRET_KEY=${SECRET_KEY}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    volumes:
      - ./api:/app
      - backend_uploads:/app/uploads
    depends_on:
      - postgres
      - redis
      - qdrant
    restart: unless-stopped

  # Celery Beat (Scheduler)
  celery-beat:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: clouisle-celery-beat
    command: celery -A app.core.celery beat --loglevel=info
    environment:
      - DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
      - REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
    volumes:
      - ./api:/app
    depends_on:
      - postgres
      - redis
    restart: unless-stopped

  # Frontend
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
      args:
        - NEXT_PUBLIC_API_URL=${SITE_URL}/api
    container_name: clouisle-frontend
    environment:
      - NEXT_PUBLIC_API_URL=${SITE_URL}/api
    ports:
      - "3000:3000"
    depends_on:
      - backend
    restart: unless-stopped

  # Nginx Reverse Proxy
  nginx:
    image: nginx:alpine
    container_name: clouisle-nginx
    volumes:
      - ./deploy/nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./deploy/nginx/ssl:/etc/nginx/ssl:ro
    ports:
      - "80:80"
      - "443:443"
    depends_on:
      - backend
      - frontend
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
  qdrant_data:
  backend_uploads:
```

### Development Configuration

**docker-compose.dev.yml:**

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: clouisle_dev
      POSTGRES_USER: clouisle
      POSTGRES_PASSWORD: dev_password
    ports:
      - "5432:5432"
    volumes:
      - postgres_dev_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_dev_data:/data

  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
    volumes:
      - qdrant_dev_data:/qdrant/storage

volumes:
  postgres_dev_data:
  redis_dev_data:
  qdrant_dev_data:
```

**Start development services:**

```bash
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

**Stop and remove volumes:**

```bash
docker compose down -v
```

**Stop specific service:**

```bash
docker compose stop api
```

### Restarting Services

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
```

**View last 100 lines:**

```bash
docker compose logs --tail=100 api
```

## Updating Deployment

### Update Application

**Pull latest changes:**

```bash
git pull origin main
```

**Rebuild and restart:**

```bash
docker compose build
docker compose up -d
```

**Run migrations:**

```bash
docker compose exec api alembic upgrade head
```

### Update Docker Images

**Pull latest images:**

```bash
docker compose pull
```

**Restart services:**

```bash
docker compose up -d
```

## Backup and Restore

### Database Backup

**Create backup:**

```bash
docker compose exec postgres pg_dump -U clouisle clouisle > backup_$(date +%Y%m%d_%H%M%S).sql
```

**Automated backup script:**

```bash
#!/bin/bash
# backup.sh

BACKUP_DIR="/backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/clouisle_$DATE.sql"

# Create backup
docker compose exec -T postgres pg_dump -U clouisle clouisle > "$BACKUP_FILE"

# Compress backup
gzip "$BACKUP_FILE"

# Keep only last 7 days
find "$BACKUP_DIR" -name "clouisle_*.sql.gz" -mtime +7 -delete

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
docker compose up -d postgres

# Wait for database to be ready
sleep 10

# Restore backup
gunzip -c backup_20260211_020000.sql.gz | \
  docker compose exec -T postgres psql -U clouisle clouisle

# Start all services
docker compose up -d
```

### Volume Backup

**Backup volumes:**

```bash
# Backup postgres data
docker run --rm \
  -v clouisle_postgres_data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/postgres_data.tar.gz /data

# Backup uploads
docker run --rm \
  -v clouisle_backend_uploads:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/uploads.tar.gz /data
```

**Restore volumes:**

```bash
# Restore postgres data
docker run --rm \
  -v clouisle_postgres_data:/data \
  -v $(pwd):/backup \
  alpine tar xzf /backup/postgres_data.tar.gz -C /

# Restore uploads
docker run --rm \
  -v clouisle_backend_uploads:/data \
  -v $(pwd):/backup \
  alpine tar xzf /backup/uploads.tar.gz -C /
```

## Monitoring

### Health Checks

**Check service health:**

```bash
docker compose ps
```

**Check backend health:**

```bash
curl http://localhost:8000/health
```

**Expected response:**
```json
{
  "status": "healthy",
  "database": "connected",
  "redis": "connected",
  "qdrant": "connected"
}
```

### Resource Usage

**View resource usage:**

```bash
docker stats
```

**View specific service:**

```bash
docker stats clouisle-backend
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
docker compose build --no-cache
docker compose up -d
```

### Database Connection Issues

**Problem**: Cannot connect to database

**Solutions:**

1. **Check database is running:**
```bash
docker compose ps postgres
```

2. **Check database logs:**
```bash
docker compose logs postgres
```

3. **Test connection:**
```bash
docker compose exec postgres psql -U clouisle -d clouisle -c "SELECT 1"
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

2. **Increase Docker memory limit:**
```bash
# Edit Docker Desktop settings
# Or edit /etc/docker/daemon.json
{
  "default-ulimits": {
    "memlock": {
      "Hard": -1,
      "Name": "memlock",
      "Soft": -1
    }
  }
}
```

3. **Restart Docker:**
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
docker volume inspect clouisle_postgres_data
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
- Expose unnecessary ports
- Run as root
- Commit secrets to git
- Skip security updates

### Performance

**✅ Do:**
- Use volume mounts for data
- Enable health checks
- Monitor resource usage
- Use multi-stage builds
- Optimize images
- Use caching

**❌ Don't:**
- Use bind mounts for data
- Skip health checks
- Ignore resource limits
- Use large base images
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
- Forget to migrate
- Delete old backups immediately

## Related Documentation

- [Environment Variables](./environment-variables.md) - Configuration reference
- [Kubernetes Deployment](./kubernetes.md) - K8s deployment
- [Troubleshooting](./troubleshooting.md) - Common issues
- [Security Best Practices](../best-practices/security.md) - Security guide

---

**Last Updated**: 2026-02-11
