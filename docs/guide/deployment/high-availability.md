# High Availability

This guide covers deploying Clouisle with high availability (HA) for production environments.

## Overview

High availability ensures:

- **Uptime**: 99.9%+ availability (< 8.76 hours downtime/year)
- **Redundancy**: No single point of failure
- **Failover**: Automatic recovery from failures
- **Load distribution**: Traffic spread across instances
- **Data durability**: No data loss during failures
- **Geographic distribution**: Multi-region deployment

## Architecture

### HA Architecture Diagram

```
                    ┌─────────────────┐
                    │   DNS / CDN     │
                    │  (CloudFlare)   │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  Load Balancer  │
                    │   (HAProxy)     │
                    │   Active/Active │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
┌───────▼────────┐  ┌────────▼───────┐  ┌────────▼───────┐
│   Backend 1    │  │   Backend 2    │  │   Backend 3    │
│   (Active)     │  │   (Active)     │  │   (Active)     │
└───────┬────────┘  └────────┬───────┘  └────────┬───────┘
        │                    │                    │
        └────────────────────┼────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
┌───────▼────────┐  ┌────────▼───────┐  ┌────────▼───────┐
│  PostgreSQL    │  │     Redis      │  │    Qdrant      │
│   Primary      │  │   Sentinel     │  │    Cluster     │
│  + Replicas    │  │   + Replicas   │  │   3 nodes      │
└────────────────┘  └────────────────┘  └────────────────┘
```

## Load Balancer Setup

### HAProxy Configuration

**Install HAProxy:**

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install haproxy

# CentOS/RHEL
sudo yum install haproxy
```

**HAProxy Configuration:**

```conf
# /etc/haproxy/haproxy.cfg
global
    log /dev/log local0
    log /dev/log local1 notice
    chroot /var/lib/haproxy
    stats socket /run/haproxy/admin.sock mode 660 level admin
    stats timeout 30s
    user haproxy
    group haproxy
    daemon

    # SSL
    ssl-default-bind-ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256
    ssl-default-bind-options ssl-min-ver TLSv1.2 no-tls-tickets

defaults
    log     global
    mode    http
    option  httplog
    option  dontlognull
    timeout connect 5000
    timeout client  50000
    timeout server  50000
    errorfile 400 /etc/haproxy/errors/400.http
    errorfile 403 /etc/haproxy/errors/403.http
    errorfile 408 /etc/haproxy/errors/408.http
    errorfile 500 /etc/haproxy/errors/500.http
    errorfile 502 /etc/haproxy/errors/502.http
    errorfile 503 /etc/haproxy/errors/503.http
    errorfile 504 /etc/haproxy/errors/504.http

# Stats page
listen stats
    bind *:8404
    stats enable
    stats uri /stats
    stats refresh 30s
    stats admin if TRUE

# Frontend - HTTP
frontend http_front
    bind *:80
    redirect scheme https code 301 if !{ ssl_fc }

# Frontend - HTTPS
frontend https_front
    bind *:443 ssl crt /etc/haproxy/certs/clouisle.pem

    # ACLs
    acl is_api path_beg /api
    acl is_websocket hdr(Upgrade) -i WebSocket

    # Use backends
    use_backend backend_api if is_api
    use_backend backend_websocket if is_websocket
    default_backend backend_frontend

# Backend - API
backend backend_api
    balance roundrobin
    option httpchk GET /health
    http-check expect status 200

    server backend1 backend-1:8000 check inter 2000 rise 2 fall 3
    server backend2 backend-2:8000 check inter 2000 rise 2 fall 3
    server backend3 backend-3:8000 check inter 2000 rise 2 fall 3

# Backend - Frontend
backend backend_frontend
    balance roundrobin
    option httpchk GET /
    http-check expect status 200

    server frontend1 frontend-1:3000 check inter 2000 rise 2 fall 3
    server frontend2 frontend-2:3000 check inter 2000 rise 2 fall 3
    server frontend3 frontend-3:3000 check inter 2000 rise 2 fall 3

# Backend - WebSocket
backend backend_websocket
    balance leastconn
    option http-server-close
    option forceclose

    server backend1 backend-1:8000 check inter 2000 rise 2 fall 3
    server backend2 backend-2:8000 check inter 2000 rise 2 fall 3
    server backend3 backend-3:8000 check inter 2000 rise 2 fall 3
```

**Start HAProxy:**

```bash
# Enable and start
sudo systemctl enable haproxy
sudo systemctl start haproxy

# Check status
sudo systemctl status haproxy

# View stats
curl http://localhost:8404/stats
```

### Keepalived for HAProxy HA

**Install Keepalived:**

```bash
sudo apt-get install keepalived
```

**Keepalived Configuration (Master):**

```conf
# /etc/keepalived/keepalived.conf
vrrp_script chk_haproxy {
    script "killall -0 haproxy"
    interval 2
    weight 2
}

vrrp_instance VI_1 {
    state MASTER
    interface eth0
    virtual_router_id 51
    priority 101
    advert_int 1

    authentication {
        auth_type PASS
        auth_pass your-secret-password
    }

    virtual_ipaddress {
        192.168.1.100/24
    }

    track_script {
        chk_haproxy
    }
}
```

**Keepalived Configuration (Backup):**

```conf
# /etc/keepalived/keepalived.conf
vrrp_script chk_haproxy {
    script "killall -0 haproxy"
    interval 2
    weight 2
}

vrrp_instance VI_1 {
    state BACKUP
    interface eth0
    virtual_router_id 51
    priority 100
    advert_int 1

    authentication {
        auth_type PASS
        auth_pass your-secret-password
    }

    virtual_ipaddress {
        192.168.1.100/24
    }

    track_script {
        chk_haproxy
    }
}
```

## Database High Availability

### PostgreSQL Replication

**Primary Configuration:**

```conf
# postgresql.conf
listen_addresses = '*'
wal_level = replica
max_wal_senders = 3
max_replication_slots = 3
hot_standby = on
```

```conf
# pg_hba.conf
# Allow replication connections
host replication clouisle 192.168.1.0/24 md5
```

**Create Replication User:**

```sql
CREATE USER replicator WITH REPLICATION ENCRYPTED PASSWORD 'replication-password';
```

**Replica Configuration:**

```bash
# Stop replica
sudo systemctl stop postgresql

# Remove data directory
sudo rm -rf /var/lib/postgresql/14/main/*

# Create base backup
sudo -u postgres pg_basebackup -h primary-host -D /var/lib/postgresql/14/main -U replicator -v -P -W

# Create standby signal
sudo -u postgres touch /var/lib/postgresql/14/main/standby.signal

# Configure recovery
cat > /var/lib/postgresql/14/main/postgresql.auto.conf <<EOF
primary_conninfo = 'host=primary-host port=5432 user=replicator password=replication-password'
EOF

# Start replica
sudo systemctl start postgresql
```

**Verify Replication:**

```sql
-- On primary
SELECT client_addr, state, sync_state
FROM pg_stat_replication;

-- On replica
SELECT pg_is_in_recovery();
```

### PostgreSQL Automatic Failover (Patroni)

**Patroni Configuration:**

```yaml
# patroni.yml
scope: clouisle
namespace: /db/
name: postgres1

restapi:
  listen: 0.0.0.0:8008
  connect_address: postgres1:8008

etcd:
  hosts: etcd1:2379,etcd2:2379,etcd3:2379

bootstrap:
  dcs:
    ttl: 30
    loop_wait: 10
    retry_timeout: 10
    maximum_lag_on_failover: 1048576
    postgresql:
      use_pg_rewind: true
      parameters:
        max_connections: 200
        shared_buffers: 2GB
        effective_cache_size: 6GB
        maintenance_work_mem: 512MB
        checkpoint_completion_target: 0.9
        wal_buffers: 16MB
        default_statistics_target: 100
        random_page_cost: 1.1
        effective_io_concurrency: 200
        work_mem: 10MB
        min_wal_size: 1GB
        max_wal_size: 4GB

  initdb:
    - encoding: UTF8
    - data-checksums

  pg_hba:
    - host replication replicator 0.0.0.0/0 md5
    - host all all 0.0.0.0/0 md5

postgresql:
  listen: 0.0.0.0:5432
  connect_address: postgres1:5432
  data_dir: /var/lib/postgresql/14/main
  bin_dir: /usr/lib/postgresql/14/bin
  authentication:
    replication:
      username: replicator
      password: replication-password
    superuser:
      username: postgres
      password: postgres-password
  parameters:
    unix_socket_directories: '/var/run/postgresql'
```

**Docker Compose with Patroni:**

```yaml
# docker-compose.yml
version: '3.8'

services:
  etcd1:
    image: quay.io/coreos/etcd:v3.5.0
    environment:
      ETCD_NAME: etcd1
      ETCD_INITIAL_CLUSTER: etcd1=http://etcd1:2380,etcd2=http://etcd2:2380,etcd3=http://etcd3:2380
      ETCD_INITIAL_CLUSTER_STATE: new
      ETCD_INITIAL_CLUSTER_TOKEN: etcd-cluster
      ETCD_LISTEN_CLIENT_URLS: http://0.0.0.0:2379
      ETCD_ADVERTISE_CLIENT_URLS: http://etcd1:2379
      ETCD_LISTEN_PEER_URLS: http://0.0.0.0:2380
      ETCD_INITIAL_ADVERTISE_PEER_URLS: http://etcd1:2380

  patroni1:
    image: patroni/patroni:latest
    environment:
      PATRONI_NAME: postgres1
      PATRONI_SCOPE: clouisle
      PATRONI_ETCD_HOSTS: etcd1:2379,etcd2:2379,etcd3:2379
      PATRONI_POSTGRESQL_CONNECT_ADDRESS: patroni1:5432
      PATRONI_RESTAPI_CONNECT_ADDRESS: patroni1:8008
      PATRONI_POSTGRESQL_DATA_DIR: /var/lib/postgresql/data
      PATRONI_REPLICATION_USERNAME: replicator
      PATRONI_REPLICATION_PASSWORD: replication-password
      PATRONI_SUPERUSER_USERNAME: postgres
      PATRONI_SUPERUSER_PASSWORD: postgres-password
    volumes:
      - patroni1-data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
      - "8008:8008"

  patroni2:
    image: patroni/patroni:latest
    environment:
      PATRONI_NAME: postgres2
      PATRONI_SCOPE: clouisle
      PATRONI_ETCD_HOSTS: etcd1:2379,etcd2:2379,etcd3:2379
      PATRONI_POSTGRESQL_CONNECT_ADDRESS: patroni2:5432
      PATRONI_RESTAPI_CONNECT_ADDRESS: patroni2:8008
      PATRONI_POSTGRESQL_DATA_DIR: /var/lib/postgresql/data
      PATRONI_REPLICATION_USERNAME: replicator
      PATRONI_REPLICATION_PASSWORD: replication-password
      PATRONI_SUPERUSER_USERNAME: postgres
      PATRONI_SUPERUSER_PASSWORD: postgres-password
    volumes:
      - patroni2-data:/var/lib/postgresql/data
    ports:
      - "5433:5432"
      - "8009:8008"

volumes:
  patroni1-data:
  patroni2-data:
```

### Redis Sentinel

**Redis Sentinel Configuration:**

```conf
# sentinel.conf
port 26379
sentinel monitor mymaster redis-master 6379 2
sentinel down-after-milliseconds mymaster 5000
sentinel parallel-syncs mymaster 1
sentinel failover-timeout mymaster 10000
sentinel auth-pass mymaster your-redis-password
```

**Docker Compose with Redis Sentinel:**

```yaml
# docker-compose.yml
services:
  redis-master:
    image: redis:7-alpine
    command: redis-server --requirepass your-redis-password --appendonly yes
    volumes:
      - redis-master-data:/data

  redis-replica1:
    image: redis:7-alpine
    command: redis-server --requirepass your-redis-password --replicaof redis-master 6379 --masterauth your-redis-password --appendonly yes
    volumes:
      - redis-replica1-data:/data
    depends_on:
      - redis-master

  redis-replica2:
    image: redis:7-alpine
    command: redis-server --requirepass your-redis-password --replicaof redis-master 6379 --masterauth your-redis-password --appendonly yes
    volumes:
      - redis-replica2-data:/data
    depends_on:
      - redis-master

  sentinel1:
    image: redis:7-alpine
    command: redis-sentinel /etc/redis/sentinel.conf
    volumes:
      - ./sentinel.conf:/etc/redis/sentinel.conf
    depends_on:
      - redis-master

  sentinel2:
    image: redis:7-alpine
    command: redis-sentinel /etc/redis/sentinel.conf
    volumes:
      - ./sentinel.conf:/etc/redis/sentinel.conf
    depends_on:
      - redis-master

  sentinel3:
    image: redis:7-alpine
    command: redis-sentinel /etc/redis/sentinel.conf
    volumes:
      - ./sentinel.conf:/etc/redis/sentinel.conf
    depends_on:
      - redis-master

volumes:
  redis-master-data:
  redis-replica1-data:
  redis-replica2-data:
```

**Connect to Redis Sentinel:**

```python
# app/core/redis.py
from redis.sentinel import Sentinel

sentinel = Sentinel([
    ('sentinel1', 26379),
    ('sentinel2', 26379),
    ('sentinel3', 26379)
], socket_timeout=0.1)

# Get master
master = sentinel.master_for('mymaster', socket_timeout=0.1, password='your-redis-password')

# Get slave for read operations
slave = sentinel.slave_for('mymaster', socket_timeout=0.1, password='your-redis-password')
```

### Qdrant Cluster

**Qdrant Cluster Configuration:**

```yaml
# docker-compose.yml
services:
  qdrant1:
    image: qdrant/qdrant:v1.7.4
    environment:
      QDRANT__CLUSTER__ENABLED: "true"
      QDRANT__CLUSTER__P2P__PORT: 6335
      QDRANT__CLUSTER__CONSENSUS__TICK_PERIOD_MS: 100
    volumes:
      - qdrant1-data:/qdrant/storage
    ports:
      - "6333:6333"
      - "6335:6335"

  qdrant2:
    image: qdrant/qdrant:v1.7.4
    environment:
      QDRANT__CLUSTER__ENABLED: "true"
      QDRANT__CLUSTER__P2P__PORT: 6335
      QDRANT__CLUSTER__P2P__BOOTSTRAP__URI: "http://qdrant1:6335"
    volumes:
      - qdrant2-data:/qdrant/storage
    ports:
      - "6334:6333"
      - "6336:6335"
    depends_on:
      - qdrant1

  qdrant3:
    image: qdrant/qdrant:v1.7.4
    environment:
      QDRANT__CLUSTER__ENABLED: "true"
      QDRANT__CLUSTER__P2P__PORT: 6335
      QDRANT__CLUSTER__P2P__BOOTSTRAP__URI: "http://qdrant1:6335"
    volumes:
      - qdrant3-data:/qdrant/storage
    ports:
      - "6337:6333"
      - "6338:6335"
    depends_on:
      - qdrant1

volumes:
  qdrant1-data:
  qdrant2-data:
  qdrant3-data:
```

**Create Replicated Collection:**

```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

client = QdrantClient(url="http://qdrant1:6333")

# Create collection with replication
client.create_collection(
    collection_name="documents",
    vectors_config=VectorParams(
        size=1536,
        distance=Distance.COSINE,
    ),
    replication_factor=3,  # Replicate to 3 nodes
    write_consistency_factor=2,  # Wait for 2 nodes to confirm
)
```

## Application High Availability

### Stateless Application Design

**Session Management:**

```python
# Use Redis for session storage
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

app = FastAPI()

# Use Redis-backed sessions
app.add_middleware(
    SessionMiddleware,
    secret_key="your-secret-key",
    session_cookie="clouisle_session",
    max_age=3600,
    same_site="lax",
    https_only=True,
)
```

**Shared File Storage:**

```yaml
# Use S3 or shared volume for uploads
services:
  backend1:
    volumes:
      - shared-uploads:/app/uploads

  backend2:
    volumes:
      - shared-uploads:/app/uploads

  backend3:
    volumes:
      - shared-uploads:/app/uploads

volumes:
  shared-uploads:
    driver: local
    driver_opts:
      type: nfs
      o: addr=nfs-server,rw
      device: ":/exports/uploads"
```

### Health Checks

**Application Health Endpoint:**

```python
# app/api/v1/endpoints/health.py
from fastapi import APIRouter, status
from app.core.database import database
from app.core.redis import redis_client
from app.core.qdrant import qdrant_client

router = APIRouter()

@router.get("/health")
async def health_check():
    """Comprehensive health check"""
    health = {
        "status": "healthy",
        "checks": {}
    }

    # Check database
    try:
        await database.execute("SELECT 1")
        health["checks"]["database"] = "healthy"
    except Exception as e:
        health["checks"]["database"] = f"unhealthy: {str(e)}"
        health["status"] = "unhealthy"

    # Check Redis
    try:
        await redis_client.ping()
        health["checks"]["redis"] = "healthy"
    except Exception as e:
        health["checks"]["redis"] = f"unhealthy: {str(e)}"
        health["status"] = "unhealthy"

    # Check Qdrant
    try:
        qdrant_client.get_collections()
        health["checks"]["qdrant"] = "healthy"
    except Exception as e:
        health["checks"]["qdrant"] = f"unhealthy: {str(e)}"
        health["status"] = "unhealthy"

    status_code = status.HTTP_200_OK if health["status"] == "healthy" else status.HTTP_503_SERVICE_UNAVAILABLE

    return health, status_code
```

### Graceful Shutdown

```python
# app/main.py
import signal
import asyncio
from fastapi import FastAPI

app = FastAPI()

shutdown_event = asyncio.Event()

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    print(f"Received signal {signum}, shutting down gracefully...")
    shutdown_event.set()

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

@app.on_event("shutdown")
async def shutdown():
    """Graceful shutdown"""
    print("Shutting down...")

    # Stop accepting new requests
    # Wait for ongoing requests to complete
    await asyncio.sleep(5)

    # Close database connections
    await database.disconnect()

    # Close Redis connections
    await redis_client.close()

    print("Shutdown complete")
```

## Disaster Recovery

### Backup Strategy

**Automated Backups:**

```bash
#!/bin/bash
# ha-backup.sh

# Backup from primary
pg_dump -h primary-host -U clouisle clouisle | gzip > backup_$(date +%Y%m%d).sql.gz

# Upload to S3
aws s3 cp backup_$(date +%Y%m%d).sql.gz s3://backups/postgres/

# Backup Qdrant snapshots
for node in qdrant1 qdrant2 qdrant3; do
    curl -X POST "http://$node:6333/collections/documents/snapshots"
done

# Backup Redis
redis-cli --rdb /backups/redis/dump_$(date +%Y%m%d).rdb
```

### Multi-Region Deployment

**DNS Failover (Route53):**

```json
{
  "HostedZoneId": "Z1234567890ABC",
  "ChangeBatch": {
    "Changes": [
      {
        "Action": "CREATE",
        "ResourceRecordSet": {
          "Name": "clouisle.com",
          "Type": "A",
          "SetIdentifier": "Primary",
          "Failover": "PRIMARY",
          "TTL": 60,
          "ResourceRecords": [
            {
              "Value": "primary-region-ip"
            }
          ],
          "HealthCheckId": "health-check-id"
        }
      },
      {
        "Action": "CREATE",
        "ResourceRecordSet": {
          "Name": "clouisle.com",
          "Type": "A",
          "SetIdentifier": "Secondary",
          "Failover": "SECONDARY",
          "TTL": 60,
          "ResourceRecords": [
            {
              "Value": "secondary-region-ip"
            }
          ]
        }
      }
    ]
  }
}
```

## Monitoring and Alerting

### Health Monitoring

**Prometheus Alerts:**

```yaml
# alerts.yml
groups:
  - name: clouisle
    rules:
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High error rate detected"

      - alert: DatabaseDown
        expr: up{job="postgres"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "PostgreSQL is down"

      - alert: HighLatency
        expr: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High latency detected"
```

## Testing HA Setup

### Failover Testing

**Test Database Failover:**

```bash
# Stop primary
docker compose stop postgres-primary

# Verify replica promotion
docker compose exec postgres-replica psql -U clouisle -c "SELECT pg_is_in_recovery();"

# Should return false (promoted to primary)
```

**Test Load Balancer Failover:**

```bash
# Stop one backend
docker compose stop backend1

# Verify traffic redirects
curl -v http://load-balancer/health

# Should still return 200 OK
```

### Chaos Testing

```bash
# Install chaos toolkit
pip install chaostoolkit

# Run chaos experiments
chaos run experiments/kill-random-pod.yaml
chaos run experiments/network-delay.yaml
chaos run experiments/cpu-stress.yaml
```

## Best Practices

**✅ Do:**
- Eliminate single points of failure
- Use health checks everywhere
- Implement graceful shutdown
- Test failover regularly
- Monitor all components
- Automate recovery
- Document procedures
- Use load balancing
- Implement circuit breakers
- Plan for disasters

**❌ Don't:**
- Rely on single instance
- Skip health checks
- Force kill processes
- Forget to test failover
- Ignore monitoring
- Manual recovery only
- Skip documentation
- Direct traffic to instances
- Ignore cascading failures
- Assume it works

## Related Documentation

- [Kubernetes Deployment](./kubernetes.md) - K8s HA setup
- [Scaling Guide](./scaling.md) - Scaling strategies
- [Backup and Recovery](./backup-recovery.md) - Backup procedures
- [Monitoring](../operations/monitoring.md) - Monitoring guide

---

**Last Updated**: 2026-02-11
