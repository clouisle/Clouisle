# Clouisle 部署指南

本文档提供 Clouisle 平台的完整部署指南，包括三种部署方案的详细说明。

## 目录

- [系统要求](#系统要求)
- [部署方案概览](#部署方案概览)
- [方案一：All-in-One 部署](#方案一all-in-one-部署)
- [方案二：App 部署](#方案二app-部署)
- [方案三：微服务部署](#方案三微服务部署)
- [环境变量配置](#环境变量配置)
- [反向代理配置](#反向代理配置)
- [SSL/HTTPS 配置](#sslhttps-配置)
- [数据备份与恢复](#数据备份与恢复)
- [监控与日志](#监控与日志)
- [常见问题](#常见问题)
- [升级指南](#升级指南)

---

## 系统要求

### 硬件要求

| 部署方案 | CPU | 内存 | 磁盘 |
|---------|-----|------|------|
| All-in-One | 2 核+ | 4 GB+ | 20 GB+ |
| App | 2 核+ | 4 GB+ | 20 GB+ |
| 微服务 | 4 核+ | 8 GB+ | 40 GB+ |

### 软件要求

- Docker 20.10+
- Docker Compose 2.0+
- (可选) Nginx 用于反向代理

### 网络要求

| 端口 | 用途 | 部署方案 |
|------|------|---------|
| 80 | HTTP 访问 | All-in-One |
| 443 | HTTPS 访问 | 所有（通过反向代理） |
| 3000 | 前端服务 | App / 微服务 |
| 8000 | 后端 API | App / 微服务 |

---

## 部署方案概览

Clouisle 提供三种部署方案，适用于不同场景：

| 方案 | 容器数量 | 适用场景 | 复杂度 |
|------|---------|---------|--------|
| **All-in-One** | 1 | 开发、测试、演示、小型部署 | 低 |
| **App** | 4 | 中小型生产环境 | 中 |
| **微服务** | 7 | 大型生产环境、需要独立扩展 | 高 |

### Docker 镜像

所有镜像托管在 GitHub Container Registry：

```
ghcr.io/yunhai-dev/clouisle:all-in-one   # 全栈镜像（含数据库）
ghcr.io/yunhai-dev/clouisle:app          # 应用镜像（前后端+Worker+Beat）
ghcr.io/yunhai-dev/clouisle:frontend     # 前端镜像
ghcr.io/yunhai-dev/clouisle:backend      # 后端 API 镜像
ghcr.io/yunhai-dev/clouisle:worker       # Celery Worker 镜像
ghcr.io/yunhai-dev/clouisle:beat         # Celery Beat 镜像
```

---

## 方案一：All-in-One 部署

单容器包含所有服务：Frontend、Backend、Worker、Beat、PostgreSQL、Redis、Qdrant、Nginx。

**优点**：部署简单，资源占用少，适合快速体验
**缺点**：不适合高可用场景，无法独立扩展

### 1.1 快速部署

```bash
# 创建部署目录
mkdir -p /opt/clouisle && cd /opt/clouisle

# 下载配置文件
curl -O https://raw.githubusercontent.com/yunhai-dev/Clouisle/main/deploy/docker-compose.all-in-one.yml
curl -O https://raw.githubusercontent.com/yunhai-dev/Clouisle/main/.env.example

# 创建环境配置
cp .env.example .env

# 编辑配置（至少修改 SECRET_KEY）
nano .env

# 启动服务
docker-compose -f docker-compose.all-in-one.yml up -d
```

### 1.2 环境配置

编辑 `.env` 文件：

```bash
# 必须修改
SECRET_KEY=your-secure-random-key-at-least-32-characters

# 可选修改
PROJECT_NAME=Clouisle
TIMEZONE=Asia/Shanghai
POSTGRES_PASSWORD=your-db-password
REDIS_PASSWORD=your-redis-password
QDRANT_API_KEY=your-qdrant-key
```

### 1.3 访问服务

部署完成后，访问 `http://your-server-ip` 即可使用。

### 1.4 数据持久化

All-in-One 模式使用以下 Docker volumes：

| Volume | 用途 |
|--------|------|
| `clouisle_postgres` | PostgreSQL 数据 |
| `clouisle_redis` | Redis 数据 |
| `clouisle_qdrant` | Qdrant 向量数据 |
| `clouisle_uploads` | 用户上传文件 |
| `clouisle_logs` | 应用日志 |

---

## 方案二：App 部署

应用容器（Frontend + Backend + Worker + Beat）+ 独立数据库容器。

**优点**：数据库独立管理，便于备份和维护
**缺点**：无法独立扩展各组件

### 2.1 快速部署

```bash
# 创建部署目录
mkdir -p /opt/clouisle && cd /opt/clouisle

# 下载配置文件
curl -O https://raw.githubusercontent.com/yunhai-dev/Clouisle/main/deploy/docker-compose.app.yml
curl -O https://raw.githubusercontent.com/yunhai-dev/Clouisle/main/.env.example

# 创建环境配置
cp .env.example .env
nano .env

# 启动服务
docker-compose -f docker-compose.app.yml up -d
```

### 2.2 服务架构

```
┌─────────────────────────────────────────────────────────┐
│                    docker-compose                        │
│  ┌─────────────────────────────────────────────────┐    │
│  │              clouisle-app (:3000, :8000)        │    │
│  │  ┌──────────┐ ┌──────────┐ ┌────────┐ ┌──────┐ │    │
│  │  │ Frontend │ │ Backend  │ │ Worker │ │ Beat │ │    │
│  │  └──────────┘ └──────────┘ └────────┘ └──────┘ │    │
│  └─────────────────────────────────────────────────┘    │
│                          │                               │
│         ┌────────────────┼────────────────┐             │
│         ▼                ▼                ▼             │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐        │
│  │ PostgreSQL │  │   Redis    │  │   Qdrant   │        │
│  │  (db)      │  │  (redis)   │  │  (qdrant)  │        │
│  └────────────┘  └────────────┘  └────────────┘        │
└─────────────────────────────────────────────────────────┘
```

### 2.3 访问服务

- 前端：`http://your-server-ip:3000`
- API：`http://your-server-ip:8000`
- API 文档：`http://your-server-ip:8000/docs`

### 2.4 使用外部数据库

如果你已有 PostgreSQL、Redis、Qdrant 服务，可以修改 `docker-compose.app.yml`：

```yaml
services:
  app:
    image: ghcr.io/yunhai-dev/clouisle:app
    ports:
      - "3000:3000"
      - "8000:8000"
    environment:
      # 指向外部数据库
      POSTGRES_SERVER: your-postgres-host
      POSTGRES_PORT: 5432
      POSTGRES_USER: your-user
      POSTGRES_PASSWORD: your-password
      POSTGRES_DB: clouisle
      REDIS_HOST: your-redis-host
      REDIS_PORT: 6379
      REDIS_PASSWORD: your-redis-password
      QDRANT_URL: http://your-qdrant-host:6333
      QDRANT_API_KEY: your-qdrant-key
      # ... 其他配置
    volumes:
      - uploads_data:/app/uploads
      - logs_data:/var/log/supervisor

volumes:
  uploads_data:
  logs_data:
```

---

## 方案三：微服务部署

各组件独立容器，支持独立扩展。

**优点**：高可用、可独立扩展、故障隔离
**缺点**：配置复杂、资源占用较多

### 3.1 快速部署

```bash
# 创建部署目录
mkdir -p /opt/clouisle && cd /opt/clouisle

# 下载配置文件
curl -O https://raw.githubusercontent.com/yunhai-dev/Clouisle/main/deploy/docker-compose.microservices.yml
curl -O https://raw.githubusercontent.com/yunhai-dev/Clouisle/main/.env.example

# 创建环境配置
cp .env.example .env
nano .env

# 启动服务
docker-compose -f docker-compose.microservices.yml up -d
```

### 3.2 服务架构

```
┌──────────────────────────────────────────────────────────────┐
│                      docker-compose                           │
│                                                               │
│  ┌──────────────┐  ┌──────────────┐                          │
│  │   frontend   │  │   backend    │                          │
│  │   (:3000)    │  │   (:8000)    │                          │
│  └──────────────┘  └──────────────┘                          │
│                           │                                   │
│         ┌─────────────────┼─────────────────┐                │
│         ▼                 ▼                 ▼                │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐             │
│  │   worker   │  │    beat    │  │   qdrant   │             │
│  └────────────┘  └────────────┘  └────────────┘             │
│         │                 │                                   │
│         └────────┬────────┘                                  │
│                  ▼                                            │
│  ┌────────────────────────────────────────────┐              │
│  │              PostgreSQL + Redis             │              │
│  └────────────────────────────────────────────┘              │
└──────────────────────────────────────────────────────────────┘
```

### 3.3 扩展 Worker

根据负载情况扩展 Worker 数量：

```bash
# 扩展到 3 个 Worker 实例
docker-compose -f docker-compose.microservices.yml up -d --scale worker=3
```

### 3.4 访问服务

- 前端：`http://your-server-ip:3000`
- API：`http://your-server-ip:8000`
- API 文档：`http://your-server-ip:8000/docs`

---

## 环境变量配置

### 完整配置说明

```bash
# =============================================================================
# 应用配置
# =============================================================================
PROJECT_NAME=Clouisle                    # 项目名称
SECRET_KEY=your-secret-key               # JWT 签名密钥（必须修改！）
TIMEZONE=Asia/Shanghai                   # 时区

# URL 配置（根据实际部署地址修改）
API_BASE_URL=http://localhost:8000       # 后端 API 地址
FRONTEND_URL=http://localhost:3000       # 前端地址

# =============================================================================
# PostgreSQL 数据库
# =============================================================================
POSTGRES_SERVER=localhost                # 数据库主机
POSTGRES_PORT=5432                       # 数据库端口
POSTGRES_USER=postgres                   # 数据库用户
POSTGRES_PASSWORD=password               # 数据库密码（生产环境必须修改！）
POSTGRES_DB=clouisle                     # 数据库名称

# 或使用完整 DSN（优先级更高）
# DATABASE_URL=postgres://user:pass@host:5432/dbname

# =============================================================================
# Redis 缓存/消息队列
# =============================================================================
REDIS_HOST=localhost                     # Redis 主机
REDIS_PORT=6379                          # Redis 端口
REDIS_PASSWORD=your-redis-password       # Redis 密码

# =============================================================================
# Qdrant 向量数据库
# =============================================================================
VECTOR_BACKEND=qdrant                    # 向量数据库类型
QDRANT_URL=http://localhost:6333         # Qdrant 地址
QDRANT_API_KEY=your-qdrant-key           # Qdrant API 密钥
QDRANT_COLLECTION_PREFIX=kb_dim          # 集合前缀
QDRANT_DISTANCE=Cosine                   # 距离计算方式

# =============================================================================
# 外部 API（可选）
# =============================================================================
TAVILY_API_KEY=                          # Tavily 搜索 API 密钥

# =============================================================================
# 前端配置
# =============================================================================
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1  # 前端访问的 API 地址
```

### 生成安全密钥

```bash
# 使用 openssl 生成
openssl rand -hex 32

# 或使用 Python
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## 反向代理配置

生产环境建议使用 Nginx 作为反向代理，统一入口并提供 SSL 终止。

### Nginx 配置示例

创建 `/etc/nginx/sites-available/clouisle`：

```nginx
# HTTP 重定向到 HTTPS
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

# HTTPS 配置
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    # SSL 证书
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # SSL 配置
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers off;

    # 上传文件大小限制
    client_max_body_size 100M;

    # API 请求代理到后端
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE/流式响应支持
        proxy_set_header Connection '';
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 86400s;
    }

    # API 文档
    location ~ ^/(docs|openapi.json|redoc) {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # 前端请求
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

启用配置：

```bash
ln -s /etc/nginx/sites-available/clouisle /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx
```

---

## SSL/HTTPS 配置

### 使用 Let's Encrypt（推荐）

```bash
# 安装 Certbot
apt install certbot python3-certbot-nginx

# 获取证书
certbot --nginx -d your-domain.com

# 自动续期（Certbot 会自动配置）
certbot renew --dry-run
```

### 使用自签名证书（测试环境）

```bash
# 生成自签名证书
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/ssl/private/clouisle.key \
  -out /etc/ssl/certs/clouisle.crt
```

---

## 数据备份与恢复

### PostgreSQL 备份

```bash
# 备份数据库
docker exec clouisle-db pg_dump -U postgres clouisle > backup_$(date +%Y%m%d).sql

# 压缩备份
docker exec clouisle-db pg_dump -U postgres clouisle | gzip > backup_$(date +%Y%m%d).sql.gz
```

### PostgreSQL 恢复

```bash
# 恢复数据库
cat backup_20240101.sql | docker exec -i clouisle-db psql -U postgres clouisle

# 从压缩文件恢复
gunzip -c backup_20240101.sql.gz | docker exec -i clouisle-db psql -U postgres clouisle
```

### Qdrant 备份

```bash
# 创建快照
curl -X POST "http://localhost:6333/collections/kb_dim_*/snapshots" \
  -H "api-key: your-qdrant-key"

# 备份快照目录
docker cp clouisle-qdrant:/qdrant/storage/snapshots ./qdrant_backup
```

### 完整备份脚本

创建 `/opt/clouisle/backup.sh`：

```bash
#!/bin/bash
set -e

BACKUP_DIR="/opt/clouisle/backups"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

echo "Backing up PostgreSQL..."
docker exec clouisle-db pg_dump -U postgres clouisle | gzip > $BACKUP_DIR/postgres_$DATE.sql.gz

echo "Backing up uploads..."
docker cp clouisle-app:/app/uploads $BACKUP_DIR/uploads_$DATE 2>/dev/null || \
docker cp clouisle-backend:/app/uploads $BACKUP_DIR/uploads_$DATE 2>/dev/null || \
docker cp clouisle-all-in-one:/app/uploads $BACKUP_DIR/uploads_$DATE

echo "Backing up Qdrant..."
docker cp clouisle-qdrant:/qdrant/storage $BACKUP_DIR/qdrant_$DATE

echo "Cleaning old backups (keep 7 days)..."
find $BACKUP_DIR -type f -mtime +7 -delete
find $BACKUP_DIR -type d -empty -delete

echo "Backup completed: $BACKUP_DIR"
```

设置定时任务：

```bash
chmod +x /opt/clouisle/backup.sh

# 每天凌晨 2 点执行备份
crontab -e
# 添加：0 2 * * * /opt/clouisle/backup.sh >> /var/log/clouisle-backup.log 2>&1
```

---

## 监控与日志

### 查看日志

```bash
# All-in-One 模式
docker logs clouisle-all-in-one -f

# 查看 supervisor 管理的各服务日志
docker exec clouisle-all-in-one tail -f /var/log/supervisor/backend.log
docker exec clouisle-all-in-one tail -f /var/log/supervisor/worker.log
docker exec clouisle-all-in-one tail -f /var/log/supervisor/frontend.log

# App 模式
docker logs clouisle-app -f

# 微服务模式
docker logs clouisle-backend -f
docker logs clouisle-worker -f
docker logs clouisle-beat -f
docker logs clouisle-frontend -f
```

### 查看服务状态

```bash
# 查看所有容器状态
docker-compose -f docker-compose.xxx.yml ps

# 查看资源使用
docker stats
```

### 健康检查

```bash
# 检查后端 API
curl http://localhost:8000/

# 检查前端
curl http://localhost:3000/

# 检查数据库连接
docker exec clouisle-db pg_isready -U postgres

# 检查 Redis
docker exec clouisle-redis redis-cli -a your-password ping

# 检查 Qdrant
curl http://localhost:6333/collections -H "api-key: your-key"
```

---

## 常见问题

### Q1: 容器启动失败，提示数据库连接错误

**原因**：数据库容器尚未就绪

**解决**：
```bash
# 检查数据库容器状态
docker-compose -f docker-compose.xxx.yml ps

# 等待数据库就绪后重启应用
docker-compose -f docker-compose.xxx.yml restart app
# 或
docker-compose -f docker-compose.xxx.yml restart backend
```

### Q2: 前端无法访问后端 API

**原因**：`NEXT_PUBLIC_API_URL` 配置错误

**解决**：
1. 检查 `.env` 中的 `NEXT_PUBLIC_API_URL` 是否正确
2. 确保后端服务正常运行
3. 检查防火墙是否放行相关端口

### Q3: 文件上传失败

**原因**：上传目录权限问题或大小限制

**解决**：
```bash
# 检查 uploads 目录
docker exec clouisle-app ls -la /app/uploads

# 如果使用 Nginx，检查 client_max_body_size 配置
```

### Q4: Worker 不处理任务

**原因**：Redis 连接问题或队列配置错误

**解决**：
```bash
# 检查 Worker 日志
docker logs clouisle-worker

# 检查 Redis 连接
docker exec clouisle-redis redis-cli -a your-password ping

# 检查队列中的任务
docker exec clouisle-redis redis-cli -a your-password llen celery
```

### Q5: 内存不足

**原因**：服务器资源不足

**解决**：
```bash
# 查看内存使用
docker stats --no-stream

# 限制容器内存（在 docker-compose.yml 中添加）
services:
  app:
    deploy:
      resources:
        limits:
          memory: 2G
```

### Q6: 如何重置管理员密码

```bash
# 进入后端容器
docker exec -it clouisle-backend bash
# 或
docker exec -it clouisle-app bash

# 使用 Python 重置密码
cd /app/backend
python -c "
import asyncio
from app.models import User
from app.core.security import get_password_hash
from tortoise import Tortoise
from app.core.config import settings

async def reset_password():
    await Tortoise.init(db_url=settings.DATABASE_URL, modules={'models': ['app.models']})
    user = await User.get(username='admin')
    user.hashed_password = get_password_hash('new-password')
    await user.save()
    print('Password reset successfully')
    await Tortoise.close_connections()

asyncio.run(reset_password())
"
```

---

## 升级指南

### 升级步骤

```bash
cd /opt/clouisle

# 1. 备份数据
./backup.sh

# 2. 拉取最新镜像
docker-compose -f docker-compose.xxx.yml pull

# 3. 停止服务
docker-compose -f docker-compose.xxx.yml down

# 4. 启动新版本
docker-compose -f docker-compose.xxx.yml up -d

# 5. 检查服务状态
docker-compose -f docker-compose.xxx.yml ps
docker-compose -f docker-compose.xxx.yml logs -f
```

### 回滚

如果升级后出现问题：

```bash
# 停止服务
docker-compose -f docker-compose.xxx.yml down

# 使用指定版本的镜像
# 编辑 docker-compose.xxx.yml，将镜像标签改为之前的版本
# 例如：ghcr.io/yunhai-dev/clouisle:backend-v1.0.0

# 重新启动
docker-compose -f docker-compose.xxx.yml up -d

# 如需恢复数据库
cat backup_xxx.sql | docker exec -i clouisle-db psql -U postgres clouisle
```

---

## 生产环境检查清单

部署到生产环境前，请确认以下事项：

- [ ] 修改 `SECRET_KEY` 为安全的随机字符串
- [ ] 修改所有默认密码（PostgreSQL、Redis、Qdrant）
- [ ] 配置 HTTPS/SSL 证书
- [ ] 配置防火墙，仅开放必要端口
- [ ] 设置数据备份定时任务
- [ ] 配置日志轮转
- [ ] 设置监控告警
- [ ] 测试备份恢复流程
- [ ] 记录所有配置和密码到安全位置

---

## 获取帮助

- GitHub Issues: https://github.com/yunhai-dev/Clouisle/issues
- 文档: https://github.com/yunhai-dev/Clouisle/docs
