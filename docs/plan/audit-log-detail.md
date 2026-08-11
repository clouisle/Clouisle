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
- `_json_safe(value)`：orjson 兼容（Enum→`.value`、UUID→str、datetime/date→ISO、Decimal→str）+ 硬性大小上限（长字符串截断 500；超限 dict/list 转 500 字符 JSON 预览字符串）。
- `snapshot(instance, resource_type)`：按注册表 getattr，纯内存、零查询；缺失属性→`None`，属性异常→跳过该字段。
- `build_changes(before, after)`：仅变化键的 before/after 字典；无变化返回 `None`。

## 接线规则

对每个端点的既有 `AuditLogService.log(...)` 调用：

1. 更新：实体首次取回后、任何变更前捕获 `audit_before = snapshot(...)`；变更/保存/重载后传 `changes=build_changes(audit_before, snapshot(变更后实体))`。
2. 创建：传 `changes={"after": snapshot(创建的实例)}`。
3. 删除：破坏性调用前捕获 `audit_before`，传 `changes={"before": audit_before}`。
4. 不改动 `log(...)` 其他参数、`metadata`、脱敏器、模型、schema、管理端审计 API、前端。

覆盖：管理端与用户侧的 agent、workflow、knowledge_base、document、document_chunk、api_key、team、user（含 update_user_me / TOTP 开关）、sso_provider、memory_entity、memory_relation、tool、team_model、skill（删除）、conversation（删除）、site_setting（reset 逐 key before/after）。

排除（有意不变）：认证/读/执行/导出事件（登录、登出、注册、包导出/预览、运行/调试/取消工作流、技能测试、SSO 测试）；文档流水线事件（process/reprocess/retry/rechunk）；批量操作；`sso_connection`、`workflow_run`、`workflow_version`、`TeamMember`、`ToolShare`、`ToolConfig`（存原始凭证）、`file` 上传。

## 验证

- `uv run pytest tests/services/test_audit_log_changes.py -q` — 辅助方法全分支。
- `uv run pytest` + `uv run python scripts/check_coverage.py` — 95% 行+分支门槛。
- `uv run ruff format --check`（pre-commit 强制；非破坏性校验）。
- 端到端：管理端 UI 修改 agent 名称 → 审计日志抽屉显示 `before: {"name": "old"}` / `after: {"name": "new"}`；无操作发布 → `changes` 为 `None`。
- 大小护栏：`_json_safe` 处理 100 KB 嵌套字符串时序列化结果 < 2 KB。
