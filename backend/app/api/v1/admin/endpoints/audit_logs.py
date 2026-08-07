from datetime import timedelta
from typing import Any
from uuid import UUID
import csv
import json
from io import StringIO

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from tortoise.expressions import Q

from app.api.deps import PermissionChecker
from app.core.i18n import has_translation, t
from app.core.timezone import now_utc
from app.models.audit_log import AuditLog
from app.services.error_messages import is_safe_user_visible_error
from app.models.user import User
from app.models.site_setting import SiteSetting
from app.schemas.audit_log import (
    AuditLog as AuditLogSchema,
    AuditLogActionOption,
    AuditLogStats,
    AuditLogRetentionStats,
)
from app.schemas.response import Response, success, ResponseCode, BusinessError

router = APIRouter()


def serialize_audit_error(error_message: str | None) -> str | None:
    if not error_message:
        return None
    if has_translation(error_message):
        return t(error_message)
    if is_safe_user_visible_error(error_message):
        return error_message
    return t("unknown_error")


def serialize_audit_log(log: AuditLog) -> AuditLogSchema:
    data = AuditLogSchema.model_validate(log).model_dump()
    data["error_message"] = serialize_audit_error(log.error_message)
    return AuditLogSchema.model_validate(data)


AUDIT_ACTION_OPTIONS: list[AuditLogActionOption] = [
    AuditLogActionOption(
        value="login_success",
        translation_key="auditLogs.actionlogin_success",
        fallback_label="Login Success",
    ),
    AuditLogActionOption(
        value="login_failed",
        translation_key="auditLogs.actionlogin_failed",
        fallback_label="Login Failed",
    ),
    AuditLogActionOption(
        value="logout",
        translation_key="auditLogs.actionlogout",
        fallback_label="Logout",
    ),
    AuditLogActionOption(
        value="register",
        translation_key="auditLogs.actionregister",
        fallback_label="Register",
    ),
    AuditLogActionOption(
        value="create_user",
        translation_key="auditLogs.actioncreate_user",
        fallback_label="Create User",
    ),
    AuditLogActionOption(
        value="update_user",
        translation_key="auditLogs.actionupdate_user",
        fallback_label="Update User",
    ),
    AuditLogActionOption(
        value="delete_user",
        translation_key="auditLogs.actiondelete_user",
        fallback_label="Delete User",
    ),
    AuditLogActionOption(
        value="activate_user",
        translation_key="auditLogs.actionactivate_user",
        fallback_label="Activate User",
    ),
    AuditLogActionOption(
        value="deactivate_user",
        translation_key="auditLogs.actiondeactivate_user",
        fallback_label="Deactivate User",
    ),
    AuditLogActionOption(
        value="change_password",
        translation_key="auditLogs.actionchange_password",
        fallback_label="Change Password",
    ),
    AuditLogActionOption(
        value="reset_password",
        translation_key="auditLogs.actionreset_password",
        fallback_label="Reset Password",
    ),
    AuditLogActionOption(
        value="force_password_change",
        translation_key="auditLogs.actionforce_password_change",
        fallback_label="Force Password Change",
    ),
    AuditLogActionOption(
        value="reset_password_expiration",
        translation_key="auditLogs.actionreset_password_expiration",
        fallback_label="Reset Password Expiration",
    ),
    AuditLogActionOption(
        value="exempt_password_expiration",
        translation_key="auditLogs.actionexempt_password_expiration",
        fallback_label="Exempt Password Expiration",
    ),
    AuditLogActionOption(
        value="bulk_force_password_change",
        translation_key="auditLogs.actionbulk_force_password_change",
        fallback_label="Bulk Force Password Change",
    ),
    AuditLogActionOption(
        value="create_api_key",
        translation_key="auditLogs.actioncreate_api_key",
        fallback_label="Create API Key",
    ),
    AuditLogActionOption(
        value="update_api_key",
        translation_key="auditLogs.actionupdate_api_key",
        fallback_label="Update API Key",
    ),
    AuditLogActionOption(
        value="activate_api_key",
        translation_key="auditLogs.actionactivate_api_key",
        fallback_label="Activate API Key",
    ),
    AuditLogActionOption(
        value="deactivate_api_key",
        translation_key="auditLogs.actiondeactivate_api_key",
        fallback_label="Deactivate API Key",
    ),
    AuditLogActionOption(
        value="delete_api_key",
        translation_key="auditLogs.actiondelete_api_key",
        fallback_label="Delete API Key",
    ),
    AuditLogActionOption(
        value="create_team",
        translation_key="auditLogs.actioncreate_team",
        fallback_label="Create Team",
    ),
    AuditLogActionOption(
        value="update_team",
        translation_key="auditLogs.actionupdate_team",
        fallback_label="Update Team",
    ),
    AuditLogActionOption(
        value="delete_team",
        translation_key="auditLogs.actiondelete_team",
        fallback_label="Delete Team",
    ),
    AuditLogActionOption(
        value="add_team_member",
        translation_key="auditLogs.actionadd_team_member",
        fallback_label="Add Team Member",
    ),
    AuditLogActionOption(
        value="remove_team_member",
        translation_key="auditLogs.actionremove_team_member",
        fallback_label="Remove Team Member",
    ),
    AuditLogActionOption(
        value="create_agent",
        translation_key="auditLogs.actioncreate_agent",
        fallback_label="Create Agent",
    ),
    AuditLogActionOption(
        value="update_agent",
        translation_key="auditLogs.actionupdate_agent",
        fallback_label="Update Agent",
    ),
    AuditLogActionOption(
        value="delete_agent",
        translation_key="auditLogs.actiondelete_agent",
        fallback_label="Delete Agent",
    ),
    AuditLogActionOption(
        value="publish_agent",
        translation_key="auditLogs.actionpublish_agent",
        fallback_label="Publish Agent",
    ),
    AuditLogActionOption(
        value="unpublish_agent",
        translation_key="auditLogs.actionunpublish_agent",
        fallback_label="Unpublish Agent",
    ),
    AuditLogActionOption(
        value="create_tool",
        translation_key="auditLogs.actioncreate_tool",
        fallback_label="Create Tool",
    ),
    AuditLogActionOption(
        value="update_tool",
        translation_key="auditLogs.actionupdate_tool",
        fallback_label="Update Tool",
    ),
    AuditLogActionOption(
        value="delete_tool",
        translation_key="auditLogs.actiondelete_tool",
        fallback_label="Delete Tool",
    ),
    AuditLogActionOption(
        value="create_workflow",
        translation_key="auditLogs.actioncreate_workflow",
        fallback_label="Create Workflow",
    ),
    AuditLogActionOption(
        value="update_workflow",
        translation_key="auditLogs.actionupdate_workflow",
        fallback_label="Update Workflow",
    ),
    AuditLogActionOption(
        value="delete_workflow",
        translation_key="auditLogs.actiondelete_workflow",
        fallback_label="Delete Workflow",
    ),
    AuditLogActionOption(
        value="trigger_audit_log_archive",
        translation_key="auditLogs.actiontrigger_audit_log_archive",
        fallback_label="Trigger Audit Log Archive",
    ),
    AuditLogActionOption(
        value="update_site_setting",
        translation_key="auditLogs.actionupdate_site_setting",
        fallback_label="Update Site Setting",
    ),
    AuditLogActionOption(
        value="bulk_update_site_settings",
        translation_key="auditLogs.actionbulk_update_site_settings",
        fallback_label="Bulk Update Site Settings",
    ),
    AuditLogActionOption(
        value="reset_site_settings",
        translation_key="auditLogs.actionreset_site_settings",
        fallback_label="Reset Site Settings",
    ),
    AuditLogActionOption(
        value="sso_login_success",
        translation_key="auditLogs.actionsso_login_success",
        fallback_label="SSO Login",
    ),
    AuditLogActionOption(
        value="sso_login_failed",
        translation_key="auditLogs.actionsso_login_failed",
        fallback_label="SSO Login Failed",
    ),
    AuditLogActionOption(
        value="disconnect_sso",
        translation_key="auditLogs.actiondisconnect_sso",
        fallback_label="Disconnect SSO",
    ),
    AuditLogActionOption(
        value="enable_totp",
        translation_key="auditLogs.actionenable_totp",
        fallback_label="Enable Two-Factor Authentication",
    ),
    AuditLogActionOption(
        value="disable_totp",
        translation_key="auditLogs.actiondisable_totp",
        fallback_label="Disable Two-Factor Authentication",
    ),
    AuditLogActionOption(
        value="verify_totp_success",
        translation_key="auditLogs.actionverify_totp_success",
        fallback_label="Verify TOTP Code (Success)",
    ),
    AuditLogActionOption(
        value="verify_totp_failed",
        translation_key="auditLogs.actionverify_totp_failed",
        fallback_label="Verify TOTP Code (Failed)",
    ),
    AuditLogActionOption(
        value="use_backup_code",
        translation_key="auditLogs.actionuse_backup_code",
        fallback_label="Use Backup Code",
    ),
    AuditLogActionOption(
        value="regenerate_backup_codes",
        translation_key="auditLogs.actionregenerate_backup_codes",
        fallback_label="Regenerate Backup Codes",
    ),
    AuditLogActionOption(
        value="admin_disable_totp",
        translation_key="auditLogs.actionadmin_disable_totp",
        fallback_label="Admin Disable User 2FA",
    ),
    AuditLogActionOption(
        value="create_sso_provider",
        translation_key="auditLogs.actioncreate_sso_provider",
        fallback_label="Create SSO Provider",
    ),
    AuditLogActionOption(
        value="update_sso_provider",
        translation_key="auditLogs.actionupdate_sso_provider",
        fallback_label="Update SSO Provider",
    ),
    AuditLogActionOption(
        value="delete_sso_provider",
        translation_key="auditLogs.actiondelete_sso_provider",
        fallback_label="Delete SSO Provider",
    ),
    AuditLogActionOption(
        value="update_auto_notification_config",
        translation_key="auditLogs.actionupdate_auto_notification_config",
        fallback_label="Update Auto Notification Config",
    ),
    AuditLogActionOption(
        value="update_memory_entity",
        translation_key="auditLogs.actionupdate_memory_entity",
        fallback_label="Update Memory Entity",
    ),
    AuditLogActionOption(
        value="delete_memory_entity",
        translation_key="auditLogs.actiondelete_memory_entity",
        fallback_label="Delete Memory Entity",
    ),
    AuditLogActionOption(
        value="delete_memory_relation",
        translation_key="auditLogs.actiondelete_memory_relation",
        fallback_label="Delete Memory Relation",
    ),
    AuditLogActionOption(
        value="agent_create_memory_entity",
        translation_key="auditLogs.actionagent_create_memory_entity",
        fallback_label="Agent Created Memory Entity",
    ),
    AuditLogActionOption(
        value="agent_create_memory_relation",
        translation_key="auditLogs.actionagent_create_memory_relation",
        fallback_label="Agent Created Memory Relation",
    ),
    AuditLogActionOption(
        value="agent_update_memory_entity",
        translation_key="auditLogs.actionagent_update_memory_entity",
        fallback_label="Agent Updated Memory Entity",
    ),
    AuditLogActionOption(
        value="preview_skill_import",
        translation_key="auditLogs.actionpreview_skill_import",
        fallback_label="Preview Skill Import",
    ),
    AuditLogActionOption(
        value="install_skill_import",
        translation_key="auditLogs.actioninstall_skill_import",
        fallback_label="Install Skill Import",
    ),
    AuditLogActionOption(
        value="update_skill",
        translation_key="auditLogs.actionupdate_skill",
        fallback_label="Update Skill",
    ),
    AuditLogActionOption(
        value="delete_skill",
        translation_key="auditLogs.actiondelete_skill",
        fallback_label="Delete Skill",
    ),
    AuditLogActionOption(
        value="test_skill",
        translation_key="auditLogs.actiontest_skill",
        fallback_label="Test Skill",
    ),
    AuditLogActionOption(
        value="admin_preview_skill_import",
        translation_key="auditLogs.actionadmin_preview_skill_import",
        fallback_label="Admin Preview Skill Import",
    ),
    AuditLogActionOption(
        value="admin_install_skill_import",
        translation_key="auditLogs.actionadmin_install_skill_import",
        fallback_label="Admin Install Skill Import",
    ),
    AuditLogActionOption(
        value="admin_update_skill",
        translation_key="auditLogs.actionadmin_update_skill",
        fallback_label="Admin Update Skill",
    ),
    AuditLogActionOption(
        value="admin_delete_skill",
        translation_key="auditLogs.actionadmin_delete_skill",
        fallback_label="Admin Delete Skill",
    ),
    AuditLogActionOption(
        value="admin_test_skill",
        translation_key="auditLogs.actionadmin_test_skill",
        fallback_label="Admin Test Skill",
    ),
    AuditLogActionOption(
        value="admin_create_agent",
        translation_key="auditLogs.actionadmin_create_agent",
        fallback_label="Admin Create Agent",
    ),
    AuditLogActionOption(
        value="admin_update_agent",
        translation_key="auditLogs.actionadmin_update_agent",
        fallback_label="Admin Update Agent",
    ),
    AuditLogActionOption(
        value="admin_publish_agent",
        translation_key="auditLogs.actionadmin_publish_agent",
        fallback_label="Admin Publish Agent",
    ),
    AuditLogActionOption(
        value="admin_unpublish_agent",
        translation_key="auditLogs.actionadmin_unpublish_agent",
        fallback_label="Admin Unpublish Agent",
    ),
    AuditLogActionOption(
        value="admin_duplicate_agent",
        translation_key="auditLogs.actionadmin_duplicate_agent",
        fallback_label="Admin Duplicate Agent",
    ),
    AuditLogActionOption(
        value="admin_delete_agent",
        translation_key="auditLogs.actionadmin_delete_agent",
        fallback_label="Admin Delete Agent",
    ),
    AuditLogActionOption(
        value="admin_create_workflow",
        translation_key="auditLogs.actionadmin_create_workflow",
        fallback_label="Admin Create Workflow",
    ),
    AuditLogActionOption(
        value="admin_update_workflow",
        translation_key="auditLogs.actionadmin_update_workflow",
        fallback_label="Admin Update Workflow",
    ),
    AuditLogActionOption(
        value="admin_publish_workflow",
        translation_key="auditLogs.actionadmin_publish_workflow",
        fallback_label="Admin Publish Workflow",
    ),
    AuditLogActionOption(
        value="admin_unpublish_workflow",
        translation_key="auditLogs.actionadmin_unpublish_workflow",
        fallback_label="Admin Unpublish Workflow",
    ),
    AuditLogActionOption(
        value="admin_duplicate_workflow",
        translation_key="auditLogs.actionadmin_duplicate_workflow",
        fallback_label="Admin Duplicate Workflow",
    ),
    AuditLogActionOption(
        value="admin_delete_workflow",
        translation_key="auditLogs.actionadmin_delete_workflow",
        fallback_label="Admin Delete Workflow",
    ),
    AuditLogActionOption(
        value="duplicate_agent",
        translation_key="auditLogs.actionduplicate_agent",
        fallback_label="Duplicate Agent",
    ),
    AuditLogActionOption(
        value="edit_message",
        translation_key="auditLogs.actionedit_message",
        fallback_label="Edit Message",
    ),
    AuditLogActionOption(
        value="delete_conversation",
        translation_key="auditLogs.actiondelete_conversation",
        fallback_label="Delete Conversation",
    ),
    AuditLogActionOption(
        value="batch_delete_conversations",
        translation_key="auditLogs.actionbatch_delete_conversations",
        fallback_label="Batch Delete Conversations",
    ),
    AuditLogActionOption(
        value="run_workflow_embed",
        translation_key="auditLogs.actionrun_workflow_embed",
        fallback_label="Run Workflow (Embed)",
    ),
    AuditLogActionOption(
        value="upload_document",
        translation_key="auditLogs.actionupload_document",
        fallback_label="Upload Document",
    ),
    AuditLogActionOption(
        value="add_url_document",
        translation_key="auditLogs.actionadd_url_document",
        fallback_label="Add URL Document",
    ),
    AuditLogActionOption(
        value="update_document",
        translation_key="auditLogs.actionupdate_document",
        fallback_label="Update Document",
    ),
    AuditLogActionOption(
        value="delete_document",
        translation_key="auditLogs.actiondelete_document",
        fallback_label="Delete Document",
    ),
    AuditLogActionOption(
        value="process_document",
        translation_key="auditLogs.actionprocess_document",
        fallback_label="Process Document",
    ),
    AuditLogActionOption(
        value="process_document_with_chunks",
        translation_key="auditLogs.actionprocess_document_with_chunks",
        fallback_label="Process Document with Chunks",
    ),
    AuditLogActionOption(
        value="reprocess_document",
        translation_key="auditLogs.actionreprocess_document",
        fallback_label="Reprocess Document",
    ),
    AuditLogActionOption(
        value="retry_failed_chunks",
        translation_key="auditLogs.actionretry_failed_chunks",
        fallback_label="Retry Failed Chunks",
    ),
    AuditLogActionOption(
        value="retry_failed_chunk",
        translation_key="auditLogs.actionretry_failed_chunk",
        fallback_label="Retry Failed Chunk",
    ),
    AuditLogActionOption(
        value="update_document_chunk",
        translation_key="auditLogs.actionupdate_document_chunk",
        fallback_label="Update Document Chunk",
    ),
    AuditLogActionOption(
        value="delete_document_chunk",
        translation_key="auditLogs.actiondelete_document_chunk",
        fallback_label="Delete Document Chunk",
    ),
    AuditLogActionOption(
        value="create_document_chunk",
        translation_key="auditLogs.actioncreate_document_chunk",
        fallback_label="Create Document Chunk",
    ),
    AuditLogActionOption(
        value="rechunk_document",
        translation_key="auditLogs.actionrechunk_document",
        fallback_label="Rechunk Document",
    ),
    AuditLogActionOption(
        value="export_clouisle_package",
        translation_key="auditLogs.actionexport_clouisle_package",
        fallback_label="Export Clouisle Package",
    ),
    AuditLogActionOption(
        value="preview_clouisle_import",
        translation_key="auditLogs.actionpreview_clouisle_import",
        fallback_label="Preview Clouisle Import",
    ),
    AuditLogActionOption(
        value="install_clouisle_package",
        translation_key="auditLogs.actioninstall_clouisle_package",
        fallback_label="Install Clouisle Package",
    ),
    AuditLogActionOption(
        value="test_sso_provider_failed",
        translation_key="auditLogs.actiontest_sso_provider_failed",
        fallback_label="Test SSO Provider Failed",
    ),
    AuditLogActionOption(
        value="create_memory_entity",
        translation_key="auditLogs.actioncreate_memory_entity",
        fallback_label="Create Memory Entity",
    ),
    AuditLogActionOption(
        value="create_memory_relation",
        translation_key="auditLogs.actioncreate_memory_relation",
        fallback_label="Create Memory Relation",
    ),
    AuditLogActionOption(
        value="update_tool_config",
        translation_key="auditLogs.actionupdate_tool_config",
        fallback_label="Update Tool Config",
    ),
    AuditLogActionOption(
        value="delete_tool_config",
        translation_key="auditLogs.actiondelete_tool_config",
        fallback_label="Delete Tool Config",
    ),
    AuditLogActionOption(
        value="generate_prompt",
        translation_key="auditLogs.actiongenerate_prompt",
        fallback_label="Generate Prompt",
    ),
    AuditLogActionOption(
        value="optimize_prompt",
        translation_key="auditLogs.actionoptimize_prompt",
        fallback_label="Optimize Prompt",
    ),
    AuditLogActionOption(
        value="debug_workflow",
        translation_key="auditLogs.actiondebug_workflow",
        fallback_label="Debug Workflow",
    ),
    AuditLogActionOption(
        value="add_team_model",
        translation_key="auditLogs.actionadd_team_model",
        fallback_label="Add Team Model",
    ),
    AuditLogActionOption(
        value="batch_add_team_models",
        translation_key="auditLogs.actionbatch_add_team_models",
        fallback_label="Batch Add Team Models",
    ),
    AuditLogActionOption(
        value="batch_remove_team_models",
        translation_key="auditLogs.actionbatch_remove_team_models",
        fallback_label="Batch Remove Team Models",
    ),
    AuditLogActionOption(
        value="cancel_workflow_run",
        translation_key="auditLogs.actioncancel_workflow_run",
        fallback_label="Cancel Workflow Run",
    ),
    AuditLogActionOption(
        value="create_tool_config",
        translation_key="auditLogs.actioncreate_tool_config",
        fallback_label="Create Tool Config",
    ),
    AuditLogActionOption(
        value="create_workflow_version",
        translation_key="auditLogs.actioncreate_workflow_version",
        fallback_label="Create Workflow Version",
    ),
    AuditLogActionOption(
        value="delete_file",
        translation_key="auditLogs.actiondelete_file",
        fallback_label="Delete File",
    ),
    AuditLogActionOption(
        value="delete_workflow_run",
        translation_key="auditLogs.actiondelete_workflow_run",
        fallback_label="Delete Workflow Run",
    ),
    AuditLogActionOption(
        value="duplicate_tool",
        translation_key="auditLogs.actionduplicate_tool",
        fallback_label="Duplicate Tool",
    ),
    AuditLogActionOption(
        value="duplicate_workflow",
        translation_key="auditLogs.actionduplicate_workflow",
        fallback_label="Duplicate Workflow",
    ),
    AuditLogActionOption(
        value="publish_workflow",
        translation_key="auditLogs.actionpublish_workflow",
        fallback_label="Publish Workflow",
    ),
    AuditLogActionOption(
        value="regenerate_webhook_token",
        translation_key="auditLogs.actionregenerate_webhook_token",
        fallback_label="Regenerate Webhook Token",
    ),
    AuditLogActionOption(
        value="remove_team_model",
        translation_key="auditLogs.actionremove_team_model",
        fallback_label="Remove Team Model",
    ),
    AuditLogActionOption(
        value="restore_workflow_version",
        translation_key="auditLogs.actionrestore_workflow_version",
        fallback_label="Restore Workflow Version",
    ),
    AuditLogActionOption(
        value="run_workflow",
        translation_key="auditLogs.actionrun_workflow",
        fallback_label="Run Workflow",
    ),
    AuditLogActionOption(
        value="share_tool",
        translation_key="auditLogs.actionshare_tool",
        fallback_label="Share Tool",
    ),
    AuditLogActionOption(
        value="toggle_tool",
        translation_key="auditLogs.actiontoggle_tool",
        fallback_label="Toggle Tool",
    ),
    AuditLogActionOption(
        value="unpublish_workflow",
        translation_key="auditLogs.actionunpublish_workflow",
        fallback_label="Unpublish Workflow",
    ),
    AuditLogActionOption(
        value="unshare_tool",
        translation_key="auditLogs.actionunshare_tool",
        fallback_label="Unshare Tool",
    ),
    AuditLogActionOption(
        value="update_team_model",
        translation_key="auditLogs.actionupdate_team_model",
        fallback_label="Update Team Model",
    ),
    AuditLogActionOption(
        value="upload_file",
        translation_key="auditLogs.actionupload_file",
        fallback_label="Upload File",
    ),
    AuditLogActionOption(
        value="upload_image",
        translation_key="auditLogs.actionupload_image",
        fallback_label="Upload Image",
    ),
    AuditLogActionOption(
        value="upload_sandbox_artifact",
        translation_key="auditLogs.actionupload_sandbox_artifact",
        fallback_label="Upload Sandbox Artifact",
    ),
    AuditLogActionOption(
        value="create_knowledge_base",
        translation_key="auditLogs.actioncreate_knowledge_base",
        fallback_label="Create Knowledge Base",
    ),
    AuditLogActionOption(
        value="update_knowledge_base",
        translation_key="auditLogs.actionupdate_knowledge_base",
        fallback_label="Update Knowledge Base",
    ),
    AuditLogActionOption(
        value="delete_knowledge_base",
        translation_key="auditLogs.actiondelete_knowledge_base",
        fallback_label="Delete Knowledge Base",
    ),
]


@router.get("/actions", response_model=Response[list[AuditLogActionOption]])
async def get_audit_log_actions(
    current_user: User = Depends(PermissionChecker("audit:read")),
) -> Any:
    return success(data=AUDIT_ACTION_OPTIONS)


@router.get("", response_model=Response[dict])
async def list_audit_logs(
    user_id: UUID | None = Query(None),
    team_id: UUID | None = Query(None),
    action: list[str] | None = Query(None),
    resource_type: str | None = Query(None),
    resource_id: UUID | None = Query(None),
    status: list[str] | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(PermissionChecker("audit:read")),
) -> Any:
    """
    查询审计日志（需要 audit:read 权限）

    支持多种过滤条件和分页
    """
    # 构建查询条件
    query = AuditLog.all()

    if user_id:
        query = query.filter(user_id=user_id)
    if team_id:
        query = query.filter(team_id=team_id)
    if action:
        query = query.filter(action__in=action)
    if resource_type:
        query = query.filter(resource_type=resource_type)
    if resource_id:
        query = query.filter(resource_id=resource_id)
    if status:
        query = query.filter(status__in=status)
    if start_date:
        query = query.filter(created_at__gte=start_date)
    if end_date:
        query = query.filter(created_at__lte=end_date)
    if search:
        # 搜索资源名称、资源 ID 或 IP 地址
        query = query.filter(
            Q(resource_name__icontains=search)
            | Q(resource_id__icontains=search)
            | Q(ip_address__icontains=search)
        )

    # 获取总数
    total = await query.count()

    # 分页查询
    offset = (page - 1) * page_size
    logs = await query.order_by("-created_at").offset(offset).limit(page_size)

    # 转换为schema
    logs_data = [serialize_audit_log(log) for log in logs]

    return success(
        data={
            "items": logs_data,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
        }
    )


@router.get("/stats", response_model=Response[AuditLogStats])
async def get_audit_log_stats(
    current_user: User = Depends(PermissionChecker("audit:read")),
) -> Any:
    """
    获取审计日志统计信息（需要 audit:read 权限）
    """
    # 总日志数
    total_logs = await AuditLog.all().count()

    # 今日日志数
    today_start = now_utc().replace(hour=0, minute=0, second=0, microsecond=0)
    today_logs = await AuditLog.filter(created_at__gte=today_start).count()

    # 失败日志数
    failed_logs = await AuditLog.filter(status="failed").count()

    # 活跃用户数（最近7天）
    seven_days_ago = now_utc() - timedelta(days=7)
    active_users = (
        await AuditLog.filter(created_at__gte=seven_days_ago)
        .distinct()
        .values_list("user_id", flat=True)
    )
    active_users_count = len([u for u in active_users if u])

    # Top 5 操作类型
    from tortoise.functions import Count

    top_actions = (
        await AuditLog.all()
        .annotate(count=Count("id"))
        .group_by("action")
        .order_by("-count")
        .limit(5)
        .values("action", "count")
    )

    # Top 5 活跃用户
    top_users = (
        await AuditLog.filter(user_id__not_isnull=True)
        .annotate(count=Count("id"))
        .group_by("user_id", "username")
        .order_by("-count")
        .limit(5)
        .values("user_id", "username", "count")
    )

    return success(
        data=AuditLogStats(
            total_logs=total_logs,
            today_logs=today_logs,
            failed_logs=failed_logs,
            active_users=active_users_count,
            top_actions=top_actions,
            top_users=top_users,
        )
    )


@router.get("/stats/retention", response_model=Response[AuditLogRetentionStats])
async def get_retention_stats(
    current_user: User = Depends(PermissionChecker("audit:read")),
) -> Any:
    """获取日志保留统计信息（需要 audit:read 权限）"""
    retention_days = await SiteSetting.get_value("audit_log_retention_days", 365)
    cutoff_date = now_utc() - timedelta(days=retention_days)

    total_logs = await AuditLog.all().count()
    logs_to_archive = await AuditLog.filter(created_at__lt=cutoff_date).count()
    oldest_log = await AuditLog.all().order_by("created_at").first()

    return success(
        data=AuditLogRetentionStats(
            total_logs=total_logs,
            logs_to_archive=logs_to_archive,
            oldest_log_date=oldest_log.created_at.isoformat() if oldest_log else None,
            retention_days=retention_days,
            cutoff_date=cutoff_date.isoformat(),
            next_archive_date=(now_utc() + timedelta(days=1))
            .replace(hour=3, minute=0, second=0, microsecond=0)
            .isoformat(),
        )
    )


@router.post("/archive", response_model=Response[dict])
async def trigger_manual_archive(
    current_user: User = Depends(PermissionChecker("audit:export")),
) -> Any:
    """手动触发归档任务（需要 audit:export 权限）"""
    from app.tasks.audit_log import archive_old_audit_logs

    # 异步执行归档任务
    task = archive_old_audit_logs.delay()  # type: ignore[attr-defined]

    return success(data={"task_id": str(task.id)}, msg_key="archive_task_started")


@router.get("/export", response_model=None)
async def export_audit_logs(
    format: str = Query("csv", pattern="^(csv|json)$"),
    user_id: UUID | None = Query(None),
    team_id: UUID | None = Query(None),
    action: list[str] | None = Query(None),
    resource_type: str | None = Query(None),
    status: list[str] | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    search: str | None = Query(None),
    current_user: User = Depends(PermissionChecker("audit:export")),
) -> Any:
    """
    导出审计日志（需要 audit:export 权限）

    支持CSV和JSON格式
    """
    # 构建查询条件（与list_audit_logs相同）
    query = AuditLog.all()

    if user_id:
        query = query.filter(user_id=user_id)
    if team_id:
        query = query.filter(team_id=team_id)
    if action:
        query = query.filter(action__in=action)
    if resource_type:
        query = query.filter(resource_type=resource_type)
    if status:
        query = query.filter(status__in=status)
    if start_date:
        query = query.filter(created_at__gte=start_date)
    if end_date:
        query = query.filter(created_at__lte=end_date)
    if search:
        query = query.filter(
            Q(resource_name__icontains=search) | Q(ip_address__icontains=search)
        )

    # 获取所有日志（限制最多10000条）
    logs = await query.order_by("-created_at").limit(10000)

    if format == "csv":
        # 生成CSV
        output = StringIO()
        writer = csv.writer(output)

        # 写入表头
        writer.writerow(
            [
                "ID",
                "Time",
                "User",
                "Action",
                "Resource Type",
                "Resource Name",
                "Operation",
                "Status",
                "IP Address",
                "Error Message",
            ]
        )

        # 写入数据
        for log in logs:
            writer.writerow(
                [
                    str(log.id),
                    log.created_at.isoformat() if log.created_at else "",
                    log.username or "",
                    log.action,
                    log.resource_type,
                    log.resource_name or "",
                    log.operation,
                    log.status,
                    log.ip_address or "",
                    serialize_audit_error(log.error_message) or "",
                ]
            )

        # 返回CSV文件
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=audit-logs-{now_utc().strftime('%Y%m%d-%H%M%S')}.csv"
            },
        )

    else:  # JSON
        # 生成JSON
        logs_data = [serialize_audit_log(log).model_dump(mode="json") for log in logs]
        json_str = json.dumps(logs_data, indent=2, ensure_ascii=False)

        return StreamingResponse(
            iter([json_str]),
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename=audit-logs-{now_utc().strftime('%Y%m%d-%H%M%S')}.json"
            },
        )


@router.get("/{log_id}", response_model=Response[AuditLogSchema])
async def get_audit_log(
    log_id: UUID,
    current_user: User = Depends(PermissionChecker("audit:read")),
) -> Any:
    """获取单个审计日志详情（需要 audit:read 权限）"""
    log = await AuditLog.get_or_none(id=log_id)
    if not log:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="audit_log_not_found",
        )

    return success(data=serialize_audit_log(log))
