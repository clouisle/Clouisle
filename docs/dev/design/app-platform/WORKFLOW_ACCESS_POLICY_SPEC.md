# 工作流权限管理设计

状态：**已完整实现**（后端策略与全部入口 + 前端权限页签 + 审计 + 测试）。

已落地文件的对应关系：

| 设计要点 | 实现位置 |
|---|---|
| 策略模式与校验 | `backend/app/schemas/workflow_access.py` |
| 求值与强制 | `backend/app/services/workflow_access.py` |
| 模型列与迁移 | `backend/app/models/workflow.py`、`backend/app/core/workflow_access_policy_migration.py` |
| JWT 入口接入 | `backend/app/api/workflow_access.py`（`check_workflow_access(..., operation=...)`，默认按 `require_write` 推导 view/edit） |
| Embed 入口接入 | `backend/app/api/v1/endpoints/embed.py`（`_get_embed_workflow(..., operation=...)`） |
| Webhook 入口接入 | `backend/app/api/v1/endpoints/workflows.py` 的 `trigger_workflow_webhook`（无受众，受限策略直接关闭该入口） |
| 子工作流入口接入 | `backend/app/services/workflow/executors/subworkflow.py`（继承父运行的凭据，拒绝时节点失败而非中断父运行） |
| 三接口 | `GET/PUT /api/v1/workflows/{id}/access-policy`、`POST .../access-policy/evaluate` |
| 审计字段 | `backend/app/services/audit_log.py` 的 workflow 快照新增 `access_policy` |
| 前端页签 | `frontend/app/(platform)/app/apps/workflow/[id]/permissions/page.tsx` + `_components/access-policy-editor.tsx` |
| 前端 API | `frontend/lib/api/workflows.ts` 的三个方法与 `WorkflowAccess*` 类型 |
| 测试 | 后端 3 个文件（求值、接口、子工作流），前端 2 个文件（编辑器纯函数、API 客户端） |

## 1. 目标

让每个工作流的"谁能看、谁能跑、谁能改"成为**工作流自己的策略**，而不是只靠团队角色 + `visibility` + 全局 RBAC 码三者拼出来的隐式规则。要求：

- 一个策略同时约束所有入口：应用内手动运行、Public API（API Key）、Embed、Webhook、子工作流调用、调试运行。
- 默认策略必须等于**当前行为**，升级不改变任何既有权限。
- 决策可审计：改策略与"因策略被拒"都要留痕。
- 拒绝时不得泄露工作流是否存在、节点结构或运行输出。

## 2. 现状

| 维度 | 现状 |
|---|---|
| 全局 RBAC | `workflow:read/create/update/delete/publish/run/execute`（`app/core/permissions.py`） |
| 团队角色 | `TeamMember.role`（owner/admin/member/viewer） |
| 资源可见性 | `Workflow.visibility`：`private`（仅创建者）/ `team` / `public` |
| 入口 | JWT 直连、API Key（含 Embed）、Webhook、子工作流、调试 |
| 团队级日志 | `/workflows/runs` 只要求 `workflow:read`，与后台活动页的 admin 门禁不一致（已记录为待确认项） |

现状的问题：同一团队里"能读工作流"就等于"能跑它"，无法表达"这条生产流程只有 SRE 能跑"；`visibility` 是单一开关，无法按角色/人细分；入口之间靠各自的路由做检查，容易漂移。

## 3. 参考实现：工具审批策略

工具审批（`app/schemas/tool_approval.py`、`app/services/tool_approvals.py`）已经有一套成熟的分层策略，工作流权限按同样的形状实现，避免发明第二套概念：

| 审批策略 | 对应到工作流权限 |
|---|---|
| `default_decision`：`allow` / `deny` / `require_approval` | 每个操作的默认结论 |
| `gates`：`GateKind` 受众 + `allow_self_approval` | 允许的受众（团队角色、用户） |
| `operation_overrides`：按操作名覆盖整条策略 | 按 `view` / `run` / `edit` / `publish` / `delete` 覆盖 |
| `PolicyLayer` 分层 + `deny > require_approval > allow` | 团队默认策略层 + 工作流层，写法一致 |
| 策略快照入审计 | `AuditLogService.snapshot` / `build_changes` 记录前后 diff |
| `PolicyConfigurationError` 失败即拒 | 配置不合法时**不执行**，返回明确配置错误 |

## 4. 数据模型

```python
class Workflow(Model):
    # 已有：visibility、team_id、created_by_id
    # 新增：
    access_policy = fields.JSONField(default=dict)   # 空 {} = 历史默认行为
    access_policy_version = fields.IntField(default=1)
```

不做新表：策略是工作流的属性，随工作流一起导入/导出、复制、回滚版本。空策略必须逐字等价于现状，因此无需回填，迁移只加列（与 `execution_history_migration` 同样的写法：先 `ADD COLUMN`，可重复执行）。

## 5. 决策模型

操作（operation）与现有路由一一对应：

| operation | 覆盖的路由/入口 |
|---|---|
| `view` | 工作流详情、版本、运行历史、运行详情、节点输出 |
| `run` | 手动运行、`run/stream`、Public API 运行、Embed 运行、Webhook 触发、子工作流调用 |
| `edit` | 更新定义/变量、保存版本、导入覆盖 |
| `publish` | 发布、取消发布、修改触发器 |
| `delete` | 删除、删除版本 |

结论（decision）：`allow` / `deny`。审批式 `require_approval` 默认**不启用**：工作流运行会拉起 worker 与沙箱，中途挂起审批的成本远高于工具调用；若后续需要，可复用工具审批的 `ToolApprovalRequest` 机制按同一形状扩展（见未决问题 2）。

受众（audience）gate：

- `team_role`：`owner` / `admin` / `member` / `viewer`
- `user`：显式用户列表
- `api_key`：显式 API Key 列表（决定"哪把 Key 能跑"，与历史隔离的凭据模型一致）

## 6. 求值顺序

单一入口函数，所有路由必须调用它，禁止各自判断：

```
ensure_workflow_permission(workflow, operation, principal) -> None
```

`principal` 携带现有身份信息：`user`、`team_member.role`、`api_key`、`entrypoint`。顺序：

1. **系统管理员**：`is_superuser` 直接放行（与现有 `PermissionChecker` 一致），但审计记录"superuser 放行"。
2. **团队边界**：非团队成员一律拒绝（`private` 工作流的非创建者同样拒绝）。
3. **策略求值**：`deny` 优先 → `allow` → 无匹配则回落到**兼容默认**（见第 7 节）。
4. **入口补充约束**：API Key 仍需 `api_key.workflows` 关联；Embed 仍需 `embed_config.enabled` 与域名校验；Webhook 仍需 token 有效。策略只收紧，不放宽这些检查。

拒绝统一返回 `404`（不存在/无权不区分），与现有历史隔离的"不泄露存在性"做法一致；`publish`/`delete` 这类管理操作返回 `403`，因为调用者已经能看到工作流。

## 7. 兼容默认（空策略）

空 `{}` 必须复现现状：

- `view`：`private` 仅创建者 + 团队管理员；`team` 团队可见（按现有 `workflow_read_visibility_filter`）。
- `run`：`workflow:run` + 团队边界（现状即如此）。
- `edit` / `publish` / `delete`：`workflow:update` / `workflow:publish` / `workflow:delete` + 创建者或团队管理员。

实现上把现状规则写成"兼容层"，由同一个求值函数调用，这样配置与不配置走同一条路径，不会出现两套语义。

## 8. API

```
GET  /api/v1/workflows/{id}/access-policy        # 读策略（含 effective 兼容默认）
PUT  /api/v1/workflows/{id}/access-policy        # 覆盖策略，走 workflow:update + 团队管理员
POST /api/v1/workflows/{id}/access-policy/evaluate  # 调试：给定期望主体，返回每个操作的结论与命中规则
```

`evaluate` 只做决策、不执行，便于"保存前预览"与前端解释"为什么我不能跑"。`PUT` 必须返回 `effective` 结果与审计链接。

## 9. 前端

工作流详情新增"权限"页签（沿用 Agent 的权限页签信息结构）：

- 每个操作一行：`view` / `run` / `edit` / `publish` / `delete`，可选"允许的角色"、"指定用户"、"指定 API Key"。
- 顶部固定提示：默认继承团队规则；覆盖后以本工作流为准。
- 保存前调用 `evaluate` 预览当前用户自己的有效权限，避免把自己锁在外面（保存后仍可自救：团队管理员可改策略）。
- 全部文案进 `zh` / `en`，`<PermissionGuard>` 与后端 `workflow:update` 双重校验。

## 10. 审计

- 策略变更：`action=update_workflow_access_policy`，`AuditLogService.snapshot` 记录 `before`/`after`，与工具审批策略更新一致。
- 策略导致的拒绝：`action=workflow_access_denied`，记录 `operation`、`entrypoint`、命中规则 id；**不记录**节点结构或运行输入输出。
- 运行记录本身继续携带 `api_key_id` / 触发者，便于与历史隔离一起排查。

## 11. 测试计划

1. 求值单测：`deny` 优先、角色/用户/Key 命中、无匹配回落、空策略等于现状（用现状用例做参数化）。
2. 入口矩阵：同一工作流在 6 个入口上分别用"创建者、团队管理员、普通成员、Viewer、他团队成员、他人 API Key、超级管理员"跑 `view`/`run`，逐格断言状态码。
3. 不泄露：拒绝响应不含工作流名、节点、运行 id；`view` 拒绝统一 `404`。
4. 审计：变更 diff 字段级正确；拒绝日志不含敏感内容。
5. 兼容：存量工作流（空策略）在全部入口行为与升级前完全一致（用升级前快照对比）。
6. 前端：页签渲染、保存、`evaluate` 预览、无权限时只读。

## 12. 未决问题

1. ~~参考物~~：按工具审批策略的形状实现（已确认）。
2. **运行前放行**：明确不做（产品已确认）。运行即执行，审批只在运行中途遇到时暂停——这部分**已实现**，见第 12.1 节。`require_approval` 仍不作为访问策略取值，访问策略只有 `allow`/`deny`。

### 12.1 运行中途审批（已实现）

工作流工具节点不再“取消并失败”，而是把运行停在审批上：节点返回 `ExecutionResult(waiting=True)`，编排器按既有 pause 路径把节点置 `WAITING`、运行置 `WAITING` 并结束本次任务；决定后由 `schedule_workflow_run_approval_resume` 拉起 `resume_workflow_task`，凭稳定 `tool_call_id` 找回并领取同一条 `ToolExecution` 续跑，不会重建或重复执行。

改动位置：

- `app/services/tool_execution.py`：删除 workflow 的审批绕过（`is_workflow_tool_call` 及其入口常量已移除），工作流调用与 Agent 一样读取工具自身的存储策略；遗留 `user`/`team_role` 关卡对工作流同样失败关闭（`6510`），不再被静默忽略。
- `app/services/workflow/executors/tool.py`：`PendingToolApproval` → `waiting=True`（原来的取消逻辑已删除）。
- `app/services/tool_approvals.py`：`caller_self_approvable` 对 `run_kind == workflow` 为真（非交互，但受众可以离线决定）；`_request_audience_matches` 对 workflow 运行的 caller 关卡接受团队 `owner`/`admin` 兜底，收件箱查询同步放开。
- 谁可以批准：**运行发起人（优先）+ 运行所属团队的 owner/admin（兜底）**；普通成员既看不到也无法决定；Agent 运行的 caller 关卡不享受该兜底。停止运行仍由 `cancel` 取消其待处理执行（`RUN_STOPPED`）。
3. **受众是否包含 API Key**：已包含（`api_key` gate）。
4. **团队级 `/workflows/runs` 的权限落差**：仍待决定是否收紧到与后台活动页一致。
5. **运行前放行**明确不做（见第 12 节）。中途审批由工具审批承担，工作流现在会真正停下并在决定后续跑。

**容器内不允许审批**：迭代/循环体内部不能放暂停节点，也不能放“可能要求审批的工具”节点。容器一轮无法中途续跑，重跑会重复执行前面的轮次，所以这类定义在保存时就被拒绝（`app/services/workflow/definition_rules.py`，由 `update_workflow` 与版本回滚两处调用，错误码 `workflow_pause_inside_container` / `workflow_approval_inside_container` 并带上 `node`）。运行时仍保留 fail-closed 守卫，用于策略在保存之后被改成需要审批的情况。
## 13. 实施顺序

1. 模型列 + 迁移（可重复执行的 `ADD COLUMN`）+ 空策略兼容层。
2. 求值服务 + 全部入口接入 + 拒绝语义统一。
3. 审计事件 + `evaluate` 预览。
4. 前端权限页签 + i18n。
5. 测试矩阵与文档（本文件 + `docs/guide` 用户文档）。

## 14. 实际验收（隔离环境，真实浏览器）

- 升级路径：在已有数据库上启动新版本，启动日志自动补出 `access_policy` / `access_policy_version`，应用正常启动。**第一次实现时把迁移放在 `generate_schemas()` 之后，启动直接失败**（Tortoise 在生成 schema 时引用了尚不存在的列），已改为先加列。
- 页面：`/app/apps/workflow/{id}/permissions` 渲染五个操作，未配置时显示“当前：继承”。[截图](worktree://4ab33767-d7b2-4141-bf51-a640aeb896d1/qa/history-isolation-e2e/screenshots/82-workflow-permissions-inherit.png)
- 保存：把“运行”设为允许 + 仅所有者/管理员，保存后落库为 `{"operations": {"run": {"gates": [{"kind": "team_role", "roles": ["owner", "admin"]}], "decision": "allow"}}}`，审计记录字段级 before/after。[截图](worktree://4ab33767-d7b2-4141-bf51-a640aeb896d1/qa/history-isolation-e2e/screenshots/84-workflow-permissions-saved.png)
- 强制生效：同一工作流下，团队成员仍可**查看**（继承）但**运行**返回 `404 工作流未找到`；超级管理员与所有者可运行并可开 Webhook。
- Webhook：受限策略下，成员 Key 调用返回 `404`，所有者 Key 返回 `200`。
- 两个已修问题：超级管理员的继承操作曾被报成 `source: policy`（现已报 `inherit` 并保留 `reason: superuser`）；存储的策略曾带空 `user_ids`/`api_key_ids`（现用 `exclude_defaults` 只存实际字段，响应仍补全供前端使用）。
- 门禁：后端 **11,802 通过、5 跳过**，行覆盖 **96.75%**、分支 **95.09%**，Ruff check/format 通过；前端 **3,391 通过、0 失败**，覆盖率 **95.25% 函数 / 97.64% 行**，生产构建与 lint（0 error）通过。
- 已知环境限制：`tests/services/test_sandbox_recovery.py` 的 2 项在本机工作目录下因 `AF_UNIX path too long` 失败；在未包含本次改动的 `HEAD` 干净检出上同样失败，与本改动无关。
