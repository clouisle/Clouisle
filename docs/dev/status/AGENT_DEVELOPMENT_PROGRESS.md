# Agent 模块开发进度

> 最后更新：2025-12-28

## 概述

本文档记录 Agent 模块的开发进度，包括已完成功能、技术实现细节和待办事项。

---

## 1. 已完成功能

### 1.1 通用 Chat 组件库

创建了一套可复用的 Chat 组件库，位于 `/frontend/components/chat/`，支持多种消息类型的展示。

#### 组件结构

```
frontend/components/chat/
├── index.ts                 # 统一导出
├── types.ts                 # 类型定义
├── chat.tsx                 # Chat 主组件（组合 Container + Input）
├── chat-container.tsx       # 消息容器（支持自动滚动）
├── chat-input.tsx           # 输入框组件（OpenAI 风格，支持 IME）
├── message.tsx              # 消息组件（集成 ChainOfThought）
├── variable-form.tsx        # 变量表单组件
└── message-parts/           # 消息部件
    ├── index.ts             # 部件导出
    ├── text-content.tsx     # 文本内容（Markdown、引用标记）
    ├── reasoning-content.tsx # 推理内容（思维链）
    ├── tool-content.tsx     # 工具调用内容
    ├── file-content.tsx     # 文件内容（图片预览）
    └── source-content.tsx   # 来源引用（支持文档聚合和分段弹窗）
```

### 1.2 AI 元素组件库

创建了通用的 AI 交互元素组件库，位于 `/frontend/components/ai-elements/`：

#### 组件结构

```
frontend/components/ai-elements/
├── index.ts                 # 统一导出
├── chain-of-thought.tsx     # 思维链组件（聚合 RAG/推理/生成步骤）
├── message.tsx              # 消息基础组件
├── shimmer.tsx              # 闪烁动画组件
└── tool.tsx                 # 工具调用组件
```

#### ChainOfThought 组件

聚合展示 AI 处理过程的各个步骤：

```tsx
import {
  ChainOfThought,
  ChainOfThoughtHeader,
  ChainOfThoughtContent,
  ChainOfThoughtStep,
} from '@/components/ai-elements/chain-of-thought'

<ChainOfThought isStreaming={isStreaming}>
  <ChainOfThoughtHeader title="思考过程" />
  <ChainOfThoughtContent>
    <ChainOfThoughtStep
      icon={SearchIcon}
      label="搜索知识库"
      status="complete"  // pending | active | complete | error
    />
    <ChainOfThoughtStep
      label="推理中..."
      status="active"
    >
      {/* 可选：展示推理内容 */}
      <div className="text-xs">推理内容...</div>
    </ChainOfThoughtStep>
    <ChainOfThoughtStep
      icon={SparklesIcon}
      label="生成回复"
      status="active"
    />
  </ChainOfThoughtContent>
</ChainOfThought>
```

**特性：**
- 自动折叠：流式结束后 3 秒自动折叠（`AUTO_CLOSE_DELAY = 3000`）
- 状态图标：pending（空心圆）、active（旋转加载）、complete（绿色勾）、error（红色）
- 响应式宽度：`w-full` 占满容器宽度

#### 支持的消息类型

| 类型 | Part Type | 用途 |
|------|-----------|------|
| 文本 | `text` | 普通对话内容，支持流式输出和引用标记 |
| 推理 | `reasoning` | Chain of Thought，展示模型思考过程 |
| 任务 | `task` | RAG 检索、生成等任务状态 |
| 工具调用 | `tool-call` / `tool-result` | 函数调用及返回结果 |
| MCP 工具 | `mcp-tool-call` / `mcp-tool-result` | Model Context Protocol 工具调用 |
| URL 来源 | `source-url` | 引用的网页链接 |
| 文档来源 | `source-document` | 引用的知识库文档（RAG），支持引用标记 |
| 文件 | `file` | 上传的文件或图片 |

#### 类型定义

```typescript
// 消息角色
type MessageRole = 'user' | 'assistant' | 'system'

// 消息结构
interface ChatMessage {
  id: string
  role: MessageRole
  parts: MessagePart[]     // 支持多部件组合
  createdAt?: Date
  metadata?: Record<string, unknown>
}

// 任务部件（RAG、生成等）
interface TaskPart {
  type: 'task'
  taskType: 'rag' | 'generating'
  state: 'pending' | 'running' | 'completed' | 'error'
  info?: string | number  // 附加信息，如检索到的来源数量
}

// 推理部件
interface ReasoningPart {
  type: 'reasoning'
  text: string
  state: 'streaming' | 'complete'
  duration?: number  // 毫秒
}

// 文档来源部件（支持引用）
interface SourceDocumentPart {
  type: 'source-document'
  documentId?: string
  documentName?: string
  content: string
  metadata?: {
    score?: number        // 相关度分数
    page?: number
    chunkIndex?: number
  }
}
```

### 1.3 后端 SSE 事件流

实现了完整的 Server-Sent Events 流式响应，用于 Agent 对话：

#### SSE 事件类型

| 事件 | 数据 | 说明 |
|------|------|------|
| `message_start` | `{conversation_id, message_id}` | 消息开始 |
| `rag_start` | `{}` | RAG 检索开始 |
| `rag_context` | `{documents: [{id, name, content, score}]}` | RAG 检索结果 |
| `reasoning_start` | `{}` | 推理开始 |
| `reasoning_delta` | `{delta: string}` | 推理内容增量 |
| `reasoning_end` | `{duration: number}` | 推理结束，含耗时（毫秒） |
| `content_delta` | `{delta: string}` | 回复内容增量 |
| `message_end` | `{usage: {...}, task_state: {...}}` | 消息结束 |
| `error` | `{code, message}` | 错误 |

#### 后端事件发送示例

```python
# backend/app/api/v1/endpoints/chat.py

# RAG 开始
yield create_sse_event("rag_start", {})

# RAG 结果
yield create_sse_event("rag_context", {
    "documents": [
        {
            "id": doc.document_id,
            "name": doc.document_name,
            "content": doc.content,
            "score": doc.metadata.get("score"),
        }
        for doc in rag_results
    ]
})

# 推理过程
yield create_sse_event("reasoning_start", {})
async for chunk in reasoning_stream:
    yield create_sse_event("reasoning_delta", {"delta": chunk})
yield create_sse_event("reasoning_end", {"duration": duration_ms})

# 内容生成
async for chunk in content_stream:
    yield create_sse_event("content_delta", {"delta": chunk})

# 消息结束
yield create_sse_event("message_end", {
    "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    "task_state": {"rag": "completed", "generating": "completed", "ragSourceCount": 3}
})
```

### 1.4 前端 useChat Hook

实现了完整的 Chat 状态管理 Hook：

```typescript
// frontend/hooks/use-chat.ts

interface TaskState {
  rag?: 'pending' | 'running' | 'completed'
  generating?: 'pending' | 'running' | 'completed'
  ragSourceCount?: number
}

const { messages, status, error, isLoading, isStreaming, sendMessage, stop, reset } = useChat({
  agentId: 'xxx',
  variables: { name: 'User' },
  onError: (err) => console.error(err),
})
```

**特性：**
- 自动处理 SSE 事件流
- TaskState 跟踪 RAG/生成状态
- 支持流式中断（AbortController）
- 消息持久化（taskState 在流结束后保留）

### 1.5 OpenAI 风格 UI 设计

参考 OpenAI ChatGPT 官网，实现了以下 UI 特性：

#### 消息布局
- **用户消息**：右对齐，灰色圆角气泡 (`bg-muted rounded-3xl`)
- **助手消息**：左对齐，无背景色，直接展示内容
- **无头像显示**：简洁设计，不显示用户/助手头像
- **无分割线**：消息之间无 `border` 分隔

#### 输入框样式
- **药丸形状**：`rounded-full` 圆角设计
- **悬浮布局**：无顶部边框，独立于消息区域
- **IME 支持**：正确处理中文输入法组合状态，避免回车误触发
- **按钮设计**：
  - 左侧 `+` 按钮：附加文件
  - 右侧 `↑` 按钮：发送消息（黑色圆形背景）
  - 流式时显示停止按钮

#### 整体布局
```
┌────────────────────────────────────────┐
│           消息区域 (可滚动)              │
│  ┌──────────────────────────────────┐  │
│  │                     用户消息 ─┐ │  │
│  │                    [灰色气泡] │ │  │
│  │                               └─┘  │
│  │                                    │
│  │  ┌─ 思考过程 ──────────────────┐   │
│  │  │ ✓ 搜索知识库 (3个来源)      │   │
│  │  │ ✓ 推理中... (3秒)          │   │
│  │  │ ● 生成回复                  │   │
│  │  └────────────────────────────┘   │
│  │                                    │
│  │  助手回复内容 [1] 带引用标记       │
│  │                                    │
│  │  已使用 1 个来源 ▼                 │
│  │    📄 文档名称                     │
│  └──────────────────────────────────┘  │
├────────────────────────────────────────┤
│  ┌────────────────────────────────┐    │
│  │ [+] 输入消息...              [↑] │   │
│  └────────────────────────────────┘    │
└────────────────────────────────────────┘
```

### 1.6 来源内容展示

实现了文档来源的聚合展示和详情弹窗：

#### 功能特性
- **文档聚合**：相同文档的多个片段聚合显示，避免重复
- **片段计数**：显示每个文档的片段数量
- **点击查看**：点击文档打开弹窗查看所有分段
- **可折叠分段**：弹窗中每个分段可折叠，显示预览和相关度
- **弹窗宽度**：80vw 宽度，适合阅读长内容

```tsx
// frontend/components/chat/message-parts/source-content.tsx

// 分段项组件 - 支持折叠
function SegmentItem({ segment, index }) {
  const [isOpen, setIsOpen] = useState(false);
  
  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <CollapsibleTrigger>
        <div>
          片段 {index + 1}  相关度 {score}%
          {!isOpen && <div>预览内容...</div>}
        </div>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div>{segment.content}</div>
      </CollapsibleContent>
    </Collapsible>
  );
}
```

### 1.7 引用标记系统

实现了文本中的引用标记展示：

- **标记格式**：`[[cite:N]]`，N 为引用序号
- **渲染方式**：使用 MutationObserver 监听 Streamdown 渲染，替换为 React Portal
- **Tooltip 展示**：悬停显示引用的文档名称和内容摘要

```tsx
// 引用标记渲染
<CitationBadge index={1} source={documentSource} />
// 显示为：[1] 带 Tooltip
```

### 1.8 国际化 (i18n)

使用 `next-intl` 实现多语言支持，添加了 `chat.*` 命名空间。

#### 翻译键结构

```json
{
  "chat": {
    "reasoning": {
      "thinking": "思考中",
      "thoughtFor": "思考了 {seconds} 秒",
      "thought": "思考过程",
      "processing": "推理中..."
    },
    "task": {
      "searchingKnowledge": "搜索知识库...",
      "foundSources": "找到 {count} 个来源",
      "generating": "生成回复..."
    },
    "tool": {
      "running": "执行中...",
      "error": "执行失败",
      "completed": "已完成",
      "pending": "等待执行",
      "input": "输入",
      "output": "输出",
      "mcp": "MCP 工具"
    },
    "source": {
      "sources": "参考来源",
      "usedSources": "已使用 {count} 个来源",
      "document": "文档",
      "url": "链接",
      "segment": "片段 {index}",
      "segmentCount": "{count} 个片段",
      "relevance": "相关度 {score}%"
    },
    "variables": {
      "title": "变量",
      "fillRequired": "请填写必填变量"
    },
    "input": {
      "placeholder": "输入消息...",
      "send": "发送",
      "stop": "停止",
      "attachFile": "附加文件",
      "maxFilesReached": "最多只能上传 {max} 个文件"
    },
    "message": {
      "copy": "复制",
      "copied": "已复制",
      "thinking": "思考中...",
      "user": "用户",
      "assistant": "助手"
    }
  }
}
```

### 1.9 Agent 预览面板集成

将 Chat 组件集成到 Agent 编排页面的预览面板：

**文件位置**：`/frontend/app/(platform)/app/apps/[id]/_components/agent-preview-panel.tsx`

#### 功能特性
- 实时对话测试
- 模拟助手响应（含推理过程展示）
- 重置对话
- 流式输出支持（UI 准备就绪）

---

## 2. 技术实现细节

### 2.1 ChatContainer 滚动处理

使用 `scrollTop` 替代 `scrollIntoView` 避免页面被撑高：

```tsx
// ❌ 会导致外部页面滚动
bottomRef.current.scrollIntoView({ behavior: 'smooth' });

// ✅ 只滚动容器内部
containerRef.current.scrollTop = containerRef.current.scrollHeight;
```

### 2.2 IME 输入法组合状态处理

防止中文输入法输入时回车误触发发送：

```tsx
const [isComposing, setIsComposing] = useState(false);

const handleKeyDown = (e: KeyboardEvent) => {
  // 忽略 IME 组合状态下的回车
  if (e.key === 'Enter' && !e.shiftKey && !isComposing) {
    e.preventDefault();
    handleSubmit();
  }
};

<Textarea
  onKeyDown={handleKeyDown}
  onCompositionStart={() => setIsComposing(true)}
  onCompositionEnd={() => setIsComposing(false)}
/>
```

### 2.3 Base-UI Tooltip 注意事项

本项目使用 base-ui（非 radix-ui），Tooltip 组件**不支持 `asChild` prop**，需使用 `render` prop：

```tsx
// ❌ 错误 - base-ui 不支持 asChild
<TooltipTrigger asChild>
  <Button>触发器</Button>
</TooltipTrigger>

// ✅ 正确 - 使用 render prop
<TooltipTrigger
  render={
    <button className="...">
      触发器
    </button>
  }
/>
```

### 2.4 Collapsible 组件使用

用于可折叠内容（推理过程、工具调用详情）：

```tsx
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'

<Collapsible open={isOpen} onOpenChange={setIsOpen}>
  <CollapsibleTrigger>
    点击展开
  </CollapsibleTrigger>
  <CollapsibleContent>
    折叠内容
  </CollapsibleContent>
</Collapsible>
```

### 2.5 流式光标动画

文本流式输出时的光标动画：

```tsx
// CSS 动画定义（需添加到 globals.css）
@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

.animate-blink {
  animation: blink 1s step-end infinite;
}

// 使用
{isStreaming && (
  <span className="inline-block w-0.5 h-4 ml-0.5 bg-current animate-blink" />
)}
```

### 2.6 消息部件类型守卫

使用类型守卫区分不同消息部件：

```typescript
// 类型守卫函数
export function isTextPart(part: MessagePart): part is TextPart {
  return part.type === 'text'
}

export function isReasoningPart(part: MessagePart): part is ReasoningPart {
  return part.type === 'reasoning'
}

// 使用
if (isTextPart(part)) {
  return <TextContent part={part} />
}
if (isReasoningPart(part)) {
  return <ReasoningContent part={part} />
}
```

### 2.7 Dialog 宽度覆盖

base-ui 的 DialogContent 有默认 `sm:max-w-md`，需要用 `!important` 覆盖：

```tsx
// DialogContent 默认样式包含 sm:max-w-md
// 需要使用 ! 强制覆盖
<DialogContent className="w-[80vw] !max-w-[80vw]">
```

---

## 3. 文件附件功能

ChatInput 组件支持文件上传：

```typescript
interface ChatInputFile {
  id: string
  name: string
  size: number
  type: string
  file: File
  previewUrl?: string  // 图片预览
}

// 配置
<ChatInput
  allowAttachments={true}
  acceptedFileTypes="image/*,.pdf,.doc,.docx,.txt,.md"
  maxFiles={5}
  onSubmit={(message, files) => {
    // 处理消息和文件
  }}
/>
```

---

## 4. 待完成功能

### 4.1 短期 (P0)

- [x] **流式响应**：实现 SSE 流式消息接收 ✅
- [x] **RAG 来源展示**：展示知识库检索结果来源 ✅
- [x] **ChainOfThought**：聚合展示处理步骤 ✅
- [x] **MCP 工具支持**：对接 MCP Server ✅
- [x] **内置工具**：计算器、时间工具 ✅
- [x] **消息版本管理**：支持消息重新生成 ✅
- [x] **消息复制**：复制助手消息内容 ✅
- [ ] **错误处理**：网络错误、超时、配额超限等

### 4.2 中期 (P1)

- [x] **工具调用集成**：对接实际工具执行 ✅
- [x] **历史消息加载**：加载历史对话 ✅
- [x] **消息重试**：重新生成助手回复 ✅
- [ ] **对话管理**：对话列表、删除、重命名

### 4.3 长期 (P2)

- [x] **Markdown 代码块高亮**：Streamdown 内置 Shiki 高亮 ✅
- [x] **LaTeX 公式渲染**：Streamdown 内置 KaTeX 渲染 ✅
- [x] **图片预览**：点击查看大图（ImageLightbox 组件）✅
- [ ] **语音输入**：语音转文字
- [ ] **多模态支持**：图片理解

---

## 5. 后端架构

### 5.1 LLM 工具系统

```
backend/app/llm/tools/
├── __init__.py              # 导出 tool_registry
├── registry.py              # 工具注册表（统一执行接口）
├── types.py                 # 工具类型定义
├── executors.py             # 共享执行器（HTTP 工具）
├── mcp_client.py            # MCP 客户端（stdio/sse 传输）
├── sandbox.py               # 代码沙箱执行
└── builtin/                 # 内置工具
    ├── __init__.py
    ├── calculator.py        # 计算器（数学表达式、单位换算）
    └── time.py              # 时间工具（当前时间、时区转换）
```

### 5.2 工具注册表 (registry.py)

```python
from app.llm.tools import tool_registry

# 获取所有内置工具定义
tools = tool_registry.list_tools()

# 执行工具
result = await tool_registry.execute("calculator", {"expression": "2+2"})
```

### 5.3 MCP 客户端 (mcp_client.py)

支持两种传输方式：

```python
# stdio 传输（本地进程）
mcp_config = {
    "transport": "stdio",
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem"],
    "env": {"HOME": "/Users/xxx"}
}

# sse 传输（远程服务）
mcp_config = {
    "transport": "sse",
    "url": "http://localhost:3000/sse"
}

# 获取工具列表
tools = await get_mcp_tools(mcp_config)

# 执行工具
result = await execute_mcp_tool(mcp_config, "read_file", {"path": "/tmp/test.txt"})
```

### 5.4 Token 计数 (token_counter.py)

使用 tiktoken 进行准确的 token 计数：

```python
from app.llm.token_counter import count_tokens

# 自动选择编码器
tokens = count_tokens("Hello, world!", model_id="gpt-4o", provider="openai")

# 支持的模型映射
# - OpenAI: gpt-4o, gpt-4, gpt-3.5-turbo -> cl100k_base
# - Claude: claude-3-* -> cl100k_base (近似)
# - Gemini: gemini-* -> cl100k_base (近似)
```

### 5.5 消息版本管理

数据库字段：

```python
class Message(models.Model):
    # 版本支持
    parent_id = fields.UUIDField(null=True)      # 父消息 ID（版本组根）
    is_active = fields.BooleanField(default=True) # 当前激活版本
    version_number = fields.IntField(default=1)   # 版本号
```

API 端点：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/messages/{id}/versions` | 获取所有版本 |
| POST | `/messages/{id}/switch-version` | 切换版本 |
| POST | `/messages/{id}/regenerate` | 重新生成（创建新版本） |

---

## 6. 相关文件

| 文件 | 说明 |
|------|------|
| `/frontend/components/chat/` | Chat 组件库目录 |
| `/frontend/components/ai-elements/` | AI 元素组件库目录 |
| `/frontend/hooks/use-chat.ts` | Chat 状态管理 Hook |
| `/frontend/messages/zh.json` | 中文翻译（chat.* 命名空间） |
| `/frontend/messages/en.json` | 英文翻译（chat.* 命名空间） |
| `/frontend/app/(platform)/app/apps/[id]/_components/agent-preview-panel.tsx` | Agent 预览面板 |
| `/backend/app/api/v1/endpoints/chat.py` | 后端对话 API（SSE 流式） |
| `/backend/app/schemas/agent.py` | Agent Schema（含 SSE 事件类型） |
| `/backend/app/llm/tools/` | LLM 工具系统 |
| `/backend/app/llm/tools/mcp_client.py` | MCP 客户端 |
| `/backend/app/llm/tools/registry.py` | 工具注册表 |
| `/backend/app/llm/tools/builtin/` | 内置工具 |
| `/backend/app/llm/token_counter.py` | Token 计数器 |
| `/docs/dev/design/app-platform/AGENT_WORKFLOW_SPEC.md` | Agent & Workflow 设计规范 |
| `/docs/dev/design/app-platform/TOOL_SYSTEM_SPEC.md` | 工具系统设计规范 |

---

## 7. 更新日志

| 日期 | 更新内容 |
|------|----------|
| 2025-12-26 | 创建 Chat 组件库：types, message, chat-container, chat-input |
| 2025-12-26 | 实现 OpenAI 风格 UI：药丸输入框、无头像、无分割线 |
| 2025-12-26 | 添加消息部件：text-content, reasoning-content, tool-content, source-content, file-content |
| 2025-12-26 | 添加 i18n 支持：chat.* 命名空间 |
| 2025-12-26 | 集成到 Agent 预览面板 |
| 2025-12-26 | 修复 i18n 参数名：thoughtFor 的 duration → seconds |
| 2025-12-27 | 创建 AI 元素组件库：chain-of-thought, shimmer |
| 2025-12-27 | 实现后端 SSE 事件流：rag_start, rag_context, reasoning_*, content_delta, message_end |
| 2025-12-27 | 实现前端 useChat Hook：SSE 解析、TaskState 跟踪 |
| 2025-12-27 | ChainOfThought 组件：聚合 RAG/推理/生成步骤，3秒自动折叠 |
| 2025-12-27 | SourceContent 组件：文档聚合、分段弹窗（80vw 宽度、可折叠） |
| 2025-12-27 | 引用标记系统：[[cite:N]] 渲染为 Tooltip 徽章 |
| 2025-12-27 | 修复页面高度溢出：scrollTop 替代 scrollIntoView |
| 2025-12-27 | 修复输入框 IME 问题：onCompositionStart/End 处理中文输入法 |
| 2025-12-28 | **MCP 工具支持**：实现 mcp_client.py，支持 stdio/sse 传输 |
| 2025-12-28 | **内置工具**：calculator.py（数学计算、单位换算）、time.py（时间、时区） |
| 2025-12-28 | **工具注册表**：registry.py 统一工具执行接口 |
| 2025-12-28 | **共享执行器**：executors.py 提取 HTTP 工具执行逻辑 |
| 2025-12-28 | **Token 计数**：token_counter.py 集成 tiktoken |
| 2025-12-28 | **消息版本管理**：parent_id, is_active, version_number 字段 |
| 2025-12-28 | **PR Review 修复**：N+1 查询优化、竞态条件修复、代码复用 |
| 2025-12-28 | **类型修复**：mypy 类型错误、TypeScript 构建错误、ESLint 错误 |
| 2025-12-29 | **Agent 功能完善**：消息复制、历史消息加载、代码高亮、LaTeX、图片预览 |
