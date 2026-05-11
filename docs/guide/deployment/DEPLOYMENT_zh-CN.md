# 部署指南

本指南介绍如何在生产环境中使用 **Docker Compose** 或 **Kubernetes** 部署 Clouisle。

---

## 目录

- [架构总览](#架构总览)
- [前置要求](#前置要求)
- [构建镜像](#构建镜像)
- [Docker Compose 部署](#docker-compose-部署)
  - [快速开始](#快速开始)
  - [配置说明](#配置说明)
  - [卷挂载](#卷挂载)
  - [端口映射](#端口映射)
  - [自定义域名与 HTTPS](#自定义域名与-https)
  - [扩缩容](#扩缩容)
  - [运维操作](#运维操作)
- [Kubernetes 部署](#kubernetes-部署)
  - [快速开始（K8s）](#快速开始k8s)
  - [清单结构](#清单结构)
  - [Secrets 配置](#secrets-配置)
  - [持久化存储](#持久化存储)
  - [Ingress 与 TLS](#ingress-与-tls)
  - [扩缩容（K8s）](#扩缩容k8s)
  - [运维操作（K8s）](#运维操作k8s)
- [环境变量参考](#环境变量参考)
- [请求流与代理架构](#请求流与代理架构)
- [备份与恢复](#备份与恢复)
- [升级](#升级)
- [安全检查清单](#安全检查清单)
- [故障排查](#故障排查)

---

## 架构总览

Clouisle 使用 **2 个 Docker 镜像**，运行为 **4 个应用服务** + **3 个基础设施服务**：

```
                         ┌─────────────────────────────────────────────┐
                         │              Frontend Container             │
  Browser ──────────────►│  Nginx (:3000)                              │
                         │    ├── /api/*  ──► proxy to api:8000    │
                         │    ├── /_next/static/* ──► local files      │
                         │    └── /*  ──► Node.js SSR (:3001 internal) │
                         └──────────────────┬──────────────────────────┘
                                            │
                         ┌──────────────────▼──────────────────────────┐
                         │             Backend Container               │
                         │  Gunicorn + UvicornWorker (:8000)           │
                         │    └── FastAPI application                  │
                         └──────┬──────────┬───────────────────────────┘
                                │          │
              ┌─────────────────┤          ├─────────────────┐
              ▼                 ▼          ▼                 ▼
         PostgreSQL          Redis      Qdrant         Celery Worker
           (:5432)          (:6379)    (:6333)         (background)
                                                       Celery Beat
                                                       (scheduler)
```

| 镜像 | 服务 | 说明 |
|------|------|------|
| `clouisle-backend` | api, worker, beat | Python 3.13：API 服务、Celery worker、Celery beat |
| `clouisle-sandbox-worker` | sandbox-worker | 沙箱任务执行和产物上传 |
| `clouisle-frontend` | frontend | Next.js standalone（SSR） |

后端镜像被 3 个服务复用，沙箱使用独立镜像，通过启动命令区分：

| 服务 | 命令 | 副本数 |
|------|------|--------|
| api | `python main.py server -H 0.0.0.0 -w 4 --no-reload` | 1+ |
| worker | `python main.py worker -c 4 -Q default,workflow` | 1+ |
| sandbox-worker | `python main.py sandbox-worker -c ${SANDBOX_WORKER_CONCURRENCY:-1}` | 1+ |
| beat | `python main.py beat` | **必须为 1** |

> **重要**：beat 服务必须始终保持 1 个副本。运行多个 beat 会导致定时任务重复执行。

---

## 前置要求

| 要求 | 最低配置 | 推荐配置 |
|------|----------|----------|
| Docker | 24.0+ | 最新版 |
| Docker Compose | v2.20+ | 最新版 |
| Kubernetes（如使用 K8s） | 1.25+ | 1.28+ |
| 内存 | 4 GB | 8 GB+ |
| 磁盘 | 20 GB | 50 GB+ |
| CPU | 2 核 | 4 核+ |

---

## 构建镜像

所有命令都在**项目根目录**执行：

```bash
# Backend image (shared by api, worker, beat services)
docker build -f deploy/dockerfiles/backend.Dockerfile -t clouisle-backend:latest .

# Sandbox worker image
docker build -f deploy/dockerfiles/sandbox-worker.Dockerfile -t clouisle-sandbox-worker:latest .

# Frontend image (Next.js standalone)
docker build -f deploy/dockerfiles/frontend.Dockerfile -t clouisle-frontend:latest .
```

私有镜像仓库示例：

```bash
docker tag clouisle-backend:latest registry.example.com/clouisle/clouisle-backend:latest
docker tag clouisle-sandbox-worker:latest registry.example.com/clouisle/clouisle-sandbox-worker:latest
docker tag clouisle-frontend:latest registry.example.com/clouisle/clouisle-frontend:latest
docker push registry.example.com/clouisle/clouisle-backend:latest
docker push registry.example.com/clouisle/clouisle-sandbox-worker:latest
docker push registry.example.com/clouisle/clouisle-frontend:latest
```

---

## Kubernetes Helm 部署

Kubernetes 推荐使用 Helm 部署：

```bash
helm lint deploy/helm/clouisle
helm upgrade --install clouisle deploy/helm/clouisle \
  --namespace clouisle \
  --create-namespace
```

生产环境建议先创建 `clouisle-secret`，再使用生产 values：

```bash
helm upgrade --install clouisle deploy/helm/clouisle \
  --namespace clouisle \
  --create-namespace \
  -f deploy/helm/clouisle/values-production.yaml
```

单文件 manifest 仍保留在 `deploy/k8s/clouisle.yaml`，用于 fallback 或调试。

## Docker Compose 部署

### 快速开始

```bash
cd deploy

# 1. Create and edit environment file
cp .env.example .env

# 2. Generate secure passwords (run each command, paste results into .env)
openssl rand -base64 32    # → SECRET_KEY
openssl rand -base64 16    # → POSTGRES_PASSWORD
openssl rand -base64 16    # → REDIS_PASSWORD
openssl rand -base64 16    # → QDRANT_API_KEY

# 3. Build images and start all services
docker compose up -d --build

# 4. Verify all services are healthy
docker compose ps
```

### 配置说明

启动前请编辑 `deploy/.env`。以下变量**必须**修改：

| 变量 | 原因 | 示例 |
|------|------|------|
| `SECRET_KEY` | JWT 签名密钥，默认值不安全 | `openssl rand -base64 32` |
| `POSTGRES_PASSWORD` | 数据库访问密码 | `openssl rand -base64 16` |
| `REDIS_PASSWORD` | 缓存/队列访问密码 | `openssl rand -base64 16` |
| `QDRANT_API_KEY` | 向量数据库访问密钥 | `openssl rand -base64 16` |

以下变量在生产域名下建议修改：

| 变量 | 默认值 | 生产示例 |
|------|--------|----------|
| `API_BASE_URL` | `http://localhost:8000` | `https://api.example.com` |
| `FRONTEND_URL` | `http://localhost:3000` | `https://example.com` |
| `BACKEND_CORS_ORIGINS` | `http://localhost:3000` | `https://example.com` |

> **说明**：`POSTGRES_SERVER`、`REDIS_HOST`、`QDRANT_URL` 会在 `docker-compose.yml` 的 `environment` 中被覆盖为 Docker 服务名（`db`、`redis`、`qdrant`）。无需在 `.env` 里修改它们。

### 卷挂载

Docker Compose 使用命名卷持久化数据：

| 卷 | 容器路径 | 用途 | 数据丢失影响 |
|----|----------|------|--------------|
| `postgres_data` | `/var/lib/postgresql/data` | 数据库文件 | **全部数据丢失** |
| `redis_data` | `/data` | 缓存与 Celery broker 状态 | 队列丢失，可恢复 |
| `qdrant_data` | `/qdrant/storage` | 向量嵌入数据 | 需重建知识库索引 |
| `uploads_data` | `/app/uploads` | 用户上传文件 | 上传文档丢失 |

如需使用主机路径挂载（便于备份），可替换为：

```yaml
# In docker-compose.yml, replace:
volumes:
  postgres_data:

# With:
volumes:
  postgres_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /data/clouisle/postgres
```

或者直接在服务中指定：

```yaml
volumes:
  - /data/clouisle/postgres:/var/lib/postgresql/data
  - /data/clouisle/uploads:/app/uploads
```

> **重要**：`uploads_data` 在 `backend` 与 `worker` 间共享。两者都需要读写权限以处理上传文档。若使用主机路径挂载，请在启动前确保目录存在且权限正确。

### 端口映射

默认暴露端口：

| 服务 | 主机端口 | 容器端口 | 用途 |
|------|----------|----------|------|
| frontend | 3000 | 3000 | Web UI（Nginx） |
| backend | 8000 | 8000 | API（Gunicorn） |
| db | 5432 | 5432 | PostgreSQL |
| redis | 6379 | 6379 | Redis |
| qdrant | 6333 | 6333 | Qdrant |

**生产环境**建议仅暴露 frontend 端口，并放在反向代理后。请移除或注释基础设施端口：

```yaml
# In docker-compose.yml, remove these lines for production:
  db:
    ports:
      - "5432:5432"    # Remove — no external DB access needed
  redis:
    ports:
      - "6379:6379"    # Remove
  qdrant:
    ports:
      - "6333:6333"    # Remove
  api:
    ports:
      - "8000:8000"    # Remove — frontend Nginx proxies API requests
```

### 自定义域名与 HTTPS

在生产环境使用自定义域名时，建议在 frontend 容器前增加外部反向代理（如 Nginx、Caddy、Traefik）：

**方案 A：Caddy（自动 HTTPS）**

```
# Caddyfile
example.com {
    reverse_proxy localhost:3000
}
```

**方案 B：外部 Nginx**

```nginx
server {
    listen 443 ssl http2;
    server_name example.com;

    ssl_certificate     /etc/ssl/certs/example.com.pem;
    ssl_certificate_key /etc/ssl/private/example.com.key;

    client_max_body_size 100m;

    location / {
        proxy_pass http://127.0.0.1:3000;

        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket
        proxy_http_version 1.1;
        proxy_set_header Upgrade    $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Streaming
        proxy_buffering off;
        proxy_read_timeout 300s;
    }
}
```

启用 HTTPS 后，同时更新如下环境变量：

```bash
API_BASE_URL=https://example.com
FRONTEND_URL=https://example.com
BACKEND_CORS_ORIGINS=https://example.com
```

### 扩缩容

```bash
# Scale Celery workers (safe to run multiple)
docker compose up -d --scale worker=4

# Scale backend API (safe to run multiple behind Nginx)
docker compose up -d --scale api=2

# NEVER scale beat beyond 1
# docker compose up -d --scale beat=2  ← DO NOT DO THIS
```

当 backend 扩容到多个副本时，移除主机端口映射避免冲突：

```yaml
api:
    # Remove: ports: ["8000:8000"]
    expose:
      - "8000"
```

### 运维操作

```bash
# View logs (follow mode)
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f frontend

# View logs for a specific time range
docker compose logs --since 1h api

# Restart a single service (zero-downtime for stateless services)
docker compose restart api

# Stop all services
docker compose down

# Stop and destroy all data (CAUTION)
docker compose down -v

# Update images and restart
docker compose pull
docker compose up -d --build
```

---

## Kubernetes 部署

### 快速开始（K8s）

所有资源都在单一文件中定义：`deploy/k8s/clouisle.yaml`。

```bash
# 1. Edit the manifest — replace secret placeholders and set your domain
vi deploy/k8s/clouisle.yaml

# 2. Apply everything
kubectl apply -f deploy/k8s/clouisle.yaml

# 3. Wait for infrastructure
kubectl -n clouisle wait --for=condition=ready pod -l app=postgres --timeout=120s
kubectl -n clouisle wait --for=condition=ready pod -l app=redis --timeout=120s
kubectl -n clouisle wait --for=condition=ready pod -l app=qdrant --timeout=120s

# 4. Verify all pods
kubectl -n clouisle get pods
```

### 清单结构

该清单包含 11 组资源，并使用 YAML anchor 去重重复配置：

| # | 资源 | 类型 | 说明 |
|---|------|------|------|
| 1 | Namespace | Namespace | `clouisle` |
| 2 | ConfigMap | ConfigMap | 非敏感配置 |
| 3 | Secret | Secret | 密码与密钥（**必须编辑**） |
| 4 | PostgreSQL | StatefulSet + Service + PVC | Headless Service，10Gi 存储 |
| 5 | Redis | Deployment + Service | |
| 6 | Qdrant | StatefulSet + Service + PVC | Headless Service，10Gi 存储 |
| 7 | Backend | Deployment + Service | 2 副本，端口 8000 |
| 8 | Worker | Deployment | 2 副本，无 Service |
| 9 | Beat | Deployment | 1 副本，`Recreate` 策略 |
| 10 | Frontend | Deployment + Service | 2 副本，端口 3000 |
| 11 | Ingress | Ingress | `/api` → backend，`/` → frontend |

### Secrets 配置

应用前，先替换 Secret 段中的 base64 占位值：

```bash
# Generate base64-encoded values
echo -n 'your-strong-secret-key' | base64
echo -n 'your-postgres-password' | base64
echo -n 'your-redis-password' | base64
echo -n 'your-qdrant-api-key' | base64
```

在 `clouisle.yaml` 中替换：

```yaml
data:
  SECRET_KEY: <paste-base64-here>
  POSTGRES_PASSWORD: <paste-base64-here>
  REDIS_PASSWORD: <paste-base64-here>
  QDRANT_API_KEY: <paste-base64-here>
```

> **提示**：生产环境建议使用外部密钥管理（Vault、AWS Secrets Manager 等）配合 External Secrets Operator，而不是将明文/编码后的密钥直接放在 YAML 中。

### 持久化存储

| PVC | 大小 | 使用方 | StorageClass |
|-----|------|--------|--------------|
| `postgres-data` | 10Gi | PostgreSQL | default |
| `qdrant-data` | 10Gi | Qdrant | default |

如需修改容量或存储类，编辑 PVC 定义：

```yaml
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: your-storage-class    # Add this line
  resources:
    requests:
      storage: 50Gi                       # Adjust size
```

backend 与 worker 的 `uploads` 卷默认使用 `emptyDir`。生产环境请改为 PVC 或共享文件系统（如 NFS、EFS），以便上传文件在 Pod 重启后仍保留，且 backend/worker 均可访问：

```yaml
# Replace in the anchors section:
- &uploads-volume
  name: uploads
  persistentVolumeClaim:
    claimName: clouisle-uploads

# Add a new PVC:
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: clouisle-uploads
  namespace: clouisle
spec:
  accessModes: [ReadWriteMany]    # Must be RWX for multi-pod access
  resources:
    requests:
      storage: 20Gi
```

> **重要**：`ReadWriteMany` 需要支持 RWX 的存储类（NFS、CephFS、EFS 等）。常见块存储（如 gp2、gp3）仅支持 `ReadWriteOnce`。

### Ingress 与 TLS

编辑 Ingress 区段，设置你的域名：

```yaml
spec:
  ingressClassName: nginx
  rules:
    - host: your-domain.com        # ← Change this
```

启用 TLS：

```yaml
spec:
  ingressClassName: nginx
  tls:
    - hosts:
        - your-domain.com
      secretName: clouisle-tls      # cert-manager or manual TLS secret
  rules:
    - host: your-domain.com
```

使用 cert-manager（自动 Let's Encrypt）：

```yaml
metadata:
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
```

同时更新 ConfigMap：

```yaml
data:
  API_BASE_URL: "https://your-domain.com"
  FRONTEND_URL: "https://your-domain.com"
  BACKEND_CORS_ORIGINS: "https://your-domain.com"
```

### 扩缩容（K8s）

```bash
# Scale workers
kubectl -n clouisle scale deployment worker --replicas=4

# Scale backend
kubectl -n clouisle scale deployment api --replicas=3

# Scale frontend
kubectl -n clouisle scale deployment frontend --replicas=3

# NEVER scale beat beyond 1
```

自动扩缩容示例：

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api-hpa
  namespace: clouisle
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
```

### 运维操作（K8s）

```bash
# View pod status
kubectl -n clouisle get pods -o wide

# View logs
kubectl -n clouisle logs -f deployment/api
kubectl -n clouisle logs -f deployment/worker
kubectl -n clouisle logs -f deployment/beat
kubectl -n clouisle logs -f deployment/frontend

# View logs for a specific pod
kubectl -n clouisle logs -f <pod-name>

# Restart a deployment (rolling restart)
kubectl -n clouisle rollout restart deployment api

# Check rollout status
kubectl -n clouisle rollout status deployment api

# Execute a command in a pod
kubectl -n clouisle exec -it deployment/api -- bash

# View resource usage
kubectl -n clouisle top pods
```

---

## 环境变量参考

### 必填（必须修改）

| 变量 | 描述 | 生成方式 |
|------|------|----------|
| `SECRET_KEY` | JWT 签名密钥。修改后会使现有会话全部失效。 | `openssl rand -base64 32` |
| `POSTGRES_PASSWORD` | PostgreSQL 密码 | `openssl rand -base64 16` |

### 推荐（生产环境应修改）

| 变量 | 默认值 | 描述 |
|------|--------|------|
| `REDIS_PASSWORD` | *(empty)* | Redis 密码。为空表示不鉴权。 |
| `QDRANT_API_KEY` | *(empty)* | Qdrant API 密钥。为空表示不鉴权。 |
| `API_BASE_URL` | `http://localhost:8000` | 后端访问地址，用于文件访问与 SSO 回调。生产环境应设置为真实域名。 |
| `FRONTEND_URL` | `http://localhost:3000` | 前端地址，用于 SSO 重定向 URI。生产环境应设置为真实域名。 |
| `BACKEND_CORS_ORIGINS` | `http://localhost:3000` | 允许的 CORS 源（逗号分隔）。必须包含前端域名。 |

### 可选

| 变量 | 默认值 | 描述 |
|------|--------|------|
| `PROJECT_NAME` | `Clouisle` | 展示名称 |
| `TIMEZONE` | `Asia/Shanghai` | 服务器时区（影响定时任务） |
| `POSTGRES_SERVER` | `localhost` | PostgreSQL 主机。部署配置中会覆盖为 Compose 的 `db` 或 K8s 的 `postgres`。 |
| `POSTGRES_PORT` | `5432` | PostgreSQL 端口 |
| `POSTGRES_USER` | `postgres` | PostgreSQL 用户 |
| `POSTGRES_DB` | `clouisle` | PostgreSQL 数据库名 |
| `DATABASE_URL` | *(auto-assembled)* | 完整 PostgreSQL DSN。若设置则覆盖 `POSTGRES_*` 变量。 |
| `REDIS_HOST` | `localhost` | Redis 主机。部署配置中会覆盖为 `redis`。 |
| `REDIS_PORT` | `6379` | Redis 端口 |
| `VECTOR_BACKEND` | `qdrant` | 向量数据库后端 |
| `QDRANT_URL` | `http://localhost:6333` | Qdrant 地址。部署配置中会覆盖为 `http://qdrant:6333`。 |
| `QDRANT_COLLECTION_PREFIX` | `kb_dim` | Qdrant collection 前缀 |
| `QDRANT_DISTANCE` | `Cosine` | 向量距离度量 |
| `TAVILY_API_KEY` | *(empty)* | Tavily 网页搜索 API Key（用于 Agent 网页搜索能力） |

---

## 请求流与代理架构

理解请求流对于调试和配置外部反向代理非常关键。

### 客户端 API 请求流

```
Browser
  │
  ├── Page requests (HTML/SSR) ──► Nginx (:3000) ──► Node.js (:3001 internal)
  │
  └── API requests (/api/*) ──► Nginx (:3000) ──► Backend Gunicorn (:8000)
```

frontend 容器中运行两个进程：
1. **Nginx**（3000 端口，外部）负责路由、静态文件和代理
2. **Node.js**（3001 端口，内部）负责 SSR

### Header 转发

Nginx 在 `/api/*` 请求中向 backend 转发以下 Header：

| Header | 值 | 用途 |
|--------|----|------|
| `Host` | 原始 Host | 虚拟主机路由 |
| `X-Real-IP` | 客户端 IP | 真实客户端地址 |
| `X-Forwarded-For` | 客户端 IP 链 | 代理链路追踪 |
| `X-Forwarded-Proto` | `http` 或 `https` | 原始协议 |
| `X-Forwarded-Host` | 原始 Host | 原始主机名 |
| `X-Forwarded-Port` | 原始端口 | 原始端口 |
| `Accept-Language` | 浏览器语言 | i18n（后端兜底） |
| `X-Language` | 应用语言 | i18n（前端设置，优先级更高） |

Gunicorn 配置了 `--forwarded-allow-ips *` 以信任这些代理头。

### 如使用外部反向代理

如果在 frontend 容器前再加一层反向代理（Nginx、Caddy、Traefik、云 LB），请确保链路为：

```
External Proxy → Frontend Nginx (:3000) → Backend Gunicorn (:8000)
```

外部代理必须正确设置 `X-Real-IP` 和 `X-Forwarded-For`，frontend Nginx 会继续透传给 backend。

---

## 备份与恢复

### PostgreSQL

```bash
# Docker Compose — backup
docker compose exec db pg_dump -U postgres clouisle > backup_$(date +%Y%m%d).sql

# Docker Compose — restore
docker compose exec -T db psql -U postgres clouisle < backup_20260206.sql

# Kubernetes — backup
kubectl -n clouisle exec statefulset/postgres -- pg_dump -U postgres clouisle > backup.sql

# Kubernetes — restore
kubectl -n clouisle exec -i statefulset/postgres -- psql -U postgres clouisle < backup.sql
```

### Qdrant

```bash
# Docker Compose — backup the volume
docker run --rm -v deploy_qdrant_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/qdrant_backup.tar.gz -C /data .

# Kubernetes — use Qdrant's snapshot API
kubectl -n clouisle exec statefulset/qdrant -- \
  wget -qO- -post-data '{}' http://localhost:6333/snapshots
```

### 上传文件

```bash
# Docker Compose
docker run --rm -v deploy_uploads_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/uploads_backup.tar.gz -C /data .

# Kubernetes (if using PVC)
kubectl -n clouisle exec deployment/api -- tar czf - /app/uploads > uploads_backup.tar.gz
```

### 自动备份计划

生产环境建议配置 CronJob（K8s）或主机 cron（Docker）执行每日备份：

```yaml
# K8s CronJob example
apiVersion: batch/v1
kind: CronJob
metadata:
  name: postgres-backup
  namespace: clouisle
spec:
  schedule: "0 2 * * *"    # Daily at 2:00 AM
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: backup
              image: postgres:16
              command:
                - sh
                - -c
                - pg_dump -h postgres -U postgres clouisle | gzip > /backup/clouisle_$(date +%Y%m%d).sql.gz
              env:
                - name: PGPASSWORD
                  valueFrom:
                    secretKeyRef:
                      name: clouisle-secret
                      key: POSTGRES_PASSWORD
              volumeMounts:
                - name: backup
                  mountPath: /backup
          restartPolicy: OnFailure
          volumes:
            - name: backup
              persistentVolumeClaim:
                claimName: backup-pvc
```

---

## 升级

### Docker Compose

```bash
cd deploy

# 1. Pull latest code
git pull

# 2. Rebuild images
docker compose build

# 3. Rolling restart (services restart one by one)
docker compose up -d

# 4. Verify
docker compose ps
docker compose logs --tail=50 backend
```

### Kubernetes

```bash
# 1. Build and push new images
docker build -f deploy/dockerfiles/backend.Dockerfile -t registry.example.com/clouisle/api:v2.0.0 .
docker build -f deploy/dockerfiles/frontend.Dockerfile -t registry.example.com/clouisle/frontend:v2.0.0 .
docker push registry.example.com/clouisle/api:v2.0.0
docker push registry.example.com/clouisle/frontend:v2.0.0

# 2. Update image tags in clouisle.yaml (the anchors at the top)
#    - &backend-image registry.example.com/clouisle/api:v2.0.0
#    - &frontend-image registry.example.com/clouisle/frontend:v2.0.0

# 3. Apply
kubectl apply -f deploy/k8s/clouisle.yaml

# 4. Monitor rollout
kubectl -n clouisle rollout status deployment api
kubectl -n clouisle rollout status deployment worker
kubectl -n clouisle rollout status deployment frontend
```

> **说明**：若有数据库迁移，请先执行迁移再更新 backend Deployment。具体步骤请查看发布说明。

---

## 安全检查清单

- [ ] **修改所有默认密码**：`SECRET_KEY`、`POSTGRES_PASSWORD`、`REDIS_PASSWORD`、`QDRANT_API_KEY`
- [ ] **启用 HTTPS**：在外部反向代理或 K8s Ingress 做 TLS 终止
- [ ] **限制暴露端口**：生产环境仅暴露 3000（或反向代理后的 443），移除 DB/Redis/Qdrant 的端口映射
- [ ] **设置 CORS 来源**：`BACKEND_CORS_ORIGINS` 仅包含真实前端域名，不要使用 `*`
- [ ] **更新 `API_BASE_URL` 与 `FRONTEND_URL`**：必须与生产域名一致，否则 SSO 与内部文件访问可能异常
- [ ] **网络隔离**：Compose 下基础设施服务（db、redis、qdrant）不应对外访问；K8s 下默认使用 ClusterIP（不对外）
- [ ] **定期备份**：配置 PostgreSQL 与 Qdrant 自动备份
- [ ] **资源限制**：按实际负载调整 K8s 清单中的 CPU/内存 limits
- [ ] **镜像扫描**：部署前对 Docker 镜像进行漏洞扫描

---

## 故障排查

### Backend 无法连接数据库

```bash
# Docker Compose
docker compose logs db          # Check PostgreSQL logs
docker compose exec db pg_isready -U postgres

# Kubernetes
kubectl -n clouisle logs statefulset/postgres
kubectl -n clouisle exec statefulset/postgres -- pg_isready -U postgres
```

常见原因：
- `POSTGRES_PASSWORD` 在数据库与 backend 中不一致
- backend 启动时数据库尚未就绪（通常 healthcheck 会避免）
- `POSTGRES_SERVER` 错误（Compose 应为 `db`，K8s 应为 `postgres`）

### Frontend 访问 API 返回 502

frontend Nginx 将 `/api/*` 代理到 `http://api:8000`。502 说明 backend 不可达。

```bash
# Check if backend is running
docker compose ps api
# or
kubectl -n clouisle get pods -l app=api

# Test connectivity from frontend container
docker compose exec frontend wget -qO- http://api:8000/api/v1/health
```

### Worker 不处理任务

```bash
# Check worker logs
docker compose logs worker
# or
kubectl -n clouisle logs deployment/worker

# Verify Redis connectivity
docker compose exec worker python -c "import redis; r = redis.Redis(host='redis'); print(r.ping())"
```

常见原因：
- `REDIS_PASSWORD` 不一致
- Redis 尚未就绪
- 队列名称配置错误

### Beat 重复执行定时任务

确保只有 1 个 beat 实例在运行：

```bash
# Docker Compose
docker compose ps beat    # Should show exactly 1 replica

# Kubernetes
kubectl -n clouisle get pods -l app=beat    # Should show exactly 1 pod
```

K8s 中 beat Deployment 使用 `strategy: Recreate`，确保新 Pod 启动前旧 Pod 已完全终止。

### 上传文件不可访问

`uploads` 卷必须在 `backend` 与 `worker` 之间共享：

```bash
# Docker Compose — verify both mount the same volume
docker compose exec api ls -la /app/uploads
docker compose exec worker ls -la /app/uploads
```

在 Kubernetes 中，若使用 `emptyDir`，Pod 重启后文件会丢失。请改为 `ReadWriteMany` 模式的 PVC（见[持久化存储](#持久化存储)）。

### 内存不足 / OOMKilled

检查资源使用并调整限制：

```bash
# Docker
docker stats

# Kubernetes
kubectl -n clouisle top pods
kubectl -n clouisle describe pod <pod-name>    # Check "Last State" for OOMKilled
```

可在 `docker-compose.yml`（`deploy.resources`）或 `clouisle.yaml`（`resources` 段）中调大限制。

### LLM 请求超时

默认代理超时为 300 秒（5 分钟）。若 LLM 操作较长：

- Frontend Nginx：编辑 `deploy/nginx/default.conf` 中的 `proxy_read_timeout`
- K8s Ingress：编辑 `nginx.ingress.kubernetes.io/proxy-read-timeout` 注解
- Gunicorn：编辑 backend Dockerfile CMD 中的 `--timeout`
