# Clouisle Deployment Guide

## Architecture

Clouisle uses **2 Docker images** that run as **4 application services**:

| Image | Service(s) | Description |
|-------|-----------|-------------|
| `clouisle-backend` | backend, worker, beat | Python 3.13 — FastAPI API server, Celery worker, Celery beat scheduler |
| `clouisle-frontend` | frontend | Next.js app served via Nginx (static assets + API reverse proxy) |

Infrastructure dependencies: **PostgreSQL 16**, **Redis 7**, **Qdrant**.

### Frontend Nginx Architecture

The frontend container runs Nginx on port 3000 with the Next.js standalone server on an internal port (3001). Nginx handles:

- **Static assets** (`/_next/static/`, `/public/`) — served directly with long cache headers
- **API requests** (`/api/*`) — proxied to the backend with full client IP forwarding (`X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`, etc.)
- **All other requests** — proxied to the internal Next.js server for SSR

This ensures the backend receives real client IP addresses and other request metadata.

---

## Building Images

From the **project root**:

```bash
# Backend image (used for backend, worker, and beat)
docker build -f deploy/dockerfiles/backend.Dockerfile -t clouisle-backend .

# Frontend image
docker build -f deploy/dockerfiles/frontend.Dockerfile -t clouisle-frontend .
```

---

## Docker Compose Deployment

### Quick Start

```bash
cd deploy

# 1. Create environment file
cp .env.example .env
# Edit .env — set strong passwords for POSTGRES_PASSWORD, REDIS_PASSWORD, QDRANT_API_KEY, SECRET_KEY

# 2. Build and start
docker compose up -d --build
```

### Services

| Service | Port | Description |
|---------|------|-------------|
| `frontend` | 3000 | Next.js + Nginx |
| `backend` | 8000 | FastAPI API server |
| `worker` | — | Celery worker (no exposed port) |
| `beat` | — | Celery beat scheduler (no exposed port) |
| `db` | 5432 | PostgreSQL 16 |
| `redis` | 6379 | Redis 7 |
| `qdrant` | 6333 | Qdrant vector database |

### Volumes

| Volume | Purpose |
|--------|---------|
| `postgres_data` | PostgreSQL data |
| `redis_data` | Redis persistence |
| `qdrant_data` | Qdrant vector storage |
| `uploads_data` | User-uploaded files |

### Common Operations

```bash
# View logs
docker compose logs -f backend
docker compose logs -f worker

# Restart a single service
docker compose restart backend

# Scale workers
docker compose up -d --scale worker=4

# Stop everything
docker compose down

# Stop and remove volumes (DESTROYS DATA)
docker compose down -v
```

---

## Kubernetes Deployment

### Prerequisites

- Kubernetes cluster (1.25+)
- `kubectl` configured
- Ingress controller (e.g., ingress-nginx) installed
- Container images pushed to a registry accessible by the cluster

### Deploy

All K8s resources are in a single file `deploy/k8s/clouisle.yaml`, using YAML anchors to deduplicate repeated values (image names, envFrom, resource limits, probe timings, etc.).

```bash
# 1. Edit the manifest — replace base64 secret placeholders and set your domain
#    Generate base64: echo -n 'your-value' | base64
vi deploy/k8s/clouisle.yaml

# 2. Apply everything at once
kubectl apply -f deploy/k8s/clouisle.yaml

# 3. Wait for infrastructure to be ready
kubectl -n clouisle wait --for=condition=ready pod -l app=postgres --timeout=120s
kubectl -n clouisle wait --for=condition=ready pod -l app=redis --timeout=120s
kubectl -n clouisle wait --for=condition=ready pod -l app=qdrant --timeout=120s

# Application pods will start automatically once infrastructure is healthy
```

### Manifest Sections (clouisle.yaml)

| # | Resource | Notes |
|---|----------|-------|
| 1 | Namespace | `clouisle` |
| 2 | ConfigMap | Non-sensitive configuration |
| 3 | Secret | Passwords and keys (replace base64 placeholders) |
| 4 | PostgreSQL | StatefulSet + Headless Service + PVC (10Gi) |
| 5 | Redis | Deployment + Service |
| 6 | Qdrant | StatefulSet + Headless Service + PVC (10Gi) |
| 7 | Backend | Deployment (2 replicas) + Service :8000 |
| 8 | Worker | Deployment (2 replicas), no Service |
| 9 | Beat | Deployment (1 replica, Recreate), no Service |
| 10 | Frontend | Deployment (2 replicas) + Service :3000 |
| 11 | Ingress | `/api` → backend, `/` → frontend |

### YAML Anchors

Repeated values are extracted as anchors at the top of the file under `x-definitions`:

| Anchor | Usage |
|--------|-------|
| `*ns` | Namespace `clouisle` — used in every `metadata.namespace` |
| `*backend-image` | `clouisle-backend:latest` — shared by backend, worker, beat |
| `*frontend-image` | `clouisle-frontend:latest` |
| `*pull-policy` | `IfNotPresent` |
| `*env-from` | ConfigMap + Secret envFrom — shared by backend, worker, beat |
| `*uploads-volume` / `*uploads-mount` | Shared uploads emptyDir volume |
| `*backend-resources` | CPU/memory limits for backend, worker |
| `*probe-readiness-fast` / `*probe-liveness-slow` | Probe timing presets |

### Scaling

```bash
# Scale workers
kubectl -n clouisle scale deployment worker --replicas=4

# Scale backend
kubectl -n clouisle scale deployment backend --replicas=3

# IMPORTANT: beat must always be exactly 1 replica
```

### Logs

```bash
kubectl -n clouisle logs -f deployment/backend
kubectl -n clouisle logs -f deployment/worker
kubectl -n clouisle logs -f deployment/beat
kubectl -n clouisle logs -f deployment/frontend
```

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `PROJECT_NAME` | No | `Clouisle` | Project display name |
| `SECRET_KEY` | **Yes** | — | JWT signing key |
| `TIMEZONE` | No | `Asia/Shanghai` | Server timezone |
| `API_BASE_URL` | No | `http://localhost:8000` | Backend URL (for internal file access) |
| `FRONTEND_URL` | No | `http://localhost:3000` | Frontend URL (for SSO redirects) |
| `POSTGRES_SERVER` | No | `localhost` | PostgreSQL host |
| `POSTGRES_PORT` | No | `5432` | PostgreSQL port |
| `POSTGRES_USER` | No | `postgres` | PostgreSQL user |
| `POSTGRES_PASSWORD` | **Yes** | — | PostgreSQL password |
| `POSTGRES_DB` | No | `clouisle` | PostgreSQL database |
| `REDIS_HOST` | No | `localhost` | Redis host |
| `REDIS_PORT` | No | `6379` | Redis port |
| `REDIS_PASSWORD` | No | — | Redis password |
| `QDRANT_URL` | No | `http://localhost:6333` | Qdrant URL |
| `QDRANT_API_KEY` | No | — | Qdrant API key |
| `BACKEND_CORS_ORIGINS` | No | `http://localhost:3000` | Allowed CORS origins |
| `TAVILY_API_KEY` | No | — | Tavily search API key |

---

## Troubleshooting

**Backend can't connect to database**
- Ensure PostgreSQL is healthy: `docker compose ps db` or `kubectl -n clouisle get pods -l app=postgres`
- Check that `POSTGRES_SERVER`, `POSTGRES_PASSWORD` are correct in the environment

**Frontend returns 502 for API requests**
- Ensure the backend is running and healthy
- In Docker Compose, the Nginx config proxies `/api/*` to `http://backend:8000` — verify the backend service name matches

**Worker not processing tasks**
- Check worker logs for connection errors to Redis
- Verify `REDIS_HOST` and `REDIS_PASSWORD` are correct

**Beat running duplicate schedules**
- Ensure only 1 beat replica is running (K8s: `replicas: 1` with `Recreate` strategy)
