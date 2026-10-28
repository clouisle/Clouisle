# Caller-Only Tool Confirmation Design Document

## Background & Goals

角色和指定用户审批增加跨用户授权、通知和状态管理复杂度；现有代码工具界面可保存这些策略，但运行时忽略，存在未经审批即执行的风险。产品改为仅保留交互式 Agent 对话中的调用者确认，不将其宣称为独立审核。

成功标准：调用前明确暂停，只有调用者可批准或拒绝；批准绑定原参数并恢复一次；非交互入口不隐式获得确认；角色和指定用户不再可配置或创建；历史配置与待处理执行不能转换为放行或由发起者代批。

## High-Level Design

保留现有 durable ToolExecution、调用者确认卡与决策记录，移除外部审批受众及不再使用的配置、管理和通知入口。工具连接身份与权限保持独立。交互式 Agent chat 支持 Agent 级确认和 MCP 操作策略确认；工作流、工具测试、API Key、嵌入及后台入口保持现有不请求确认的契约，但必须对遗留外部审批配置失败关闭，不得因新契约而绕过。

历史数据必须可重复处理：识别工具策略及持久策略层中任意嵌套 `user`/`team_role` 关卡，保留原始配置并阻止关联执行，提示管理员重新配置，不能默认替换成 caller 或 allow；取消包含外部关卡的未决执行及其待处理关卡，避免旧运行自动恢复。已完成的历史记录保留可审计性。迁移需覆盖并发、幂等、数据库启动和无表环境，明确升级与回滚。

## Implementation Plan

### Stage 1: Inventory and legacy-data cutover
- **Files modified**: `backend/app/core/` migration and bootstrap entrypoints, `backend/app/models/tool_approval.py`, relevant migration tests.
- **Specific logic**: inspect actual persisted `tools.approval_policy`, policy definitions and pending execution/request states. Implement idempotent fail-closed handling of external audiences, preserving original policy evidence; cancel pending external gates and owning execution atomically without resuming work. Avoid schema changes that invalidate historical completed records or rolling old processes.
- **Validation**: real database migration tests for nested external gates, mixed caller/external gates, pending vs terminal rows, repeat execution and concurrency; confirm nothing is silently approved or executed.

### Stage 2: Caller-only backend execution and contracts
- **Files modified**: `backend/app/schemas/tool_approval.py`, `backend/app/services/tool_execution.py`, `backend/app/services/tool_approvals.py`, approval endpoints and related tests.
- **Specific logic**: accept only caller gates on new policy writes; reject legacy external gates with actionable configuration error at every tool type and execution entrypoint before side effects; enforce decision authorization against execution actor; preserve current confirmation binding, denial, idempotency and resume semantics. Remove unused external-recipient management only after inventorying callers and retained audit reads.
- **Validation**: interactive caller approval and rejection; non-caller denial; code/HTTP/MCP tool policy cannot be bypassed; non-interactive scope and fixed connections remain correct; invalid legacy policies fail before invocation.

### Stage 3: Frontend and API cleanup
- **Files modified**: `frontend/components/tools/tool-policy-editor.tsx`, tool dialogs, API types, approval card and `frontend/i18n/{en,zh,types}`.
- **Specific logic**: eliminate role/user selection, self-approval and multi-audience UI; expose caller-only confirmation consistently; never normalize a saved external gate to caller or allow. Surface the legacy reconfiguration error. Remove obsolete API clients/routes only when no supported caller depends on them.
- **Validation**: component tests for new/edit flows, nested MCP overrides, legacy invalid policies, caller card and localization; TypeScript and focused lint.

### Stage 4: Documentation and end-to-end proof
- **Files modified**: applicable `docs/guide/` API, user and operator guides, changelogs; implementation index.
- **Specific logic**: document interactive-only confirmation, legacy remediation, no silent auto-approval, and rollback limitations. Update all affected contracts and remove stale multi-audience claims.
- **Validation**: focused backend and frontend behavior suites; exercise actual execution path using a throwaway isolated script without starting services; verify migration failure paths and idempotence, remove temporary artifacts. Existing running services/browser are not started without explicit permission.
- **Observed**: 79 focused backend tests passed, including SQLite migration and legacy claim rejection; 11 policy-editor tests passed, TypeScript, targeted ESLint/Ruff and i18n catalog checks passed. An isolated SQLite invocation exercised caller approval to ready and rejection/cancellation of a previously approved legacy execution. No browser, running service, PostgreSQL concurrency or rolling deployment was exercised.

## Testing Strategy

Happy paths: caller accepts and rejects, correct single execution and resume. Negative paths: other user decision, unconfigured/invalid legacy policy, revoked connection, non-interactive context and tool definition change. Regression: MCP operation overrides, connection identity isolation, replay/expiry, import/export and existing execution history. Tests assert consumer-visible behavior, not forwarding or implementation text.

## Risks & Mitigation

- Legacy roles/users cannot be safely translated into caller approval: preserve and fail closed until an administrator explicitly edits the policy; cancellation of pending work is safer than accidental side effects.
- Old processes during rolling deployment may create old gates: use backward-compatible schema and guard enforcement; deploy migration and application in a coordinated manner, audit any old workers before cutover.
- Rollback cannot reactivate cancelled executions automatically. Restore code/config from backup; require users to initiate new runs, never replay uncertain side effects.
