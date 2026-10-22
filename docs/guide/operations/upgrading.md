# Upgrading Clouisle

Use a maintenance window for upgrades. The supplied Compose file references prebuilt images and has no `build:` blocks; it does not provide a rolling-update guarantee. Pin an immutable image tag or digest for production rather than relying on `latest`.

## Pre-Upgrade Checklist

- [ ] Back up PostgreSQL, Qdrant snapshots, and uploads; decide whether Redis queue state is needed.
- [ ] Review the release notes for breaking changes and configuration changes.
- [ ] Test the exact image tags in staging.
- [ ] Confirm the rollback image tag/digest and available backup restore path.
- [ ] Schedule and announce the maintenance window.

## WeChat polling cutover

This release replaces all-bindings polling with bounded batches on `default`, consumed by ordinary workers. Stop Beat first. If an older dedicated polling worker exists, drain its `wechat_poll` backlog before stopping it; otherwise wait for its 90-second claims to expire and let the new dispatcher recover them. Start the matching API for schema upgrades, then ordinary workers, then Beat. Polling shares worker slots with other tasks; no dedicated service or compatibility queue consumer is deployed.

Agent wakeups now use `app.tasks.wechat_agent.process_claimed_binding_task` with a required ownership token. The former `process_binding_task` message name is not registered, so old one-argument messages cannot execute under the new protocol. Restart all producers and workers together. Old deliveries may be logged as unregistered and discarded; pending receipts and unsent replies remain in PostgreSQL and the enabled recovery task publishes fresh owned wakeups. Do not purge shared Redis queues.

Before enabling WeChat at scale, install these PostgreSQL indexes in autocommit mode (each statement outside a transaction). They are intentionally not part of API startup: concurrent index builds may take longer than startup migration deadlines. `IF NOT EXISTS` does not repair a failed/invalid index; check index validity and retry failed builds before rollout.

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS wechat_poll_due_idx
ON wechat_knowledge_bindings (poll_next_at, id)
WHERE status = 'connected' AND purpose IN ('agent', 'knowledge_collection') AND token <> '';
CREATE INDEX CONCURRENTLY IF NOT EXISTS wechat_agent_recovery_due_idx
ON wechat_knowledge_bindings (agent_recovery_at, id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS wechat_agent_receipt_pending_idx
ON wechat_agent_receipts (binding_id) WHERE status IN ('pending', 'submitted');
CREATE INDEX CONCURRENTLY IF NOT EXISTS wechat_agent_delivery_pending_idx
ON wechat_agent_deliveries (receipt_id) WHERE status IN ('pending', 'sending');
```

Verify the due-binding and recovery queries with `EXPLAIN (ANALYZE, BUFFERS)` on representative data. Match polling limits across replicas; raising replicas does not raise the global `WECHAT_POLL_MAX_BATCHES` cap. Validate new-message intake, empty-message behavior, Agent replies, feature disable/re-enable and worker-loss recovery before reopening traffic.

## Docker Compose Upgrade

Run from the installation directory that contains the active `docker-compose.yml` and `.env` (for the installer default, `/opt/clouisle`). The commands below replace `IMAGE_TAG` in your Compose/environment configuration with the tag you have published; they do not build images locally.

```bash
cd /opt/clouisle  # replace with your installation directory
git pull          # only if this directory is a source checkout; installer installs may omit this

# Pull the pinned images and recreate services. This is a stop/recreate operation, not rolling restart.
docker compose pull
docker compose up -d --force-recreate --remove-orphans
# Verify every supplied service and the API health endpoint
docker compose ps
docker compose logs --tail=50 api worker sandbox-worker beat frontend
curl --fail http://localhost:8000/api/v1/health
```

If you build your own images, build from the **repository root**, tag all three images with the same immutable release tag, push them, then update the Compose image references before running `docker compose pull`:

```bash
# Run from the repository root; REGISTRY and IMAGE_TAG are examples to replace.
REGISTRY=registry.example.com/clouisle
IMAGE_TAG=vX.Y.Z
docker build -f deploy/dockerfiles/backend.Dockerfile -t "$REGISTRY/clouisle-backend:$IMAGE_TAG" .
docker build -f deploy/dockerfiles/frontend.Dockerfile -t "$REGISTRY/clouisle-frontend:$IMAGE_TAG" .
docker build -f deploy/dockerfiles/sandbox-worker.Dockerfile -t "$REGISTRY/clouisle-sandbox-worker:$IMAGE_TAG" .
docker push "$REGISTRY/clouisle-backend:$IMAGE_TAG"
docker push "$REGISTRY/clouisle-frontend:$IMAGE_TAG"
docker push "$REGISTRY/clouisle-sandbox-worker:$IMAGE_TAG"
```

## Kubernetes Upgrade

The supplied Kubernetes deployment uses namespace `clouisle`, with `api`, `worker`, `beat`, and `frontend` Deployments plus a `sandbox-worker` DaemonSet (one pod per eligible node). Build from the repository root, publish immutable tags, update application workloads, and watch each rollout:

For an existing installation that still has the previous `sandbox-worker` Deployment, drain its work and remove that Deployment before applying the updated manifest; do not run both controllers against the same local sandbox path. Apply `deploy/k8s/clouisle.yaml` to create the DaemonSet, then run the image update commands below.

```bash
# Generic registry/tag example: replace REGISTRY and IMAGE_TAG with real values.
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
kubectl -n clouisle set image daemonset/sandbox-worker sandbox-worker="$REGISTRY/clouisle-sandbox-worker:$IMAGE_TAG"
kubectl -n clouisle set image deployment/beat beat="$REGISTRY/clouisle-backend:$IMAGE_TAG"
kubectl -n clouisle set image deployment/frontend frontend="$REGISTRY/clouisle-frontend:$IMAGE_TAG"

kubectl -n clouisle rollout status deployment/api
kubectl -n clouisle rollout status deployment/worker
kubectl -n clouisle rollout status daemonset/sandbox-worker
kubectl -n clouisle rollout status deployment/beat
kubectl -n clouisle rollout status deployment/frontend
```

When using Helm, update the backend, sandbox-worker, and frontend tags in a values file and run `helm upgrade` with `--namespace clouisle`; keep the existing Secret and all required secret keys. Do not use a routine Alembic command: Clouisle initializes/updates its schema at backend startup through Tortoise ORM (`init_db`).

## Rollback

```bash
# Compose: restore the previous image tag/digest in the active Compose configuration, then recreate.
docker compose pull
docker compose up -d --force-recreate

# Kubernetes: undo each application Deployment in the clouisle namespace.
kubectl -n clouisle rollout undo deployment/api
kubectl -n clouisle rollout undo deployment/worker
kubectl -n clouisle rollout undo daemonset/sandbox-worker
kubectl -n clouisle rollout undo deployment/beat
kubectl -n clouisle rollout undo deployment/frontend
```

Do not roll back application code across an incompatible data/schema change without following the release's documented recovery procedure.

## Post-Upgrade Verification

- [ ] All infrastructure and application services are running.
- [ ] `GET /api/v1/health` succeeds through the public proxy.
- [ ] Login, agent chat/streaming, file upload, knowledge-base search, and workflow execution work.
- [ ] Worker, sandbox-worker, and beat logs are free of startup errors; beat remains exactly one replica.
- [ ] Backup and monitoring jobs continue to run.
