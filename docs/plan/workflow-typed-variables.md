# Workflow Typed Variables 设计文档

## Background & Goals

当前工作流系统两个核心痛点：

1. **对象/数组在跨节点传递时被强制 JSON 字符串化**。`ExecutionContext` 把所有变量在写入 Redis 前 `json.dumps`（`backend/app/services/workflow/context.py:170,214,429`），并在变量插值路径上用 `str(value)` 兜底（`context.py:296,304`）。下游 LLM/template/code 节点接收到的常常是 `"[{...}, {...}]"` 字符串而非原生 list/dict。
2. **类型系统几乎不存在**。后端 `dict[str, Any]` 散落在 18+ 个文件、约 61 处；前端 `AvailableVariable.type` 是裸 `string`，`NodeData.config: Record<string, unknown>`。任何"对象/数组"的字段、元素类型都无法被工具链利用。

### 用户决策（已锁定）
- **统一原生对象传递**：禁止跨节点的隐式字符串化；只有「文本插值 / 展示 / LLM prompt」三处需要显式字符串化。
- **去除 `any`**：所有 object/array 输出位点必须有显式类型描述。
- **类型策略：调试运行后自动推断 schema**，作为**软类型**（仅用于辅助 UI、变量选择器过滤、prompt hint，**不在运行时强制校验**）；每次调试运行后**合并更新**（union merge）。
- **Redis 层换 msgpack**（不再 JSON）。
- **硬切换**：不兼容历史 workflow 数据。
- **端到端**：前后端一次性交付。

### 成功标准
- 节点之间传递原生类型；前端变量选择器能按类型过滤
- 用户调试一次后，下游节点立即能看到上游节点输出的字段名补全
- 后端 mypy / 前端 lint 在工作流模块内零 `Any` / `unknown`（IO 边界用 `WorkflowValue`）

---

## High-Level Design

### 类型表达：TypeSpec
新增统一的类型描述结构，前后端镜像。

```python
# backend/app/services/workflow/types.py（新增）
class TypeSpec(BaseModel):
    kind: Literal["string", "number", "boolean", "object", "array",
                  "file", "image", "files", "images", "null"]
    item: TypeSpec | None = None                # array 元素类型
    fields: dict[str, TypeSpec] | None = None   # object 字段类型
    nullable: bool = False
    source: Literal["declared", "inferred"] = "declared"
    sample: Any | None = None                   # 仅推断时保留一份样本（截断）
```

```ts
// frontend/lib/workflow/type-spec.ts（新增）
export type TypeSpec = {
  kind: 'string'|'number'|'boolean'|'object'|'array'|'file'|'image'|'files'|'images'|'null'
  item?: TypeSpec
  fields?: Record<string, TypeSpec>
  nullable?: boolean
  source?: 'declared' | 'inferred'
  sample?: unknown
}
```

不引入 JSON Schema —— 体量过重、UI 成本高，且只需要"字段名 + 嵌套类型"。

### 数据流（节点间）

```
[上游节点 outputs: dict[str, WorkflowValue]]
    ↓ ExecutionContext.set_node_outputs (msgpack 序列化)
[Redis: workflow:run:{id}:outputs hash]
    ↓ ExecutionContext.get_node_output (msgpack 反序列化)
[原生 dict/list/str/int/float/bool]
    ↓ resolve_variable_ref：单引用直接返回原值；插值才 to_text(value)
[下游节点 inputs：保持原生类型]
```

### Schema 推断与存储
- 节点声明类型存于 `workflow.definition.nodes[].data.config.outputs[].typeSpec`
- 推断结果存于 `workflow.definition.nodes[].data.inferredSchema: dict[outputName, TypeSpec]`
- 调试运行结束后，Orchestrator 调用 `SchemaInferer.merge_run_outputs(workflow_id, run_id)` 把本次 run 的 NodeExecution.outputs 推断出的 TypeSpec 与已有 inferredSchema 做 union merge，写回 workflow definition。
- 前端 `getAvailableVariables` 在收集变量时优先 declared，缺失回落 inferred。

### 序列化层

| 用途 | 当前 | 新方案 |
|------|------|--------|
| ExecutionContext Redis 存储 | json.dumps | **msgpack**（保留 LazyStream 占位符） |
| Stream 事件 (SSE / Pub-Sub) | json.dumps | **保留 json**（前端消费需要 JSON） |
| Cache 层 (cache.py) | json.dumps(default=str) | **msgpack**（同步去掉 default=str） |
| Celery 任务参数 | json | **保留 json** |
| 数据库 JSONField | JSON | **保留** |
| API 出参 | Pydantic dump | **保留** |
| Answer 节点输出 | json.dumps | **保留**（显示语义） |
| Template/LLM prompt 插值 | str() | **新增 to_text(value)**：dict/list → json.dumps，其他 → str() |

### 类型清理
- 引入 `WorkflowValue = Union[str, int, float, bool, None, list["WorkflowValue"], dict[str, "WorkflowValue"]]` 作为节点 IO 的统一标注。
- `dict[str, Any]` → `dict[str, WorkflowValue]`（仅在 IO 边界）。
- 前端 `Record<string, unknown>` 在 IO 边界改为 `Record<string, WorkflowValue>`；节点 config 类型改为 discriminated union。

---

## Implementation Plan

### Stage 1: TypeSpec 与 msgpack 序列化层
**目标**：新增 TypeSpec、`WorkflowValue`、msgpack 序列化、`to_text` helper，**不改任何现有节点 IO 行为**，可单独发布并跑通现有测试。

- **新增**：`backend/app/services/workflow/types.py`、`backend/app/services/workflow/serialization.py`
- **修改**：`context.py`（170/177/214/239/429/443）、`cache.py`（json 替换）、`pyproject.toml`（msgpack）
- **插值路径改用 to_text**：`context.py:296,304,392-406`、`executors/answer.py:23-31`
- **验证**：新增 `test_serialization.py`、`test_types.py`；现有 `tests/services/workflow` 全绿

### Stage 2: 节点 IO 摆脱字符串化
**目标**：`resolve_inputs` 与节点 executor 之间一律走原生类型。

- 修改 `executor.py:92-154` `resolve_inputs`
- 逐节点修改：`executors/llm.py:104-113`（去 flatten）、`executors/condition.py:28-40,224`（类型归一）、`executors/variable.py`（parameter_extractor）、`executors/iteration.py:170,223,316`（fail-fast）、`executors/code.py`（输出可序列化检查）
- 统一约定：不再 `json.loads(input)` 兜底；类型不匹配 BusinessError
- **验证**：新增 `test_native_passthrough.py`，现有用例适配

### Stage 3: NodeExecutor 输出 schema 声明
**目标**：每个 executor 的 `get_output_variables` 返回带 TypeSpec 的声明。

```python
def get_output_variables(self, config: dict) -> list[NodeOutputDecl]:
    # NodeOutputDecl(name: str, type: TypeSpec, description: str | None)
```

- llm / code / parameter_extractor / iteration / loop / variable_aggregator 等逐一适配
- code 节点缺省类型 fail-fast（UI 强制选择）
- 扩展 `backend/app/schemas/workflow.py`，无需 DB 迁移
- **验证**：`test_output_schema.py`

### Stage 4: 调试运行后的 schema 推断与持久化
**目标**：每次 debug run 结束，把节点真实输出推断出的 TypeSpec 合并写回。

- 新增 `backend/app/services/workflow/schema_inference.py`：`infer_run_schemas`、`merge_into_workflow`
- 接入点：`orchestrator.py` 工作流执行结束的回调；只在 `WorkflowRun.mode == "debug"` 触发
- **验证**：`test_schema_inference.py`，含两次 debug 后字段并集断言

### Stage 5: 前端 TypeSpec 镜像与变量选择器升级
**目标**：前端类型与后端对齐；变量选择器按类型过滤。

- 新增 `frontend/lib/workflow/type-spec.ts`
- 修改 `node-config/types.ts`：`AvailableVariable.type` → `typeSpec`
- 修改 `lib/api/workflows.ts`：NodeData 改为 discriminated union；新增 `inferredSchema`
- 修改 `node-config-drawer.tsx:339-890` 的 `getAvailableVariables`：merge declared+inferred；增 `acceptType` 过滤
- 修改 `node-config/variable-selector.tsx`：根据 `acceptType` 灰显
- **验证**：浏览器手动跑

### Stage 6: 前端节点配置面板的 schema UI
**目标**：用户能查看推断结果、给 object 输出手填字段、必要时 reset 推断。

- 新增 `node-config/type-spec-editor.tsx`
- 修改 `node-config/configs/code-node-config.tsx` 等：object/array 时展开字段编辑器；显示推断字段；"清空推断"按钮
- 修改 `workflow-run-drawer.tsx`：调试结束触发 refetch
- **验证**：浏览器手动跑

### Stage 7: 清理 `Any`、删除兼容代码、文档

**已完成**：
- 删除：`context.py` 中 `str(value)` 兜底（Stage 1）、`executors/iteration.py` 的
  string→list 隐式 `json.loads`、`executors/variable.py` 的 string→object 隐式
  `json.loads`（Stage 2）
- 文档：新增 `docs/dev/design/app-platform/WORKFLOW_TYPE_SYSTEM.md`；
  `WORKFLOW_ENGINE_ARCHITECTURE.md` 加链接到类型系统章节；
  `WORKFLOW_ENGINE_STATUS.md` 新增 Phase 6 段落

**显式延后**：后端 `services/workflow/` 范围 `Any` 全量替换、前端
`Record<string, unknown>` / `as any` 全量替换。两者各自有几十到上百处，
逐项替换需要单独立项。新代码（`types.py` / `serialization.py` /
`schema_inference.py` / `type-spec.ts` / `type-spec-editor.tsx`）已遵循
新约定；存量替换列入下一轮专项 `workflow-types-followup.md`（待建）。

### Stage 8: 硬切换执行
- `WorkflowDefinition` 增加 `schema_version: int = 2`
- 加载旧 workflow（无 schema_version 或 < 2）时 UI 提示 + 禁用运行
- 提供 `scripts/clear_workflow_runtime.py` 清理 Redis（`workflow:run:*`、`wf:cache:*`）
- 写 changelog

---

## Testing Strategy

### Happy path
- start → code(`[{a:1},{a:2}]`) → iteration(item) → template(`{{ item.a }}`) → answer：全程原生 list/dict
- 调试一次后变量选择器有字段补全

### Error / fail-fast
- 输出类型 `object{a: number}` 实际返回 `{a: "x"}`：软类型不抛错；推断 schema 记录 union；UI warning
- iteration 输入非 array：BusinessError（i18n）
- 选了 string 但目标 array：UI 灰显并提示

### Regression
- `tests/services/workflow/` 全套通过
- 旧工作流加载提示且不可运行（不可崩溃）
- LLM、tool、agent 三类节点的 e2e 调试链路通过

### 新测试
- `test_serialization.py`、`test_types.py`、`test_native_passthrough.py`、`test_output_schema.py`、`test_schema_inference.py`
- 前端：手动浏览器验证

---

## Risks & Mitigation

| 风险 | 影响 | 缓解 |
|------|------|------|
| msgpack 不支持的对象类型（datetime、自定义类）静默丢失 | 数据错误 | `serialization.dumps_value` 前显式 normalize；遇不可序列化 fail-fast |
| 推断 schema 把不稳定字段写入 schema | UI 噪声 | 仅 debug 触发；提供"清空推断"按钮 |
| 节点输出类型声明缺失，强制要求让用户不耐烦 | 体验下降 | 仅 code / parameter_extractor 强制；其他节点 executor 内部声明 |
| 大规模替换 `Any` 引起 mypy / lint 雪崩 | 拖慢交付 | 拆 PR，按子目录 / 节点逐个清理 |
| 硬切换导致用户丢失历史工作流 | 用户体验 | 提前公告；提供"导出旧定义"接口 |
| LazyStreamResult 占位符在 msgpack 中需特殊处理 | 流式输出失效 | `serialization` 层显式识别；单测覆盖 |

---

## Verification

完整验收：

1. `cd backend && uv sync && uv run ruff check . && uv run ruff format --check . && uv run mypy app/`
2. `cd backend && uv run pytest tests/services/workflow -v` 全绿
3. `cd frontend && bun install && bun run lint && bun run build` 无错误
4. `docker-compose -f deploy/docker-compose.dev.yml up -d` 起依赖
5. 浏览器场景：
   - start → code(`return [{"a":1,"b":"x"},{"a":2,"b":"y"}]`，声明 `array<object{a:number,b:string}>`) → iteration(items 选 code.result) → template(`{{item.a}} - {{item.b}}`) → answer
   - 第一次调试：观察 answer 输出 `1 - x` 与 `2 - y`，不是 `[object Object]` 或 JSON 字符串
   - 关闭 drawer 重开 iteration 输入选择器：除 array 外被灰显
   - code 节点声明输出类型为空时保存：UI 报错"必须声明输出类型"
6. 旧工作流加载：用 dev DB 一条 schema_version<2 的 workflow，刷新后 UI 显示提示且禁用运行按钮
