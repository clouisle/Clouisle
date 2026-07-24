# Clouisle Deployment Guide

## Architecture

Clouisle uses **3 Docker images** that run as **5 application services**:

| Image | Service(s) | Description |
|-------|------------|-------------|
| `clouisle-backend` | `api`, `worker`, `beat` | FastAPI API server, Celery worker, Celery beat scheduler |
| `clouisle-sandbox-worker` | `sandbox-worker` | Sandbox task execution and artifact collection |
| `clouisle-frontend` | `frontend` | Next.js standalone server running with `node server.js` |

Infrastructure dependencies: **PostgreSQL 16**, **Redis 7**, **Qdrant 1.18.3**, and **OpenSearch 3.7.0**.

The API service is named `api` in deployment files. Older docs and scripts may refer to it as `backend`; update those commands to use `api`.

### Request Routing

The frontend container serves the Next.js standalone app on port 3000. It does not include Nginx. In production, route traffic with an external reverse proxy or Ingress:

- `/api/*` → `api:8000`
- `/` → `frontend:3000`

`deploy/nginx/default.conf` is an optional external Nginx example, not part of the current frontend image.

---

## Building Images

### CI/CD

Push a `v*` tag to trigger `.github/workflows/build-images.yml`:

```bash
git tag v0.1.0
git push origin v0.1.0
```

Images are pushed to:

```text
<ACR_REGISTRY>/<ACR_NAMESPACE>/clouisle-backend:<version>
<ACR_REGISTRY>/<ACR_NAMESPACE>/clouisle-sandbox-worker:<version>
<ACR_REGISTRY>/<ACR_NAMESPACE>/clouisle-frontend:<version>
```

Required GitHub Secrets: `ACR_REGISTRY`, `ACR_NAMESPACE`, `ACR_USERNAME`, `ACR_PASSWORD`.

### Local Build

From the project root:

```bash
docker build -f deploy/dockerfiles/backend.Dockerfile -t clouisle-backend .
docker build -f deploy/dockerfiles/sandbox-worker.Dockerfile -t clouisle-sandbox-worker .
docker build -f deploy/dockerfiles/frontend.Dockerfile -t clouisle-frontend .
```

---

## Docker Compose Deployment

### Quick Start

```bash
cd deploy
cp .env.example .env
# Edit .env and set strong values for SECRET_KEY, POSTGRES_PASSWORD, REDIS_PASSWORD,
# QDRANT_API_KEY, and OPENSEARCH_PASSWORD.

docker compose up -d --build
```

Compose reads `deploy/.env`. The default image prefix is `clouisle`; set these when using registry images:

```env
IMAGE_REGISTRY=registry.cn-hangzhou.aliyuncs.com/your-namespace/clouisle
IMAGE_TAG=0.1.0
```

### Services

| Service | Port | Description |
|---------|------|-------------|
| `frontend` | 3000 | Next.js standalone server |
| `api` | 8000 | FastAPI API server |
| `worker` | — | Celery worker for `default,workflow` queues |
| `sandbox-worker` | — | Celery worker for sandbox queue and artifact upload |
| `beat` | — | Celery beat scheduler; keep exactly one replica |
| `db` | 5432 | PostgreSQL 16 |
| `redis` | 6379 | Redis 7 |
| `qdrant` | 6333 | Qdrant 1.18.3 vector database |
| `opensearch` | 9200 | OpenSearch 3.7.0 lexical index |

### Important Internal URLs

Containerized services should use internal service names:

```env
POSTGRES_SERVER=db
REDIS_HOST=redis
QDRANT_URL=http://qdrant:6333
OPENSEARCH_URL=https://opensearch:9200
OPENSEARCH_USERNAME=admin
API_BASE_URL=http://api:8000
SANDBOX_ARTIFACT_UPLOAD_BASE_URL=http://api:8000
```

`sandbox-worker` uploads artifacts to `/api/v1/upload/sandbox-artifact`. Keep `SANDBOX_ARTIFACT_UPLOAD_BASE_URL` on an internal API address; do not point it at `localhost` inside containers.

### Volumes

| Volume | Purpose |
|--------|---------|
| `postgres_data` | PostgreSQL data |
| `redis_data` | Redis persistence |
| `qdrant_data` | Qdrant vector storage |
| `opensearch_data` | OpenSearch lexical indexes |
| `uploads_data` | User uploads and sandbox artifacts |

### Common Operations

```bash
# View logs
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f sandbox-worker
docker compose logs -f beat
docker compose logs -f frontend

# Restart a single service
docker compose restart api

# Scale workers
docker compose up -d --scale worker=4
docker compose up -d --scale sandbox-worker=2

# Stop everything
docker compose down

# Stop and remove volumes (DESTROYS DATA)
docker compose down -v
```

---

## Kubernetes Deployment

### Prerequisites

- Kubernetes cluster 1.25+
- `kubectl` configured
- Helm 3.x installed
- Ingress controller, such as ingress-nginx
- Container images pushed to a registry accessible by the cluster
- A `ReadWriteMany` capable StorageClass for multi-replica uploads, or single-replica application deployments

### Option A: Helm Chart (recommended)

```bash
helm lint deploy/helm/clouisle
helm upgrade --install clouisle deploy/helm/clouisle \
  --namespace clouisle \
  --create-namespace
```

For production, create a Secret and use `values-production.yaml`:

```bash
kubectl create namespace clouisle
kubectl -n clouisle create secret generic clouisle-secret \
  --from-literal=SECRET_KEY='replace-with-strong-random-key' \
  --from-literal=POSTGRES_PASSWORD='replace-with-postgres-password' \
  --from-literal=REDIS_PASSWORD='replace-with-redis-password' \
  --from-literal=QDRANT_API_KEY='replace-with-qdrant-api-key' \
  --from-literal=OPENSEARCH_PASSWORD='replace-with-a-strong-opensearch-password'

helm upgrade --install clouisle deploy/helm/clouisle \
  --namespace clouisle \
  --create-namespace \
  -f deploy/helm/clouisle/values-production.yaml
```

See `deploy/helm/clouisle/README.md` for external PostgreSQL, Redis, Qdrant, and OpenSearch examples.

### Option B: Single-file manifest

The plain manifest is still available at `deploy/k8s/clouisle.yaml` for debugging or environments that do not use Helm.

```bash
# 1. Edit the manifest: replace base64 secret placeholders and set image/domain/storage values.
vi deploy/k8s/clouisle.yaml

# 2. Apply everything
kubectl apply -f deploy/k8s/clouisle.yaml

# 3. Wait for infrastructure
kubectl -n clouisle wait --for=condition=ready pod -l app=postgres --timeout=120s
kubectl -n clouisle wait --for=condition=ready pod -l app=redis --timeout=120s
kubectl -n clouisle wait --for=condition=ready pod -l app=qdrant --timeout=120s
kubectl -n clouisle wait --for=condition=ready pod -l app=opensearch --timeout=180s
```

### Manifest Sections

| # | Resource | Notes |
|---|----------|-------|
| 1 | Namespace | `clouisle` |
| 2 | ConfigMap | Non-sensitive configuration |
| 3 | Secret | Passwords and keys |
| 4 | PostgreSQL | StatefulSet + headless Service + PVC |
| 5 | Redis | Deployment + Service |
| 6 | Qdrant | StatefulSet + headless Service + PVC |
| 7 | OpenSearch | Single-node StatefulSet + headless Service + PVC |
| 8 | Uploads | Shared `uploads-data` PVC |
| 9 | API | Deployment + Service :8000 |
| 10 | Worker | Deployment, no Service |
| 11 | Sandbox Worker | Deployment, no Service |
| 12 | Beat | Deployment, 1 replica, Recreate |
| 13 | Frontend | Deployment + Service :3000 |
| 14 | Ingress | `/api` → `api`, `/` → `frontend` |

### Scaling

```bash
kubectl -n clouisle scale deployment worker --replicas=4
kubectl -n clouisle scale deployment sandbox-worker --replicas=2
kubectl -n clouisle scale deployment api --replicas=3
```

Keep `beat` at exactly one replica.

If `uploads-data` uses `ReadWriteMany`, API/worker/sandbox-worker replicas can share uploaded files and sandbox artifacts. If your cluster does not support RWX storage, keep those deployments single-replica or move uploads/artifacts to object storage before scaling.

### Logs

```bash
kubectl -n clouisle logs -f deployment/api
kubectl -n clouisle logs -f deployment/worker
kubectl -n clouisle logs -f deployment/sandbox-worker
kubectl -n clouisle logs -f deployment/beat
kubectl -n clouisle logs -f deployment/frontend
```

---

## Environment Variables

| Variable | Required | Compose default | Description |
|----------|----------|-----------------|-------------|
| `SECRET_KEY` | Yes | placeholder | JWT signing key and default sandbox upload signing basis |
| `API_BASE_URL` | Yes | `http://api:8000` | Internal API URL for containers |
| `SANDBOX_ARTIFACT_UPLOAD_BASE_URL` | Yes for sandbox | `http://api:8000` | Internal API URL used by sandbox artifact upload |
| `FRONTEND_URL` | Yes | `http://localhost:3000` | Public frontend URL |
| `BACKEND_CORS_ORIGINS` | Yes | `["http://localhost:3000"]` | JSON array of allowed frontend origins |
| `POSTGRES_SERVER` | Yes | `db` | PostgreSQL host |
| `POSTGRES_PASSWORD` | Yes | empty | PostgreSQL password |
| `REDIS_HOST` | Yes | `redis` | Redis host |
| `REDIS_PASSWORD` | Recommended | empty | Redis password |
| `QDRANT_URL` | Yes | `http://qdrant:6333` | Qdrant URL |
| `QDRANT_API_KEY` | Recommended | empty | Qdrant API key |
| `OPENSEARCH_URL` | Yes | `https://opensearch:9200` | OpenSearch endpoint |
| `OPENSEARCH_USERNAME` | Yes | `admin` | OpenSearch user |
| `OPENSEARCH_PASSWORD` | Yes | documented placeholder | OpenSearch password; replace before deployment |
| `OPENSEARCH_JAVA_OPTS` | No | `-Xms512m -Xmx512m` | Built-in single-node heap settings |
| `RETRIEVAL_HYBRID_KILL_SWITCH` | No | `false` | Emergency environment override that forces vector-only retrieval |
| `RETRIEVAL_SHADOW_ENABLED` | No | `false` | Run hybrid retrieval in shadow for rollout-excluded teams; stores IDs, ranks, versions, and latency only |
| `SANDBOX_WORKER_CONCURRENCY` | No | `1` | Sandbox worker concurrency |
| `SANDBOX_WORKSPACE_ROOT` | No | `/tmp/clouisle-sandbox/jobs` | Sandbox workspace root |
| `NEXT_PUBLIC_API_URL` | Yes for frontend build | `/api/v1` | Browser-visible API base path |
| `TAVILY_API_KEY` | No | empty | Tavily search API key |

---

## Troubleshooting

**API can't connect to database**
- Check `docker compose ps db` or `kubectl -n clouisle get pods -l app=postgres`.
- Verify `POSTGRES_SERVER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB`.

**Frontend cannot reach API**
- Confirm your external proxy or Ingress sends `/api/*` to `api:8000`.
- In Compose, verify `docker compose logs -f api` and `curl http://localhost:8000/api/v1/health`.

**Sandbox artifacts are not uploaded**
- Verify `SANDBOX_ARTIFACT_UPLOAD_BASE_URL=http://api:8000` in containerized deployment.
- Check `docker compose logs -f sandbox-worker` or `kubectl -n clouisle logs -f deployment/sandbox-worker`.
- Ensure `SECRET_KEY` is the same for `api` and `sandbox-worker`, unless `SANDBOX_ARTIFACT_UPLOAD_API_KEY` is configured.

**Worker not processing tasks**
- Check worker logs for Redis connection or auth errors.
- Verify `REDIS_HOST` and `REDIS_PASSWORD`.

**Observability slow queries are unavailable**
- The built-in Compose and Helm PostgreSQL services start with `shared_preload_libraries=pg_stat_statements` and `pg_stat_statements.track=all`.
- For an existing PostgreSQL container, restart/recreate the database container after applying the updated command so the preload setting takes effect.
- For external PostgreSQL, ask the database administrator to enable `pg_stat_statements` in `shared_preload_libraries`, restart PostgreSQL, and allow the application database user to run `CREATE EXTENSION IF NOT EXISTS pg_stat_statements` or create the extension manually.

**Beat running duplicate schedules**
- Ensure only one `beat` replica is running.

**Old backend commands no longer work**
- Replace `backend` service references with `api`, for example `docker compose logs -f api`.
