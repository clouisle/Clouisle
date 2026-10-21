"""Administrator API for Feishu directory configuration and manual sync."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from tortoise.expressions import Q

from app.api.deps import PermissionChecker
from app.integrations.feishu import (
    FeishuAPIError,
    FeishuClient,
)
from app.integrations.credentials import IntegrationSecretError
from app.models import User
from app.services.integration_config import (
    get_builtin_integration,
    update_builtin_config,
)
from app.schemas.response import BusinessError, Response, ResponseCode, success
from app.services.audit_log import AuditLogService
from app.services.feishu_directory import sync_department_teams, sync_directory_users
from app.services.feishu_agent_events import (
    CONNECTION_MODE_KEY,
    FeishuConnectionMode,
    get_connection_mode,
)
from app.services.integration_receiver_state import receiver_status

router = APIRouter()
logger = logging.getLogger(__name__)
FEISHU_COMPANY_DEPARTMENT_ID = "0"


class FeishuConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    app_id: str = Field(min_length=1, max_length=255)
    app_secret: str | None = Field(default=None, max_length=4096)


class FeishuDepartmentScopeUpdate(BaseModel):
    department_ids: list[str] = Field(min_length=1, max_length=500)


class FeishuTestMessageRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=2000)


class FeishuAgentChatConfigUpdate(BaseModel):
    """Agent-chat channel settings; secrets are input-only and may be blank."""

    model_config = ConfigDict(extra="forbid")

    connection_mode: FeishuConnectionMode | None = None
    event_verification_token: str | None = Field(default=None, max_length=255)
    event_encrypt_key: str | None = Field(default=None, max_length=255)

    @field_validator("event_verification_token", "event_encrypt_key")
    @classmethod
    def normalize_secret(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if stripped and len(stripped) < 8:
            raise ValueError("feishu_agent_chat_secret_too_short")
        return stripped or None


async def _configured_client() -> FeishuClient:
    """Client for directory operations, or an actionable administrator error."""
    integration = await get_builtin_integration("feishu")
    app_id = integration.config.get("app_id", "")
    encrypted_secret = integration.credentials.get("app_secret", "")
    if not app_id or not encrypted_secret:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST, msg_key="feishu_not_configured"
        )
    if (
        not integration.is_enabled
        or "directory_sync" not in integration.enabled_capabilities
    ):
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST, msg_key="feishu_directory_sync_disabled"
        )
    return _new_client(app_id, encrypted_secret)


async def _configured_auth_client() -> FeishuClient:
    integration = await get_builtin_integration("feishu")
    app_id = integration.config.get("app_id", "")
    app_secret = integration.credentials.get("app_secret", "")
    if not app_id or not app_secret:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST, msg_key="feishu_not_configured"
        )
    return _new_client(app_id, app_secret)


async def _configured_notification_client() -> FeishuClient:
    integration = await get_builtin_integration("feishu")
    app_id = integration.config.get("app_id", "")
    encrypted_secret = integration.credentials.get("app_secret", "")
    if not app_id or not encrypted_secret:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="feishu_notification_not_configured",
        )
    if (
        not integration.is_enabled
        or "notification" not in integration.enabled_capabilities
    ):
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST, msg_key="feishu_notification_not_enabled"
        )
    return _new_client(app_id, encrypted_secret)


@router.post("/connection-check", response_model=Response[dict[str, str]])
async def check_connection(
    current_user: User = Depends(
        PermissionChecker("admin:integrations:settings:update")
    ),
):
    try:
        client = await _configured_auth_client()
        await client.check_connection()
    except BusinessError:
        raise
    except Exception as exc:
        raise _feishu_failure(exc, "Feishu connection check") from exc
    return success(data={"status": "ok"})


@router.get("/test-recipients", response_model=Response[list[dict[str, str]]])
async def list_test_recipients(
    search: str = "",
    current_user: User = Depends(PermissionChecker("admin:integrations:settings:read")),
):
    from app.models.feishu_user import FeishuUser

    integration = await get_builtin_integration("feishu")
    if (
        not integration.is_enabled
        or "notification" not in integration.enabled_capabilities
    ):
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST, msg_key="feishu_notification_not_enabled"
        )
    query = FeishuUser.filter(user__is_active=True).select_related("user")
    if search.strip():
        term = search.strip()
        query = query.filter(
            Q(user__username__icontains=term) | Q(user__email__icontains=term)
        )
    bindings = await query.order_by("user__username").limit(20)
    return success(
        data=[
            {
                "id": str(item.user_id),
                "username": item.user.username,
                "email": item.user.email,
            }
            for item in bindings
        ]
    )


@router.post("/test-message", response_model=Response[dict[str, str]])
async def send_test_message(
    data: FeishuTestMessageRequest,
    current_user: User = Depends(
        PermissionChecker("admin:integrations:settings:update")
    ),
):
    from app.models.feishu_user import FeishuUser

    binding = await FeishuUser.filter(
        user_id=data.user_id, user__is_active=True
    ).first()
    if not binding:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST, msg_key="feishu_test_recipient_unavailable"
        )
    client = await _configured_notification_client()
    try:
        await client.send_user_message(
            binding.feishu_user_id, data.title.strip(), data.content.strip()
        )
    except Exception as exc:
        raise _feishu_failure(exc, "Feishu test message") from exc
    return success(data={"status": "sent"})


def _new_client(app_id: str, encrypted_secret: str) -> FeishuClient:
    return FeishuClient(app_id, encrypted_secret)


def _feishu_failure(exc: Exception, context: str) -> BusinessError:
    """Map a failed Feishu call to an administrator-visible error (never the app secret).

    `BAD_REQUEST` is used because the frontend renders backend messages for this code;
    validation errors are reserved for field-level form validation and are not toasted.
    """
    if isinstance(exc, FeishuAPIError):
        logger.warning(
            "%s rejected by Feishu: %s | response=%s", context, exc, exc.detail
        )
        return BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="feishu_api_error",
            error=str(exc),
        )
    if isinstance(exc, IntegrationSecretError):
        logger.error("%s failed: %s", context, exc)
        return BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="feishu_secret_undecryptable",
        )
    logger.exception("%s failed", context)
    return BusinessError(code=ResponseCode.UNKNOWN_ERROR, msg_key="internal_error")


def _flatten_department_ids(departments) -> set[str]:
    result: set[str] = set()
    pending = list(departments)
    while pending:
        department = pending.pop()
        result.add(department.department_id)
        pending.extend(department.children)
    return result


@router.get("/config", response_model=Response[dict[str, Any]])
async def get_config(
    current_user: User = Depends(PermissionChecker("admin:integrations:settings:read")),
):
    integration = await get_builtin_integration("feishu")
    return success(
        data={
            "app_id": integration.config.get("app_id", ""),
            "app_secret_configured": bool(integration.credentials.get("app_secret")),
            "department_ids": integration.config.get("department_ids", []),
            "is_enabled": integration.is_enabled,
        }
    )


@router.put("/config", response_model=Response[dict[str, Any]])
async def update_config(
    request: Request,
    data: FeishuConfigUpdate,
    current_user: User = Depends(
        PermissionChecker("admin:integrations:settings:update")
    ),
):
    app_id = data.app_id.strip()
    if not app_id:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR, msg_key="validation_error"
        )
    integration = await update_builtin_config(
        "feishu",
        {"app_id": app_id},
        {"app_secret": data.app_secret.strip()}
        if data.app_secret and data.app_secret.strip()
        else None,
    )
    configured = bool(integration.credentials.get("app_secret"))
    await AuditLogService.log(
        user=current_user,
        action="update_feishu_integration_config",
        resource_type="integration",
        resource_id=integration.id,
        resource_name="feishu_integration",
        operation="update",
        status="success",
        request=request,
        changes={"after": {"app_id": app_id, "app_secret_configured": configured}},
    )
    return success(
        data={
            "app_id": app_id,
            "app_secret_configured": configured,
            "is_enabled": integration.is_enabled,
            "department_ids": integration.config.get("department_ids", []),
        }
    )


@router.get("/agent-chat/config", response_model=Response[dict[str, Any]])
async def get_agent_chat_config(
    current_user: User = Depends(PermissionChecker("admin:integrations:settings:read")),
):
    """Agent-chat channel state; secrets are reported as configured flags only."""
    integration = await get_builtin_integration("feishu")
    credentials = integration.credentials
    return success(
        data={
            "connection_mode": get_connection_mode(integration),
            "event_verification_token_configured": bool(
                credentials.get("event_verification_token")
            ),
            "event_encrypt_key_configured": bool(credentials.get("event_encrypt_key")),
            "is_enabled": integration.is_enabled,
            "capability_enabled": "agent_chat" in integration.enabled_capabilities,
            "receiver_status": await receiver_status(integration),
        }
    )


@router.put("/agent-chat/config", response_model=Response[dict[str, Any]])
async def update_agent_chat_config(
    request: Request,
    data: FeishuAgentChatConfigUpdate,
    current_user: User = Depends(
        PermissionChecker("admin:integrations:settings:update")
    ),
):
    """Store transport mode and callback secrets; users own Agent selection."""
    secret_values = {
        key: value
        for key, value in {
            "event_verification_token": data.event_verification_token,
            "event_encrypt_key": data.event_encrypt_key,
        }.items()
        if value
    }
    config_values: dict[str, Any] = {}
    if data.connection_mode is not None:
        config_values[CONNECTION_MODE_KEY] = data.connection_mode
    updated = await update_builtin_config(
        "feishu",
        config_values,
        secret_values or None,
    )
    await AuditLogService.log(
        user=current_user,
        action="update_feishu_agent_chat_config",
        resource_type="integration",
        resource_id=updated.id,
        resource_name="feishu_agent_chat",
        operation="update",
        status="success",
        request=request,
        changes={
            "after": {
                "connection_mode": get_connection_mode(updated),
                "event_verification_token_configured": bool(
                    updated.credentials.get("event_verification_token")
                ),
                "event_encrypt_key_configured": bool(
                    updated.credentials.get("event_encrypt_key")
                ),
            }
        },
    )
    return success(
        data={
            "connection_mode": get_connection_mode(updated),
            "event_verification_token_configured": bool(
                updated.credentials.get("event_verification_token")
            ),
            "event_encrypt_key_configured": bool(
                updated.credentials.get("event_encrypt_key")
            ),
            "is_enabled": updated.is_enabled,
            "capability_enabled": "agent_chat" in updated.enabled_capabilities,
            "receiver_status": await receiver_status(updated),
        }
    )


@router.get("/departments", response_model=Response[list[dict[str, Any]]])
async def list_departments(
    current_user: User = Depends(PermissionChecker("admin:integrations:settings:read")),
):
    try:
        departments = await (await _configured_client()).list_departments()
    except BusinessError:
        raise
    except Exception as exc:
        raise _feishu_failure(exc, "Feishu department listing") from exc
    return success(data=[department.as_dict() for department in departments])


@router.put("/department-scope", response_model=Response[dict[str, list[str]]])
async def update_department_scope(
    request: Request,
    data: FeishuDepartmentScopeUpdate,
    current_user: User = Depends(
        PermissionChecker("admin:integrations:settings:update")
    ),
):
    client = await _configured_client()
    try:
        departments = await client.list_departments()
    except Exception as exc:
        raise _feishu_failure(exc, "Feishu department scope validation") from exc
    department_ids = list(
        dict.fromkeys(value.strip() for value in data.department_ids if value.strip())
    )
    selectable_ids = _flatten_department_ids(departments) | {
        FEISHU_COMPANY_DEPARTMENT_ID
    }
    if not department_ids or not set(department_ids).issubset(selectable_ids):
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR, msg_key="validation_error"
        )
    integration = await update_builtin_config(
        "feishu", {"department_ids": department_ids}
    )
    await AuditLogService.log(
        user=current_user,
        action="update_feishu_department_scope",
        resource_type="integration",
        resource_id=integration.id,
        resource_name="feishu_department_scope",
        operation="update",
        status="success",
        request=request,
        changes={"after": {"department_ids": department_ids}},
    )
    return success(data={"department_ids": department_ids})


@router.post("/sync", response_model=Response[dict[str, int]])
async def sync_contacts(
    request: Request,
    current_user: User = Depends(
        PermissionChecker("admin:integrations:settings:update")
    ),
):
    department_ids = (await get_builtin_integration("feishu")).config.get(
        "department_ids", []
    )
    if not isinstance(department_ids, list) or not department_ids:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR, msg_key="validation_error"
        )
    try:
        client = await _configured_client()
        departments = await client.list_departments()
        selected_ids = set(department_ids)

        def select_departments(nodes):
            selected = []
            for department in nodes:
                if (
                    department.department_id in selected_ids
                    or FEISHU_COMPANY_DEPARTMENT_ID in selected_ids
                ):
                    selected.append(department)
                selected.extend(select_departments(department.children))
            return selected

        selected_departments = (
            [
                departments[0],
                *select_departments(departments[0].children),
            ]
            if departments
            else []
        )
        user_department_ids = list(
            dict.fromkeys(
                (
                    [FEISHU_COMPANY_DEPARTMENT_ID]
                    if FEISHU_COMPANY_DEPARTMENT_ID in selected_ids
                    else []
                )
                + [department.department_id for department in selected_departments]
            )
        )
        members = await client.list_users(user_department_ids)
        result = await sync_directory_users(
            members, actor=current_user, request=request
        )
        teams_created = await sync_department_teams(selected_departments, members)
    except BusinessError:
        raise
    except Exception as exc:
        raise _feishu_failure(exc, "Feishu directory synchronization") from exc
    return success(
        data={
            "created": result.created,
            "updated": result.updated,
            "skipped": result.skipped,
            "teams_created": teams_created,
        }
    )
