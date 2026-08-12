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
  password-only operations, auto-processing pipelines) — they keep their
  operation-level audit and would only add noise.

To add a new resource type: register its plain columns in
`AuditLogService.SNAPSHOT_FIELDS` in `app/services/audit_log.py`, then follow
the wiring recipe above at the endpoint's existing `log(...)` call.

## i18n requirements for new actions

Every new audit action must add translations in both backend and frontend.

### Backend

Add a key to `TRANSLATIONS` in `app/core/i18n.py`:
- key format: `audit_log_{action}`

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

The existing action set includes:

```text
activate_api_key, activate_user, add_team_member, bulk_update_site_settings,
change_password, create_agent, create_api_key, create_team, create_user,
deactivate_api_key, deactivate_user, delete_agent, delete_api_key, delete_team,
delete_user, login_failed, login_success, logout, publish_agent, register,
remove_team_member, reset_password, reset_site_settings, trigger_audit_log_archive,
unpublish_agent, update_agent, update_api_key, update_site_setting, update_team,
update_user
```

## Related docs

- `./api-conventions.md`
- `../design/access-control/RBAC_SPEC.md`
