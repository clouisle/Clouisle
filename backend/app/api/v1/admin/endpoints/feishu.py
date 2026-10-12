"""Administrator API for Feishu directory configuration and manual sync."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.api.deps import PermissionChecker
from app.integrations.feishu import (
    FeishuAPIError,
    FeishuClient,
    FeishuSecretError,
    encrypt_app_secret,
)
from app.models import SiteSetting, User
from app.schemas.response import BusinessError, Response, ResponseCode, success
from app.services.audit_log import AuditLogService
from app.services.feishu_directory import sync_department_teams, sync_directory_users

router = APIRouter()
logger = logging.getLogger(__name__)
FEISHU_COMPANY_DEPARTMENT_ID = "0"
APP_ID_KEY = "feishu_app_id"
APP_SECRET_KEY = "feishu_app_secret_encrypted"
DEPARTMENT_SCOPE_KEY = "feishu_department_scope"


class FeishuConfigUpdate(BaseModel):
    app_id: str = Field(min_length=1, max_length=255)
    app_secret: str | None = Field(default=None, max_length=4096)


class FeishuDepartmentScopeUpdate(BaseModel):
    department_ids: list[str] = Field(min_length=1, max_length=500)


def _new_client(app_id: str, encrypted_secret: str) -> FeishuClient:
    return FeishuClient(app_id, encrypted_secret)


async def _configured_client() -> FeishuClient:
    app_id = await SiteSetting.get_value(APP_ID_KEY, "")
    encrypted_secret = await SiteSetting.get_value(APP_SECRET_KEY, "")
    if not app_id or not encrypted_secret:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR, msg_key="validation_error"
        )
    return _new_client(app_id, encrypted_secret)


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
    if isinstance(exc, FeishuSecretError):
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
    current_user: User = Depends(PermissionChecker("admin:settings:read")),
):
    return success(
        data={
            "app_id": await SiteSetting.get_value(APP_ID_KEY, ""),
            "app_secret_configured": bool(
                await SiteSetting.get_value(APP_SECRET_KEY, "")
            ),
            "department_ids": await SiteSetting.get_value(DEPARTMENT_SCOPE_KEY, []),
        }
    )


@router.put("/config", response_model=Response[dict[str, Any]])
async def update_config(
    request: Request,
    data: FeishuConfigUpdate,
    current_user: User = Depends(PermissionChecker("admin:settings:update")),
):
    app_id = data.app_id.strip()
    if not app_id:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR, msg_key="validation_error"
        )
    await SiteSetting.set_value(
        APP_ID_KEY, app_id, category="integration", is_public=False
    )
    if data.app_secret and data.app_secret.strip():
        encrypted_secret = encrypt_app_secret(data.app_secret.strip())
        await SiteSetting.set_value(
            APP_SECRET_KEY, encrypted_secret, category="integration", is_public=False
        )
    configured = bool(await SiteSetting.get_value(APP_SECRET_KEY, ""))
    await AuditLogService.log(
        user=current_user,
        action="update_feishu_integration_config",
        resource_type="site_setting",
        resource_id=None,
        resource_name="feishu_integration",
        operation="update",
        status="success",
        request=request,
        changes={"after": {"app_id": app_id, "app_secret_configured": configured}},
    )
    return success(data={"app_id": app_id, "app_secret_configured": configured})


@router.get("/departments", response_model=Response[list[dict[str, Any]]])
async def list_departments(
    current_user: User = Depends(PermissionChecker("admin:settings:read")),
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
    current_user: User = Depends(PermissionChecker("admin:settings:update")),
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
    await SiteSetting.set_value(
        DEPARTMENT_SCOPE_KEY,
        department_ids,
        value_type="json",
        category="integration",
        is_public=False,
    )
    await AuditLogService.log(
        user=current_user,
        action="update_feishu_department_scope",
        resource_type="site_setting",
        resource_id=None,
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
    current_user: User = Depends(PermissionChecker("admin:settings:update")),
):
    department_ids = await SiteSetting.get_value(DEPARTMENT_SCOPE_KEY, [])
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
