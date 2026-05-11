# Upgrading Clouisle

Version upgrade procedures.

## Pre-Upgrade Checklist

- [ ] Backup all data (PostgreSQL, Qdrant, uploads)
- [ ] Review changelog for breaking changes
- [ ] Test upgrade in staging environment
- [ ] Schedule maintenance window
- [ ] Notify users of downtime

## Docker Compose Upgrade

```bash
cd deploy

# 1. Pull latest code
git pull

# 2. Rebuild images
docker compose build

# 3. Stop services
docker compose down

# 4. Start services
docker compose up -d

# 5. Verify
docker compose ps
docker compose logs --tail=50 api
```

## Kubernetes Upgrade

```bash
# 1. Build and push new images
docker build -t registry.example.com/clouisle/api:v2.0.0 .
docker push registry.example.com/clouisle/api:v2.0.0

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

**Note**: This is a placeholder document. Please update with detailed content.

For more information, see the [main documentation](../README.md).
