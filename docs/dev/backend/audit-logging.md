# Audit Logging Conventions

Use `AuditLogService.log()` from `app/services/audit_log` for operation logging.

## Standard usage

```python
await AuditLogService.log(
    user=current_user,
    action="delete_user",
    resource_type="user",
    resource_id=str(user_id),
    resource_name=user.username,
    operation="delete",
    status="success",
    request=request,
    changes={"before": {...}, "after": {...}},
    metadata={...},
)
```

## Required fields

When adding a new audit event, include:
- `action`
- `resource_type`
- `resource_id`
- `operation`
- `status`
- `request`

Add `resource_name`, `changes`, and `metadata` when they help explain the operation.

## Field-level before/after diffs

Every direct CRUD mutation of a snapshot-capable resource records `changes` via
three `AuditLogService` static helpers:

- `snapshot(instance, resource_type)` — JSON-safe snapshot of the registered
  plain columns of an already-fetched row. **Zero extra queries**: never pass a
  lazy relation descriptor (e.g. `team`, `created_by`) — only plain columns and
  raw `<fk>_id` UUID columns.
- `build_changes(before, after)` — `{"before": {...}, "after": {...}}` with only
  changed keys; returns `None` when nothing changed (pass `changes=None`).
- `_json_safe` (used internally by `snapshot`) — orjson-safe (Enum/UUID/
  datetime/Decimal), truncates values to 500 chars, converts oversized
  structures to preview strings, and masks nested sensitive keys (`token`,
  `api_key`, `email`, ...) before serializing.

### Wiring recipe

```python
# update: snapshot right after fetch, diff after save/reload
audit_before = AuditLogService.snapshot(entity, "agent")
...mutate + save + reload...
changes = AuditLogService.build_changes(
    audit_before, AuditLogService.snapshot(entity, "agent")
)

# create
changes = {"after": AuditLogService.snapshot(created, "agent")}

# delete: snapshot before the destructive call
changes = {"before": AuditLogService.snapshot(entity, "agent")}
```

Rules:

- Never add a field the sanitizer cannot key-match (`credentials`, `config`,
  `http_config`, `mcp_config`, `trigger_config`, `hashed_password`, `api_key`,
  ...) — the `changes` column is sanitized by key, so such containers would
  persist raw secrets.
- Relation-only mutations must also produce a diff: merge association IDs
  before/after (see `admin_update_agent` knowledge_base_ids, `admin_update_user`
  roles).
- Batch operations snapshot each row in the loop (`batch_*_team_models`,
  `bulk_force_password_change`) or record a before list
  (`batch_delete_conversations` titles).
- Do not wire events with no field-level change (auth/read/execute events,
  operations that change only secret fields, auto-processing pipelines) —
  they keep their operation-level audit and would only add noise. Password
  *flag* operations that mutate registered non-secret fields are wired:
  `force_password_change` and `exempt_password_expiration` record field-level
  diffs; only operations changing exclusively secret fields
  (`change_password`, `reset_password_expiration`) are excluded.

To add a new resource type: register its plain columns in
`AuditLogService.SNAPSHOT_FIELDS` in `app/services/audit_log.py`, then follow
the wiring recipe above at the endpoint's existing `log(...)` call.

## i18n requirements for new actions

Every new audit action must add translations in both backend and frontend.

### Backend

Backend messages are stored in the Babel catalogs — there is no hand-edited
Python translation dict. `app/core/i18n.py` imports `TRANSLATIONS` from the
**generated** compatibility snapshot `app/core/i18n_legacy.py`
(`scripts/sync_i18n_legacy.py`, driven by `scripts/i18n_catalog_utils.py`), so
never edit `TRANSLATIONS` directly.

To add a key:
1. Add `audit_log_{action}` to both catalogs:
   - `backend/app/locales/en/LC_MESSAGES/messages.po`
   - `backend/app/locales/zh/LC_MESSAGES/messages.po`
2. Regenerate the legacy snapshot: `python scripts/sync_i18n_legacy.py`.
3. Verify: `python scripts/check_i18n_catalogs.py` and
   `python scripts/check_i18n_legacy_sync.py`.

Example:
- `audit_log_delete_user` → `Delete user` / `删除用户`

### Frontend

Add a key to both files:
- `frontend/i18n/en/auditLogs.json`
- `frontend/i18n/zh/auditLogs.json`

Key format:
- `action{action}`

Example:
- `actiondelete_user` → `Delete User` / `删除用户`

## Current action inventory

The action set is large (141 distinct values at this revision) and grows with
each feature, so treat the code as the source of truth and regenerate the list
with:

```bash
grep -rho 'action="[a-z_0-9]*"' backend/app | sed 's/action="//;s/"//' | sort -u
```

Grouped by domain, the current set is:

```text
认证与会话 (19): login_success, login_failed, logout, register, change_password,
  reset_password, reset_password_expiration, force_password_change,
  exempt_password_expiration, bulk_force_password_change, use_backup_code,
  regenerate_backup_codes, enable_totp, disable_totp, verify_totp_success,
  verify_totp_failed, sso_login_success, sso_login_failed, disconnect_sso
用户（管理侧，5): activate_user, deactivate_user, create_user, update_user, delete_user
团队与成员 (5): create_team, update_team, delete_team, add_team_member, remove_team_member
团队模型 (5): add_team_model, update_team_model, remove_team_model,
  batch_add_team_models, batch_remove_team_models
SSO 提供方 (4): create_sso_provider, update_sso_provider, delete_sso_provider,
  test_sso_provider_failed
API 密钥 (6): create_api_key, update_api_key, delete_api_key, activate_api_key,
  deactivate_api_key, regenerate_webhook_token
Agent (12): create_agent, update_agent, delete_agent, duplicate_agent,
  publish_agent, unpublish_agent, admin_create_agent, admin_update_agent,
  admin_delete_agent, admin_duplicate_agent, admin_publish_agent,
  admin_unpublish_agent
Workflow (20): create_workflow, update_workflow, delete_workflow,
  duplicate_workflow, publish_workflow, unpublish_workflow,
  create_workflow_version, restore_workflow_version, run_workflow,
  run_workflow_embed, cancel_workflow_run, debug_workflow, delete_workflow_run,
  submit_workflow_pause_request, admin_create_workflow, admin_update_workflow,
  admin_delete_workflow, admin_duplicate_workflow, admin_publish_workflow,
  admin_unpublish_workflow
知识库/文档/分块 (18): create_knowledge_base, update_knowledge_base,
  delete_knowledge_base, share_knowledge_base, unshare_knowledge_base,
  upload_document, add_url_document, update_document, delete_document,
  process_document, process_document_with_chunks, reprocess_document,
  rechunk_document, retry_failed_chunk, retry_failed_chunks,
  create_document_chunk, update_document_chunk, delete_document_chunk
工具 (10): create_tool, update_tool, delete_tool, duplicate_tool, toggle_tool,
  share_tool, unshare_tool, create_tool_config, update_tool_config,
  delete_tool_config
技能 (10): update_skill, delete_skill, test_skill, install_skill_import,
  preview_skill_import, admin_update_skill, admin_delete_skill, admin_test_skill,
  admin_install_skill_import, admin_preview_skill_import
记忆 (8): create_memory_entity, update_memory_entity, delete_memory_entity,
  create_memory_relation, delete_memory_relation, agent_create_memory_entity,
  agent_create_memory_relation, agent_update_memory_entity
提示词 (2): generate_prompt, optimize_prompt
包 (3): export_clouisle_package, install_clouisle_package, preview_clouisle_import
站点设置/通知/审计 (6): update_site_setting, bulk_update_site_settings,
  reset_site_settings, update_auto_notification_config,
  trigger_audit_log_archive, admin_disable_totp
会话与消息 (4): delete_conversation, batch_delete_conversations, create_message,
  delete_message
文件与上传 (4): upload_file, delete_file, upload_image, upload_sandbox_artifact
```

Every action needs a matching `audit_log_{action}` backend key and
`action{action}` frontend key (see above).

## Related docs

- `./api-conventions.md`
- `../design/access-control/RBAC_SPEC.md`
