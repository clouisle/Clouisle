# 工作流后端对接规范

本文档梳理前端工作流功能和节点类型，用于指导后端实现工作流执行引擎。

## 一、当前状态概览

### 已完成（后端）
- ✅ Workflow CRUD API
- ✅ WorkflowRun 记录模型
- ✅ NodeExecution 执行记录模型
- ✅ WorkflowVersion 版本历史
- ✅ 发布/取消发布
- ✅ 版本快照和恢复
- ✅ **工作流执行引擎** — `backend/app/services/workflow/`
  （orchestrator / plan / context / executor）
- ✅ **节点执行器** — `backend/app/services/workflow/executors/`（start、answer、
  llm、decision、condition、code、template、variable、iteration、tool、
  subworkflow、knowledge、media_generation、pause）
- ✅ **变量系统** — `ExecutionContext` + TypeSpec
  （types.py / serialization.py / schema_inference.py）
- ✅ **调试运行** — `POST /api/v1/workflows/{id}/debug`（使用草稿并推断类型）
- ✅ **流式输出** — SSE：`GET /api/v1/workflows/runs/{run_id}/stream`
- ✅ **Webhook 触发** — `POST /api/v1/workflows/webhook/{webhook_token}`
- ✅ 分布式执行任务 — `backend/app/tasks/workflow.py`：`run_workflow_task`（运行）、
  `resume_workflow_task`（暂停恢复）、`cancel_workflow_task`（取消），Celery 名称为
  `app.tasks.workflow.*`，由 `app.tasks.workflow.*` 路由规则投递到 `workflow` 队列；
  该模块在 `backend/app/core/celery.py` 的 `include` 列表中注册
- ⚠️ **未接线** — `backend/app/services/workflow/tasks.py` 定义了
  `workflow.execute` / `workflow.execute_node` / `workflow.execute_stage` /
  `workflow.cancel` / `workflow.cleanup` / `workflow.check_scheduled` /
  `workflow.cleanup_old_runs`，但该模块既不在 Celery `include` 列表中，也没有生产代码
  导入它（仅测试引用），任务名又不匹配现有 `task_routes` —— 因此这些任务在当前部署中
  **不会注册**，投递会报 unregistered task

### 待实现（后端）
- ❌ **Cron 定时调度** — 扫描逻辑位于 `backend/app/services/workflow/tasks.py`
  的 `workflow.check_scheduled`（读取已发布且 `trigger_type=cron` 的工作流，
  用 `croniter` 做分钟匹配）。要真正生效需同时满足：把该模块加入 Celery
  `include`、把任务加入 `beat_schedule`（例如每分钟）、并为任务名补充
  `task_routes`；此外任务读取的 cron 字段是 `trigger_config["cron"]`，需与前端
  写入的字段名一致
- ❌ **断点 / 单步调试** — `services/workflow/debugger.py` 已有断点与单步
  原语，但尚未接入任何 API

---

## 二、节点类型清单

### 2.1 开始节点

#### user_input（用户输入）
工作流入口，定义用户输入参数。

```typescript
interface UserInputNodeConfig {
  parameters: Parameter[]
}

interface Parameter {
  id: string
  name: string                    // 变量名
  type: ParameterType             // 类型
  required: boolean               // 是否必填
  defaultValue?: string           // 默认值
  description?: string            // 描述
  options?: string[]              // select 类型的选项
  fileConfig?: FileParameterConfig  // 文件类型配置
}

type ParameterType = 
  | 'text'      // 单行文本
  | 'paragraph' // 多行文本
  | 'select'    // 下拉选择
  | 'number'    // 数字
  | 'checkbox'  // 布尔
  | 'array'     // 数组
  | 'object'    // 对象
  | 'file'      // 单文件
  | 'image'     // 单图片
  | 'files'     // 多文件
  | 'images'    // 多图片
```

**后端执行逻辑**：
1. 验证输入参数是否满足 required 要求
2. 类型校验和转换
3. 文件上传处理
4. 将参数注入到变量上下文

**系统变量**（自动注入）：
- `sys.user_id` - 当前用户 ID
- `sys.app_id` - 应用 ID  
- `sys.workflow_id` - 工作流 ID
- `sys.workflow_run_id` - 运行实例 ID
- `sys.timestamp` - 当前时间戳

---

#### trigger（触发器）
API/Webhook/Cron 触发的工作流入口。

```typescript
interface TriggerNodeConfig {
  parameters: Parameter[]  // 同 user_input
}
```

**后端执行逻辑**：
1. Webhook: 验证 token，解析 request body 为参数
2. Cron: 使用 Celery Beat 定时触发
3. API: 直接调用执行

---

### 2.2 AI 节点

#### llm（大语言模型）
调用 LLM 生成文本。

```typescript
interface LLMNodeConfig {
  // 模型配置
  modelId?: string              // 团队模型授权 ID
  modelName?: string            // 模型名称（显示用）
  
  // 提示词（支持变量插值 {{var}}）
  systemPrompt?: string
  userPrompt?: string
  
  // 模型参数
  temperature?: number          // 0-2, 默认 0.7
  topP?: number                 // 0-1, 默认 1
  maxTokens?: number            // 最大输出 token
  
  // 响应格式
  responseFormat?: 'text' | 'json' | 'json_schema'
  jsonSchema?: string           // JSON Schema（responseFormat 为 json_schema 时）
  
  // 记忆配置
  memoryConfig?: {
    enabled: boolean
    mode: 'none' | 'window' | 'token_limit'
    windowSize?: number         // 窗口模式：消息轮次
    tokenLimit?: number         // Token 限制
  }
  
  // 多模态配置
  visionConfig?: {
    enabled: boolean
    imageVariable?: string      // 图片变量引用
    imagePosition?: 'before' | 'after'
  }
  
  // 输出变量
  outputVariables?: {
    response?: string           // 模型回复，默认 'response'
    reasoning?: string          // 推理过程，默认 'reasoning'
    usage?: string              // token 用量，默认 'usage'
  }
  
  // 高级
  streaming?: boolean           // 是否流式，默认 true
  timeout?: number              // 超时秒数，默认 60
}
```

**后端执行逻辑**：
1. 从 team_models 获取模型配置和 API Key
2. 解析提示词中的变量 `{{node.var}}` 替换为实际值
3. 调用 LLM Provider（OpenAI/Anthropic/等）
4. 流式模式：通过 SSE 返回 chunk
5. 记录 token 用量到 NodeExecution
6. 输出变量：`response`, `reasoning`, `usage`

---

#### decision（决策）

调用类型为 `decision` 的决策模型（当前为 TypeSafe AI System One），对 state 提出一个类型化问题并按其答案分支，不生成自由文本。

```typescript
type DecisionQuestionType = 'choice' | 'score' | 'noul'

interface DecisionNodeConfig {
  modelId?: string                    // 团队模型授权 ID（仅 decision 类型模型）
  modelName?: string

  stateTemplate: string               // 被评估的内容，支持 {{变量}}
  questionId: string                  // 问题 id，默认 'decision'
  questionType: DecisionQuestionType  // choice | score | noul
  instructions: string                // 要模型判断的问题
  options: string[]                   // choice: 1-255 唯一选项；score: 2-10 有序等级
  defaultHandle?: string              // 兜底分支，默认 'default'
  confidenceThreshold?: number        // 0-1，低于该置信度走兜底分支
}
```

**后端执行逻辑**：
1. 校验配置：`modelId`、`stateTemplate`、`instructions` 必填；choice 需 1-255 个唯一非空选项，score 需 2-10 个唯一有序等级
2. 解析 `stateTemplate` 变量，经 `ModelManager.team_decide` 调用决策适配器（`POST {base_url}/v1/systemone`）
3. 校验返回答案的类型与选项集合，任一项不符即 `decision_result_missing`
4. 映射分支 handle：choice 取 `choice`；score 取概率最高的等级；noul 概率 ≥ 0.5 走 `yes`，否则 `no`；低于置信度阈值时走兜底 handle
5. 输出 `answer`、`selected_handle`、`usage`，以及类型化字段（choice: `choice`/`confidence`/`probabilities`；score: `score`/`confidence`/`probabilities`；noul: `noul`）

---

#### question_classifier（问题分类）
使用 LLM 对问题智能分类，走不同分支。

```typescript
interface QuestionClassifierConfig {
  sourceVariable: string        // 问题文本变量
  sourceNodeLabel?: string
  
  modelId?: string
  modelName?: string
  
  instruction?: string          // 额外分类指令
  
  categories: ClassifierCategory[]
}

interface ClassifierCategory {
  id: string
  name: string                  // 类别名称
  description: string           // 类别描述（帮助 LLM 理解）
}
```

**后端执行逻辑**：
1. 构建分类 prompt，包含所有类别描述
2. 调用 LLM 返回分类结果
3. 根据分类结果决定走哪个输出分支
4. 每个 category 对应一个 sourceHandle

---

#### parameter_extractor（参数提取器）
从文本中提取结构化参数。

```typescript
interface ParameterExtractorConfig {
  extractionMethod: 'llm' | 'regex' | 'json_path'
  
  sourceVariable: string        // 源文本变量
  sourceNodeLabel?: string
  
  // LLM 模式
  modelId?: string
  modelName?: string
  useJsonSchema?: boolean
  systemPrompt?: string
  
  // 要提取的参数
  parameters: ExtractedParameter[]
}

interface ExtractedParameter {
  id: string
  name: string                  // 参数名（输出变量名）
  type: 'string' | 'number' | 'boolean' | 'array' | 'object'
  description: string           // 参数描述
  required: boolean
  pattern?: string              // regex 模式的正则表达式
  jsonPath?: string             // json_path 模式的路径
  defaultValue?: string
  enum?: string[]               // 枚举值
  arrayItemType?: string        // 数组元素类型
}
```

**后端执行逻辑**：
1. **LLM 模式**：构建 JSON Schema 强制输出格式，调用 LLM
2. **Regex 模式**：对每个参数执行正则匹配
3. **JSON Path 模式**：解析 JSON，按路径提取
4. 每个参数作为独立输出变量

---

### 2.3 流程控制节点

#### condition（条件分支）
根据条件走不同分支。

```typescript
interface ConditionNodeConfig {
  branches: ConditionBranch[]
}

interface ConditionBranch {
  id: string
  type: 'if' | 'else_if' | 'else'
  name: string
  conditions: ConditionRule[]
  logicOperator: 'and' | 'or'
}

interface ConditionRule {
  id: string
  variable: string              // {{node.var}}
  variableSource?: string
  operator: ConditionOperator
  value: string
}

type ConditionOperator = 
  | 'equals' | 'not_equals'
  | 'contains' | 'not_contains'
  | 'starts_with' | 'ends_with'
  | 'is_empty' | 'is_not_empty'
  | 'greater_than' | 'less_than'
  | 'greater_or_equal' | 'less_or_equal'
```

**后端执行逻辑**：
1. 按顺序评估每个分支
2. 获取变量值，执行条件比较
3. 第一个满足条件的分支激活
4. 激活分支的 sourceHandle 对应的后续节点执行

---

#### iteration（迭代）
遍历数组/对象执行子图。

```typescript
interface IterationConfig {
  iteratorVariable: string      // 要迭代的变量
  iteratorSource?: string
  iteratorType: 'array' | 'object'
  
  // 数组迭代
  itemVariable: string          // 默认 'item'
  indexVariable: string         // 默认 'index'
  
  // 对象迭代
  keyVariable: string           // 默认 'key'
  valueVariable: string         // 默认 'value'
  
  // 并行
  parallel: boolean
  maxParallel?: number
  
  outputVariable: string        // 结果数组变量名
}
```

**后端执行逻辑**：
1. 获取迭代变量值
2. 遍历每个元素，注入 item/index 或 key/value
3. 执行容器内子图（从 iteration_start 开始）
4. 收集每次迭代的结果到 results 数组
5. 并行模式：使用 asyncio.gather 并发执行

---

#### loop（循环）
基于条件的循环。

```typescript
interface LoopConfig {
  maxIterations: number         // 最大循环次数
  indexVariable: string         // 索引变量名
  
  loopVariables: LoopVariable[] // 循环内部变量
  
  exitConditions: ConditionRule[]
  exitLogicOperator: 'and' | 'or'
  
  outputVariable: string
}

interface LoopVariable {
  id: string
  name: string
  type: 'string' | 'number' | 'boolean' | 'array' | 'object'
  defaultValue: string
  description?: string
}
```

**后端执行逻辑**：
1. 初始化循环变量
2. 执行循环体（从 loop_start 到 loop_exit 或循环结束）
3. 每次迭代后检查退出条件
4. 达到 maxIterations 或满足退出条件时停止
5. 内部节点可通过 variable_assignment 更新循环变量

---

### 2.4 数据处理节点

#### code（代码执行）
执行 Python/JavaScript 代码。

```typescript
interface CodeConfig {
  language: 'python' | 'javascript'
  code: string
  inputs: CodeInput[]
  outputs: CodeOutputVariable[]
  outputVariable: string
  retry: RetryConfig
  errorHandling: ErrorHandlingConfig
}

interface CodeInput {
  id: string
  name: string                  // 代码中的变量名
  value: string                 // 变量引用 {{node.var}}
  valueSource?: string
}

interface CodeOutputVariable {
  id: string
  name: string
  type: 'string' | 'number' | 'boolean' | 'array' | 'object'
}

interface RetryConfig {
  enabled: boolean
  maxRetries: number
  retryInterval: number         // ms
}

interface ErrorHandlingConfig {
  type: 'none' | 'default_value' | 'error_branch'
  defaultValue?: string
}
```

**后端执行逻辑**：
1. 创建沙箱环境
2. 注入 inputs 变量
3. 执行代码，捕获 main() 返回值
4. Python：使用 RestrictedPython 或子进程沙箱
5. JavaScript：使用 Node.js 子进程
6. 错误处理：重试、默认值、或走异常分支

---

#### template（模板转换）
Jinja2 模板渲染。

```typescript
interface TemplateConfig {
  inputs: TemplateInput[]
  template: string              // Jinja2 模板
  outputVariable: string        // 默认 'output'
  outputDescription: string
}

interface TemplateInput {
  id: string
  name: string                  // 模板中的变量名 {{ name }}
  value: string                 // 变量引用
  valueSource?: string
}
```

**后端执行逻辑**：
1. 使用 Jinja2 渲染模板
2. 注入 inputs 中定义的变量
3. 输出渲染后的字符串

---

#### variable_aggregator（变量聚合器）
聚合多个变量为一个。

```typescript
interface VariableAggregatorConfig {
  mode: 'object' | 'array' | 'concat' | 'merge'
  variables: VariableMapping[]
  outputVariable: string
  separator?: string            // concat 模式分隔符
  mergeStrategy?: 'shallow' | 'deep'
}

interface VariableMapping {
  id: string
  sourceVariable: string
  sourceNodeLabel?: string
  targetKey?: string            // object 模式的 key
}
```

**后端执行逻辑**：
- `object`: `{ key1: var1, key2: var2 }`
- `array`: `[var1, var2, var3]`
- `concat`: `var1 + separator + var2`
- `merge`: 深度合并对象

---

#### variable_assignment（变量赋值）
修改对话变量值。

```typescript
interface VariableAssignmentConfig {
  assignments: AssignmentItem[]
}

interface AssignmentItem {
  id: string
  targetVariable: string        // 目标变量
  targetVariableLabel?: string
  operation: 'overwrite' | 'clear' | 'set'
  variableRef?: string          // overwrite 使用
  variableRefNodeLabel?: string
  constantValue?: string        // set 使用
}
```

---

#### file_to_url（文件转 URL）
将文件变量转为可访问 URL。

```typescript
interface FileToUrlConfig {
  inputs: FileToUrlInput[]
  ensureAbsolute: boolean
}

interface FileToUrlInput {
  id: string
  name: string                  // 输出变量名
  sourceVariable: string        // 源文件变量
  sourceType: 'file' | 'image' | 'files' | 'images'
}
```

---

### 2.5 工具节点

#### tool（工具调用）
调用内置/自定义/MCP 工具。

```typescript
interface ToolNodeConfig {
  toolId?: string
  toolName?: string
  toolType: 'builtin' | 'custom' | 'mcp'
  toolDisplayName?: string
  toolDescription?: string
  toolIcon?: string
  toolCategory?: ToolCategory
  
  // MCP 特有
  mcpToolName?: string
  mcpToolDescription?: string
  
  parameterMappings: ParameterMapping[]
  outputVariable: string
}

interface ParameterMapping {
  name: string
  type: string
  required: boolean
  description?: string
  source: 'variable' | 'constant'
  variableRef?: string
  variableRefNodeLabel?: string
  constantValue?: string
}
```

**后端执行逻辑**：
1. 根据 toolType 获取工具定义
2. 解析参数映射，获取实际参数值
3. 调用工具执行
4. 返回结果到 outputVariable

---

#### agent（智能体）
调用已创建的 Agent。

```typescript
interface AgentNodeConfig {
  agentId?: string
  agentName?: string
  inputVariable: string
  outputVariable: string
}
```

---

#### sub_workflow（子工作流）
调用其他工作流。

```typescript
interface SubWorkflowConfig {
  workflowId?: string
  workflowName?: string
  inputMappings: InputMapping[]
  outputMappings: OutputMapping[]
}
```

**后端执行逻辑**：
1. 创建子 WorkflowRun（设置 parent_run_id, depth+1）
2. 执行子工作流
3. 映射输出到当前上下文

---

### 2.6 输出节点

#### answer（输出）
定义工作流最终输出。

```typescript
interface AnswerNodeConfig {
  outputs: OutputVariable[]
  streaming: {
    enabled: boolean
    variable?: string           // 流式输出的变量
  }
}

interface OutputVariable {
  id: string
  name: string                  // 输出变量名（API 返回的 key）
  sourceVariable: string        // 源变量引用
  sourceNodeLabel?: string
  type: 'string' | 'number' | 'boolean' | 'array' | 'object' | 'file' | 'any'
  description?: string
}
```

**后端执行逻辑**：
1. 收集所有 output 变量值
2. 流式模式：监听 sourceVariable 对应的 LLM 流，实时 SSE 推送
3. 设置 WorkflowRun.outputs

---

## 三、工作流执行引擎设计

### 3.1 执行流程

```
1. 创建 WorkflowRun 记录
2. 解析 definition，构建节点图（DAG）
3. 找到开始节点（user_input / trigger）
4. 从开始节点 BFS/DFS 遍历执行
5. 每个节点执行：
   a. 创建 NodeExecution 记录
   b. 解析输入变量
   c. 执行节点逻辑
   d. 输出变量写入上下文
   e. 更新 NodeExecution 状态
6. 遇到分支节点，根据结果选择下游
7. 遇到 answer 节点，收集输出
8. 全部完成，更新 WorkflowRun 状态
```

### 3.2 变量上下文

```python
class ExecutionContext:
    """工作流执行上下文"""
    
    def __init__(self, workflow_run: WorkflowRun):
        self.run = workflow_run
        self.variables: dict[str, Any] = {}
        self.node_outputs: dict[str, dict[str, Any]] = {}  # node_id -> outputs
        
    def set_variable(self, node_id: str, name: str, value: Any):
        """设置节点输出变量"""
        if node_id not in self.node_outputs:
            self.node_outputs[node_id] = {}
        self.node_outputs[node_id][name] = value
        
    def resolve_variable(self, ref: str) -> Any:
        """解析变量引用 {{node_id.var_name}} 或 {{sys.xxx}}"""
        # 解析 {{xxx}} 格式
        match = re.match(r'\{\{(.+?)\.(.+?)\}\}', ref)
        if match:
            node_id, var_name = match.groups()
            if node_id == 'sys':
                return self.get_system_variable(var_name)
            return self.node_outputs.get(node_id, {}).get(var_name)
        return ref
```

### 3.3 节点执行器接口

```python
from abc import ABC, abstractmethod

class NodeExecutor(ABC):
    """节点执行器基类"""
    
    @abstractmethod
    async def execute(
        self,
        node: dict,
        context: ExecutionContext,
    ) -> dict[str, Any]:
        """
        执行节点
        
        Args:
            node: 节点定义 (id, type, data)
            context: 执行上下文
            
        Returns:
            输出变量字典
        """
        pass

class LLMNodeExecutor(NodeExecutor):
    async def execute(self, node, context):
        config = node['data'].get('llmConfig', {})
        
        # 解析提示词中的变量
        system_prompt = self.resolve_template(config.get('systemPrompt', ''), context)
        user_prompt = self.resolve_template(config.get('userPrompt', ''), context)
        
        # 获取模型配置
        model_auth = await TeamModelAuth.get(id=config['modelId'])
        
        # 调用 LLM
        response = await llm_manager.generate(
            model_auth=model_auth,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=config.get('temperature', 0.7),
            max_tokens=config.get('maxTokens'),
            stream=config.get('streaming', True),
        )
        
        return {
            'response': response.content,
            'reasoning': response.reasoning,
            'usage': response.total_tokens,
        }
```

### 3.4 API 端点

已实现的运行相关端点（实现见 `backend/app/api/v1/endpoints/workflows.py`）：

```python
# 运行工作流（返回 run_id，异步执行）
POST /api/v1/workflows/{workflow_id}/run
Body: WorkflowRunRequest (inputs, ...)
Response: { "run_id": "...", "stream_url": "/api/v1/workflows/runs/{run_id}/stream" }

# 调试运行（使用草稿而非已发布版本）
POST /api/v1/workflows/{workflow_id}/debug
Body: WorkflowRunRequest

# 流式输出（SSE）
GET /api/v1/workflows/runs/{run_id}/stream?from_sequence=0
Response: SSE stream

# 取消运行
POST /api/v1/workflows/runs/{run_id}/cancel

# 运行记录
GET  /api/v1/workflows/runs
GET  /api/v1/workflows/runs/stats
GET  /api/v1/workflows/runs/{run_id}
GET  /api/v1/workflows/runs/{run_id}/nodes
DELETE /api/v1/workflows/runs/{run_id}

# Webhook 触发
POST /api/v1/workflows/webhook/{webhook_token}
```

没有独立的 `POST /{workflow_id}/run/stream` 端点（SSE 走
`GET /runs/{run_id}/stream`），也没有 `/runs/{run_id}/continue`、`/step`
等逐步调试端点。

---

## 四、待办事项

原 P0～P2（执行引擎、变量上下文、各类型节点执行器、调试运行、SSE、运行 API）
已全部落地，实现说明与端点清单见
`docs/dev/status/WORKFLOW_ENGINE_STATUS.md`；本节只保留仍未完成的项。

### 待办

1. [ ] **Cron 定时任务** — 扫描逻辑在 `backend/app/services/workflow/tasks.py` 的
   `workflow.check_scheduled`（已实现定期扫描），但要生效需要三处接线：加入
   `backend/app/core/celery.py` 的 `include` 列表、加入 `beat_schedule`、并为
   `workflow.*` 任务名补充 `task_routes`；另外任务读取 `trigger_config["cron"]`
   而前端写入的是 `trigger_config["cron_expression"]`，字段名需统一
2. [ ] **断点 / 单步调试** — 将 `backend/app/services/workflow/debugger.py`
   的断点、单步、变量查看能力接入 API 与前端调试面板
3. [ ] **调试 API 补全** — 现有调试入口仅
   `POST /api/v1/workflows/{workflow_id}/debug`（整轮运行），没有
   `/runs/{run_id}/continue`、`/step` 等逐步控制端点

---

## 五、文件结构

本规范最初是"待实现"的对接建议；以下是引擎落地后的实际布局
（完整说明见 `docs/dev/status/WORKFLOW_ENGINE_STATUS.md`）：

```
backend/app/
├── tasks/
│   └── workflow.py             # 已注册：app.tasks.workflow.run_workflow_task /
│                               # resume_workflow_task / cancel_workflow_task（workflow 队列）
├── services/workflow/
│   ├── orchestrator.py         # 执行引擎核心
│   ├── context.py              # 执行上下文
│   ├── executor.py             # 节点执行器基类 + 注册表
│   ├── plan.py                 # DAG 解析与执行计划
│   ├── stream.py               # SSE 流式输出
│   ├── retry.py / cache.py / metrics.py / profiler.py
│   ├── versioning.py / debugger.py / templates.py / benchmark.py
│   ├── types.py / serialization.py / schema_inference.py
│   ├── pause_approvers.py
│   ├── tasks.py                # 未接线（不在 Celery include / beat / routes）：
│   │                           # workflow.execute / execute_node / execute_stage /
│   │                           # cancel / cleanup / check_scheduled / cleanup_old_runs
│   └── executors/              # 各类型节点执行器
│       ├── start.py            # user_input, trigger
│       ├── answer.py           # answer
│       ├── llm.py              # llm
│       ├── decision.py         # decision
│       ├── condition.py        # condition, question_classifier
│       ├── code.py             # code
│       ├── template.py         # template
│       ├── variable.py         # variable_assignment / aggregator / parameter_extractor
│       ├── iteration.py        # iteration, loop
│       ├── tool.py             # tool, agent, http_request
│       ├── subworkflow.py      # sub_workflow, file_to_url
│       ├── knowledge.py        # knowledge_retrieval, document_extractor
│       ├── media_generation.py # media_generation
│       └── pause.py            # pause
└── api/v1/endpoints/workflows.py  # 工作流与运行相关端点
```

Webhook / 运行记录端点直接实现在 `api/v1/endpoints/workflows.py` 内，
没有单独的 `triggers/`、`engine.py` 或 `output.py` 模块。
