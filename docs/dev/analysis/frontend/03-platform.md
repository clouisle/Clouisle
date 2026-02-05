# 用户平台页面

路由分组: `(platform)`
布局: 顶部导航

## /app - 平台首页

**文件位置**: `frontend/app/(platform)/app/page.tsx`

**页面作用**: 用户平台首页，展示快速入口和统计

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `knowledgeBasesApi.getKnowledgeBases()` | GET `/knowledge-bases` | 获取知识库数量 |
| `teamModelsApi.getTeamModels()` | GET `/teams/{id}/models` | 获取团队模型 |
| `agentsApi.getAgents()` | GET `/agents` | 获取 Agent 列表 |
| `workflowsApi.getWorkflows()` | GET `/workflows` | 获取工作流列表 |
| `conversationsApi.getTrends()` | GET `/agents/conversations/trends` | 获取使用趋势 |

**主要功能**:
- 快速创建入口（Agent、工作流、知识库）
- 最近使用的 Agent
- 使用统计概览

---

## /app/apps - 应用列表

**文件位置**: `frontend/app/(platform)/app/apps/page.tsx`

**页面作用**: Agent 和工作流统一列表

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `agentsApi.getAgents()` | GET `/agents` | 获取 Agent 列表 |
| `workflowsApi.getWorkflows()` | GET `/workflows` | 获取工作流列表 |
| `agentsApi.deleteAgent()` | DELETE `/agents/{id}` | 删除 Agent |
| `workflowsApi.deleteWorkflow()` | DELETE `/workflows/{id}` | 删除工作流 |
| `agentsApi.duplicateAgent()` | POST `/agents/{id}/duplicate` | 复制 Agent |
| `workflowsApi.duplicateWorkflow()` | POST `/workflows/{id}/duplicate` | 复制工作流 |
| `agentsApi.publishAgent()` | POST `/agents/{id}/publish` | 发布 Agent |
| `agentsApi.unpublishAgent()` | POST `/agents/{id}/unpublish` | 取消发布 |
| `workflowsApi.publishWorkflow()` | POST `/workflows/{id}/publish` | 发布工作流 |
| `workflowsApi.unpublishWorkflow()` | POST `/workflows/{id}/unpublish` | 取消发布 |

**主要功能**:
- Agent 和工作流卡片列表
- 筛选（类型、状态、团队）
- 快速操作（编辑、复制、删除、发布）

---

## /app/apps/[id] - Agent 配置

**文件位置**: `frontend/app/(platform)/app/apps/[id]/page.tsx`

**页面作用**: Agent 详细配置

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `agentsApi.getAgent()` | GET `/agents/{id}` | 获取 Agent 详情 |
| `agentsApi.updateAgent()` | PUT `/agents/{id}` | 更新 Agent |
| `agentsApi.publishAgent()` | POST `/agents/{id}/publish` | 发布 |
| `agentsApi.unpublishAgent()` | POST `/agents/{id}/unpublish` | 取消发布 |
| `modelsApi.getAvailable()` | GET `/models/available` | 获取可用模型 |
| `knowledgeBasesApi.getKnowledgeBases()` | GET `/knowledge-bases` | 获取知识库列表 |
| `toolsApi.list()` | GET `/tools` | 获取工具列表 |
| `promptsApi.generate()` | POST `/prompt-generator/generate` | 生成提示词 |
| `promptsApi.optimize()` | POST `/prompt-generator/optimize` | 优化提示词 |

**主要功能**:
- 基本信息配置（名称、描述、图标）
- 模型选择和参数配置
- 系统提示词编辑（支持 AI 生成）
- 知识库关联
- 工具配置
- 变量定义
- 预览和测试

---

## /app/apps/[id]/api - Agent API 文档

**文件位置**: `frontend/app/(platform)/app/apps/[id]/api/page.tsx`

**页面作用**: 查看 Agent API 调用文档

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `agentsApi.getAgent()` | GET `/agents/{id}` | 获取 Agent 详情 |

**主要功能**:
- API 端点说明
- 请求/响应示例
- 代码示例（cURL、Python、JavaScript）

---

## /app/apps/[id]/logs - Agent 对话日志

**文件位置**: `frontend/app/(platform)/app/apps/[id]/logs/page.tsx`

**页面作用**: 查看 Agent 对话历史

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `agentsApi.getAgentConversations()` | GET `/agents/{id}/conversations` | 获取对话列表 |
| `agentsApi.getConversation()` | GET `/agents/conversations/{id}` | 获取对话详情 |
| `agentsApi.deleteConversation()` | DELETE `/agents/conversations/{id}` | 删除对话 |

**主要功能**:
- 对话列表（分页、搜索）
- 对话详情查看
- 消息内容展示

---

## /app/apps/[id]/monitor - Agent 监控

**文件位置**: `frontend/app/(platform)/app/apps/[id]/monitor/page.tsx`

**页面作用**: Agent 使用监控和统计

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `agentStatsApi.getStats()` | GET `/agents/{id}/stats` | 获取统计 |
| `agentStatsApi.getTrends()` | GET `/agents/{id}/stats/trends` | 获取趋势 |
| `agentStatsApi.getToolUsage()` | GET `/agents/{id}/stats/tools` | 获取工具使用 |
| `agentStatsApi.getRecentConversations()` | GET `/agents/{id}/conversations` | 获取最近对话 |

**主要功能**:
- 使用统计（对话数、消息数、Token 消耗）
- 趋势图表
- 工具使用分布
- 最近对话列表

---

## /app/apps/workflow/[id] - 工作流配置

**文件位置**: `frontend/app/(platform)/app/apps/workflow/[id]/page.tsx`

**页面作用**: 工作流可视化编辑

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `workflowsApi.getWorkflow()` | GET `/workflows/{id}` | 获取工作流详情 |
| `workflowsApi.updateWorkflow()` | PUT `/workflows/{id}` | 更新工作流 |
| `workflowsApi.publishWorkflow()` | POST `/workflows/{id}/publish` | 发布 |
| `workflowsApi.unpublishWorkflow()` | POST `/workflows/{id}/unpublish` | 取消发布 |
| `workflowsApi.runWorkflow()` | POST `/workflows/{id}/run` | 运行工作流 |
| `workflowsApi.debugWorkflow()` | POST `/workflows/{id}/debug` | 调试工作流 |

**主要功能**:
- 可视化节点编辑器
- 节点配置面板
- 变量管理
- 触发器配置
- 运行和调试

---

## /app/apps/workflow/[id]/api - 工作流 API 文档

**文件位置**: `frontend/app/(platform)/app/apps/workflow/[id]/api/page.tsx`

**页面作用**: 查看工作流 API 和 Webhook 信息

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `workflowsApi.getWorkflow()` | GET `/workflows/{id}` | 获取工作流详情 |

**主要功能**:
- API 端点说明
- Webhook URL
- 请求/响应示例

---

## /app/apps/workflow/[id]/logs - 工作流运行日志

**文件位置**: `frontend/app/(platform)/app/apps/workflow/[id]/logs/page.tsx`

**页面作用**: 查看工作流执行历史

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `workflowsApi.getWorkflowRuns()` | GET `/workflows/{id}/runs` | 获取运行列表 |
| `workflowsApi.getWorkflowRun()` | GET `/workflows/runs/{id}` | 获取运行详情 |
| `workflowsApi.getRunNodeExecutions()` | GET `/workflows/runs/{id}/nodes` | 获取节点执行 |
| `workflowsApi.deleteWorkflowRun()` | DELETE `/workflows/runs/{id}` | 删除运行 |
| `workflowsApi.streamWorkflowRun()` | GET `/workflows/runs/{id}/stream` | 流式获取事件 |

**主要功能**:
- 运行记录列表
- 运行详情和节点执行情况
- 实时运行状态（SSE）

---

## /app/apps/workflow/[id]/monitor - 工作流监控

**文件位置**: `frontend/app/(platform)/app/apps/workflow/[id]/monitor/page.tsx`

**页面作用**: 工作流执行监控

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `workflowsApi.getWorkflowStats()` | GET `/workflows/{id}/stats` | 获取统计 |
| `workflowsApi.getWorkflowTrends()` | GET `/workflows/{id}/stats/trends` | 获取趋势 |

**主要功能**:
- 执行统计（成功率、平均耗时）
- 趋势图表
- 错误分析

---

## /app/kb - 知识库列表

**文件位置**: `frontend/app/(platform)/app/kb/page.tsx`

**页面作用**: 用户知识库管理

**使用的 API**: 同 Dashboard 知识库列表

---

## /app/kb/[id] - 知识库详情

**文件位置**: `frontend/app/(platform)/app/kb/[id]/page.tsx`

**页面作用**: 知识库文档管理（用户视图）

**使用的 API**: 同 Dashboard 知识库详情

---

## /app/kb/[id]/search - 知识库搜索

**文件位置**: `frontend/app/(platform)/app/kb/[id]/search/page.tsx`

**页面作用**: 测试知识库搜索（用户视图）

**使用的 API**: 同 Dashboard 知识库搜索

---

## /app/kb/[id]/documents/[docId] - 文档详情

**文件位置**: `frontend/app/(platform)/app/kb/[id]/documents/[docId]/page.tsx`

**页面作用**: 文档分块管理（用户视图）

**使用的 API**: 同 Dashboard 文档详情

---

## /app/kb/[id]/documents/preview - 文档预览

**文件位置**: `frontend/app/(platform)/app/kb/[id]/documents/preview/page.tsx`

**页面作用**: 预览文档分块（用户视图）

**使用的 API**: 同 Dashboard 文档预览

---

## /app/models - 模型列表

**文件位置**: `frontend/app/(platform)/app/models/page.tsx`

**页面作用**: 查看团队可用模型

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `teamModelsApi.getTeamModels()` | GET `/teams/{id}/models` | 获取团队模型 |
| `teamModelsApi.getTeamModelsQuota()` | GET `/teams/{id}/models/quota` | 获取配额 |

**主要功能**:
- 可用模型列表
- 配额使用情况

---

## /app/tools - 工具列表

**文件位置**: `frontend/app/(platform)/app/tools/page.tsx`

**页面作用**: 工具管理（用户视图）

**使用的 API**: 同 Dashboard 工具管理

---

## /app/tools/code - 代码工具测试

**文件位置**: `frontend/app/(platform)/app/tools/code/page.tsx`

**页面作用**: 代码工具沙箱（用户视图）

**使用的 API**: 同 Dashboard 代码工具

---

## /app/notifications - 用户通知

**文件位置**: `frontend/app/(platform)/app/notifications/page.tsx`

**页面作用**: 用户通知中心

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `notificationsApi.list()` | GET `/notifications` | 获取通知列表 |
| `notificationsApi.unreadCount()` | GET `/notifications/unread-count` | 获取未读数 |
| `notificationsApi.markRead()` | POST `/notifications/read` | 标记已读 |

**主要功能**:
- 通知列表
- 未读标记
- 批量标记已读
