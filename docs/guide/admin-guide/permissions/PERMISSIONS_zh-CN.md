# 权限系统说明

本文档描述 Clouisle 平台的权限系统设计，包括特殊权限的用途、权限组合带来的数据可见性变化。

## 一、权限分类

### 1.1 特殊权限

| 权限 | 说明 | 用途 |
|------|------|------|
| `*` | 超级权限 | 仅 Super Admin 角色拥有，绕过所有权限检查 |
| `admin:dashboard:access` | 后台访问权限 | 控制是否能访问管理后台，是区分「管理员」和「普通用户」的关键权限 |

### 1.2 后台管理权限（需要 `admin:dashboard:access`）

这些权限用于后台管理功能，通常只有管理员角色拥有：

| 权限 | 说明 |
|------|------|
| `admin:user:read/create/update/delete` | 用户管理 |
| `admin:role:read/create/update/delete` | 角色管理 |
| `admin:permission:read` | 查看权限列表 |
| `admin:model:read/create/update/delete` | 模型管理 |
| `admin:memory:read` | 查看记忆记录 |
| `admin:conversation:read/delete` | 后台对话管理 |
| `admin:notification:create/delete` | 后台通知管理 |
| `admin:team:read/create/update/delete` | 全局团队管理 |
| `admin:app:read/create/update/delete/publish/duplicate` | 跨团队 Agent 与工作流（App）管理 |
| `admin:capability:read/create/update/delete/execute` | 跨团队工具与技能（Capability）管理 |
| `admin:knowledge-base:read/test/create/update/delete` | 后台知识库管理 |
| `admin:settings:read` | 查看站点设置 |
| `admin:settings:update` | 修改站点设置 |
| `admin:sso:read` | 查看 SSO 提供商与配置 |
| `admin:sso:update` | 管理 SSO 提供商与用户 SSO 连接 |
| `audit:read` | 查看审计日志 |
| `audit:export` | 导出审计日志 |

### 1.3 资源管理权限（有数据隔离）

这些权限用于管理业务资源，所有用户都可能拥有，但数据受团队隔离限制：

| 权限 | 说明 |
|------|------|
| `team:read/create/update/delete/manage` | 团队管理 |
| `agent:read/create/update/delete/publish/chat` | Agent 管理 |
| `workflow:read/create/update/delete/publish/run/execute` | 工作流管理 |
| `kb:read/test/create/update/delete` | 知识库管理 |
| `tool:read/create/update/delete/execute` | 工具管理 |
| `skill:read/create/update/delete/execute` | 技能管理 |
| `apikey:read/create/update/delete` | API Key 管理 |
| `conversation:read/delete` | 对话管理 |

---

## 二、角色定义

### 2.1 系统预设角色

| 角色 | 说明 | 关键权限 |
|------|------|---------|
| **Super Admin** | 超级管理员 | `*`（所有权限） |
| **Admin** | 管理员 | `admin:dashboard:access` + 系统读权限 + 团队作用域资源管理 |
| **Member** | 成员 | 日常资源创建与编辑（无后台访问） |
| **Viewer** | 查看者 | 默认只读用户，具备 chat/run/execute 权限 |

### 2.2 角色权限对比

| 权限 | Super Admin | Admin | Member | Viewer |
|------|:-----------:|:-----:|:------:|:------:|
| `*` | ✓ | | | |
| `admin:dashboard:access` | ✓ | ✓ | | |
| `admin:user:*` | ✓ | ✓ | | |
| `admin:role:read` | ✓ | ✓ | | |
| `admin:role:create/update/delete` | ✓ | | | |
| `admin:permission:read` | ✓ | ✓ | | |
| `admin:permission:create/update/delete` | ✓ | | | |
| `admin:model:*` | ✓ | ✓ | | |
| `admin:memory:read` | ✓ | ✓ | | |
| `admin:conversation:read/delete` | ✓ | ✓ | | |
| `admin:notification:create/delete` | ✓ | ✓ | | |
| `admin:settings:read` | ✓ | ✓ | | |
| `admin:settings:update` | ✓ | | | |
| `admin:sso:read` | ✓ | ✓ | | |
| `admin:sso:update` | ✓ | | | |
| `audit:read` | ✓ | ✓ | | |
| `audit:export` | ✓ | ✓ | | |
| `team:read` | ✓ | ✓ | ✓ | ✓ |
| `team:create/update/manage` | ✓ | ✓ | | |
| `team:delete` | ✓ | ✓ | | |
| `agent:read/chat` | ✓ | ✓ | ✓ | ✓ |
| `agent:create/update` | ✓ | ✓ | ✓ | |
| `agent:delete/publish` | ✓ | ✓ | | |
| `workflow:read/run` | ✓ | ✓ | ✓ | ✓ |
| `workflow:create/update` | ✓ | ✓ | ✓ | |
| `workflow:delete/publish` | ✓ | ✓ | | |
| `workflow:execute` | ✓ | ✓ | | |
| `kb:read` | ✓ | ✓ | ✓ | ✓ |
| `kb:test` | ✓ | ✓ | ✓ | ✓ |
| `kb:create/update` | ✓ | ✓ | ✓ | |
| `kb:delete` | ✓ | ✓ | ✓ | |
| `tool:read/execute` | ✓ | ✓ | ✓ | ✓ |
| `tool:create/update/delete` | ✓ | ✓ | ✓ | |
| `skill:read/execute` | ✓ | ✓ | ✓ | ✓ |
| `skill:create/update/delete` | ✓ | ✓ | ✓ | |
| `apikey:read` | ✓ | ✓ | ✓ | |
| `apikey:create/update/delete` | ✓ | ✓ | ✓ | |
| `conversation:read` | ✓ | ✓ | ✓ | ✓ |
| `conversation:delete` | ✓ | ✓ | ✓ | |

---

## 三、数据可见性与隔离

### 3.1 作用域模型

- `/api/v1/admin/...` 下的后台 API 在调用者拥有相应 `admin:*`、`audit:*` 或后台权限时按系统范围工作，并不会自动限制为管理员所属团队；例如后台 Agent/Workflow 与团队列表查询的是系统资源。
- `/api/v1/...` 下的平台 API 才按资源的 `team_id`、团队成员关系和作用域权限执行团队隔离。
- **Super Admin/Admin** 表示后台授权范围的区别，并不意味着每个端点都采用同一数据范围；对话和统计端点仍有各自的所有权/团队规则。

### 3.2 `admin:dashboard:access` 的影响

`admin:dashboard:access` 控制后台界面和后台 API 的入口；每个界面仍需要具体权限，例如 `admin:user:read`、`admin:model:read`、`admin:settings:read` 或 `audit:read`。没有后台权限时，应使用可用的平台团队作用域端点。

### 3.3 团队资源访问

平台 Agent、Workflow、知识库、工具等资源的有效范围由资源所属团队和调用者的作用域权限决定。未绑定团队的系统 Skill 或显式跨团队共享的 Tool 可能遵循不同规则，不要从角色名称推导“所有资源都完全隔离”。

### 3.4 实用规则

记录权限说明时必须同时写出端点和权限：`/api/v1/admin/...` 表示系统范围后台 API，`/api/v1/...` 表示团队作用域平台 API；再以该端点自身的所有权和成员检查为准。

---

## 四、权限组合场景

### 4.1 普通平台用户

没有 `admin:dashboard:access` 的 Member/Viewer 只能在作用域权限允许的范围内调用平台端点。例如 Viewer 可以读取、聊天和运行资源，但不能创建、修改、删除或发布资源。

### 4.2 后台管理员

拥有 `admin:dashboard:access` 的 Admin 可在拥有具体 `admin:*` 或 `audit:*` 权限时调用系统范围后台 API。除非端点明确提供团队过滤，不应描述为“仅限管理员所属团队”。

### 4.3 站点设置与 SSO

`admin:settings:read`/`admin:settings:update` 与 `admin:sso:read`/`admin:sso:update` 是独立权限。当前系统角色中 Super Admin 拥有更新权限，Admin 对这些设置只读；自定义角色可另行改变分配。

### 4.4 审计日志归档

编辑存储设置需要 `admin:settings:update`；归档/导出审计日志需要 `audit:export`。两项能力应分别控制，不应复用同一个前端权限判断。

---

## 五、前端菜单可见性

### 5.1 侧边栏菜单权限映射

| 菜单项 | 所需权限 | Super Admin | Admin | Member | Viewer |
|--------|---------|:-----------:|:-----:|:------:|:------:|
| 仪表盘 | `admin:dashboard:access` | ✓ | ✓ | | |
| 团队 | `team:read` | ✓ | ✓ | ✓ | ✓ |
| 知识库 | `admin:knowledge-base:read` | ✓ | ✓ | | |
| 活动 | `conversation:read` | ✓ | ✓ | ✓ | ✓ |
| 用户 | `admin:user:read` | ✓ | ✓ | | |
| 角色 | `admin:role:read` | ✓ | ✓ | | |
| 权限 | `admin:permission:read` | ✓ | ✓ | | |
| API Keys | `apikey:read` | ✓ | ✓ | ✓ | |
| 模型 | `admin:model:read` | ✓ | ✓ | | |
| Apps | `admin:app:read` | ✓ | ✓ | | |
| Capabilities | `admin:capability:read` | ✓ | ✓ | | |
| Memories | `admin:memory:read` | ✓ | ✓ | | |
| Observability | `admin:dashboard:access` | ✓ | ✓ | | |
| 通知 | `admin:dashboard:access` | ✓ | ✓ | | |
| 审计日志 | `audit:read` | ✓ | ✓ | | |
| 站点设置 | `admin:settings:read` | ✓ | ✓ | | |

### 5.2 管理菜单组可见性

「管理」菜单组（包含用户、角色、权限、模型、审计日志等）仅在用户拥有 `admin:dashboard:access` 权限时显示。

---

## 六、API 权限检查

### 6.1 权限检查方式

```python
# 方式 1：单一权限检查
current_user: User = Depends(PermissionChecker("admin:user:read"))

# 方式 2：超级管理员专用（已废弃，改用权限检查）
# current_user: User = Depends(get_current_active_superuser)
```

### 6.2 数据隔离实现

```python
# 检查是否有管理员权限
has_dashboard_access = current_user.is_superuser
if not has_dashboard_access:
    for role in current_user.roles:
        for perm in role.permissions:
            if perm.code == "admin:dashboard:access" or perm.code == "*":
                has_dashboard_access = True
                break

# 根据权限级别过滤数据
if current_user.is_superuser:
    # 超级管理员：无过滤
    query = Model.all()
elif has_dashboard_access:
    # 管理员：团队级过滤
    query = Model.filter(team_id__in=user_team_ids)
else:
    # 普通用户：用户级过滤（如对话）
    query = Model.filter(user_id=current_user.id)
```

---

## 七、最佳实践

### 7.1 角色分配建议

| 用户类型 | 推荐角色 | 说明 |
|----------|---------|------|
| 系统管理员 | Super Admin | 负责系统配置、用户管理 |
| 部门管理员 | Admin | 负责部门内用户和资源管理 |
| 开发人员 | Member | 创建和管理 Agent、工作流等 |
| 业务用户 | Viewer | 使用 Agent 和工作流，不需要创建 |

### 7.2 自定义角色

可以基于业务需求创建自定义角色，例如：

**数据分析师**：
- `agent:read`, `agent:chat`
- `workflow:read`, `workflow:run`
- `kb:read`
- `conversation:read`

**内容管理员**：
- `kb:read`, `kb:create`, `kb:update`, `kb:delete`
- `agent:read`

### 7.3 权限最小化原则

- 只授予用户完成工作所需的最小权限
- 避免给普通用户分配 `admin:dashboard:access` 权限
- `admin:settings:update` 权限应仅限于系统管理员
