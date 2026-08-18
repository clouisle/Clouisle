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

Clouisle uses **3 Docker images** running as **5 application services** + **3 infrastructure services**:

```
                         ┌─────────────────────────────────────────────┐
                         │              Frontend Container             │
  Browser ──────────────►│  Next.js standalone (node server.js, :3000) │
                         │    └── /api/*  ──► Next rewrites → api:8000 │
                         └──────────────────┬──────────────────────────┘
                                            │
                         ┌──────────────────▼──────────────────────────┐
                         │              Backend Container              │
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

The frontend container runs the Next.js standalone server directly (`node server.js`) on port 3000; it does **not** include Nginx. API requests are proxied by Next.js rewrites (`/api/:path*` → backend). `deploy/nginx/default.conf` is an optional external Nginx example, not part of the frontend image.

| Image | Services | Description |
|-------|----------|-------------|
| `clouisle-backend` | api, worker, beat | Python 3.13 — API server, Celery worker, Celery beat |
| `clouisle-sandbox-worker` | sandbox-worker | Sandbox task execution and artifact upload |
| `clouisle-frontend` | frontend | Next.js standalone (SSR) |

The backend image is shared across three services, and sandbox execution uses a separate image. Services are differentiated by startup command:

| Service | Command | Replicas |
|---------|---------|----------|
| api | `python main.py server -H 0.0.0.0 -w 4 --no-reload` | 1+ |
| worker | `python main.py worker -c 4 -Q default,knowledge,workflow` | 1+ |
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
# Lint only: this placeholder satisfies the chart's required token and is not a deployment.
helm lint deploy/helm/clouisle \
  --set-string secrets.values.INTERNAL_API_TOKEN=lint-only-token

# Demo only. Do not expose this install; set every production secret or use an existing Secret.
helm upgrade --install clouisle deploy/helm/clouisle \
  --namespace clouisle \
  --create-namespace \
  --set-string secrets.values.SECRET_KEY="$(openssl rand -hex 32)" \
  --set-string secrets.values.POSTGRES_PASSWORD="$(openssl rand -hex 16)" \
  --set-string secrets.values.REDIS_PASSWORD="$(openssl rand -hex 16)" \
  --set-string secrets.values.QDRANT_API_KEY="$(openssl rand -hex 16)" \
  --set-string secrets.values.INTERNAL_API_TOKEN="$(openssl rand -hex 32)"
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

Run the interactive installer from any directory:

```bash
curl -fsSL https://raw.githubusercontent.com/clouisle/Clouisle/main/deploy/install.sh | bash
```

Choose Docker Compose for a single server, Kubernetes with Helm, or Kubernetes single-file manifest generation. Docker mode prompts for an installation directory, defaulting to `/opt/clouisle`, then generates strong secrets, downloads the current Compose file, pulls images, and starts all services. Helm mode guides you through namespace, Ingress, shared storage, and optional image-pull-secret settings. The manifest mode writes a `0600` file at `./clouisle-k8s.yaml` by default (override with `CLOUISLE_K8S_MANIFEST`), does not apply it automatically, and requires applying the generated file path after review; when `CLOUISLE_K8S_MANIFEST` is unset, use `kubectl apply -f ./clouisle-k8s.yaml`.

For non-interactive Docker installation:

```bash
curl -fsSL https://raw.githubusercontent.com/clouisle/Clouisle/main/deploy/install.sh | \
  CLOUISLE_DEPLOYMENT=docker CLOUISLE_YES=1 bash
```

### Configuration

Docker installations keep their generated configuration in `<installation-directory>/.env` (`/opt/clouisle/.env` by default). Review it before exposing the deployment publicly. The following variables are generated automatically when empty:

| Variable | Why | Example |
|----------|-----|---------|
| `SECRET_KEY` | JWT signing — default is insecure | `openssl rand -base64 32` |
| `POSTGRES_PASSWORD` | Database access | `openssl rand -base64 16` |
| `REDIS_PASSWORD` | Cache/queue access | `openssl rand -base64 16` |
| `QDRANT_API_KEY` | Vector DB access | `openssl rand -base64 16` |
| `SANDBOX_ARTIFACT_UPLOAD_API_KEY` | Optional API-key authentication for sandbox artifact uploads | `openssl rand -base64 32` |
| `INTERNAL_API_TOKEN` | Authenticated worker-to-API upload gateway | `openssl rand -base64 32` |

The following are the public-origin settings to change for production. Keep service-to-service URLs internal:

| Variable | Default | Production Example |
|----------|---------|-------------------|
| `PUBLIC_API_URL` | *(empty)* | `https://example.com` |
| `FRONTEND_URL` | `http://localhost:3000` | `https://example.com` |
| `BACKEND_CORS_ORIGINS` | `http://localhost:3000` | `["https://example.com"]` |

`API_BASE_URL` and `API_INTERNAL_BASE_URL` are internal service URLs (usually `http://api:8000` in Compose/Kubernetes), not public domains. `PUBLIC_API_URL` is for browser-visible absolute API/file URLs. `POSTGRES_SERVER`, `REDIS_HOST`, and `QDRANT_URL` are overridden in the supplied deployment files with internal service names.

### Sandbox Filesystem Isolation

The sandbox-worker image installs Bubblewrap and enables per-task filesystem isolation by default:

```bash
SANDBOX_FILESYSTEM_ISOLATION_ENABLED=true
SANDBOX_FILESYSTEM_ISOLATION_BINARY=/usr/bin/bwrap
```

Keep these values enabled for production. Each task receives its current job/session directory at `/workspace`; sibling workspaces and `/app/uploads` are not mounted into the task namespace.

Rootless Bubblewrap needs namespace and mount syscalls. The supplied Compose service sets `seccomp=unconfined` for sandbox-worker only, runs the worker as root with `CAP_SYS_ADMIN` added to the runtime default cap set, and keeps `no-new-privileges` enabled. Do not remove the seccomp setting unless you replace it with a Localhost profile that permits the required syscalls.

The privileged worker creates the Bubblewrap user namespace directly, so the supplied deployments work even on hosts that gate non-privileged user namespaces (e.g. Ubuntu 23.10+ via `kernel.apparmor_restrict_unprivileged_userns=1`, Debian via `kernel.unprivileged_userns_clone=0`) — no host sysctl changes are required. Custom deployments that keep the worker non-root need the host to permit unprivileged user namespaces at the node level (see [Code Sandbox → Host Kernel Requirements](../concepts/code-sandbox.md#host-kernel-requirements)); otherwise every sandbox job fails with `bwrap: No permissions to create new namespace, likely because the kernel does not allow non-privileged user namespaces.`

### User Namespace Remapping (Hardening)

The sandbox task runs in a fresh Bubblewrap user + mount namespace, so it cannot directly reach the worker container's capabilities. However, if a task ever escapes Bubblewrap (a bwrap or kernel vulnerability), it lands inside the worker container **as root with `CAP_SYS_ADMIN`**. In a default Docker daemon the container shares the host's initial user namespace, so that capability is host-user-namespace-scoped and well-known escape chains (cgroup `release_agent`, remounting `/proc` to write `kernel.core_pattern`, sysctl writes) become reachable in principle.

**Docker daemon user namespace remapping** contains this: every container is placed in a nested user namespace, so `CAP_SYS_ADMIN` only applies to the container's own user namespace and the host-escape chains above no longer work. The sandbox worker still creates its Bubblewrap user namespace (privileged inside the remapped namespace), so sandbox functionality is unaffected.

Enable it in `/etc/docker/daemon.json` on the Docker host and restart the daemon:

```json
{
  "userns-remap": "default"
}
```

```bash
systemctl restart docker
```

`default` uses the `dockremap` user and the subuid/subgid ranges from `/etc/subuid` / `/etc/subgid` (Docker creates both on most distributions). Verify the daemon is remapping and that container root is a mapped (non-zero) host uid:

```bash
docker info | grep -i userns          # expect "userns: remap" (not "host")
docker run --rm alpine cat /proc/self/uid_map   # expect "0 100000 65536" style mapping, not "0 0 4294967295"
```

Impact on this deployment:

- **Named volumes only** — the supplied Compose file uses named volumes (`postgres_data`, `redis_data`, `qdrant_data`, `uploads_data`), no host bind mounts. Docker auto-chowns named volumes to the remapped uid range on first use. Volumes created **before** enabling remapping must be re-chowned once, e.g.:
  ```bash
  docker run --rm -v uploads_data:/v -v postgres_data:/p alpine sh -c \
    'chown -R 100000:100000 /v /p'
  ```
  (adjust the uid to the actual remap range shown by `docker info`).
- **All containers on the daemon are remapped** (it is a daemon-wide setting). Services that must see host uids can opt out per container with `userns_mode: "host"` in Compose; Clouisle's supplied services do not need this.
- Restart all services after enabling (`docker compose up -d`) so every container runs inside the remapped user namespace.

For Kubernetes, daemon-level remapping does not apply; node-level user namespace support (containerd + the Kubernetes `UserNamespaces` feature, 1.31+) achieves the same containment on supporting clusters. Otherwise rely on NetworkPolicy for outbound sandbox traffic, keep Bubblewrap updated, and monitor its CVEs.

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

> **Important**: The `uploads_data` volume is mounted **only** by the `api` service. The `worker` and `sandbox-worker` services have no uploads volume; they access uploaded files through the authenticated internal upload gateway (`UPLOAD_STORAGE_MODE=remote`, `API_INTERNAL_BASE_URL` + `INTERNAL_API_TOKEN`, endpoints under `/internal/uploads/`).

### Port Mapping

Default exposed ports:

| Service | Host Port | Container Port | Purpose |
|---------|-----------|---------------|---------|
| frontend | 3000 | 3000 | Web UI (Next.js standalone) |
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
      - "8000:8000"    # Remove — frontend Next rewrites proxy API requests
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
        proxy_read_timeout 1800s;
    }
}
```

When using HTTPS, set the public browser origin separately from internal service URLs:

```bash
# Internal service-to-service address; keep this as http://api:8000 in Compose/Kubernetes.
API_BASE_URL=http://api:8000
API_INTERNAL_BASE_URL=http://api:8000

# Public/browser origin and CORS policy
PUBLIC_API_URL=https://example.com
FRONTEND_URL=https://example.com
BACKEND_CORS_ORIGINS='["https://example.com"]'
```

`API_BASE_URL` is not the public domain. `PUBLIC_API_URL` is used when absolute browser-visible API/file URLs are needed; `FRONTEND_URL` is used for browser/SSO redirects.

### Scaling

```bash
# Scale Celery workers (safe to run multiple)
docker compose up -d --scale worker=4

# Scale backend API (safe to run multiple behind the frontend/external proxy)
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

# Restarting a service may cause downtime; Docker Compose provides no zero-downtime guarantee.
docker compose restart api

# Stop all services
docker compose down

# Stop and destroy all data (CAUTION)
docker compose down -v

# Update images and restart
docker compose pull
docker compose up -d
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

The manifest contains 13 resource sections. It does **not** use YAML anchors — each section is written out explicitly:

| # | Resource | Kind | Notes |
|---|----------|------|-------|
| 1 | Namespace | Namespace | `clouisle` |
| 2 | ConfigMap | ConfigMap | `clouisle-config`, non-sensitive configuration |
| 3 | Secret | Secret | `clouisle-secret`, 6 keys (**must edit/generate**) |
| 4 | PostgreSQL | StatefulSet + Service + PVC | Headless Service, `postgres-data` 10Gi |
| 5 | Redis | Deployment + Service | |
| 6 | Qdrant | StatefulSet + Service + PVC | Headless Service, `qdrant-data` 10Gi |
| 7 | Uploads | PVC | `uploads-data` 10Gi, ReadWriteMany |
| 8 | API | Deployment + Service | 2 replicas, port 8000 |
| 9 | Worker | Deployment | 2 replicas, no Service |
| 10 | Sandbox Worker | Deployment | 1 replica, no Service |
| 11 | Beat | Deployment | 1 replica, `Recreate` strategy |
| 12 | Frontend | Deployment + Service | 2 replicas, port 3000 |
| 13 | Ingress | Ingress | `/api` → api:8000, `/` → frontend:3000 |

### Secrets Configuration

Before applying, replace the base64 placeholder values in the Secret section. The `clouisle-secret` Secret has **6 keys**:

```bash
# Generate base64-encoded values
echo -n 'your-strong-secret-key' | base64
echo -n 'your-postgres-password' | base64
echo -n 'your-redis-password' | base64
echo -n 'your-qdrant-api-key' | base64
echo -n 'your-sandbox-artifact-key' | base64
echo -n 'your-internal-gateway-token' | base64
```

Replace in `clouisle.yaml`:

```yaml
data:
  SECRET_KEY: <paste-base64-here>
  POSTGRES_PASSWORD: <paste-base64-here>
  REDIS_PASSWORD: <paste-base64-here>
  QDRANT_API_KEY: <paste-base64-here>
  SANDBOX_ARTIFACT_UPLOAD_API_KEY: <paste-base64-here>
  INTERNAL_API_TOKEN: <paste-base64-here>
```

> **Note**: `INTERNAL_API_TOKEN` is required and shared by the API, worker, and sandbox-worker workloads. `SANDBOX_ARTIFACT_UPLOAD_API_KEY` is optional; set it to add API-key authentication to sandbox artifact uploads. The supplied manifest keeps that Secret key with an empty value when it is unused. `deploy/install.sh` generates the internal token in Kubernetes output copies (mode `0600`); review and apply them manually. The workloads read `INTERNAL_API_TOKEN` through the `INTERNAL_API_TOKEN_FILE` mount.

> **Tip**: For production, consider using an external secret manager (Vault, AWS Secrets Manager, etc.) with the External Secrets Operator instead of storing secrets in YAML.

### Persistent Storage

| PVC | Size | Used By | Access Mode |
|-----|------|---------|-------------|
| `postgres-data` | 10Gi | PostgreSQL | ReadWriteOnce |
| `qdrant-data` | 10Gi | Qdrant | ReadWriteOnce |
| `uploads-data` | 10Gi | API (uploads) | ReadWriteMany |

To change the storage size or class, edit the PVC definitions:

```yaml
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: your-storage-class    # Add this line
  resources:
    requests:
      storage: 50Gi                       # Adjust size
```

The `uploads-data` PVC (10Gi, `ReadWriteMany`) is mounted by the `api` Deployment at `/app/uploads`. Workers and sandbox-worker do **not** mount it — they read/write authorized documents and upload sandbox artifacts through the authenticated internal upload gateway. `ReadWriteMany` is only required when scaling `api` beyond one replica with local upload storage; with `ReadWriteOnce` keep `api` at one replica (worker and sandbox-worker replicas remain independently scalable).

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

Also update the ConfigMap (keep `API_BASE_URL` internal; put the public origin in `PUBLIC_API_URL`):

```yaml
data:
  PUBLIC_API_URL: "https://your-domain.com"
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
POD_NAME='replace-with-pod-name'
kubectl -n clouisle logs -f "$POD_NAME"

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
| `INTERNAL_API_TOKEN` | Shared internal upload-gateway token for API, worker, and sandbox-worker | `openssl rand -hex 32` |

### Recommended (Should Change for Production)
| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_PASSWORD` | *(empty)* | Redis password. Empty means no authentication. |
| `QDRANT_API_KEY` | *(empty)* | Qdrant API key. Empty means no authentication. |
| `PUBLIC_API_URL` | *(empty)* | Browser-visible public API origin for absolute API/file URLs. |
| `FRONTEND_URL` | `http://localhost:3000` | Frontend URL used for SSO redirect URIs. Set to your actual public domain in production. |
| `BACKEND_CORS_ORIGINS` | `http://localhost:3000` | Comma-separated list of allowed CORS origins. Must include your frontend domain. |

> `API_BASE_URL` and `API_INTERNAL_BASE_URL` are internal server-to-server addresses used by the backend and workers. Do not set them to public domains. Use `PUBLIC_API_URL` for browser-visible API/file links and `FRONTEND_URL` for SSO redirect URIs.

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
| `SANDBOX_RUNTIME_ENABLED` | `true` | Route executable tasks through the sandbox runtime. |
| `SANDBOX_FILESYSTEM_ISOLATION_ENABLED` | `true` in sandbox-worker deployments | Enable the Bubblewrap mount namespace. Generic application default is `false`. |
| `SANDBOX_FILESYSTEM_ISOLATION_BINARY` | `/usr/bin/bwrap` in sandbox-worker deployments | Bubblewrap executable path. Generic application default is `bwrap`. |
| `SANDBOX_WORKER_CONCURRENCY` | `1` | Sandbox Celery worker concurrency. |
| `SANDBOX_WORKSPACE_ROOT` | `/tmp/clouisle-sandbox/jobs` | Host-side root for sandbox job and session directories. |

---

## Request Flow & Proxy Architecture

Understanding the request flow is important for debugging and configuring external reverse proxies.

### Client-Side API Requests

```
Browser
  │
  ├── Page requests (HTML/SSR) ──► Node.js SSR (frontend container, :3000)
  │
  └── API requests (/api/*) ──► Next rewrites (frontend container) ──► Backend Gunicorn (:8000)
```

The frontend container runs the Next.js standalone server (`node server.js`) on port 3000. It handles server-side rendering and proxies `/api/*` requests to the backend through Next.js rewrites (`frontend/next.config.ts`, destination from `BACKEND_INTERNAL_URL`, default `http://api:8000`).

### Header Forwarding

The optional external Nginx (`deploy/nginx/default.conf`) forwards the following headers to the backend on `/api/*` requests (when used in front of the frontend container):

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
External Proxy → frontend container (node server.js, :3000) → Next rewrites → Backend Gunicorn (:8000)
```

The external proxy must set `X-Real-IP` and `X-Forwarded-For` correctly. If the external proxy itself proxies `/api/*` directly to the backend, it must forward the same headers (the `deploy/nginx/default.conf` example shows the full header set).

---

## Backup & Restore

### PostgreSQL

```bash
# Docker Compose — backup
docker compose exec -T db pg_dump -U postgres -Fc clouisle > backup_$(date +%Y%m%d).dump

# Docker Compose — restore
docker compose exec -T db pg_restore -U postgres -d clouisle --clean --if-exists < backup_20260206.dump

# Kubernetes — backup
kubectl -n clouisle exec -i statefulset/postgres -- pg_dump -U postgres -Fc clouisle > backup.dump

# Kubernetes — restore
kubectl -n clouisle exec -i statefulset/postgres -- pg_restore -U postgres -d clouisle --clean --if-exists < backup.dump
```

### Qdrant

Run these Compose commands from the directory containing the active `docker-compose.yml` and `.env`: `deploy/` for a source checkout, or the installer-created directory such as `/opt/clouisle`. The supplied Compose volume is project-prefixed, so discover its actual Docker volume name instead of assuming `deploy_qdrant_data`.

The file-level volume backup below does not require a Qdrant host port. If you use the API-based snapshot procedure instead and production hardening removed the mapping, temporarily add `127.0.0.1:6333:6333`, recreate Qdrant, then remove the mapping after the API backup. Do not publish Qdrant on all host interfaces just to run a backup.

```bash
QDRANT_VOLUME="$(docker inspect "$(docker compose ps -q qdrant)" --format '{{range .Mounts}}{{if eq .Destination "/qdrant/storage"}}{{.Name}}{{end}}{{end}}')"
test -n "$QDRANT_VOLUME"
docker run --rm -v "$QDRANT_VOLUME:/data:ro" -v "$(pwd):/backup" \
  alpine tar czf /backup/qdrant_backup.tar.gz -C /data .
```

For a portable Qdrant backup, use the Qdrant collection snapshot API for each collection and pass `api-key: $QDRANT_API_KEY` when authentication is enabled. The API is collection-scoped; there is no generic `/snapshots` endpoint in the supplied application.

### Uploaded Files

Stream the API-mounted uploads directory so the command does not depend on a Docker volume prefix:

```bash
docker compose exec -T api \
  tar -czf - -C /app uploads > uploads_backup.tar.gz
```

In Kubernetes, use the `uploads-data` PVC mounted by `api` and an explicit backup destination:

```bash
kubectl -n clouisle exec -i deployment/api -- tar -czf - -C /app uploads > uploads_backup.tar.gz
```

### Automated Backup Schedule

The supplied Kubernetes manifest does not declare a `backup-pvc` and does not install a backup CronJob. Provision an approved object-store, backup PVC, or CSI snapshot destination first, then schedule the PostgreSQL/Qdrant/uploads commands above. Do not treat a pod-local `emptyDir` as durable backup storage.


---

## Upgrading

### Docker Compose

The supplied Compose file references prebuilt images; it has no `build:` blocks and `docker compose up -d` is not a rolling-update guarantee.

```bash
cd /path/to/clouisle
git pull
docker compose -f deploy/docker-compose.yml pull
docker compose -f deploy/docker-compose.yml up -d --force-recreate
docker compose -f deploy/docker-compose.yml ps
docker compose -f deploy/docker-compose.yml logs --tail=50 api worker sandbox-worker beat frontend
```

### Kubernetes

Build and push immutable, versioned tags from the repository root, then update every application workload in the `clouisle` namespace:

```bash
cd /path/to/clouisle
REGISTRY=registry.example.com/clouisle
IMAGE_TAG=vX.Y.Z
docker build -f deploy/dockerfiles/backend.Dockerfile -t "$REGISTRY/clouisle-backend:$IMAGE_TAG" .
docker build -f deploy/dockerfiles/frontend.Dockerfile -t "$REGISTRY/clouisle-frontend:$IMAGE_TAG" .
docker build -f deploy/dockerfiles/sandbox-worker.Dockerfile -t "$REGISTRY/clouisle-sandbox-worker:$IMAGE_TAG" .
docker push "$REGISTRY/clouisle-backend:$IMAGE_TAG"
docker push "$REGISTRY/clouisle-frontend:$IMAGE_TAG"
docker push "$REGISTRY/clouisle-sandbox-worker:$IMAGE_TAG"

kubectl -n clouisle set image deployment/api api="$REGISTRY/clouisle-backend:$IMAGE_TAG"
kubectl -n clouisle set image deployment/worker worker="$REGISTRY/clouisle-backend:$IMAGE_TAG"
kubectl -n clouisle set image deployment/sandbox-worker sandbox-worker="$REGISTRY/clouisle-sandbox-worker:$IMAGE_TAG"
kubectl -n clouisle set image deployment/beat beat="$REGISTRY/clouisle-backend:$IMAGE_TAG"
kubectl -n clouisle set image deployment/frontend frontend="$REGISTRY/clouisle-frontend:$IMAGE_TAG"

kubectl -n clouisle rollout status deployment/api
kubectl -n clouisle rollout status deployment/worker
kubectl -n clouisle rollout status deployment/sandbox-worker
kubectl -n clouisle rollout status deployment/beat
kubectl -n clouisle rollout status deployment/frontend
```

The backend initializes/updates the schema at startup through Tortoise ORM (`init_db`); do not run a routine Alembic migration command. Follow release-specific notes only when a release explicitly documents an additional data migration.

---

## Security Checklist

- [ ] **Change all default passwords** — `SECRET_KEY`, `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `QDRANT_API_KEY`
- [ ] **Enable HTTPS** — Use TLS termination at the external reverse proxy or K8s Ingress
- [ ] **Restrict exposed ports** — In production, only expose port 3000 (or 443 via reverse proxy). Remove database/Redis/Qdrant port mappings.
- [ ] **Set CORS origins** — `BACKEND_CORS_ORIGINS` should only contain your actual frontend domain, not `*`
- [ ] **Set URL variables by role** — keep `API_BASE_URL` internal (for example `http://api:8000` inside Compose/K8s); use `PUBLIC_API_URL` for browser-visible API/file links and `FRONTEND_URL` for SSO redirects
- [ ] **Network isolation** — In Docker Compose, infrastructure services (db, redis, qdrant) should not be accessible from outside. In K8s, they use ClusterIP services (no external access by default).
- [ ] **Regular backups** — Set up automated PostgreSQL and Qdrant backups
- [ ] **Resource limits** — Review and adjust CPU/memory limits in K8s manifests based on actual usage
- [ ] **Verify sandbox isolation** — Keep `SANDBOX_FILESYSTEM_ISOLATION_ENABLED=true`, ensure `/usr/bin/bwrap` exists in the sandbox-worker image, retain the worker-specific seccomp configuration, and confirm the worker runs as root with `CAP_SYS_ADMIN` (`grep CapEff /proc/self/status` non-zero in the container) — or, for non-root worker setups, that the host permits unprivileged user namespaces (`unshare -U true`)
- [ ] **Docker daemon hardening (Compose)** — Consider enabling user namespace remapping (`userns-remap` in `/etc/docker/daemon.json`) so the worker's `CAP_SYS_ADMIN` is contained in a nested user namespace (see [User Namespace Remapping](#user-namespace-remapping-hardening)); re-chown pre-existing volumes after enabling
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

The frontend container proxies `/api/*` to `http://api:8000` via Next.js rewrites (destination from `BACKEND_INTERNAL_URL`). A 502 means the backend is unreachable.

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

### Sandbox jobs fail with bwrap user namespace error

```text
bwrap: No permissions to create new namespace, likely because the kernel does not allow non-privileged user namespaces.
```

With the supplied deployments this means the worker is not actually running as root with `CAP_SYS_ADMIN` (the image's non-root user has empty effective capabilities, so `cap_add` alone does nothing — the deployment must set `user: "0"` / `runAsUser: 0`). Verify inside the container: `grep CapEff /proc/self/status` must be non-zero.

For custom deployments that keep the worker non-root, the host kernel must permit unprivileged user namespaces — fix at the **node level** (`seccomp=unconfined` does not help): on Ubuntu 23.10+ run `sysctl -w kernel.apparmor_restrict_unprivileged_userns=0`; on Debian run `sysctl -w kernel.unprivileged_userns_clone=1`, then persist via `/etc/sysctl.d/` and verify with `unshare -U true`. See [Code Sandbox → Host Kernel Requirements](../concepts/code-sandbox.md#host-kernel-requirements). In Kubernetes apply the sysctl to every node; it cannot be set per pod.

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

In the supplied deployments the `uploads_data` volume is mounted **only** by the `api` service; workers access files through the authenticated internal upload gateway (`/internal/uploads/...`, protected by `INTERNAL_API_TOKEN`):

```bash
# Docker Compose — api mounts the volume; worker must NOT have it mounted
docker compose exec api ls -la /app/uploads
docker compose exec api env | grep -E "UPLOAD_STORAGE_MODE|INTERNAL_API_TOKEN"
```

If `UPLOAD_STORAGE_MODE=remote` is set (workers) but the gateway token is missing or mismatched, document processing fails with authentication errors — regenerate and share a single `INTERNAL_API_TOKEN` between api and the workers. In Kubernetes, `uploads-data` is the 10Gi `ReadWriteMany` PVC mounted only by `api` (see [Persistent Storage](#persistent-storage)).

### Out of memory / OOM killed

Check resource usage and adjust limits:

```bash
# Docker
docker stats

# Kubernetes
kubectl -n clouisle top pods
POD_NAME='replace-with-pod-name'
kubectl -n clouisle describe pod "$POD_NAME"  # Check "Last State" for OOMKilled
```

Adjust resource limits in `docker-compose.yml` (add `deploy.resources`) or in `clouisle.yaml` (edit the `resources` section).

### LLM requests timing out

The default proxy timeout is 1800 seconds (30 minutes). For very long LLM operations:

- Optional external Nginx: edit `proxy_read_timeout` / `proxy_send_timeout` in `deploy/nginx/default.conf`
- K8s Ingress: edit `nginx.ingress.kubernetes.io/proxy-read-timeout` annotation
- Gunicorn: edit `--timeout` in the `start_server` command in `main.py` (the production gunicorn invocation) — the supplied Compose/K8s `api` command does not override it
