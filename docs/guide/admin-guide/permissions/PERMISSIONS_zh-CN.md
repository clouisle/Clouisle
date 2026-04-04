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
| `user:read/create/update/delete` | 用户管理 |
| `role:read/create/update/delete` | 角色管理 |
| `permission:read` | 查看权限列表 |
| `model:read/create/update/delete` | 模型管理 |
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
| `workflow:read/create/update/delete/publish/run` | 工作流管理 |
| `kb:read/create/update/delete` | 知识库管理 |
| `tool:read/create/update/delete/execute` | 工具管理 |
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
| `kb:read` | ✓ | ✓ | ✓ | ✓ |
| `kb:create/update` | ✓ | ✓ | ✓ | |
| `kb:delete` | ✓ | ✓ | | |
| `tool:read/execute` | ✓ | ✓ | ✓ | ✓ |
| `tool:create/update/delete` | ✓ | ✓ | | |
| `apikey:read` | ✓ | ✓ | ✓ | |
| `apikey:create/update/delete` | ✓ | ✓ | ✓ | |
| `conversation:read` | ✓ | ✓ | ✓ | ✓ |
| `conversation:delete` | ✓ | ✓ | ✓ | |

---

## 三、数据隔离规则

### 3.1 核心概念

- **Super Admin**：无数据隔离，可访问系统所有数据
- **Admin**：团队级隔离，可访问所属团队的所有数据
- **Member/Viewer**：团队级隔离 + 用户级隔离（对话数据）

### 3.2 `admin:dashboard:access` 权限的影响

`admin:dashboard:access` 是区分「管理员视角」和「用户视角」的关键权限：

| 数据类型 | 有 `admin:dashboard:access` | 无 `admin:dashboard:access` |
|----------|----------------------|----------------------|
| 用户列表 | 可见（需要 `admin:user:read`） | 不可见 |
| 角色列表 | 可见（需要 `admin:role:read`） | 不可见 |
| 模型列表 | 可见（需要 `admin:model:read`） | 不可见 |
| 审计日志 | 可见（需要 `audit:read`） | 不可见 |
| 站点设置 | 可见（需要 `admin:settings:read`） | 不可见 |
| **对话列表** | **团队内所有用户的对话** | **仅自己的对话** |
| **对话统计** | **团队内所有对话的统计** | **仅自己对话的统计** |

### 3.3 对话数据的特殊隔离

对话（Conversation）数据有更细粒度的隔离：

```
Super Admin
└── 可查看所有对话

Admin (有 admin:dashboard:access)
└── 可查看所属团队内所有用户的对话
    └── 团队 A 的所有对话
    └── 团队 B 的所有对话（如果是成员）

Member / Viewer (无 admin:dashboard:access)
└── 只能查看自己的对话
    └── 自己在团队 A 创建的对话
    └── 自己在团队 B 创建的对话
```

### 3.4 其他资源的隔离

除对话外，其他资源（Agent、Workflow、知识库等）的隔离规则：

| 角色 | 可见范围 |
|------|---------|
| Super Admin | 所有资源 |
| Admin | 所属团队的所有资源 |
| Member | 所属团队的所有资源 |
| Viewer | 所属团队的所有资源（只读） |

---

## 四、权限组合场景

### 4.1 场景：普通用户查看活动日志

**用户角色**：Member（无 `admin:dashboard:access`）

**可见数据**：
- ✓ 自己创建的对话
- ✓ 自己的对话统计
- ✗ 团队其他成员的对话
- ✗ 后台管理菜单

### 4.2 场景：管理员查看活动日志

**用户角色**：Admin（有 `admin:dashboard:access`）

**可见数据**：
- ✓ 团队内所有用户的对话
- ✓ 团队级对话统计
- ✓ 后台管理菜单
- ✗ 其他团队的对话

### 4.3 场景：只读用户

**用户角色**：Viewer

**可执行操作**：
- ✓ 查看团队资源（Agent、Workflow、知识库等）
- ✓ 与 Agent 对话（`agent:chat`）
- ✓ 运行工作流（`workflow:run`）
- ✓ 执行工具（`tool:execute`）
- ✗ 创建/修改/删除任何资源
- ✗ 访问后台管理

### 4.4 场景：站点设置管理

| 角色 | `admin:settings:read` | `admin:settings:update` | 可执行操作 |
|------|:---------------:|:-----------------:|-----------|
| Super Admin | ✓ | ✓ | 查看和修改所有设置 |
| Admin | ✓ | ✗ | 仅查看设置 |
| Member | ✗ | ✗ | 无法访问 |

### 4.5 场景：SSO 管理

| 角色 | `admin:sso:read` | `admin:sso:update` | 可执行操作 |
|------|:----------------:|:------------------:|-----------|
| Super Admin | ✓ | ✓ | 查看并管理所有 SSO 提供商，以及断开用户的 SSO 连接 |
| Admin | ✓ | ✗ | 仅查看 SSO 配置 |
| Member | ✗ | ✗ | 无法访问 |

### 4.6 场景：审计日志归档

- 编辑存储设置需要 `admin:settings:update`
- 归档审计日志需要 `audit:export`
- 这两种能力应分别控制，不应复用同一个前端权限判断

---

## 五、前端菜单可见性

### 5.1 侧边栏菜单权限映射

| 菜单项 | 所需权限 | Super Admin | Admin | Member | Viewer |
|--------|---------|:-----------:|:-----:|:------:|:------:|
| 仪表盘 | `admin:dashboard:access` | ✓ | ✓ | | |
| 团队 | `team:read` | ✓ | ✓ | ✓ | ✓ |
| 知识库 | `kb:read` | ✓ | ✓ | ✓ | ✓ |
| 活动 | `conversation:read` | ✓ | ✓ | ✓ | ✓ |
| 用户 | `admin:user:read` | ✓ | ✓ | | |
| 角色 | `admin:role:read` | ✓ | ✓ | | |
| 权限 | `permission:read` | ✓ | ✓ | | |
| API Keys | `apikey:read` | ✓ | ✓ | ✓ | ✓ |
| 模型 | `admin:model:read` | ✓ | ✓ | | |
| 工具 | `tool:read` | ✓ | ✓ | ✓ | ✓ |
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
current_user: User = Depends(PermissionChecker("user:read"))

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
