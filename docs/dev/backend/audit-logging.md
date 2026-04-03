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
