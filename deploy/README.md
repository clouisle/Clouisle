# Clouisle Docker Deployment

This directory contains Docker deployment configurations for Clouisle.

## Docker Images

All images are available on GitHub Container Registry:

```
ghcr.io/yunhai-dev/clouisle:all-in-one
ghcr.io/yunhai-dev/clouisle:app
ghcr.io/yunhai-dev/clouisle:frontend
ghcr.io/yunhai-dev/clouisle:backend
ghcr.io/yunhai-dev/clouisle:worker
ghcr.io/yunhai-dev/clouisle:beat
```

## Deployment Options

### 1. All-in-One (`clouisle:all-in-one`)

Single container with everything included: Frontend, Backend, Worker, Beat, PostgreSQL, Redis, Qdrant, and Nginx.

**Best for:** Development, testing, demos, or small single-server deployments.

```bash
docker-compose -f deploy/docker-compose.all-in-one.yml up -d
```

### 2. App (`clouisle:app`)

Single application container with Frontend, Backend, Worker, and Beat. Requires external databases.

**Best for:** Simple production deployments where you want to manage databases separately.

```bash
docker-compose -f deploy/docker-compose.app.yml up -d
```

### 3. Microservices (Separate Images)

Four separate containers for independent scaling:
- `clouisle:frontend` - Next.js frontend
- `clouisle:backend` - FastAPI backend
- `clouisle:worker` - Celery worker
- `clouisle:beat` - Celery beat scheduler

**Best for:** Production deployments requiring independent scaling and high availability.

```bash
docker-compose -f deploy/docker-compose.microservices.yml up -d
```

## Building Images Locally

If you need to build images locally:

```bash
# Build specific target
docker build --target all-in-one -t clouisle:all-in-one -f deploy/Dockerfile .
docker build --target app -t clouisle:app -f deploy/Dockerfile .
docker build --target frontend -t clouisle:frontend -f deploy/Dockerfile .
docker build --target backend -t clouisle:backend -f deploy/Dockerfile .
docker build --target worker -t clouisle:worker -f deploy/Dockerfile .
docker build --target beat -t clouisle:beat -f deploy/Dockerfile .
```

## Quick Start

### Using Docker Compose

```bash
# Option 1: All-in-One (simplest)
docker-compose -f deploy/docker-compose.all-in-one.yml up -d

# Option 2: App + External DBs
docker-compose -f deploy/docker-compose.app.yml up -d

# Option 3: Microservices (production)
docker-compose -f deploy/docker-compose.microservices.yml up -d
```

### Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Key variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | JWT signing key | `changethis-to-a-secure-random-secret-key` |
| `POSTGRES_PASSWORD` | Database password | `password` |
| `REDIS_PASSWORD` | Redis password | `clouisle-redis-cbd3c07d` |
| `QDRANT_API_KEY` | Qdrant API key | `clouisle-qdrant-cbd3c07d` |
| `TAVILY_API_KEY` | Tavily search API key | (optional) |

## Ports

| Deployment | Port | Description |
|------------|------|-------------|
| All-in-One | 80 | Nginx (unified entry point) |
| App / Microservices | 3000 | Next.js frontend |
| App / Microservices | 8000 | FastAPI backend |
| PostgreSQL | 5432 | Database (internal) |
| Redis | 6379 | Cache/Queue (internal) |
| Qdrant | 6333 | Vector DB (internal) |

## Volumes

| Volume | Description |
|--------|-------------|
| `postgres_data` | PostgreSQL database files |
| `redis_data` | Redis persistence |
| `qdrant_data` | Qdrant vector storage |
| `uploads_data` | User uploaded files |

## File Structure

```
deploy/
├── Dockerfile                      # Multi-stage Dockerfile
├── docker-compose.yml              # Infrastructure only (dev)
├── docker-compose.all-in-one.yml   # All-in-one deployment
├── docker-compose.app.yml          # App + external DBs
├── docker-compose.microservices.yml # Separate services
├── nginx/
│   └── nginx.conf                  # Nginx config for all-in-one
├── supervisor/
│   ├── all-in-one.conf             # Supervisor config for all-in-one
│   └── app.conf                    # Supervisor config for app
├── scripts/
│   └── all-in-one-entrypoint.sh    # Entrypoint for all-in-one
└── README.md                       # This file
```

## Production Recommendations

1. **Use microservices deployment** for better scaling and reliability
2. **Set strong passwords** for all services
3. **Use external managed databases** (RDS, ElastiCache, etc.) for production
4. **Add a reverse proxy** (Nginx, Traefik) for SSL termination
5. **Configure resource limits** in docker-compose
6. **Set up monitoring** (Prometheus, Grafana)
7. **Implement backup strategy** for PostgreSQL and Qdrant data

## Scaling Workers

For microservices deployment, scale workers independently:

```bash
# Scale to 3 worker instances
docker-compose -f deploy/docker-compose.microservices.yml up -d --scale worker=3
```

## Logs

```bash
# View all logs
docker-compose -f deploy/docker-compose.app.yml logs -f

# View specific service logs
docker-compose -f deploy/docker-compose.app.yml logs -f backend
docker-compose -f deploy/docker-compose.app.yml logs -f worker
```

## Troubleshooting

### Database connection issues
- Ensure database containers are healthy before starting app
- Check `POSTGRES_SERVER`, `REDIS_HOST` point to correct hostnames

### Frontend can't reach backend
- Verify `NEXT_PUBLIC_API_URL` is set correctly
- Check network connectivity between containers

### Worker not processing tasks
- Verify Redis connection
- Check worker logs for errors
- Ensure queues match (`default,workflow`)
