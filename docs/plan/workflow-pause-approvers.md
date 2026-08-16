# Workflow Pause Approvers + Notification Design Document

## Background & Goals
- Problem: 审批(approval)与输入(variables)提交端点只校验 `check_workflow_access(require_write=True)`,任何工作流 owner / team admin / superuser 都能处理。无法限定"哪些人能处理",也没有待办通知,处理人只能主动刷新运行页。
- Success criteria:
  1. pause 节点可配置可选的 `approverIds`(团队用户列表);配置后仅列表内用户 + superuser 可提交,其余返回 403。
  2. 未配置时回退现状(owner + team admin + superuser 可处理),不破坏既有流程。
  3. 运行进入等待时,站内信 + 已配置外部渠道通知处理人,带运行页深链。
  4. 运行页审批面板对无权限用户禁用提交并提示处理人。

## High-Level Design
- 配置载体:节点 `data.pauseConfig.approverIds: string[]`(前端编辑器写入,运行快照 `context_snapshot` 天然保留)。老运行无此字段 → 回退。
- 处理人解析:`resolve_pause_approver_ids(workflow, config)` 单一事实来源,供通知与提交校验共用:
  - `config.approverIds` 非空 → 直接使用(逐项 `UUID(str)` 归一);
  - 空/缺失 → 工作流 `created_by_id` + 团队 `owner`/`admin` 成员(即现有写权限集合)。
- 通知:`AutoNotificationService.send_to_user`(站内信 + 外部渠道),新类型 `workflow.pause_pending`,文案走 Babel `t()`,`link_url=/run/{run_id}`。
- 触发点:`PauseNodeExecutor` 创建 `WorkflowPauseRequest` 时(每次 run+node 仅一次,天然幂等)。

## Implementation Plan

### Stage 1: 后端通知类型 + i18n
- **Files modified**: `backend/app/models/notification.py`, `backend/app/core/i18n_legacy.py`, `backend/app/locales/{en,zh}/LC_MESSAGES/messages.po`
- **Specific logic**:
  - `AutoNotificationType.WORKFLOW_PAUSE_PENDING = "workflow.pause_pending"`。
  - i18n keys:`notify_workflow_pause_pending_title`(en "Workflow waiting for review" / zh "工作流等待处理")、`notify_workflow_pause_pending_content`(en "Workflow **{workflow_name}** is waiting for input at node **{node_name}**." / zh "工作流 **{workflow_name}** 在节点 **{node_name}** 等待处理。")、`workflow_pause_not_approver`(403 文案)。
- **Validation**: 后端测试引用新枚举;无运行时依赖。

### Stage 2: 处理人解析 + 通知 service
- **Files modified**: 新建 `backend/app/services/workflow/pause_approvers.py`
- **Specific logic**:
  - `resolve_pause_approver_ids(workflow, config) -> list[UUID]`(上述规则;`TeamMember.role in {owner, admin}` 用 `TeamMemberRole` 枚举)。
  - `notify_pause_pending(run, config, node_name)`:fetch workflow,解析处理人,逐个用户按 `user.locale` 发 `send_to_user`(title/content 走 `t()`,`link_url=f"/run/{run.id}"`,data 带 run/workflow/node id)。失败仅 log 不阻断 run(通知是副作用)。
- **Validation**: 单测覆盖配置优先、回退、空处理人、通知参数。

### Stage 3: executor 触发通知
- **Files modified**: `backend/app/services/workflow/executors/pause.py`
- **Specific logic**: `WorkflowPauseRequest.create(...)` 后调用 `notify_pause_pending(run, config, node_name)`(仅首次创建分支)。
- **Validation**: `test_pause_executor.py` 补 `monkeypatch` 该函数断言调用;更新 run fixture。

### Stage 4: submit 端点 approver 校验
- **Files modified**: `backend/app/api/v1/endpoints/workflows.py`
- **Specific logic**: `pause_submission_is_valid` 通过后、条件更新前:
  - `approver_ids = await resolve_pause_approver_ids(workflow, config)`;
  - 若非 superuser 且 `current_user.id not in approver_ids` → `BusinessError(FORBIDDEN, "workflow_pause_not_approver", 403)`。
- **Validation**: 新增测试:配置后非处理人 403、处理人通过、未配置 owner/admin 通过;更新既有 submit 测试 fixture(workflow 需 `created_by_id`/`team_id`,mock `TeamMember.filter`)。

### Stage 5: pending 端点返回处理人信息
- **Files modified**: `backend/app/api/v1/endpoints/workflows.py`
- **Specific logic**: `get_pending_workflow_pause_request` 返回 `approver_ids: list[str]`、`approver_names: list[str]`(username)、`can_submit: bool`(superuser 或 id 在处理人列表)。
- **Validation**: 更新既有精确 dict 断言测试,补 can_submit/approver_names 断言。

### Stage 6: 前端 API 类型 + 节点处理人选择器
- **Files modified**: `frontend/lib/api/workflows.ts`, `frontend/app/(platform)/app/apps/workflow/[id]/_components/node-config/configs/pause-node-config.tsx` + 测试
- **Specific logic**:
  - `WorkflowPauseRequest` 加 `approver_ids: string[]`、`approver_names: string[]`、`can_submit: boolean`。
  - `PauseNodeConfig` 加 `approverIds: string[]`(默认 `[]`);approval/variables 两种模式都显示"处理人"多选(checkbox 组),成员来自 `teamsApi.getTeam(currentTeam.id).members`,空态提示"留空 = 工作流所有者与团队管理员可处理"。
- **Validation**: 组件测试断言成员加载、勾选回写 `approverIds`、空态文案。

### Stage 7: 审批面板禁用 + 运行页接线
- **Files modified**: `frontend/app/(chat)/run/[id]/_components/workflow-pause-panel.tsx`、`workflow-run-page.tsx` + 测试
- **Specific logic**:
  - panel 新增 props `canSubmit: boolean`、`approverNames: string[]`;`canSubmit=false` 时禁用提交按钮 + 表单,显示"仅处理人可处理:xxx"提示。
  - run page 从 `pendingPause.can_submit/approver_names` 透传。
- **Validation**: run-page 测试断言禁用与提示。

### Stage 8: 前端 i18n + 全量验证
- **Files modified**: `frontend/i18n/{en,zh}/...`(run/config 文案)、相关测试
- **Validation**: `bun run i18n:lint`、tsc、前端全量;后端 pytest + ruff + mypy。

## Testing Strategy
- Happy path:配置处理人 → 处理人提交成功、收到通知;未配置 → owner/admin 提交成功。
- Error path:非处理人 403;superuser 始终可提交;通知失败不阻断运行。
- Regression:既有 submit/get-pending 测试更新;前端 run-page、node-config 全量回归。

## Code Review Fixes (2026-08-16)
- checkbox 类型变量加入 `pause_submission_is_valid` 类型表(此前 checkbox 变量永远 400,运行无法恢复)。
- submit 端点去掉 `require_write=True`:配置的处理人(member 角色)不再被写门槛 403 卡死;未配置时回退 owner/admin 集合与写权限一致。`can_submit` 与提交校验现在同源。
- 空数字(`""`)视为未提供;`defaultValue: ""` 映射为 `None`(避免 number 预填 0);`options`/`fileConfig` 透传给前端表单。
- StreamManager `seed_sequence()`:resume pass 从 buffer 最后 sequence 续号,replay 过滤不再丢弃整个 resumed pass。
- `_persist_skipped_node`:分支剪枝节点持久化 `NodeStatus.SKIPPED`,resume 不再重跑错误分支。
- submit 端点恢复路径:request 已 SUBMITTED 且 run 仍 WAITING(丢失的 resume task)→ 处理人可重新触发 dispatch。
- `resume_workflow_task`:run 再次 WAITING 时返回 `status: "waiting"`(multi-pause 正确);`workflow_run_not_waiting` 走 t() 翻译。
- `cancel()` 将 pending pause requests 置为 CANCELLED;approval 输出声明补 `submitted_by`。
- 前端:run.json 恢复 `typePlaceholder`(agent-run-page 仍消费);`validation.invalidVariableName` 补键;空 input_variables 渲染提交按钮(否则运行永久卡死);pause-node/drawer/validator 对部分形状 pauseConfig 加防护。
- embed 适配器无 pause 端点(API-key 公开运行无审批接口):embed 运行页在 waiting 时显示"需登录 Clouisle 处理"提示(方案 B),不再静默卡死。

## Approval Visibility (2026-08-16)
- **不可见**:`get_pending_workflow_pause_request` 对非处理人(superuser 除外)返回 `pause_request: null`(与"无请求"同态,不泄露存在性)。可见性 = 提交权限集合:配置 approverIds 时仅列表内;未配置时 owner + team admins。
- **不可审批**:submit 端点 403(既有)。
- 前端:非处理人(登录用户)看到 `run.pause.waitingForReview` 中性提示;embed 无审批能力显示 `embedNotice`。

## Approver Scope Enforcement (2026-08-16)
- **保存期校验**:`update_workflow` 更新 definition 时调用 `validate_pause_approvers(team_id, definition)`:每个 pause 节点的 `approverIds` 必须是工作流团队的**现存且激活**成员;格式无效的 id 直接判无效。非法 → 400 `workflow_pause_invalid_approvers`(列出前 5 个无效 id),definition 不落库。
- 此前只有前端选择器(团队成员)做软限制,API/导入可绕过;现在"团队成员"升级为后端契约,无效配置在保存时失败而非运行到审批时卡死。
- create_workflow 用默认定义(无 pause 节点),无需校验;发布快照来自已校验的保存定义。

## Approval Content + Inline Approval (2026-08-16)
- **审批内容配置**:approval 模式新增 `description` 文本域(节点配置),随运行快照持久化;executor 在暂停时解析运行变量并持久化结果;不可用或解析失败的引用渲染为空且绝不泄漏 `{{var}}`;上传文件值只显示文件名。`get_pending_workflow_pause_request` 返回该已解析内容。
- **通知携带审批内容**:`notify_pause_pending` 把已解析 `description` 追加到通知 content,并在 data 中增加 `pause_request_id` 与 `node_id`(executor 创建请求后传入)。
- **通知内完成审批**:站内通知中心(`notifications-client.tsx`)对 `workflow.pause_pending` 类型通知渲染"通过/拒绝"按钮,点击直接调 `submitPauseRequest`(已登录用户 + 后端 approver 校验兜底),成功 toast + 标记已读 + 刷新列表;失败 toast 提示可能已被处理。外部渠道(email/IM)保持 deep link 到运行页。
- 注意:`workflow.pause_pending` 需在站点通知设置 `enabled_types` 中启用(默认列表未含,已部署站点需手动启用或迁移)。

## Code Review Remediation (2026-08-17)
- Resolve configured IDs against current active `TeamMember` rows on every notify/read/submit path. A departed or deactivated member must receive neither pause content nor approval authority.
- The submit endpoint must authorize configured approvers before the private-workflow owner-only gate, while all unrelated workflow endpoints retain their existing access policy.
- Require-all approvals need a locked/conditional state transition so concurrent approvers cannot overwrite each other's audit records.
- Notification deep links must include `type=workflow`; variable-input notifications otherwise load the agent runner.
- Persist a pause request before emitting a waiting event; a duplicate `(run_id, node_id)` write resolves to the existing request so retries do not create duplicate approvals.
- Register workflow waiting as a first-class stream event. Resume events continue the prior event sequence and the client updates existing node traces rather than appending duplicate node cards.
- Workflow-run history removes only the `run` parameter while preserving `type=workflow`; stale detail loads are generation-guarded after switching to a different run or starting a fresh run.
- Startup DDL creates the physical `workflow_node_executions` foreign key target, applies new columns independently, and rebuilds the approval unique constraint around `node_id`.
- Activity filters and every runner surface expose the `waiting` lifecycle state.

## Risks & Mitigation
- 老版本运行快照无 `approverIds` → 回退逻辑保证行为不变。
- 通知在 executor 内触发,测试需 patch;通过独立 service + monkeypatch 隔离。
- `approverIds` 中用户被移除/失效 → 提交校验按 id 匹配,失效用户自然无权限;通知只发给现存用户。
- Rollback:去掉 Stage 4 校验即恢复旧行为;通知为副作用,可安全移除。
