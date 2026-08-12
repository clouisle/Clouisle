# Audit Log Detail — 记录每次操作具体改了什么

## 背景

审计日志此前只记录「谁做了操作」（用户、动作、资源、状态），不记录「改了什么」。本次为所有可快照资源的直接增删改操作补齐字段级 before/after 差异。存储模型已支持：`AuditLog.changes`（JSONField，`{"before": {...}, "after": {...}}`）、`sanitize_changes` 入库前脱敏、管理端抽屉已渲染 before/after。无需迁移、无前端改动。

性能约束：快照只读已取回行的普通列（零额外查询、零懒加载、无 N+1）；所有存储值 ≤500 字符（大 JSON 字段存预览字符串）；审计写入保持原有单次异步 INSERT。

## changes 形状

- 更新：`{"before": {...}, "after": {...}}`，仅含值发生变化的键（`AuditLogService.build_changes(before_snapshot, after_snapshot)`）；无变化返回 `None`。
- 创建：`{"after": {...}}`。
- 删除：`{"before": {...}}`。

## 核心实现

`backend/app/services/audit_log.py` 新增：

- `AuditLogService.AUDIT_MAX_FIELD_LENGTH = 500`（与 chat.py 预览长度一致）。
- `AuditLogService.SNAPSHOT_FIELDS`：`resource_type -> 字段元组` 注册表。规则：
  - 只允许普通列与原始 `<fk>_id` UUID 列；**禁止关联描述符**（对其 getattr 触发懒加载查询）。
  - 排除 `id`/`*_at` 时间戳/计数器，以及脱敏器按键匹配无法覆盖的密钥容器：`credentials`、`config`、`http_config`、`mcp_config`、`trigger_config`、`tools_credentials`、`key_prefix`、`key_hash`、`hashed_password`、`totp_secret`、`totp_backup_codes_hash`、`api_key`。
- `_json_safe(value)` / `_json_safe_inner(value, bound)`：orjson 兼容（Enum→`.value`、UUID→str、datetime/date→ISO、Decimal→str）+ 硬性大小上限（长字符串截断 500；超限结构在最外层转 500 字符 JSON 预览字符串）。**转换前先按键名脱敏**（与 `_sanitize_dict` 同规则，且递归进入 list），嵌套敏感键（如 `{"nodes": [{"token": ...}]}`）不会绕过 `sanitize_changes` 泄露。
- `_structured_or_preview(value)`：结构在大小上限内原样返回，否则返回前 500 字符 JSON 预览。
- `snapshot(instance, resource_type)`：按注册表 getattr，纯内存、零查询；缺失属性→`None`，属性异常→跳过该字段。
- `build_changes(before, after)`：仅变化键的 before/after 字典；无变化返回 `None`。

## 接线规则

对每个端点的既有 `AuditLogService.log(...)` 调用：

1. 更新：实体首次取回后、任何变更前捕获 `audit_before = snapshot(...)`；变更/保存/重载后传 `changes=build_changes(audit_before, snapshot(变更后实体))`。
2. 创建：传 `changes={"after": snapshot(创建的实例)}`。
3. 删除：破坏性调用前捕获 `audit_before`，传 `changes={"before": audit_before}`。
4. 仅关联集合变化也要记录：如 `admin_update_agent` 合并 `knowledge_base_ids` 前后差异、`admin_update_user` 合并 `roles` 前后差异（否则关联-only 变更会产生 `changes=None`）。
5. 批量操作：循环内逐条快照（`batch_*_team_models`、`bulk_force_password_change` 按用户/模型 diff 列表；`batch_delete_conversations` 记删除标题列表）。
6. 不改动 `log(...)` 其他参数、`metadata`、脱敏器、模型、schema、管理端审计 API、前端。

覆盖（注册表 21 个资源类型）：agent、workflow、knowledge_base、document、document_chunk、api_key、team、user（含 update_user_me / TOTP 开关 / force/exempt 密码过期 / 批量强制改密）、sso_provider、sso_connection（断开）、memory_entity、memory_relation、tool、tool_share（分享/取消）、team_model（含批量）、team_member（增删成员）、workflow_run（删除）、workflow_version（创建）、skill（更新/删除/安装）、conversation（删除/批量删除）、site_setting（单条/批量/自动通知/重置）。

排除（有意不变）：
- **认证/读/执行/导出事件**：登录、登出、注册、SSO 登录、TOTP 验证、密码重置/修改、包导出/预览、提示词生成/优化、技能预览/测试、SSO 测试、工作流运行/调试/取消、归档触发——本身已有操作级审计，无字段级 diff 价值。
- **自动/批量流水线**：文档 process / process_with_chunks / retry_failed_chunks（自动处理）；`retry_failed_chunk`（chunk 行零变化，diff 恒空）；agent 会话自动创建 memory（噪音）。
- **技术限制**：ToolConfig（存原始凭证，脱敏器无法按键匹配）、file 上传/删除（无模型实体，存储对象）。
- 用户主动的文档操作 `reprocess_document` / `rechunk_document` **已接线**（有真实字段变化）。

## 验证

- `uv run pytest tests/services/test_audit_log_changes.py -q` — 辅助方法全分支。
- `uv run pytest` + `uv run python scripts/check_coverage.py` — 95% 行+分支门槛。
- `uv run ruff format --check`（pre-commit 强制；非破坏性校验）。
- 端到端：管理端 UI 修改 agent 名称 → 审计日志抽屉显示 `before: {"name": "old"}` / `after: {"name": "new"}`；无操作发布 → `changes` 为 `None`。
- 大小护栏：`_json_safe` 处理 100 KB 嵌套字符串时序列化结果 < 2 KB。
