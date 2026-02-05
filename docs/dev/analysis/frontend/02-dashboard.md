# 管理后台页面

路由分组: `(dashboard)`
布局: 侧边栏导航

## /dashboard - 仪表盘首页

**文件位置**: `frontend/app/(dashboard)/dashboard/page.tsx`

**页面作用**: 管理后台首页，展示系统统计数据和图表

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `dashboardApi.getStats()` | GET `/dashboard/stats` | 获取整体统计 |
| `dashboardApi.getTrends()` | GET `/dashboard/stats/trends` | 获取趋势数据 |
| `dashboardApi.getTopAgents()` | GET `/dashboard/stats/agents/top` | 获取热门 Agent |
| `dashboardApi.getTeamTokenUsage()` | GET `/dashboard/stats/teams/token-usage` | 获取团队 Token 使用 |
| `dashboardApi.getWorkflowSummary()` | GET `/dashboard/stats/workflows/summary` | 获取工作流统计 |
| `dashboardApi.getModelDistribution()` | GET `/dashboard/stats/models/distribution` | 获取模型使用分布 |

**主要组件**:
- 统计卡片（用户数、团队数、Agent 数等）
- 趋势图表（用户增长、对话量等）
- 热门 Agent 排行
- Token 使用排行

---

## /users - 用户管理

**文件位置**: `frontend/app/(dashboard)/users/page.tsx`

**页面作用**: 用户列表和管理

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `usersApi.getUsers()` | GET `/users` | 获取用户列表 |
| `usersApi.getStats()` | GET `/users/stats` | 获取用户统计 |
| `usersApi.createUser()` | POST `/users` | 创建用户 |
| `usersApi.updateUser()` | PUT `/users/{id}` | 更新用户 |
| `usersApi.deleteUser()` | DELETE `/users/{id}` | 删除用户 |
| `usersApi.activateUser()` | POST `/users/{id}/activate` | 激活用户 |
| `usersApi.deactivateUser()` | POST `/users/{id}/deactivate` | 停用用户 |
| `usersApi.sendEmail()` | POST `/users/send-email` | 发送邮件 |

**主要功能**:
- 用户列表（分页、搜索、筛选）
- 创建/编辑用户对话框
- 批量操作（激活、停用、发送邮件）
- 用户详情查看

---

## /roles - 角色管理

**文件位置**: `frontend/app/(dashboard)/roles/page.tsx`

**页面作用**: 角色和权限管理

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `rolesApi.getRoles()` | GET `/roles` | 获取角色列表 |
| `rolesApi.createRole()` | POST `/roles` | 创建角色 |
| `rolesApi.updateRole()` | PUT `/roles/{id}` | 更新角色 |
| `rolesApi.updateRolePermissions()` | PUT `/roles/{id}/permissions` | 更新角色权限 |
| `rolesApi.deleteRole()` | DELETE `/roles/{id}` | 删除角色 |

**主要功能**:
- 角色列表
- 创建/编辑角色
- 权限分配界面

---

## /permissions - 权限管理

**文件位置**: `frontend/app/(dashboard)/permissions/page.tsx`

**页面作用**: 权限项管理

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `permissionsApi.getPermissions()` | GET `/permissions` | 获取权限列表 |
| `permissionsApi.createPermission()` | POST `/permissions` | 创建权限 |
| `permissionsApi.updatePermission()` | PUT `/permissions/{id}` | 更新权限 |
| `permissionsApi.deletePermission()` | DELETE `/permissions/{id}` | 删除权限 |

---

## /teams - 团队管理

**文件位置**: `frontend/app/(dashboard)/teams/page.tsx`

**页面作用**: 团队列表和成员管理

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `teamsApi.getTeams()` | GET `/teams` | 获取团队列表 |
| `teamsApi.getTeam()` | GET `/teams/{id}` | 获取团队详情 |
| `teamsApi.createTeam()` | POST `/teams` | 创建团队 |
| `teamsApi.updateTeam()` | PUT `/teams/{id}` | 更新团队 |
| `teamsApi.deleteTeam()` | DELETE `/teams/{id}` | 删除团队 |
| `teamsApi.addMember()` | POST `/teams/{id}/members` | 添加成员 |
| `teamsApi.updateMember()` | PUT `/teams/{id}/members/{userId}` | 更新成员角色 |
| `teamsApi.removeMember()` | DELETE `/teams/{id}/members/{userId}` | 移除成员 |
| `teamsApi.transferOwnership()` | POST `/teams/{id}/transfer-ownership` | 转让所有权 |

**主要功能**:
- 团队列表
- 团队详情和成员管理
- 成员角色调整
- 所有权转让

---

## /models - 模型管理

**文件位置**: `frontend/app/(dashboard)/models/page.tsx`

**页面作用**: LLM 模型配置和团队授权

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `modelsApi.getModels()` | GET `/models` | 获取模型列表 |
| `modelsApi.getProviders()` | GET `/models/providers` | 获取提供商列表 |
| `modelsApi.getModelTypes()` | GET `/models/types` | 获取模型类型 |
| `modelsApi.createModel()` | POST `/models` | 创建模型 |
| `modelsApi.updateModel()` | PUT `/models/{id}` | 更新模型 |
| `modelsApi.deleteModel()` | DELETE `/models/{id}` | 删除模型 |
| `modelsApi.testConnection()` | POST `/models/{id}/test` | 测试连接 |
| `modelsApi.setDefault()` | POST `/models/{id}/set-default` | 设为默认 |
| `teamModelsApi.getTeamModels()` | GET `/teams/{id}/models` | 获取团队模型 |
| `teamModelsApi.addTeamModel()` | POST `/teams/{id}/models` | 授权模型 |
| `teamModelsApi.removeTeamModel()` | DELETE `/teams/{id}/models/{modelId}` | 取消授权 |

**主要功能**:
- 模型列表和配置
- 连接测试
- 团队模型授权管理

---

## /knowledge-bases - 知识库列表

**文件位置**: `frontend/app/(dashboard)/knowledge-bases/page.tsx`

**页面作用**: 知识库管理概览

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `knowledgeBasesApi.getKnowledgeBases()` | GET `/knowledge-bases` | 获取知识库列表 |
| `knowledgeBasesApi.createKnowledgeBase()` | POST `/knowledge-bases` | 创建知识库 |
| `knowledgeBasesApi.updateKnowledgeBase()` | PUT `/knowledge-bases/{id}` | 更新知识库 |
| `knowledgeBasesApi.deleteKnowledgeBase()` | DELETE `/knowledge-bases/{id}` | 删除知识库 |

---

## /knowledge-bases/[id] - 知识库详情

**文件位置**: `frontend/app/(dashboard)/knowledge-bases/[id]/page.tsx`

**页面作用**: 知识库文档管理

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `knowledgeBasesApi.getKnowledgeBase()` | GET `/knowledge-bases/{id}` | 获取知识库详情 |
| `knowledgeBasesApi.getDocuments()` | GET `/knowledge-bases/{id}/documents` | 获取文档列表 |
| `knowledgeBasesApi.uploadDocument()` | POST `/knowledge-bases/{id}/documents` | 上传文档 |
| `knowledgeBasesApi.importUrl()` | POST `/knowledge-bases/{id}/documents/import-url` | URL 导入 |
| `knowledgeBasesApi.deleteDocument()` | DELETE `/knowledge-bases/{id}/documents/{docId}` | 删除文档 |
| `knowledgeBasesApi.processDocument()` | POST `/knowledge-bases/{id}/documents/{docId}/process` | 处理文档 |
| `knowledgeBasesApi.getStats()` | GET `/knowledge-bases/{id}/stats` | 获取统计 |

---

## /knowledge-bases/[id]/search - 知识库搜索测试

**文件位置**: `frontend/app/(dashboard)/knowledge-bases/[id]/search/page.tsx`

**页面作用**: 测试知识库搜索功能

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `knowledgeBasesApi.search()` | POST `/knowledge-bases/{id}/search` | 搜索知识库 |

---

## /knowledge-bases/[id]/documents/[docId] - 文档详情

**文件位置**: `frontend/app/(dashboard)/knowledge-bases/[id]/documents/[docId]/page.tsx`

**页面作用**: 文档分块管理

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `knowledgeBasesApi.getDocument()` | GET `/knowledge-bases/{kbId}/documents/{docId}` | 获取文档 |
| `knowledgeBasesApi.getDocumentChunks()` | GET `/knowledge-bases/{kbId}/documents/{docId}/chunks` | 获取分块 |
| `knowledgeBasesApi.updateChunk()` | PUT `/knowledge-bases/{kbId}/documents/{docId}/chunks/{chunkId}` | 更新分块 |
| `knowledgeBasesApi.deleteChunk()` | DELETE `/knowledge-bases/{kbId}/documents/{docId}/chunks/{chunkId}` | 删除分块 |
| `knowledgeBasesApi.createChunk()` | POST `/knowledge-bases/{kbId}/documents/{docId}/chunks` | 创建分块 |
| `knowledgeBasesApi.rechunkDocument()` | POST `/knowledge-bases/{kbId}/documents/{docId}/rechunk` | 重新分块 |

---

## /knowledge-bases/[id]/documents/preview - 文档预览

**文件位置**: `frontend/app/(dashboard)/knowledge-bases/[id]/documents/preview/page.tsx`

**页面作用**: 预览文档分块结果

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `knowledgeBasesApi.previewChunks()` | POST `/knowledge-bases/{id}/documents/preview-chunks` | 预览分块 |
| `knowledgeBasesApi.processDocumentWithChunks()` | POST `/knowledge-bases/{id}/documents/{docId}/process` | 处理文档 |

---

## /tools - 工具管理

**文件位置**: `frontend/app/(dashboard)/tools/page.tsx`

**页面作用**: 工具配置和管理

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `toolsApi.list()` | GET `/tools` | 获取工具列表 |
| `toolsApi.create()` | POST `/tools` | 创建工具 |
| `toolsApi.update()` | PUT `/tools/{id}` | 更新工具 |
| `toolsApi.delete()` | DELETE `/tools/{id}` | 删除工具 |
| `toolsApi.toggle()` | PUT `/tools/{id}` | 切换启用状态 |
| `toolsApi.duplicate()` | POST `/tools/{id}/duplicate` | 复制工具 |
| `toolsApi.test()` | POST `/tools/execute` | 测试工具 |
| `toolsApi.shareTool()` | POST `/tools/shares` | 共享工具 |
| `toolsApi.listToolShares()` | GET `/tools/shares` | 获取共享列表 |
| `toolsApi.unshareTool()` | DELETE `/tools/shares/{id}` | 取消共享 |

---

## /tools/code - 代码工具测试

**文件位置**: `frontend/app/(dashboard)/tools/code/page.tsx`

**页面作用**: 代码工具沙箱测试

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `toolsApi.executeCode()` | POST `/tools/code/execute` | 执行代码 |

---

## /api-keys - API Key 管理

**文件位置**: `frontend/app/(dashboard)/api-keys/page.tsx`

**页面作用**: API Key 管理

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `apiKeysApi.getAPIKeys()` | GET `/api-keys` | 获取 API Key 列表 |
| `apiKeysApi.getStats()` | GET `/api-keys/stats` | 获取统计 |
| `apiKeysApi.createAPIKey()` | POST `/api-keys` | 创建 API Key |
| `apiKeysApi.updateAPIKey()` | PUT `/api-keys/{id}` | 更新 API Key |
| `apiKeysApi.deleteAPIKey()` | DELETE `/api-keys/{id}` | 删除 API Key |
| `apiKeysApi.activateAPIKey()` | POST `/api-keys/{id}/activate` | 激活 |
| `apiKeysApi.deactivateAPIKey()` | POST `/api-keys/{id}/deactivate` | 停用 |

---

## /activities - 活动日志

**文件位置**: `frontend/app/(dashboard)/activities/page.tsx`

**页面作用**: 监控对话和工作流运行

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `conversationsApi.listAll()` | GET `/agents/conversations/all` | 获取所有对话 |
| `conversationsApi.getStats()` | GET `/agents/conversations/stats` | 获取对话统计 |
| `conversationsApi.getDetail()` | GET `/agents/conversations/{id}` | 获取对话详情 |
| `conversationsApi.delete()` | DELETE `/agents/conversations/{id}` | 删除对话 |
| `conversationsApi.batchDelete()` | POST `/agents/conversations/batch-delete` | 批量删除 |
| `workflowsApi.getAllWorkflowRuns()` | GET `/workflows/runs` | 获取所有运行 |
| `workflowsApi.getWorkflowRunStats()` | GET `/workflows/runs/stats` | 获取运行统计 |
| `workflowsApi.getWorkflowRun()` | GET `/workflows/runs/{id}` | 获取运行详情 |
| `workflowsApi.getRunNodeExecutions()` | GET `/workflows/runs/{id}/nodes` | 获取节点执行 |
| `workflowsApi.deleteWorkflowRun()` | DELETE `/workflows/runs/{id}` | 删除运行 |

---

## /audit-logs - 审计日志

**文件位置**: `frontend/app/(dashboard)/audit-logs/page.tsx`

**页面作用**: 查看和导出审计日志

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `auditLogsApi.list()` | GET `/audit-logs` | 获取审计日志列表 |
| `auditLogsApi.get()` | GET `/audit-logs/{id}` | 获取日志详情 |
| `auditLogsApi.getStats()` | GET `/audit-logs/stats` | 获取统计 |
| `auditLogsApi.getRetentionStats()` | GET `/audit-logs/stats/retention` | 获取保留统计 |
| `auditLogsApi.triggerArchive()` | POST `/audit-logs/archive` | 触发归档 |
| `auditLogsApi.export()` | GET `/audit-logs/export` | 导出日志 |

---

## /notifications - 通知管理（管理员）

**文件位置**: `frontend/app/(dashboard)/notifications/page.tsx`

**页面作用**: 管理员通知管理

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `notificationsApi.adminList()` | GET `/notifications/admin` | 获取所有通知 |
| `notificationsApi.adminCreate()` | POST `/notifications/admin` | 创建通知 |
| `notificationsApi.adminDelete()` | DELETE `/notifications/admin/{id}` | 删除通知 |

---

## /site-settings - 站点设置（通用）

**文件位置**: `frontend/app/(dashboard)/site-settings/page.tsx`

**页面作用**: 站点基本设置

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `siteSettingsApi.getGeneral()` | GET `/site-settings?category=general` | 获取通用设置 |
| `siteSettingsApi.updateGeneral()` | PUT `/site-settings` | 更新通用设置 |

---

## /site-settings/security - 安全设置

**文件位置**: `frontend/app/(dashboard)/site-settings/security/page.tsx`

**页面作用**: 安全相关设置

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `siteSettingsApi.getSecurity()` | GET `/site-settings?category=security` | 获取安全设置 |
| `siteSettingsApi.updateSecurity()` | PUT `/site-settings` | 更新安全设置 |

---

## /site-settings/notifications - 通知渠道设置

**文件位置**: `frontend/app/(dashboard)/site-settings/notifications/page.tsx`

**页面作用**: 配置通知渠道

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `siteSettingsApi.getEmail()` | GET `/site-settings?category=email` | 获取邮件设置 |
| `siteSettingsApi.updateEmail()` | PUT `/site-settings` | 更新邮件设置 |
| `siteSettingsApi.sendTestEmail()` | POST `/site-settings/test-email` | 测试邮件 |
| `siteSettingsApi.getDingTalk()` | GET `/site-settings?category=dingtalk` | 获取钉钉设置 |
| `siteSettingsApi.updateDingTalk()` | PUT `/site-settings` | 更新钉钉设置 |
| `siteSettingsApi.sendTestDingTalk()` | POST `/site-settings/test-dingtalk` | 测试钉钉 |
| `siteSettingsApi.getWeChat()` | GET `/site-settings?category=wechat` | 获取微信设置 |
| `siteSettingsApi.updateWeChat()` | PUT `/site-settings` | 更新微信设置 |
| `siteSettingsApi.sendTestWeChat()` | POST `/site-settings/test-wechat` | 测试微信 |
| `siteSettingsApi.getFeishu()` | GET `/site-settings?category=feishu` | 获取飞书设置 |
| `siteSettingsApi.updateFeishu()` | PUT `/site-settings` | 更新飞书设置 |
| `siteSettingsApi.sendTestFeishu()` | POST `/site-settings/test-feishu` | 测试飞书 |
| `siteSettingsApi.getWebhook()` | GET `/site-settings?category=webhook` | 获取 Webhook 设置 |
| `siteSettingsApi.updateWebhook()` | PUT `/site-settings` | 更新 Webhook 设置 |
| `siteSettingsApi.sendTestWebhook()` | POST `/site-settings/test-webhook` | 测试 Webhook |
| `siteSettingsApi.getSlack()` | GET `/site-settings?category=slack` | 获取 Slack 设置 |
| `siteSettingsApi.updateSlack()` | PUT `/site-settings` | 更新 Slack 设置 |
| `siteSettingsApi.sendTestSlack()` | POST `/site-settings/test-slack` | 测试 Slack |

---

## /site-settings/storage - 存储设置

**文件位置**: `frontend/app/(dashboard)/site-settings/storage/page.tsx`

**页面作用**: 审计日志保留和归档设置

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `siteSettingsApi.getAll('storage')` | GET `/site-settings?category=storage` | 获取存储设置 |
| `siteSettingsApi.bulkUpdate()` | PUT `/site-settings` | 更新存储设置 |
| `siteSettingsApi.archiveAuditLogs()` | POST `/site-settings/archive-audit-logs` | 触发归档 |

---

## /site-settings/sso - SSO 设置

**文件位置**: `frontend/app/(dashboard)/site-settings/sso/page.tsx`

**页面作用**: SSO 提供商管理

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `ssoApi.listProviders()` | GET `/sso/admin/providers` | 获取提供商列表 |
| `ssoApi.createProvider()` | POST `/sso/admin/providers` | 创建提供商 |
| `ssoApi.updateProvider()` | PUT `/sso/admin/providers/{id}` | 更新提供商 |
| `ssoApi.deleteProvider()` | DELETE `/sso/admin/providers/{id}` | 删除提供商 |
| `ssoApi.testConnection()` | POST `/sso/admin/providers/{id}/test` | 测试连接 |

---

## /settings/account - 账户设置

**文件位置**: `frontend/app/(dashboard)/settings/account/page.tsx`

**页面作用**: 管理员账户管理

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `usersApi.getCurrentUser()` | GET `/users/me` | 获取当前用户 |
| `usersApi.changePassword()` | POST `/users/me/change-password` | 修改密码 |
| `usersApi.deleteAccount()` | DELETE `/users/me` | 删除账户 |
| `ssoApi.disconnectConnection()` | DELETE `/sso/connections/{id}` | 断开 SSO |

---

## /settings/profile - 个人资料

**文件位置**: `frontend/app/(dashboard)/settings/profile/page.tsx`

**页面作用**: 管理员个人资料编辑

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `usersApi.getCurrentUser()` | GET `/users/me` | 获取当前用户 |
| `usersApi.updateProfile()` | PUT `/users/me` | 更新个人资料 |

---

## /settings/api-keys - 个人 API Key

**文件位置**: `frontend/app/(dashboard)/settings/api-keys/page.tsx`

**页面作用**: 用户个人 API Key 管理

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `apiKeysApi.getAPIKeys()` | GET `/api-keys` | 获取 API Key 列表 |
| `apiKeysApi.createAPIKey()` | POST `/api-keys` | 创建 API Key |
| `apiKeysApi.updateAPIKey()` | PUT `/api-keys/{id}` | 更新 API Key |
| `apiKeysApi.deleteAPIKey()` | DELETE `/api-keys/{id}` | 删除 API Key |
