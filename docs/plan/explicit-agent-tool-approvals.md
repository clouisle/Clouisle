# Explicit Agent Tool Approvals Design Document

## Background & Goals
- **Problem**: 之前的审批实现使用了复杂的 4 层策略继承（站点/团队/入口/工具），并在内置工具中通过 `ToolConcurrency.SHARED` 和只读列表进行启发式推测推导。同时让 Workflow 中的工具节点也参与审批，导致自动化工作流被中断或遇到容器审批报错。用户明确指出：只有 Agent 对话调用工具才需要审批，Workflow 中不需要；且工具是否需要审批必须由用户在 Agent 编排中显式决定，不应由后台推测判断。
- **Success Criteria**:
  1. **纯用户显式决定**：在 Agent 编排配置（`agent.tools_config`）中，为每个绑定的工具提供明确的“调用前需确认”开关（`require_approval: bool`），默认 `False`。
  2. **Workflow 完全免审批**：Workflow 中的工具节点（以及 Workflow 内运行的 Agent 节点）作为自动化管道，工具调用直接执行，绝不挂起等待审批。
  3. **移除推测逻辑**：移除内置工具中关于并发只读/只写的启发式策略推测（如 `_approval_policy`、`ToolConcurrency.SHARED` 推导），工具自身不预设强制审批。
  4. **保留 Chat 审批体验**：Agent 对话调用开启了 `require_approval` 的工具时，仍正常生成审批单并在前端 Chat 界面展示确认卡片，点击确认后恢复对话。

## High-Level Design
1. **Agent 编排与 Schema**：
   - `ToolConfig`（`backend/app/schemas/agent.py` 与 `frontend/lib/api/agents.ts`）新增字段：`require_approval: bool = False`。
   - 前端 Agent 编排工具列表（`tool-selector.tsx`）增加“调用前确认”直观开关。
2. **执行边界裁剪 (`tool_execution.py`)**：
   - 检查调用来源：
     - 若 `entrypoint == ExecutionEntrypoint.WORKFLOW` 或来源为 Workflow：强制跳过审批，直接执行。
     - 若 `entrypoint == ExecutionEntrypoint.CHAT`（交互式 Agent 对话）：
       根据 `agent.tools_config` 中该工具的 `require_approval` 布尔值决定：
       - `require_approval == True`：挂起并创建审批单 `PendingToolApproval`，交由 Chat 前端卡片由用户点击确认；
       - `require_approval == False`：直接执行，不走审批。
3. **内置工具启发式清理 (`builtin_tools.py`)**：
   - 清理根据 `ToolConcurrency.SHARED` 或硬编码列表给内置工具塞入 `require_approval` 策略的推测代码，内置工具默认统一为免审批，完全由使用它的 Agent 决定是否需确认。

## Implementation Plan

### Stage 1: Agent ToolConfig require_approval schema and execution boundary bypass for workflows
- **Files modified**: `backend/app/schemas/agent.py`, `backend/app/services/tool_execution.py`, `backend/app/services/workflow/executors/tool.py`
- **Specific logic**:
  - `ToolConfig` 增加 `require_approval: bool = False` 字段；
  - `execute_stored_tool` / `execute` 在 `context.entrypoint == ExecutionEntrypoint.WORKFLOW` 或非交互执行时直接放行；
  - 清理 `WorkflowToolNodeExecutor` 中的审批挂起分支，使工作流工具节点纯自动执行。

### Stage 2: Eliminate heuristic concurrency/read-only approval deduction on builtin tools
- **Files modified**: `backend/app/services/builtin_tools.py`, `backend/app/services/agent_tool_execution.py`, `backend/app/api/v1/endpoints/chat_tools.py`
- **Specific logic**:
  - 移除 `_approval_policy` 和 `_internal_approval_policy` 中的启发式推测逻辑；
  - 在 Agent 运行时，读取 `agent.tools_config` 中的 `require_approval`；
  - 只有明确标记为 `require_approval=True` 的工具才在 Chat 中触发审批。

### Stage 3: Frontend Agent orchestration per-tool confirmation switch and localization
- **Files modified**: `frontend/lib/api/agents.ts` (or `tools.ts`), `frontend/app/(platform)/app/apps/[id]/_components/tool-selector.tsx`, `frontend/i18n/en/agents.json`, `frontend/i18n/zh/agents.json`
- **Specific logic**:
  - Agent 编排界面的工具卡片中展示“调用前确认 / Require confirmation”开关；
  - 切换开关更新当前工具项的 `require_approval` 字段并保存。

### Stage 4: Automated verification and regression test alignment
- **Files modified**: `backend/tests/services/test_builtin_tools.py`, `backend/tests/services/workflow/test_tool_node_approval.py`, `frontend/app/(platform)/app/apps/[id]/_components/tool-selector.test.tsx`
- **Specific logic**:
  - 更新测试用例，验证 Agent 对话中只有显式标记 `require_approval=True` 才需要审批；
  - 验证 Workflow 中工具节点始终自动执行且不触发审批；
  - 验证前端切换开关能正确更新 `tools_config`。
