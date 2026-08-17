# Workflow Pause Node Design Document

## Background & Goals

工作流目前是"启动后一次性跑完"的模型：Celery 任务在单个 worker 里顺序执行完所有节点，`RunStatus`/`NodeStatus` 没有 waiting 态，无法在中间停顿等待外部输入。

需求：新增**暂停（pause）节点**——工作流执行到该节点时暂停，外部（API 调用方/人工）通过提交接口**传入一组变量值**，恢复后这些值注入执行上下文，下游节点可引用。**人工审批是其中的一种模式**：审批 = pause 节点的 approval 模式，提交 `decision` 变量（approved/rejected）+ 备注，rejected 使 run 失败。

### Success Criteria

- 发布版与调试运行都能在 pause 节点暂停，run 状态显示 waiting
- 提交变量后自动恢复执行（重新调度 Celery 任务），提交的值以节点输出形式供下游引用（`{{node_id.var}}`）
- 审批模式：approve 继续、reject 使 run 失败；审批人/意见有审计记录
- 提交接口有权限校验与变量 schema 校验
- 前端：画布可添加/配置 pause 节点（variables / approval 两种模式）；运行页展示 waiting 状态与提交/审批操作
- 前后端全量测试通过，覆盖率门槛不降

## High-Level Design

```
运行任务 (run_workflow_task)
  → orchestrator.run_with_run_id
    → plan.stages 顺序执行
      → pause 节点 executor
        ├─ 无已提交值 → 挂起：run=WAITING, node=WAITING, 建 pause_request(pending), 续 Redis TTL → 任务正常退出
        └─ 已提交值 → 输出提交的变量 → 继续后续节点（approval 模式 decision=rejected → run 失败）

提交 (submit API, 权限 = workflow 写权限)
  → 校验 run.status==WAITING + request pending + 变量 schema
  → 更新 request（values/comment/submitted_by/status=submitted）+ run（WAITING → RUNNING）
  → resume_workflow_task.delay(run_id)

恢复任务 (resume_workflow_task)
  → orchestrator.run_with_run_id(resume=True)
    → 重建 context（Redis，挂起时已续 TTL）
    → 重建 plan
    → 跳过已完成的节点（从 node_executions 构建 executed/skipped 初始集；复用 WAITING 的 node_execution）
    → pause 节点重跑：读到已提交值 → 输出变量 → 继续
```

### 节点配置

```jsonc
// pause 节点 data.config
{
  "mode": "variables" | "approval",
  // variables 模式：声明需外部传入的变量
  "inputVariables": [
    { "name": "target_price", "type": "number", "required": true, "description": "目标价格" }
  ],
  // approval 模式：固定 decision/comment 变量（审批 UI 驱动）
  "title": "请审批这笔付款",
  "description": "金额超过阈值，需要人工确认"
}
```

- 输出：提交的变量（approval 模式输出 `decision`/`approved`/`comment`）；下游用 `{{pause节点id.变量名}}` 或节点输出选择器引用
- 审批模式 `decision=rejected` → executor 返回 `workflow_approval_rejected` 错误 → run 标记失败（错误信息含审批意见入口）

### 模块

| 模块 | 职责 |
|---|---|
| `models/workflow.py` | `RunStatus.WAITING`、`NodeStatus.WAITING`；新模型 `WorkflowPauseRequest`（表 `workflow_pause_requests`） |
| `core/init_data.py` | `workflow_pause_requests` 建表（对照 workflow_runs 模式） |
| `services/workflow/executor.py` | `ExecutionResult.waiting: bool = False` |
| `services/workflow/executors/pause.py` | `PauseNodeExecutor`（variables/approval 两模式；pending → waiting；已提交 → 输出变量） |
| `services/workflow/orchestrator.py` | 挂起/恢复：`NodeWaitingError`、`run_with_run_id(resume=...)`、`_execute` 恢复模式（跳过已执行节点、复用 WAITING node_execution）、挂起时续 Redis TTL |
| `tasks/workflow.py` | `resume_workflow_task`（重新调度恢复执行） |
| `api/v1/endpoints/workflows.py` | 提交端点 `POST .../pause-requests/{id}/submit`（校验 + 审计 + 调度恢复） |
| `services/workflow/errors.py` | `NodeWaitingError`（正常挂起信号） |
| 前端 | 节点注册/渲染/配置面板/validator、run waiting 状态展示、变量提交 UI（approval 模式渲染审批按钮）、i18n |

### 数据流

- 挂起信息持久化在 `workflow_pause_requests`（run_id + node_execution_id + node_id + mode + status pending/submitted + values + comment + submitted_by + 时间戳）——审批审计即该表记录
- 已执行节点输出双份：Redis context（`workflow:run:{run_id}:outputs`，TTL 24h，挂起时续期）+ `workflow_node_executions.outputs`（DB）
- 恢复优先用 Redis context（挂起时续 TTL 保证存活）；如 Redis 数据丢失，pause 节点之前的执行状态从 node_executions 重建不可行（缺全局变量）——产品约束：暂停等待窗口 ≤ Redis TTL，超时后 run 需手动取消重跑（记录在 Risks）

## Implementation Plan

### Stage 1: 后端状态机与挂起/恢复核心
- **Files modified**: `backend/app/models/workflow.py`、`backend/app/services/workflow/executor.py`、`backend/app/services/workflow/errors.py`、`backend/app/services/workflow/executors/pause.py`（新）、`backend/app/services/workflow/orchestrator.py`、`backend/app/tasks/workflow.py`、`backend/app/core/init_data.py`
- **Specific logic**:
  - `RunStatus.WAITING = "waiting"`、`NodeStatus.WAITING = "waiting"`（CharEnumField 存字符串，无需 ALTER）
  - `ExecutionResult.waiting: bool = False`
  - `NodeWaitingError`（正常挂起信号，不进错误翻译）
  - `WorkflowPauseRequest` 模型 + `PauseRequestStatus`（pending/submitted/cancelled）
  - `PauseNodeExecutor`：读最新 request；无 → 创建 pending + waiting；pending → waiting；submitted → 输出 values（approval 模式 decision=rejected → error）
  - `orchestrator.run_with_run_id(resume=...)`：resume 从 node_executions 构建 executed/skipped 初始集；`_execute_node` 复用 WAITING 记录、返回 waiting → `_execute` 抛 `NodeWaitingError` → run_with_run_id 捕获 → run=WAITING + 续 Redis TTL + 正常返回；approval reject → run failed（走既有失败路径）
  - `resume_workflow_task(run_id)`：校验 run.status==WAITING → resume 执行
  - `init_data.py`：`workflow_pause_requests` 建表
- **Validation**: `test_pause_executor.py`（variables/approval 两模式、pending/submitted 分支）+ `test_orchestrator_pause.py`（挂起 → waiting 持久化 → resume → 完成；reject → failed）+ 既有 workflow 套件回归

### Stage 2: 提交 API 与恢复调度
- **Files modified**: `backend/app/api/v1/endpoints/workflows.py`、`backend/app/schemas/workflow.py`、`backend/app/tasks/workflow.py`
- **Specific logic**:
  - `POST /api/v1/workflows/{workflow_id}/runs/{run_id}/pause-requests/{request_id}/submit`：body `{values, comment?}`；校验 run 存在且 status==WAITING、request pending、`check_workflow_access(require_write=True)`；按节点配置校验变量（required/类型/approval 模式 decision ∈ {approved, rejected}）；更新 request + node_execution（waiting → success，outputs=values）+ run（WAITING → RUNNING）；`resume_workflow_task.delay(run_id)`；AuditLogService 记录
  - 取消语义：run 在 WAITING 时被 cancel → cancelled；提交接口幂等拒绝（run 非 WAITING → 冲突）
- **Validation**: API 测试（权限、schema 校验、幂等、approval reject 路径）+ 审计断言

### Stage 3: 前端节点（画布/配置/validator）
- **Files modified**: `frontend/app/(platform)/app/apps/workflow/[id]/_components/constants.ts`、`add-node-popover.tsx`、`nodes/pause-node.tsx`（新）、`node-config/configs/pause-node-config.tsx`（新）、`node-config-drawer.tsx`、`workflow-validator.ts`、`i18n/*/workflow.json`
- **Specific logic**: 节点注册（logic 分组，图标 PauseCircle）、画布渲染（waiting 样式）、配置面板（mode 切换：variables 变量列表编辑器 / approval 标题+说明）、validator（配置校验 + **禁止在 iteration/loop body 内**——body 内挂起点需重建迭代作用域，二期）、`get_output_variables`（声明的变量）
- **Validation**: 节点/配置/validator 测试

### Stage 4: 前端运行页（waiting 状态 + 提交/审批 UI）
- **Files modified**: `frontend/app/(chat)/run/[id]/_components/workflow-run-page.tsx`、`workflow-run-drawer.tsx`（如需要）、`frontend/lib/api/workflows.ts`、`frontend/i18n/*/run.json`
- **Specific logic**: run status waiting 翻译（"等待输入/审批"）、live/history 视图 waiting 展示 + 提交表单（variables 模式）/审批按钮（approval 模式：approve/reject + 备注）+ 已提交记录展示；embed 模式隐藏提交操作
- **Validation**: run 页测试（waiting 渲染、提交/审批交互）

### Stage 5: i18n 与全量验证
- **Files modified**: `frontend/i18n/*/*.json`、后端 `messages.po`/`i18n_legacy.py`
- **Validation**: 前后端全量测试、tsc、ruff/mypy、i18n lint、覆盖率门槛

### Stage 6: Code-review remediation
- **Files modified**: `backend/app/api/v1/endpoints/workflows.py`, `backend/app/api/workflow_access.py`, `backend/app/services/workflow/{orchestrator.py,stream.py,pause_approvers.py}`, `backend/app/services/workflow/executors/pause.py`, `backend/app/tasks/workflow.py`, `backend/app/core/init_data.py`, `frontend/components/chat/pause-request-actions.tsx`, `frontend/app/(chat)/run/[id]/_components/workflow-run-page.tsx`, `frontend/app/(platform)/app/apps/workflow/[id]/_components/workflow-run-drawer.tsx`, and focused regression tests.
- **Specific logic**:
  - Make configured approvers an authorization alternative to private-workflow visibility without weakening generic workflow access; resolve configured IDs only when they are still active team members.
  - Serialize `requireAllApprovals` updates and claim a waiting run atomically before resuming. Any resume setup failure must persist a terminal failure.
  - Treat `NodeWaitingError` as a normal state in both orchestrator entry points; replay historical stream events without treating an old pause as the current terminal event.
  - Validate non-empty required pause values; never persist raw unresolved templates or non-basename upload paths; repair startup DDL ordering and table names.
  - Link pause notifications to the workflow runner, remove deep links with an explicit path, and render `waiting` from all streaming run surfaces.
- **Validation**: focused backend API/orchestrator/task/stream/pause tests; focused frontend run-page/drawer/action tests; formatter/type checks for changed code.

## Testing Strategy

- Happy path: 发布版 run → pause 挂起（waiting）→ 提交变量 → 自动恢复 → success；下游引用提交的变量；approval 模式 approve → 继续
- Error path: approval 模式 reject → run failed；缺失必填变量 → 提交 400；无权限提交 → 403；run 非 waiting 时提交 → 冲突；重复提交 → 幂等拒绝
- 取消路径：waiting 中 cancel → cancelled；取消后提交不生效
- Regression: 既有 workflow 全套（orchestrator/task/API/executors）+ 前端 workflow 组件套件

## Risks & Mitigation

- **Redis context TTL 24h**：暂停等待超过 24h 丢执行状态。缓解：挂起时续 TTL；产品约束暂停窗口 ≤ 24h；超时后 run 只能取消重跑（二期做超时自动拒绝/提醒）
- **多 worker 并发恢复**：提交接口原子条件更新（仅 WAITING → RUNNING 才调度恢复）；恢复任务入口校验 run.status，避免重复恢复
- **迭代/循环内 pause**：MVP 禁止（validator 报错）——body 内挂起需重建迭代作用域；二期支持
- **LazyStreamResult**：挂起时未消费的 lazy 输出在恢复任务中无法重建——MVP 接受（暂停前避免依赖未消费 lazy 输出），文档记录
- **Rollback**: 不发布 pause 节点（前端不注册）即可回退；后端新状态/新表不影响既有 run

## 已确认决策（用户选定）

- 通用暂停 + 变量传递机制（方案 B：持久化挂起 + 重新调度恢复），审批是 pause 节点的 approval 模式，走同一路径。
- reject 语义：run 标记失败（条件分支二期）。
- 提交/审批权限：配置 `approverIds` 时仅现存、激活的团队成员与 superuser；未配置时回退工作流所有者与团队 owner/admin。
