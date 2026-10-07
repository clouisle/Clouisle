# Clouisle Helm Chart

This chart deploys Clouisle on Kubernetes with the current service model:

- `api`
- `worker`
- `sandbox-worker`
- `beat`
- `frontend`
- optional built-in ParadeDB PostgreSQL 17, Redis, and Qdrant

## Quick Start

```bash
INTERNAL_API_TOKEN="$(openssl rand -base64 32)"
helm upgrade --install clouisle deploy/helm/clouisle \
  --namespace clouisle \
  --create-namespace \
  --set-string secrets.values.INTERNAL_API_TOKEN="$INTERNAL_API_TOKEN"
unset INTERNAL_API_TOKEN
```

Check status:

```bash
kubectl -n clouisle get pods
kubectl -n clouisle get svc
kubectl -n clouisle get ingress
kubectl -n clouisle get pvc
```

## Production Install

Create a production Secret first:

```bash
kubectl create namespace clouisle
kubectl -n clouisle create secret generic clouisle-secret \
  --from-literal=SECRET_KEY='replace-with-strong-random-key' \
  --from-literal=POSTGRES_PASSWORD='replace-with-postgres-password' \
  --from-literal=REDIS_PASSWORD='replace-with-redis-password' \
  --from-literal=QDRANT_API_KEY='replace-with-qdrant-api-key' \
  --from-literal=INTERNAL_API_TOKEN="$(openssl rand -base64 32)"
```

Install with production values:

```bash
helm upgrade --install clouisle deploy/helm/clouisle \
  --namespace clouisle \
  --create-namespace \
  -f deploy/helm/clouisle/values-production.yaml
```

## External Infrastructure

Disable built-in PostgreSQL, Redis, and Qdrant when using managed services. External PostgreSQL must be PostgreSQL 17 or newer with pg_search 0.24.3 available and `pg_search,pg_stat_statements` preloaded. Confirm AGPL or commercial license approval for pg_search before deployment:

```bash
helm upgrade --install clouisle deploy/helm/clouisle \
  --namespace clouisle \
  --create-namespace \
  --set secrets.create=false \
  --set secrets.existingSecret=clouisle-secret \
  --set postgresql.enabled=false \
  --set postgresql.external.host=postgres.example.internal \
  --set redis.enabled=false \
  --set redis.external.host=redis.example.internal \
  --set qdrant.enabled=false \
  --set qdrant.external.url=https://qdrant.example.internal
```

## Important Values

| Value | Default | Description |
|-------|---------|-------------|
| `images.backend.repository` | `registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-backend` | API, worker, and beat image |
| `images.sandboxWorker.repository` | `registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-sandbox-worker` | Sandbox worker image |
| `images.frontend.repository` | `registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-frontend` | Frontend image |
| `config.API_BASE_URL` | `http://api:8000` | Internal API URL |
| `config.API_INTERNAL_BASE_URL` | `http://api:8000` | Worker-to-API internal upload gateway URL |
| `config.SANDBOX_ARTIFACT_UPLOAD_BASE_URL` | `http://api:8000` | Internal artifact upload API URL |
| `secrets.create` | `true` | Create a Secret from values |
| `secrets.existingSecret` | empty | Existing Secret for production |
| `secrets.values.INTERNAL_API_TOKEN` | required | Shared token for the internal upload gateway; set a unique value when chart-managed Secrets are enabled |
| `uploads.accessModes` | `ReadWriteMany` | Shared uploads PVC mode |
| `postgresql.enabled` | `true` | Deploy built-in ParadeDB PostgreSQL 17 with pg_search 0.24.3 |
| `postgresql.external.host` | empty | External PG17+ host with pg_search 0.24.3 preloaded when built-in mode is disabled |
| `redis.enabled` | `true` | Deploy built-in Redis |
| `qdrant.enabled` | `true` | Deploy built-in Qdrant 1.18.3 |
| `sandboxWorker.nodeSelector` | `{}` | Eligible sandbox nodes; one DaemonSet worker per node |
| `sandboxWorker.tolerations` | `[]` | Additional tolerations for dedicated sandbox nodes |
| `sandboxWorker.localDataPath` | empty | Exclusive node-local data path; defaults to `/var/lib/clouisle/<namespace>/<release>/sandbox` |

## PostgreSQL Upgrade and Licensing

The built-in image defaults to `registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-postgres-pg-search:0.24.3-pg17-alpine1`, built from `deploy/postgres/Dockerfile`. Override `postgresql.image.repository` when mirroring it to another cluster registry. This Alpine/musl port is maintained by Clouisle; every Alpine, PostgreSQL, Rust, pgrx, or pg_search update requires full amd64 and arm64 qualification. It preloads `pg_search,pg_stat_statements` with `pg_stat_statements.track=all`. External PostgreSQL must be PostgreSQL 17 or newer with pg_search 0.24.3 installed and the same libraries preloaded. Confirm your organization has approved pg_search's AGPL or commercial license before deployment.

Existing PostgreSQL 16 volumes cannot be mounted directly by PostgreSQL 17. Migrate with `pg_dump`/restore or `pg_upgrade` during a planned maintenance window before enabling the PG17 deployment.

## Storage

`api` alone mounts the `uploads` PVC at `/app/uploads`. `worker` and `sandbox-worker` read authorized documents/attachments through the authenticated internal upload gateway, and `sandbox-worker` uploads artifacts through the API.

Local upload storage needs a `ReadWriteMany` capable StorageClass, such as NFS, EFS, or CephFS, only when scaling `api` beyond one replica. With `ReadWriteOnce`, keep `api` at one replica; workers remain independently scalable.

Sandbox workers run as a DaemonSet with one isolated hostPath disk per eligible node. Worker/storage IDs are generated once on the disk sentinel; each supervised Celery child gets a fresh instance ID. Do not share `sandboxWorker.localDataPath` across installations or set a single global worker ID. Pod reconstruction on the same node and child-process restarts retain workspaces, checkpoints and caches. Restrict eligibility using `sandboxWorker.nodeSelector` (merged with the global selector), and use `sandboxWorker.tolerations` for dedicated tainted nodes. Label one node for single-node capacity, or several for multi-node capacity; `sandboxWorker.replicas` is no longer used.

The hostPath must be writable by the configured worker UID. Restricted Pod Security admission may reject hostPath, `SYS_ADMIN`, `SETFCAP`, `NET_ADMIN` or the unconfined seccomp profile; run sandbox capacity only on trusted nodes with the required permissions. Node/disk loss does not preserve files: after bounded original-disk recovery, sessions may move to a prepared fresh workspace with an explicit workspace-loss notice. No distributed sandbox storage is introduced. An unavailable sole eligible node means no ready sandbox capacity. See [deployment recovery guidance](../../README.md#sandbox-local-persistence-and-recovery).

`config.SANDBOX_WORKSPACE_ROOT` is the common virtual path for API, Agent workers and sandbox workers. Its default is `/var/lib/clouisle/sandbox/jobs`; checkpoints and the sandbox data mount derive from the same parent. Only the sandbox DaemonSet mounts retained physical data. Change the path in `config`, not `extraEnv`, so caller-generated commands and worker paths stay aligned without sharing any physical disk.

## Beat Replica Safety

`beat.replicas` must remain `1`. The chart fails rendering if this value is changed to avoid duplicate scheduled tasks.

## Validation

```bash
helm lint deploy/helm/clouisle \
  --set-string secrets.values.INTERNAL_API_TOKEN=lint-only-token
helm template clouisle deploy/helm/clouisle --namespace clouisle --create-namespace \
  --set-string secrets.values.INTERNAL_API_TOKEN=lint-only-token
helm template clouisle deploy/helm/clouisle --namespace clouisle --create-namespace \
  -f deploy/helm/clouisle/values-production.yaml
helm template clouisle deploy/helm/clouisle --namespace clouisle --create-namespace \
  --set secrets.create=false --set secrets.existingSecret=clouisle-secret
helm template clouisle deploy/helm/clouisle --namespace clouisle --create-namespace \
  --set secrets.create=false --set secrets.existingSecret=clouisle-secret \
  | kubectl apply --dry-run=client -f -
```

## Upgrade and Rollback

```bash
helm upgrade clouisle deploy/helm/clouisle \
  --namespace clouisle \
  --set images.backend.tag=0.1.1 \
  --set images.sandboxWorker.tag=0.1.1 \
  --set images.frontend.tag=0.1.1

helm rollback clouisle 1 --namespace clouisle
```
