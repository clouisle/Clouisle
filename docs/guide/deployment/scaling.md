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
  backend:
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G
        reservations:
          cpus: '2'
          memory: 4G

  postgres:
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
# Increase Uvicorn workers
uvicorn app.main:app --workers 8 --host 0.0.0.0 --port 8000

# Or in docker-compose.yml
command: uvicorn app.main:app --workers 8 --host 0.0.0.0 --port 8000
```

**Celery Workers:**

```yaml
# Increase Celery concurrency
celery -A app.core.celery worker --concurrency=8 --loglevel=info

# Or in docker-compose.yml
command: celery -A app.core.celery worker --concurrency=8 --loglevel=info
```

## Horizontal Scaling

### Add Backend Replicas

**Docker Compose:**

```yaml
# docker-compose.yml
services:
  backend:
    deploy:
      replicas: 3
      update_config:
        parallelism: 1
        delay: 10s
      restart_policy:
        condition: on-failure
```

**Kubernetes:**

```yaml
# api-deployment.yaml
spec:
  replicas: 5
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
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
  backend:
    deploy:
      replicas: 3
      placement:
        max_replicas_per_node: 1
      update_config:
        parallelism: 1
        delay: 10s
```

## Load Balancing

### Nginx Load Balancer

```nginx
# nginx.conf
upstream api {
    least_conn;
    server api-1:8000 weight=1 max_fails=3 fail_timeout=30s;
    server api-2:8000 weight=1 max_fails=3 fail_timeout=30s;
    server api-3:8000 weight=1 max_fails=3 fail_timeout=30s;
    keepalive 32;
}

upstream frontend {
    least_conn;
    server frontend-1:3000 weight=1;
    server frontend-2:3000 weight=1;
    server frontend-3:3000 weight=1;
    keepalive 32;
}

server {
    listen 80;
    server_name your-domain.com;

    location /api {
        proxy_pass http://api;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;

        # Buffering
        proxy_buffering on;
        proxy_buffer_size 4k;
        proxy_buffers 8 4k;
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
    # health_check interval=10s fails=3 passes=2 uri=/health;
}
```

## Database Scaling

### PostgreSQL Optimization

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
clouisle = host=postgres port=5432 dbname=clouisle

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
      DATABASES_HOST: postgres
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
      - postgres

  backend:
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

**PostgreSQL Replication:**

```yaml
# docker-compose.yml
services:
  postgres-primary:
    image: postgres:14
    environment:
      POSTGRES_USER: clouisle
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: clouisle
    volumes:
      - postgres-primary-data:/var/lib/postgresql/data
    command: >
      postgres
      -c wal_level=replica
      -c max_wal_senders=3
      -c max_replication_slots=3

  postgres-replica:
    image: postgres:14
    environment:
      POSTGRES_USER: clouisle
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      PGUSER: clouisle
      PGPASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres-replica-data:/var/lib/postgresql/data
    command: >
      bash -c "
      until pg_basebackup -h postgres-primary -D /var/lib/postgresql/data -U clouisle -v -P -W; do
        echo 'Waiting for primary to be ready...'
        sleep 1
      done
      echo 'standby_mode = on' > /var/lib/postgresql/data/recovery.conf
      echo 'primary_conninfo = \"host=postgres-primary port=5432 user=clouisle password=${POSTGRES_PASSWORD}\"' >> /var/lib/postgresql/data/recovery.conf
      postgres
      "
```

## Caching Strategy

### Redis Caching

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
# app/core/celery.py
from celery import Celery

celery_app = Celery(
    'clouisle',
    broker=REDIS_URL,
    backend=REDIS_URL,
    broker_connection_retry_on_startup=True,
)

celery_app.conf.update(
    # Performance
    task_acks_late=True,
    worker_prefetch_multiplier=4,
    worker_max_tasks_per_child=1000,

    # Timeouts
    task_soft_time_limit=300,
    task_time_limit=600,

    # Serialization
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],

    # Results
    result_expires=3600,
    result_backend_transport_options={
        'master_name': 'mymaster',
    },
)
```

**Task Routing:**

```python
# Route tasks to specific queues
celery_app.conf.task_routes = {
    'app.tasks.document.*': {'queue': 'documents'},
    'app.tasks.embedding.*': {'queue': 'embeddings'},
    'app.tasks.workflow.*': {'queue': 'workflows'},
    'app.tasks.email.*': {'queue': 'emails'},
}

# Start workers for specific queues
# celery -A app.core.celery worker -Q documents --concurrency=4
# celery -A app.core.celery worker -Q embeddings --concurrency=2
# celery -A app.core.celery worker -Q workflows --concurrency=8
```

### Message Queue Scaling

**Multiple Celery Workers:**

```yaml
# docker-compose.yml
services:
  celery-worker-general:
    image: clouisle-backend
    command: celery -A app.core.celery worker -Q default --concurrency=8
    deploy:
      replicas: 3

  celery-worker-documents:
    image: clouisle-backend
    command: celery -A app.core.celery worker -Q documents --concurrency=4
    deploy:
      replicas: 2

  celery-worker-embeddings:
    image: clouisle-backend
    command: celery -A app.core.celery worker -Q embeddings --concurrency=2
    deploy:
      replicas: 2
```

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

```yaml
# docker-compose.yml
services:
  qdrant-1:
    image: qdrant/qdrant:v1.7.4
    environment:
      QDRANT__CLUSTER__ENABLED: "true"
      QDRANT__CLUSTER__P2P__PORT: 6335
    ports:
      - "6333:6333"
      - "6335:6335"

  qdrant-2:
    image: qdrant/qdrant:v1.7.4
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
- [Performance Tuning](../best-practices/performance.md) - Performance tips
- [High Availability](./high-availability.md) - HA setup

---

**Last Updated**: 2026-02-11
