# Upgrading Clouisle

Version upgrade procedures.

## Pre-Upgrade Checklist

- [ ] Backup all data (PostgreSQL, Qdrant, uploads)
- [ ] Review changelog for breaking changes
- [ ] Test upgrade in staging environment
- [ ] Schedule maintenance window
- [ ] Notify users of downtime

## Docker Compose Upgrade

The compose files (`deploy/docker-compose.yml`) reference prebuilt images (e.g. `registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-backend:latest`) and have no `build:` sections, so upgrades are done by pulling the new images.

```bash
cd deploy

# 1. Pull latest code
git pull

# 2. Pull new images
docker compose pull

# 3. Stop services
docker compose down

# 4. Start services
docker compose up -d

# 5. Verify
docker compose ps
docker compose logs --tail=50 api
```

If you maintain your own images, build them from the per-service Dockerfiles and push to your registry:

```bash
docker build -f deploy/dockerfiles/backend.Dockerfile -t registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-backend:latest .
docker build -f deploy/dockerfiles/frontend.Dockerfile -t registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-frontend:latest .
docker build -f deploy/dockerfiles/sandbox-worker.Dockerfile -t registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-sandbox-worker:latest .
```

## Kubernetes Upgrade

```bash
# 1. Build and push new images
docker build -f deploy/dockerfiles/backend.Dockerfile -t registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-backend:latest .
docker push registry.cn-shanghai.aliyuncs.com/clouisle/clouisle-backend:latest

# 2. Update manifests
kubectl apply -f deploy/k8s/clouisle.yaml

# 3. Monitor rollout
kubectl rollout status deployment/api
```

## Rollback Procedures

If upgrade fails:

```bash
# Docker Compose
docker compose down
git checkout previous-version
docker compose up -d

# Kubernetes
kubectl rollout undo deployment/api
```

## Post-Upgrade Verification

- [ ] Check all services are running
- [ ] Test login functionality
- [ ] Test agent chat
- [ ] Test workflow execution
- [ ] Review error logs

---

For more information, see the [main documentation](../README.md).
