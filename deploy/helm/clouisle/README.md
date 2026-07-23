# Clouisle Helm Chart

This chart deploys Clouisle on Kubernetes with the current service model:

- `api`
- `worker`
- `sandbox-worker`
- `beat`
- `frontend`
- optional built-in `postgres`, `redis`, `qdrant`, and `opensearch`

## Quick Start

```bash
helm lint deploy/helm/clouisle
helm upgrade --install clouisle deploy/helm/clouisle \
  --namespace clouisle \
  --create-namespace
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
  --from-literal=OPENSEARCH_PASSWORD='replace-with-a-strong-opensearch-password'
```

Install with production values:

```bash
helm upgrade --install clouisle deploy/helm/clouisle \
  --namespace clouisle \
  --create-namespace \
  -f deploy/helm/clouisle/values-production.yaml
```

## External Infrastructure

Disable built-in PostgreSQL, Redis, Qdrant, and OpenSearch when using managed services. The existing Secret must still contain `OPENSEARCH_PASSWORD` for authenticated OpenSearch:

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
  --set qdrant.external.url=https://qdrant.example.internal \
  --set opensearch.enabled=false \
  --set opensearch.external.url=https://opensearch.example.internal:9200 \
  --set config.OPENSEARCH_USERNAME=clouisle
```

## Important Values

| Value | Default | Description |
|-------|---------|-------------|
| `images.backend.repository` | `clouisle-backend` | API, worker, and beat image |
| `images.sandboxWorker.repository` | `clouisle-sandbox-worker` | Sandbox worker image |
| `images.frontend.repository` | `clouisle-frontend` | Frontend image |
| `config.API_BASE_URL` | `http://api:8000` | Internal API URL |
| `config.SANDBOX_ARTIFACT_UPLOAD_BASE_URL` | `http://api:8000` | Internal artifact upload API URL |
| `secrets.create` | `true` | Create a Secret from values |
| `secrets.existingSecret` | empty | Existing Secret for production |
| `uploads.accessModes` | `ReadWriteMany` | Shared uploads PVC mode |
| `postgresql.enabled` | `true` | Deploy built-in PostgreSQL |
| `redis.enabled` | `true` | Deploy built-in Redis |
| `qdrant.enabled` | `true` | Deploy built-in Qdrant 1.18.3 |
| `opensearch.enabled` | `true` | Deploy built-in single-node OpenSearch 3.7.0 |
| `opensearch.external.url` | empty | Required OpenSearch URL when built-in mode is disabled |

## Storage

`api`, `worker`, and `sandbox-worker` share the `uploads` PVC at `/app/uploads`.

Production multi-replica deployments require a `ReadWriteMany` capable StorageClass, such as NFS, EFS, or CephFS. If your cluster does not support RWX storage, keep `api`, `worker`, and `sandbox-worker` single-replica or move uploads/artifacts to object storage.

## Beat Replica Safety

`beat.replicas` must remain `1`. The chart fails rendering if this value is changed to avoid duplicate scheduled tasks.

## Validation

```bash
helm lint deploy/helm/clouisle
helm template clouisle deploy/helm/clouisle --namespace clouisle --create-namespace
helm template clouisle deploy/helm/clouisle --namespace clouisle --create-namespace \
  -f deploy/helm/clouisle/values-production.yaml
helm template clouisle deploy/helm/clouisle --namespace clouisle --create-namespace \
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
