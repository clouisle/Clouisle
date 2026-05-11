# Deployment Guide

This guide covers deploying Clouisle in production using **Docker Compose** or **Kubernetes**.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Prerequisites](#prerequisites)
- [Building Images](#building-images)
- [Docker Compose Deployment](#docker-compose-deployment)
  - [Quick Start](#quick-start)
  - [Configuration](#configuration)
  - [Volume Mounts](#volume-mounts)
  - [Port Mapping](#port-mapping)
  - [Custom Domain & HTTPS](#custom-domain--https)
  - [Scaling](#scaling)
  - [Operations](#operations)
- [Kubernetes Deployment](#kubernetes-deployment)
  - [Quick Start (K8s)](#quick-start-k8s)
  - [Manifest Structure](#manifest-structure)
  - [Secrets Configuration](#secrets-configuration)
  - [Persistent Storage](#persistent-storage)
  - [Ingress & TLS](#ingress--tls)
  - [Scaling (K8s)](#scaling-k8s)
  - [Operations (K8s)](#operations-k8s)
- [Environment Variables Reference](#environment-variables-reference)
- [Request Flow & Proxy Architecture](#request-flow--proxy-architecture)
- [Backup & Restore](#backup--restore)
- [Upgrading](#upgrading)
- [Security Checklist](#security-checklist)
- [Troubleshooting](#troubleshooting)

---

## Architecture Overview

Clouisle uses **2 Docker images** running as **4 application services** + **3 infrastructure services**:

```
                         ┌─────────────────────────────────────────────┐
                         │              Frontend Container             │
  Browser ──────────────►│  Nginx (:3000)                              │
                         │    ├── /api/*  ──► proxy to api:8000    │
                         │    ├── /_next/static/* ──► local files      │
                         │    └── /*  ──► Node.js SSR (:3001 internal) │
                         └──────────────────┬──────────────────────────┘
                                            │
                         ┌──────────────────▼──────────────────────────┐
                         │             Backend Container               │
                         │  Gunicorn + UvicornWorker (:8000)           │
                         │    └── FastAPI application                  │
                         └──────┬──────────┬───────────────────────────┘
                                │          │
              ┌─────────────────┤          ├─────────────────┐
              ▼                 ▼          ▼                 ▼
         PostgreSQL          Redis      Qdrant         Celery Worker
           (:5432)          (:6379)    (:6333)         (background)
                                                       Celery Beat
                                                       (scheduler)
```

| Image | Services | Description |
|-------|----------|-------------|
| `clouisle-backend` | api, worker, beat | Python 3.13 — API server, Celery worker, Celery beat |
| `clouisle-sandbox-worker` | sandbox-worker | Sandbox task execution and artifact upload |
| `clouisle-frontend` | frontend | Next.js standalone (SSR) |

The backend image is shared across three services, and sandbox execution uses a separate image. Services are differentiated by startup command:

| Service | Command | Replicas |
|---------|---------|----------|
| api | `python main.py server -H 0.0.0.0 -w 4 --no-reload` | 1+ |
| worker | `python main.py worker -c 4 -Q default,workflow` | 1+ |
| sandbox-worker | `python main.py sandbox-worker -c ${SANDBOX_WORKER_CONCURRENCY:-1}` | 1+ |
| beat | `python main.py beat` | **Exactly 1** |

> **Important**: The beat service must always run exactly 1 replica. Running multiple beat instances will cause duplicate scheduled tasks.

---

## Prerequisites

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| Docker | 24.0+ | Latest |
| Docker Compose | v2.20+ | Latest |
| Kubernetes (if using K8s) | 1.25+ | 1.28+ |
| RAM | 4 GB | 8 GB+ |
| Disk | 20 GB | 50 GB+ |
| CPU | 2 cores | 4 cores+ |

---

## Building Images

All commands run from the **project root** directory:

```bash
# Backend image (shared by api, worker, beat services)
docker build -f deploy/dockerfiles/backend.Dockerfile -t clouisle-backend:latest .

# Sandbox worker image
docker build -f deploy/dockerfiles/sandbox-worker.Dockerfile -t clouisle-sandbox-worker:latest .

# Frontend image (Next.js standalone)
docker build -f deploy/dockerfiles/frontend.Dockerfile -t clouisle-frontend:latest .
```

For a private registry:

```bash
docker tag clouisle-backend:latest registry.example.com/clouisle/clouisle-backend:latest
docker tag clouisle-sandbox-worker:latest registry.example.com/clouisle/clouisle-sandbox-worker:latest
docker tag clouisle-frontend:latest registry.example.com/clouisle/clouisle-frontend:latest
docker push registry.example.com/clouisle/clouisle-backend:latest
docker push registry.example.com/clouisle/clouisle-sandbox-worker:latest
docker push registry.example.com/clouisle/clouisle-frontend:latest
```

---

## Kubernetes Helm Deployment

Helm is the recommended Kubernetes deployment method:

```bash
helm lint deploy/helm/clouisle
helm upgrade --install clouisle deploy/helm/clouisle \
  --namespace clouisle \
  --create-namespace
```

For production, create `clouisle-secret` and use production values:

```bash
helm upgrade --install clouisle deploy/helm/clouisle \
  --namespace clouisle \
  --create-namespace \
  -f deploy/helm/clouisle/values-production.yaml
```

The plain manifest remains available at `deploy/k8s/clouisle.yaml` for fallback or debugging.

## Docker Compose Deployment

### Quick Start

```bash
cd deploy

# 1. Create and edit environment file
cp .env.example .env

# 2. Generate secure passwords (run each command, paste results into .env)
openssl rand -base64 32    # → SECRET_KEY
openssl rand -base64 16    # → POSTGRES_PASSWORD
openssl rand -base64 16    # → REDIS_PASSWORD
openssl rand -base64 16    # → QDRANT_API_KEY

# 3. Build images and start all services
docker compose up -d --build

# 4. Verify all services are healthy
docker compose ps
```

### Configuration

Edit `deploy/.env` before starting. The following variables **must** be changed:

| Variable | Why | Example |
|----------|-----|---------|
| `SECRET_KEY` | JWT signing — default is insecure | `openssl rand -base64 32` |
| `POSTGRES_PASSWORD` | Database access | `openssl rand -base64 16` |
| `REDIS_PASSWORD` | Cache/queue access | `openssl rand -base64 16` |
| `QDRANT_API_KEY` | Vector DB access | `openssl rand -base64 16` |

The following should be changed for production domains:

| Variable | Default | Production Example |
|----------|---------|-------------------|
| `API_BASE_URL` | `http://localhost:8000` | `https://api.example.com` |
| `FRONTEND_URL` | `http://localhost:3000` | `https://example.com` |
| `BACKEND_CORS_ORIGINS` | `http://localhost:3000` | `https://example.com` |

> **Note**: `POSTGRES_SERVER`, `REDIS_HOST`, `QDRANT_URL` are overridden in `docker-compose.yml` via the `environment` section (set to Docker service names `db`, `redis`, `qdrant`). You do not need to change them in `.env`.

### Volume Mounts

Docker Compose uses named volumes for data persistence:

| Volume | Container Path | Purpose | Data Loss Impact |
|--------|---------------|---------|-----------------|
| `postgres_data` | `/var/lib/postgresql/data` | Database files | **All data lost** |
| `redis_data` | `/data` | Cache & Celery broker state | Task queue lost, recoverable |
| `qdrant_data` | `/qdrant/storage` | Vector embeddings | Must re-index knowledge base |
| `uploads_data` | `/app/uploads` | User-uploaded files | Uploaded documents lost |

To use host-path mounts instead of named volumes (for easier backup):

```yaml
# In docker-compose.yml, replace:
volumes:
  postgres_data:

# With:
volumes:
  postgres_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /data/clouisle/postgres
```

Or directly in the service definition:

```yaml
volumes:
  - /data/clouisle/postgres:/var/lib/postgresql/data
  - /data/clouisle/uploads:/app/uploads
```

> **Important**: The `uploads_data` volume is shared between `backend` and `worker` services. Both need read/write access to process uploaded documents. If using host-path mounts, ensure the directory exists and has correct permissions before starting.

### Port Mapping

Default exposed ports:

| Service | Host Port | Container Port | Purpose |
|---------|-----------|---------------|---------|
| frontend | 3000 | 3000 | Web UI (Nginx) |
| backend | 8000 | 8000 | API (Gunicorn) |
| db | 5432 | 5432 | PostgreSQL |
| redis | 6379 | 6379 | Redis |
| qdrant | 6333 | 6333 | Qdrant |

**For production**, you should only expose the frontend port and place it behind a reverse proxy. Remove or comment out the infrastructure ports:

```yaml
# In docker-compose.yml, remove these lines for production:
  db:
    ports:
      - "5432:5432"    # Remove — no external DB access needed
  redis:
    ports:
      - "6379:6379"    # Remove
  qdrant:
    ports:
      - "6333:6333"    # Remove
  api:
    ports:
      - "8000:8000"    # Remove — frontend Nginx proxies API requests
```

### Custom Domain & HTTPS

For production with a custom domain, place an external reverse proxy (e.g., Nginx, Caddy, Traefik) in front of the frontend container:

**Option A: Caddy (automatic HTTPS)**

```
# Caddyfile
example.com {
    reverse_proxy localhost:3000
}
```

**Option B: External Nginx**

```nginx
server {
    listen 443 ssl http2;
    server_name example.com;

    ssl_certificate     /etc/ssl/certs/example.com.pem;
    ssl_certificate_key /etc/ssl/private/example.com.key;

    client_max_body_size 100m;

    location / {
        proxy_pass http://127.0.0.1:3000;

        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket
        proxy_http_version 1.1;
        proxy_set_header Upgrade    $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Streaming
        proxy_buffering off;
        proxy_read_timeout 300s;
    }
}
```

When using HTTPS, update these environment variables:

```bash
API_BASE_URL=https://example.com
FRONTEND_URL=https://example.com
BACKEND_CORS_ORIGINS=https://example.com
```

### Scaling

```bash
# Scale Celery workers (safe to run multiple)
docker compose up -d --scale worker=4

# Scale backend API (safe to run multiple behind Nginx)
docker compose up -d --scale api=2

# NEVER scale beat beyond 1
# docker compose up -d --scale beat=2  ← DO NOT DO THIS
```

When scaling backend to multiple replicas, remove the host port mapping to avoid conflicts:

```yaml
api:
    # Remove: ports: ["8000:8000"]
    expose:
      - "8000"
```

### Operations

```bash
# View logs (follow mode)
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f frontend

# View logs for a specific time range
docker compose logs --since 1h api

# Restart a single service (zero-downtime for stateless services)
docker compose restart api

# Stop all services
docker compose down

# Stop and destroy all data (CAUTION)
docker compose down -v

# Update images and restart
docker compose pull
docker compose up -d --build
```

---

## Kubernetes Deployment

### Quick Start (K8s)

All resources are defined in a single file: `deploy/k8s/clouisle.yaml`.

```bash
# 1. Edit the manifest — replace secret placeholders and set your domain
vi deploy/k8s/clouisle.yaml

# 2. Apply everything
kubectl apply -f deploy/k8s/clouisle.yaml

# 3. Wait for infrastructure
kubectl -n clouisle wait --for=condition=ready pod -l app=postgres --timeout=120s
kubectl -n clouisle wait --for=condition=ready pod -l app=redis --timeout=120s
kubectl -n clouisle wait --for=condition=ready pod -l app=qdrant --timeout=120s

# 4. Verify all pods
kubectl -n clouisle get pods
```

### Manifest Structure

The manifest contains 11 resource groups, using YAML anchors to deduplicate repeated values:

| # | Resource | Kind | Notes |
|---|----------|------|-------|
| 1 | Namespace | Namespace | `clouisle` |
| 2 | ConfigMap | ConfigMap | Non-sensitive configuration |
| 3 | Secret | Secret | Passwords and keys (**must edit**) |
| 4 | PostgreSQL | StatefulSet + Service + PVC | Headless Service, 10Gi storage |
| 5 | Redis | Deployment + Service | |
| 6 | Qdrant | StatefulSet + Service + PVC | Headless Service, 10Gi storage |
| 7 | Backend | Deployment + Service | 2 replicas, port 8000 |
| 8 | Worker | Deployment | 2 replicas, no Service |
| 9 | Beat | Deployment | 1 replica, `Recreate` strategy |
| 10 | Frontend | Deployment + Service | 2 replicas, port 3000 |
| 11 | Ingress | Ingress | `/api` → backend, `/` → frontend |

### Secrets Configuration

Before applying, replace the base64 placeholder values in the Secret section:

```bash
# Generate base64-encoded values
echo -n 'your-strong-secret-key' | base64
echo -n 'your-postgres-password' | base64
echo -n 'your-redis-password' | base64
echo -n 'your-qdrant-api-key' | base64
```

Replace in `clouisle.yaml`:

```yaml
data:
  SECRET_KEY: <paste-base64-here>
  POSTGRES_PASSWORD: <paste-base64-here>
  REDIS_PASSWORD: <paste-base64-here>
  QDRANT_API_KEY: <paste-base64-here>
```

> **Tip**: For production, consider using an external secret manager (Vault, AWS Secrets Manager, etc.) with the External Secrets Operator instead of storing secrets in YAML.

### Persistent Storage

| PVC | Size | Used By | StorageClass |
|-----|------|---------|-------------|
| `postgres-data` | 10Gi | PostgreSQL | default |
| `qdrant-data` | 10Gi | Qdrant | default |

To change the storage size or class, edit the PVC definitions:

```yaml
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: your-storage-class    # Add this line
  resources:
    requests:
      storage: 50Gi                       # Adjust size
```

The `uploads` volume for backend and worker uses `emptyDir` by default. For production, replace it with a PVC or a shared filesystem (e.g., NFS, EFS) so that uploaded files persist across pod restarts and are accessible by both backend and worker pods:

```yaml
# Replace in the anchors section:
- &uploads-volume
  name: uploads
  persistentVolumeClaim:
    claimName: clouisle-uploads

# Add a new PVC:
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: clouisle-uploads
  namespace: clouisle
spec:
  accessModes: [ReadWriteMany]    # Must be RWX for multi-pod access
  resources:
    requests:
      storage: 20Gi
```

> **Important**: `ReadWriteMany` requires a storage class that supports it (NFS, CephFS, EFS, etc.). Standard block storage (gp2, gp3) only supports `ReadWriteOnce`.

### Ingress & TLS

Edit the Ingress section to set your domain:

```yaml
spec:
  ingressClassName: nginx
  rules:
    - host: your-domain.com        # ← Change this
```

To enable TLS:

```yaml
spec:
  ingressClassName: nginx
  tls:
    - hosts:
        - your-domain.com
      secretName: clouisle-tls      # cert-manager or manual TLS secret
  rules:
    - host: your-domain.com
```

With cert-manager (automatic Let's Encrypt):

```yaml
metadata:
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
```

Also update the ConfigMap:

```yaml
data:
  API_BASE_URL: "https://your-domain.com"
  FRONTEND_URL: "https://your-domain.com"
  BACKEND_CORS_ORIGINS: "https://your-domain.com"
```

### Scaling (K8s)

```bash
# Scale workers
kubectl -n clouisle scale deployment worker --replicas=4

# Scale backend
kubectl -n clouisle scale deployment api --replicas=3

# Scale frontend
kubectl -n clouisle scale deployment frontend --replicas=3

# NEVER scale beat beyond 1
```

For auto-scaling:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api-hpa
  namespace: clouisle
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
```

### Operations (K8s)

```bash
# View pod status
kubectl -n clouisle get pods -o wide

# View logs
kubectl -n clouisle logs -f deployment/api
kubectl -n clouisle logs -f deployment/worker
kubectl -n clouisle logs -f deployment/beat
kubectl -n clouisle logs -f deployment/frontend

# View logs for a specific pod
kubectl -n clouisle logs -f <pod-name>

# Restart a deployment (rolling restart)
kubectl -n clouisle rollout restart deployment api

# Check rollout status
kubectl -n clouisle rollout status deployment api

# Execute a command in a pod
kubectl -n clouisle exec -it deployment/api -- bash

# View resource usage
kubectl -n clouisle top pods
```

---

## Environment Variables Reference

### Required (Must Change)

| Variable | Description | How to Generate |
|----------|-------------|----------------|
| `SECRET_KEY` | JWT token signing key. Changing this invalidates all existing sessions. | `openssl rand -base64 32` |
| `POSTGRES_PASSWORD` | PostgreSQL password | `openssl rand -base64 16` |

### Recommended (Should Change for Production)

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_PASSWORD` | *(empty)* | Redis password. Empty means no authentication. |
| `QDRANT_API_KEY` | *(empty)* | Qdrant API key. Empty means no authentication. |
| `API_BASE_URL` | `http://localhost:8000` | Backend URL used internally for file access and SSO callbacks. Set to your actual domain in production. |
| `FRONTEND_URL` | `http://localhost:3000` | Frontend URL used for SSO redirect URIs. Set to your actual domain in production. |
| `BACKEND_CORS_ORIGINS` | `http://localhost:3000` | Comma-separated list of allowed CORS origins. Must include your frontend domain. |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `PROJECT_NAME` | `Clouisle` | Display name |
| `TIMEZONE` | `Asia/Shanghai` | Server timezone (affects scheduled tasks) |
| `POSTGRES_SERVER` | `localhost` | PostgreSQL host. Overridden to `db` (Compose) or `postgres` (K8s) in deployment configs. |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `POSTGRES_USER` | `postgres` | PostgreSQL user |
| `POSTGRES_DB` | `clouisle` | PostgreSQL database name |
| `DATABASE_URL` | *(auto-assembled)* | Full PostgreSQL DSN. If set, overrides individual `POSTGRES_*` variables. |
| `REDIS_HOST` | `localhost` | Redis host. Overridden to `redis` in deployment configs. |
| `REDIS_PORT` | `6379` | Redis port |
| `VECTOR_BACKEND` | `qdrant` | Vector database backend |
| `QDRANT_URL` | `http://localhost:6333` | Qdrant URL. Overridden to `http://qdrant:6333` in deployment configs. |
| `QDRANT_COLLECTION_PREFIX` | `kb_dim` | Qdrant collection name prefix |
| `QDRANT_DISTANCE` | `Cosine` | Vector distance metric |
| `TAVILY_API_KEY` | *(empty)* | Tavily web search API key (for agent web search capability) |

---

## Request Flow & Proxy Architecture

Understanding the request flow is important for debugging and configuring external reverse proxies.

### Client-Side API Requests

```
Browser
  │
  ├── Page requests (HTML/SSR) ──► Nginx (:3000) ──► Node.js (:3001 internal)
  │
  └── API requests (/api/*) ──► Nginx (:3000) ──► Backend Gunicorn (:8000)
```

The frontend container runs two processes:
1. **Nginx** on port 3000 (external) — handles routing, static files, and proxying
2. **Node.js** on port 3001 (internal) — handles server-side rendering

### Header Forwarding

Nginx forwards the following headers to the backend on `/api/*` requests:

| Header | Value | Purpose |
|--------|-------|---------|
| `Host` | Original host | Virtual host routing |
| `X-Real-IP` | Client IP | Real client IP address |
| `X-Forwarded-For` | Client IP chain | Proxy chain |
| `X-Forwarded-Proto` | `http` or `https` | Original protocol |
| `X-Forwarded-Host` | Original host | Original hostname |
| `X-Forwarded-Port` | Original port | Original port |
| `Accept-Language` | Browser language | i18n (backend fallback) |
| `X-Language` | App locale | i18n (set by frontend, takes priority) |

Gunicorn is configured with `--forwarded-allow-ips *` to trust these proxy headers.

### If Using an External Reverse Proxy

When placing an additional reverse proxy (Nginx, Caddy, Traefik, cloud LB) in front of the frontend container, ensure it forwards:

```
External Proxy → Frontend Nginx (:3000) → Backend Gunicorn (:8000)
```

The external proxy must set `X-Real-IP` and `X-Forwarded-For` correctly. The frontend Nginx will pass them through to the backend.

---

## Backup & Restore

### PostgreSQL

```bash
# Docker Compose — backup
docker compose exec db pg_dump -U postgres clouisle > backup_$(date +%Y%m%d).sql

# Docker Compose — restore
docker compose exec -T db psql -U postgres clouisle < backup_20260206.sql

# Kubernetes — backup
kubectl -n clouisle exec statefulset/postgres -- pg_dump -U postgres clouisle > backup.sql

# Kubernetes — restore
kubectl -n clouisle exec -i statefulset/postgres -- psql -U postgres clouisle < backup.sql
```

### Qdrant

```bash
# Docker Compose — backup the volume
docker run --rm -v deploy_qdrant_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/qdrant_backup.tar.gz -C /data .

# Kubernetes — use Qdrant's snapshot API
kubectl -n clouisle exec statefulset/qdrant -- \
  wget -qO- -post-data '{}' http://localhost:6333/snapshots
```

### Uploaded Files

```bash
# Docker Compose
docker run --rm -v deploy_uploads_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/uploads_backup.tar.gz -C /data .

# Kubernetes (if using PVC)
kubectl -n clouisle exec deployment/api -- tar czf - /app/uploads > uploads_backup.tar.gz
```

### Automated Backup Schedule

For production, set up a CronJob (K8s) or cron task (Docker host) to run daily backups:

```yaml
# K8s CronJob example
apiVersion: batch/v1
kind: CronJob
metadata:
  name: postgres-backup
  namespace: clouisle
spec:
  schedule: "0 2 * * *"    # Daily at 2:00 AM
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: backup
              image: postgres:16
              command:
                - sh
                - -c
                - pg_dump -h postgres -U postgres clouisle | gzip > /backup/clouisle_$(date +%Y%m%d).sql.gz
              env:
                - name: PGPASSWORD
                  valueFrom:
                    secretKeyRef:
                      name: clouisle-secret
                      key: POSTGRES_PASSWORD
              volumeMounts:
                - name: backup
                  mountPath: /backup
          restartPolicy: OnFailure
          volumes:
            - name: backup
              persistentVolumeClaim:
                claimName: backup-pvc
```

---

## Upgrading

### Docker Compose

```bash
cd deploy

# 1. Pull latest code
git pull

# 2. Rebuild images
docker compose build

# 3. Rolling restart (services restart one by one)
docker compose up -d

# 4. Verify
docker compose ps
docker compose logs --tail=50 backend
```

### Kubernetes

```bash
# 1. Build and push new images
docker build -f deploy/dockerfiles/backend.Dockerfile -t registry.example.com/clouisle/api:v2.0.0 .
docker build -f deploy/dockerfiles/frontend.Dockerfile -t registry.example.com/clouisle/frontend:v2.0.0 .
docker push registry.example.com/clouisle/api:v2.0.0
docker push registry.example.com/clouisle/frontend:v2.0.0

# 2. Update image tags in clouisle.yaml (the anchors at the top)
#    - &backend-image registry.example.com/clouisle/api:v2.0.0
#    - &frontend-image registry.example.com/clouisle/frontend:v2.0.0

# 3. Apply
kubectl apply -f deploy/k8s/clouisle.yaml

# 4. Monitor rollout
kubectl -n clouisle rollout status deployment api
kubectl -n clouisle rollout status deployment worker
kubectl -n clouisle rollout status deployment frontend
```

> **Note**: Database migrations (if any) should be run before updating the backend deployment. Check the release notes for migration instructions.

---

## Security Checklist

- [ ] **Change all default passwords** — `SECRET_KEY`, `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `QDRANT_API_KEY`
- [ ] **Enable HTTPS** — Use TLS termination at the external reverse proxy or K8s Ingress
- [ ] **Restrict exposed ports** — In production, only expose port 3000 (or 443 via reverse proxy). Remove database/Redis/Qdrant port mappings.
- [ ] **Set CORS origins** — `BACKEND_CORS_ORIGINS` should only contain your actual frontend domain, not `*`
- [ ] **Update `API_BASE_URL` and `FRONTEND_URL`** — Must match your actual production domain for SSO and internal file access to work correctly
- [ ] **Network isolation** — In Docker Compose, infrastructure services (db, redis, qdrant) should not be accessible from outside. In K8s, they use ClusterIP services (no external access by default).
- [ ] **Regular backups** — Set up automated PostgreSQL and Qdrant backups
- [ ] **Resource limits** — Review and adjust CPU/memory limits in K8s manifests based on actual usage
- [ ] **Image scanning** — Scan Docker images for vulnerabilities before deploying

---

## Troubleshooting

### Backend cannot connect to database

```bash
# Docker Compose
docker compose logs db          # Check PostgreSQL logs
docker compose exec db pg_isready -U postgres

# Kubernetes
kubectl -n clouisle logs statefulset/postgres
kubectl -n clouisle exec statefulset/postgres -- pg_isready -U postgres
```

Common causes:
- `POSTGRES_PASSWORD` mismatch between the database and the backend
- Database not yet ready when backend starts (healthcheck should prevent this)
- Wrong `POSTGRES_SERVER` value (should be `db` in Compose, `postgres` in K8s)

### Frontend returns 502 for API requests

The frontend Nginx proxies `/api/*` to `http://api:8000`. A 502 means the backend is unreachable.

```bash
# Check if backend is running
docker compose ps api
# or
kubectl -n clouisle get pods -l app=api

# Test connectivity from frontend container
docker compose exec frontend wget -qO- http://api:8000/api/v1/health
```

### Worker not processing tasks

```bash
# Check worker logs
docker compose logs worker
# or
kubectl -n clouisle logs deployment/worker

# Verify Redis connectivity
docker compose exec worker python -c "import redis; r = redis.Redis(host='redis'); print(r.ping())"
```

Common causes:
- `REDIS_PASSWORD` mismatch
- Redis not yet ready
- Wrong queue names

### Beat running duplicate scheduled tasks

Ensure only 1 beat instance is running:

```bash
# Docker Compose
docker compose ps beat    # Should show exactly 1 replica

# Kubernetes
kubectl -n clouisle get pods -l app=beat    # Should show exactly 1 pod
```

The K8s beat Deployment uses `strategy: Recreate` to ensure the old pod is fully terminated before a new one starts.

### Uploaded files not accessible

The `uploads` volume must be shared between `backend` and `worker` services:

```bash
# Docker Compose — verify both mount the same volume
docker compose exec api ls -la /app/uploads
docker compose exec worker ls -la /app/uploads
```

In Kubernetes, if using `emptyDir`, files are lost on pod restart. Switch to a PVC with `ReadWriteMany` access mode (see [Persistent Storage](#persistent-storage)).

### Out of memory / OOM killed

Check resource usage and adjust limits:

```bash
# Docker
docker stats

# Kubernetes
kubectl -n clouisle top pods
kubectl -n clouisle describe pod <pod-name>    # Check "Last State" for OOMKilled
```

Adjust resource limits in `docker-compose.yml` (add `deploy.resources`) or in `clouisle.yaml` (edit the `resources` section).

### LLM requests timing out

The default proxy timeout is 300 seconds (5 minutes). For very long LLM operations:

- Frontend Nginx: edit `proxy_read_timeout` in `deploy/nginx/default.conf`
- K8s Ingress: edit `nginx.ingress.kubernetes.io/proxy-read-timeout` annotation
- Gunicorn: edit `--timeout` in the backend Dockerfile CMD
