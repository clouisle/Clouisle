# 后端 API 概述

## 技术架构

- **框架**: FastAPI (Python 3.13)
- **ORM**: Tortoise ORM + AsyncPG
- **向量数据库**: Qdrant
- **LLM 框架**: LangChain + LangGraph
- **任务队列**: Celery + Redis
- **文档处理**: MarkItDown

## API 端点文件

| 文件 | 路径前缀 | 说明 |
|------|----------|------|
| `login.py` | `/api/v1/login` | 登录认证 |
| `users.py` | `/api/v1/users` | 用户管理 |
| `teams.py` | `/api/v1/teams` | 团队管理 |
| `roles.py` | `/api/v1/roles` | 角色管理 |
| `permissions.py` | `/api/v1/permissions` | 权限管理 |
| `agents.py` | `/api/v1/agents` | Agent 管理 |
| `models.py` | `/api/v1/models` | 模型管理 |
| `knowledge_bases.py` | `/api/v1/knowledge-bases` | 知识库管理 |
| `tools.py` | `/api/v1/tools` | 工具管理 |
| `workflows.py` | `/api/v1/workflows` | 工作流管理 |
| `api_keys.py` | `/api/v1/api-keys` | API Key 管理 |
| `chat.py` | `/api/v1/chat` | 聊天接口 |
| `notifications.py` | `/api/v1/notifications` | 通知管理 |
| `sso.py` | `/api/v1/sso` | SSO 单点登录 |
| `site_settings.py` | `/api/v1/site-settings` | 站点设置 |
| `dashboard.py` | `/api/v1/dashboard` | 仪表盘统计 |
| `audit_logs.py` | `/api/v1/audit-logs` | 审计日志 |
| `prompt_generator.py` | `/api/v1/prompt-generator` | 提示词生成 |

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

使用 `deps.get_current_active_superuser` 依赖：
```python
@router.get("/admin")
async def admin_only(
    current_user: User = Depends(deps.get_current_active_superuser)
):
    ...
```

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
