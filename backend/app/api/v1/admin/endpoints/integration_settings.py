"""Typed builtin configuration and global login policy management."""

import json
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr, Field

from app.api.deps import PermissionChecker
from app.core.email import send_email
from app.core.i18n import t
from app.core.webhook import get_webhook_config, send_webhook_notification
from app.models import DEFAULT_SETTINGS, SiteSetting, User
from app.models.user_sso_connection import UserSSOConnection
from app.schemas.response import BusinessError, Response, ResponseCode, success
from app.services.audit_log import AuditLogService
from app.services.integration_config import (
    get_builtin_integration,
    update_builtin_config,
)

router = APIRouter()


class SSOSettings(BaseModel):
    sso_enabled: bool = False
    sso_allow_password_login: bool = True
    sso_auto_create_users: bool = True
    sso_require_approval: bool = False
    sso_match_by_email: bool = True


class EmailSettings(BaseModel):
    smtp_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_encryption: Literal["none", "ssl", "tls"] = "tls"
    smtp_username: str = ""
    smtp_password: str = ""
    email_from_name: str = "Clouisle"
    email_from_address: str = ""


class WebhookSettings(BaseModel):
    webhook_enabled: bool = False
    webhook_url: str = ""
    webhook_method: Literal["POST", "GET"] = "POST"
    webhook_headers: dict[str, str] = Field(default_factory=dict)
    webhook_body_template: str = (
        '{"title": "{{title}}", "content": "{{content}}", "link_url": "{{link_url}}"}'
    )
    webhook_secret: str = ""


class TestEmailRequest(BaseModel):
    email: EmailStr


@router.get("/login-settings", response_model=Response[SSOSettings])
async def get_login_settings(
    current_user: User = Depends(PermissionChecker("admin:integrations:login:read")),
):
    values = {
        key: await SiteSetting.get_value(key, value)
        for key, value in SSOSettings().model_dump().items()
    }
    return success(data=SSOSettings(**values))


@router.put("/login-settings", response_model=Response[SSOSettings])
async def update_login_settings(
    request: Request,
    data: SSOSettings,
    current_user: User = Depends(PermissionChecker("admin:integrations:login:update")),
):
    values = data.model_dump(exclude_unset=True)
    if values.get("sso_allow_password_login") is False:
        if await UserSSOConnection.filter(user__is_superuser=True).count() == 0:
            raise BusinessError(
                code=ResponseCode.FORBIDDEN, msg_key="require_superadmin_sso"
            )
    before = {key: await SiteSetting.get_value(key) for key in values}
    for key, value in values.items():
        await SiteSetting.set_value(
            key,
            value,
            value_type="bool",
            category="integration",
            is_public=DEFAULT_SETTINGS[key]["public"],
        )
    await AuditLogService.log(
        user=current_user,
        action="update_site_settings",
        resource_type="site_setting",
        resource_id=None,
        resource_name="login_settings",
        operation="update",
        status="success",
        request=request,
        changes={"before": before, "after": values},
    )
    return await get_login_settings(current_user)


@router.get("/email", response_model=Response[EmailSettings])
async def get_email_settings(
    current_user: User = Depends(PermissionChecker("admin:integrations:settings:read")),
):
    integration = await get_builtin_integration("email")
    return success(
        data=EmailSettings(
            **{
                **integration.config,
                "smtp_enabled": integration.is_enabled,
                "smtp_password": "",
            }
        )
    )


@router.put("/email", response_model=Response[EmailSettings])
async def update_email_settings(
    request: Request,
    data: EmailSettings,
    current_user: User = Depends(
        PermissionChecker("admin:integrations:settings:update")
    ),
):
    values = data.model_dump(exclude_unset=True)
    enabled = values.pop("smtp_enabled", None)
    password = values.pop("smtp_password", "")
    integration = await update_builtin_config(
        "email", values, {"smtp_password": password}, enabled
    )
    await _audit_builtin(request, current_user, integration, values)
    return await get_email_settings(current_user)


@router.get("/webhook", response_model=Response[WebhookSettings])
async def get_webhook_settings(
    current_user: User = Depends(PermissionChecker("admin:integrations:settings:read")),
):
    integration = await get_builtin_integration("webhook")
    return success(
        data=WebhookSettings(
            **{
                **integration.config,
                "webhook_enabled": integration.is_enabled,
                "webhook_headers": {},
                "webhook_secret": "",
            }
        )
    )


@router.put("/webhook", response_model=Response[WebhookSettings])
async def update_webhook_settings(
    request: Request,
    data: WebhookSettings,
    current_user: User = Depends(
        PermissionChecker("admin:integrations:settings:update")
    ),
):
    values = data.model_dump(exclude_unset=True)
    enabled = values.pop("webhook_enabled", None)
    secrets = {"webhook_secret": values.pop("webhook_secret", "")}
    if "webhook_headers" in values:
        headers = values.pop("webhook_headers")
        if headers:
            secrets["webhook_headers"] = json.dumps(headers)
    integration = await update_builtin_config("webhook", values, secrets, enabled)
    await _audit_builtin(request, current_user, integration, values)
    return await get_webhook_settings(current_user)


async def _audit_builtin(request, user, integration, values):
    await AuditLogService.log(
        user=user,
        action="update_site_settings",
        resource_type="integration",
        resource_id=integration.id,
        resource_name=integration.name,
        operation="update",
        status="success",
        request=request,
        changes={"after": values},
    )


@router.post("/email/test", response_model=Response[None])
async def send_test_email(
    data: TestEmailRequest,
    current_user: User = Depends(
        PermissionChecker("admin:integrations:settings:update")
    ),
):
    if not (await get_builtin_integration("email")).is_enabled:
        raise BusinessError(
            code=ResponseCode.EMAIL_SEND_FAILED, msg_key="smtp_not_configured"
        )
    site_name = await SiteSetting.get_value("site_name", "Clouisle")
    result = await send_email(
        data.email,
        t("test_email_subject", site_name=site_name),
        t("test_email_body_text", site_name=site_name),
        t("test_email_body_html", site_name=site_name),
    )
    if not result:
        raise BusinessError(
            code=ResponseCode.EMAIL_SEND_FAILED, msg_key="email_send_failed"
        )
    return success(msg_key="test_email_sent")


@router.post("/webhook/test", response_model=Response[None])
async def send_test_webhook(
    current_user: User = Depends(
        PermissionChecker("admin:integrations:settings:update")
    ),
):
    config = await get_webhook_config()
    if not config["enabled"]:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST, msg_key="webhook_not_enabled"
        )
    if not config["url"]:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST, msg_key="webhook_not_configured"
        )
    site_name = await SiteSetting.get_value("site_name", "Clouisle")
    if not await send_webhook_notification(
        title=t("test_notification_title", site_name=site_name),
        content=t("test_webhook_content"),
    ):
        raise BusinessError(
            code=ResponseCode.INTERNAL_ERROR, msg_key="webhook_send_failed"
        )
    return success(msg_key="test_webhook_sent")
