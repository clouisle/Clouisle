# 更新日志 (Changelog)

本文档记录项目的所有重要变更。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [Unreleased]

### 修复 (Fixed)

#### 知识库检索效果优化

- **相似度计算修正**：修正余弦相似度计算公式
  - 之前：`1 - (distance / 2)` - 导致分数偏高
  - 之后：`GREATEST(0, 1 - distance)` - 正确转换余弦距离为相似度
  - 参考：pgvector 余弦距离范围 `[0, 2]`，距离 0 = 完全相同，1 = 正交，2 = 相反

- **默认阈值调整**：将 `score_threshold` 默认值从 `0.5` 降低到 `0.3`
  - 后端 `AgentKnowledgeBase` 模型
  - 前端 `knowledge-base-selector.tsx` 和 `agent-orchestration-form.tsx`

#### 文本分块算法修复

- **分块大小限制生效**：修复 `chunk_size` 设置不生效的问题
  - 当分割片段超过目标大小时，现在会递归使用更细粒度的分隔符继续分割
  - 无法继续分割时，按字符数硬切分到目标长度
  - 修改文件：`backend/app/services/document_processor.py` 的 `_merge_splits` 方法

#### Streamdown 图片渲染水合错误

- **问题**：Markdown 中的图片会被 Streamdown 渲染为 `<div>` 包装器，当图片出现在段落内时导致 `<div>` 嵌套在 `<p>` 内，违反 HTML 规范引发 React hydration 错误
- **修复**：为 Streamdown 组件提供自定义 `p` 组件，检测 AST 节点和 React 子元素是否包含图片，若包含则用 `<div>` 替代 `<p>`
- **修改文件**：
  - `frontend/components/chat/message.tsx` - `TextWithCitations`
  - `frontend/components/chat/message-parts/text-content.tsx` - `TextContent`
  - `frontend/components/ai-elements/message.tsx` - `MessageResponse`
  - `frontend/components/ai-elements/reasoning.tsx` - `ReasoningContent`

#### 公开聊天页面布局修复

- **问题**：模型输出内容过长时会撑大整个页面高度，而不是在消息区域内滚动
- **修复**：
  - `frontend/app/(chat)/layout.tsx`：使用 `fixed inset-0` 定位替代 `h-screen`，完全脱离文档流
  - `frontend/app/(chat)/chat/[id]/page.tsx`：
    - 外层容器使用 `h-full` 继承父容器高度
    - 添加必要的 `min-h-0` 和 `overflow-hidden` 约束
    - Sidebar 添加 `shrink-0` 防止收缩

### 文档更新 (Documentation)

#### 知识库规范文档完善

更新 `docs/design/KNOWLEDGE_BASE_SPEC.md`：

- **搜索功能** (第 6 章)：完全重写
  - 三种搜索模式详细说明 (vector/fulltext/hybrid)
  - 相似度计算公式和距离-相似度对照表
  - 阈值建议 (0.0-0.6+ 不同场景)
  - RRF 混合搜索算法实现详解
  - jieba 全文搜索实现

- **文本分块** (5.3 节)：扩展
  - 分块参数表
  - 递归分割策略和分隔符优先级列表
  - 分块算法流程描述
  - 使用示例

---

### 新增 (Added)

#### 平台 Header 关于对话框

- 新增「关于」对话框，可从平台 Header 用户菜单访问
- 显示应用 Logo、版本号、版权信息
- 提供 GitHub、文档、更新日志快捷链接
- 设计风格参考 Dify

#### 常量文件统一管理

- 新增 `frontend/lib/constants.ts` 统一管理应用常量
- 包含：`APP_VERSION`、`APP_NAME`、`GITHUB_URL`、`DOCS_URL`、`CHANGELOG_URL`、`API_BASE_URL`
- 重构多个文件引用统一的 `API_BASE_URL`

#### 聊天历史管理优化 (#24)

##### 删除操作刷新机制

修复了多个页面在删除操作后使用本地状态过滤而非从服务器刷新数据的问题，确保删除后列表数据与服务器一致：

- **公开聊天页面** (`/frontend/app/(chat)/chat/[id]/page.tsx`)：
  - 修复新建对话后侧边栏历史不更新的问题
  - 将 `refreshConversations` 提取到 `useCallback` 中
  - 在 `onConversationChange` 回调中正确调用刷新函数

- **后台对话管理** (`/frontend/app/(dashboard)/conversations/_components/conversations-client.tsx`)：
  - 单条删除后调用 `fetchConversations(currentPage)` 刷新
  - 批量删除后同样调用服务器刷新

- **后台知识库文档分块** (`/frontend/app/(dashboard)/knowledge-bases/[id]/documents/[docId]/_components/document-detail-client.tsx`)：
  - 分块删除后调用 `loadChunks()` 从服务器获取最新数据

- **后台分块编辑器** (`/frontend/app/(dashboard)/knowledge-bases/[id]/_components/chunk-editor-dialog.tsx`)：
  - 分块删除后调用 `loadChunks()` 刷新

- **中台文档分块** (`/frontend/app/(platform)/app/kb/[id]/documents/[docId]/_components/document-detail-client.tsx`)：
  - 分块删除后调用 `loadChunks()` 刷新

- **中台应用日志** (`/frontend/app/(platform)/app/apps/[id]/logs/page.tsx`)：
  - 对话删除后调用 `fetchConversations(currentPage)` 刷新

### 修复 (Fixed)

#### Textarea 组件换行问题

- 修复 Agent 设置中「建议问题」输入框无法换行的问题
- **原因**：`Textarea` 组件使用了 `field-sizing-content` CSS 属性，该属性会覆盖 `rows` 属性的行为
- **修复** (`/frontend/components/ui/textarea.tsx`)：
  - 当传入 `rows` 属性时，不使用 `field-sizing-content`，让 textarea 按照指定行数显示
  - 未传入 `rows` 时，保持自动调整大小的行为

#### 建议问题按钮交互优化

- 为 Agent 预览面板和公开聊天页面的建议问题气泡添加 `cursor-pointer` 样式
- **修复文件**：
  - `/frontend/app/(platform)/app/apps/[id]/_components/agent-preview-panel.tsx`
  - `/frontend/app/(chat)/chat/[id]/page.tsx`

#### 嵌套按钮水合错误

- 修复用户设置 API 密钥页面的 React hydration 错误
- **原因**：`DropdownMenuTrigger` 内嵌套了 `Button` 组件，导致 HTML 按钮嵌套
- **修复** (`/frontend/app/(dashboard)/settings/api-keys/page.tsx`)：
  - 移除嵌套的 `Button`，将按钮样式直接应用到 `DropdownMenuTrigger`

---

### 新增 (Added)

#### API 密钥管理 - 完整实现 (#23)

##### Agent 绑定功能

- **API Key 与 Agent 多对多关联**：
  - 一个 API Key 可以绑定多个 Agent
  - 绑定后该 API Key 只能访问已绑定的 Agent
  - 不绑定任何 Agent 时可访问所有公开 Agent

- **后端实现**：
  - `api_key_agents` 关联表（多对多）
  - 创建/更新 API Key 时支持设置 `agent_ids`
  - Chat 端点增加 API Key 认证支持（`X-API-Key` header）
  - API Key 认证时校验 Agent 访问权限

- **前端实现**：
  - API Key 创建/编辑对话框新增 Agent 绑定选择器
  - API Key 列表显示已绑定的 Agent 数量

##### 后端 (Backend)

- **APIKey 模型** (`/backend/app/models/api_key.py`)：
  - `id`: UUID 主键
  - `name`: 密钥名称
  - `key_prefix`: 密钥前缀（12 字符），用于识别
  - `key_hash`: 密钥哈希值，使用密码哈希算法存储
  - `user`: 外键关联用户
  - `scopes`: JSON 字段，权限范围列表
  - `rate_limit`: 速率限制（每分钟请求数）
  - `is_active`: 启用状态
  - `expires_at`: 过期时间
  - `last_used_at`: 最后使用时间
  - `generate_key()`: 生成安全随机密钥
  - `verify_key()`: 验证密钥

- **API 密钥端点** (`/api/v1/api-keys/`)：
  - `GET /`: 获取密钥列表，支持 `user_id` 筛选
  - `GET /stats`: 获取统计信息（总数、激活、禁用）
  - `POST /`: 创建密钥，返回完整密钥（仅一次）
  - `GET /{id}`: 获取单个密钥详情
  - `PUT /{id}`: 更新密钥信息
  - `DELETE /{id}`: 删除密钥
  - `POST /{id}/activate`: 激活密钥
  - `POST /{id}/deactivate`: 禁用密钥

- **权限控制**：
  - 超级管理员可查看和管理所有密钥
  - 普通用户只能管理自己的密钥
  - 新增权限：`apikey:read`、`apikey:create`、`apikey:update`、`apikey:delete`

- **安全特性**：
  - 使用 `secrets.token_urlsafe(32)` 生成 43 字符安全密钥
  - 密钥使用密码哈希算法存储，原始值不保存
  - 完整密钥仅在创建时返回一次

##### 前端 (Frontend)

- **管理后台 API 密钥页面** (`/api-keys`)：
  - 密钥列表表格，支持批量选择
  - 搜索过滤（名称、前缀）
  - 状态筛选（全部/已启用/已禁用）
  - 用户筛选下拉框
  - 创建密钥对话框
  - 编辑密钥对话框
  - 删除确认对话框
  - 新建密钥展示对话框（一次性复制）
  - 激活/禁用操作
  - 分页支持

- **用户设置 API 密钥页面** (`/settings/api-keys`)：
  - 个人密钥列表
  - 创建/删除密钥
  - 密钥复制功能

- **UI 组件**：
  - `api-keys-client.tsx`: 管理后台主组件
  - `api-key-dialog.tsx`: 创建/编辑对话框
  - `delete-api-key-dialog.tsx`: 删除确认
  - `show-key-dialog.tsx`: 新密钥展示

- **API 客户端** (`/frontend/lib/api/api-keys.ts`)：
  - 完整的 TypeScript 类型定义
  - CRUD 操作方法
  - 用户筛选支持

##### 国际化

- 新增 `apiKeys` 命名空间翻译（中英文）
- 导航菜单翻译

##### 导航更新

- 管理后台侧边栏添加「API 密钥」入口
- 用户设置页面添加「API 密钥」入口

---

### 新增 (Added)

#### Agent API 访问页面

实现了 Agent 的 API 访问文档页面，方便开发者集成 Agent 能力：

- **页面路由**: `/app/apps/[id]/api`
- **功能特性**：
  - 显示 API 端点 URL 和认证方式
  - 请求/响应格式说明
  - 代码示例（cURL、Python、JavaScript）
  - Agent 变量定义展示（如有）
  - 未发布 Agent 警告提示
  - 多轮对话文档说明

- **UI 组件**：
  - Alert 组件新增 `warning` 变体

- **国际化**：
  - 新增 `apiAccess` 命名空间翻译（中英文）

---

### 新增 (Added)

#### 后台工具管理页面 (#27)

实现了后台管理端的工具管理功能：

- **页面路由**: `/tools`
- **工具类型支持**：
  - **HTTP API 工具**：配置 URL、方法、Headers、Body 模板
  - **MCP 服务器工具**：配置 stdio/sse 传输方式、命令、环境变量
  - **代码工具**：在线编辑器支持 JavaScript/Python

- **功能特性**：
  - 工具列表表格，支持搜索和类型筛选
  - 批量选择与批量删除
  - 创建工具对话框（按类型）
  - 编辑工具对话框
  - 删除确认对话框
  - 代码工具单独页面 `/tools/code`

- **UI 组件**：
  - `http-tool-dialog.tsx` - HTTP 工具创建/编辑
  - `mcp-tool-dialog.tsx` - MCP 工具创建/编辑
  - `tools-client.tsx` - 工具列表主组件
  - `delete-tool-dialog.tsx` - 删除确认

- **导航更新**：
  - 管理后台侧边栏添加「工具」入口

- **国际化**：
  - 扩展 `tools` 命名空间翻译（中英文）

---

### 新增 (Added)

#### Agent 监控页面 - 统计与可视化

实现了 Agent 编排页面中的监控（Monitor）功能，提供使用统计和性能指标的可视化展示。

##### 后端 (Backend)

- **Agent 统计 API** (`/backend/app/api/v1/endpoints/agent_stats.py`)：
  - `GET /agents/{agent_id}/stats` - 获取总体统计数据
    - 对话数、消息数（按角色分类）
    - Token 用量（prompt/completion）
    - 平均响应时间
    - 活跃用户数
    - 工具调用次数
  - `GET /agents/{agent_id}/stats/trends` - 获取趋势数据
    - 支持 24h/7d/30d 时间范围
    - 按小时/天粒度聚合
    - 返回对话数、消息数、Token、响应时间时序数据
  - `GET /agents/{agent_id}/stats/tool-usage` - 获取工具使用统计
    - 按工具名称聚合调用次数
    - 支持多种 tool_call 数据格式
  - `GET /agents/{agent_id}/stats/recent-conversations` - 获取最近对话列表

##### 前端 (Frontend)

- **Chart UI 组件** (`/frontend/components/ui/chart.tsx`)：
  - 基于 recharts 的 shadcn 风格封装
  - `ChartContainer` - 响应式图表容器
  - `ChartTooltip` / `ChartTooltipContent` - 自定义悬浮提示
  - `ChartLegend` / `ChartLegendContent` - 图例组件
  - 支持深色/浅色主题自适应

- **监控页面** (`/frontend/app/(platform)/app/apps/[id]/monitor/page.tsx`)：
  - 概览统计卡片：对话数、消息数、Token 用量、平均响应时间、活跃用户、工具调用
  - 对话趋势图（Area Chart）- 显示对话数和消息数变化
  - Token 用量趋势图 - 显示总 Token 消耗变化
  - 响应时间趋势图 - 显示平均响应时间变化
  - 工具使用分布图（Bar Chart）- 显示各工具调用次数
  - 最近对话列表 - 显示最新 5 条对话
  - 时间段筛选（24 小时 / 7 天 / 30 天）

- **API 客户端** (`/frontend/lib/api/agents.ts`)：
  - 新增 `agentStatsApi` 对象
  - 类型定义：`AgentStats`、`AgentTrends`、`AgentToolUsage`、`RecentConversationItem`

##### 图表主题适配

- **深色模式颜色**（`globals.css`）：
  - `--chart-1`: 青色 (对话数)
  - `--chart-2`: 绿色 (消息数)
  - `--chart-3`: 紫色 (Token)
  - `--chart-4`: 橙色 (响应时间)
  - `--chart-5`: 粉色 (工具使用)
- 图表配置使用 `theme` 对象分别定义 light/dark 颜色

##### 国际化

- 新增 `agents.monitor` 命名空间翻译（中英文）
  - 页面描述、时间段选项
  - 统计指标名称
  - 图表标题和描述
  - 图表数据标签

##### 依赖

- 新增 `recharts` 图表库

---

### 新增 (Added)

#### 知识库模块 - 动态 Embedding 维度支持

##### 多维度 Embedding 向量存储

实现了动态 embedding 维度支持，允许不同知识库使用不同维度的 embedding 模型：

- **KnowledgeBase 模型扩展**：
  - 新增 `embedding_dimension` 字段，记录知识库使用的向量维度
  - 首次处理文档时自动检测并锁定维度
  - 后续文档必须使用相同维度的模型

- **动态向量列管理**：
  - 支持多种维度：768 (BGE)、1024 (Cohere)、1536 (OpenAI ada)、3072 (OpenAI large)
  - 按需创建 embedding 列：`embedding_768`、`embedding_1024` 等
  - 每个维度独立的 HNSW 索引，优化搜索性能

- **pgvector 初始化优化** (`init_pgvector`):
  - 启动时预创建常用维度的列和索引
  - 运行时动态创建新维度列（`ensure_embedding_column`）

- **向量存储服务重构** (`vector_store.py`):
  - `ensure_embedding_column(dimension)`: 确保指定维度的列存在
  - `get_kb_embedding_dimension(kb_id)`: 获取知识库的向量维度
  - `set_kb_embedding_dimension(kb_id, dimension)`: 设置知识库维度
  - `DimensionMismatchError`: 维度不匹配异常

- **API 响应扩展**：
  - `KnowledgeBase` schema 新增 `embedding_dimension` 字段
  - `KnowledgeBaseStats` 新增 `embedding_dimension` 字段
  - 统计 API 返回维度信息

- **数据迁移脚本** (`backend/app/scripts/migrate_embeddings.py`):
  - 自动检测现有 embedding 列的维度
  - 迁移数据到新的维度列
  - 为现有知识库设置 `embedding_dimension`

##### 文档处理流程优化

- **维度自动检测**：
  - 首次处理文档时检测 embedding 模型输出的维度
  - 自动创建对应维度的数据库列
  - 将维度记录到知识库

- **维度一致性检查**：
  - 处理文档时验证 embedding 维度与知识库维度一致
  - 不一致时抛出 `DimensionMismatchError`，提示用户更换模型

##### 预览页面分块设置同步

- **设置变更清除预览**：
  - 修改分块设置（chunk_size、chunk_overlap、separator、clean_text）时自动清除已生成的预览
  - 强制用户重新预览后才能处理，确保分块结果与设置一致

### 修复 (Fixed)

#### Select 组件控制状态警告

- 修复 `KnowledgeBaseDialog` 中 Select 组件从 uncontrolled 变为 controlled 的警告
- 将 `teamId` 和 `embeddingModelId` 初始值从 `null` 改为空字符串 `''`

---

### 新增 (Added)

#### Chat 模块 - 通用聊天组件系统与 MCP 工具支持 (#22)

##### 前端 Chat 组件库

创建了一套完整的可复用 Chat 组件库，位于 `/frontend/components/chat/`：

- **Chat 主组件** (`chat.tsx`)：组合 Container + Input 的完整聊天界面
- **消息容器** (`chat-container.tsx`)：支持自动滚动、Streamdown 渲染
- **输入框** (`chat-input.tsx`)：OpenAI 风格设计，支持 IME 输入法、文件附件
- **消息组件** (`message.tsx`)：集成 ChainOfThought，支持多种消息类型
- **变量表单** (`variable-form.tsx`)：Agent 变量输入表单

##### 消息部件系统

位于 `/frontend/components/chat/message-parts/`：

- **文本内容** (`text-content.tsx`)：Markdown 渲染、流式光标、引用标记
- **推理内容** (`reasoning-content.tsx`)：思维链展示、可折叠
- **工具调用** (`tool-content.tsx`)：工具执行状态、输入/输出展示
- **文件内容** (`file-content.tsx`)：图片预览、文件信息展示
- **来源内容** (`source-content.tsx`)：RAG 来源聚合、分段弹窗

##### AI 元素组件库

位于 `/frontend/components/ai-elements/`：

- **ChainOfThought** (`chain-of-thought.tsx`)：聚合展示 RAG/推理/生成步骤，3秒自动折叠
- **Shimmer** (`shimmer.tsx`)：加载闪烁动画
- **Tool** (`tool.tsx`)：工具调用状态组件
- **Message** (`message.tsx`)：消息基础组件

##### useChat Hook

实现了完整的 Chat 状态管理 Hook (`/frontend/hooks/use-chat.ts`)：

- SSE 事件流解析
- TaskState 跟踪（RAG、生成状态）
- 流式中断支持（AbortController）
- 消息版本管理

##### 后端 SSE 流式响应

实现了完整的 Server-Sent Events 流式响应 (`/backend/app/api/v1/endpoints/chat.py`)：

| 事件类型 | 数据 | 说明 |
|----------|------|------|
| `message_start` | `{conversation_id, message_id}` | 消息开始 |
| `rag_start` | `{}` | RAG 检索开始 |
| `rag_context` | `{documents: [...]}` | RAG 检索结果 |
| `reasoning_start` | `{}` | 推理开始 |
| `reasoning_delta` | `{delta: string}` | 推理内容增量 |
| `reasoning_end` | `{duration: number}` | 推理结束 |
| `content_delta` | `{delta: string}` | 回复内容增量 |
| `tool_call` | `{tool_name, arguments}` | 工具调用 |
| `tool_result` | `{tool_name, result}` | 工具结果 |
| `message_end` | `{usage, task_state}` | 消息结束 |
| `error` | `{code, message}` | 错误 |

##### MCP (Model Context Protocol) 工具支持

- **MCP 客户端** (`/backend/app/llm/tools/mcp_client.py`)：
  - 支持 `stdio` 和 `sse` 两种传输方式
  - 工具发现与执行
  - 连接池管理
  - 超时处理

- **MCP 工具类型定义** (`/backend/app/llm/tools/types.py`)：
  - `McpToolInfo`：MCP 工具信息
  - `McpToolResult`：MCP 工具执行结果

- **工具注册表** (`/backend/app/llm/tools/registry.py`)：
  - 统一的工具执行接口
  - 支持内置工具、自定义工具、MCP 工具

##### 内置工具

位于 `/backend/app/llm/tools/builtin/`：

- **计算器** (`calculator.py`)：数学表达式计算、单位换算
- **时间工具** (`time.py`)：当前时间、时区转换

##### 消息版本管理

实现了消息版本系统，支持消息重新生成：

- `parent_id`：父消息 ID（版本组）
- `is_active`：当前激活版本
- `version_number`：版本号
- API 端点：`/messages/{id}/versions`、`/messages/{id}/switch-version`、`/messages/{id}/regenerate`

##### Token 计数优化

- **tiktoken 集成** (`/backend/app/llm/token_counter.py`)：
  - 准确的 token 计数
  - 多模型支持（GPT-4、Claude、Gemini）
  - 自动回退到字符估算

##### 共享工具执行器

- **executors.py** (`/backend/app/llm/tools/executors.py`)：
  - HTTP 工具执行（支持模板变量替换）
  - 统一的结果格式化

##### 新增依赖

- 后端：`tiktoken>=0.7.0`（Token 计数）
- 后端：`mcp` 相关依赖（MCP 协议支持）

### 修复 (Fixed)

#### PR Review 修复

- **N+1 查询优化**：Agent 列表页批量获取模型信息，避免循环查询
- **竞态条件修复**：使用 Tortoise ORM `F()` 表达式进行原子更新
- **代码复用**：提取 `executors.py` 共享 HTTP 工具执行逻辑
- **Token 计数准确性**：使用 tiktoken 替代字符估算

#### TypeScript 构建错误修复

- **Select 组件类型**：处理 `value` 可能为 `null` 的情况
- **Button 类型兼容**：修复 base-ui Button `type` prop 类型
- **HoverCard delay props**：移除不支持的 `openDelay`/`closeDelay`
- **ChatImageContent 类型**：添加缺失的 `type` 属性

#### mypy 类型错误修复

- **ResponseCode 枚举**：添加 `BAD_REQUEST`、`INTERNAL_ERROR`、`FORBIDDEN`
- **Model FK 类型**：`Tool.team_id`、`Agent.model_id` 等改为 `UUID` 类型
- **QuerySet 操作**：使用 `Q()` 对象替代 `|` 运算符
- **ImageContent None 检查**：添加 `img is not None` 条件
- **变量类型冲突**：重命名 `result` 变量避免 MCP/HTTP/code 类型混淆

#### 其他修复

- **ESLint @ts-ignore**：移除不必要的类型忽略注释
- **Ruff 格式化**：修复 87 个文件的代码格式

---

#### 应用模块 - Agent 编排页面重构

##### 布局重构

将 Agent 配置页面从传统的 Tab 表单布局重构为现代化三栏布局：

- **左侧边栏** (`agent-sidebar.tsx`):
  - Agent 图标、名称和类型标签显示
  - 悬停时图标变为返回箭头，点击返回应用列表
  - 导航菜单：编排、访问 API、日志与标注、监控

- **中间主内容区** (`agent-orchestration-form.tsx`):
  - 提示词编辑器：带 AI 生成按钮、字符计数
  - 变量配置：可折叠面板，支持添加自定义变量
  - 知识库关联：显示已关联知识库，元数据过滤开关
  - 工具配置：工具列表与启用状态开关
  - 视觉能力：可折叠面板，图片理解功能开关

- **右侧预览面板** (`agent-preview-panel.tsx`):
  - 调试与预览聊天窗口
  - 实时对话测试
  - 功能状态指示器

- **顶部工具栏** (`agent-toolbar.tsx`):
  - Agent 设置按钮（打开侧边抽屉）
  - 模型选择器下拉菜单（带模型图标和标签）
  - 模型参数调整对话框（温度、最大 Token）
  - 发布/取消发布下拉菜单

- **设置抽屉** (`agent-settings-drawer.tsx`):
  - 基础信息配置：图标、名称、描述
  - 开场消息和建议问题
  - 可见性设置（私有/团队）

##### 导航整合

- 将「智能 Agent」和「工作流」聚合到「应用」导航项下
- 更新 `platform-header.tsx`：移除独立的 Agents 导航，使用 AppWindow 图标
- 更新路由：`/app/workspace` → `/app/apps`

##### 应用列表页面 (`apps/page.tsx`)

- 统一的应用列表，支持类型筛选标签（全部/Agent/工作流）
- 简化的创建对话框：只需输入名称和描述，选择应用类型
- 应用卡片：显示类型标签、状态徽章、操作菜单

##### 后端修复

- 修复 `build_agent_out()` 函数：手动构建字典避免 Tortoise ORM ForeignKey 字段的 Pydantic 验证错误
- 修复 `build_agent_list_out()` 函数：同样的 QuerySet 序列化问题
- 正确处理 `model_id` UUID 转字符串、枚举值提取

##### 新增 UI 组件

- 通过 shadcn/ui 安装 `Slider` 组件
- 通过 shadcn/ui 安装 `RadioGroup` 组件

##### 国际化

- 新增 `apps` 命名空间翻译（中文/英文）
- 包含应用类型、创建流程、状态提示等文案

### 修复 (Fixed)

- Agent 详情 API 验证错误：`model.name`、`model.provider`、`model.model_id` 字段缺失
- 嵌套按钮水合错误：移除 DropdownMenuTrigger 的 `asChild` 属性
- base-ui 组件兼容性：Tooltip、Dialog、Dropdown 等组件不支持 `asChild`，改用直接样式
- Select 组件 `onValueChange` 类型：处理 `null` 值情况
- Slider `onValueChange` 类型：处理 `number | readonly number[]` 联合类型

---

#### 知识库模块 - 完整实现 (#12)

##### 后端 (Backend)

- **知识库 CRUD API**: 完整的知识库管理接口，支持创建、查询、更新、删除
- **文档管理**: 支持多种文件格式上传 (PDF, DOCX, TXT, MD, HTML, CSV, XLSX, JSON, PPTX)
- **URL 导入**: 支持从网页 URL 导入内容到知识库
- **文档处理流水线**:
  - 文档解析与文本提取
  - 智能分块 (支持自定义 chunk_size, chunk_overlap, separator)
  - 分块预览功能，确认后再入库
  - 文本清洗选项
- **向量化与存储**:
  - 集成 embedding 模型进行文档向量化
  - 支持自定义 embedding 模型选择
- **三种搜索模式**:
  - `vector`: 语义向量搜索，基于 embedding 相似度
  - `fulltext`: 全文关键词搜索，集成 jieba 中文分词
  - `hybrid`: 混合搜索，使用 RRF (Reciprocal Rank Fusion) 算法融合结果
- **搜索性能优化**: 数据库层 ILIKE 预过滤，大幅提升搜索速度
- **文档下载 API**: 支持下载原始上传文件，返回 `file_path`、`source_url`、`error_message` 字段
- **分块编辑 API**: 支持对已处理文档的分块进行增删改

##### 前端 (Frontend)

- **知识库列表页**:
  - 支持搜索、状态筛选
  - 批量选择与批量删除
  - 分页浏览
- **知识库详情页**:
  - 统计卡片 (文档数、分块数、Token 数、处理状态)
  - 文档列表与管理
- **文档上传**:
  - 拖拽上传支持
  - 多文件批量上传
  - 文件类型验证
  - 上传进度显示
- **文档处理预览**:
  - 单文档/批量文档分块预览
  - 分块参数实时调整
  - 分块内容编辑、删除、新增
  - 预览确认后再提交处理
- **搜索测试页面** (后台 + 中台):
  - 三种搜索模式切换
  - 搜索结果可折叠卡片，显示相似度分数
  - 底部圆角胶囊式搜索栏，现代 AI 聊天风格
  - 高级设置弹出菜单 (Popover): 检索方式、top_k、threshold
  - 支持中文输入法 (IME) 组合状态检测，避免回车误触发
  - 相似度阈值支持小数输入 (0-1)
- **文档操作**:
  - 下载原始文件 (带 Authorization 鉴权)
  - 查看源链接 (URL 类型文档)
  - 显示处理失败错误信息
  - 重新处理
  - 删除文档
  - 查看分块详情

##### 新增 UI 组件

- `ToggleGroup`: 搜索模式切换组件
- `Collapsible`: 可折叠面板组件
- `Progress`: 进度条组件
- `Popover`: 弹出菜单组件 (用于高级设置)

##### 依赖更新

- 后端新增 `jieba>=0.42.1` - 中文分词支持

### 修复 (Fixed)

- 搜索性能问题：从 11 秒优化到毫秒级响应
- 中文搜索分词问题：使用 jieba 替代简单字符分割
- 搜索测试页面布局：搜索栏固定在底部，不被内容挤压
- 文档上传路径计算错误：修正 dirname 层级从 5 改为 4
- 中文输入法回车误触发：添加 `e.nativeEvent.isComposing` 检测
- 后台 SidebarInset 圆角被遮挡：底部栏添加 `md:rounded-b-xl`
- 中台搜索栏 sticky 定位失效：使用 `calc(100vh - 64px)` 显式高度

---

## 贡献指南

在提交代码时，请在提交信息中关联相关 Issue，格式如：

```
feat(knowledge-base): 实现知识库搜索功能

- 添加向量搜索、全文搜索、混合搜索三种模式
- 集成 jieba 中文分词

Closes #12
```
