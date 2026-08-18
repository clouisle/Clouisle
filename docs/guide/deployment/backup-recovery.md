# Backup and Recovery

This guide covers backup and recovery procedures for Clouisle.

## Overview

Backup and recovery ensures:

- **Data protection**: Prevent data loss
- **Disaster recovery**: Restore after failures
- **Business continuity**: Minimize downtime
- **Compliance**: Meet regulatory requirements
- **Version control**: Restore to specific points in time

## What to Backup

### Critical Data

**Database (PostgreSQL):**
- User accounts and profiles
- Teams and memberships
- Agents and configurations
- Workflows and executions
- Knowledge bases metadata
- Conversations and messages
- API keys and settings
- Audit logs

**Vector Database (Qdrant):**
- Document embeddings
- Vector collections
- Search indexes

**File Storage:**
- Uploaded documents
- User avatars
- Agent icons
- Exported data

**Configuration:**
- Environment variables
- Application settings
- SSL certificates
- Secrets

## Backup Strategy

### Backup Types

**Full Backup:**
- Complete copy of all data
- Largest size, longest time
- Recommended: Weekly

**Incremental Backup:**
- Only changed data since last backup
- Smaller size, faster
- Recommended: Daily

**Differential Backup:**
- Changed data since last full backup
- Medium size and time
- Recommended: Daily

### Backup Schedule

**Example operator schedule (external design only; not a shipped WAL/PITR capability):**
```yaml
Full Backup:
  Frequency: Weekly
  Day: Sunday
  Time: 2:00 AM
  Retention: 4 weeks

Incremental Backup:
  Frequency: Daily
  Time: 2:00 AM
  Retention: 7 days

WAL/PITR:
  Frequency: Operator-defined
  Retention: Operator-defined
```

WAL archiving and point-in-time recovery (PITR) require a separately designed and operated PostgreSQL process; they are not provided by this Compose deployment.

## Database Backup

### PostgreSQL Backup

**Manual Backup:**

```bash
# Full database backup
docker compose exec db pg_dump -U postgres clouisle > backup_$(date +%Y%m%d_%H%M%S).sql

# Compressed backup
docker compose exec db pg_dump -U postgres clouisle | gzip > backup_$(date +%Y%m%d_%H%M%S).sql.gz

# Custom format (recommended)
docker compose exec db pg_dump -U postgres -Fc clouisle > backup_$(date +%Y%m%d_%H%M%S).dump
```

**Automated Backup Script:**

```bash
#!/bin/bash
# backup-postgres.sh

# Configuration
BACKUP_DIR="/backups/postgres"
RETENTION_DAYS=30
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/clouisle_$TIMESTAMP.dump"

# Create backup directory
mkdir -p $BACKUP_DIR

# Perform backup
docker compose exec -T db pg_dump -U postgres -Fc clouisle > $BACKUP_FILE

# Compress backup
gzip $BACKUP_FILE

# Remove old backups
find $BACKUP_DIR -name "*.dump.gz" -mtime +$RETENTION_DAYS -delete

# Log backup
echo "$(date): Backup completed: $BACKUP_FILE.gz" >> $BACKUP_DIR/backup.log

# Verify backup
if [ -f "$BACKUP_FILE.gz" ]; then
    echo "Backup successful"
    exit 0
else
    echo "Backup failed"
    exit 1
fi
```

**Schedule with Cron:**

```bash
# Edit crontab
crontab -e

# Add backup job (daily at 2 AM)
0 2 * * * /path/to/backup-postgres.sh
```

### PostgreSQL Restore

**Restore from Backup:**

```bash
# Stop application
docker compose stop api worker beat frontend

# Restore database
docker compose exec -T db pg_restore -U postgres -d clouisle -c < backup.dump

# Or from compressed backup
gunzip -c backup.dump.gz | docker compose exec -T db pg_restore -U postgres -d clouisle -c

# Restart application
docker compose start api worker beat frontend
```

**Restore to New Database:**

```bash
# Create new database
docker compose exec db createdb -U postgres clouisle_restored

# Restore to new database
docker compose exec -T db pg_restore -U postgres -d clouisle_restored < backup.dump

# Switch to restored database (update .env)
POSTGRES_DB=clouisle_restored
```

## Vector Database Backup

### Qdrant Backup
Qdrant snapshots are collection-scoped. Back up every collection returned by `GET /collections`; Clouisle commonly uses `kb_dim_<dimension>` for knowledge-base vectors and `memory_entities_dim_<dimension>` for memory vectors when those features have been used. Before any Qdrant API command, export `QDRANT_API_KEY` into the invoking shell or cron environment from the protected deployment `.env` or Kubernetes Secret when authentication is enabled; Docker Compose does not export `.env` values into the shell.

The snippets default to `http://localhost:6333`, which works only while the Qdrant host-port mapping is published. If production hardening removed that mapping, temporarily bind Qdrant to `127.0.0.1:6333:6333` and recreate the service, or run the commands from a network-attached helper; remove the temporary host mapping afterward.

**Create Snapshot:**

```bash
# The supplied Compose layout uses qdrant/qdrant:v1.18.3. Keep restore and
# backup operations on a Qdrant version with compatible snapshot API semantics.
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

# List snapshots and use the returned name in the download request.
curl --fail "${QDRANT_URL}/collections/${COLLECTION}/snapshots" \
  "${QDRANT_AUTH[@]}"
SNAPSHOT_NAME='replace-with-the-name-returned-above'
curl --fail "${QDRANT_URL}/collections/${COLLECTION}/snapshots/${SNAPSHOT_NAME}" \
  "${QDRANT_AUTH[@]}" \
  --output "${COLLECTION}_${SNAPSHOT_NAME}.snapshot"
```

**Automated Qdrant Backup:**

```bash
#!/bin/bash
# backup-qdrant.sh

BACKUP_DIR="/backups/qdrant"
QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
# When Qdrant authentication is enabled, inject QDRANT_API_KEY into this script's
# environment securely before it runs; Docker Compose does not export .env values.
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
QDRANT_AUTH=()
if [ -n "${QDRANT_API_KEY:-}" ]; then
  QDRANT_AUTH=(--header "api-key: $QDRANT_API_KEY")
fi

mkdir -p "$BACKUP_DIR"
collections=$(curl --fail --silent --show-error "${QDRANT_URL}/collections" \
  "${QDRANT_AUTH[@]}" | jq -r '.result.collections[].name')

for collection in $collections; do
  echo "Backing up collection: $collection"
  snapshot=$(curl --fail --silent --show-error --request POST \
    "${QDRANT_URL}/collections/${collection}/snapshots" \
    "${QDRANT_AUTH[@]}" | jq -r '.result.name')
  curl --fail --silent --show-error \
    "${QDRANT_URL}/collections/${collection}/snapshots/${snapshot}" \
    "${QDRANT_AUTH[@]}" \
    --output "$BACKUP_DIR/${collection}_${TIMESTAMP}.snapshot"
  curl --fail --silent --show-error --request DELETE \
    "${QDRANT_URL}/collections/${collection}/snapshots/${snapshot}" \
    "${QDRANT_AUTH[@]}"
done

echo "Qdrant backup completed"
```

### Qdrant Restore

Restore a collection snapshot using the snapshot upload operation supported by the target Qdrant version. The supplied Compose image is `qdrant/qdrant:v1.18.3`; do not substitute an endpoint from another Qdrant release without checking that release's snapshot API semantics. The upload operation restores the collection; there is no separate `/recover` command here. Set `COLLECTION` and `SNAPSHOT_FILE` to one matching pair and repeat the upload for every backed-up collection.

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


### Backup Configuration Files

```bash
#!/bin/bash
# backup-config.sh

COMPOSE_DIR="${COMPOSE_DIR:-$(pwd)}"
BACKUP_DIR="/backups/config"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
CONFIG_ITEMS=(docker-compose.yml .env)

mkdir -p "$BACKUP_DIR"
test -f "$COMPOSE_DIR/docker-compose.yml" || { echo "Missing docker-compose.yml" >&2; exit 1; }
test -f "$COMPOSE_DIR/.env" || { echo "Missing .env" >&2; exit 1; }

# The supplied layout has deploy/nginx/default.conf. Include it and
# deploy/nginx/certs only when an operator has actually provided them.
[ -f "$COMPOSE_DIR/nginx/default.conf" ] && CONFIG_ITEMS+=(nginx/default.conf)
[ -d "$COMPOSE_DIR/nginx/certs" ] && CONFIG_ITEMS+=(nginx/certs)

tar -czf "$BACKUP_DIR/config_$TIMESTAMP.tar.gz" \
  -C "$COMPOSE_DIR" "${CONFIG_ITEMS[@]}"

echo "Configuration backup completed"
```

### Restore Configuration

```bash
# Extract configuration into the directory used by Compose.
tar -xzf config_backup.tar.gz -C /path/to/clouisle/deploy
```

## File Storage Backup

### Backup Uploaded Files

**Manual Backup:**

```bash
# Backup uploads directory
tar -czf uploads_backup_$(date +%Y%m%d_%H%M%S).tar.gz /path/to/uploads

# Backup to remote location
rsync -avz /path/to/uploads/ user@backup-server:/backups/uploads/
```

**Automated File Backup:**

```bash
#!/bin/bash
# backup-files.sh

COMPOSE_DIR="${COMPOSE_DIR:-$(pwd)}"
COMPOSE_FILE="$COMPOSE_DIR/docker-compose.yml"
BACKUP_DIR="/backups/files"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/uploads_$TIMESTAMP.tar.gz"

mkdir -p "$BACKUP_DIR"

# Stream the api service's mounted uploads directory; do not assume a host
# path or a generated Docker volume name.
docker compose --project-directory "$COMPOSE_DIR" -f "$COMPOSE_FILE" \
  exec -T api tar -czf - -C /app uploads > "$BACKUP_FILE"

# This basic -name/-mtime form is supported by both GNU and BSD/macOS find.
find "$BACKUP_DIR" -name 'uploads_*.tar.gz' -mtime +30 -delete

echo "File backup completed: $BACKUP_FILE"
```
### Restore Files

```bash
# Extract backup
tar -xzf uploads_backup.tar.gz -C /

# Or to specific location
tar -xzf uploads_backup.tar.gz -C /restore/location
```

## Complete System Backup

### Full System Backup Script

```bash
#!/bin/bash
# full-backup.sh

BACKUP_ROOT="/backups"
COMPOSE_DIR="${COMPOSE_DIR:-$(pwd)}"
COMPOSE_FILE="$COMPOSE_DIR/docker-compose.yml"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="$BACKUP_ROOT/full_$TIMESTAMP"
ARCHIVE_PATH="$BACKUP_ROOT/full_backup_$TIMESTAMP.tar.gz"

compose() {
  docker compose --project-directory "$COMPOSE_DIR" -f "$COMPOSE_FILE" "$@"
}

mkdir -p "$BACKUP_DIR"
echo "Starting full system backup..."
compose stop sandbox-worker worker beat

echo "Backing up PostgreSQL..."
compose exec -T db pg_dump -U "${POSTGRES_USER:-postgres}" \
  -Fc "${POSTGRES_DB:-clouisle}" > "$BACKUP_DIR/postgres.dump"
gzip "$BACKUP_DIR/postgres.dump"

echo "Backing up Qdrant..."
QDRANT_CONTAINER="$(compose ps -q qdrant)"
test -n "$QDRANT_CONTAINER" || { echo "Qdrant container not found" >&2; exit 1; }
QDRANT_VOLUME="$(docker inspect "$QDRANT_CONTAINER" --format '{{range .Mounts}}{{if eq .Destination "/qdrant/storage"}}{{.Name}}{{end}}{{end}}')"
test -n "$QDRANT_VOLUME" || { echo "Qdrant volume not found" >&2; exit 1; }

mkdir -p "$BACKUP_DIR/qdrant"
docker run --rm -v "$QDRANT_VOLUME:/data:ro" -v "$BACKUP_DIR/qdrant:/backup" \
  alpine tar czf /backup/storage.tar.gz -C /data .

echo "Backing up Redis..."
compose exec -T redis sh -c 'redis-cli ${REDIS_PASSWORD:+-a "$REDIS_PASSWORD"} SAVE'
compose cp redis:/data/dump.rdb "$BACKUP_DIR/redis_dump.rdb"

echo "Backing up uploaded files..."
UPLOADS_CONTAINER="$(compose ps -q api)"
test -n "$UPLOADS_CONTAINER" || { echo "API container not found" >&2; exit 1; }
UPLOADS_VOLUME="$(docker inspect "$UPLOADS_CONTAINER" --format '{{range .Mounts}}{{if eq .Destination "/app/uploads"}}{{.Name}}{{end}}{{end}}')"
test -n "$UPLOADS_VOLUME" || { echo "Uploads volume not found" >&2; exit 1; }
docker run --rm -v "$UPLOADS_VOLUME:/data:ro" -v "$BACKUP_DIR:/backup" \
  alpine tar czf /backup/uploads.tar.gz -C /data .

echo "Backing up configuration..."
CONFIG_ITEMS=(docker-compose.yml .env)
test -f "$COMPOSE_DIR/docker-compose.yml" || { echo "Missing docker-compose.yml" >&2; exit 1; }
test -f "$COMPOSE_DIR/.env" || { echo "Missing .env" >&2; exit 1; }
[ -f "$COMPOSE_DIR/nginx/default.conf" ] && CONFIG_ITEMS+=(nginx/default.conf)
[ -d "$COMPOSE_DIR/nginx/certs" ] && CONFIG_ITEMS+=(nginx/certs)
tar -czf "$BACKUP_DIR/config.tar.gz" -C "$COMPOSE_DIR" "${CONFIG_ITEMS[@]}"

cat > "$BACKUP_DIR/manifest.txt" <<EOF
Backup Date: $(date)
Backup Type: Full System Backup
Components:
  - PostgreSQL: postgres.dump.gz
  - Qdrant: qdrant/storage.tar.gz
  - Redis: redis_dump.rdb
  - Files: uploads.tar.gz
  - Config: config.tar.gz
EOF

# Keep Compose operations independent of the shell's current directory.
tar -czf "$ARCHIVE_PATH" -C "$BACKUP_ROOT" "full_$TIMESTAMP"
rm -rf "$BACKUP_DIR"
compose start worker sandbox-worker beat

echo "Full backup completed: $ARCHIVE_PATH"
```

## Remote Backup

### Backup to S3

```bash
#!/bin/bash
# backup-to-s3.sh

S3_BUCKET="s3://your-bucket/clouisle-backups"
LOG_FILE=$(mktemp)
set -o pipefail


# Upload the exact archive path emitted by full-backup.sh; do not derive a
# second timestamp.
if ! ./full-backup.sh | tee "$LOG_FILE"; then
  rm -f "$LOG_FILE"
  exit 1
fi
ARCHIVE_PATH=$(sed -n 's/^Full backup completed: //p' "$LOG_FILE" | tail -n 1)
rm -f "$LOG_FILE"
test -n "$ARCHIVE_PATH"
ARCHIVE_NAME=$(basename "$ARCHIVE_PATH")

aws s3 cp "$ARCHIVE_PATH" "$S3_BUCKET/$ARCHIVE_NAME" \
  --storage-class STANDARD_IA
rm "$ARCHIVE_PATH"
echo "Backup uploaded to S3"
```

### Backup to Azure Blob Storage

```bash
#!/bin/bash
# backup-to-azure.sh

CONTAINER="clouisle-backups"
LOG_FILE=$(mktemp)
set -o pipefail

if ! ./full-backup.sh | tee "$LOG_FILE"; then
  rm -f "$LOG_FILE"
  exit 1
fi
ARCHIVE_PATH=$(sed -n 's/^Full backup completed: //p' "$LOG_FILE" | tail -n 1)
rm -f "$LOG_FILE"
test -n "$ARCHIVE_PATH"
ARCHIVE_NAME=$(basename "$ARCHIVE_PATH")

az storage blob upload \
  --account-name your-account \
  --container-name "$CONTAINER" \
  --name "$ARCHIVE_NAME" \
  --file "$ARCHIVE_PATH"
echo "Backup uploaded to Azure"
```



## Disaster Recovery

### Recovery Procedures

**Complete System Recovery:**

1. **Prepare the environment and unpack the full archive:**
   ```bash
   # Install Docker and Docker Compose, then clone the repository.
   git clone https://github.com/clouisle/Clouisle.git /opt/clouisle
   RESTORE_ROOT=/tmp/clouisle-restore
   mkdir -p "$RESTORE_ROOT"
   tar -xzf /backups/full_backup_TIMESTAMP.tar.gz -C "$RESTORE_ROOT"
   BACKUP_DIR="$RESTORE_ROOT/full_TIMESTAMP"

   # The full-backup script stores .env and docker-compose.yml in config.tar.gz.
   mkdir -p /opt/clouisle/deploy
   tar -xzf "$BACKUP_DIR/config.tar.gz" -C /opt/clouisle/deploy
   cd /opt/clouisle/deploy
   ```

2. **Start infrastructure only:**
   ```bash
   docker compose up -d db redis qdrant
   docker compose ps
   ```

3. **Restore PostgreSQL:**
   ```bash
   gunzip -c "$BACKUP_DIR/postgres.dump.gz" \
     | docker compose exec -T db pg_restore -U "${POSTGRES_USER:-postgres}" \
         -d "${POSTGRES_DB:-clouisle}" --clean --if-exists
   ```

4. **Restore Qdrant storage:**
   ```bash
   # Discover the volume while qdrant is running; compose ps -q may be empty
   # after the service is stopped.
   QDRANT_CONTAINER="$(docker compose ps -q qdrant)"
   QDRANT_VOLUME="$(docker inspect "$QDRANT_CONTAINER" --format '{{range .Mounts}}{{if eq .Destination "/qdrant/storage"}}{{.Name}}{{end}}{{end}}')"
   test -n "$QDRANT_VOLUME"
   docker compose stop qdrant
   docker run --rm -v "$QDRANT_VOLUME:/data" -v "$BACKUP_DIR/qdrant:/backup" \
     alpine tar xzf /backup/storage.tar.gz -C /data
   docker compose start qdrant
   ```


5. **Restore uploads:**
   ```bash
   # The API must be running because it owns the uploads volume.
   docker compose up -d api
   docker compose exec -T api tar -xzf - -C /app/uploads < "$BACKUP_DIR/uploads.tar.gz"
   ```

6. **Start the remaining application services:**
   ```bash
   docker compose up -d worker sandbox-worker beat frontend
   docker compose ps
   ```

7. **Verify recovery:**
   ```bash
   curl --fail http://localhost:8000/api/v1/health
   # Test login, a knowledge-base search, an upload, and a representative workflow.
   ```

### Recovery Time Objective (RTO)

The following figures are **external operator targets**, not shipped service guarantees. Set them against your infrastructure, backup destination, and restore test results.

| Component | RTO | Notes |
|-----------|-----|-------|
| Database | 30 minutes | Restore from backup |
| Vector DB | 1 hour | Restore embeddings |
| Files | 30 minutes | Restore from backup |
| Application | 15 minutes | Redeploy containers |
| **Total** | **2 hours** | Complete recovery |

### Recovery Point Objective (RPO)

The following figures are **external operator targets**, not shipped backup or WAL/PITR capabilities:

| Data Type | RPO | Backup Frequency |
|-----------|-----|------------------|
| Database | 24 hours | Daily |
| Files | 24 hours | Daily |
| Vectors | 24 hours | Daily |
| Logs | 1 hour | Continuous only if separately implemented |

## Backup Verification

### Test Backup Integrity

```bash
#!/bin/bash
# verify-backup.sh

BACKUP_FILE=$1

echo "Verifying backup: $BACKUP_FILE"

# 1. Check file exists
if [ ! -f "$BACKUP_FILE" ]; then
    echo "ERROR: Backup file not found"
    exit 1
fi

# BSD/macOS stat uses -f%z; GNU/Linux stat uses -c%s.
SIZE=$(stat -f%z "$BACKUP_FILE" 2>/dev/null || stat -c%s "$BACKUP_FILE")
if [ $SIZE -lt 1000000 ]; then
    echo "WARNING: Backup file seems too small"
fi

# 3. Test archive integrity
if [[ $BACKUP_FILE == *.gz ]]; then
    gunzip -t "$BACKUP_FILE"
    if [ $? -ne 0 ]; then
        echo "ERROR: Archive is corrupted"
        exit 1
    fi
fi

# 4. Test database backup
if [[ $BACKUP_FILE == *.dump* ]]; then
    # Create test database
    docker compose exec db createdb -U postgres test_restore

    # Try to restore
    gunzip -c "$BACKUP_FILE" | docker compose exec -T db pg_restore -U postgres -d test_restore

    if [ $? -eq 0 ]; then
        echo "Database backup is valid"
        docker compose exec db dropdb -U postgres test_restore
    else
        echo "ERROR: Database backup is invalid"
        exit 1
    fi
fi

echo "Backup verification completed successfully"
```

### Automated Backup Testing

```bash
#!/bin/bash
# test-restore.sh

# Use a scratch database on the running db service (there is no docker-compose.test.yml)
docker compose exec db createdb -U postgres restore_test

# Restore latest backup
LATEST_BACKUP=$(ls -t /backups/postgres/*.dump.gz | head -1)
gunzip -c $LATEST_BACKUP | docker compose exec -T db pg_restore -U postgres -d restore_test

# Run smoke checks
docker compose exec -T db psql -U postgres -d restore_test -c "SELECT count(*) FROM users;"
curl -fsS http://localhost:8000/api/v1/health

# Cleanup
docker compose exec db dropdb -U postgres restore_test

echo "Restore test completed"
```

## Backup Monitoring

### Monitor Backup Status

```bash
#!/bin/bash
# check-backups.sh

BACKUP_DIR="/backups"
MAX_AGE_HOURS=26  # Alert if no backup in 26 hours

# Check last backup time
# GNU find -printf and GNU stat -c are used below. On BSD/macOS, replace
# -printf '%T@ %p\\n' with find -print plus stat -f %m, or use a platform-
# appropriate backup-monitoring implementation.
LAST_BACKUP=$(find "$BACKUP_DIR" -name '*.dump.gz' -type f -printf '%T@ %p\\n' | sort -n | tail -1 | cut -d' ' -f2)
LAST_BACKUP_TIME=$(stat -c %Y "$LAST_BACKUP")
CURRENT_TIME=$(date +%s)
AGE_HOURS=$(( ($CURRENT_TIME - $LAST_BACKUP_TIME) / 3600 ))

if [ $AGE_HOURS -gt $MAX_AGE_HOURS ]; then
    echo "ALERT: Last backup is $AGE_HOURS hours old"
    # Send alert (email, Slack, etc.)
    exit 1
else
    echo "OK: Last backup is $AGE_HOURS hours old"
    exit 0
fi
```

### Backup Metrics

**Track Backup Metrics:**
- Backup size
- Backup duration
- Success/failure rate
- Storage usage
- Recovery time

## Best Practices

**✅ Do:**
- Automate backups
- Test restores regularly
- Store backups off-site
- Encrypt sensitive backups
- Monitor backup status
- Document procedures
- Verify backup integrity
- Keep multiple versions
- Set retention policies

**❌ Don't:**
- Rely on single backup
- Skip backup testing
- Store only on-site
- Leave backups unencrypted
- Ignore backup failures
- Forget documentation
- Trust without verification
- Keep backups forever
- Ignore storage costs

## Related Documentation

- [Docker Compose Deployment](./docker-compose.md) - Deployment guide
- [Kubernetes Deployment](./kubernetes.md) - K8s deployment
- [Monitoring](../operations/monitoring.md) - Monitoring guide
- [Troubleshooting](./troubleshooting.md) - Common issues

---

**Last Updated**: 2026-02-11
