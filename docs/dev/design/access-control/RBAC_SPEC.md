# 当前权限设计（以代码实现为准）

本文档基于当前代码实现整理权限设计，不以历史设计稿或分析文档为准。

权威实现入口：

- `backend/app/core/permissions.py`：系统权限定义
- `backend/app/core/init_data.py`：内置角色与默认角色初始化
- `backend/app/services/team_role_sync.py`：团队角色到团队作用域角色授权的同步
- `backend/app/api/deps.py`：认证与 `PermissionChecker`
- `backend/app/api/v1/endpoints/teams.py`：团队成员角色边界

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

主要权限：

- 后台管理能力：包含 `admin:dashboard:access`、用户/角色/权限读取、模型管理、设置读取、SSO 读取、审计读取/导出等；部分高危后台变更能力仅 Super Admin 拥有
- 平台业务能力：包含团队范围的 Agent、Workflow、KB、Tool、Skill 等管理与使用权限

注意：当前代码中 `Admin` 角色既承担后台能力，也可作为团队作用域角色复用；但团队作用域 `Admin` 不能满足 `admin:*` 后台权限。

### 4.3 Member

普通协作型平台角色。

当前意图包括：

- 访问团队内常用业务资源
- 对 Agent、Workflow、KB、Tool、Skill 拥有创建和更新权限
- 可以使用 Agent、运行 Workflow、执行 Tool/Skill
- 不具备后台访问能力（无 `admin:*` 权限）
- 不具备 Agent / Workflow 的删除或发布权限

主要权限：

- `agent:read/create/update/chat`
- `workflow:read/create/update/run`
- `kb:read/create/update/delete`
- `tool:read/create/update/delete/execute`
- `skill:read/create/update/delete/execute`
- `team:read`、`apikey:*`、`conversation:read/delete`

### 4.4 Viewer

只读型平台角色，系统默认角色（新用户注册时自动分配）。

主要权限：

- `agent:read/chat`
- `workflow:read/run`
- `kb:read`
- `tool:read/execute`
- `skill:read/execute`
- `team:read`、`conversation:read`

### 4.5 默认角色与默认团队

默认分配逻辑位于 `backend/app/services/team_role_sync.py`，初始化逻辑位于 `backend/app/core/init_data.py`。

- `default_role_id`：新用户默认全局角色；系统初始化时如果为空，会写入 `Viewer` 角色 ID。
- `default_team_id`：配置后，新注册用户会自动加入该团队。
- `default_team_role`：自动加入默认团队时使用的团队角色，默认 `member`。
- 自动团队角色只允许 `viewer`、`member`、`admin`；配置异常时回退到 `member`。
- `owner` 不会作为自动默认团队角色分配。

注意：默认全局角色和默认团队角色是两套概念。全局角色提供 permission code，团队角色只决定用户在某个 team 内的管理级别。

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
- 能力管理权限（后台）：`admin:capability:read/create/update/delete/execute`，覆盖工具与技能的系统级管理
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
- Tool 权限：`tool:read/create/update/delete/execute`
- Skill 权限：`skill:read/create/update/delete/execute`
- Memory 权限

### 5.3 现状限制

当前权限定义源与角色初始化列表并未完全收敛，存在以下现象：

- 有些权限在角色初始化中被引用，但不在权限定义常量中
- 前端某些页面依赖的权限，也可能未在统一权限定义中出现

因此，当前实现已经形成了稳定的权限分层思路，但权限字典仍有漂移。

---

## 6. 团队成员角色与作用域 RBAC 的关系

当前代码通过 `backend/app/services/team_role_sync.py` 将 `TeamMember.role` 维护为团队作用域角色授权，而不是再授予或移除全局 `Admin` / `Member`。

### 6.1 ScopedRoleAssignment

团队作用域授权存储在 `ScopedRoleAssignment`：

- `user`：授权用户
- `role`：复用现有 `Role`
- `scope_type`：当前为 `team`
- `scope_id`：团队 ID
- `source`：`manual`、`migration`、`system` 等来源标记
- `(user, role, scope_type, scope_id)` 唯一

启动初始化会幂等创建表和索引，并从现有 `TeamMember` 回填团队作用域授权。

### 6.2 映射规则

当前规则：

- 团队 `owner` / `admin` -> 该 team 下的作用域 `Admin`
- 团队 `member` -> 该 team 下的作用域 `Member`
- 团队 `viewer` -> 该 team 下的作用域 `Viewer`

该同步不会删除或授予用户的全局角色。历史上由团队角色同步出来的全局 `Admin` / `Member` 因无法区分来源，不会自动批量清理。

### 6.3 权限解析规则

作用域权限检查使用 `check_scoped_permission(user, code, scope_type, scope_id)`：

1. `is_superuser` 直接通过
2. 全局角色命中目标 permission 或 `*` 时通过
3. 对非 `admin:*` 权限，团队作用域角色命中目标 permission 或 `*` 时通过
4. 其他情况拒绝

`admin:*` 始终只允许全局角色或超级管理员满足，团队作用域角色不能授予后台管理权限。

### 6.4 触发时机

以下团队操作会维护团队作用域授权：

- 添加成员
- 修改成员角色
- 移除成员
- 主动离开团队
- 转移所有权

默认团队注册流程会创建 `TeamMember`，并立即同步为团队作用域授权。

### 6.5 团队 Viewer 与只可浏览权限

团队 `viewer` 和全局 `Viewer` 不是同一个角色：

- 团队 `viewer` 只表示用户在某个团队内处于最低管理级别。
- 团队 `viewer` 不会自动授予全局 `Viewer` 角色。
- 全局 `Viewer` 才提供 `team:read`、`agent:read/chat`、`workflow:read/run`、`kb:read`、`tool:read/execute`、`skill:read/execute` 等 permission code。

因此，“只可浏览”在当前实现中更准确地表示：不能 create / update / delete / publish，但可以在已有资源上执行安全使用类动作，例如 chat、run、execute。

---

## 7. 团队范围资源访问控制

当前平台资源大多按团队隔离。

典型模式是在各资源 endpoint 中实现一个 `check_team_access()` helper。

常见逻辑：

1. 检查 team 是否存在
2. 超级管理员直接放行
3. 检查用户是否为该 team 成员
4. 如果是写操作或管理操作，且 `require_admin=True`
   - 常见要求是团队角色必须是 `owner` 或 `admin`
   - 但各资源 helper 仍有差异，KB 的后台路径可绕过普通团队成员校验

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
- 某些操作必须是 `owner/admin`；具体以对应 endpoint/helper 为准

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
- `admin:capability:*`
- `admin:knowledge-base:*`
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
- `skill:*`
- `memory:*`

### 10.3 管理后台知识库接口与平台知识库接口

知识库管理接口按使用场景分为两套：

- 工作台使用 `/api/v1/knowledge-bases/*`，检查 `kb:*`，并执行 team membership / resource visibility 校验。
- 管理后台使用 `/api/v1/admin/knowledge-bases/*`，检查 `admin:knowledge-base:*`，用于跨团队的系统级管理。

### 10.4 管理后台包接口与平台包接口

导入导出接口按使用场景分为两套：

- 工作台使用 `/api/v1/packages/*`，只检查平台业务权限，例如 `tool:*`、`agent:*`、`workflow:*`、`kb:*`，并继续执行 team membership / resource visibility 校验。
- 管理后台使用 `/api/v1/admin/packages/*`，只检查后台权限，例如 `admin:capability:*` 与 `admin:knowledge-base:*`，用于跨团队的系统级管理。

这些接口不通过 `_has_permission()` 做隐式权限映射。后台权限不会让平台接口自动通过，平台权限也不会让后台接口自动通过。

### 10.5 `admin:capability:*` 与 `tool:*` / `skill:*` 的关系

`admin:capability:*` 是工具与技能的**管理后台权限**，`tool:*` / `skill:*` 是工作台侧 team-scoped 权限。

- 管理后台工具导入导出通过 `/api/v1/admin/packages/*` 检查 `admin:capability:read/create/update`。
- 工作台工具导入导出通过 `/api/v1/packages/*` 检查 `tool:read/create/update`。
- 两者权限 code 不互相覆盖，避免后台权限泄漏到工作台路径。

### 10.6 实际运行方式

`Admin` 角色当前同时拥有后台权限和平台业务权限，因此该内置角色可以访问管理后台，也可以在工作台操作团队资源。若未来要表达“只能管理后台操作、不能工作台操作”的角色，应只授予 `admin:*` 权限，不授予对应的平台业务权限。

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
- `/knowledge-bases` -> `admin:knowledge-base:read`
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

- **全局角色体系** 与 **团队作用域授权体系** 同时存在
- `team_role_sync` 只维护团队作用域授权，不再把团队角色同步为全局 `Admin` / `Member`

因此，当前系统更准确的描述应为：

> 一个以全局 RBAC 为全局能力层、以团队作用域 RBAC 为 team 内能力层、以资源可见性为对象层的复合权限系统。

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

- 后端权限定义（`backend/app/core/permissions.py`）
- 系统角色初始化逻辑（`backend/app/core/init_data.py`）
- 前端路由/菜单权限映射

### 13.5 后台权限与平台权限不要隐式互认

后台接口应使用 `admin:*` 权限，平台接口应使用平台业务权限。需要两个场景都可操作的角色，应显式同时授予两套权限，而不是在权限检查 helper 里做隐式覆盖。

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
