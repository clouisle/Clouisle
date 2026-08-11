# Clouisle Deployment Guide

## Architecture

Clouisle uses **3 Docker images** that run as **5 application services**:

| Image | Service(s) | Description |
|-------|------------|-------------|
| `clouisle-backend` | `api`, `worker`, `beat` | FastAPI API server, Celery worker, Celery beat scheduler |
| `clouisle-sandbox-worker` | `sandbox-worker` | Sandbox task execution and artifact collection |
| `clouisle-frontend` | `frontend` | Next.js standalone server running with `node server.js` |

Infrastructure dependencies are **PostgreSQL 17 with pg_search 0.24.3**, **Redis 7**, and **Qdrant 1.18.3**. `registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-postgres-pg-search:0.24.3-pg17-alpine1` is the canonical built-in PostgreSQL image. It is built from `deploy/postgres/Dockerfile` and maintained by Clouisle as an Alpine/musl port.

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
registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-backend:latest
registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-sandbox-worker:latest
registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-frontend:latest
```

Required GitHub Secrets: `ACR_REGISTRY`, `ACR_NAMESPACE`, `ACR_USERNAME`, `ACR_PASSWORD`.

### Local Build

From the project root:

```bash
docker build -f deploy/postgres/Dockerfile -t registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-postgres-pg-search:0.24.3-pg17-alpine1 .
docker build -f deploy/dockerfiles/backend.Dockerfile -t clouisle-backend .
docker build -f deploy/dockerfiles/sandbox-worker.Dockerfile -t clouisle-sandbox-worker .
docker build -f deploy/dockerfiles/frontend.Dockerfile -t clouisle-frontend .
```

---

## Docker Compose Deployment

### Guided One-Command Install

```bash
curl -fsSL https://raw.githubusercontent.com/clouisle/Clouisle/main/deploy/install.sh | bash
```

The installer offers Docker Compose, Kubernetes with Helm, or secure single-file Kubernetes manifest generation. Docker mode prompts for an installation directory (`/opt/clouisle` by default), downloads deployment files, generates strong secrets, validates the Compose configuration, pulls published images, and starts services. Existing `.env` files are preserved during upgrades.

### Manual Docker Compose Install

```bash
cd deploy
cp .env.example .env
# Generate the shared API-to-worker gateway token before starting Compose.
internal_api_token="$(openssl rand -hex 32)"
sed -i.bak "s/^INTERNAL_API_TOKEN=.*/INTERNAL_API_TOKEN=${internal_api_token}/" .env
rm .env.bak
unset internal_api_token
# Edit .env when custom domains or external API keys are required.
docker compose pull
docker compose up -d
```

Compose pulls the published `latest` images listed above by default.

### Services

| Service | Port | Description |
|---------|------|-------------|
| `frontend` | 3000 | Next.js standalone server |
| `api` | 8000 | FastAPI API server |
| `worker` | — | Celery worker for `default,knowledge,workflow` queues |
| `sandbox-worker` | — | Celery worker for sandbox queue and artifact upload |
| `beat` | — | Celery beat scheduler; keep exactly one replica |
| `db` | 5432 | ParadeDB PostgreSQL 17 with pg_search 0.24.3 |
| `redis` | 6379 | Redis 7 |
| `qdrant` | 6333 | Qdrant 1.18.3 vector database |

### Important Internal URLs

Containerized services should use internal service names:

```env
POSTGRES_SERVER=db
REDIS_HOST=redis
QDRANT_URL=http://qdrant:6333
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
- `kubectl` configured to apply either Kubernetes option
- Helm 3.x only for the Helm chart option
- Ingress controller, such as ingress-nginx
- Container images pushed to a registry accessible by the cluster
- A `ReadWriteMany` capable StorageClass for multiple API replicas using local upload storage; otherwise use one API replica or object storage

### Option A: Helm Chart (recommended)

```bash
helm lint deploy/helm/clouisle \
  --set-string secrets.values.INTERNAL_API_TOKEN=lint-only-token
helm upgrade --install clouisle deploy/helm/clouisle \
  --namespace clouisle \
  --create-namespace \
  --set-string secrets.values.INTERNAL_API_TOKEN="$(openssl rand -hex 32)"

```

For production, create a Secret and use `values-production.yaml`:

```bash
kubectl create namespace clouisle
kubectl -n clouisle create secret generic clouisle-secret \
  --from-literal=SECRET_KEY='replace-with-strong-random-key' \
  --from-literal=POSTGRES_PASSWORD='replace-with-postgres-password' \
  --from-literal=REDIS_PASSWORD='replace-with-redis-password' \
  --from-literal=QDRANT_API_KEY='replace-with-qdrant-api-key' \
  --from-literal=SANDBOX_ARTIFACT_UPLOAD_API_KEY='replace-with-sandbox-artifact-key' \
  --from-literal=INTERNAL_API_TOKEN='replace-with-internal-upload-gateway-token'

helm upgrade --install clouisle deploy/helm/clouisle \
  --namespace clouisle \
  --create-namespace \
  -f deploy/helm/clouisle/values-production.yaml
```

See `deploy/helm/clouisle/README.md` for external PostgreSQL, Redis, and Qdrant examples.

### Option B: Generated single-file manifest

Generate a separate manifest with strong values for all required application secrets. The source
template is not changed, the output is mode `0600`, and the installer does **not** apply it.

```bash
curl -fsSL https://raw.githubusercontent.com/clouisle/Clouisle/main/deploy/install.sh | \
  CLOUISLE_DEPLOYMENT=k8s \
  CLOUISLE_K8S_MANIFEST="$PWD/clouisle-k8s.yaml" \
  CLOUISLE_YES=1 bash

# Review image, domain, and storage settings before applying.
kubectl apply -f ./clouisle-k8s.yaml
```

The generated document contains base64-encoded secrets; store it securely and do not commit it.
It contains `SECRET_KEY`, `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `QDRANT_API_KEY`,
`SANDBOX_ARTIFACT_UPLOAD_API_KEY`, and `INTERNAL_API_TOKEN`. The raw backend workloads wait in
their `wait-for-postgres` init containers until PostgreSQL accepts connections, preventing a
database startup race from turning into application restart loops.

### Option C: Manual single-file template

`deploy/k8s/clouisle.yaml` remains available for debugging or environments that need a manually
edited template.

```bash
# 1. Replace base64 Secret placeholders and set image/domain/storage values.
vi deploy/k8s/clouisle.yaml

# 2. Apply everything. Backend workloads wait for PostgreSQL automatically.
kubectl apply -f deploy/k8s/clouisle.yaml

# 3. Observe infrastructure readiness when diagnosing a cluster deployment.
kubectl -n clouisle wait --for=condition=ready pod -l app=postgres --timeout=120s
kubectl -n clouisle wait --for=condition=ready pod -l app=redis --timeout=120s
kubectl -n clouisle wait --for=condition=ready pod -l app=qdrant --timeout=120s
```

### Manifest Sections

| # | Resource | Notes |
|---|----------|-------|
| 1 | Namespace | `clouisle` |
| 2 | ConfigMap | Non-sensitive configuration |
| 3 | Secret | Passwords and keys |
| 4 | PostgreSQL | ParadeDB PG17 StatefulSet + headless Service + PVC |
| 5 | Redis | Deployment + Service |
| 6 | Qdrant | StatefulSet + headless Service + PVC |
| 7 | Uploads | Shared `uploads-data` PVC |
| 8 | API | Deployment + Service :8000 |
| 9 | Worker | Deployment, no Service |
| 10 | Sandbox Worker | Deployment, no Service |
| 11 | Beat | Deployment, 1 replica, Recreate |
| 12 | Frontend | Deployment + Service :3000 |
| 13 | Ingress | `/api` → `api`, `/` → `frontend` |

### Scaling

```bash
kubectl -n clouisle scale deployment worker --replicas=4
kubectl -n clouisle scale deployment sandbox-worker --replicas=2
kubectl -n clouisle scale deployment api --replicas=3
```

Keep `beat` at exactly one replica.

`uploads-data` is mounted only by `api`; workers and sandbox-worker read authorized attachments/documents through the authenticated internal upload gateway, while sandbox artifacts are uploaded through the API. Local upload storage needs `ReadWriteMany` only when scaling `api` beyond one replica. With `ReadWriteOnce`, keep `api` at one replica; worker and sandbox-worker replicas remain independently scalable.

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
| `PUBLIC_API_URL` | No | empty | Public API origin used when workflow file URLs must be absolute |
| `SANDBOX_ARTIFACT_UPLOAD_BASE_URL` | Yes for sandbox | `http://api:8000` | Internal API URL used by sandbox artifact upload |
| `FRONTEND_URL` | Yes | `http://localhost:3000` | Public frontend URL |
| `BACKEND_CORS_ORIGINS` | Yes | `["http://localhost:3000"]` | JSON array of allowed frontend origins |
| `POSTGRES_SERVER` | Yes | `db` | PostgreSQL host |
| `POSTGRES_PASSWORD` | Yes | empty | PostgreSQL password |
| `REDIS_HOST` | Yes | `redis` | Redis host |
| `REDIS_PASSWORD` | Recommended | empty | Redis password |
| `QDRANT_URL` | Yes | `http://qdrant:6333` | Qdrant URL |
| `QDRANT_API_KEY` | Recommended | empty | Qdrant API key |
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

**PostgreSQL and lexical search prerequisites**
- Compose, raw Kubernetes, and Helm use `registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-postgres-pg-search:0.24.3-pg17-alpine1` by default. This Clouisle-maintained Alpine/musl image requires full amd64 and arm64 qualification whenever Alpine, PostgreSQL, Rust, pgrx, or pg_search changes.
- Built-in deployments start with `shared_preload_libraries=pg_search,pg_stat_statements` plus `pg_stat_statements.track=all`.
- External PostgreSQL must be PostgreSQL 17 or newer with pg_search 0.24.3 installed and `pg_search,pg_stat_statements` preloaded. Confirm your organization has approved pg_search's AGPL or commercial license before deployment.
- Restart PostgreSQL after changing `shared_preload_libraries`; ensure the application database user can create the required extensions or have the database administrator create them.
- Existing PostgreSQL 16 volumes cannot be mounted directly by PostgreSQL 17. Migrate with `pg_dump`/restore or `pg_upgrade` during a planned maintenance window before switching images.

**Beat running duplicate schedules**
- Ensure only one `beat` replica is running.

**Old backend commands no longer work**
- Replace `backend` service references with `api`, for example `docker compose logs -f api`.
