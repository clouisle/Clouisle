# In-Chat Tool Approvals & Approvals Center Removal Design Document

## Background & Goals
- **Problem**: 之前的审批方案设计了独立的“审批中心”页面（`/app/capabilities/approvals`），在 Agent 对话中遇到工具审批时，聊天卡片仅提供一个跳转链接“前往审批中心”，强迫用户跳出对话流。用户明确决定采用方案 B：彻底移除独立的审批中心页面，工具确认完全收敛在 Chat 对话卡片中原地完成（一键“允许 / 拒绝”并自动恢复执行）；对于需要团队其他人审批的情况，复用通知中心，点击通知直接跳转进入对话卡片。
- **Success Criteria**:
  1. **Chat 就地确认**：在 `PendingToolApprovalCard` 中直接提供【允许】与【拒绝】按钮，点击后立即调用决策接口并原地唤醒 AgentRun 继续执行。
  2. **直接执行决策接口**：后端增加 `POST /api/v1/tool-executions/{execution_id}/decision` 接口，支持由 execution_id 直接提交审批决策，无需前端多步换取内部 request_id。
  3. **移除独立审批中心**：删除 `frontend/app/(platform)/app/capabilities/approvals/` 路由及下辖面板，移除 Capabilities 工具栏中的外跳按钮。
  4. **全套自动化测试通过**：后端针对 execution 决策接口和审批流单测通过，前端组件及类型检查通过。

## High-Level Design
1. **后端 API (`backend/app/api/v1/endpoints/tool_approvals.py`)**：
   - 在 `execution_router`（挂载于 `/api/v1/tool-executions`）下新增 `POST /{execution_id}/decision`：
     - 校验调用者身份；
     - 查找与该 execution 关联且状态为 `PENDING` 的审批关卡；
     - 调用 `decide_approval` 记录审批结果并调度 Agent 恢复执行（`schedule_agent_run_approval_resume`）；
     - 返回最新的执行状态与决策记录。
2. **前端 API (`frontend/lib/api/tool-approvals.ts`)**：
   - `toolExecutionsApi` 增加 `decide(executionId, input)` 方法。
3. **前端卡片改造 (`frontend/components/tool-interactions/pending-tool-approval-card.tsx`)**：
   - 增加 `submitting` 状态和 `handleDecision(decision)` 方法；
   - 在 `execution.status === 'awaiting_approval'` 时渲染【允许】和【拒绝】按钮；
   - 点击后显示 loading 状态，成功后提示 toast 并调用 `onRefreshRun()` 刷新会话。
4. **移除独立审批中心页面**：
   - 移除 `frontend/app/(platform)/app/capabilities/approvals/`；
   - 移除 `frontend/app/(platform)/app/capabilities/page.tsx` 中的“审批中心”入口按钮；
   - 移除 `tool-test-panel.tsx` 中的审批中心外链。

## Implementation Plan

### Stage 1: Backend direct execution decision endpoint and notification deep-linking
- **Files modified**: `backend/app/api/v1/endpoints/tool_approvals.py`, `backend/tests/services/test_tool_approvals.py`
- **Specific logic**:
  - 在 `execution_router` 增加 `POST /{execution_id}/decision`；
  - 编写单测验证通过 execution_id 直接批准/拒绝并正确驱动 AgentRun 恢复。

### Stage 2: Inline Approve/Reject actions in PendingToolApprovalCard and auto-resume
- **Files modified**: `frontend/lib/api/tool-approvals.ts`, `frontend/components/tool-interactions/pending-tool-approval-card.tsx`, `frontend/components/tool-interactions/pending-tool-approval-card.test.tsx`
- **Specific logic**:
  - 在 `toolExecutionsApi` 增加 `decide`；
  - 在 `PendingToolApprovalCard` 增加原地允许与拒绝操作；
  - 更新组件单测覆盖原地允许与原地拒绝交互。

### Stage 3: Remove standalone approvals center page and obsolete navigation links
- **Files modified**: 删除 `frontend/app/(platform)/app/capabilities/approvals/` 目录；修改 `frontend/app/(platform)/app/capabilities/page.tsx` 与 `tool-test-panel.tsx`
- **Specific logic**:
  - 移除多余的审批中心页面代码；
  - 移除所有指向 `/app/capabilities/approvals` 的链接。

### Stage 4: Automated verification and test suite alignment
- **Files modified**: 相关测试文件
- **Specific logic**:
  - 运行后端 pytest 套件和前端 bun test 套件，确保所有类型与测试 100% 通过。
