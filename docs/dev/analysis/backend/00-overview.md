# 后端 API 概述

## 技术架构

- **框架**: FastAPI (Python 3.13)
- **ORM**: Tortoise ORM + AsyncPG
- **向量数据库**: Qdrant
- **LLM 框架**: LangChain + LangGraph
- **任务队列**: Celery + Redis
- **文档处理**: MarkItDown

## API 端点文件

API 分为两个路由组，均挂载在 `/api/v1/` 下。

### 平台侧 (`app/api/v1/endpoints/`) — 普通用户可访问

| 文件 | 路径前缀 | 说明 |
|------|----------|------|
| `login.py` | `/api/v1/login` | 登录认证 |
| `users.py` | `/api/v1/users` | 当前用户自身操作（`/me`、改密码、注销账号） |
| `teams.py` | `/api/v1/teams` | 我的团队、团队详情、成员管理、离开、转让 |
| `agents.py` | `/api/v1/agents` | Agent 管理 |
| `models.py` | `/api/v1/models` | 公开模型接口（providers、types、available、default） |
| `knowledge_bases.py` | `/api/v1/knowledge-bases` | 知识库管理 |
| `tools.py` | `/api/v1/tools` | 工具管理 |
| `workflows.py` | `/api/v1/workflows` | 工作流管理 |
| `api_keys.py` | `/api/v1/api-keys` | API Key 管理 |
| `chat.py` | `/api/v1/agents` | 聊天接口 |
| `notifications.py` | `/api/v1/notifications` | 用户通知（读取、标记已读） |
| `sso.py` | `/api/v1/sso` | 公开 SSO 接口（providers、login、callback、用户断开连接） |
| `site_settings.py` | `/api/v1/site-settings` | 公开站点设置（`/public`） |
| `prompt_generator.py` | `/api/v1/prompts` | 提示词生成 |

### 管理侧 (`app/api/v1/admin/endpoints/`) — 路径前缀 `/api/v1/admin/`，需要管理员权限

| 文件 | 路径前缀 | 说明 |
|------|----------|------|
| `dashboard.py` | `/api/v1/admin/dashboard` | 仪表盘统计 |
| `audit_logs.py` | `/api/v1/admin/audit-logs` | 审计日志 |
| `conversations.py` | `/api/v1/admin/conversations` | 全局对话管理 |
| `users.py` | `/api/v1/admin/users` | 用户 CRUD、激活/停用、发邮件 |
| `roles.py` | `/api/v1/admin/roles` | 角色管理 |
| `permissions.py` | `/api/v1/admin/permissions` | 权限管理 |
| `site_settings.py` | `/api/v1/admin/site-settings` | 站点配置（全量读写） |
| `models.py` | `/api/v1/admin/models` | 模型 CRUD、测试、设为默认 |
| `teams.py` | `/api/v1/admin/teams` | 全量团队列表、创建、删除 |
| `sso.py` | `/api/v1/admin/sso` | SSO 提供商 CRUD、断开任意用户连接 |
| `notifications.py` | `/api/v1/admin/notifications` | 创建、删除、全量通知列表 |

## 认证模式

### 1. 无认证（公开接口）

适用于登录、注册、SSO 等公开端点：
- `/login/*` - 登录相关
- `/register` - 用户注册
- `/sso/providers` - SSO 提供商列表
- `/sso/login/*`, `/sso/callback/*` - SSO 流程
- `/models/providers`, `/models/types` - 模型元数据
- `/site-settings/public` - 公开站点设置

### 2. 活跃用户认证

使用 `deps.get_current_active_user` 依赖：
```python
@router.get("/")
async def list_items(
    current_user: User = Depends(deps.get_current_active_user)
):
    ...
```

### 3. 权限检查

使用 `deps.PermissionChecker("scope:action")` 依赖：
```python
@router.post("/")
async def create_item(
    current_user: User = Depends(deps.PermissionChecker("item:create"))
):
    ...
```

常见权限范围：
- `user:read|create|update|delete|manage`
- `model:read|create|update|delete`
- `apikey:read|create|update|delete`
- `agent:read|create|update|delete`

### 4. 超级管理员

使用 `deps.get_current_active_superuser` 依赖（主要用于 admin 路由组中的 SSO 管理接口）：
```python
@router.get("/providers")
async def list_providers(
    current_user: User = Depends(deps.get_current_active_superuser)
):
    ...
```

> **注意**：大多数管理侧接口使用 `PermissionChecker` 而非直接要求 superuser，以便通过角色权限灵活控制访问。

## 响应格式

### 成功响应

```json
{
  "code": 0,
  "data": {
    "id": "xxx",
    "name": "xxx"
  },
  "msg": "success"
}
```

### 错误响应

```json
{
  "code": 4001,
  "data": null,
  "msg": "Resource not found"
}
```

### 响应码范围

| 范围 | 说明 |
|------|------|
| `0` | 成功 |
| `1000-1999` | 通用错误（验证、请求、内部错误） |
| `2000-2999` | 认证错误（未授权、Token 无效/过期） |
| `3000-3999` | 权限错误（权限拒绝、非团队成员） |
| `4000-4999` | 资源错误（未找到） |
| `5000-5099` | 注册错误（禁用、已存在、邮箱验证） |
| `5100-5199` | 重复资源错误（名称已存在、已是成员） |
| `5200-5299` | 操作禁止错误（不能删除系统角色） |
| `5300-5399` | 登录安全错误（账户锁定、尝试过多） |
| `5400-5499` | 限流错误 |
| `6000-6099` | 知识库错误 |
| `6100-6199` | 模型错误 |
| `6200-6299` | Agent 错误 |

## 审计日志

所有关键操作都会记录审计日志：

```python
await AuditLogService.log(
    user=current_user,
    action="create_user",
    resource_type="user",
    resource_id=str(user.id),
    resource_name=user.username,
    operation="create",
    status="success",
    request=request,
    changes={"before": None, "after": user_data},
)
```

## 分页格式

列表接口统一使用分页：

**请求参数**：
- `page`: 页码（从 1 开始）
- `page_size`: 每页数量

**响应格式**：
```json
{
  "code": 0,
  "data": {
    "items": [...],
    "total": 100,
    "page": 1,
    "page_size": 20
  },
  "msg": "success"
}
```
