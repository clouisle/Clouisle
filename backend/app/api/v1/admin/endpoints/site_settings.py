from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr

from app.api.deps import PermissionChecker
from app.models import (
    SiteSetting,
    DEFAULT_SETTINGS,
    User,
    KB_DOCUMENT_MIN_MAX_UPLOAD_SIZE_MB,
    KB_DOCUMENT_MAX_MAX_UPLOAD_SIZE_MB,
)
from app.models.notification import AutoNotificationType
from app.models.user_sso_connection import UserSSOConnection
from app.schemas.site_setting import (
    SiteSettingResponse,
    SiteSettingUpdate,
    SiteSettingBulkUpdate,
    SiteSettingsResponse,
    AutoNotificationConfigResponse,
    AutoNotificationConfigUpdate,
)
from app.schemas.response import Response, ResponseCode, BusinessError, success
from app.core.email import send_email
from app.core.i18n import t
from app.services.audit_log import AuditLogService
from app.tasks.audit_log import archive_old_audit_logs

router = APIRouter()


def _validate_setting_value(key: str, value: object) -> None:
    if key != "kb_document_max_upload_size_mb":
        return
    if not isinstance(value, int) or isinstance(value, bool):
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="validation_error",
        )
    if (
        value < KB_DOCUMENT_MIN_MAX_UPLOAD_SIZE_MB
        or value > KB_DOCUMENT_MAX_MAX_UPLOAD_SIZE_MB
    ):
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="validation_error",
        )


async def _ensure_superadmin_sso_bound() -> None:
    count = await UserSSOConnection.filter(user__is_superuser=True).count()
    if count == 0:
        raise BusinessError(
            code=ResponseCode.FORBIDDEN,
            msg_key="require_superadmin_sso",
        )


class TestEmailRequest(BaseModel):
    email: EmailStr


@router.get("", response_model=Response[SiteSettingsResponse])
async def get_all_settings(
    category: Optional[str] = None,
    current_user: User = Depends(PermissionChecker("admin:settings:read")),
):
    settings = await SiteSetting.get_all_by_category(category=category)
    return success(data=SiteSettingsResponse(settings=settings))


@router.get(
    "/auto-notifications", response_model=Response[AutoNotificationConfigResponse]
)
async def get_auto_notification_config(
    current_user: User = Depends(PermissionChecker("admin:settings:read")),
):
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
    current_user: User = Depends(PermissionChecker("admin:settings:update")),
):
    old_config = await SiteSetting.get_value("auto_notification_config", {})

    valid_types = {t.value for t in AutoNotificationType}
    for type_key in data.enabled_types:
        if type_key not in valid_types:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg_key="invalid_notification_type",
                type_key=type_key,
            )

    new_config = {
        "channels": data.channels,
        "enabled_types": data.enabled_types,
    }

    await SiteSetting.set_value(
        key="auto_notification_config",
        value=new_config,
        value_type="json",
        category="notification",
        description="Auto notification configuration",
        is_public=False,
    )

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
    current_user: User = Depends(PermissionChecker("admin:settings:read")),
):
    setting = await SiteSetting.filter(key=key).first()
    if not setting:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="setting_not_found",
            key=key,
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
    current_user: User = Depends(PermissionChecker("admin:settings:update")),
):
    old_setting = await SiteSetting.filter(key=key).first()
    old_value = None
    if old_setting:
        old_value = SiteSetting._convert_value(
            old_setting.value, old_setting.value_type
        )

    if key == "sso_allow_password_login" and data.value is False:
        await _ensure_superadmin_sso_bound()
    _validate_setting_value(key, data.value)

    setting = await SiteSetting.filter(key=key).first()
    if not setting:
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
                msg_key="setting_not_found",
                key=key,
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
    current_user: User = Depends(PermissionChecker("admin:settings:update")),
):
    if data.settings.get("sso_allow_password_login") is False:
        await _ensure_superadmin_sso_bound()
    for key, value in data.settings.items():
        _validate_setting_value(key, value)

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

    settings = await SiteSetting.get_all_by_category()
    return success(data=SiteSettingsResponse(settings=settings))


@router.post("/reset", response_model=Response[SiteSettingsResponse])
async def reset_settings(
    request: Request,
    category: Optional[str] = None,
    current_user: User = Depends(PermissionChecker("admin:settings:update")),
):
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
    current_user: User = Depends(PermissionChecker("admin:settings:update")),
):
    smtp_enabled = await SiteSetting.get_value("smtp_enabled", False)
    if not smtp_enabled:
        raise BusinessError(
            code=ResponseCode.EMAIL_SEND_FAILED,
            msg_key="smtp_not_configured",
        )

    site_name = await SiteSetting.get_value("site_name", "Clouisle")

    subject = t("test_email_subject", site_name=site_name)
    body_text = t("test_email_body_text", site_name=site_name)
    body_html = t("test_email_body_html", site_name=site_name)

    result = await send_email(data.email, subject, body_text, body_html)

    if not result:
        raise BusinessError(
            code=ResponseCode.EMAIL_SEND_FAILED,
            msg_key="email_send_failed",
        )

    return success(msg_key="test_email_sent")


@router.post("/test-dingtalk", response_model=Response[None])
async def send_test_dingtalk(
    current_user: User = Depends(PermissionChecker("admin:settings:update")),
):
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
        title=t("test_notification_title", site_name=site_name),
        content=t("test_dingtalk_content"),
    )

    if not result:
        raise BusinessError(
            code=ResponseCode.INTERNAL_ERROR,
            msg_key="dingtalk_send_failed",
        )

    return success(msg_key="test_dingtalk_sent")


@router.post("/test-wechat", response_model=Response[None])
async def send_test_wechat(
    current_user: User = Depends(PermissionChecker("admin:settings:update")),
):
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
        title=t("test_notification_title", site_name=site_name),
        content=t("test_wechat_content"),
    )

    if not result:
        raise BusinessError(
            code=ResponseCode.INTERNAL_ERROR,
            msg_key="wechat_send_failed",
        )

    return success(msg_key="test_wechat_sent")


@router.post("/test-feishu", response_model=Response[None])
async def send_test_feishu(
    current_user: User = Depends(PermissionChecker("admin:settings:update")),
):
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
        title=t("test_notification_title", site_name=site_name),
        content=t("test_feishu_content"),
    )

    if not result:
        raise BusinessError(
            code=ResponseCode.INTERNAL_ERROR,
            msg_key="feishu_send_failed",
        )

    return success(msg_key="test_feishu_sent")


@router.post("/test-webhook", response_model=Response[None])
async def send_test_webhook(
    current_user: User = Depends(PermissionChecker("admin:settings:update")),
):
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
        title=t("test_notification_title", site_name=site_name),
        content=t("test_webhook_content"),
    )

    if not result:
        raise BusinessError(
            code=ResponseCode.INTERNAL_ERROR,
            msg_key="webhook_send_failed",
        )

    return success(msg_key="test_webhook_sent")


@router.post("/test-slack", response_model=Response[None])
async def send_test_slack(
    current_user: User = Depends(PermissionChecker("admin:settings:update")),
):
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
        title=t("test_notification_title", site_name=site_name),
        content=t("test_slack_content"),
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
    try:
        # Use Celery task to avoid blocking the server
        task = archive_old_audit_logs.delay()  # type: ignore[attr-defined]
        task_id = task.id
    except Exception:
        # Log error without exposing stack trace to user
        await AuditLogService.log(
            user=current_user,
            action="trigger_audit_log_archive",
            resource_type="system",
            resource_id=None,
            resource_name="audit_log_archive",
            operation="execute",
            status="failed",
            request=request,
        )
        raise BusinessError(
            code=ResponseCode.INTERNAL_ERROR,
            msg_key="archive_failed",
        )

    await AuditLogService.log(
        user=current_user,
        action="trigger_audit_log_archive",
        resource_type="system",
        resource_id=None,
        resource_name="audit_log_archive",
        operation="execute",
        status="pending",
        request=request,
        metadata={"task_id": task_id},
    )

    return success(
        data={"task_id": task_id, "status": "pending"},
        msg_key="archive_task_started",
    )
