# Scaling Guide

This guide covers scaling Clouisle for high traffic and large deployments.

## Overview

Scaling strategies include:

- **Vertical scaling**: Increase resources per instance
- **Horizontal scaling**: Add more instances
- **Database scaling**: Optimize and scale database
- **Caching**: Reduce database load
- **Load balancing**: Distribute traffic
- **CDN**: Serve static assets
- **Async processing**: Offload heavy tasks

## Performance Metrics

### Key Metrics to Monitor

**Application Metrics:**
- Requests per second (RPS)
- Response time (p50, p95, p99)
- Error rate
- Active connections
- Queue length

**Resource Metrics:**
- CPU usage
- Memory usage
- Disk I/O
- Network I/O
- Database connections

**Business Metrics:**
- Active users
- Conversations per minute
- Workflow executions
- Document uploads
- API calls

### Performance Targets
These are operator-defined baseline targets, not guarantees provided by the shipped configuration. Validate them with representative workload tests.

**Response Time Targets:**
```yaml
API Endpoints:
  p50: < 100ms
  p95: < 500ms
  p99: < 1000ms

Chat Responses:
  First token: < 2s
  Streaming: < 100ms per token

Workflow Execution:
  Simple: < 5s
  Complex: < 30s

Search:
  Vector search: < 500ms
  Hybrid search: < 1s
```

## Vertical Scaling

### Increase Instance Resources

**Docker Compose:**

```yaml
# docker-compose.yml
services:
  api:
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G
        reservations:
          cpus: '2'
          memory: 4G

  db:
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G
        reservations:
          cpus: '2'
          memory: 4G
```

**Kubernetes:**

```yaml
# api-deployment.yaml
spec:
  containers:
  - name: api
    resources:
      requests:
        memory: "4Gi"
        cpu: "2000m"
      limits:
        memory: "8Gi"
        cpu: "4000m"
```

### Optimize Resource Allocation

**Backend Workers:**

```yaml
# Increase API workers (production mode)
python main.py server --no-reload -w 8 -H 0.0.0.0 -p 8000

# Or in docker-compose.yml (api service)
command: python main.py server --no-reload -w 8 -H 0.0.0.0 -p 8000
```

**Celery Workers:**

```yaml
# Increase Celery concurrency (worker service)
python main.py worker -c 8 -Q default,knowledge,workflow

# Or in docker-compose.yml
command: python main.py worker -c 8 -Q default,knowledge,workflow
```

## Horizontal Scaling

### Add Backend Replicas

**Docker Compose:**

The supplied Compose file publishes the API on host port `8000`. Before adding replicas, remove that `ports` mapping from the `api` service and keep the service reachable through an internal `expose` entry and a reverse proxy. Then scale with Compose:

```bash
docker compose up -d --scale api=3
```

Compose does not provide rolling-update or zero-downtime guarantees. For Docker Swarm, use a separate stack file and deploy it with `docker stack deploy`; the `deploy:` keys below are not applied by ordinary `docker compose up`.

**Kubernetes:**

The supplied manifest already uses a `RollingUpdate` strategy. Change the replica count declaratively in `deploy/k8s/clouisle.yaml`, or apply a temporary scale and watch the rollout:

```bash
kubectl -n clouisle scale deployment/api --replicas=5
kubectl -n clouisle rollout status deployment/api
```

### Auto-Scaling

**Kubernetes HPA:**

```yaml
# hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api
  minReplicas: 3
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Percent
        value: 50
        periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
      - type: Percent
        value: 100
        periodSeconds: 30
      - type: Pods
        value: 2
        periodSeconds: 30
      selectPolicy: Max
```

**Docker Swarm:**

```yaml
# docker-compose.yml
services:
  api:
    deploy:
      replicas: 3
      placement:
        max_replicas_per_node: 1
      update_config:
        parallelism: 1
        delay: 10s
```

## Load Balancing

### Nginx Load Balancer (generic example)

The supplied Compose deployment has no Nginx service; place an external proxy in front of the frontend when needed. For API/SSE traffic, disable buffering and use long read/send timeouts:

```nginx
# Generic example; replace upstream names and public server_name.
upstream api {
    least_conn;
    server api-1:8000 weight=1 max_fails=3 fail_timeout=30s;
    server api-2:8000 weight=1 max_fails=3 fail_timeout=30s;
}
upstream frontend {
    least_conn;
    server frontend-1:3000;
    server frontend-2:3000;
}

server {
    listen 80;
    server_name example.com;

    location /api {
        proxy_pass http://api;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_connect_timeout 10s;
        proxy_send_timeout 1800s;
        proxy_read_timeout 1800s;
        proxy_buffering off;
        proxy_cache off;
        add_header X-Accel-Buffering no;
    }

    location / {
        proxy_pass http://frontend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

### Health Checks

```nginx
# Health check configuration
upstream backend {
    server backend-1:8000 max_fails=3 fail_timeout=30s;
    server backend-2:8000 max_fails=3 fail_timeout=30s;
    server backend-3:8000 max_fails=3 fail_timeout=30s;

    # Active health checks (nginx plus)
    # health_check interval=10s fails=3 passes=2 uri=/api/v1/health;
}
```

## Database Scaling

### PostgreSQL Optimization
> **Scope:** The following pooling example is generic architecture guidance. The shipped Clouisle backend does not expose `app/core/database.py` or configure application pool knobs in this guide; validate any external PgBouncer deployment against your database and connection limits.

**Connection Pooling:**

```python
# app/core/database.py
from tortoise import Tortoise

async def init_db():
    await Tortoise.init(
        db_url=DATABASE_URL,
        modules={'models': ['app.models']},
        # Connection pool settings
        minsize=10,
        maxsize=50,
        max_queries=50000,
        max_inactive_connection_lifetime=300,
    )
```

**PgBouncer Configuration:**

```ini
# pgbouncer.ini
[databases]
clouisle = host=db port=5432 dbname=clouisle

[pgbouncer]
listen_addr = 0.0.0.0
listen_port = 6432
auth_type = md5
auth_file = /etc/pgbouncer/userlist.txt

# Connection pooling
pool_mode = transaction
max_client_conn = 1000
default_pool_size = 25
reserve_pool_size = 5
reserve_pool_timeout = 3

# Performance
server_idle_timeout = 600
server_lifetime = 3600
server_connect_timeout = 15
query_timeout = 0
```

**Docker Compose with PgBouncer:**

```yaml
services:
  pgbouncer:
    image: pgbouncer/pgbouncer:latest
    environment:
      DATABASES_HOST: db
      DATABASES_PORT: 5432
      DATABASES_DBNAME: clouisle
      DATABASES_USER: clouisle
      DATABASES_PASSWORD: ${POSTGRES_PASSWORD}
      PGBOUNCER_POOL_MODE: transaction
      PGBOUNCER_MAX_CLIENT_CONN: 1000
      PGBOUNCER_DEFAULT_POOL_SIZE: 25
    ports:
      - "6432:6432"
    depends_on:
      - db

  api:
    environment:
      POSTGRES_SERVER: pgbouncer
      POSTGRES_PORT: 6432
```

### Database Indexes

**Create Indexes:**

```sql
-- User indexes
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_is_active ON users(is_active);

-- Team indexes
CREATE INDEX idx_teams_name ON teams(name);
CREATE INDEX idx_team_members_user_id ON team_members(user_id);
CREATE INDEX idx_team_members_team_id ON team_members(team_id);

-- Agent indexes
CREATE INDEX idx_agents_team_id ON agents(team_id);
CREATE INDEX idx_agents_is_active ON agents(is_active);
CREATE INDEX idx_agents_created_at ON agents(created_at DESC);

-- Conversation indexes
CREATE INDEX idx_conversations_user_id ON conversations(user_id);
CREATE INDEX idx_conversations_agent_id ON conversations(agent_id);
CREATE INDEX idx_conversations_created_at ON conversations(created_at DESC);

-- Message indexes
CREATE INDEX idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX idx_messages_created_at ON messages(created_at DESC);

-- Composite indexes
CREATE INDEX idx_conversations_user_agent ON conversations(user_id, agent_id);
CREATE INDEX idx_messages_conv_created ON messages(conversation_id, created_at DESC);
```

### Read Replicas

The supplied Compose and Kubernetes manifests run a single PostgreSQL primary; read replicas are an external scaling design, not a shipped workload. If you add replicas for PostgreSQL 17, use the upstream physical-replication procedure with `standby.signal` and `primary_conninfo` in `postgresql.auto.conf`. Do not use the removed PostgreSQL 12-era `recovery.conf` file or copy this guide as a complete production replication configuration.

## Caching Strategy

### Redis Caching

> **Scope:** The shipped application does not provide a general `app/core/cache.py` LLM-response cache. Current caches are limited to workflow definitions and selected deterministic workflow nodes; add privacy, invalidation, and TTL controls before introducing another cache.
**Cache Configuration:**

```python
# app/core/cache.py
import redis.asyncio as redis
from functools import wraps
import json

redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    decode_responses=True,
    max_connections=50,
)

def cache(ttl: int = 300):
    """Cache decorator"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key
            cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"

            # Try to get from cache
            cached = await redis_client.get(cache_key)
            if cached:
                return json.loads(cached)

            # Execute function
            result = await func(*args, **kwargs)

            # Store in cache
            await redis_client.setex(
                cache_key,
                ttl,
                json.dumps(result)
            )

            return result
        return wrapper
    return decorator

# Usage
@cache(ttl=600)
async def get_agent(agent_id: str):
    return await Agent.get(id=agent_id)
```

**Cache Patterns:**

```python
# Cache-aside pattern
async def get_user(user_id: str):
    # Try cache first
    cached = await redis_client.get(f"user:{user_id}")
    if cached:
        return json.loads(cached)

    # Get from database
    user = await User.get(id=user_id)

    # Store in cache
    await redis_client.setex(
        f"user:{user_id}",
        3600,
        json.dumps(user.dict())
    )

    return user

# Write-through pattern
async def update_user(user_id: str, data: dict):
    # Update database
    user = await User.get(id=user_id)
    await user.update_from_dict(data)
    await user.save()

    # Update cache
    await redis_client.setex(
        f"user:{user_id}",
        3600,
        json.dumps(user.dict())
    )

    return user

# Cache invalidation
async def delete_user(user_id: str):
    # Delete from database
    await User.filter(id=user_id).delete()

    # Invalidate cache
    await redis_client.delete(f"user:{user_id}")
```

### Application-Level Caching

**LRU Cache:**

```python
from functools import lru_cache

@lru_cache(maxsize=1000)
def get_model_config(model_id: str):
    """Cache model configurations in memory"""
    return ModelConfig.get(id=model_id)

# Clear cache when needed
get_model_config.cache_clear()
```

## CDN Configuration

### Static Asset Delivery

**Nginx CDN Configuration:**

```nginx
# nginx.conf
server {
    listen 80;
    server_name cdn.your-domain.com;

    # Cache static assets
    location ~* \.(jpg|jpeg|png|gif|ico|css|js|svg|woff|woff2|ttf|eot)$ {
        root /var/www/static;
        expires 1y;
        add_header Cache-Control "public, immutable";
        add_header X-Cache-Status $upstream_cache_status;
    }

    # Cache uploaded files
    location /uploads/ {
        root /var/www;
        expires 30d;
        add_header Cache-Control "public";
    }
}
```

**CloudFront Configuration:**

```yaml
# cloudfront-config.yaml
DistributionConfig:
  Origins:
    - Id: S3Origin
      DomainName: your-bucket.s3.amazonaws.com
      S3OriginConfig:
        OriginAccessIdentity: origin-access-identity/cloudfront/ABCDEFG

  DefaultCacheBehavior:
    TargetOriginId: S3Origin
    ViewerProtocolPolicy: redirect-to-https
    AllowedMethods:
      - GET
      - HEAD
      - OPTIONS
    CachedMethods:
      - GET
      - HEAD
    Compress: true
    DefaultTTL: 86400
    MaxTTL: 31536000
    MinTTL: 0
```

## Async Processing

### Celery Task Optimization

**Task Configuration:**

```python
# backend/app/core/celery.py
from celery import Celery
from app.core.config import settings

# Broker and result backend are derived from REDIS_HOST/PORT/PASSWORD:
# redis://.../0 (broker), redis://.../1 (backend)
celery_app = Celery(
    'clouisle',
    broker=REDIS_URL + '/0',
    backend=REDIS_URL + '/1',
    broker_connection_retry_on_startup=True,
)

celery_app.conf.update(
    # Performance
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,        # one task per worker process at a time
    worker_max_tasks_per_child=100,      # recycle worker processes every 100 tasks

    # Serialization
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',

    # Results
    result_expires=3600 * 24,            # 24 hours
    visibility_timeout=settings.CELERY_VISIBILITY_TIMEOUT_SECONDS,
)
```

**Task Routing:**

```python
# backend/app/core/celery.py — task routes
celery_app.conf.task_routes = {
    'app.tasks.knowledge_base.*': {'queue': 'knowledge'},
    'app.tasks.workflow.*': {'queue': 'workflow'},
    'app.tasks.sandbox.*': {'queue': 'sandbox'},
    'app.tasks.usage.*': {'queue': 'default'},
    'app.tasks.notification.*': {'queue': 'default'},
    'app.tasks.audit_log.*': {'queue': 'default'},
    'app.tasks.api_key.*': {'queue': 'default'},
    'app.tasks.password_expiration.*': {'queue': 'default'},
    'app.tasks.session_memory.*': {'queue': 'default'},
    # ... (see backend/app/core/celery.py for the complete route table)
}

# The supplied worker service consumes all three main queues:
#   python main.py worker -c 4 -Q default,knowledge,workflow
# The sandbox-worker service consumes only the sandbox queue:
#   python main.py sandbox-worker -c ${SANDBOX_WORKER_CONCURRENCY:-1}
```

### Message Queue Scaling

**Multiple Compose workers:**

The supplied Compose services can be scaled directly; worker and sandbox-worker have no published host ports:

```bash
docker compose up -d --scale worker=3 --scale sandbox-worker=2
```

For Docker Swarm, use a separate stack file with `deploy.replicas` and deploy it with `docker stack deploy`; ordinary `docker compose up` ignores those Swarm keys.

Knowledge-base and workflow tasks use the `knowledge` and `workflow` queues on the worker service; sandbox jobs use the separate `sandbox-worker` queue. Scale the corresponding service when queue lag appears.

## Vector Database Scaling

### Qdrant Optimization

**Collection Configuration:**

```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, OptimizersConfigDiff

client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

# Create optimized collection
client.create_collection(
    collection_name="documents",
    vectors_config=VectorParams(
        size=1536,
        distance=Distance.COSINE,
    ),
    optimizers_config=OptimizersConfigDiff(
        indexing_threshold=20000,
        memmap_threshold=50000,
    ),
    hnsw_config={
        "m": 16,
        "ef_construct": 100,
    },
)
```

**Qdrant Cluster:**
The following is an external Qdrant cluster design, not part of the supplied Compose or Kubernetes manifests (both deploy one Qdrant instance with one data volume). Treat it as a migration design: configure replication, peer discovery, storage, authentication, and client failover before using it in production.

```yaml
# docker-compose.yml
services:
  qdrant-1:
    image: qdrant/qdrant:v1.18.3
    environment:
      QDRANT__CLUSTER__ENABLED: "true"
      QDRANT__CLUSTER__P2P__PORT: 6335
    ports:
      - "6333:6333"
      - "6335:6335"

  qdrant-2:
    image: qdrant/qdrant:v1.18.3
    environment:
      QDRANT__CLUSTER__ENABLED: "true"
      QDRANT__CLUSTER__P2P__PORT: 6335
      QDRANT__CLUSTER__P2P__BOOTSTRAP__URI: "http://qdrant-1:6335"
    ports:
      - "6334:6333"
      - "6336:6335"
```

## Monitoring and Optimization

### Performance Monitoring

**Prometheus Metrics:**

```python
# app/core/metrics.py
from prometheus_client import Counter, Histogram, Gauge

# Request metrics
request_count = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

request_duration = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration',
    ['method', 'endpoint']
)

# Application metrics
active_users = Gauge(
    'active_users',
    'Number of active users'
)

queue_length = Gauge(
    'celery_queue_length',
    'Celery queue length',
    ['queue']
)

# Database metrics
db_connections = Gauge(
    'database_connections',
    'Active database connections'
)
```

### Query Optimization

> **Scope:** The shipped deployment has no `app/core/metrics.py`, Prometheus middleware, `/metrics` route, or ServiceMonitor. Use the authenticated admin observability endpoints for current metrics; the snippet below is a generic integration example only.
**Slow Query Logging:**

```sql
-- Enable slow query log
ALTER SYSTEM SET log_min_duration_statement = 1000;  -- Log queries > 1s
ALTER SYSTEM SET log_statement = 'all';
SELECT pg_reload_conf();

-- View slow queries
SELECT
    query,
    calls,
    total_time,
    mean_time,
    max_time
FROM pg_stat_statements
ORDER BY mean_time DESC
LIMIT 10;
```

**Query Analysis:**

```sql
-- Analyze query plan
EXPLAIN ANALYZE
SELECT * FROM conversations
WHERE user_id = 'user-123'
ORDER BY created_at DESC
LIMIT 20;

-- Check index usage
SELECT
    schemaname,
    tablename,
    indexname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
ORDER BY idx_scan ASC;
```

## Scaling Checklist

### Pre-Scaling Checklist

**✅ Before Scaling:**
- [ ] Identify bottlenecks
- [ ] Set performance targets
- [ ] Establish baseline metrics
- [ ] Review current architecture
- [ ] Plan scaling strategy
- [ ] Test in staging
- [ ] Prepare rollback plan
- [ ] Document changes

### Post-Scaling Verification

**✅ After Scaling:**
- [ ] Verify all services running
- [ ] Check health endpoints
- [ ] Monitor resource usage
- [ ] Test application functionality
- [ ] Verify load distribution
- [ ] Check error rates
- [ ] Review performance metrics
- [ ] Update documentation

## Cost Optimization

### Resource Optimization

**Right-Sizing:**
- Monitor actual resource usage
- Adjust limits based on metrics
- Use spot instances for non-critical workloads
- Schedule scaling based on traffic patterns

**Cost Monitoring:**
```python
# Track costs by component
costs = {
    'compute': {
        'backend': 500,
        'frontend': 200,
        'celery': 300,
    },
    'database': {
        'postgres': 400,
        'redis': 100,
        'qdrant': 200,
    },
    'storage': 150,
    'network': 100,
    'llm_api': 2000,
}

total_cost = sum(sum(v.values()) if isinstance(v, dict) else v for v in costs.values())
```

## Best Practices

**✅ Do:**
- Scale horizontally when possible
- Use connection pooling
- Implement caching strategically
- Monitor performance continuously
- Test scaling in staging
- Use auto-scaling
- Optimize database queries
- Use CDN for static assets
- Implement rate limiting
- Plan for peak traffic

**❌ Don't:**
- Scale without monitoring
- Ignore database optimization
- Skip caching
- Over-provision resources
- Forget about costs
- Scale without testing
- Ignore bottlenecks
- Use synchronous processing
- Skip load testing
- Forget documentation

## Related Documentation

- [Kubernetes Deployment](./kubernetes.md) - K8s deployment
- [Monitoring](../operations/monitoring.md) - Monitoring guide
- [Performance Tuning](../best-practices/performance-tuning.md) - Performance guidance
- [High Availability](./high-availability.md) - HA setup

---

**Last Updated**: 2026-02-11
