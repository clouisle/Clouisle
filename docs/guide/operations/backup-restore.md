# Backup and Restore

Back up the data stores that contain application state and verify a restore before relying on the backup.

## What to Back Up

1. **PostgreSQL**: users, teams, agents, workflows, knowledge-base metadata, conversations, and settings.
2. **Qdrant**: vector collections and their snapshots.
3. **Uploads**: files in the Compose `api` service's `/app/uploads` volume or the Kubernetes `uploads-data` PVC.
4. **Redis**: optional cache and queue state. A Redis dump is useful for planned recovery, but queued work can be recreated.
5. **Configuration and secrets**: store `.env`/Secret-manager records separately and securely; never put plaintext secrets in a backup archive shared broadly.

## Docker Compose Backup

Run these commands from the directory containing the supplied `docker-compose.yml` and `.env`. `-T` is required for cron/non-interactive runs.

```bash
# This is an online, best-effort multi-store backup, not a transactionally
# consistent full snapshot; coordinate downtime separately when strict
# cross-store consistency is required.
docker compose stop worker sandbox-worker beat

# PostgreSQL custom-format dump
docker compose exec -T db pg_dump -U "${POSTGRES_USER:-postgres}" -Fc "${POSTGRES_DB:-clouisle}" > "postgres_$(date +%Y%m%d_%H%M%S).dump"

# Redis is optional. Authenticate when REDIS_PASSWORD is set.
docker compose exec -T redis sh -c 'redis-cli ${REDIS_PASSWORD:+-a "$REDIS_PASSWORD"} --rdb -' > "redis_$(date +%Y%m%d_%H%M%S).rdb"

# Uploads are mounted only in api; stream the volume without assuming a Docker volume name.
docker compose exec -T api tar -czf - -C /app uploads > "uploads_$(date +%Y%m%d_%H%M%S).tar.gz"
```

For Qdrant, create and download a snapshot through its API for every existing collection. The supplied Compose image is `qdrant/qdrant:v1.18.3`; keep recovery on a Qdrant version with compatible snapshot API semantics. Before any Qdrant API command, export `QDRANT_API_KEY` in the invoking shell from the protected deployment `.env` or Kubernetes Secret when authentication is enabled; Docker Compose does not export `.env` values into your shell.

The snippets default to `http://localhost:6333`, which works only while the Qdrant host-port mapping is published. If production hardening removed that mapping, temporarily bind Qdrant to `127.0.0.1:6333:6333` and recreate the service, or run the commands from a network-attached helper; remove the temporary host mapping afterward.

```bash
QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
QDRANT_AUTH=()
if [ -n "${QDRANT_API_KEY:-}" ]; then
  QDRANT_AUTH=(--header "api-key: $QDRANT_API_KEY")
fi

# List every current collection. Set COLLECTION to one returned name, then
# repeat the create/list/download commands for every name.
curl --fail "${QDRANT_URL}/collections" "${QDRANT_AUTH[@]}"
COLLECTION='replace-with-a-name-returned-above'

# Create a collection snapshot.
curl --fail --request POST "${QDRANT_URL}/collections/${COLLECTION}/snapshots" \
  "${QDRANT_AUTH[@]}"
curl --fail "${QDRANT_URL}/collections/${COLLECTION}/snapshots" \
  "${QDRANT_AUTH[@]}"
SNAPSHOT_NAME='replace-with-the-name-returned-above'
curl --fail "${QDRANT_URL}/collections/${COLLECTION}/snapshots/${SNAPSHOT_NAME}" \
  "${QDRANT_AUTH[@]}" \
  --output "${COLLECTION}_${SNAPSHOT_NAME}.snapshot"
```
Repeat this sequence for every returned collection. Clouisle commonly creates `kb_dim_<dimension>` for knowledge-base vectors and `memory_entities_dim_<dimension>` for memory vectors when those features have been used.


Start the stopped workers after all backup commands complete:

```bash
docker compose start worker sandbox-worker beat
```

## Kubernetes Backup

The supplied manifest uses namespace `clouisle`, StatefulSets `postgres` and `qdrant`, and an `uploads-data` PVC mounted by `api`. Use a backup destination provided by your cluster (object storage, a backup PVC, or a CSI snapshot); the manifest does **not** declare a generic `backup-pvc`.

```bash
# PostgreSQL; keep stdout available for the dump.
kubectl -n clouisle exec -i statefulset/postgres -- pg_dump -U postgres -Fc clouisle > postgres.dump

# Uploads; stream the mounted PVC through an api pod.
kubectl -n clouisle exec -i deployment/api -- tar -czf - -C /app uploads > uploads.tar.gz

# Qdrant images are not required to contain curl. Forward the Qdrant service in one terminal,
# then run the snapshot API commands from the other shell using QDRANT_URL=http://127.0.0.1:6333.
kubectl -n clouisle port-forward statefulset/qdrant 6333:6333
```

## Restore

Keep API and workers stopped while restoring PostgreSQL and Qdrant. Leave the database and Qdrant services running, but do not start application services until both stores are restored:

```bash
# Compose example
docker compose stop api worker sandbox-worker beat
docker compose exec -T db pg_restore -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-clouisle}" --clean --if-exists < postgres.dump
```

For Kubernetes:

```bash
kubectl -n clouisle scale deployment api worker sandbox-worker beat --replicas=0
kubectl -n clouisle exec -i statefulset/postgres -- pg_restore -U postgres -d clouisle --clean --if-exists < postgres.dump
```

Restore the Qdrant snapshot for every collection that was backed up before starting API, workers, or beat. The upload operation restores the collection; do not add an unsupported separate `/recover` request. Set `COLLECTION` and `SNAPSHOT_FILE` to a matching pair and repeat the upload for every backed-up collection.

```bash
QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
# Set these to one matching collection/snapshot pair; repeat for every collection.
COLLECTION='replace-with-a-backed-up-collection-name'
SNAPSHOT_FILE='replace-with-the-matching-snapshot.snapshot'
QDRANT_AUTH=()
if [ -n "${QDRANT_API_KEY:-}" ]; then
  QDRANT_AUTH=(--header "api-key: $QDRANT_API_KEY")
fi

curl --fail --request POST \
  "${QDRANT_URL}/collections/${COLLECTION}/snapshots/upload" \
  "${QDRANT_AUTH[@]}" \
  --form "snapshot=@${SNAPSHOT_FILE}"
```

After PostgreSQL and Qdrant are restored, start only API to restore the uploads archive, then restore the application workload replica counts. The supplied manifest uses `api=2`, `worker=2`, `sandbox-worker=1`, and `beat=1`; adjust these values if your deployment was scaled differently.

```bash
# Compose
docker compose start api
docker compose exec -T api tar -xzf - -C /app < uploads.tar.gz
docker compose start worker sandbox-worker beat

# Kubernetes
kubectl -n clouisle scale deployment api --replicas=2
kubectl -n clouisle rollout status deployment/api
kubectl -n clouisle exec -i deployment/api -- tar -xzf - -C /app < uploads.tar.gz
kubectl -n clouisle scale deployment worker --replicas=2
kubectl -n clouisle scale deployment sandbox-worker --replicas=1
kubectl -n clouisle scale deployment beat --replicas=1
```

After restoring, verify `/api/v1/health`, login, a knowledge-base search, an upload, and a representative workflow. Redis queue state is optional; if it is not restored, re-submit jobs that were pending at the time of failure.

## Automated Backups

Schedule the Compose commands with host cron, or run equivalent commands in a Kubernetes CronJob that mounts an explicitly provisioned backup destination and reads credentials from a Secret. Keep encrypted, off-site copies, define retention, and perform regular scratch-environment restore tests.

See [Deployment Guide](../deployment/DEPLOYMENT.md) and [Backup and Recovery](../deployment/backup-recovery.md) for deployment-specific details.
