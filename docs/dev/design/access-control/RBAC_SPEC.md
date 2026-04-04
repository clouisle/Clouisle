# 当前权限设计（以代码实现为准）

本文档基于当前代码实现整理权限设计，不以历史设计稿或分析文档为准。

适用范围：

- 后端认证与授权
- 全局角色与权限模型
- 团队成员角色
- 团队作用域资源访问控制
- Agent / Workflow 私有可见性规则
- 前端路由权限映射

---

## 1. 总体结构

当前实现不是单一 RBAC，而是四层叠加：

1. **超级管理员绕过层**
   - `User.is_superuser = True` 时绕过常规权限检查。
2. **全局 RBAC 层**
   - `User -> Role -> Permission`。
   - 用于判断用户是否具备某类操作能力。
3. **团队成员角色层**
   - `TeamMember.role` 用于判断用户在某个团队中的管理级别。
4. **资源可见性层**
   - Agent / Workflow 等资源还会叠加 `private / team` 等可见性规则。

可以概括为：

- **全局权限**：决定“能不能做这类事”
- **团队角色**：决定“能不能操作这个 team 下的资源”
- **资源可见性**：决定“能不能访问这个具体对象”

---

## 2. 认证与基础权限检查

### 2.1 用户认证

当前支持两类认证：

- JWT Bearer Token
- API Key

认证入口位于 `backend/app/api/deps.py`：

- `get_current_user()`：JWT 认证
- `get_current_user_or_api_key()`：JWT / API Key 二选一
- `get_current_active_user()`：附加 `is_active` 校验

### 2.2 超级管理员

`User.is_superuser` 是最高权限开关。

在 `PermissionChecker` 中，超级管理员直接放行，不再检查角色权限。

这意味着：

- 超级管理员不依赖角色上的 permission code
- 超级管理员也通常跳过 team membership 校验

### 2.3 PermissionChecker

统一权限检查入口为 `PermissionChecker(required_permission)`。

检查逻辑：

1. 若 `current_user.is_superuser`，直接通过
2. 否则遍历用户的所有全局角色
3. 遍历角色下所有权限
4. 若命中目标权限或 `*`，则通过
5. 否则返回 403

该检查本身**不负责团队范围和资源归属判断**。

---

## 3. 数据模型

### 3.1 全局权限模型

#### Permission

表示最小权限单元。

字段：

- `id`
- `scope`
- `code`
- `description`
- `is_system`

说明：

- `is_system=True` 表示系统内置权限，不允许普通接口修改或删除
- `code` 是权限判断的唯一标识

#### Role

表示权限集合。

字段：

- `id`
- `name`
- `description`
- `is_system_role`
- `permissions`（多对多）

说明：

- `is_system_role=True` 的角色不允许通过角色管理接口修改或删除

#### User

用户通过 `roles` 多对多关联全局角色。

另有：

- `is_superuser`
- `is_active`

### 3.2 团队模型

#### Team

团队是平台内大多数业务资源的隔离边界。

#### TeamMember

团队成员关系表。

关键字段：

- `team`
- `user`
- `role`
- `joined_at`

`role` 当前实际取值：

- `owner`
- `admin`
- `member`
- `viewer`

说明：

- 这不是全局 RBAC 角色，而是**团队内角色**
- 主要用于团队范围资源的管理权限判断

---

## 4. 当前系统内置全局角色

当前代码初始化的系统角色位于 `backend/app/core/init_data.py`。

实际内置角色如下：

### 4.1 Super Admin

系统级最高角色。

特点：

- 设计上表示全权限角色
- 与 `is_superuser` 概念接近，但二者并不完全等价
- 实际运行时，真正具有绝对绕过能力的是 `is_superuser`

### 4.2 Admin

高权限平台角色。

当前意图包括：

- 访问管理后台
- 读取和管理系统级资源
- 管理团队内业务资源

注意：当前代码中 `Admin` 角色既承担后台能力，也会被团队角色同步逻辑自动授予，见下文。

### 4.3 Member

普通协作型平台角色。

当前意图包括：

- 访问团队内常用业务资源
- 创建与修改部分业务对象
- 不具备后台访问能力

### 4.4 Viewer

只读型平台角色。

当前更接近默认基础角色。

### 4.5 现状说明

虽然存在内置全局角色，但当前实现中：

- `Admin` / `Member` 会被团队成员角色自动同步
- `Viewer` 不会由团队 `viewer` 自动同步得到

因此，全局角色并非完全独立于团队体系。

---

## 5. 当前系统权限命名

### 5.1 命名风格

当前代码里主要存在两类权限命名：

#### 管理后台权限

格式通常为：

- `admin:<resource>:<action>`

例如：

- `admin:dashboard:access`
- `admin:user:read`
- `admin:role:create`
- `admin:permission:update`
- `admin:settings:read`

#### 平台业务权限

格式通常为：

- `<resource>:<action>`

例如：

- `team:read`
- `team:update`
- `team:manage`
- `agent:read`
- `workflow:create`
- `kb:update`
- `tool:delete`
- `memory:read`

### 5.2 当前代码中的权限类别

按代码定义，当前主要包括：

- 管理后台访问权限
- 用户管理权限
- 角色管理权限
- 权限管理权限
- 团队管理权限（后台）
- 模型管理权限（后台）
- 系统设置权限
- SSO 管理权限
- 会话查看权限（后台）
- 记忆管理权限（后台）
- 通知管理权限（后台）
- 审计日志权限
- 团队权限（平台）
- Agent 权限
- Workflow 权限
- Knowledge Base 权限
- Tool 权限
- Memory 权限

### 5.3 现状限制

当前权限定义源与角色初始化列表并未完全收敛，存在以下现象：

- 有些权限在角色初始化中被引用，但不在权限定义常量中
- 前端某些页面依赖的权限，也可能未在统一权限定义中出现

因此，当前实现已经形成了稳定的权限分层思路，但权限字典仍有漂移。

---

## 6. 团队成员角色与全局角色的关系

当前代码存在一个重要同步机制：

- `backend/app/services/team_role_sync.py`

其逻辑是根据用户在所有团队中的最高角色，同步用户的全局角色。

### 6.1 映射规则

当前规则：

- 只要用户在任意团队中是 `owner` 或 `admin`
  - 确保用户拥有全局 `Admin`
  - 同时确保用户拥有全局 `Member`
- 如果用户最高团队角色是 `member`
  - 移除全局 `Admin`
  - 确保拥有全局 `Member`
- 如果用户只有 `viewer` 或已不在任何团队中
  - 移除全局 `Admin`
  - 移除全局 `Member`
  - 保留其他角色（例如默认 `Viewer`）

### 6.2 触发时机

以下团队操作会触发同步：

- 添加成员
- 修改成员角色
- 移除成员
- 主动离开团队

### 6.3 影响

这意味着当前实现里：

- 全局 `Admin` / `Member` 不是纯粹静态角色
- 它们会被团队角色反向驱动
- 团队角色与全局角色在语义上已经耦合

这是当前权限体系最核心的实现特征之一。

---

## 7. 团队范围资源访问控制

当前平台资源大多按团队隔离。

典型模式是在各资源 endpoint 中实现一个 `check_team_access()` helper。

常见逻辑：

1. 检查 team 是否存在
2. 超级管理员直接放行
3. 检查用户是否为该 team 成员
4. 如果是写操作或管理操作，且 `require_admin=True`
   - 要求团队角色必须是 `owner` 或 `admin`

### 7.1 资源模块中的统一模式

以下模块都采用类似模式：

- Agents
- Workflows
- Tools
- Knowledge Bases
- Conversations
- Notifications
- Team Models
- Teams

### 7.2 当前实际语义

当前访问控制通常分两步：

#### 第一步：全局 permission

例如：

- `agent:update`
- `workflow:read`
- `team:manage`

#### 第二步：团队范围约束

例如：

- 必须是该 team 成员
- 某些操作必须是 `owner/admin`

因此，拥有某个 permission code 并不代表可以操作任意团队的数据。

---

## 8. Team 接口中的团队角色规则

当前 `teams` 相关接口体现了团队角色的真实边界。

### 8.1 读取团队

- 需要全局权限：`team:read`
- 若不是超级管理员，还必须是该团队成员

### 8.2 更新团队信息

- 需要全局权限：`team:update`
- 若不是超级管理员，还必须是该团队的 `owner` 或 `admin`

### 8.3 添加 / 移除团队成员

- 需要全局权限：`team:manage`
- 若不是超级管理员，还必须是该团队的 `owner` 或 `admin`

### 8.4 修改成员角色

- 需要全局权限：`team:manage`
- 若不是超级管理员，必须是该团队的 `owner`

### 8.5 转移所有权

- 需要全局权限：`team:manage`
- 必须是当前团队的 `owner`

### 8.6 离开团队

- 需要全局权限：`team:read`
- `owner` 不能直接离开，必须先转移所有权

---

## 9. Agent / Workflow 的资源可见性规则

Agent 和 Workflow 在团队访问控制之外，还叠加资源可见性。

### 9.1 Agent

当前实现中：

- `private`
  - 仅创建者可访问
  - 若创建者已不存在，则退化为按团队访问控制判断
- 非 `private`
  - 按团队成员关系判断访问

写操作场景会进一步要求团队管理员级权限。

### 9.2 Workflow

Workflow 采用与 Agent 类似的模式：

- `private`
  - 优先限定为创建者本人可访问
  - 创建者缺失时回退到团队访问控制
- `team`
  - 按团队成员访问

### 9.3 结论

当前实现中，资源是否可访问不只取决于 RBAC，还取决于：

- 是否是创建者
- 资源可见性
- 是否是该 team 成员
- 是否具有团队管理员身份

---

## 10. 管理后台与平台权限的边界

当前代码已经形成两块边界较清晰的能力域：

### 10.1 管理后台

面向系统级配置与全局资源管理。

典型权限：

- `admin:dashboard:access`
- `admin:user:*`
- `admin:role:*`
- `admin:permission:*`
- `admin:model:*`
- `admin:settings:*`
- `audit:*`

### 10.2 平台业务侧

面向 team-scoped 资源的日常操作。

典型权限：

- `team:*`
- `agent:*`
- `workflow:*`
- `kb:*`
- `tool:*`
- `memory:*`

### 10.3 实际运行方式

虽然后台权限与平台权限已经分层，但 `Admin` 角色当前可能同时拥有两边的权限，因此在角色语义上仍偏重叠。

---

## 11. 前端权限消费方式

前端通过当前用户的角色与权限列表聚合出权限集合。

核心模式：

1. 拉取当前用户信息
2. 收集 `user.roles[].permissions[].code`
3. 形成去重后的权限集合
4. 用于路由与菜单显隐判断

当前前端路由已为多个页面绑定 required permission，例如：

- `/dashboard` -> `admin:dashboard:access`
- `/teams` -> `team:read`
- `/knowledge-bases` -> `kb:read`
- `/users` -> `admin:user:read`
- `/roles` -> `admin:role:read`
- `/permissions` -> `admin:permission:read`
- `/models` -> `admin:model:read`
- `/tools` -> `tool:read`
- `/api-keys` -> `apikey:read`
- `/memories` -> `admin:memory:read`
- `/audit-logs` -> `audit:read`

注意：

- 前端路由权限映射依赖权限 code 字符串
- `/site-settings/sso` 当前已绑定 `admin:sso:read`
- SSO 页面内创建、修改、删除、测试、断开连接等变更操作当前已绑定 `admin:sso:update`
- Storage 页面中的“归档审计日志”操作当前单独绑定 `audit:export`，不再复用 `admin:settings:update`
- Dashboard 的 TOTP 统计接口当前绑定 `admin:dashboard:access`
- 若后端权限定义、角色初始化、前端映射三者不一致，会出现菜单或页面权限漂移

---

## 12. 当前设计的关键特征

### 12.1 已经成立的部分

当前代码中，以下设计已经明确成立：

- 使用全局 RBAC 进行功能授权
- 使用 TeamMember 进行团队范围控制
- 使用资源可见性处理 private/team 访问差异
- 超级管理员拥有统一绕过能力
- 团队是大多数平台资源的隔离边界

### 12.2 当前最重要的实现事实

当前权限体系并非“只有内置角色 + 权限表”，而是：

- **全局角色体系** 与 **团队成员体系** 同时存在
- 且两者通过 `team_role_sync` 存在反向同步

因此，当前系统更准确的描述应为：

> 一个以全局 RBAC 为能力层、以 TeamMember 为作用域层、以资源可见性为对象层的复合权限系统。

### 12.3 当前主要问题

从实现现状看，最突出的问题不是没有权限体系，而是：

1. 全局角色与团队角色存在语义重叠
2. `Admin / Member / Viewer` 在全局与团队语境下容易混淆
3. 权限定义源、角色初始化列表、前端权限映射尚未完全收敛
4. 各资源模块的团队访问 helper 逻辑相似，但仍分散在多个文件中

---

## 13. 当前应遵循的实现原则

新增或调整权限相关功能时，应遵循以下原则：

### 13.1 新接口先定义全局 permission

所有需要受控的功能入口，都应先明确对应的 permission code。

### 13.2 Team 资源必须显式校验 team membership

只做 `PermissionChecker` 不足以保证团队隔离。

如果资源带 `team_id`，应继续校验：

- 当前用户是否属于该 team
- 对于管理动作，是否需要 `owner/admin`

### 13.3 私有资源必须显式校验创建者或可见性规则

如资源支持 `private`，必须额外处理创建者访问规则。

### 13.4 角色与权限变更要同时检查三处

变更权限时至少需要核对：

- 后端权限定义
- 系统角色初始化逻辑
- 前端路由/菜单权限映射

---

## 14. 文档结论

当前系统的权限设计可以归纳为：

- **身份绕过层**：`is_superuser`
- **能力层**：全局 `User -> Role -> Permission`
- **作用域层**：`TeamMember.role`
- **对象层**：资源可见性与创建者规则

内置角色当前实际为：

- `Super Admin`
- `Admin`
- `Member`
- `Viewer`

团队角色当前实际为：

- `owner`
- `admin`
- `member`
- `viewer`

这两套角色体系当前共同参与权限决策，并通过同步逻辑发生耦合。后续若要继续收敛设计，应优先明确：

- 全局角色只表达能力，还是也表达组织层级
- 团队角色是否只保留团队作用域语义
- `Admin / Member / Viewer` 是否需要与 team role 改名或彻底解耦
