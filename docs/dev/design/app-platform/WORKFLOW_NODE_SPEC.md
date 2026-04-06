# 工作流节点设计规范

本文档描述了 Clouisle 工作流编辑器中各类节点的设计规范、特点和 UI 风格指南。

## 目录

- [整体 UI 风格](#整体-ui-风格)
- [节点分类](#节点分类)
- [基础节点](#基础节点)
- [流程控制节点](#流程控制节点)
- [数据处理节点](#数据处理节点)
- [容器节点](#容器节点)
- [配置面板](#配置面板)

---

## 整体 UI 风格

### 设计原则

1. **现代简洁**：采用圆角卡片设计，边框清晰，层次分明
2. **交互友好**：悬停显示操作按钮，选中状态明显
3. **颜色编码**：不同类型节点使用不同主题色，便于快速识别
4. **响应式反馈**：拖拽、连接等操作有视觉反馈

### 视觉规范

| 属性 | 规范 |
|------|------|
| 卡片圆角 | `rounded-xl` (12px) |
| 边框 | 1px，默认 `border-border`，选中 `border-primary` |
| 阴影 | `shadow-sm` |
| 图标容器 | `rounded-lg` (8px)，尺寸 `h-7 w-7` |
| 图标大小 | 14px (`h-3.5 w-3.5`) |
| 节点最小宽度 | 180px (`min-w-[180px]`) |
| 节点最大宽度 | 240px (`max-w-[240px]`) |
| 内边距 | `px-2.5 py-2` |
| 元素间距 | `gap-2` |

### 节点卡片样式代码

```tsx
// 节点卡片容器
<div
  className={cn(
    'relative flex items-center gap-2 px-2.5 py-2 rounded-xl border bg-card shadow-sm transition-all',
    'min-w-[180px] max-w-[240px]',
    selected 
      ? 'border-primary' 
      : 'border-border hover:border-primary/50'
  )}
>
  {/* 内容 */}
</div>
```

### Handle（连接点）样式

**普通节点 Handle**：
- 尺寸：8px × 8px (`w-2 h-2`)
- 形状：圆形 (`rounded-full`)
- 颜色：主色 (`bg-primary`)
- 边框：无 (`border-0`)
- 悬停效果：放大 (`group-hover:scale-150`)

```tsx
// 输入 Handle（左侧）
<Handle
  type="target"
  position={Position.Left}
  className="w-2! h-2! rounded-full! bg-primary! border-0! transition-transform group-hover:scale-150"
/>

// 输出 Handle（右侧）
<Handle
  type="source"
  position={Position.Right}
  className="w-2! h-2! rounded-full! bg-primary! border-0! transition-transform group-hover:scale-150"
/>
```

**容器节点 Handle**：
- 尺寸：8px × 8px
- 形状：圆形
- 无边框

### 节点顶部标签

```tsx
// 节点标签行
<div className="flex items-center justify-between mb-2 px-1 h-5">
  <span className="text-xs text-muted-foreground">节点类型名称</span>
  <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity bg-muted rounded-lg px-1 py-0.5">
    <button className="p-1 rounded hover:bg-background" title="调试运行">
      <Play className="h-3 w-3 text-muted-foreground" />
    </button>
    <button className="p-1 rounded hover:bg-background">
      <MoreHorizontal className="h-3 w-3 text-muted-foreground" />
    </button>
  </div>
</div>
```

### 图标容器样式

```tsx
// 图标容器
<div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-{color}-500 text-white">
  <IconComponent className="h-3.5 w-3.5" />
</div>
```

### 节点内容区域

```tsx
// 单行标签
<span className="flex-1 text-sm font-medium truncate">
  {data.label || '节点名称'}
</span>

// 带副标题的内容
<div className="flex-1 min-w-0">
  <span className="block text-sm font-medium truncate">
    {data.label || '节点名称'}
  </span>
  {hasConfig ? (
    <span className="text-xs text-muted-foreground truncate block">{configName}</span>
  ) : (
    <span className="text-xs text-amber-500">未配置</span>
  )}
</div>
```

### 颜色系统

| 节点类型 | 主题色 | Tailwind 类 |
|---------|--------|-------------|
| 开始/用户输入 | Primary | `bg-primary` |
| 触发器 | 琥珀色 | `bg-amber-500` |
| LLM | 蓝色 | `bg-blue-500` |
| 条件分支 | 青色 | `bg-cyan-500` |
| 问题分类 | 紫罗兰 | `bg-violet-500` |
| 迭代/循环 | 青色 | `bg-cyan-500` |
| 子工作流 | 紫色 | `bg-purple-500` |
| 工具 | 翠绿色 | `bg-emerald-500` |
| 代码 | 蓝色 | `bg-blue-500` |
| 模板转换 | 蓝色 | `bg-blue-500` |
| 文件转URL | 青绿色 | `bg-teal-500` |
| 变量聚合器 | 紫罗兰 | `bg-violet-500` |
| 变量赋值 | 青绿色 | `bg-teal-500` |
| 参数提取器 | 琥珀色 | `bg-amber-500` |
| 输出 | 翠绿色 | `bg-emerald-500` |

---

## 节点分类

```
├── 基础节点
│   ├── 用户输入节点 (user_input)
│   ├── 触发器节点 (trigger)
│   ├── LLM 节点 (llm) ✅
│   ├── 工具节点 (tool) ✅
│   ├── 子工作流节点 (sub_workflow)
│   ├── 代码节点 (code) ✅
│   └── 输出节点 (answer) ✅
│
├── 数据处理节点
│   ├── 模板转换节点 (template) ✅
│   ├── 文件转URL节点 (file_to_url) ✅
│   ├── 变量聚合器节点 (variable_aggregator) ✅
│   ├── 变量赋值节点 (variable_assignment) ✅
│   └── 参数提取器节点 (parameter_extractor) ✅
│
├── 流程控制节点
│   ├── 条件分支节点 (condition) ✅
│   └── 问题分类节点 (question_classifier) ✅
│
└── 容器节点
    ├── 迭代节点 (iteration) ✅
    │   ├── 迭代开始节点 (iteration_start)
    │   └── 迭代退出节点 (iteration_exit)
    │
    └── 循环节点 (loop) ✅
        ├── 循环开始节点 (loop_start)
        └── 循环退出节点 (loop_exit)
```

---

## 基础节点

### 用户输入节点 (user_input)

**用途**：工作流的起始节点，定义用户输入参数

**视觉特点**：
- 图标：`Home` (lucide-react)
- 主题色：`bg-primary`
- 布局：垂直布局，显示参数列表
- 顶部标签：「开始」

**配置项**：
- 参数列表（可添加多个）
  - 参数名称（变量名，支持字母数字下划线）
  - 参数类型：text | paragraph | select | number | checkbox | array | object | file | image | files | images
  - 是否必填
  - 默认值（根据类型显示不同输入控件）
  - 描述
  - 选项列表（仅 select 类型）
- 系统参数（只读）
  - `sys.user_id` - 当前用户ID
  - `sys.app_id` - 应用ID
  - `sys.workflow_id` - 工作流ID
  - `sys.workflow_run_id` - 工作流运行ID
  - `sys.timestamp` - 当前时间戳

**输出变量**：
- 所有用户定义的参数作为变量供后续节点使用
- 格式：`{{参数名}}`

---

### 触发器节点 (trigger)

**用途**：事件驱动的工作流起始节点

**视觉特点**：
- 图标：`Zap` (lucide-react)
- 主题色：`bg-amber-500`
- 布局：与用户输入节点类似
- 顶部标签：「开始」

**配置项**：
- 同用户输入节点

---

### LLM 节点 (llm) ✅

**用途**：调用大语言模型进行文本生成

**视觉特点**：
- 图标：`Bot` (lucide-react)
- 主题色：`bg-blue-500`
- 布局：水平布局，图标+名称
- 顶部标签：「LLM」
- 圆角：`rounded-xl`
- 副标题：显示选中的模型名称

**配置项**：

```typescript
// 响应格式类型
type ResponseFormat = 'text' | 'json' | 'json_schema'

// 记忆模式类型
type MemoryMode = 'none' | 'window' | 'token_limit'

// LLM 节点配置
interface LLMNodeConfigData {
  // 模型配置
  modelId?: string            // 团队模型授权 ID（从团队模型 API 获取）
  modelName?: string          // 模型名称（显示用）
  
  // 提示词配置（支持变量补全，显示为带样式的标签）
  systemPrompt?: string       // 系统提示词
  userPrompt?: string         // 用户提示词
  
  // 模型参数
  temperature?: number        // 温度 0-2，默认 0.7
  topP?: number              // Top P 0-1，默认 1
  maxTokens?: number         // 最大输出 token 数
  
  // 响应格式
  responseFormat?: ResponseFormat  // text | json | json_schema
  jsonSchema?: string        // JSON Schema（当 responseFormat 为 json_schema 时）
  
  // 记忆/上下文配置
  memoryConfig?: {
    enabled: boolean
    mode: MemoryMode         // none | window | token_limit
    windowSize?: number      // 窗口模式：消息轮次
    tokenLimit?: number      // Token 限制模式：最大 token 数
  }
  
  // 多模态配置（仅当模型支持 vision 时显示）
  visionConfig?: {
    enabled: boolean
    imageVariable?: string   // 图片变量引用
    imagePosition?: 'before' | 'after'  // 图片位置：消息前/后
  }
  
  // 输出变量配置（三个独立的输出变量）
  outputVariables?: {
    response?: string        // 模型回复，默认 'response'，类型 String
    reasoning?: string       // 推理过程，默认 'reasoning'，类型 String
    usage?: string           // 用量统计（总 token 数），默认 'usage'，类型 Number
  }
  
  // 高级选项
  streaming?: boolean        // 是否流式输出，默认 true
  timeout?: number           // 超时时间（秒），默认 60
}
```

**提示词编辑器特性**：
- 使用 `contenteditable` 实现，支持光标精确定位
- 输入 `{{` 触发变量补全菜单
- 变量显示为带样式的标签：`[节点名 / 变量名]`
- 标签不可编辑，仅可整体删除

**输出变量**：
| 变量名 | 类型 | 说明 |
|--------|------|------|
| `response` | String | 模型的文本回复 |
| `reasoning` | String | 模型的推理过程（如有） |
| `usage` | Number | 本次调用的总 token 数 |

---

### 工具节点 (tool) ✅

**用途**：调用外部工具或 API，支持内置工具、自定义工具、MCP 工具

**视觉特点**：
- 图标：`Wrench` (lucide-react) 或工具自定义图标
- 主题色：`bg-emerald-500`（内置/自定义），`bg-violet-500`（MCP）
- 布局：卡片式，显示工具名称和参数状态
- 顶部标签：「工具」
- 右上角：类型徽章（内置/自定义/MCP）

**配置项**：

```typescript
// 工具类型
type ToolType = 'builtin' | 'custom' | 'mcp'

// 工具分类
type ToolCategory = 'time' | 'math' | 'search' | 'web' | 'file' | 'code' | 'api' | 'data' | 'other'

// 参数映射
interface ParameterMapping {
  name: string
  type: string
  required: boolean
  description?: string
  source: 'variable' | 'constant'  // 来源：变量引用或常量值
  variableRef?: string             // 变量引用
  variableRefNodeLabel?: string    // 来源节点标签
  constantValue?: string           // 常量值
}

// 工具节点配置
interface ToolNodeConfig {
  toolId?: string              // 工具 ID
  toolName?: string            // 工具名称
  toolType: ToolType           // 工具类型
  toolDisplayName?: string     // 显示名称
  toolDescription?: string     // 工具描述
  toolIcon?: string            // 图标（emoji）
  toolCategory?: ToolCategory  // 工具分类
  
  // MCP 特有配置
  mcpToolName?: string         // MCP 服务器中的具体工具名
  mcpToolDescription?: string  // MCP 工具描述
  
  parameterMappings: ParameterMapping[]  // 参数映射列表
  outputVariable: string       // 输出变量名，默认 'result'
}
```

**工具类型说明**：
| 类型 | 说明 | 颜色 |
|------|------|------|
| `builtin` | 系统内置工具 | 翠绿色 |
| `custom` | 用户自定义工具 | 琥珀色 |
| `mcp` | MCP 协议工具（需先选服务器再选工具） | 紫罗兰 |

**输出变量**：
- 用户定义的输出变量名（默认 `result`）
- 类型为 `Any`，根据工具返回动态决定

---

### 子工作流节点 (sub_workflow)

**用途**：调用其他工作流作为子流程

**视觉特点**：
- 图标：`Workflow` (lucide-react)
- 主题色：`bg-purple-500`
- 布局：水平布局
- 顶部标签：「子工作流」

**配置项**（规划中）：
- 工作流选择
- 输入参数映射
- 输出结果映射

---

### 代码节点 (code) ✅

**用途**：执行自定义代码逻辑，支持 Python 和 JavaScript

**视觉特点**：
- 图标：`Code` (lucide-react)
- 主题色：`bg-blue-500`
- 布局：垂直布局，支持异常分支时显示额外行
- 顶部标签：「代码执行」
- 特殊：启用异常分支时右侧有两个 Handle（正常/异常）

**配置项**：

```typescript
// 代码语言
type CodeLanguage = 'python' | 'javascript'

// 输出变量类型
type OutputVariableType = 'string' | 'number' | 'boolean' | 'array' | 'object'

// 异常处理类型
type ErrorHandlingType = 'none' | 'default_value' | 'error_branch'

// 代码输入变量
interface CodeInput {
  id: string
  name: string           // 变量名（在代码中使用）
  value: string          // 变量值（引用上游变量，如 {{query}}）
  valueSource?: string   // 变量来源节点
}

// 代码输出变量
interface CodeOutputVariable {
  id: string
  name: string           // 变量名
  type: OutputVariableType  // 变量类型
}

// 重试配置
interface RetryConfig {
  enabled: boolean       // 是否启用重试
  maxRetries: number     // 最大重试次数
  retryInterval: number  // 重试间隔（毫秒）
}

// 异常处理配置
interface ErrorHandlingConfig {
  type: ErrorHandlingType
  defaultValue?: string  // 当 type 为 default_value 时使用
}

// 代码节点配置
interface CodeConfig {
  language: CodeLanguage
  code: string
  inputs: CodeInput[]
  outputs: CodeOutputVariable[]
  outputVariable: string
  retry: RetryConfig
  errorHandling: ErrorHandlingConfig
}
```

**代码模板**：

Python:
```python
def main(inputs: dict) -> dict:
    # inputs 包含所有输入变量
    # 返回一个字典作为输出
    result = inputs.get("input", "")
    return {"output": result}
```

JavaScript:
```javascript
function main(inputs) {
    // inputs 包含所有输入变量
    // 返回一个对象作为输出
    const result = inputs.input || "";
    return { output: result };
}
```

**异常处理模式**：
| 模式 | 说明 |
|------|------|
| `none` | 不处理，直接抛出异常终止工作流 |
| `default_value` | 返回默认值，继续执行 |
| `error_branch` | 走异常分支（节点显示两个输出 Handle） |

**输出变量**：
- 用户定义的输出变量列表
- 格式：`{{节点名.变量名}}`

---

### 输出节点 (answer) ✅

**用途**：定义工作流的最终输出结果，支持流式输出

**视觉特点**：
- 图标：`MessageSquareText` (lucide-react)
- 主题色：`bg-emerald-500`
- 布局：卡片式，显示输出变量列表
- 顶部标签：「输出」
- 副标题：启用流式时显示「流式输出」
- 只有输入 Handle，无输出 Handle

**配置项**：

```typescript
// 输出变量类型
type OutputVariableType = 'string' | 'number' | 'boolean' | 'array' | 'object' | 'file' | 'any'

// 输出变量定义
interface OutputVariable {
  id: string
  name: string               // 输出变量名（外部 API 可见）
  sourceVariable: string     // 源变量引用（如 {{node.var}}）
  sourceNodeLabel?: string   // 源节点标签（用于显示）
  type: OutputVariableType   // 输出类型
  description?: string       // 变量描述
}

// 输出节点配置
interface AnswerNodeConfig {
  // 输出变量列表
  outputs: OutputVariable[]
  
  // 流式输出配置
  streaming: {
    enabled: boolean         // 是否启用流式输出
    variable?: string        // 流式输出的变量（通常是 LLM 的 response）
  }
}
```

**流式输出**：
- 用于 LLM 场景，实时返回生成内容
- 只能选择 String 类型的输出变量作为流式输出源

**输出变量**：
- 所有定义的输出变量将作为工作流的最终输出
- 外部调用工作流时可获取这些输出

---

## 流程控制节点

### 条件分支节点 (condition) ✅

**用途**：根据条件判断执行不同分支

**视觉特点**：
- 图标：`GitBranch` (lucide-react)
- 主题色：`bg-cyan-500`
- 布局：主卡片 + 分支出口列表
- 顶部标签：「条件」
- 特殊：右侧显示多个分支出口，每个分支有独立的 Handle

**分支类型**：
- `IF` - 首个条件分支
- `ELSE IF` - 额外条件分支（可添加多个）
- `ELSE` - 默认分支

**配置项**：

```typescript
interface ConditionRule {
  id: string
  variable: string        // 变量名，如 {{query}}
  variableSource?: string // 变量来源节点
  operator: ConditionOperator
  value: string           // 比较值
}

interface ConditionBranch {
  id: string
  type: 'if' | 'else_if' | 'else'
  name: string
  conditions: ConditionRule[]
  logicOperator: 'and' | 'or'
}
```

**支持的操作符**：
| 操作符 | 名称 | 说明 |
|--------|------|------|
| `equals` | 等于 | 精确匹配 |
| `not_equals` | 不等于 | 不匹配 |
| `contains` | 包含 | 字符串包含 |
| `not_contains` | 不包含 | 字符串不包含 |
| `starts_with` | 开头是 | 以指定字符串开头 |
| `ends_with` | 结尾是 | 以指定字符串结尾 |
| `is_empty` | 为空 | 值为空（无需比较值） |
| `is_not_empty` | 不为空 | 值不为空（无需比较值） |
| `greater_than` | 大于 | 数值比较 |
| `less_than` | 小于 | 数值比较 |
| `greater_or_equal` | 大于等于 | 数值比较 |
| `less_or_equal` | 小于等于 | 数值比较 |

**多条件逻辑**：
- `AND` - 所有条件都满足
- `OR` - 任一条件满足

---

### 问题分类节点 (question_classifier) ✅

**用途**：使用 LLM 对问题进行智能分类，根据分类结果走不同分支

**视觉特点**：
- 图标：`Tags` (lucide-react)
- 主题色：`bg-violet-500`
- 布局：卡片式，显示类别列表
- 顶部标签：「问题分类」
- 副标题：显示选中的模型名称
- 特殊：每个类别对应一个输出 Handle（分支）

**配置项**：

```typescript
// 分类类别定义
interface ClassifierCategory {
  id: string
  name: string           // 类别名称（作为输出分支标识）
  description: string    // 类别描述（帮助 LLM 理解分类标准）
}

// 问题分类器配置
interface QuestionClassifierConfig {
  // 源变量（问题文本，必须为 String 类型）
  sourceVariable: string
  sourceNodeLabel?: string
  
  // 模型配置（从团队模型 API 获取）
  modelId?: string
  modelName?: string
  
  // 分类指令（可选，提供额外的分类规则说明）
  instruction?: string
  
  // 类别列表（每个类别是一个输出分支）
  categories: ClassifierCategory[]
}
```

**工作原理**：
1. 接收 String 类型的问题变量
2. 使用 LLM 分析问题内容
3. 根据类别描述，选择最匹配的类别
4. 执行对应类别的输出分支

**输出变量**：
- 无传统输出变量
- 每个类别作为独立的输出分支（Handle）

**视觉特点**：
- 图标：`FileText` (lucide-react)
- 主题色：`bg-blue-500`
- 布局：水平布局，图标+名称
- 顶部标签：「模板转换」

**配置项**：

```typescript
// 模板输入变量
interface TemplateInput {
  id: string
  name: string           // 变量名（在模板中使用，如 arg1）
  value: string          // 变量值（引用上游变量，如 {{query}}）
  valueSource?: string   // 变量来源节点
}

// 模板转换配置
interface TemplateConfig {
  inputs: TemplateInput[]   // 输入变量列表
  template: string          // Jinja2 模板内容
  outputVariable: string    // 输出变量名（固定为 output）
  outputDescription: string // 输出描述
}
```

**模板语法**：
- 变量插入：`{{ arg1 }}`
- 条件判断：`{% if condition %}...{% endif %}`
- 循环：`{% for item in items %}...{% endfor %}`

**输出变量**：
- `output` - 模板渲染后的字符串

---

## 数据处理节点

### 模板转换节点 (template) ✅

**用途**：使用 Jinja2 模板语法转换和拼接数据

**视觉特点**：
- 图标：`FileText` (lucide-react)
- 主题色：`bg-blue-500`
- 布局：水平布局，图标+名称
- 顶部标签：「模板转换」

**配置项**：

```typescript
// 模板输入变量
interface TemplateInput {
  id: string
  name: string           // 变量名（在模板中使用，如 arg1）
  value: string          // 变量值（引用上游变量，如 {{query}}）
  valueSource?: string   // 变量来源节点
}

// 模板转换配置
interface TemplateConfig {
  inputs: TemplateInput[]   // 输入变量列表
  template: string          // Jinja2 模板内容
  outputVariable: string    // 输出变量名（默认 output）
  outputDescription: string // 输出描述
}
```

**模板语法**：
- 变量插入：`{{ arg1 }}`
- 条件判断：`{% if condition %}...{% endif %}`
- 循环：`{% for item in items %}...{% endfor %}`

**输出变量**：
- `output` - 模板渲染后的字符串

---

### 文件转URL节点 (file_to_url) ✅

**用途**：将文件/图片变量转换为可访问的 URL

**视觉特点**：
- 图标：`Link` (lucide-react)
- 主题色：`bg-teal-500`
- 布局：水平布局，图标+名称+输入数量
- 顶部标签：「文件转URL」

**配置项**：

```typescript
// 文件转URL输入配置
interface FileToUrlInput {
  id: string
  name: string                // 输出变量名
  sourceVariable: string      // 源文件变量引用（如 {{start.image}}）
  sourceType: 'file' | 'image' | 'files' | 'images'  // 源类型
}

// 文件转URL节点配置
interface FileToUrlConfig {
  inputs: FileToUrlInput[]    // 输入列表（支持多个文件变量）
  ensureAbsolute: boolean     // 是否确保绝对URL
}
```

**输出变量**：
- 每个 input 对应一个输出变量
- 单文件输出 String 类型
- 多文件输出 Array 类型

---

### 变量聚合器节点 (variable_aggregator) ✅

**用途**：将多个变量聚合为一个结构化数据

**视觉特点**：
- 图标：`Combine` (lucide-react)
- 主题色：`bg-violet-500`
- 布局：卡片式，显示模式徽章和变量列表预览
- 顶部标签：「变量聚合器」
- 模式徽章：右上角显示当前聚合模式图标和名称

**聚合模式**：

| 模式 | 图标 | 说明 | 输出类型 |
|------|------|------|----------|
| `object` | `Braces` | 将变量聚合为对象 `{ key: value }` | Object |
| `array` | `List` | 将变量聚合为数组 `[item1, item2]` | Array |
| `concat` | `Link` | 将字符串变量拼接 | String |
| `merge` | `Merge` | 深度合并多个对象 | Object |

**配置项**：

```typescript
// 聚合模式
type AggregationMode = 'object' | 'array' | 'concat' | 'merge'

// 变量映射项
interface VariableMapping {
  id: string
  sourceVariable: string      // 源变量，如 {{node1.output}}
  sourceNodeLabel?: string    // 源节点名称（用于显示）
  targetKey?: string          // 目标键名（object 模式下使用）
}

// 聚合器配置
interface VariableAggregatorConfig {
  mode: AggregationMode
  variables: VariableMapping[]
  outputVariable: string
  separator?: string           // concat 模式分隔符
  mergeStrategy?: 'shallow' | 'deep'  // merge 模式合并策略
}
```

**输出变量**：
- 用户定义的输出变量名（默认 `result`）
- 类型根据聚合模式决定

---

### 变量赋值节点 (variable_assignment) ✅

**用途**：修改对话变量的值，支持覆盖、清空、设置操作

**视觉特点**：
- 图标：`Variable` (lucide-react)
- 主题色：`bg-teal-500`
- 布局：卡片式，显示赋值项列表预览
- 顶部标签：「变量赋值」
- 右上角显示赋值项数量徽章

**操作类型**：

| 操作 | 符号 | 说明 |
|------|------|------|
| `overwrite` | ← | 用另一个变量的值覆盖目标变量 |
| `clear` | ∅ | 将目标变量清空（重置为空值） |
| `set` | = | 将目标变量设置为指定的常量值 |

**配置项**：

```typescript
// 赋值操作类型
type AssignmentOperation = 'overwrite' | 'clear' | 'set'

// 单个赋值项
interface AssignmentItem {
  id: string
  targetVariable: string           // 目标对话变量名
  targetVariableLabel?: string     // 目标变量显示名
  operation: AssignmentOperation
  variableRef?: string             // 变量引用（overwrite 使用）
  variableRefNodeLabel?: string    // 来源节点标签
  constantValue?: string           // 常量值（set 使用）
}

// 变量赋值配置
interface VariableAssignmentConfig {
  assignments: AssignmentItem[]
}
```

**使用场景**：
- 更新对话上下文中的状态变量
- 累积循环中的结果
- 清空临时变量

---

### 参数提取器节点 (parameter_extractor) ✅

**用途**：从文本中提取结构化参数，支持 LLM 智能提取、正则表达式、JSON Path

**视觉特点**：
- 图标：`Braces` (lucide-react)
- 主题色：`bg-amber-500`
- 布局：卡片式，显示提取方式徽章和参数列表预览
- 顶部标签：「参数提取器」
- 方式徽章：右上角显示当前提取方式（LLM/正则/JSON）

**提取方式**：

| 方式 | 图标 | 说明 | 支持的参数类型 | 源变量类型 |
|------|------|------|---------------|-----------|
| `llm` | `Bot` | 使用大语言模型理解语义，智能提取 | string, number, boolean, array, object | String |
| `regex` | `Code` | 使用正则表达式匹配提取 | string, number | String |
| `json_path` | `FileJson` | 从 JSON 字符串按路径提取 | string, number, boolean, array, object | String |

**配置项**：

```typescript
// 提取方式
type ExtractionMethod = 'llm' | 'regex' | 'json_path'

// 参数类型
type ExtractedParamType = 'string' | 'number' | 'boolean' | 'array' | 'object'

// 参数定义
interface ExtractedParameter {
  id: string
  name: string                   // 参数名（作为输出变量名）
  type: ExtractedParamType       // 参数类型
  description: string            // 参数描述（LLM 模式用于理解语义）
  required: boolean              // 是否必填
  
  // 不同提取方式的配置
  pattern?: string               // 正则表达式（regex 模式）
  jsonPath?: string              // JSON Path 表达式（json_path 模式）
  defaultValue?: string          // 默认值（提取失败时使用）
  
  // LLM JSON Schema 扩展字段
  enum?: string[]                // 枚举值（限制可选值）
  arrayItemType?: ExtractedParamType  // 数组元素类型
}

// 参数提取器配置
interface ParameterExtractorConfig {
  extractionMethod: ExtractionMethod
  
  // 源文本（只支持 String 类型变量）
  sourceVariable: string
  sourceNodeLabel?: string
  
  // LLM 模式配置
  modelId?: string               // 模型 ID（从团队模型 API 获取）
  modelName?: string             // 模型名称（用于显示）
  useJsonSchema?: boolean        // 是否启用 JSON Schema 结构化输出
  systemPrompt?: string          // 自定义系统提示词
  
  // 参数列表（每个参数是独立的输出变量）
  parameters: ExtractedParameter[]
}
```

**LLM 模式特性**：
- 模型选择从团队授权模型 API 动态获取
- 支持启用 JSON Schema 结构化输出
- 自动生成 JSON Schema 约束输出格式
- 参数描述帮助 LLM 理解提取语义

**JSON Schema 生成**：
```typescript
function generateJsonSchema(parameters: ExtractedParameter[]): object {
  // 根据参数列表自动生成 OpenAI 兼容的 JSON Schema
  return {
    name: 'extracted_parameters',
    strict: true,
    schema: {
      type: 'object',
      properties: { /* 根据参数生成 */ },
      required: [ /* 必填参数名列表 */ ],
      additionalProperties: false,
    },
  }
}
```

**输出变量**：
- 每个定义的参数作为独立的输出变量
- 变量类型与参数类型一致
- 格式：`{{节点名.参数名}}`

---

## 容器节点

容器节点是特殊的父节点，可以包含子节点形成子图。使用 ReactFlow 的 `parentId` 和 `extent` 机制实现嵌套。

### 迭代节点 (iteration) ✅

**用途**：遍历数组或对象，对每个元素执行子图中的操作

**视觉特点**：
- 图标：`RefreshCw` (lucide-react)
- 主题色：`bg-cyan-500`
- 布局：大容器卡片，可调整大小
- 边框：`border-2`，圆角 `rounded-2xl`
- 内部区域：带虚线边框的子图区域
- 最小尺寸：400×220px
- 可调整大小：右下角拖拽手柄

**子节点**：

#### 迭代开始节点 (iteration_start)
- 形状：小圆形 (40×40px)
- 图标：`RefreshCw`
- 位置：容器内左侧
- 显示：当前项变量名
- 输出 Handle：右侧

#### 迭代退出节点 (iteration_exit)（可选）
- 形状：小圆形 (40×40px)
- 图标：`LogOut`
- 用途：提前退出迭代
- 输入 Handle：左侧

**配置项**：

```typescript
interface IterationConfig {
  iteratorVariable: string    // 要迭代的变量，如 {{items}}
  iteratorSource?: string     // 变量来源节点
  iteratorType: 'array' | 'object'
  
  // 数组迭代输出变量
  itemVariable: string        // 当前项变量名，默认 item
  indexVariable: string       // 索引变量名，默认 index
  
  // 对象迭代输出变量
  keyVariable: string         // 键名变量名，默认 key
  valueVariable: string       // 键值变量名，默认 value
  
  // 并行配置
  parallel: boolean           // 是否并行执行
  maxParallel?: number        // 最大并行数
  
  // 输出
  outputVariable: string      // 结果数组变量名，默认 results
}
```

**输出变量**：
- 数组迭代：`{{item}}`、`{{index}}`
- 对象迭代：`{{key}}`、`{{value}}`
- 结果：`{{results}}` (数组)

---

### 循环节点 (loop) ✅

**用途**：基于条件的循环执行，支持自定义内部变量

**视觉特点**：
- 图标：`Infinity` (lucide-react)
- 主题色：`bg-cyan-500`
- 布局：与迭代节点类似，大容器卡片
- 边框颜色：`border-cyan-500/30`
- 最小尺寸：400×220px

**子节点**：

#### 循环开始节点 (loop_start)
- 形状：小圆形 (40×40px)
- 图标：`Infinity`
- 位置：容器内左侧
- 显示：变量名列表（超过2个时截断）
- 输出 Handle：右侧

#### 循环退出节点 (loop_exit)（可选）
- 形状：小圆形 (40×40px)
- 图标：`LogOut`
- 用途：满足条件时退出循环
- 输入 Handle：左侧

**配置项**：

```typescript
// 循环变量类型
type LoopVariableType = 'string' | 'number' | 'boolean' | 'array' | 'object'

// 循环内部变量定义
interface LoopVariable {
  id: string
  name: string              // 变量名
  type: LoopVariableType    // 变量类型
  defaultValue: string      // 默认值
  description?: string      // 描述
}

interface LoopConfig {
  maxIterations: number         // 最大循环次数（防止无限循环）
  indexVariable: string         // 循环索引变量名，固定 Number 类型
  
  // 内部变量（可添加多个）
  loopVariables: LoopVariable[]
  
  // 退出条件（复用条件分支的规则结构）
  exitConditions: ConditionRule[]
  exitLogicOperator: 'and' | 'or'
  
  // 输出
  outputVariable: string        // 结果数组变量名
}
```

**与迭代节点的区别**：
| 特性 | 迭代 (Iteration) | 循环 (Loop) |
|------|-----------------|-------------|
| 数据源 | 外部数组/对象 | 无，基于条件 |
| 次数 | 由数据长度决定 | 由退出条件决定 |
| 内部变量 | 固定（item/index 或 key/value） | 自定义多个变量 |
| 退出方式 | 遍历完成或 break | 满足退出条件或达到最大次数 |
| 变量更新 | 自动更新当前项 | 内部节点手动更新 |

---

## 配置面板

配置面板 (`NodeConfigDrawer`) 是节点的详细配置界面，采用抽屉式布局。

### 布局结构

```
┌─────────────────────────────────┐
│ [图标] 节点类型标题     [关闭] │  Header
├─────────────────────────────────┤
│ 节点名称输入框                   │
│ 描述输入框                       │
├─────────────────────────────────┤
│ [设置]  [上次执行]               │  Tabs
├─────────────────────────────────┤
│                                 │
│    节点类型特定配置内容          │  Content
│                                 │
└─────────────────────────────────┘
```

### 通用配置

- **节点名称**：可自定义，需要唯一性校验
- **描述**：可选，点击展开输入

### 变量选择器

配置面板中的变量选择使用 Popover 组件，支持：
- 搜索过滤
- 按来源分组显示
- 显示变量类型
- 系统变量与用户变量区分（不同颜色）
- 类型过滤（根据节点需求只显示特定类型）

### 提示词编辑器 (PromptTextarea)

LLM 节点和其他需要提示词输入的场景使用专用编辑器：
- 使用 `contenteditable` 实现
- 输入 `{{` 触发变量补全菜单
- 变量显示为带样式的标签：`[节点名 / 变量名]`
- 标签使用不同颜色区分系统变量和用户变量
- 支持精确光标定位

### 参数编辑对话框

用于添加/编辑开始节点的参数，包含：
- 变量名输入（带格式验证）
- 类型选择
- 必填开关
- 默认值输入（根据类型变化）
- 描述输入
- 选项配置（仅 select 类型）

---

## 变量命名规则

### 变量名格式

变量名必须符合以下规则：
- 只能包含字母、数字、下划线
- 不能以数字开头
- 不能为空

### 变量重复规则

| 场景 | 是否允许 | 说明 |
|------|---------|------|
| 同一节点内重复 | ❌ 不允许 | 节点内多个输出变量不能同名 |
| 不同节点间重复 | ✅ 允许 | 不同节点可以有相同名称的变量 |

**设计说明**：变量引用采用 `节点名.变量名` 的格式，因此不同节点的同名变量可以被唯一区分。

### 变量选择器规则

变量选择器仅显示当前节点的**上游节点**的变量：
- 剖除当前节点本身的输出变量
- 剖除当前节点下游节点的变量
- 系统变量（如 `sys.user_id`）始终可用

这确保了节点只能引用在其之前已执行节点的输出，避免循环依赖。

---

## 技术实现

### 使用的库

- **@xyflow/react**：流程图核心库
  - `ReactFlow`：主画布
  - `Handle`：连接点
  - `NodeResizeControl`：节点大小调整
  - `useReactFlow`：操作 API

- **lucide-react**：图标库

- **shadcn/ui**：UI 组件
  - Dialog、Popover、Select、Input、Button、Switch 等

### 节点注册

```typescript
const nodeTypes = {
  // 基础节点
  user_input: UserInputNode,
  trigger: TriggerNode,
  llm: LLMNode,
  tool: ToolNode,
  sub_workflow: SubWorkflowNode,
  code: CodeNode,
  answer: AnswerNode,
  
  // 数据处理节点
  template: TemplateNode,
  file_to_url: FileToUrlNode,
  variable_aggregator: VariableAggregatorNode,
  variable_assignment: VariableAssignmentNode,
  parameter_extractor: ParameterExtractorNode,
  
  // 流程控制节点
  condition: ConditionNode,
  question_classifier: QuestionClassifierNode,
  
  // 容器节点
  iteration: IterationNode,
  iteration_start: IterationStartNode,
  iteration_exit: IterationExitNode,
  loop: LoopNode,
  loop_start: LoopStartNode,
  loop_exit: LoopExitNode,
  
  // 兼容旧版本
  start: UserInputNode,
}
```

### 嵌套节点实现

容器节点使用 ReactFlow 的父子关系：

```typescript
// 子节点创建时设置 parentId 和 extent
const childNode = {
  id: childId,
  type: 'iteration_start',
  parentId: parentNode.id,  // 关联父节点
  extent: 'parent',         // 限制在父节点范围内
  position: { x: 50, y: 100 },
  data: { ... }
}
```

---

## 文件结构

```
frontend/app/(platform)/app/apps/workflow/[id]/
├── page.tsx                      # 主页面，ReactFlow 画布
└── _components/
    ├── nodes/
    │   ├── user-input-node.tsx   # 用户输入节点
    │   ├── trigger-node.tsx      # 触发器节点
    │   ├── llm-node.tsx          # LLM 节点 ✅
    │   ├── tool-node.tsx         # 工具节点 ✅
    │   ├── sub-workflow-node.tsx # 子工作流节点
    │   ├── code-node.tsx         # 代码节点 ✅
    │   ├── answer-node.tsx       # 输出节点 ✅
    │   ├── template-node.tsx     # 模板转换节点 ✅
    │   ├── file-to-url-node.tsx  # 文件转URL节点 ✅
    │   ├── variable-aggregator-node.tsx   # 变量聚合器节点 ✅
    │   ├── variable-assignment-node.tsx   # 变量赋值节点 ✅
    │   ├── parameter-extractor-node.tsx   # 参数提取器节点 ✅
    │   ├── condition-node.tsx    # 条件分支节点 ✅
    │   ├── question-classifier-node.tsx   # 问题分类节点 ✅
    │   ├── iteration-node.tsx    # 迭代节点 + 子节点 ✅
    │   ├── loop-node.tsx         # 循环节点 + 子节点 ✅
    │   └── start-node.tsx        # 旧版开始节点（兼容）
    ├── node-config-drawer.tsx    # 节点配置面板（主入口）
    ├── node-config/              # 节点配置组件模块
    │   ├── index.ts              # 统一导出
    │   ├── types.ts              # 类型定义
    │   ├── constants.ts          # 常量配置
    │   ├── utils.ts              # 工具函数
    │   ├── variable-selector.tsx # 变量选择器组件
    │   ├── components/           # 通用组件
    │   │   └── prompt-textarea.tsx  # 提示词编辑器 ✅
    │   ├── configs/              # 各节点类型配置组件
    │   │   ├── index.ts
    │   │   ├── start-node-config.tsx      # 开始节点配置
    │   │   ├── llm-node-config.tsx        # LLM 节点配置 ✅
    │   │   ├── tool-node-config.tsx       # 工具节点配置 ✅
    │   │   ├── code-node-config.tsx       # 代码节点配置 ✅
    │   │   ├── answer-node-config.tsx     # 输出节点配置 ✅
    │   │   ├── condition-node-config.tsx  # 条件分支节点配置 ✅
    │   │   ├── question-classifier-node-config.tsx  # 问题分类配置 ✅
    │   │   ├── iteration-node-config.tsx  # 迭代节点配置 ✅
    │   │   ├── loop-node-config.tsx       # 循环节点配置 ✅
    │   │   ├── template-node-config.tsx   # 模板转换配置 ✅
    │   │   ├── file-to-url-node-config.tsx         # 文件转URL配置 ✅
    │   │   ├── variable-aggregator-node-config.tsx  # 变量聚合器配置 ✅
    │   │   ├── variable-assignment-node-config.tsx  # 变量赋值配置 ✅
    │   │   └── parameter-extractor-node-config.tsx  # 参数提取器配置 ✅
    │   └── dialogs/              # 配置对话框组件
    │       ├── index.ts
    │       ├── parameter-edit-dialog.tsx  # 参数编辑对话框
    │       └── code-input-dialog.tsx      # 代码输入对话框
    ├── add-node-popover.tsx      # 添加节点弹窗
    ├── node-panel.tsx            # 节点面板
    └── start-node-selector.tsx   # 开始节点选择器
```

---

## 更新日志

- **2025-01-02**：新增流程控制和输出节点
  - 新增问题分类节点 (question_classifier)：基于 LLM 的智能问题分类，多分支输出
  - 新增输出节点 (answer)：定义工作流最终输出，支持流式输出配置
  - 完善 LLM 节点：
    - 三个输出变量（response、reasoning、usage）
    - 多模态配置仅在模型支持 vision 时显示
    - 支持 JSON Schema 响应格式
    - 提示词编辑器支持变量补全和样式化标签显示
  - 完善参数提取器节点：
    - 每个参数作为独立输出变量（非 Object 包装）
    - 不同提取方式支持不同参数类型
    - LLM 模式支持 JSON Schema 结构化输出
  - 完善工具节点：支持内置、自定义、MCP 三种工具类型
  - 新增文件转URL节点 (file_to_url)：将文件变量转为可访问 URL

- **2025-12-31**：新增数据处理节点
  - 新增模板转换节点 (template)：支持 Jinja2 模板语法
  - 新增变量聚合器节点 (variable_aggregator)：4种聚合模式（object/array/concat/merge）
  - 新增变量赋值节点 (variable_assignment)：3种操作（覆盖/清空/设置）
  - 新增参数提取器节点 (parameter_extractor)：3种提取方式（LLM/正则/JSON Path）
  - 参数提取器 LLM 模式支持从团队模型 API 动态获取模型列表
  - 删除文档提取器节点（功能整合到参数提取器）
  - 完善代码节点：支持重试配置、异常处理（默认值/异常分支）

- **2024-12-31**：配置面板组件化重构
  - 将 `node-config-drawer.tsx` 拆分为模块化结构
  - 新增 `node-config/` 目录，包含类型、常量、工具函数
  - 拆分各节点类型配置组件到 `configs/` 子目录
  - 拆分对话框组件到 `dialogs/` 子目录

- **2024-12-31**：初始版本
  - 完成基础节点实现
  - 完成条件分支节点
  - 完成迭代容器节点
  - 完成循环容器节点（支持多内部变量）
