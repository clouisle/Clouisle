from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr

from app.api.deps import PermissionChecker
from app.models import SiteSetting, DEFAULT_SETTINGS, User
from app.models.notification import AutoNotificationType
from app.models.user_sso_connection import UserSSOConnection
from app.schemas.site_setting import (
    SiteSettingResponse,
    SiteSettingUpdate,
    SiteSettingBulkUpdate,
    SiteSettingsResponse,
    PublicSiteSettingsResponse,
    AutoNotificationConfigResponse,
    AutoNotificationConfigUpdate,
)
from app.schemas.response import Response, ResponseCode, BusinessError, success
from app.core.email import send_email
from app.services.audit_log import AuditLogService
from app.tasks.audit_log import archive_old_audit_logs

router = APIRouter()


async def _ensure_superadmin_sso_bound() -> None:
    count = await UserSSOConnection.filter(user__is_superuser=True).count()
    if count == 0:
        raise BusinessError(
            code=ResponseCode.FORBIDDEN,
            msg_key="require_superadmin_sso",
        )


class TestEmailRequest(BaseModel):
    """测试邮件请求"""

    email: EmailStr


@router.get("/public", response_model=Response[PublicSiteSettingsResponse])
async def get_public_settings():
    """Get public site settings (no authentication required)"""
    settings = await SiteSetting.get_all_by_category(public_only=True)
    return success(
        data=PublicSiteSettingsResponse(
            site_name=settings.get("site_name", "Clouisle"),
            site_description=settings.get("site_description", ""),
            site_url=settings.get("site_url", ""),
            site_icon=settings.get("site_icon", ""),
            allow_registration=settings.get("allow_registration", True),
            require_approval=settings.get("require_approval", False),
            email_verification=settings.get("email_verification", True),
            enable_captcha=settings.get("enable_captcha", False),
            allow_account_deletion=settings.get("allow_account_deletion", True),
            sso_enabled=settings.get("sso_enabled", False),
            sso_allow_password_login=settings.get("sso_allow_password_login", True),
        )
    )


@router.get("", response_model=Response[SiteSettingsResponse])
async def get_all_settings(
    category: Optional[str] = None,
    current_user: User = Depends(PermissionChecker("settings:read")),
):
    """Get all site settings (requires settings:read permission)"""
    settings = await SiteSetting.get_all_by_category(category=category)
    return success(data=SiteSettingsResponse(settings=settings))


@router.get(
    "/auto-notifications", response_model=Response[AutoNotificationConfigResponse]
)
async def get_auto_notification_config(
    current_user: User = Depends(PermissionChecker("settings:read")),
):
    """Get auto notification configuration (requires settings:read permission)"""
    config = await SiteSetting.get_value("auto_notification_config", {})

    return success(
        data=AutoNotificationConfigResponse(
            channels=config.get("channels", []),
            enabled_types=config.get("enabled_types", []),
        )
    )


@router.put(
    "/auto-notifications", response_model=Response[AutoNotificationConfigResponse]
)
async def update_auto_notification_config(
    request: Request,
    data: AutoNotificationConfigUpdate,
    current_user: User = Depends(PermissionChecker("settings:update")),
):
    """Update auto notification configuration (requires settings:update permission)"""
    # Get current config for audit log
    old_config = await SiteSetting.get_value("auto_notification_config", {})

    # Validate notification types
    valid_types = {t.value for t in AutoNotificationType}
    for type_key in data.enabled_types:
        if type_key not in valid_types:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg=f"Invalid notification type: {type_key}",
            )

    new_config = {
        "channels": data.channels,
        "enabled_types": data.enabled_types,
    }

    # Save config
    await SiteSetting.set_value(
        key="auto_notification_config",
        value=new_config,
        value_type="json",
        category="notification",
        description="Auto notification configuration",
        is_public=False,
    )

    # Audit log
    await AuditLogService.log(
        user=current_user,
        action="update_auto_notification_config",
        resource_type="site_setting",
        resource_id=None,
        resource_name="auto_notification_config",
        operation="update",
        status="success",
        request=request,
        changes={
            "before": old_config,
            "after": new_config,
        },
    )

    return success(
        data=AutoNotificationConfigResponse(
            channels=new_config["channels"],
            enabled_types=new_config["enabled_types"],
        )
    )


@router.get("/{key}", response_model=Response[SiteSettingResponse])
async def get_setting(
    key: str,
    current_user: User = Depends(PermissionChecker("settings:read")),
):
    """Get a specific setting by key (requires settings:read permission)"""
    setting = await SiteSetting.filter(key=key).first()
    if not setting:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg=f"Setting '{key}' not found",
        )
    return success(
        data=SiteSettingResponse(
            key=setting.key,
            value=SiteSetting._convert_value(setting.value, setting.value_type),
            value_type=setting.value_type,
            category=setting.category,
            description=setting.description,
            is_public=setting.is_public,
        )
    )


@router.put("/{key}", response_model=Response[SiteSettingResponse])
async def update_setting(
    request: Request,
    key: str,
    data: SiteSettingUpdate,
    current_user: User = Depends(PermissionChecker("settings:update")),
):
    """Update a specific setting (requires settings:update permission)"""
    # 获取旧值用于审计日志
    old_setting = await SiteSetting.filter(key=key).first()
    old_value = None
    if old_setting:
        old_value = SiteSetting._convert_value(
            old_setting.value, old_setting.value_type
        )

    if key == "sso_allow_password_login" and data.value is False:
        await _ensure_superadmin_sso_bound()

    setting = await SiteSetting.filter(key=key).first()
    if not setting:
        # Check if it's a known default setting
        if key in DEFAULT_SETTINGS:
            config = DEFAULT_SETTINGS[key]
            setting = await SiteSetting.set_value(
                key=key,
                value=data.value,
                value_type=config["type"],
                category=config["category"],
                description=config["desc"],
                is_public=config["public"],
            )
        else:
            raise BusinessError(
                code=ResponseCode.NOT_FOUND,
                msg=f"Setting '{key}' not found",
            )
    else:
        setting = await SiteSetting.set_value(
            key=key,
            value=data.value,
            value_type=setting.value_type,
            category=setting.category,
            description=setting.description,
            is_public=setting.is_public,
        )

    # 记录审计日志
    await AuditLogService.log(
        user=current_user,
        action="update_site_setting",
        resource_type="site_setting",
        resource_id=None,
        resource_name=key,
        operation="update",
        status="success",
        request=request,
        changes={
            "before": {"value": old_value},
            "after": {"value": data.value},
        },
        metadata={"category": setting.category},
    )

    return success(
        data=SiteSettingResponse(
            key=setting.key,
            value=SiteSetting._convert_value(setting.value, setting.value_type),
            value_type=setting.value_type,
            category=setting.category,
            description=setting.description,
            is_public=setting.is_public,
        )
    )


@router.put("", response_model=Response[SiteSettingsResponse])
async def bulk_update_settings(
    request: Request,
    data: SiteSettingBulkUpdate,
    current_user: User = Depends(PermissionChecker("settings:update")),
):
    """Bulk update multiple settings (requires settings:update permission)"""
    if data.settings.get("sso_allow_password_login") is False:
        await _ensure_superadmin_sso_bound()

    updated_keys = []
    for key, value in data.settings.items():
        setting = await SiteSetting.filter(key=key).first()
        if setting:
            await SiteSetting.set_value(
                key=key,
                value=value,
                value_type=setting.value_type,
                category=setting.category,
                description=setting.description,
                is_public=setting.is_public,
            )
            updated_keys.append(key)
        elif key in DEFAULT_SETTINGS:
            config = DEFAULT_SETTINGS[key]
            await SiteSetting.set_value(
                key=key,
                value=value,
                value_type=config["type"],
                category=config["category"],
                description=config["desc"],
                is_public=config["public"],
            )
            updated_keys.append(key)

    # 记录审计日志
    await AuditLogService.log(
        user=current_user,
        action="bulk_update_site_settings",
        resource_type="site_setting",
        resource_id=None,
        resource_name="bulk_update",
        operation="update",
        status="success",
        request=request,
        metadata={
            "updated_keys": updated_keys,
            "count": len(updated_keys),
        },
    )

    # Return all settings
    settings = await SiteSetting.get_all_by_category()
    return success(data=SiteSettingsResponse(settings=settings))


@router.post("/reset", response_model=Response[SiteSettingsResponse])
async def reset_settings(
    request: Request,
    category: Optional[str] = None,
    current_user: User = Depends(PermissionChecker("settings:update")),
):
    """Reset settings to default values (requires settings:update permission)"""
    reset_keys = []
    for key, config in DEFAULT_SETTINGS.items():
        if category and config["category"] != category:
            continue
        await SiteSetting.set_value(
            key=key,
            value=config["value"],
            value_type=config["type"],
            category=config["category"],
            description=config["desc"],
            is_public=config["public"],
        )
        reset_keys.append(key)

    # 记录审计日志
    await AuditLogService.log(
        user=current_user,
        action="reset_site_settings",
        resource_type="site_setting",
        resource_id=None,
        resource_name="reset",
        operation="update",
        status="success",
        request=request,
        metadata={
            "category": category,
            "reset_keys": reset_keys,
            "count": len(reset_keys),
        },
    )

    settings = await SiteSetting.get_all_by_category(category=category)
    return success(data=SiteSettingsResponse(settings=settings))


@router.post("/test-email", response_model=Response[None])
async def send_test_email(
    data: TestEmailRequest,
    current_user: User = Depends(PermissionChecker("settings:update")),
):
    """Send a test email to verify SMTP configuration (requires settings:update permission)"""
    # Check if SMTP is enabled
    smtp_enabled = await SiteSetting.get_value("smtp_enabled", False)
    if not smtp_enabled:
        raise BusinessError(
            code=ResponseCode.EMAIL_SEND_FAILED,
            msg_key="smtp_not_configured",
        )

    site_name = await SiteSetting.get_value("site_name", "Clouisle")

    subject = f"【{site_name}】测试邮件 / Test Email"
    body_text = f"""这是一封来自 {site_name} 的测试邮件。

如果您收到了这封邮件，说明 SMTP 配置正确。

---

This is a test email from {site_name}.

If you received this email, your SMTP configuration is working correctly."""

    body_html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
    <h2 style="color: #333;">✅ SMTP 配置测试成功</h2>
    <p>这是一封来自 <strong>{site_name}</strong> 的测试邮件。</p>
    <p style="color: #666;">如果您收到了这封邮件，说明 SMTP 配置正确。</p>
    <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
    <h2 style="color: #333;">✅ SMTP Configuration Test Successful</h2>
    <p>This is a test email from <strong>{site_name}</strong>.</p>
    <p style="color: #666;">If you received this email, your SMTP configuration is working correctly.</p>
</body>
</html>
"""

    result = await send_email(data.email, subject, body_text, body_html)

    if not result:
        raise BusinessError(
            code=ResponseCode.EMAIL_SEND_FAILED,
            msg_key="email_send_failed",
        )

    return success(msg_key="test_email_sent")


@router.post("/test-dingtalk", response_model=Response[None])
async def send_test_dingtalk(
    current_user: User = Depends(PermissionChecker("settings:update")),
):
    """Send a test DingTalk message to verify configuration (requires settings:update permission)"""
    from app.core.dingtalk import get_dingtalk_config, send_dingtalk_notification

    config = await get_dingtalk_config()

    if not config["enabled"]:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="dingtalk_not_enabled",
        )

    if config["notification_type"] == "webhook":
        if not config["webhook_url"]:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg_key="dingtalk_not_configured",
            )
    elif config["notification_type"] == "app":
        if not config["app_key"] or not config["app_secret"] or not config["agent_id"]:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg_key="dingtalk_not_configured",
            )

    site_name = await SiteSetting.get_value("site_name", "Clouisle")

    result = await send_dingtalk_notification(
        title=f"【{site_name}】测试消息",
        content="这是一条测试消息，如果您收到此消息，说明钉钉通知配置正确。\n\nThis is a test message. If you received this, your DingTalk configuration is working correctly.",
    )

    if not result:
        raise BusinessError(
            code=ResponseCode.INTERNAL_ERROR,
            msg_key="dingtalk_send_failed",
        )

    return success(msg_key="test_dingtalk_sent")


@router.post("/test-wechat", response_model=Response[None])
async def send_test_wechat(
    current_user: User = Depends(PermissionChecker("settings:update")),
):
    """Send a test WeChat Work message to verify configuration (requires settings:update permission)"""
    from app.core.wechat import get_wechat_config, send_wechat_notification

    config = await get_wechat_config()

    if not config["enabled"]:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="wechat_not_enabled",
        )

    if config["notification_type"] == "webhook":
        if not config["webhook_url"]:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg_key="wechat_not_configured",
            )
    elif config["notification_type"] == "app":
        if not config["corp_id"] or not config["secret"] or not config["agent_id"]:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg_key="wechat_not_configured",
            )

    site_name = await SiteSetting.get_value("site_name", "Clouisle")

    result = await send_wechat_notification(
        title=f"【{site_name}】测试消息",
        content="这是一条测试消息，如果您收到此消息，说明企业微信通知配置正确。\n\nThis is a test message. If you received this, your WeChat Work configuration is working correctly.",
    )

    if not result:
        raise BusinessError(
            code=ResponseCode.INTERNAL_ERROR,
            msg_key="wechat_send_failed",
        )

    return success(msg_key="test_wechat_sent")


@router.post("/test-feishu", response_model=Response[None])
async def send_test_feishu(
    current_user: User = Depends(PermissionChecker("settings:update")),
):
    """Send a test Feishu message to verify configuration (requires settings:update permission)"""
    from app.core.feishu import get_feishu_config, send_feishu_notification

    config = await get_feishu_config()

    if not config["enabled"]:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="feishu_not_enabled",
        )

    if config["notification_type"] == "webhook":
        if not config["webhook_url"]:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg_key="feishu_not_configured",
            )
    elif config["notification_type"] == "app":
        if not config["app_id"] or not config["app_secret"]:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg_key="feishu_not_configured",
            )

    site_name = await SiteSetting.get_value("site_name", "Clouisle")

    result = await send_feishu_notification(
        title=f"【{site_name}】测试消息",
        content="这是一条测试消息，如果您收到此消息，说明飞书通知配置正确。\n\nThis is a test message. If you received this, your Feishu configuration is working correctly.",
    )

    if not result:
        raise BusinessError(
            code=ResponseCode.INTERNAL_ERROR,
            msg_key="feishu_send_failed",
        )

    return success(msg_key="test_feishu_sent")


@router.post("/test-webhook", response_model=Response[None])
async def send_test_webhook(
    current_user: User = Depends(PermissionChecker("settings:update")),
):
    """Send a test Webhook message to verify configuration (requires settings:update permission)"""
    from app.core.webhook import get_webhook_config, send_webhook_notification

    config = await get_webhook_config()

    if not config["enabled"]:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="webhook_not_enabled",
        )

    if not config["url"]:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="webhook_not_configured",
        )

    site_name = await SiteSetting.get_value("site_name", "Clouisle")

    result = await send_webhook_notification(
        title=f"【{site_name}】测试消息",
        content="这是一条测试消息，如果您收到此消息，说明 Webhook 通知配置正确。\n\nThis is a test message. If you received this, your Webhook configuration is working correctly.",
    )

    if not result:
        raise BusinessError(
            code=ResponseCode.INTERNAL_ERROR,
            msg_key="webhook_send_failed",
        )

    return success(msg_key="test_webhook_sent")


@router.post("/test-slack", response_model=Response[None])
async def send_test_slack(
    current_user: User = Depends(PermissionChecker("settings:update")),
):
    """Send a test Slack message to verify configuration (requires settings:update permission)"""
    from app.core.slack import get_slack_config, send_slack_notification

    config = await get_slack_config()

    if not config["enabled"]:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="slack_not_enabled",
        )

    if not config["webhook_url"]:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="slack_not_configured",
        )

    site_name = await SiteSetting.get_value("site_name", "Clouisle")

    result = await send_slack_notification(
        title=f"【{site_name}】Test Message",
        content="This is a test message. If you received this, your Slack configuration is working correctly.\n\n这是一条测试消息，如果您收到此消息，说明 Slack 通知配置正确。",
    )

    if not result:
        raise BusinessError(
            code=ResponseCode.INTERNAL_ERROR,
            msg_key="slack_send_failed",
        )

    return success(msg_key="test_slack_sent")


@router.post("/archive-audit-logs", response_model=Response[dict])
async def trigger_archive_audit_logs(
    request: Request,
    current_user: User = Depends(PermissionChecker("audit:export")),
):
    """Manually trigger audit log archiving (requires audit:export permission)"""
    # 同步执行归档任务
    result = await archive_old_audit_logs()

    # 记录审计日志
    await AuditLogService.log(
        user=current_user,
        action="trigger_audit_log_archive",
        resource_type="system",
        resource_id=None,
        resource_name="audit_log_archive",
        operation="execute",
        status="success" if result.get("status") == "success" else "failed",
        request=request,
        metadata=result,
    )

    if result.get("status") == "failed":
        raise BusinessError(
            code=ResponseCode.INTERNAL_ERROR,
            msg=result.get("error", "Archive failed"),
        )

    return success(
        data={
            "archived_count": result.get("archived_count", 0),
            "retention_days": result.get("retention_days", 0),
            "cutoff_date": result.get("cutoff_date", ""),
        },
        msg_key="archive_task_completed",
    )
