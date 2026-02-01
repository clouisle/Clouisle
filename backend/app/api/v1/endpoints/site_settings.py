from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr

from app.api.deps import get_current_active_superuser
from app.models import SiteSetting, DEFAULT_SETTINGS, User
from app.schemas.site_setting import (
    SiteSettingResponse,
    SiteSettingUpdate,
    SiteSettingBulkUpdate,
    SiteSettingsResponse,
    PublicSiteSettingsResponse,
)
from app.schemas.response import Response, ResponseCode, BusinessError, success
from app.core.email import send_email
from app.services.audit_log import AuditLogService

router = APIRouter()


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
        )
    )


@router.get("", response_model=Response[SiteSettingsResponse])
async def get_all_settings(
    category: Optional[str] = None,
    current_user: User = Depends(get_current_active_superuser),
):
    """Get all site settings (admin only)"""
    settings = await SiteSetting.get_all_by_category(category=category)
    return success(data=SiteSettingsResponse(settings=settings))


@router.get("/{key}", response_model=Response[SiteSettingResponse])
async def get_setting(
    key: str,
    current_user: User = Depends(get_current_active_superuser),
):
    """Get a specific setting by key (admin only)"""
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
    current_user: User = Depends(get_current_active_superuser),
):
    """Update a specific setting (admin only)"""
    # 获取旧值用于审计日志
    old_setting = await SiteSetting.filter(key=key).first()
    old_value = None
    if old_setting:
        old_value = SiteSetting._convert_value(old_setting.value, old_setting.value_type)

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
    current_user: User = Depends(get_current_active_superuser),
):
    """Bulk update multiple settings (admin only)"""
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
    current_user: User = Depends(get_current_active_superuser),
):
    """Reset settings to default values (admin only)"""
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
    current_user: User = Depends(get_current_active_superuser),
):
    """Send a test email to verify SMTP configuration (admin only)"""
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
