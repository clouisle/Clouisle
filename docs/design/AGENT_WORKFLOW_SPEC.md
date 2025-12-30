# Clouisle 智能 Agent & 工作流编排 设计规范

## 1. 概述

本文档定义了 Clouisle 中台的两个核心功能：**智能 Agent** 和 **工作流编排** 的设计规范。

### 1.1 功能定位

| 功能 | 定位 | 目标用户 |
|------|------|----------|
| **智能 Agent** | 可对话的 AI 助手实体，支持配置工具、知识库、Prompt | 普通用户、开发者 |
| **工作流编排** | 可视化编排的自动化任务流程，支持复杂逻辑 | 开发者、高级用户 |

### 1.2 设计原则

1. **团队隔离**：所有资源关联 Team，实现数据隔离
2. **复用已有**：复用 LLM Manager、知识库、用量追踪等已有模块
3. **渐进增强**：先实现核心功能，再逐步扩展高级特性
4. **类型安全**：后端 Pydantic Schema 与前端 TypeScript 类型保持一致

### 1.3 架构决策：统一应用入口

> **关键设计**：Agent 和 Workflow 统一归类为「应用」（Apps），共享同一入口。

#### 1.3.1 为什么统一到「应用」？

1. **概念统一**：Agent 和 Workflow 本质上都是可执行的 AI 应用，用户无需区分底层实现
2. **简化导航**：减少顶级菜单项，降低用户认知负担
3. **便于扩展**：未来新增应用类型（如 ChatFlow、Bot）可直接纳入现有体系
4. **参考业界**：Dify、Coze 等产品均采用类似设计

#### 1.3.2 应用类型

```typescript
type AppType = "agent" | "workflow" | "chatflow";  // 未来可扩展
```

| 类型 | 说明 | 图标 |
|------|------|------|
| `agent` | 智能 Agent，支持对话交互 | 🤖 |
| `workflow` | 工作流，可视化编排执行 | ⚡ |
| `chatflow` | 对话流（规划中） | 💬 |

#### 1.3.3 统一列表页

- 路由：`/app/apps`
- 功能：展示团队下所有应用，支持按类型筛选
- 创建：统一创建入口，通过类型选择器区分

---

## 2. 智能 Agent

### 2.1 功能概述

智能 Agent 是一个可配置的 AI 对话助手，用户可以：
- 自定义系统 Prompt 定义 Agent 的角色和行为
- 选择底层 LLM 模型
- 绑定工具（内置工具 / MCP Server）
- 关联知识库实现 RAG 增强
- 定义用户输入变量
- 发布和共享 Agent

### 2.2 数据模型

#### 2.2.1 Agent 模型

```python
class AgentStatus(str, Enum):
    DRAFT = "draft"           # 草稿
    PUBLISHED = "published"   # 已发布

class AgentVisibility(str, Enum):
    PRIVATE = "private"       # 仅创建者可见
    TEAM = "team"             # 团队成员可见
    PUBLIC = "public"         # 公开（未来支持）

class Agent(Model):
    """智能 Agent"""
    id = fields.UUIDField(pk=True)
    team = fields.ForeignKeyField("models.Team", related_name="agents")
    
    # 基本信息
    name = fields.CharField(max_length=100)
    description = fields.TextField(null=True)
    avatar_url = fields.CharField(max_length=500, null=True)
    icon = fields.CharField(max_length=50, null=True)  # emoji 或图标名
    
    # 模型配置
    model = fields.ForeignKeyField(
        "models.TeamModel", 
        related_name="agents",
        null=True,  # 可使用团队默认模型
    )
    system_prompt = fields.TextField(null=True)
    temperature = fields.FloatField(default=0.7)
    max_tokens = fields.IntField(null=True)
    top_p = fields.FloatField(null=True)
    
    # 工具配置 (JSON 数组)
    # [{"type": "builtin", "name": "web_search"}, {"type": "mcp", "server_id": "xxx"}]
    tools_config = fields.JSONField(default=list)
    
    # 知识库关联 (多对多，通过中间表)
    # knowledge_bases: ReverseRelation["AgentKnowledgeBase"]
    
    # 变量定义 (JSON 数组)
    # [{"name": "user_name", "type": "string", "required": true, "default": ""}]
    variables = fields.JSONField(default=list)
    
    # 状态
    status = fields.CharEnumField(AgentStatus, default=AgentStatus.DRAFT)
    visibility = fields.CharEnumField(AgentVisibility, default=AgentVisibility.PRIVATE)
    
    # 统计
    conversation_count = fields.IntField(default=0)
    message_count = fields.IntField(default=0)
    
    # 审计
    created_by = fields.ForeignKeyField("models.User", related_name="created_agents")
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "agents"
        ordering = ["-updated_at"]
```

#### 2.2.2 Agent-知识库关联

```python
class AgentKnowledgeBase(Model):
    """Agent 与知识库的关联"""
    id = fields.UUIDField(pk=True)
    agent = fields.ForeignKeyField("models.Agent", related_name="agent_knowledge_bases")
    knowledge_base = fields.ForeignKeyField("models.KnowledgeBase", related_name="agent_knowledge_bases")
    
    # RAG 配置
    retrieval_top_k = fields.IntField(default=5)
    score_threshold = fields.FloatField(default=0.5)
    
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "agent_knowledge_bases"
        unique_together = [("agent", "knowledge_base")]
```

#### 2.2.3 对话模型

```python
class Conversation(Model):
    """对话会话"""
    id = fields.UUIDField(pk=True)
    agent = fields.ForeignKeyField("models.Agent", related_name="conversations")
    user = fields.ForeignKeyField("models.User", related_name="conversations")
    
    title = fields.CharField(max_length=200, null=True)  # 自动生成或用户自定义
    
    # 变量值 (对话时填充的变量)
    variables = fields.JSONField(default=dict)
    
    # 统计
    message_count = fields.IntField(default=0)
    token_usage = fields.IntField(default=0)
    
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "conversations"
        ordering = ["-updated_at"]


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class Message(Model):
    """对话消息"""
    id = fields.UUIDField(pk=True)
    conversation = fields.ForeignKeyField("models.Conversation", related_name="messages")
    
    role = fields.CharEnumField(MessageRole)
    content = fields.TextField()
    
    # 工具调用相关
    tool_calls = fields.JSONField(null=True)      # Assistant 的工具调用
    tool_call_id = fields.CharField(max_length=100, null=True)  # Tool 消息的关联 ID
    
    # 元数据
    model = fields.CharField(max_length=100, null=True)  # 使用的模型
    token_usage = fields.JSONField(null=True)     # {"prompt": 100, "completion": 50}
    duration_ms = fields.IntField(null=True)      # 响应耗时
    
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "messages"
        ordering = ["created_at"]
```

### 2.3 API 设计

#### 2.3.1 Agent CRUD

```
GET    /api/v1/agents                    # 列表（支持分页、筛选）
POST   /api/v1/agents                    # 创建
GET    /api/v1/agents/{id}               # 详情
PUT    /api/v1/agents/{id}               # 更新
DELETE /api/v1/agents/{id}               # 删除
POST   /api/v1/agents/{id}/duplicate     # 复制
POST   /api/v1/agents/{id}/publish       # 发布
POST   /api/v1/agents/{id}/unpublish     # 取消发布
```

**列表查询参数**：
- `team_id`: 团队筛选（必填）
- `status`: draft / published
- `visibility`: private / team / public
- `keyword`: 名称/描述搜索
- `page`, `page_size`: 分页

**创建/更新 Schema**：
```python
class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    avatar_url: str | None = None
    icon: str | None = None
    model_id: UUID | None = None
    system_prompt: str | None = None
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)
    top_p: float | None = Field(default=None, ge=0, le=1)
    tools_config: list[dict] = []
    knowledge_base_ids: list[UUID] = []
    variables: list[dict] = []
    visibility: AgentVisibility = AgentVisibility.PRIVATE

class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    avatar_url: str | None = None
    icon: str | None = None
    model_id: UUID | None = None
    system_prompt: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)
    top_p: float | None = Field(default=None, ge=0, le=1)
    tools_config: list[dict] | None = None
    knowledge_base_ids: list[UUID] | None = None
    variables: list[dict] | None = None
    visibility: AgentVisibility | None = None
```

#### 2.3.2 对话 API

```
POST   /api/v1/agents/{id}/chat          # 非流式对话
POST   /api/v1/agents/{id}/chat/stream   # 流式对话 (SSE)
GET    /api/v1/agents/{id}/conversations # Agent 的对话列表
```

**对话请求**：
```python
class ChatRequest(BaseModel):
    message: str                          # 用户消息
    conversation_id: UUID | None = None   # 续接已有对话
    variables: dict[str, Any] = {}        # 变量值
    stream: bool = False                  # 是否流式（路由区分）
```

**非流式响应**：
```python
class ChatResponse(BaseModel):
    conversation_id: UUID
    message: MessageOut                   # 助手回复
    usage: UsageInfo | None
```

**流式响应 (SSE)**：
```
event: message_start
data: {"conversation_id": "xxx", "message_id": "xxx"}

event: content_delta
data: {"delta": "Hello"}

event: content_delta
data: {"delta": " World"}

event: tool_call
data: {"tool_name": "web_search", "arguments": {...}}

event: tool_result
data: {"tool_name": "web_search", "result": {...}}

event: message_end
data: {"usage": {"prompt_tokens": 100, "completion_tokens": 50}}

event: error
data: {"code": 1001, "msg": "Error message"}
```

#### 2.3.3 会话管理 API

```
GET    /api/v1/conversations             # 我的所有对话
GET    /api/v1/conversations/{id}        # 对话详情（含消息列表）
DELETE /api/v1/conversations/{id}        # 删除对话
PATCH  /api/v1/conversations/{id}        # 更新（如修改标题）
DELETE /api/v1/conversations/{id}/messages/{msg_id}  # 删除单条消息
```

### 2.4 前端路由

#### 2.4.1 实际实现结构

> **注意**：实际实现中，Agent 和 Workflow 统一到「应用」模块下管理。

```
(platform)/app/
├── apps/
│   ├── page.tsx                         # 统一应用列表（Agent + Workflow）
│   └── _components/
│       └── app-create-dialog.tsx        # 创建应用对话框（类型选择）
│
├── apps/[id]/
│   ├── page.tsx                         # Agent 编排页面（三栏布局）
│   ├── chat/
│   │   ├── page.tsx                     # 对话界面
│   │   └── _components/
│   │       └── chat-interface.tsx       # 对话组件
│   └── _components/
│       ├── agent-sidebar.tsx            # 左侧边栏（导航）
│       ├── agent-toolbar.tsx            # 顶部工具栏
│       ├── agent-orchestration-form.tsx # 中间编排表单
│       ├── agent-preview-panel.tsx      # 右侧预览面板
│       ├── agent-settings-drawer.tsx    # 设置抽屉
│       └── agent-config-form.tsx        # 配置表单（旧版，备用）
```

#### 2.4.2 Agent 编排页面布局

```
┌────────────────────────────────────────────────────────────────────────┐
│                              顶部工具栏                                  │
│  [Agent 设置]  [模型选择器: gpt-4o-mini ▼]  [参数 ⚙]  [发布 ▼]         │
├──────────┬────────────────────────────────────┬────────────────────────┤
│          │                                    │                        │
│  左侧边栏 │           中间编排区域              │     右侧预览面板        │
│          │                                    │                        │
│ ┌──────┐ │  ┌─────────────────────────────┐  │  ┌──────────────────┐  │
│ │🤖    │ │  │  提示词                 [生成]│  │  │  调试与预览    ↻ │  │
│ │Agent │ │  │                              │  │  │                  │  │
│ │ Name │ │  │  在这里写你的提示词...        │  │  │                  │  │
│ └──────┘ │  │                              │  │  │  开始对话来测试   │  │
│          │  │                         字数 │  │  │  您的 Agent      │  │
│ ▣ 编排   │  └─────────────────────────────┘  │  │                  │  │
│ ▢ API   │                                    │  │                  │  │
│ ▢ 日志  │  ┌─────────────────────────────┐  │  │                  │  │
│ ▢ 监控  │  │  变量              [+ 添加] │  │  ├──────────────────┤  │
│          │  │  变量能使用户输入表单引入... │  │  │ [输入消息...]  ➤ │  │
│          │  └─────────────────────────────┘  │  │                  │  │
│          │                                    │  │  ● 功能已开启     │  │
│          │  ┌─────────────────────────────┐  │  └──────────────────┘  │
│          │  │  知识库            [+ 添加] │  │                        │
│          │  │  您可以导入知识库作为上下文  │  │                        │
│          │  │  ─────────────────────────  │  │                        │
│          │  │  元数据过滤           [禁用]│  │                        │
│          │  └─────────────────────────────┘  │                        │
│          │                                    │                        │
│          │  ┌─────────────────────────────┐  │                        │
│          │  │  工具       1/1 启用 [添加] │  │                        │
│          │  │  🕐 time   获取当前时间  [✓]│  │                        │
│          │  └─────────────────────────────┘  │                        │
│          │                                    │                        │
│          │  ┌─────────────────────────────┐  │                        │
│          │  │  视觉        [设置]    [  ] │  │                        │
│          │  └─────────────────────────────┘  │                        │
│          │                                    │                        │
└──────────┴────────────────────────────────────┴────────────────────────┘
```

#### 2.4.3 组件职责

| 组件 | 职责 |
|------|------|
| `agent-sidebar.tsx` | 左侧导航栏，显示 Agent 信息和导航菜单，点击图标返回列表 |
| `agent-toolbar.tsx` | 顶部工具栏，模型选择、参数配置、发布操作 |
| `agent-orchestration-form.tsx` | 中间编排区域，可折叠的配置面板（提示词、变量、知识库、工具、视觉） |
| `agent-preview-panel.tsx` | 右侧预览面板，实时对话测试 |
| `agent-settings-drawer.tsx` | 设置抽屉，基础信息配置（名称、描述、开场白等） |

#### 2.4.4 设计决策

1. **统一入口**：Agent 和 Workflow 统一到 `/app/apps` 路由下，通过类型标签筛选
2. **简化创建**：创建对话框只需名称和描述，类型选择使用 RadioGroup
3. **三栏布局**：参考主流 AI 产品（如 Dify），采用左导航 + 中编排 + 右预览布局
4. **自动保存**：配置变更自动触发防抖保存，无需手动点击保存按钮
5. **可折叠面板**：使用 Collapsible 组件，允许用户折叠不常用的配置区域

### 2.5 核心交互流程

#### 2.5.1 创建 Agent

```
用户点击「新建 Agent」
    ↓
弹出创建对话框，输入名称
    ↓
POST /api/v1/agents → 创建草稿
    ↓
跳转到配置页 /app/agents/{id}
    ↓
配置 Prompt、模型、工具、知识库
    ↓
点击「发布」→ POST /api/v1/agents/{id}/publish
```

#### 2.5.2 对话流程

```
用户进入对话页 /app/agents/{id}/chat
    ↓
输入消息，点击发送
    ↓
POST /api/v1/agents/{id}/chat/stream (SSE)
    ↓
后端处理:
  1. 创建/获取 Conversation
  2. 保存用户消息
  3. 构建消息上下文（含历史、系统 Prompt）
  4. 如有知识库，执行 RAG 检索
  5. 调用 LLM（team_chat_stream）
  6. 流式返回响应
  7. 保存助手消息
    ↓
前端实时展示流式内容
```

---

## 3. 工作流编排

### 3.1 功能概述

工作流是可视化编排的自动化任务流程，用户可以：
- 拖拽式编排节点和连线
- 配置各节点的参数和逻辑
- 定义变量和数据传递
- 调试和预览执行
- 手动/定时/Webhook 触发执行
- 查看执行历史和日志

### 3.2 节点类型

| 类型 | 代码 | 图标 | 输入 | 输出 | 说明 |
|------|------|------|------|------|------|
| 开始 | `start` | 🚀 | - | 用户输入变量 | 工作流入口，定义输入参数 |
| 结束 | `end` | ✅ | 任意 | - | 工作流出口，定义输出结果 |
| LLM | `llm` | 🧠 | Prompt + 变量 | 文本 | 调用语言模型生成 |
| Agent | `agent` | 🤖 | 消息 | 回复 | 调用已创建的 Agent |
| 子工作流 | `sub_workflow` | 📦 | 输入映射 | 输出映射 | 调用另一个工作流 |
| 知识库检索 | `kb_retrieval` | 📚 | Query | 文档片段 | RAG 检索 |
| 条件分支 | `condition` | 🔀 | 表达式 | 布尔 | if/else 逻辑分支 |
| 循环 | `loop` | 🔄 | 数组 | 元素 | 遍历数组执行子流程 |
| 代码 | `code` | 💻 | 变量 | 执行结果 | Python/JavaScript 执行 |
| HTTP 请求 | `http` | 🌐 | URL + 参数 | 响应 | 调用外部 API |
| 工具调用 | `tool` | 🔧 | 参数 | 结果 | 内置工具或 MCP |
| 人工审核 | `human_review` | 👤 | 待审内容 | 审核结果 | 暂停等待人工确认 |
| 变量赋值 | `variable` | 📝 | 表达式 | 变量 | 设置或转换变量 |
| 并行 | `parallel` | ⚡ | - | - | 并行执行多分支 |
| 延时 | `delay` | ⏱️ | 秒数 | - | 等待指定时间 |

#### 3.2.1 子工作流节点

子工作流节点允许工作流调用另一个工作流，实现流程复用和模块化：

```python
class SubWorkflowNodeConfig(BaseModel):
    """子工作流节点配置"""
    workflow_id: UUID                              # 被调用的工作流 ID
    input_mapping: dict[str, str]                  # 输入参数映射 { 子流程变量名: 父流程表达式 }
    output_mapping: dict[str, str]                 # 输出参数映射 { 父流程变量名: 子流程输出 }
    timeout_seconds: int = 300                     # 超时时间
    fail_on_error: bool = True                     # 子流程失败是否中断父流程
```

**循环依赖检测**：

```python
MAX_WORKFLOW_DEPTH = 5  # 最大嵌套深度

def detect_circular_dependency(workflow_id: str, visited: set[str] = None) -> bool:
    """检测工作流是否存在循环调用"""
    if visited is None:
        visited = set()
    
    if workflow_id in visited:
        return True  # 发现循环
    
    visited.add(workflow_id)
    sub_workflow_ids = get_sub_workflow_ids(workflow_id)
    
    for sub_id in sub_workflow_ids:
        if detect_circular_dependency(sub_id, visited.copy()):
            return True
    
    return False
```

### 3.3 数据模型

#### 3.3.1 工作流模型

```python
class WorkflowStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"

class TriggerType(str, Enum):
    MANUAL = "manual"       # 手动触发
    CRON = "cron"           # 定时触发
    WEBHOOK = "webhook"     # Webhook 触发

class Workflow(Model):
    """工作流"""
    id = fields.UUIDField(pk=True)
    team = fields.ForeignKeyField("models.Team", related_name="workflows")
    
    # 基本信息
    name = fields.CharField(max_length=100)
    description = fields.TextField(null=True)
    icon = fields.CharField(max_length=50, null=True)
    
    # 工作流定义 (ReactFlow 格式)
    # {
    #   "nodes": [...],
    #   "edges": [...],
    #   "viewport": {...}
    # }
    definition = fields.JSONField(default=dict)
    
    # 全局变量定义
    # [{"name": "input_text", "type": "string", "required": true}]
    variables = fields.JSONField(default=list)
    
    # 状态
    status = fields.CharEnumField(WorkflowStatus, default=WorkflowStatus.DRAFT)
    version = fields.IntField(default=1)
    
    # 触发配置
    trigger_type = fields.CharEnumField(TriggerType, default=TriggerType.MANUAL)
    trigger_config = fields.JSONField(default=dict)  # cron 表达式、webhook secret 等
    webhook_token = fields.CharField(max_length=100, null=True, unique=True)
    
    # 统计
    run_count = fields.IntField(default=0)
    success_count = fields.IntField(default=0)
    fail_count = fields.IntField(default=0)
    
    # 审计
    created_by = fields.ForeignKeyField("models.User", related_name="created_workflows")
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "workflows"
        ordering = ["-updated_at"]
```

#### 3.3.2 节点定义格式

```python
# ReactFlow 节点格式
class NodeData(BaseModel):
    """节点数据"""
    type: str                          # 节点类型
    label: str                         # 显示名称
    config: dict                       # 节点配置（因类型而异）

# 示例节点配置
llm_node_config = {
    "model_id": "uuid",
    "prompt": "基于以下内容生成摘要：\n{{input}}",
    "temperature": 0.7,
    "max_tokens": 1000,
}

condition_node_config = {
    "expression": "{{score}} > 0.8",
    "true_output": "high",
    "false_output": "low",
}

http_node_config = {
    "method": "POST",
    "url": "https://api.example.com/webhook",
    "headers": {"Authorization": "Bearer {{api_key}}"},
    "body": {"text": "{{input}}"},
}

code_node_config = {
    "language": "python",
    "code": """
def main(inputs):
    text = inputs.get('text', '')
    return {'word_count': len(text.split())}
""",
}
```

#### 3.3.3 执行记录模型

```python
class RunStatus(str, Enum):
    PENDING = "pending"       # 等待执行
    RUNNING = "running"       # 执行中
    SUCCESS = "success"       # 成功
    FAILED = "failed"         # 失败
    CANCELLED = "cancelled"   # 已取消
    TIMEOUT = "timeout"       # 超时

class NodeStatus(str, Enum):
    PENDING = "pending"       # 等待执行
    RUNNING = "running"       # 执行中
    SUCCESS = "success"       # 成功
    FAILED = "failed"         # 失败
    SKIPPED = "skipped"       # 跳过

class WorkflowRun(Model):
    """工作流执行记录"""
    id = fields.UUIDField(pk=True)
    workflow = fields.ForeignKeyField("models.Workflow", related_name="runs")
    
    # 触发信息
    trigger_type = fields.CharEnumField(TriggerType)
    triggered_by = fields.ForeignKeyField(
        "models.User", 
        related_name="workflow_runs",
        null=True,  # Webhook/Cron 触发时为空
    )
    
    # 执行模式
    is_debug = fields.BooleanField(default=False)  # 是否调试模式
    
    # 执行状态
    status = fields.CharEnumField(RunStatus, default=RunStatus.PENDING)
    
    # 输入/输出
    inputs = fields.JSONField(default=dict)
    outputs = fields.JSONField(null=True)
    
    # 执行上下文快照
    context_snapshot = fields.JSONField(default=dict)
    
    # 子工作流关联
    parent_run_id = fields.UUIDField(null=True)    # 父执行 ID
    root_run_id = fields.UUIDField(null=True)      # 根执行 ID
    depth = fields.IntField(default=0)             # 执行深度
    
    # ⏱️ 时间记录
    created_at = fields.DatetimeField(auto_now_add=True)
    started_at = fields.DatetimeField(null=True)
    finished_at = fields.DatetimeField(null=True)
    
    # 统计汇总
    total_nodes = fields.IntField(default=0)
    executed_nodes = fields.IntField(default=0)
    failed_nodes = fields.IntField(default=0)
    skipped_nodes = fields.IntField(default=0)
    total_duration_ms = fields.IntField(null=True)
    total_token_usage = fields.JSONField(default=dict)  # {"prompt": 0, "completion": 0}
    
    # 错误信息
    error_message = fields.TextField(null=True)
    error_node_id = fields.CharField(max_length=100, null=True)
    error_traceback = fields.TextField(null=True)

    class Meta:
        table = "workflow_runs"
        ordering = ["-created_at"]


class NodeExecution(Model):
    """节点执行记录 - 每个节点每次执行一条记录"""
    id = fields.UUIDField(pk=True)
    
    # 关联
    run = fields.ForeignKeyField("models.WorkflowRun", related_name="node_executions")
    
    # 节点标识
    node_id = fields.CharField(max_length=100)      # ReactFlow 节点 ID
    node_type = fields.CharField(max_length=50)     # start/end/llm/condition/...
    node_name = fields.CharField(max_length=200)    # 节点显示名称
    
    # 执行顺序
    execution_order = fields.IntField()
    
    # 状态
    status = fields.CharEnumField(NodeStatus, default=NodeStatus.PENDING)
    
    # ⏱️ 时间记录（精确到毫秒）
    queued_at = fields.DatetimeField(null=True)     # 进入队列时间
    started_at = fields.DatetimeField(null=True)    # 开始执行时间
    finished_at = fields.DatetimeField(null=True)   # 完成时间
    
    # 耗时（冗余存储，方便查询）
    queue_duration_ms = fields.IntField(null=True)
    execution_duration_ms = fields.IntField(null=True)
    
    # 📥 输入数据
    inputs = fields.JSONField(null=True)
    inputs_storage_key = fields.CharField(max_length=200, null=True)  # 大数据外部存储 key
    
    # 📤 输出数据
    outputs = fields.JSONField(null=True)
    outputs_storage_key = fields.CharField(max_length=200, null=True)  # 大数据外部存储 key
    
    # 节点配置快照
    config_snapshot = fields.JSONField(null=True)
    
    # 🧠 LLM 相关
    model_used = fields.CharField(max_length=100, null=True)
    prompt_tokens = fields.IntField(null=True)
    completion_tokens = fields.IntField(null=True)
    total_tokens = fields.IntField(null=True)
    
    # 🔗 子工作流
    sub_run_id = fields.UUIDField(null=True)
    
    # ❌ 错误信息
    error_message = fields.TextField(null=True)
    error_type = fields.CharField(max_length=100, null=True)
    error_traceback = fields.TextField(null=True)
    
    # 重试
    retry_count = fields.IntField(default=0)
    
    class Meta:
        table = "workflow_node_executions"
        ordering = ["execution_order"]
```

### 3.4 API 设计

#### 3.4.1 工作流 CRUD

```
GET    /api/v1/workflows                  # 列表
POST   /api/v1/workflows                  # 创建
GET    /api/v1/workflows/{id}             # 详情
PUT    /api/v1/workflows/{id}             # 更新定义
DELETE /api/v1/workflows/{id}             # 删除
POST   /api/v1/workflows/{id}/duplicate   # 复制
POST   /api/v1/workflows/{id}/publish     # 发布
POST   /api/v1/workflows/{id}/archive     # 归档
```

**创建/更新 Schema**：
```python
class WorkflowCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    icon: str | None = None

class WorkflowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    icon: str | None = None
    definition: dict | None = None
    variables: list[dict] | None = None
    trigger_type: TriggerType | None = None
    trigger_config: dict | None = None
```

#### 3.4.2 执行 API

```
POST   /api/v1/workflows/{id}/run         # 执行工作流
POST   /api/v1/workflows/{id}/debug       # 调试执行 (SSE 流式)
GET    /api/v1/workflows/{id}/runs        # 执行历史
```

**执行请求**：
```python
class WorkflowRunRequest(BaseModel):
    inputs: dict[str, Any] = {}           # 输入变量
    async_mode: bool = True               # 是否异步执行
```

**调试流式响应 (SSE)**：
```
event: run_start
data: {"run_id": "xxx"}

event: node_start
data: {"node_id": "node1", "type": "llm"}

event: node_output
data: {"node_id": "node1", "delta": "生成中..."}

event: node_end
data: {"node_id": "node1", "outputs": {...}, "duration_ms": 1500}

event: node_start
data: {"node_id": "node2", "type": "condition"}

event: node_end
data: {"node_id": "node2", "outputs": {"branch": "true"}}

event: run_end
data: {"status": "success", "outputs": {...}, "duration_ms": 3000}

event: error
data: {"node_id": "node1", "code": 1001, "msg": "Error"}
```

#### 3.4.3 执行记录 API

```
GET    /api/v1/workflow-runs/{id}         # 执行详情
POST   /api/v1/workflow-runs/{id}/cancel  # 取消执行
GET    /api/v1/workflow-runs/{id}/logs    # 执行日志
```

#### 3.4.4 Webhook API

```
POST   /api/v1/webhooks/workflow/{token}  # Webhook 触发入口
```

### 3.5 前端路由

```
(platform)/app/
├── workflows/
│   ├── page.tsx                          # 工作流列表
│   └── _components/
│       ├── workflow-grid.tsx
│       ├── workflow-card.tsx
│       ├── create-workflow-dialog.tsx
│       └── index.ts
│
├── workflows/[id]/
│   ├── page.tsx                          # 工作流编辑器
│   ├── runs/
│   │   ├── page.tsx                      # 执行历史
│   │   └── _components/
│   │       ├── run-list.tsx
│   │       └── index.ts
│   └── _components/
│       ├── flow-editor.tsx               # ReactFlow 编辑器
│       ├── node-panel.tsx                # 左侧节点面板
│       ├── config-panel.tsx              # 右侧配置面板
│       ├── toolbar.tsx                   # 顶部工具栏
│       ├── debug-panel.tsx               # 调试面板
│       ├── variable-panel.tsx            # 变量面板
│       ├── nodes/                        # 自定义节点组件
│       │   ├── base-node.tsx
│       │   ├── start-node.tsx
│       │   ├── end-node.tsx
│       │   ├── llm-node.tsx
│       │   ├── agent-node.tsx
│       │   ├── condition-node.tsx
│       │   ├── loop-node.tsx
│       │   ├── code-node.tsx
│       │   ├── http-node.tsx
│       │   └── index.ts
│       └── index.ts
│
└── workflows/[id]/runs/[runId]/
    ├── page.tsx                          # 单次执行详情
    └── _components/
        ├── run-detail.tsx
        ├── node-result.tsx
        └── index.ts
```

### 3.6 执行引擎设计

#### 3.6.1 架构

```
┌─────────────────────────────────────────────────────────────────┐
│                      WorkflowExecutor                            │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    ExecutionContext                      │    │
│  │  - run_id, workflow, inputs                             │    │
│  │  - variables (运行时变量)                                │    │
│  │  - node_results (节点结果)                               │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    NodeExecutor                          │    │
│  │  - execute(node, context) -> NodeResult                 │    │
│  └─────────────────────────────────────────────────────────┘    │
│         │          │          │          │          │           │
│         ▼          ▼          ▼          ▼          ▼           │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│  │   LLM   │ │  Code   │ │  HTTP   │ │Condition│ │  Loop   │   │
│  │Executor │ │Executor │ │Executor │ │Executor │ │Executor │   │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

#### 3.6.2 执行流程

```python
class WorkflowExecutor:
    async def execute(self, workflow: Workflow, inputs: dict) -> WorkflowRun:
        # 1. 创建执行记录
        run = await WorkflowRun.create(...)
        
        # 2. 解析工作流图
        graph = self._parse_definition(workflow.definition)
        
        # 3. 找到开始节点
        start_node = graph.get_start_node()
        
        # 4. 初始化上下文
        context = ExecutionContext(
            run=run,
            variables=inputs,
            node_results={},
        )
        
        # 5. 执行节点（拓扑排序 + BFS）
        await self._execute_node(start_node, context)
        
        # 6. 更新执行记录
        run.status = RunStatus.SUCCESS
        run.outputs = context.get_outputs()
        await run.save()
        
        return run
    
    async def _execute_node(self, node: Node, context: ExecutionContext):
        # 获取节点执行器
        executor = self._get_executor(node.type)
        
        # 执行节点
        result = await executor.execute(node, context)
        
        # 记录结果
        context.node_results[node.id] = result
        
        # 获取下一个节点
        next_nodes = self._get_next_nodes(node, result, context)
        
        # 递归执行
        for next_node in next_nodes:
            await self._execute_node(next_node, context)
```

### 3.7 执行日志系统

#### 3.7.1 统一日志架构

不论调试模式还是生产模式，都使用相同的日志记录逻辑：

```
┌─────────────────────────────────────────────────────────────────┐
│                    统一执行引擎                                  │
│                                                                 │
│   调试模式（SSE）  ──┬──▶  ExecutionLogger  ──▶  持久化存储      │
│   生产模式（异步）  ──┘     (批量写入)           (相同数据)       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

#### 3.7.2 事件发射器接口

```python
from abc import ABC, abstractmethod

class EventEmitter(ABC):
    """事件发射器抽象接口"""
    
    @abstractmethod
    async def emit(self, event: str, data: dict) -> None:
        pass


class SSEEmitter(EventEmitter):
    """SSE 事件发射器 - 调试模式实时推送"""
    
    async def emit(self, event: str, data: dict) -> None:
        await self.response.send(f"event: {event}\ndata: {json.dumps(data)}\n\n")


class NoOpEmitter(EventEmitter):
    """空操作发射器 - 生产模式"""
    
    async def emit(self, event: str, data: dict) -> None:
        pass  # 日志已记录在数据库


class RedisEmitter(EventEmitter):
    """Redis Pub/Sub 发射器 - 用于 WebSocket 推送"""
    
    async def emit(self, event: str, data: dict) -> None:
        await self.redis.publish(self.channel, json.dumps({"event": event, "data": data}))
```

#### 3.7.3 执行日志记录器

```python
class ExecutionLogger:
    """执行日志记录器 - 批量写入优化"""
    
    def __init__(self, run: WorkflowRun, flush_interval: float = 1.0):
        self.run = run
        self.pending_nodes: dict[str, NodeExecution] = {}
        self.flush_interval = flush_interval
        self._lock = asyncio.Lock()
    
    async def log_node_start(self, node_id: str, node_type: str, node_name: str, order: int):
        """记录节点开始（仅内存）"""
        async with self._lock:
            self.pending_nodes[node_id] = NodeExecution(
                id=uuid4(),
                run_id=self.run.id,
                node_id=node_id,
                node_type=node_type,
                node_name=node_name,
                execution_order=order,
                status=NodeStatus.RUNNING,
                queued_at=datetime.utcnow(),
                started_at=datetime.utcnow(),
            )
    
    async def log_node_end(self, node_id: str, status: NodeStatus, outputs: dict = None, error: str = None):
        """记录节点结束（仅内存）"""
        async with self._lock:
            node_exec = self.pending_nodes.get(node_id)
            if node_exec:
                node_exec.status = status
                node_exec.finished_at = datetime.utcnow()
                node_exec.execution_duration_ms = self._calc_duration(
                    node_exec.started_at, node_exec.finished_at
                )
                node_exec.outputs = outputs
                node_exec.error_message = error
    
    async def flush(self):
        """批量写入数据库"""
        async with self._lock:
            if not self.pending_nodes:
                return
            nodes_to_save = list(self.pending_nodes.values())
            self.pending_nodes.clear()
        
        await NodeExecution.bulk_create(
            nodes_to_save,
            update_fields=["status", "finished_at", "execution_duration_ms", "outputs", "error_message"],
            on_conflict=["id"],
        )
```

### 3.8 性能与并发优化

#### 3.8.1 数据库写入优化

**问题**：每个节点执行过程中多次写入数据库，10 个节点可能产生 40+ 次写入。

**解决方案**：批量写入 + 延迟持久化

```python
# 优化前：每个节点 4 次写入
await NodeExecution.create(...)     # 写入 1
node_exec.status = RUNNING
await node_exec.save()              # 写入 2
node_exec.status = SUCCESS
await node_exec.save()              # 写入 3
run.executed_nodes += 1
await run.save()                    # 写入 4

# 优化后：批量写入，10 个节点只需 3-5 次写入
logger.log_node_start(...)          # 内存
logger.log_node_end(...)            # 内存
await logger.flush()                # 批量写入
```

#### 3.8.2 并发统计 - Redis 原子计数器

**问题**：多个并行节点同时更新统计字段会导致数据丢失。

**解决方案**：使用 Redis 原子操作

```python
class RunStatsTracker:
    """使用 Redis 跟踪运行时统计"""
    
    def __init__(self, redis: Redis, run_id: UUID):
        self.redis = redis
        self.key_prefix = f"workflow_run:{run_id}"
    
    async def increment_executed(self):
        return await self.redis.incr(f"{self.key_prefix}:executed")
    
    async def increment_failed(self):
        return await self.redis.incr(f"{self.key_prefix}:failed")
    
    async def add_tokens(self, prompt: int, completion: int):
        pipe = self.redis.pipeline()
        pipe.incrby(f"{self.key_prefix}:prompt_tokens", prompt)
        pipe.incrby(f"{self.key_prefix}:completion_tokens", completion)
        await pipe.execute()
    
    async def sync_to_db(self, run: WorkflowRun):
        """执行结束后同步到数据库"""
        stats = await self.get_stats()
        run.executed_nodes = stats["executed_nodes"]
        run.failed_nodes = stats["failed_nodes"]
        run.total_token_usage = {
            "prompt": stats["prompt_tokens"],
            "completion": stats["completion_tokens"],
        }
        await run.save()
```

#### 3.8.3 大数据分离存储

**问题**：节点输入输出可能很大，每次 save 都要序列化。

**解决方案**：大数据存储到 Redis/S3，数据库只存引用

```python
class DataStorage:
    """大数据存储"""
    
    THRESHOLD = 10 * 1024  # 10KB 以上存储到外部
    
    async def store(self, run_id: UUID, node_id: str, data_type: str, data: dict) -> str | None:
        serialized = json.dumps(data, default=str)
        if len(serialized) < self.THRESHOLD:
            return None  # 小数据不需要外部存储
        
        key = f"workflow_data:{run_id}:{node_id}:{data_type}"
        await self.redis.setex(key, 86400 * 7, serialized)  # 7 天过期
        return key
```

#### 3.8.4 并发执行限制

```python
class ConcurrencyLimiter:
    """并发限制器"""
    
    async def limit_workflow_runs(self, team_id: UUID, max_concurrent: int = 5):
        """限制每个团队的并发工作流数"""
        key = f"workflow_concurrent:{team_id}"
        current = await self.redis.incr(key)
        if current > max_concurrent:
            await self.redis.decr(key)
            raise BusinessError(code=ResponseCode.RATE_LIMITED, msg_key="workflow_concurrent_limit_exceeded")
    
    async def limit_node_execution(self, node_type: str, max_concurrent: int = 10):
        """限制特定类型节点的并发数（如 LLM 调用）"""
        # 使用 Redis 分布式信号量实现
```

#### 3.8.5 配置参数

```python
class WorkflowConfig:
    # 日志刷新间隔
    LOG_FLUSH_INTERVAL: float = 1.0  # 秒
    
    # 并发限制
    MAX_CONCURRENT_RUNS_PER_TEAM: int = 5
    MAX_CONCURRENT_LLM_CALLS: int = 10
    MAX_CONCURRENT_HTTP_CALLS: int = 20
    MAX_PARALLEL_NODES: int = 5
    
    # 大数据阈值
    LARGE_DATA_THRESHOLD: int = 10 * 1024  # 10KB
    DATA_RETENTION_DAYS: int = 7
    
    # 执行超时
    NODE_TIMEOUT: int = 300  # 5分钟
    WORKFLOW_TIMEOUT: int = 1800  # 30分钟
    
    # 子工作流
    MAX_WORKFLOW_DEPTH: int = 5
```

#### 3.8.6 性能对比

| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| 数据库写入次数（10节点） | 40+ 次 | 3-5 次 |
| 并发冲突 | 有风险 | Redis 原子操作，无冲突 |
| 大数据存储 | 全部存 DB | 分离存储，DB 只存引用 |
| 并发执行 | 无限制 | 团队级 + 节点类型级限制 |
```

---

## 4. 后端文件结构

```
backend/app/
├── models/
│   ├── agent.py                  # Agent, AgentKnowledgeBase, Conversation, Message
│   └── workflow.py               # Workflow, WorkflowRun, NodeExecution
│
├── schemas/
│   ├── agent.py                  # Agent 相关 Schema
│   └── workflow.py               # Workflow, WorkflowRun, NodeExecution Schema
│
├── api/v1/
│   ├── agents.py                 # Agent CRUD + 对话 API
│   ├── conversations.py          # 会话管理 API
│   ├── workflows.py              # 工作流 CRUD + 执行 API
│   ├── workflow_runs.py          # 执行记录 API
│   └── webhooks.py               # Webhook 入口
│
├── services/
│   ├── agent_executor.py         # Agent 执行服务
│   └── workflow/
│       ├── __init__.py
│       ├── executor.py           # WorkflowExecutor（核心执行器）
│       ├── context.py            # ExecutionContext（执行上下文）
│       ├── graph.py              # WorkflowGraph（图解析、拓扑排序）
│       ├── logger.py             # ExecutionLogger（批量日志记录）
│       ├── stats.py              # RunStatsTracker（Redis 统计）
│       ├── storage.py            # DataStorage（大数据存储）
│       ├── limiter.py            # ConcurrencyLimiter（并发限制）
│       ├── events.py             # EventEmitter 接口
│       └── nodes/                # 节点执行器
│           ├── __init__.py
│           ├── base.py           # BaseNodeExecutor
│           ├── start.py          # 开始节点
│           ├── end.py            # 结束节点
│           ├── llm.py            # LLM 节点
│           ├── agent.py          # Agent 节点
│           ├── sub_workflow.py   # 子工作流节点
│           ├── kb_retrieval.py   # 知识库检索节点
│           ├── condition.py      # 条件分支节点
│           ├── loop.py           # 循环节点
│           ├── code.py           # 代码执行节点
│           ├── http.py           # HTTP 请求节点
│           ├── tool.py           # 工具调用节点
│           ├── variable.py       # 变量赋值节点
│           └── delay.py          # 延时节点
│
└── tasks/
    └── workflow.py               # Celery 异步任务（预留）
```

---

## 5. 实现优先级

### Phase 1: Agent 核心（P0）

| 任务 | 预估时间 | 依赖 |
|------|----------|------|
| Agent 数据模型 | 0.5d | - |
| Agent CRUD API | 0.5d | 数据模型 |
| 对话数据模型 | 0.5d | Agent 模型 |
| 对话 API（非流式） | 0.5d | 对话模型 |
| 对话 API（流式 SSE） | 1d | LLM stream |
| 前端 Agent 列表 | 0.5d | CRUD API |
| 前端 Agent 配置 | 1d | - |
| 前端对话界面 | 1d | 流式 API |

**Phase 1 总计：约 5-6 天**

### Phase 2: Agent 增强（P1）

| 任务 | 预估时间 | 依赖 |
|------|----------|------|
| Agent 关联知识库 | 1d | 知识库模块 |
| Agent 关联工具 | 1d | Tool 系统 |
| 对话 RAG 检索 | 1d | 知识库检索 |
| 工具调用展示 | 1d | - |
| 会话历史管理 | 0.5d | - |
| Agent 发布/复制 | 0.5d | - |

**Phase 2 总计：约 5 天**

### Phase 3: 工作流基础（P1）

| 任务 | 预估时间 | 依赖 |
|------|----------|------|
| Workflow 数据模型 | 0.5d | - |
| Workflow CRUD API | 0.5d | 数据模型 |
| 前端 ReactFlow 编辑器 | 2d | reactflow |
| 节点面板 + 配置面板 | 1d | - |
| 基础节点（Start/End/LLM） | 1d | - |

**Phase 3 总计：约 5 天**

### Phase 4: 工作流执行（P2）

| 任务 | 预估时间 | 依赖 |
|------|----------|------|
| 执行引擎框架 | 1d | - |
| LLM/Code/HTTP 节点执行器 | 2d | - |
| 条件/循环节点 | 1d | - |
| 执行 API + 调试流式 | 1d | - |
| 前端调试面板 | 1d | - |
| 执行历史 | 1d | - |

**Phase 4 总计：约 7 天**

### Phase 5: 高级特性（P3）

- 定时触发（Celery Beat）
- Webhook 触发
- 人工审核节点
- 并行节点
- Agent 公开发布
- 工作流版本管理

---

## 6. 与现有模块的关系

```
┌─────────────────────────────────────────────────────────────────┐
│                         中台应用层                               │
│  ┌─────────────┐     ┌─────────────────┐                       │
│  │   Agent     │◀───▶│    Workflow     │                       │
│  │  (智能助手)  │     │   (工作流编排)   │                       │
│  └──────┬──────┘     └────────┬────────┘                       │
│         │                     │                                 │
└─────────┼─────────────────────┼─────────────────────────────────┘
          │                     │
          ▼                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                       共享能力层                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │ ModelManager│  │ KnowledgeBase│  │ UsageTracker│             │
│  │ (LLM 调用)  │  │  (知识库/RAG) │  │  (用量追踪)  │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │   Tools     │  │  TeamModel  │  │    Team     │             │
│  │ (工具/MCP)  │  │  (团队模型)  │  │  (团队隔离)  │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
└─────────────────────────────────────────────────────────────────┘
```

---

## 7. 注意事项

### 7.1 团队隔离

- 所有 Agent/Workflow 必须关联 `team_id`
- API 查询时必须验证用户的团队成员身份
- 使用 `TeamModel` 时检查团队授权

### 7.2 用量追踪

- Agent 对话调用 `team_chat` / `team_chat_stream`
- Workflow 执行记录 token 使用量
- 配额超限时返回明确错误

### 7.3 流式响应

- 使用 SSE (Server-Sent Events) 格式
- 定义清晰的事件类型
- 处理连接中断和错误

### 7.4 错误处理

- 使用 `BusinessError` 统一错误格式
- 工作流执行失败记录 `error_node_id`
- 前端展示友好的错误信息

---

## 8. 实现说明

### 8.1 技术栈注意事项

#### 8.1.1 前端 UI 库

本项目使用 **shadcn/ui + base-ui** 组件库（非 radix-ui），有以下关键差异：

| 特性 | radix-ui | base-ui (本项目) |
|------|----------|------------------|
| `asChild` prop | ✅ 支持 | ❌ 不支持 |
| Trigger 包装 | 使用 `asChild` | 直接渲染，样式直接应用 |
| Composition | Slot 模式 | 直接子元素 |

**正确用法示例：**

```tsx
// ❌ 错误 - base-ui 不支持 asChild
<DropdownMenuTrigger asChild>
  <Button>打开菜单</Button>
</DropdownMenuTrigger>

// ✅ 正确 - 直接应用样式
<DropdownMenuTrigger className="flex items-center gap-2 px-3 py-2">
  打开菜单
</DropdownMenuTrigger>
```

#### 8.1.2 Slider 组件

`Slider` 的 `onValueChange` 回调参数类型为 `number | readonly number[]`：

```tsx
// ✅ 正确处理类型
<Slider
  value={[temperature]}
  onValueChange={(v) => setTemperature(Array.isArray(v) ? v[0] : v)}
/>
```

#### 8.1.3 ScrollArea 与 ref

`ScrollArea` 组件不直接支持 ref 转发，需要使用原生 `div`：

```tsx
// ❌ 不推荐
<ScrollArea ref={scrollRef}>

// ✅ 推荐
<div ref={scrollRef} className="overflow-auto">
```

### 8.2 后端 Pydantic 与 Tortoise ORM

#### 8.2.1 ForeignKey 验证问题

Tortoise ORM 的 ForeignKey 字段返回关联对象实例，不能直接传递给 Pydantic 模型验证：

```python
# ❌ 错误 - FK 字段验证失败
agent_out = AgentOut.model_validate(agent)

# ✅ 正确 - 手动构建字典
async def build_agent_out(agent: Agent) -> dict:
    model_obj = await agent.model if agent.model_id else None
    return {
        "id": agent.id,
        "name": agent.name,
        # ... 其他字段
        "model": {
            "name": model_obj.name,
            "provider": model_obj.provider,
            "model_id": model_obj.model_id,
        } if model_obj else None,
    }
```

---

## 9. 更新日志

| 日期 | 版本 | 更新内容 |
|------|------|----------|
| 2025-12-25 | 1.0 | 初始版本，定义 Agent 和 Workflow 设计规范 |
| 2025-01-19 | 1.1 | 更新前端路由结构，Agent 与 Workflow 统一到 `/app/apps` 下；新增三栏布局组件说明；添加实现说明章节 |
| 2025-12-30 | 1.2 | 新增子工作流节点设计；完善执行记录模型（NodeExecution 独立表）；新增执行日志系统设计；新增性能与并发优化章节（批量写入、Redis 原子计数、大数据分离存储、并发限制） |
