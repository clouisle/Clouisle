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

**Recommended Schedule:**
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

Transaction Logs:
  Frequency: Continuous
  Retention: 7 days
```

## Database Backup

### PostgreSQL Backup

**Manual Backup:**

```bash
# Full database backup
docker compose exec postgres pg_dump -U clouisle clouisle > backup_$(date +%Y%m%d_%H%M%S).sql

# Compressed backup
docker compose exec postgres pg_dump -U clouisle clouisle | gzip > backup_$(date +%Y%m%d_%H%M%S).sql.gz

# Custom format (recommended)
docker compose exec postgres pg_dump -U clouisle -Fc clouisle > backup_$(date +%Y%m%d_%H%M%S).dump
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
docker compose exec -T postgres pg_dump -U clouisle -Fc clouisle > $BACKUP_FILE

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
docker compose stop backend frontend celery

# Restore database
docker compose exec -T postgres pg_restore -U clouisle -d clouisle -c < backup.dump

# Or from compressed backup
gunzip -c backup.dump.gz | docker compose exec -T postgres pg_restore -U clouisle -d clouisle -c

# Restart application
docker compose start backend frontend celery
```

**Restore to New Database:**

```bash
# Create new database
docker compose exec postgres createdb -U clouisle clouisle_restored

# Restore to new database
docker compose exec -T postgres pg_restore -U clouisle -d clouisle_restored < backup.dump

# Switch to restored database (update .env)
POSTGRES_DB=clouisle_restored
```

## Vector Database Backup

### Qdrant Backup

**Create Snapshot:**

```bash
# Create snapshot via API
curl -X POST "http://localhost:6333/collections/{collection_name}/snapshots"

# List snapshots
curl "http://localhost:6333/collections/{collection_name}/snapshots"

# Download snapshot
curl "http://localhost:6333/collections/{collection_name}/snapshots/{snapshot_name}" \
  --output snapshot.snapshot
```

**Automated Qdrant Backup:**

```bash
#!/bin/bash
# backup-qdrant.sh

BACKUP_DIR="/backups/qdrant"
QDRANT_URL="http://localhost:6333"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# Get all collections
collections=$(curl -s "$QDRANT_URL/collections" | jq -r '.result.collections[].name')

# Backup each collection
for collection in $collections; do
    echo "Backing up collection: $collection"

    # Create snapshot
    snapshot=$(curl -s -X POST "$QDRANT_URL/collections/$collection/snapshots" | jq -r '.result.name')

    # Download snapshot
    curl -s "$QDRANT_URL/collections/$collection/snapshots/$snapshot" \
      --output "$BACKUP_DIR/${collection}_${TIMESTAMP}.snapshot"

    # Delete remote snapshot
    curl -X DELETE "$QDRANT_URL/collections/$collection/snapshots/$snapshot"
done

echo "Qdrant backup completed"
```

### Qdrant Restore

**Restore Collection:**

```bash
# Upload snapshot
curl -X PUT "http://localhost:6333/collections/{collection_name}/snapshots/upload" \
  -H "Content-Type: application/octet-stream" \
  --data-binary @snapshot.snapshot

# Restore from snapshot
curl -X PUT "http://localhost:6333/collections/{collection_name}/snapshots/{snapshot_name}/recover"
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

UPLOADS_DIR="/app/uploads"
BACKUP_DIR="/backups/files"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/uploads_$TIMESTAMP.tar.gz"

mkdir -p $BACKUP_DIR

# Create backup
tar -czf $BACKUP_FILE $UPLOADS_DIR

# Remove old backups (keep 30 days)
find $BACKUP_DIR -name "uploads_*.tar.gz" -mtime +30 -delete

echo "File backup completed: $BACKUP_FILE"
```

### Restore Files

```bash
# Extract backup
tar -xzf uploads_backup.tar.gz -C /

# Or to specific location
tar -xzf uploads_backup.tar.gz -C /restore/location
```

## Configuration Backup

### Backup Configuration Files

```bash
#!/bin/bash
# backup-config.sh

CONFIG_DIR="/path/to/clouisle"
BACKUP_DIR="/backups/config"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# Backup configuration files
tar -czf "$BACKUP_DIR/config_$TIMESTAMP.tar.gz" \
  $CONFIG_DIR/.env \
  $CONFIG_DIR/docker-compose.yml \
  $CONFIG_DIR/nginx.conf \
  $CONFIG_DIR/ssl/

echo "Configuration backup completed"
```

### Restore Configuration

```bash
# Extract configuration
tar -xzf config_backup.tar.gz -C /path/to/clouisle
```

## Complete System Backup

### Full System Backup Script

```bash
#!/bin/bash
# full-backup.sh

BACKUP_ROOT="/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="$BACKUP_ROOT/full_$TIMESTAMP"

mkdir -p $BACKUP_DIR

echo "Starting full system backup..."

# 1. Backup PostgreSQL
echo "Backing up PostgreSQL..."
docker compose exec -T postgres pg_dump -U clouisle -Fc clouisle > $BACKUP_DIR/postgres.dump
gzip $BACKUP_DIR/postgres.dump

# 2. Backup Qdrant
echo "Backing up Qdrant..."
mkdir -p $BACKUP_DIR/qdrant
docker compose exec -T qdrant tar -czf - /qdrant/storage > $BACKUP_DIR/qdrant/storage.tar.gz

# 3. Backup Redis (optional)
echo "Backing up Redis..."
docker compose exec redis redis-cli SAVE
docker compose cp redis:/data/dump.rdb $BACKUP_DIR/redis_dump.rdb

# 4. Backup files
echo "Backing up uploaded files..."
tar -czf $BACKUP_DIR/uploads.tar.gz /app/uploads

# 5. Backup configuration
echo "Backing up configuration..."
tar -czf $BACKUP_DIR/config.tar.gz \
  .env \
  docker-compose.yml \
  nginx.conf

# 6. Create backup manifest
cat > $BACKUP_DIR/manifest.txt <<EOF
Backup Date: $(date)
Backup Type: Full System Backup
Components:
  - PostgreSQL: postgres.dump.gz
  - Qdrant: qdrant/storage.tar.gz
  - Redis: redis_dump.rdb
  - Files: uploads.tar.gz
  - Config: config.tar.gz
EOF

# 7. Create archive
cd $BACKUP_ROOT
tar -czf "full_backup_$TIMESTAMP.tar.gz" "full_$TIMESTAMP"
rm -rf "full_$TIMESTAMP"

echo "Full backup completed: full_backup_$TIMESTAMP.tar.gz"

# 8. Upload to remote storage (optional)
# aws s3 cp "full_backup_$TIMESTAMP.tar.gz" s3://your-bucket/backups/
```

## Remote Backup

### Backup to S3

```bash
#!/bin/bash
# backup-to-s3.sh

BACKUP_DIR="/backups"
S3_BUCKET="s3://your-bucket/clouisle-backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Perform local backup
./full-backup.sh

# Upload to S3
aws s3 cp "$BACKUP_DIR/full_backup_$TIMESTAMP.tar.gz" \
  "$S3_BUCKET/full_backup_$TIMESTAMP.tar.gz" \
  --storage-class STANDARD_IA

# Remove local backup after upload
rm "$BACKUP_DIR/full_backup_$TIMESTAMP.tar.gz"

echo "Backup uploaded to S3"
```

### Backup to Azure Blob Storage

```bash
#!/bin/bash
# backup-to-azure.sh

BACKUP_DIR="/backups"
CONTAINER="clouisle-backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Perform local backup
./full-backup.sh

# Upload to Azure
az storage blob upload \
  --account-name your-account \
  --container-name $CONTAINER \
  --name "full_backup_$TIMESTAMP.tar.gz" \
  --file "$BACKUP_DIR/full_backup_$TIMESTAMP.tar.gz"

echo "Backup uploaded to Azure"
```

## Disaster Recovery

### Recovery Procedures

**Complete System Recovery:**

1. **Prepare Environment:**
   ```bash
   # Install Docker and Docker Compose
   # Clone repository
   git clone https://github.com/your-org/clouisle.git
   cd clouisle
   ```

2. **Restore Configuration:**
   ```bash
   # Extract configuration backup
   tar -xzf config_backup.tar.gz
   ```

3. **Start Infrastructure:**
   ```bash
   # Start databases only
   docker compose up -d postgres redis qdrant

   # Wait for databases to be ready
   sleep 30
   ```

4. **Restore PostgreSQL:**
   ```bash
   # Restore database
   gunzip -c postgres.dump.gz | docker compose exec -T postgres pg_restore -U clouisle -d clouisle -c
   ```

5. **Restore Qdrant:**
   ```bash
   # Stop Qdrant
   docker compose stop qdrant

   # Restore Qdrant data
   tar -xzf qdrant_storage.tar.gz -C /var/lib/docker/volumes/clouisle_qdrant_data/_data/

   # Start Qdrant
   docker compose start qdrant
   ```

6. **Restore Files:**
   ```bash
   # Restore uploaded files
   tar -xzf uploads.tar.gz -C /
   ```

7. **Start Application:**
   ```bash
   # Start all services
   docker compose up -d

   # Verify services
   docker compose ps
   ```

8. **Verify Recovery:**
   ```bash
   # Check health
   curl http://localhost:8000/health

   # Test login
   # Verify data integrity
   ```

### Recovery Time Objective (RTO)

**Target RTO by Component:**

| Component | RTO | Notes |
|-----------|-----|-------|
| Database | 30 minutes | Restore from backup |
| Vector DB | 1 hour | Restore embeddings |
| Files | 30 minutes | Restore from backup |
| Application | 15 minutes | Redeploy containers |
| **Total** | **2 hours** | Complete recovery |

### Recovery Point Objective (RPO)

**Target RPO:**

| Data Type | RPO | Backup Frequency |
|-----------|-----|------------------|
| Database | 24 hours | Daily |
| Files | 24 hours | Daily |
| Vectors | 24 hours | Daily |
| Logs | 1 hour | Continuous |

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

# 2. Check file size
SIZE=$(stat -f%z "$BACKUP_FILE")
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
    docker compose exec postgres createdb -U clouisle test_restore

    # Try to restore
    gunzip -c "$BACKUP_FILE" | docker compose exec -T postgres pg_restore -U clouisle -d test_restore

    if [ $? -eq 0 ]; then
        echo "Database backup is valid"
        docker compose exec postgres dropdb -U clouisle test_restore
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

# Create test environment
docker compose -f docker-compose.test.yml up -d

# Restore latest backup
LATEST_BACKUP=$(ls -t /backups/postgres/*.dump.gz | head -1)
gunzip -c $LATEST_BACKUP | docker compose -f docker-compose.test.yml exec -T postgres pg_restore -U clouisle -d clouisle

# Run smoke tests
docker compose -f docker-compose.test.yml exec backend pytest tests/smoke/

# Cleanup
docker compose -f docker-compose.test.yml down -v

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
LAST_BACKUP=$(find $BACKUP_DIR -name "*.dump.gz" -type f -printf '%T@ %p\n' | sort -n | tail -1 | cut -d' ' -f2)
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
