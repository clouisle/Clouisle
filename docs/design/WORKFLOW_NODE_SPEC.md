# 工作流节点设计规范

本文档描述了 Clouisle 工作流编辑器中各类节点的设计规范、特点和 UI 风格指南。

## 目录

- [整体 UI 风格](#整体-ui-风格)
- [节点分类](#节点分类)
- [基础节点](#基础节点)
- [流程控制节点](#流程控制节点)
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
| 卡片圆角 | `rounded-2xl` (16px) / `rounded-xl` (12px) |
| 边框 | 1-2px，默认 `border-border`，选中 `border-primary` |
| 阴影 | `shadow-sm` |
| 图标容器 | `rounded-xl` (12px) / `rounded-lg` (8px) |
| 图标大小 | 16px (h-4 w-4) / 14px (h-3.5 w-3.5) |
| 节点最小宽度 | 180px |
| 节点最大宽度 | 240-260px |

### Handle（连接点）样式

- **普通节点**：圆形，6-8px，带边框
- **容器节点**：小圆点，8px，无边框
- **添加按钮样式**：无连线时显示 `+` 图标，悬停时出现

### 颜色系统

| 节点类型 | 主题色 | Tailwind 类 |
|---------|--------|-------------|
| 开始/用户输入 | Primary | `bg-primary` |
| 触发器 | 琥珀色 | `bg-amber-500` |
| LLM | 蓝色 | `bg-blue-500` |
| 条件分支 | 青色 | `bg-cyan-500` |
| 迭代/循环 | 青色 | `bg-cyan-500` |
| 子工作流 | 紫色 | `bg-purple-500` |
| 工具 | 翠绿色 | `bg-emerald-500` |
| 代码 | 灰色 | `bg-gray-500` |
| 结束 | 红色 | `bg-red-500` |

---

## 节点分类

```
├── 基础节点
│   ├── 用户输入节点 (user_input)
│   ├── 触发器节点 (trigger)
│   ├── LLM 节点 (llm)
│   ├── 工具节点 (tool)
│   ├── 子工作流节点 (sub_workflow)
│   └── 代码节点 (code)
│
├── 流程控制节点
│   └── 条件分支节点 (condition)
│
└── 容器节点
    ├── 迭代节点 (iteration)
    │   ├── 迭代开始节点 (iteration_start)
    │   └── 迭代退出节点 (iteration_exit)
    │
    └── 循环节点 (loop)
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
  - 参数类型：text | paragraph | select | number | checkbox | array | object
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

### LLM 节点 (llm)

**用途**：调用大语言模型进行文本生成

**视觉特点**：
- 图标：`Bot` (lucide-react)
- 主题色：`bg-blue-500`
- 布局：水平布局，图标+名称
- 顶部标签：「LLM」
- 圆角：`rounded-2xl`

**配置项**（规划中）：
- 模型选择
- Prompt 模板
- 温度等参数

---

### 工具节点 (tool)

**用途**：调用外部工具或 API

**视觉特点**：
- 图标：`Wrench` (lucide-react)
- 主题色：`bg-emerald-500`
- 布局：水平布局
- 顶部标签：「工具」

**配置项**（规划中）：
- 工具选择
- 参数映射

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

## 流程控制节点

### 条件分支节点 (condition)

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

**条件规则**：
```typescript
interface ConditionRule {
  id: string
  variable: string        // 变量名，如 {{query}}
  variableSource?: string // 变量来源节点
  operator: ConditionOperator
  value: string           // 比较值
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

## 容器节点

容器节点是特殊的父节点，可以包含子节点形成子图。使用 ReactFlow 的 `parentId` 和 `extent` 机制实现嵌套。

### 迭代节点 (iteration)

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

### 循环节点 (loop)

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

### 参数编辑对话框

用于添加/编辑开始节点的参数，包含：
- 变量名输入（带格式验证）
- 类型选择
- 必填开关
- 默认值输入（根据类型变化）
- 描述输入
- 选项配置（仅 select 类型）

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
  user_input: UserInputNode,
  trigger: TriggerNode,
  llm: LLMNode,
  condition: ConditionNode,
  sub_workflow: SubWorkflowNode,
  tool: ToolNode,
  iteration: IterationNode,
  iteration_start: IterationStartNode,
  iteration_exit: IterationExitNode,
  loop: LoopNode,
  loop_start: LoopStartNode,
  loop_exit: LoopExitNode,
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
    │   ├── llm-node.tsx          # LLM 节点
    │   ├── condition-node.tsx    # 条件分支节点
    │   ├── iteration-node.tsx    # 迭代节点 + 子节点
    │   ├── loop-node.tsx         # 循环节点 + 子节点
    │   ├── tool-node.tsx         # 工具节点
    │   ├── sub-workflow-node.tsx # 子工作流节点
    │   ├── start-node.tsx        # 旧版开始节点
    │   └── end-node.tsx          # 结束节点
    ├── node-config-drawer.tsx    # 节点配置面板
    ├── add-node-popover.tsx      # 添加节点弹窗
    ├── node-panel.tsx            # 节点面板
    └── start-node-selector.tsx   # 开始节点选择器
```

---

## 更新日志

- **2024-12-31**：初始版本
  - 完成基础节点实现
  - 完成条件分支节点
  - 完成迭代容器节点
  - 完成循环容器节点（支持多内部变量）
