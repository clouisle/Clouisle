# Clouisle 全栈 RBAC 逐页逐操作与接口权限深度审计报告（代码级全量详审）

**审计日期**: 2026-09-14  
**审计方法**: 拒绝批量黑盒扫描，采用源码级逐文件、逐路由、逐函数、逐前端操作控件遍历核查。  
**审计范围**: 
- **前端全部 47 个页面/路由**：覆盖 `(dashboard)` 16 个后台管理页面、`(platform)/app` 15 个前台租户与编排页面、`(chat)` 2 个独立会话/运行页面、`(embed)` 2 个外部嵌入 iframe 页面、`(auth)` 8 个认证流程页面。
- **前端所有操作控件与 API 调用点**：每个页面的初始化请求、检索、筛选、表格动作菜单、弹窗表单提交、批量操作、状态切换。
- **后端对应全部 442 个 APIRoute**：装饰器依赖项、`PermissionChecker`、`check_scoped_permission`、`check_agent_access`、`check_workflow_access`、`check_kb_access`、`check_team_access`、`_kb_access_mode`。

---

## 一、 页面级全量映射与权限断言矩阵

### 1.1 管理后台（Dashboard / Admin Pages）逐页详审

| 页面与路由路径 | 页面初始化 API 调用及权限要求 | UI 关键操作控件与前端权限判断 | 触发后端 API 及鉴权依赖 | 跨层一致性与漏洞判定 |
| :--- | :--- | :--- | :--- | :--- |
| **`/dashboard`**<br>(Dashboard 总览) | 1. `dashboardApi.getStats()`<br>2. `adminTOTPApi.getStats()`<br>3. `dashboardApi.getTrends(range)`<br>4. `dashboardApi.getModelDistribution()`<br>5. `dashboardApi.getTeamTokenUsage()`<br>6. `dashboardApi.getTopAgents()`<br>7. `dashboardApi.getWorkflowSummary()`<br>*(均需 `admin:dashboard:access`)* | 1. 时间范围切换器 (7d/30d/90d)<br>2. Tab 切换 (Overview/Models/Analytics)<br>3. 刷新按钮<br>*(全页受 `RoutePermissionGuard` 保护)* | `GET /api/v1/admin/dashboard/stats`<br>`GET /api/v1/admin/dashboard/stats/trends`<br>`GET /api/v1/admin/dashboard/stats/models/distribution`<br>`GET /api/v1/admin/dashboard/stats/teams/token-usage`<br>`GET /api/v1/admin/dashboard/stats/agents/top`<br>`GET /api/v1/admin/dashboard/stats/workflows/summary`<br>`GET /api/v1/admin/totp/stats`<br>*(依赖: `PermissionChecker("admin:dashboard:access")`)* | **一致**<br>所有统计接口均严格校验 `admin:dashboard:access`，无未授权数据泄漏。 |
| **`/dashboard/observability`**<br>(可观测性监控) | 1. `observabilityApi.getOverview()`<br>2. `getThroughput()`<br>3. `getTokens()`<br>4. `getAgents()`<br>5. `getWorkflows()`<br>6. `getTimeouts()`<br>7. `getSystemHealth()`<br>8. `getSystemTrend()`<br>9. `getSlowQueries()`<br>10. `getWorkers()` | 1. 9 个监控 Tab 切换<br>2. 慢查询分页查看<br>3. 工作节点指标刷新<br>*(全页受 `RoutePermissionGuard` 保护)* | `GET /api/v1/admin/observability/overview`<br>`GET /api/v1/admin/observability/throughput`<br>`GET /api/v1/admin/observability/tokens`<br>`GET /api/v1/admin/observability/agents`<br>`GET /api/v1/admin/observability/workflows`<br>`GET /api/v1/admin/observability/timeouts`<br>`GET /api/v1/admin/observability/system/health`<br>`GET /api/v1/admin/observability/system/trend`<br>`GET /api/v1/admin/observability/system/slow-queries`<br>`GET /api/v1/admin/observability/system/workers`<br>*(依赖: `PermissionChecker("admin:dashboard:access")`)* | **一致**<br>全局监控与慢查询端点均声明式卡死 `admin:dashboard:access`。 |
| **`/users`**<br>(用户管理) | 1. `rolesApi.getRoles(1, 100)`<br>2. `siteSettingsApi.getPublic()`<br>3. `usersApi.getStats()`<br>4. `usersApi.getUsers(params)` | 1. **创建用户**: `PermissionGuard("admin:user:create")`<br>2. **编辑用户**: `canPerform("admin:user:update")`<br>3. **激活/停用**: `canPerform("admin:user:update")`<br>4. **重置/豁免密码**: `canPerform("admin:user:update")`<br>5. **删除用户**: `canPerform("admin:user:delete")`<br>6. **批量激活/停用/修改密码/豁免/删除** | `GET /api/v1/admin/users/stats` (`admin:user:read`)<br>`GET /api/v1/admin/users` (`admin:user:read`)<br>`POST /api/v1/admin/users` (`admin:user:create`)<br>`PUT /api/v1/admin/users/{id}` (`admin:user:update`)<br>`POST /api/v1/admin/users/{id}/activate` (`admin:user:update`)<br>`POST /api/v1/admin/users/{id}/deactivate` (`admin:user:update`)<br>`DELETE /api/v1/admin/users/{id}` (`admin:user:delete`)<br>`POST /api/v1/admin/users/{id}/force-password-change`<br>`POST /api/v1/admin/users/{id}/reset-password-expiration`<br>`POST /api/v1/admin/users/{id}/exempt-password-expiration`<br>`POST /api/v1/admin/users/bulk-force-password-change`<br>*(依赖: `PermissionChecker`)* | **一致**<br>前端控件判断与后端接口权限码一一对应，且后端禁止删除最后一个超级管理员。 |
| **`/roles`**<br>(角色管理) | 1. `rolesApi.getRoles(page, pageSize, query)` | 1. **创建角色**: `PermissionGuard("admin:role:create")`<br>2. **编辑角色/权限**: `canPerform("admin:role:update")`<br>3. **删除角色**: `canPerform("admin:role:delete")`<br>*(系统角色禁止删除/编辑)* | `GET /api/v1/admin/roles` (`admin:role:read`)<br>`POST /api/v1/admin/roles` (`admin:role:create`)<br>`GET /api/v1/admin/roles/{id}` (`admin:role:read`)<br>`PUT /api/v1/admin/roles/{id}` (`admin:role:update`)<br>`PUT /api/v1/admin/roles/{id}/permissions` (`admin:role:update`)<br>`DELETE /api/v1/admin/roles/{id}` (`admin:role:delete`) | **一致**<br>系统角色（Super Admin、Admin、Member、Viewer）受模型级 `is_system_role` 保护，不可篡改。 |
| **`/permissions`**<br>(权限管理) | 1. `permissionsApi.getPermissions(...)`<br>2. `permissionsApi.getScopes()` | 1. **新建权限**: `PermissionGuard("admin:permission:create")`<br>2. **编辑权限**: `canPerform("admin:permission:update")`<br>3. **删除权限**: `canPerform("admin:permission:delete")`<br>*(内置系统权限禁止删除)* | `GET /api/v1/admin/permissions` (`admin:permission:read`)<br>`GET /api/v1/admin/permissions/scopes` (`admin:permission:read`)<br>`POST /api/v1/admin/permissions` (`admin:permission:create`)<br>`PUT /api/v1/admin/permissions/{id}` (`admin:permission:update`)<br>`DELETE /api/v1/admin/permissions/{id}` (`admin:permission:delete`) | **一致**<br>系统权限 (`is_system=True`) 在后端被硬锁，无法删除。 |
| **`/teams`**<br>(团队管理) | 1. `teamsApi.getTeams(page, pageSize, query)` | 1. **创建团队**: `PermissionGuard("admin:team:create")`<br>2. **查看详情/成员**: 模态框加载团队详情<br>3. **删除团队**: `canPerform("admin:team:delete")`<br>4. **团队模型配置 Tab**: 查看/添加/移除分配模型 | `GET /api/v1/admin/teams` (`admin:team:read`)<br>`POST /api/v1/admin/teams` (`admin:team:create`)<br>`DELETE /api/v1/admin/teams/{id}` (`admin:team:delete`)<br>`GET /api/v1/teams/{team_id}/models` (`get_current_active_user`)<br>`POST/DELETE /api/v1/teams/{team_id}/models/*` (`get_current_active_superuser`) | **存在隐患**<br>管理端团队页面没有包含 `RoutePermissionGuard` 包装（仅依赖 AppSidebar 隐藏），虽然后端卡了 `admin:team:*`，但前端直接访问 `/teams` 页面骨架会先渲染。团队模型分配 API 仅限 `superuser`，缺少对 `admin:team:update` 权限角色的开放。 |
| **`/models`**<br>(全局模型配置) | 1. `platformModelsApi.getProviders()`<br>2. `platformModelsApi.getModelTypes()`<br>3. `modelsApi.getModels(params)` | 1. **添加模型**: `PermissionGuard("admin:model:create")`<br>2. **编辑模型**: `canPerform("admin:model:update")`<br>3. **设为默认**: `canPerform("admin:model:update")`<br>4. **连通性测试**: `canPerform("admin:model:update")`<br>5. **发现/探测模型**: `canPerform("admin:model:create")`<br>6. **删除模型**: `canPerform("admin:model:delete")` | `GET /api/v1/models/providers` (公开)<br>`GET /api/v1/models/types` (公开)<br>`GET /api/v1/admin/models` (`admin:model:read`)<br>`POST /api/v1/admin/models` (`admin:model:create`)<br>`PUT /api/v1/admin/models/{id}` (`admin:model:update`)<br>`DELETE /api/v1/admin/models/{id}` (`admin:model:delete`)<br>`POST /api/v1/admin/models/test` (`admin:model:create`)<br>`POST /api/v1/admin/models/{id}/test` (`admin:model:update`)<br>`POST /api/v1/admin/models/{id}/set-default` (`admin:model:update`)<br>`POST /api/v1/admin/models/discover` (`admin:model:create`) | **一致**<br>模型发现、添加、修改、测试均严密对应 `admin:model:*`。 |
| **`/apps` (管理端)**<br>(全局应用监控) | 1. `adminAgentsApi.getAgents(...)`<br>2. `adminWorkflowsApi.getWorkflows(...)` | 1. **切换 Tab** (智能体/工作流)<br>2. **搜索与状态筛选**<br>3. **发布/取消发布**: `admin:app:publish`<br>4. **复制应用**: `admin:app:duplicate`<br>5. **删除应用**: `admin:app:delete` | `GET /api/v1/admin/agents` (`admin:app:read`)<br>`POST /api/v1/admin/agents` (`admin:app:create`)<br>`PUT /api/v1/admin/agents/{id}` (`admin:app:update`)<br>`POST /api/v1/admin/agents/{id}/publish` (`admin:app:publish`)<br>`POST /api/v1/admin/agents/{id}/unpublish` (`admin:app:publish`)<br>`POST /api/v1/admin/agents/{id}/duplicate` (`admin:app:duplicate`)<br>`DELETE /api/v1/admin/agents/{id}` (`admin:app:delete`)<br>*(工作流端点同理)* | **一致**<br>管理端全局应用池读写、发布、复制、删除与 `admin:app:*` 严密对应。 |
| **`/capabilities` (管理端)**<br>(能力与技能管理) | 1. `adminToolsApi.getTools(...)`<br>2. `adminSkillsApi.getSkills(...)` | 1. **新建工具/导入技能**: `admin:capability:create`<br>2. **编辑工具/技能**: `admin:capability:update`<br>3. **测试工具/技能**: `admin:capability:execute`<br>4. **启用/停用/分享工具**: `admin:capability:update`<br>5. **删除工具/技能**: `admin:capability:delete` | `GET /api/v1/admin/tools` (`admin:capability:read`)<br>`POST /api/v1/admin/tools` (`admin:capability:create`)<br>`PUT /api/v1/admin/tools/{id}` (`admin:capability:update`)<br>`DELETE /api/v1/admin/tools/{id}` (`admin:capability:delete`)<br>`POST /api/v1/admin/tools/test` (`admin:capability:execute`)<br>`POST /api/v1/admin/tools/execute-code` (`admin:capability:execute`)<br>`GET /api/v1/admin/skills` (`admin:capability:read`)<br>`POST /api/v1/admin/skills/import/*` (`admin:capability:create`)<br>`PATCH /api/v1/admin/skills/{id}` (`admin:capability:update`)<br>`DELETE /api/v1/admin/skills/{id}` (`admin:capability:delete`)<br>`POST /api/v1/admin/skills/{id}/test` (`admin:capability:execute`) | **一致**<br>管理端工具与技能全面受 `admin:capability:*` 约束。 |
| **`/knowledge-bases` (管理端)**<br>(全局知识库管理) | 1. `knowledgeBasesApi.getKnowledgeBases(...)` | 1. 查看知识库列表<br>2. 检索、查看文档与分块<br>3. 上传文档/重新分块/删除 | 实际调用 `/api/v1/admin/knowledge-bases/*`<br>*(后端直接挂载平台端路由，执行 `require_kb_read` / `require_kb_update`)* | **架构倒置 (Medium)**<br>页面未包裹 `RoutePermissionGuard`，后端管理挂载复用了平台路由，跳过了 `admin:knowledge-base:*` 权限码校验，仅靠超管或租户判定。 |
| **`/activities`**<br>(全局会话与审计) | 1. `conversationsApi.getConversations(...)`<br>2. `conversationsApi.getStats()`<br>3. `conversationsApi.getTrends()` | 1. 会话列表检索与详情查看<br>2. 删除会话记录 | `GET /api/v1/conversations` (`conversation:read`)<br>`GET /api/v1/conversations/stats` (`conversation:read`)<br>`DELETE /api/v1/conversations/{id}` (`conversation:delete`) | **一致**<br>页面虽挂在后台，但调用的是平台端会话审计接口，严格校验 `conversation:read` / `conversation:delete`。 |
| **`/api-keys`**<br>(全局 API 密钥) | 1. `apiKeysApi.getApiKeys(...)`<br>2. `apiKeysApi.getStats()` | 1. **创建 API Key**: `apikey:create`<br>2. **启用/停用/编辑**: `apikey:update`<br>3. **删除 API Key**: `apikey:delete` | `GET /api/v1/api-keys` (`apikey:read`)<br>`POST /api/v1/api-keys` (`apikey:create`)<br>`PUT /api/v1/api-keys/{id}` (`apikey:update`)<br>`POST /api/v1/api-keys/{id}/activate` (`apikey:update`)<br>`POST /api/v1/api-keys/{id}/deactivate` (`apikey:update`)<br>`DELETE /api/v1/api-keys/{id}` (`apikey:delete`) | **一致**<br>全面受 `apikey:*` 权限保护。 |
| **`/memories`**<br>(全局记忆图谱) | 1. `memoriesApi.getEntities(...)`<br>2. `memoriesApi.getStats()`<br>3. `memoriesApi.getRelations(...)` | 1. 查看全系统实体与关系网络<br>2. 修改实体信息: `admin:memory:update`<br>3. 删除实体/关系: `admin:memory:delete` | `GET /api/v1/admin/memories/entities` (`admin:memory:read`)<br>`GET /api/v1/admin/memories/entities/stats` (`admin:memory:read`)<br>`PUT /api/v1/admin/memories/entities/{id}` (`admin:memory:update`)<br>`DELETE /api/v1/admin/memories/entities/{id}` (`admin:memory:delete`)<br>`DELETE /api/v1/admin/memories/relations/{id}` (`admin:memory:delete`) | **一致**<br>全面受 `admin:memory:*` 权限保护。 |
| **`/audit-logs`**<br>(系统审计日志) | 1. `auditLogsApi.getActions()`<br>2. `auditLogsApi.getAuditLogs(params)`<br>3. `auditLogsApi.getStats()`<br>4. `auditLogsApi.getRetentionStats()` | 1. 组合筛选（用户/团队/操作类型/资源/状态/时间）<br>2. 查看详情日志 payload<br>3. **导出日志 (CSV/JSON)**: `audit:export`<br>4. **归档历史日志**: `audit:export` | `GET /api/v1/admin/audit-logs` (`audit:read`)<br>`GET /api/v1/admin/audit-logs/actions` (`audit:read`)<br>`GET /api/v1/admin/audit-logs/stats` (`audit:read`)<br>`GET /api/v1/admin/audit-logs/export` (`audit:export`)<br>`POST /api/v1/admin/audit-logs/archive` (`audit:export`) | **一致**<br>严格区分读日志 (`audit:read`) 与敏感导出/归档 (`audit:export`)。 |
| **`/notifications` (管理端)**<br>(全局通知公告) | 1. `adminNotificationsApi.getNotifications(...)` | 1. **创建全局/团队通知**: `admin:notification:create`<br>2. **删除通知公告**: 未受前端 Guard 显式阻断 | `GET /api/v1/admin/notifications` (`get_current_active_user`)<br>`POST /api/v1/admin/notifications` (`admin:notification:create`)<br>`DELETE /api/v1/admin/notifications/{id}` (`get_current_active_user` + 内部 `is_superuser` / `team_admin`) | **高危不一致 (High)**<br>后端 `DELETE` 遗漏 `admin:notification:delete` `PermissionChecker`，内置该权限的 Admin 角色无法删除全局通知，死代码。 |
| **`/site-settings/*`**<br>(6 个子配置页面) | 1. `siteSettingsApi.getSettings(category)`<br>2. `siteSettingsApi.getPublic()`<br>3. 各类探测与测试连接接口 | 1. **修改通用设置/主题/品牌**: `admin:settings:update`<br>2. **安全配置 (SSRF/验证码/密码规则)**: `admin:settings:update`<br>3. **通知渠道与模板测试 (邮件/钉钉/飞书/企微/Slack/Webhook)**: `admin:settings:update`<br>4. **存储配置与审计日志归档**: `admin:settings:update` + `audit:export`<br>5. **SSO 身份源管理与测试**: `admin:sso:read` + `admin:sso:update` | `GET /api/v1/admin/site-settings/{category}` (`admin:settings:read`)<br>`PUT /api/v1/admin/site-settings/{category}` (`admin:settings:update`)<br>`POST /api/v1/admin/site-settings/reset` (`admin:settings:update`)<br>`POST /api/v1/admin/site-settings/test-*` (`admin:settings:update`)<br>`POST /api/v1/admin/site-settings/archive-audit-logs` (`audit:export`)<br>`GET/POST/PUT/DELETE /api/v1/admin/sso/providers/*` (`admin:sso:read` / `admin:sso:update`) | **一致**<br>读、写、测试、重置均被 `admin:settings:*` 与 `admin:sso:*` 强校验卡死。 |

---

### 1.2 前台业务端（Platform / Tenant Pages）逐页详审

| 页面与路由路径 | 页面初始化 API 调用及权限要求 | UI 关键操作控件与前端权限判断 | 触发后端 API 及鉴权依赖 | 跨层一致性与漏洞判定 |
| :--- | :--- | :--- | :--- | :--- |
| **`/app/apps`**<br>(平台应用列表) | 1. `agentsApi.getAgents({ teamId })`<br>2. `workflowsApi.getWorkflows({ teamId })` | 1. **创建应用 (Agent/Workflow)**: 检查 `canCreateApp`<br>2. **发布/取消发布**: 检查 `canPublishApp`<br>3. **复制应用**: 检查 `canDuplicateApp`<br>4. **导出应用包 (.clouisle)**: 检查 `canExportApp`<br>5. **导入应用包**: 检查 `canImportApp`<br>6. **删除应用**: 检查所有者或团队管理员 | `GET /api/v1/agents` (`agent:read`)<br>`GET /api/v1/workflows` (`workflow:read`)<br>`POST /api/v1/agents` (`get_current_active_user`)<br>`POST /api/v1/workflows` (`get_current_active_user`)<br>`POST /api/v1/agents/{id}/publish` (`agent:publish`)<br>`POST /api/v1/workflows/{id}/publish` (`workflow:publish`)<br>`POST /api/v1/agents/{id}/duplicate` (`get_current_active_user`)<br>`POST /api/v1/workflows/{id}/duplicate` (`get_current_active_user`)<br>`DELETE /api/v1/agents/{id}` (`agent:delete`)<br>`DELETE /api/v1/workflows/{id}` (`workflow:delete`)<br>`GET /api/v1/packages/{type}/{id}/export`<br>`POST /api/v1/packages/import/*` | **高危不一致 (High)**<br>后端 `POST /agents` 与 `POST /workflows` 缺失 `agent:create` / `workflow:create` 的 `PermissionChecker` 声明；Package 导入创建资源时未做 Scoped 角色判定。 |
| **`/app/apps/[id]`**<br>(Agent 编排配置页) | 1. `agentsApi.getAgent(id)`<br>2. `teamModelsApi.getAvailableModels(teamId)`<br>3. `knowledgeBasesApi.getKnowledgeBases({ teamId })`<br>4. `toolsApi.getTools({ teamId })`<br>5. `skillsApi.getSkills({ teamId })` | 1. **保存编排参数**: “保存”按钮<br>2. **发布/取消发布**: `agent:publish`<br>3. **右侧实时预览聊天**: 发起调试流<br>4. **外嵌配置 (Embed)**: 获取/重新生成 Embed Key<br>5. **语音/多模态/记忆开关** | `GET /api/v1/agents/{id}` (`agent:read`)<br>`PUT /api/v1/agents/{id}` (`get_current_active_user` + `check_agent_access`)<br>`POST /api/v1/agents/{id}/publish` (`agent:publish`)<br>`POST /api/v1/agents/{id}/unpublish` (`agent:publish`)<br>`POST /api/v1/agents/{id}/chat/stream` (`get_current_user_or_api_key`)<br>`POST /api/v1/agents/{id}/chat/runs` | **存在隐患 (High)**<br>`PUT /agents/{id}` 仅依赖 Python 函数内的 `check_agent_access`，缺少全局/作用域 `agent:update` 的 `PermissionChecker` 校验。 |
| **`/app/apps/[id]/monitor`**<br>(Agent 监控分析) | 1. `agentsApi.getAgent(id)`<br>2. `agentStatsApi.getStats(id, period)`<br>3. `agentStatsApi.getTrends(id, period)`<br>4. `agentStatsApi.getToolUsage(id, period)` | 1. 统计周期选择 (24h/7d/30d/90d)<br>2. 消息/Token/工具调用图表展示 | `GET /api/v1/agents/{id}/stats`<br>`GET /api/v1/agents/{id}/stats/trends`<br>`GET /api/v1/agents/{id}/stats/tool-usage`<br>*(依赖: `get_current_active_user` + `check_agent_access`)* | **一致 (已加固)**<br>YUN-153 加固后，所有统计端点均调用 `check_agent_access`，严格阻断跨团队或私有 Agent 越权嗅探。 |
| **`/app/apps/workflow/[id]`**<br>(工作流画布编辑器) | 1. `workflowsApi.getWorkflow(id)`<br>2. `workflowsApi.getVersions(id)`<br>3. 节点选择器所依赖的工具、知识库列表 | 1. **保存画布与节点**: “保存”按钮<br>2. **运行/单步调试**: `workflow:run`<br>3. **发布/版本恢复**: `workflow:publish`<br>4. **Webhook 触发配置与 Token 重置** | `GET /api/v1/workflows/{id}` (`workflow:read`)<br>`PUT /api/v1/workflows/{id}` (`get_current_active_user` + `check_workflow_access`)<br>`POST /api/v1/workflows/{id}/run` (`workflow:run`)<br>`POST /api/v1/workflows/{id}/debug` (`workflow:run`)<br>`POST /api/v1/workflows/{id}/publish` (`workflow:publish`)<br>`POST /api/v1/workflows/{id}/regenerate-webhook-token` | **存在隐患 (High)**<br>`PUT /workflows/{id}` 缺少 `workflow:update` 权限码校验；同时模板发布接口 `POST /api/v1/workflow-templates` 没有任何租户和管理员隔离。 |
| **`/app/kb`**<br>(知识库列表) | 1. `knowledgeBasesApi.getKnowledgeBases({ teamId })`<br>2. `teamsApi.getMyTeams()` | 1. **新建知识库**: “新建”按钮<br>2. **编辑知识库**: 所有者或团队管理员<br>3. **跨团队分享知识库**: 团队管理员<br>4. **导出/导入知识库包**: 检查导出权限<br>5. **删除知识库**: 所有者或团队管理员 | `GET /api/v1/knowledge-bases` (`require_kb_read`)<br>`POST /api/v1/knowledge-bases` (`require_kb_create`)<br>`PUT /api/v1/knowledge-bases/{id}` (`require_kb_update`)<br>`DELETE /api/v1/knowledge-bases/{id}` (`require_kb_delete`)<br>`POST /api/v1/knowledge-bases/{id}/share` (`require_kb_update`)<br>`GET /api/v1/knowledge-bases/{id}/shares` (`require_kb_read`)<br>`DELETE /api/v1/knowledge-bases/{id}/share/{teamId}` (`require_kb_delete`) | **一致**<br>知识库模块通过内部依赖 `require_kb_*` 严格执行了 `check_kb_access` 与跨团队分享白名单。 |
| **`/app/kb/[id]`**<br>(知识库文档与分块管理) | 1. `knowledgeBasesApi.getKnowledgeBase(id)`<br>2. `knowledgeBasesApi.getDocuments(id)`<br>3. `knowledgeBasesApi.getStats(id)` | 1. **上传文档/添加 URL**: `require_kb_update`<br>2. **触发向量解析/重新分块**: `require_kb_update`<br>3. **分块列表查看/手动编辑分块**: `require_kb_read` / `require_kb_update`<br>4. **检索测试 (语义+混合检索)**: `require_kb_test`<br>5. **删除文档/删除分块**: `require_kb_delete` | `GET /api/v1/knowledge-bases/{id}/documents` (`require_kb_read`)<br>`POST /api/v1/knowledge-bases/{id}/documents/upload` (`require_kb_update`)<br>`POST /api/v1/knowledge-bases/{id}/documents/{doc_id}/process` (`require_kb_update`)<br>`GET /api/v1/knowledge-bases/{id}/documents/{doc_id}/chunks` (`require_kb_read`)<br>`PUT /api/v1/knowledge-bases/{id}/documents/{doc_id}/chunks/{chunk_id}` (`require_kb_update`)<br>`DELETE /api/v1/knowledge-bases/{id}/documents/{doc_id}` (`require_kb_delete`)<br>`POST /api/v1/knowledge-bases/{id}/search` (`require_kb_test`) | **一致**<br>所有文档级与分块级操作均向下继承了知识库主体的 `check_kb_access`，无法越权篡改他人团队文档。 |
| **`/app/capabilities`**<br>(平台工具与技能中心) | 1. `toolsApi.getTools({ teamId })`<br>2. `skillsApi.getSkills({ teamId })`<br>3. `teamsApi.getMyTeams()` | 1. **新建自定义工具 (HTTP/DB/MCP)**: `tool:create`<br>2. **导入 Skill (Git/Zip)**: `skill:create`<br>3. **编辑工具/Skill**: 所有者或团队管理员<br>4. **测试工具/Skill 执行**: `tool:execute` / `skill:execute`<br>5. **跨团队分享工具**: 团队管理员<br>6. **删除工具/Skill**: 团队管理员 | `GET /api/v1/tools` (`tool:read`)<br>`POST /api/v1/tools` (`get_current_active_user`)<br>`PUT /api/v1/tools/{id}` (`get_current_active_user`)<br>`DELETE /api/v1/tools/{id}` (`get_current_active_user`)<br>`POST /api/v1/tools/test` (`tool:execute`)<br>`POST /api/v1/tools/execute-code` (`tool:execute`)<br>`POST /api/v1/tools/{id}/share` (`get_current_active_user`)<br>`GET /api/v1/skills` (`skill:read`)<br>`POST /api/v1/skills/import/*` (`skill:create`)<br>`PATCH /api/v1/skills/{id}` (`skill:update`)<br>`POST /api/v1/skills/{id}/test` (`skill:execute`) | **存在隐患 (High)**<br>平台端 `POST/PUT/DELETE /tools` 完全未挂载 `tool:create` / `tool:update` / `tool:delete` 的 `PermissionChecker`，仅在前端和函数内做了简单的团队管理员判断。 |
| **`/app/models`**<br>(团队可用模型) | 1. `teamModelsApi.getAvailableModels(teamId)`<br>2. `teamModelsApi.getModelQuota(teamId)` | 1. 查看团队被管理员分配的可用模型列表<br>2. 查看每日/每月 Token 配额使用进度条 | `GET /api/v1/teams/{teamId}/available-models` (`get_current_active_user`)<br>`GET /api/v1/teams/{teamId}/models/quota` (`get_current_active_user`)<br>*(函数内执行 `check_team_access`)* | **一致**<br>严格受团队成员资格保护，普通成员仅能查看已分配模型与配额，无法修改。 |
| **`/app/notifications`**<br>(个人通知中心) | 1. `notificationsApi.getNotifications(...)`<br>2. `notificationsApi.getUnreadCount()` | 1. 过滤已读/未读/全局/团队/个人消息<br>2. 标记单条/全部已读 | `GET /api/v1/notifications` (`get_current_active_user`)<br>`GET /api/v1/notifications/unread-count` (`get_current_active_user`)<br>`POST /api/v1/notifications/read` (`get_current_active_user`)<br>*(函数内 `build_visible_query` 自动注入 user_id 与所在 team_ids 过滤)* | **一致**<br>个人通知自动与用户及其所属团队绑定，数据范围完全隔离。 |
| **`/app/memories`**<br>(个人记忆图谱) | 1. `memoriesApi.getEntities()`<br>2. `memoriesApi.getRelations()`<br>3. `memoriesApi.getGraph()` | 1. 查看自身对话生成的记忆网络<br>2. 手动添加/编辑/删除实体与关系 | `GET /api/v1/memories/entities` (`get_current_user`)<br>`POST /api/v1/memories/entities` (`get_current_user`)<br>`PUT /api/v1/memories/entities/{id}` (`get_current_user`)<br>`DELETE /api/v1/memories/entities/{id}` (`get_current_user`)<br>*(函数内自动强制 `user_id == current_user.id`)* | **一致**<br>严格按当前登录用户 ID 进行物理数据隔离，无法读取或污染他人记忆。 |

---

### 1.3 会话、执行与外部嵌入页面（Chat / Run / Embed / Auth Pages）

| 页面与路由路径 | 页面初始化 API 调用及凭证机制 | UI 关键操作控件与前端权限判断 | 触发后端 API 及鉴权依赖 | 跨层一致性与漏洞判定 |
| :--- | :--- | :--- | :--- | :--- |
| **`/chat/[id]`**<br>(独立聊天对话页) | 1. `agentsApi.getPublicAgent(id)`<br>2. `agentsApi.getMyConversations(agentId)` (登录用户) | 1. 发送聊天消息 (文本/图片/文档)<br>2. 切换历史会话列表<br>3. 重新生成/分支切换/停止生成<br>4. 变量表单输入与外部提问响应 | `GET /api/v1/agents/{id}/public` (`get_current_user_optional`)<br>`POST /api/v1/agents/{id}/chat` (`get_current_user_or_api_key`)<br>`POST /api/v1/agents/{id}/chat/stream` (`get_current_user_or_api_key`)<br>`POST /api/v1/agents/{id}/chat/runs` (`get_current_user_or_api_key`)<br>`POST /api/v1/agents/{id}/chat/runs/{run_id}/stop`<br>`POST /api/v1/agents/{id}/chat/runs/{run_id}/inputs` | **一致**<br>支持匿名公开访问（当 Agent 为 public 时）与登录访问；私有 Agent 自动拒绝无权用户；执行端点支持 API Key。 |
| **`/run/[id]`**<br>(工作流/Agent 独立运行) | 1. `workflowsApi.getWorkflow(id)` 或 `agentsApi.getAgent(id)` | 1. 表单化输入运行参数<br>2. 启动工作流/Agent 运行任务<br>3. 实时 SSE 事件流跟踪与暂停节点审批响应 | `POST /api/v1/workflows/{id}/run` (`workflow:run`)<br>`GET /api/v1/workflows/runs/{run_id}/stream` (`get_current_user_optional`)<br>`POST /api/v1/workflows/{id}/runs/{run_id}/pause-requests/{req_id}/submit` (`workflow:run`) | **一致**<br>运行与暂停审批端点均受 `workflow:run` 权限与可见性双重保护。 |
| **`/embed/agent/[id]`**<br>(iframe 嵌入聊天) | 1. `embedApi.getAgentInfo(id)` (凭 token 查询) | 1. iframe 内部与父窗口通过 postMessage 通信<br>2. 发送聊天消息、上传临时文件<br>3. 获取历史消息列表 | `GET /api/v1/embed/agents/{id}/info` (`get_embed_auth`)<br>`POST /api/v1/embed/agents/{id}/chat/stream` (`get_embed_auth`)<br>`POST /api/v1/embed/agents/{id}/chat/runs` (`get_embed_auth`)<br>`POST /api/v1/embed/agents/{id}/upload/file` (`get_embed_auth`)<br>`GET /api/v1/embed/agents/{id}/conversations/{cId}/messages` (`get_embed_auth`) | **一致**<br>`get_embed_auth` 依赖专用的 API Key (`clou_*`) 鉴权，且严格校验 Key 是否绑定了当前 Agent ID。 |
| **`/embed/workflow/[id]`**<br>(iframe 嵌入工作流) | 1. `embedApi.getWorkflowInfo(id)` (凭 token 查询) | 1. 运行输入表单填写<br>2. 提交运行与实时流式接收结果 | `GET /api/v1/embed/workflows/{id}/info` (`get_embed_auth`)<br>`POST /api/v1/embed/workflows/{id}/run` (`get_embed_auth`)<br>`GET /api/v1/embed/workflows/runs/{run_id}/stream` (`get_embed_auth`) | **一致**<br>严格校验 Embed Key 是否绑定了当前 Workflow ID。 |
| **`/login`, `/register`, `/verify`, `/forgot-password`, `/reset-password`, `/totp-setup`, `/sso-callback`** | 1. `loginApi.getCaptcha()`<br>2. `ssoApi.getPublicProviders()`<br>3. `siteSettingsApi.getPublic()` | 1. 验证码点击完成<br>2. 提交账号密码登录/注册<br>3. TOTP 两步验证二次校验<br>4. 邮箱验证链接核销<br>5. SSO 授权登录与重定向 | `GET /api/v1/captcha` (公开)<br>`POST /api/v1/captcha/click` (公开)<br>`POST /api/v1/login/access-token` (公开)<br>`POST /api/v1/login/verify-totp` (公开)<br>`POST /api/v1/register` (公开)<br>`POST /api/v1/send-verification` (公开)<br>`GET /api/v1/verify` (公开)<br>`GET /api/v1/sso/providers` (公开)<br>`GET /api/v1/sso/login/{name}` (公开)<br>`GET /api/v1/sso/callback/{name}` (公开) | **一致**<br>所有认证流程端点按契约完全公开，无意外的权限拦截。 |

---

## 二、 详尽漏洞分析与架构风险深度剖析

### 2.1 [CRITICAL] 全局工作流模板库越权发布与删除（无租户隔离、无权限拦截）
- **涉及文件**: `backend/app/api/v1/workflow_versions.py`
  - `POST /api/v1/workflow-templates` (`create_template`, L509-547)
  - `DELETE /api/v1/workflow-templates/{template_id}` (`delete_template`, L597-628)
- **漏洞根因详析**:
  后端路由仅仅使用了 `current_user: Annotated[User, Depends(get_current_user)]`。只要用户持有任何有效的登录 Token（包括团队内权限最低的 `Viewer` 角色），就可以向全系统公开发布工作流模板。在 `delete_template` 中，仅做了 `template.author_id != str(current_user.id)` 的弱校验，缺少管理员强制删除能力和审核流。
- **真实攻击场景**:
  恶意租户注册普通账号后，调用 `POST /api/v1/workflow-templates` 发布含有恶意提示词、诱导钓鱼节点或死循环脚本的模板。该模板会立刻出现在所有租户的“推荐/公共模板列表”中，造成跨租户供应链投毒。

### 2.2 [HIGH] 资产包导入（Package Import）越权绕过团队角色权限限制
- **涉及文件**: `backend/app/api/v1/endpoints/packages.py:85-180` 与 `backend/app/services/clouisle_package.py`
- **漏洞根因详析**:
  平台端 `POST /api/v1/packages/import/preview` 和 `POST /api/v1/packages/import/{session_id}/install` 仅校验了用户是否属于目标 `team_id`，**未校验该用户在目标团队是否拥有 `agent:create`、`workflow:create` 或 `kb:create` 权限**。
- **真实攻击场景**:
  某用户在 Team A 中被管理员设置为只读 `Viewer` 角色（前端 UI 隐藏了“创建智能体”和“创建知识库”按钮）。该用户直接构造 HTTP 请求向 `POST /api/v1/packages/import/preview` 上传包含恶意 Agent 和 KB 数据的 `.clouisle` 压缩包并执行 `install`，后端成功在 Team A 下创建出全新的 Agent 和知识库，完全击穿前端权限防护。

### 2.3 [HIGH] 核心资源（Agent / Workflow / Tool）写/改接口缺失全局声明式权限码
- **涉及端点**:
  - `POST /api/v1/agents` (`create_agent`)
  - `PUT /api/v1/agents/{id}` (`update_agent`)
  - `POST /api/v1/workflows` (`create_workflow`)
  - `PUT /api/v1/workflows/{id}` (`update_workflow`)
  - `POST /api/v1/tools` (`create_tool`)
  - `PUT /api/v1/tools/{id}` (`update_tool`)
  - `DELETE /api/v1/tools/{id}` (`delete_tool`)
- **漏洞根因详析**:
  `SystemPermissions` 和系统初始化脚本中为 Admin 和 Member 赋予了明确的 `agent:create`, `agent:update`, `workflow:create`, `workflow:update`, `tool:create`, `tool:update` 权限码。然而在上述 FastAPI 路由定义中，**完全没有声明 `PermissionChecker` 依赖项**，仅依靠函数体内的所有者校验。
- **业务影响**:
  若超级管理员在后台角色管理中自定义了一个“只读协作者”角色，或者取消了某用户的 `agent:update` 权限，该用户在前端虽然可能看不到编辑按钮，但通过脚本直接发送 `PUT /api/v1/agents/{id}` 依然能够成功篡改智能体配置。

### 2.4 [HIGH] 通知删除端点死代码与越权冲突
- **涉及文件**: `backend/app/api/v1/endpoints/notifications.py:784-829`
- **漏洞根因详析**:
  系统定义了权限码 `admin:notification:delete` 并分配给内置 `Admin` 角色。但在 `DELETE /api/v1/admin/notifications/{notification_id}` 端点上：
  1. 未声明 `PermissionChecker("admin:notification:delete")`。
  2. 函数体内硬编码：若 `scope == GLOBAL`，要求 `current_user.is_superuser`；若 `scope == TEAM`，要求 `check_team_admin_permission`。
- **业务影响**:
  拥有 `admin:notification:delete` 权限的普通 Admin 无法删除全局通知；而普通团队管理员（没有任何系统全局 Admin 角色）却可以通过管理后台 API 路径删除自己团队的通知，产生了权限语义倒置。

### 2.5 [MEDIUM] 5 处本地私有 `check_team_access` 逻辑分歧与维护隐患
- **涉及文件**:
  1. `backend/app/api/team_access.py` (官方标准实现)
  2. `backend/app/api/v1/endpoints/conversations.py:64`
  3. `backend/app/api/v1/admin/endpoints/conversations.py:63`
  4. `backend/app/api/v1/endpoints/knowledge_bases.py:301`
  5. `backend/app/services/skill.py:28`
- **隐患分析**:
  各文件自行维护 `check_team_access`，导致部分文件未检查 `Team.is_deleted`（软删除状态），部分文件未支持 `require_admin` 参数，在抛出异常时有的返回 400，有的返回 403，有的返回 404。一旦安全规范演进，极易出现漏改。

---

## 三、 结构化修复队列与整改实施方案

### 第一阶段（P0 级：紧急封堵越权漏洞，需优先执行）

#### 任务 1：加固工作流模板库 (`workflow_versions.py`)
- **目标**: 阻断任意普通用户发布/篡改全局模板。
- **实施步骤**:
  1. 在 `POST /api/v1/workflow-templates` 增加 `deps.PermissionChecker("workflow:publish")` 或限制仅超级管理员/系统指定角色可发布全局模板。
  2. 在 `DELETE /api/v1/workflow-templates/{template_id}` 增加超级管理员特权分支，并对普通用户执行严格校验。

#### 任务 2：加固 Package 导入安装校验 (`packages.py`)
- **目标**: 防止只读用户通过导入资产包绕过团队权限创建资源。
- **实施步骤**:
  1. 在 `ClouislePackageService.preview` 与 `install` 中，调用 `deps.check_scoped_permission(user, f"{resource_type}:create", "team", team_id)`。
  2. 确保在目标团队中无创建权限的用户在解包时直接返回 403 `PERMISSION_DENIED`。

---

### 第二阶段（P1 级：权限码与声明式依赖对齐）

#### 任务 3：补齐平台核心写接口的 `PermissionChecker`
- **目标**: 使后台角色权限管理对平台写操作真实生效。
- **实施步骤**:
  1. `backend/app/api/v1/endpoints/agents.py`:
     - `POST ""` 增加 `current_user: User = Depends(deps.PermissionChecker(SystemPermissions.AGENT_CREATE))`
     - `PUT "/{agent_id}"` 增加 `current_user: User = Depends(deps.PermissionChecker(SystemPermissions.AGENT_UPDATE))`
     - `POST "/{agent_id}/duplicate"` 增加 `current_user: User = Depends(deps.PermissionChecker(SystemPermissions.AGENT_CREATE))`
  2. `backend/app/api/v1/endpoints/workflows.py`:
     - `POST ""` 增加 `PermissionChecker(SystemPermissions.WORKFLOW_CREATE)`
     - `PUT "/{workflow_id}"` 增加 `PermissionChecker(SystemPermissions.WORKFLOW_UPDATE)`
     - `POST "/{workflow_id}/duplicate"` 增加 `PermissionChecker(SystemPermissions.WORKFLOW_CREATE)`
  3. `backend/app/api/v1/endpoints/tools.py`:
     - `POST ""` 增加 `PermissionChecker(SystemPermissions.TOOL_CREATE)`
     - `PUT "/{tool_id}"` 增加 `PermissionChecker(SystemPermissions.TOOL_UPDATE)`
     - `DELETE "/{tool_id}"` 增加 `PermissionChecker(SystemPermissions.TOOL_DELETE)`

#### 任务 4：统一通知删除鉴权逻辑
- **目标**: 激活死权限码 `admin:notification:delete`。
- **实施步骤**:
  1. `backend/app/api/v1/endpoints/notifications.py:784`:
     - 给 `admin_delete_notification` 挂载 `Depends(deps.PermissionChecker(SystemPermissions.ADMIN_NOTIFICATION_DELETE))`。
     - 允许持有该权限的用户删除全局及团队通知。

---

### 第三阶段（P2 级：架构收敛与重构治理）

#### 任务 5：消除本地重复的 `check_team_access`
- **实施步骤**:
  1. 全局搜索并移除 `conversations.py`、`knowledge_bases.py`、`skill.py`、`notifications.py` 中的私有 `check_team_access` / `check_team_admin_permission`。
  2. 统一引入 `app.api.team_access.check_team_access`。

#### 任务 6：规范管理端知识库路由与工作流指标路由
- **实施步骤**:
  1. 为管理端知识库单独封装 Router，挂载 `admin:knowledge-base:*` 权限码。
  2. 将 `/api/v1/workflows/metrics/*` 移动至 `/api/v1/admin/observability/workflows/metrics` 或 `/api/v1/admin/workflows/metrics`，消除前后台路由前缀混乱。

#### 任务 7：前端管理路由 Guard Fail-Closed 加固
- **实施步骤**:
  1. 在 `frontend/lib/route-permissions.ts` 的 `canAccessRoute` 中，针对所有以 `/site-settings`、`/users`、`/roles`、`/permissions`、`/audit-logs` 开头的路径，若未在映射表中明确配置，默认拒绝访问（Fail-Closed）。
