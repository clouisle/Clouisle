# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

Clouisle is an enterprise-grade knowledge base and AI Agent platform. Monorepo with Python FastAPI backend and Next.js frontend.

## Commands

### Backend (cd backend)
```bash
uv sync                              # Install dependencies
uvicorn app.main:app --reload        # Dev server
uv run ruff check .                  # Lint
uv run ruff check . --fix            # Lint fix
uv run ruff format .                 # Format
uv run mypy app/                     # Type check
uv run pytest                        # Test
uv run pytest tests/test_file.py::test_name  # Run single test
celery -A app.core.celery worker --loglevel=info   # Celery worker
celery -A app.core.celery beat --loglevel=info     # Celery beat
```

### Frontend (cd frontend)
```bash
bun install          # Install dependencies
bun dev              # Dev server
bun run build        # Production build
bun run lint         # Lint
bun run lint --fix   # Lint fix
```

### Infrastructure
```bash
docker-compose -f deploy/docker-compose.dev.yml up -d   # Start PostgreSQL + Redis + Qdrant (dev)
```

## Architecture

### Backend (Python 3.13, FastAPI, uv)
- `app/api/v1/endpoints/` - 平台侧 API 路由（用户自身操作、公开接口）
- `app/api/v1/admin/endpoints/` - 管理侧 API 路由（需要管理员权限）
- `app/services/` - Business logic
- `app/models/` - Tortoise ORM models
- `app/schemas/` - Pydantic schemas
- `app/llm/` - LLM integration (providers, adapters, MCP)
- `app/tasks/` - Celery tasks (async background jobs)
- `app/core/` - Config, i18n, security, celery, audit

**Tech Stack:**
- ORM: Tortoise ORM with AsyncPG
- Vector DB: Qdrant
- LLM Framework: LangChain + LangGraph
- MCP: Model Context Protocol for tool integration
- Document Processing: MarkItDown (PDF, XLSX, etc.)

**Database Migrations:**
- This project does NOT use Alembic or Aerich for migrations
- When adding/modifying database fields in models, you MUST create a migration function in `app/core/init_data.py`
- Migration function pattern:
  ```python
  async def init_<feature_name>():
      """Add <field_name> field to <table_name> table."""
      logger.info("Initializing <feature_name>...")

      conn = Tortoise.get_connection("default")

      # Check if table exists first
      _, tables = await conn.execute_query("""
          SELECT table_name FROM information_schema.tables
          WHERE table_name = '<table_name>' AND table_schema = 'public'
      """)

      if not tables:
          logger.info("<table_name> table does not exist yet, skipping migration")
          return

      # Check if column exists
      _, rows = await conn.execute_query("""
          SELECT column_name FROM information_schema.columns
          WHERE table_name = '<table_name>' AND column_name = '<field_name>'
      """)

      if rows:
          logger.info("<field_name> field already exists, skipping")
          return

      logger.info("Adding <field_name> field to <table_name> table...")

      # Add field with appropriate type and default value
      await conn.execute_query("""
          ALTER TABLE <table_name>
          ADD COLUMN IF NOT EXISTS <field_name> <TYPE> NOT NULL DEFAULT <default_value>
      """)

      logger.info("<field_name> field added successfully")
  ```
- After creating the migration function, add it to `app/main.py`:
  1. Import it in the `lifespan` function's import block
  2. Call it in a try-except block before `await Tortoise.generate_schemas()`
- Example:
  ```python
  from app.core.init_data import (
      ...,
      init_<feature_name>,
  )

  try:
      await init_<feature_name>()
  except Exception as e:
      logger.warning(f"<Feature> migration failed: {e}")
  ```

### Frontend (Next.js 16, Bun, TypeScript)
- `app/(auth)/` - Auth pages (login, register)
- `app/(dashboard)/` - Admin interface (sidebar layout)
- `app/(platform)/` - User interface (header layout)
- `app/(chat)/` - Chat interface
- `components/ui/` - shadcn/ui base-vega components
- `lib/api/` - 平台侧 API 模块（用户自身操作、公开接口）
- `lib/api/admin/` - 管理侧 API 模块（dashboard、audit-logs、users、roles 等，路径前缀 `/admin/`）
- `i18n/` - i18n translations (modular structure: en/, zh/)

## Key Conventions

### Backend

**API Response Format:**
- All API responses use unified format: `{"code": 0, "data": {...}, "msg": "success"}`
- `code = 0` means success, `code != 0` means error
- Use `success()` and `error()` helpers from `app/schemas/response.py`

**Response Code Ranges** (defined in `ResponseCode` enum):
- `0`: Success
- `1000-1999`: General errors (validation, bad request, internal error)
- `2000-2999`: Authentication errors (unauthorized, invalid token, expired token)
- `3000-3999`: Permission errors (permission denied, not team member)
- `4000-4999`: Resource errors (not found)
- `5000-5099`: Registration errors (disabled, already exists, email verification)
- `5100-5199`: Duplicate resource errors (name exists, already member)
- `5200-5299`: Operation forbidden errors (cannot delete system role, cannot remove owner)
- `5300-5399`: Login security errors (account locked, too many attempts, captcha)
- `5400-5499`: Rate limiting errors
- `6000-6099`: Knowledge base errors
- `6100-6199`: Model errors
- `6200-6299`: Agent errors

**Error Handling:**
- Use `BusinessError` exception (not HTTPException) for business errors:
  ```python
  raise BusinessError(
      code=ResponseCode.USERNAME_EXISTS,
      msg_key="username_already_registered"
  )
  ```
- All user-facing messages must use i18n via `t()` from `app/core/i18n.py`

**Audit Logging:**
- Use `AuditLogService.log()` from `app/services/audit_log` for operation logging:
  ```python
  await AuditLogService.log(
      user=current_user,
      action="delete_user",
      resource_type="user",
      resource_id=str(user_id),
      resource_name=user.username,
      operation="delete",
      status="success",
      request=request,
      changes={"before": {...}, "after": {...}},
      metadata={...},
  )
  ```
- **IMPORTANT**: When adding new audit log actions, you MUST add corresponding i18n translations:
  - Backend: Add to `TRANSLATIONS` dict in `app/core/i18n.py` with key `audit_log_{action}`
  - Frontend: Add to `i18n/en/auditLogs.json` and `i18n/zh/auditLogs.json` with key `action{action}`

  Example for action `delete_user`:
  - Backend i18n key: `audit_log_delete_user` → "Delete user" / "删除用户"
  - Frontend i18n key: `actiondelete_user` → "Delete User" / "删除用户"

**Current Audit Actions** (must have translations):
```
activate_api_key, activate_user, add_team_member, bulk_update_site_settings,
change_password, create_agent, create_api_key, create_team, create_user,
deactivate_api_key, deactivate_user, delete_agent, delete_api_key, delete_team,
delete_user, login_failed, login_success, logout, publish_agent, register,
remove_team_member, reset_password, reset_site_settings, trigger_audit_log_archive,
unpublish_agent, update_agent, update_api_key, update_site_setting, update_team,
update_user
```

### Frontend

**API Client Usage:**
- Use `api.get/post/put/patch/delete` from `lib/api/client.ts`
- API methods return `data` directly (unwrapped from `{code, data, msg}`)
- Errors are automatically handled by interceptor:
  - `code !== 0`: throws `ApiError` with code, msg, data
  - Auth errors (2000-2999): auto redirect to login
  - Validation errors (1001): use `error.getFieldErrors()` for form errors
- **Global notifications** (Sonner toast):
  - Auto-displayed for all errors (except validation errors and silent mode)
  - Use `silent: true` option to suppress toast notifications
  - Manual toast: `import { toast } from 'sonner'` → `toast.success/error/info/warning()`
- Use `skipAuthRedirect: true` for login endpoints
- **File downloads**: Use `axiosInstance` directly with `responseType: "blob"` (bypasses JSON interceptor)
  ```typescript
  const response = await axiosInstance.get("/endpoint", {
    params: { format: "csv" },
    responseType: "blob",
  });
  return response.data; // Returns Blob directly
  ```

**UI Components:**
- shadcn/ui base-vega uses `render` prop, NOT `asChild`
- Use `AlertDialog` instead of native `confirm()`
- Use `Tooltip` instead of native `title` attribute
- Select in Dialog: add `alignItemWithTrigger={false}` to SelectContent
- **Select with i18n**: When SelectItem uses translated text, SelectValue must explicitly render the translation:
  ```typescript
  <Select value={value} onValueChange={onChange}>
    <SelectTrigger>
      <SelectValue>
        {value === 'option1' && t('translationKey1')}
        {value === 'option2' && t('translationKey2')}
      </SelectValue>
    </SelectTrigger>
    <SelectContent>
      <SelectItem value="option1">{t('translationKey1')}</SelectItem>
      <SelectItem value="option2">{t('translationKey2')}</SelectItem>
    </SelectContent>
  </Select>
  ```
  Without this, SelectValue will show raw values (e.g., "option1") instead of translated text
- Chinese IME: check `e.nativeEvent.isComposing` in keyboard events
- Decimal input: use `type="text"` with `inputMode="decimal"` + regex validation
- All interactive elements need appropriate `cursor-*` classes
- Use `mounted` state for localStorage-dependent components (hydration)

**Date/Time Formatting:**
- Use unified format: `2026/02/03 16:10` (YYYY/MM/DD HH:mm)
- Import from `@/lib/utils`:
  ```typescript
  import { formatDateTime, formatDate } from '@/lib/utils'

  formatDateTime(dateString)  // "2026/02/03 16:10"
  formatDate(dateString)      // "2026/02/03"
  ```
- Do NOT use `toLocaleDateString()` or `toLocaleString()` directly for dates

### API 路由隔离

后端 API 分为两个路由组，均挂载在 `/api/v1/` 下：

**平台侧** (`app/api/v1/endpoints/`) — 普通用户可访问：
- `users.py` — `/users/me`、`/users/me/change-password`（仅自身操作）
- `teams.py` — `/teams/my`、`/teams/{id}`、成员管理、离开、转让
- `site_settings.py` — `/site-settings/public`（无需认证）
- `models.py` — `/models/providers`、`/types`、`/available`、`/default/{type}`
- `sso.py` — `/sso/providers`、`/sso/login`、`/sso/callback`、`/sso/connections/{id}` DELETE
- `notifications.py` — `/notifications`（用户通知读取）
- 其余：agents、workflows、knowledge-bases、tools、api-keys、upload、prompts

**管理侧** (`app/api/v1/admin/endpoints/`) — 路径前缀 `/admin/`，需要管理员权限：
- `dashboard.py` → `/admin/dashboard`
- `audit_logs.py` → `/admin/audit-logs`
- `conversations.py` → `/admin/conversations`
- `users.py` → `/admin/users`（CRUD、激活/停用、发邮件）
- `roles.py` → `/admin/roles`
- `permissions.py` → `/admin/permissions`
- `site_settings.py` → `/admin/site-settings`（全量读写）
- `models.py` → `/admin/models`（CRUD、test、set-default）
- `teams.py` → `/admin/teams`（全量列表、创建、删除）
- `sso.py` → `/admin/sso`（providers CRUD、断开任意用户连接）
- `notifications.py` → `/admin/notifications`（创建、删除、全量列表）

前端对应：
- `lib/api/` — 平台侧模块，`(platform)/` 和通用组件使用
- `lib/api/admin/` — 管理侧模块，`(dashboard)/` 页面使用，所有接口路径含 `/admin/` 前缀



### i18n
- Backend: Add translations to `TRANSLATIONS` dict in `app/core/i18n.py`
- Frontend: Add to `i18n/en/` and `i18n/zh/` directories (modular structure)

## Celery 异步任务

### 添加新的 Celery 任务模块

当添加新的 Celery 任务模块时，必须完成以下步骤：

1. **在 `app/core/celery.py` 中注册任务模块**：
   ```python
   celery_app = Celery(
       "clouisle",
       broker=f"{REDIS_URL}/0",
       backend=f"{REDIS_URL}/1",
       include=[
           "app.tasks.knowledge_base",
           "app.tasks.your_new_module",  # 添加新模块
       ],
   )
   ```

2. **配置任务路由**（如果需要特定队列）：
   ```python
   celery_app.conf.task_routes = {
       "app.tasks.your_new_module.*": {"queue": "default"},
   }
   ```

3. **任务函数必须是同步函数**：
   - Celery 不支持 `async def` 任务函数
   - 如果需要调用异步代码，使用 `asyncio.run()` 包装：
   ```python
   @celery_app.task(bind=True, name="your_task_name")
   def your_task(self, param1, param2):
       async def _async_work():
           # 异步代码
           result = await some_async_function()
           return result

       return asyncio.run(_async_work())
   ```

4. **重启 Celery worker** 使新任务生效：
   ```bash
   pkill -f "celery.*worker"
   celery -A app.core.celery:celery_app worker --loglevel=info --concurrency=4 --queues=default,workflow
   ```

### 大数据量处理

**问题：** 如何处理大文件或大数据量的异步任务？

**解决方案：** 使用 StorageService 抽象层，支持多种存储后端。

#### 架构设计

```
API 端点 → StorageService → 存储后端（Local/Redis/S3）
                ↓
         Celery 任务 → StorageService → 读取文件
```

**核心代码：**

```python
from app.services.storage_service import StorageService

# 1. API 端点保存文件
file_content = await file.read()
await StorageService.save_import_file(file_content, task_id, file.filename)
await StorageService.save_team_info(task_id, str(team_id))

# 2. Celery 任务读取文件
file_content, filename = await StorageService.get_import_file(task_id)
team_id = await StorageService.get_team_info(task_id)

# 3. 处理完成后清理
await StorageService.delete_import_file(task_id)
```

#### 存储后端配置

**方案 1: 本地文件系统（默认）**
- 适用于单机部署
- 配置：`USE_REDIS_STORAGE=false`（默认）
- 优点：简单、快速、无限制
- 缺点：不支持分布式

**方案 2: Redis 存储**
- 适用于分布式部署 + 小中型文件（< 100MB）
- 配置：`USE_REDIS_STORAGE=true`
- 优点：无需额外服务、实现简单、支持分布式
- 缺点：占用内存、有大小限制
- 实现：使用 Redis database 2，避免与 Celery 冲突

**方案 3: S3/MinIO 对象存储（待实现）**
- 适用于分布式部署 + 大文件
- 优点：可扩展、支持超大文件
- 缺点：需要额外服务

#### 存储方案对比

| 方案 | 适用场景 | 优点 | 缺点 | 文件大小限制 |
|------|---------|------|------|------------|
| 本地文件系统 | 单机部署 | 简单、快速 | 不支持分布式 | 无限制 |
| Redis | 分布式、小文件 | 简单、无需额外服务 | 占用内存、有大小限制 | < 100MB |
| S3/MinIO | 分布式、大文件 | 可扩展、支持大文件 | 需要额外服务、有成本 | 无限制 |

#### 推荐配置

**开发环境：**
```bash
# 使用本地文件系统
USE_REDIS_STORAGE=false
```

**生产环境（单机）：**
```bash
# 使用本地文件系统
USE_REDIS_STORAGE=false
```

**生产环境（Kubernetes/分布式）：**
```bash
# 小文件使用 Redis
USE_REDIS_STORAGE=true

# 大文件建议实现 S3 存储（TODO）
# USE_S3_STORAGE=true
# S3_BUCKET=clouisle-imports
# S3_ENDPOINT=https://s3.amazonaws.com
```

#### 实现细节

**StorageService 自动选择后端：**
```python
class StorageService:
    @staticmethod
    def get_storage_backend() -> str:
        use_redis = getattr(settings, "USE_REDIS_STORAGE", False)
        return "redis" if use_redis else "local"
```

**Redis 存储使用 base64 编码：**
```python
# 存储
key = f"import:file:{task_id}"
await redis_client.setex(
    key,
    3600,  # 1 小时过期
    base64.b64encode(file_content).decode("utf-8")
)

# 读取
encoded_content = await redis_client.get(key)
file_content = base64.b64decode(encoded_content)
```

**本地文件系统存储：**
```python
temp_dir = Path(settings.UPLOAD_DIR) / "imports" / task_id
temp_dir.mkdir(parents=True, exist_ok=True)
file_path = temp_dir / filename
with open(file_path, "wb") as f:
    f.write(file_content)
```

**优点：**
- 统一的 API，切换存储后端无需修改业务代码
- 支持分布式部署
- 避免 Celery 消息队列大小限制
- 自动清理过期文件（Redis TTL）

### 任务进度更新

**前端轮询任务状态：**

```typescript
// 组件中轮询任务状态
useEffect(() => {
  if (!open || !taskId) return;

  let intervalId: NodeJS.Timeout;

  const pollStatus = async () => {
    try {
      const status = await importExportApi.getImportStatus(taskId);
      setResult(status);

      if (status.status === "completed" || status.status === "failed") {
        clearInterval(intervalId);
        onComplete(status);
      }
    } catch (err: any) {
      setError(err.message);
      clearInterval(intervalId);
    }
  };

  pollStatus(); // 立即执行一次
  intervalId = setInterval(pollStatus, 2000); // 每2秒轮询

  return () => {
    if (intervalId) clearInterval(intervalId);
  };
}, [open, taskId, onComplete]);
```

**后端更新任务进度：**

```python
@celery_app.task(bind=True)
def long_running_task(self, param):
    async def _work():
        # 更新进度
        self.update_state(
            state="PROGRESS",
            meta={"progress": 50, "status": "Processing data"}
        )

        # 执行工作...
        result = await do_work()

        return result

    return asyncio.run(_work())
```

**后端查询任务状态：**

```python
from celery.result import AsyncResult

@router.get("/tasks/{task_id}/status")
async def get_task_status(task_id: str):
    task = AsyncResult(task_id)

    if task.state == "PROGRESS":
        return {
            "status": "processing",
            "progress": task.info.get("progress", 0),
            "message": task.info.get("status", ""),
        }
    elif task.state == "SUCCESS":
        return {
            "status": "completed",
            "progress": 100,
            "result": task.result,
        }
    # ... 其他状态
```

### 常见问题

**问题：任务发送成功但 worker 不执行**

可能原因：
1. 任务模块未在 `app/core/celery.py` 的 `include` 列表中注册
2. Worker 监听的队列与任务发送的队列不匹配
   - 默认队列配置：`task_default_queue="default"`
   - Worker 启动时指定队列：`--queues=default,workflow`
3. Worker 未重启，没有加载新任务

排查步骤：
```bash
# 1. 检查任务是否注册
celery -A app.core.celery:celery_app inspect registered

# 2. 检查 Redis 队列中的任务
docker exec <redis-container> redis-cli -a <password> -n 0 LLEN default

# 3. 检查 worker 日志
tail -f /path/to/celery_worker.log
```

**问题：前端显示"导入成功"但实际还在处理**

原因：前端没有等待任务完成，只是任务创建成功就显示了成功消息。

解决方案：
1. 任务创建后立即显示进度对话框
2. 轮询任务状态直到完成
3. 完成后显示结果对话框
4. 参考 `ImportProgressDialog` 组件的实现

## Pre-commit Requirements
All checks must pass before commit:
- Backend: `ruff check`, `ruff format --check`, `mypy app/`
- Frontend: `bun run lint`, `bun run build`
