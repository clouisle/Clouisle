# 开发环境搭建

本指南介绍如何搭建 Clouisle 的本地开发环境。

## 前置要求

- Python 3.13+ 以及 [uv](https://github.com/astral-sh/uv)
- [Bun](https://bun.sh/) 1.0+
- Docker 和 Docker Compose（用于基础设施服务）

## 1. 克隆仓库

```bash
git clone https://github.com/clouisle/Clouisle.git
cd clouisle
```

## 2. 配置环境变量

```bash
# 复制根目录环境变量文件（用于本地开发）
cp .env.example .env
```

生成安全密码并更新 `.env`。请为以下字段设置强随机值：
`SECRET_KEY`、`QDRANT_API_KEY`。

注意：开发基础设施（`deploy/docker-compose.dev.yml`）使用**固定硬编码凭据**，不读取 `.env`：PostgreSQL 为 `postgres` / `password`，Redis 密码为 `clouisle-redis-cbd3c07d`。只有 `QDRANT_API_KEY` 从 `.env` 读取（必填）。只有在同时修改 dev compose 文件与之匹配时，才需要在 `.env` 中设置 `POSTGRES_PASSWORD` / `REDIS_PASSWORD`。

## 3. 启动基础设施

```bash
# 启动 PostgreSQL、Redis 和 Qdrant
docker compose -f deploy/docker-compose.dev.yml --env-file .env up -d
```

## 4. 启动后端

```bash
# 安装依赖
uv sync --project backend

# 启动 API 服务器（首次运行时数据库会自动初始化）
uv run --project backend main.py server

# 在单独的终端中启动 Workers
uv run --project backend main.py worker
uv run --project backend main.py beat

# 可选：沙箱 Worker（用于代码执行功能）
uv run --project backend main.py sandbox-worker -c 1
```

## 5. 启动前端

```bash
# 安装依赖
bun install --cwd frontend

# 启动开发服务器
bun run --cwd frontend dev
```

## 6. 访问应用

- **前端**：http://localhost:3000
- **API 文档**：http://localhost:8000/docs
- **首个账号**：没有预置的默认管理员——首个注册用户会自动成为超级管理员

## 开发命令

### 后端

```bash
cd backend

# 代码检查
uv run ruff check .

# 代码格式化
uv run ruff format .

# 测试
uv run pytest
```

### 前端

```bash
# 代码检查
bun run --cwd frontend lint

# 构建
bun run --cwd frontend build

# 测试与覆盖率
bun run --cwd frontend test
bun run --cwd frontend test:coverage
bun run --cwd frontend coverage:check
```

### 沙箱 Worker（可选）

```bash
# 启动沙箱 Worker（用于代码执行功能）
uv run --project backend main.py sandbox-worker -c 1

# 或使用 Dev 容器运行以隔离环境
uv run --project backend main.py sandbox-worker --local-dev -c 1
```

## 项目结构

```
clouisle/
├── backend/          # FastAPI 后端
│   ├── app/          # 应用代码
│   │   ├── api/      # API 端点和路由
│   │   ├── core/     # 核心配置、初始化、认证等
│   │   ├── llm/      # LLM 适配器和工具系统
│   │   ├── models/   # Tortoise ORM 模型
│   │   ├── schemas/  # Pydantic 数据模型
│   │   ├── services/ # 业务逻辑服务
│   │   └── tasks/    # Celery 任务定义
│   ├── tests/        # 测试套件
│   ├── scripts/      # 工具脚本
│   └── pyproject.toml
├── frontend/         # Next.js 前端
│   ├── app/          # App Router 页面
│   ├── components/   # React 组件
│   ├── lib/          # 工具函数和 API 客户端
│   ├── hooks/        # 自定义 React Hooks
│   └── contexts/     # React Contexts
├── deploy/           # 部署配置（Docker、K8s、Helm）
├── docs/             # 文档
├── main.py           # 根启动脚本
└── scripts/          # 项目级脚本
```

## 常见问题

确保 PostgreSQL 正在运行且可访问。开发 compose 文件使用固定凭据和端口：PostgreSQL `postgres`/`password` 使用 `5432`，Redis 密码为 `clouisle-redis-cbd3c07` 使用 `6379`，Qdrant 使用 `6333`。`.env` 不会改变这些 compose 值；文档化的 compose 配置只从 `.env` 读取 `QDRANT_API_KEY`。

### 端口冲突

开发 compose 文件只绑定 PostgreSQL `5432`、Redis `6379` 和 Qdrant `6333`；后端 `8000` 和前端 `3000` 单独启动。若本地服务占用端口，请修改对应的启动或配置设置，而不是修改不存在的 compose 映射。

### 热重载不生效

`server` 命令默认启用自动重载，监听 `backend/` 下的文件变更。如需手动重启，停止进程后重新运行 server 命令即可。

---

生产部署请参考 [快速开始（Docker）](./quick-start.md)。
