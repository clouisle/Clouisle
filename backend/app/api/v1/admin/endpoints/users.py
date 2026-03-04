from typing import Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, BackgroundTasks, Request
from pydantic import BaseModel
from tortoise.expressions import Q

from app.api import deps
from app.core import security
from app.core.i18n import t
from app.core.email import (
    send_email,
    check_bulk_email_rate,
    increment_bulk_email_count,
    check_recipient_email_rate,
    increment_recipient_email_count,
)
from app.models.user import User, Role
from app.models.site_setting import SiteSetting
from app.models.notification import AutoNotificationType
from app.schemas.user import User as UserSchema, UserCreate, UserUpdate
from app.schemas.response import (
    Response,
    PageData,
    ResponseCode,
    BusinessError,
    success,
)
from app.services.audit_log import AuditLogService
from app.services.auto_notification import AutoNotificationService

router = APIRouter()


async def serialize_user_with_sso(user: User) -> dict:
    from app.schemas.sso import UserSSOConnectionSchema

    if hasattr(user, "_fetched_relations") and "roles" in user._fetched_relations:
        roles = user.roles
    else:
        roles = await user.roles.all().prefetch_related("permissions")

    if (
        hasattr(user, "_fetched_relations")
        and "sso_connections" in user._fetched_relations
    ):
        sso_connections = user.sso_connections
    else:
        sso_connections = await user.sso_connections.all().prefetch_related("provider")

    user_dict = {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "is_active": user.is_active,
        "is_superuser": user.is_superuser,
        "email_verified": user.email_verified,
        "avatar_url": user.avatar_url,
        "locale": getattr(user, "locale", "en"),
        "created_at": user.created_at,
        "last_login": user.last_login,
        "auth_source": user.auth_source,
        "external_id": user.external_id,
        "roles": [
            {
                "id": role.id,
                "name": role.name,
                "description": role.description,
                "is_system_role": role.is_system_role,
                "permissions": [
                    {
                        "id": perm.id,
                        "scope": perm.scope,
                        "code": perm.code,
                        "description": perm.description,
                    }
                    for perm in role.permissions
                ],
            }
            for role in roles
        ],
        "sso_connections": [],
    }

    for conn in sso_connections:
        user_dict["sso_connections"].append(
            UserSSOConnectionSchema(
                id=conn.id,
                provider_id=conn.provider.id,
                provider_name=conn.provider.name,
                provider_display_name=conn.provider.display_name,
                provider_icon_url=conn.provider.icon_url,
                provider_user_id=conn.provider_user_id,
                provider_username=conn.provider_username,
                provider_email=conn.provider_email,
                first_login=conn.first_login,
                last_login=conn.last_login,
            ).model_dump()
        )

    return user_dict


@router.get("", response_model=Response[PageData[UserSchema]])
async def read_users(
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = Query(
        None, description="Filter by status: active, inactive, pending"
    ),
    search: Optional[str] = Query(None, description="Search by username or email"),
    current_user: User = Depends(deps.PermissionChecker("user:read")),
) -> Any:
    skip = (page - 1) * page_size
    query = User.all()

    if status == "active":
        query = query.filter(is_active=True)
    elif status == "inactive":
        query = query.filter(is_active=False)
    elif status == "pending":
        query = query.filter(is_active=False)

    if search:
        query = query.filter(Q(username__icontains=search) | Q(email__icontains=search))

    total = await query.count()
    users = (
        await query.offset(skip)
        .limit(page_size)
        .prefetch_related("roles__permissions", "sso_connections__provider")
    )

    users_data = []
    for user in users:
        users_data.append(await serialize_user_with_sso(user))
    return success(
        data={
            "items": users_data,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/stats", response_model=Response[dict])
async def get_user_stats(
    current_user: User = Depends(deps.PermissionChecker("user:read")),
) -> Any:
    total = await User.all().count()
    active = await User.filter(is_active=True).count()
    inactive = await User.filter(is_active=False).count()
    pending = await User.filter(is_active=False).count()

    return success(
        data={
            "total": total,
            "active": active,
            "inactive": inactive,
            "pending": pending,
        }
    )


@router.post("", response_model=Response[UserSchema])
async def create_user(
    *,
    request: Request,
    user_in: UserCreate,
    current_user: User = Depends(deps.PermissionChecker("user:create")),
) -> Any:
    existing_user = await User.filter(username=user_in.username).first()
    if existing_user:
        raise BusinessError(
            code=ResponseCode.USERNAME_EXISTS,
            msg_key="user_with_username_exists",
        )

    existing_email = await User.filter(email=user_in.email).first()
    if existing_email:
        raise BusinessError(
            code=ResponseCode.EMAIL_EXISTS,
            msg_key="user_with_email_exists",
        )

    user_dict = user_in.model_dump(exclude_unset=True)
    password = user_dict.pop("password")
    hashed_password = security.get_password_hash(password)

    if "locale" not in user_dict or not user_dict.get("locale"):
        default_language = await SiteSetting.get_value("default_language", "en")
        user_dict["locale"] = default_language

    user = await User.create(
        **user_dict,
        hashed_password=hashed_password,
    )
    user = await User.get(id=user.id).prefetch_related("roles__permissions")

    await AuditLogService.log(
        user=current_user,
        action="create_user",
        resource_type="user",
        resource_id=user.id,
        resource_name=user.username,
        operation="create",
        status="success",
        request=request,
    )

    return success(data=await serialize_user_with_sso(user), msg_key="user_created")


class SendEmailRequest(BaseModel):
    subject: str
    content: str
    user_ids: List[UUID]


@router.post("/send-email", response_model=Response[dict])
async def send_email_to_users(
    *,
    data: SendEmailRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(deps.PermissionChecker("user:update")),
) -> Any:
    smtp_enabled = await SiteSetting.get_value("smtp_enabled", False)
    if not smtp_enabled:
        raise BusinessError(
            code=ResponseCode.EMAIL_SEND_FAILED,
            msg_key="smtp_not_configured",
        )

    can_send, sent_count_hour, remaining = await check_bulk_email_rate(
        str(current_user.id), max_per_hour=100
    )
    if not can_send:
        raise BusinessError(
            code=ResponseCode.RATE_LIMITED,
            msg_key="email_rate_limit_exceeded",
            data={"limit": 100, "period": "hour"},
        )

    users = await User.filter(id__in=data.user_ids).all()
    if not users:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="user_not_found",
        )

    if len(users) > remaining:
        raise BusinessError(
            code=ResponseCode.RATE_LIMITED,
            msg_key="email_quota_insufficient",
            data={"requested": len(users), "remaining": remaining},
        )

    sent_count = 0
    skipped_count = 0

    for user in users:
        if not user.email:
            continue

        can_receive, _ = await check_recipient_email_rate(user.email, max_per_day=5)
        if not can_receive:
            skipped_count += 1
            continue

        background_tasks.add_task(
            send_email,
            to_email=user.email,
            subject=data.subject,
            body_text=data.content,
            body_html=f"""
            <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto;">
                <p>Hi {user.username},</p>
                <div style="margin: 20px 0; white-space: pre-wrap;">{data.content}</div>
            </div>
            """,
        )

        await increment_recipient_email_count(user.email)
        sent_count += 1

    if sent_count > 0:
        await increment_bulk_email_count(str(current_user.id), sent_count)

    return success(
        data={
            "sent_count": sent_count,
            "skipped_count": skipped_count,
            "total": len(users),
        },
        msg_key="email_queued",
    )


@router.get("/{user_id}", response_model=Response[UserSchema])
async def read_user_by_id(
    user_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("user:read")),
) -> Any:
    user = await User.filter(id=user_id).prefetch_related("roles__permissions").first()
    if not user:
        raise BusinessError(
            code=ResponseCode.USER_NOT_FOUND,
            msg_key="user_with_id_not_exists",
            status_code=404,
        )
    return success(data=await serialize_user_with_sso(user))


@router.post("/{user_id}/activate", response_model=Response[UserSchema])
async def activate_user(
    request: Request,
    user_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("user:update")),
) -> Any:
    user = await User.filter(id=user_id).first()
    if not user:
        raise BusinessError(
            code=ResponseCode.USER_NOT_FOUND,
            msg_key="user_with_id_not_exists",
            status_code=404,
        )

    if user.is_active:
        raise BusinessError(
            code=ResponseCode.USER_ALREADY_ACTIVE,
            msg_key="user_already_active",
        )

    user.is_active = True
    await user.save()

    updated_user = await User.get(id=user_id).prefetch_related("roles__permissions")

    await AuditLogService.log(
        user=current_user,
        action="activate_user",
        resource_type="user",
        resource_id=user.id,
        resource_name=user.username,
        operation="update",
        status="success",
        request=request,
    )

    await AutoNotificationService.send_to_user(
        notification_type=AutoNotificationType.USER_ACTIVATED,
        user_id=user.id,
        title=t("notify_user_activated_title", lang=user.locale),
        content=t("notify_user_activated_content", lang=user.locale),
    )

    return success(
        data=await serialize_user_with_sso(updated_user), msg_key="user_activated"
    )


@router.post("/{user_id}/deactivate", response_model=Response[UserSchema])
async def deactivate_user(
    request: Request,
    user_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("user:update")),
) -> Any:
    user = await User.filter(id=user_id).first()
    if not user:
        raise BusinessError(
            code=ResponseCode.USER_NOT_FOUND,
            msg_key="user_with_id_not_exists",
            status_code=404,
        )

    if user.is_superuser:
        raise BusinessError(
            code=ResponseCode.CANNOT_DEACTIVATE_SUPERUSER,
            msg_key="cannot_deactivate_superuser",
        )

    if not user.is_active:
        raise BusinessError(
            code=ResponseCode.USER_ALREADY_INACTIVE,
            msg_key="user_already_inactive",
        )

    user.is_active = False
    await user.save()

    updated_user = await User.get(id=user_id).prefetch_related("roles__permissions")

    await AuditLogService.log(
        user=current_user,
        action="deactivate_user",
        resource_type="user",
        resource_id=user.id,
        resource_name=user.username,
        operation="update",
        status="success",
        request=request,
    )

    await AutoNotificationService.send_to_user(
        notification_type=AutoNotificationType.USER_DEACTIVATED,
        user_id=user.id,
        title=t("notify_user_deactivated_title", lang=user.locale),
        content=t("notify_user_deactivated_content", lang=user.locale),
    )

    return success(
        data=await serialize_user_with_sso(updated_user), msg_key="user_deactivated"
    )


@router.put("/{user_id}", response_model=Response[UserSchema])
async def update_user(
    *,
    request: Request,
    user_id: UUID,
    user_in: UserUpdate,
    current_user: User = Depends(deps.PermissionChecker("user:update")),
) -> Any:
    user = await User.filter(id=user_id).first()
    if not user:
        raise BusinessError(
            code=ResponseCode.USER_NOT_FOUND,
            msg_key="user_with_id_not_exists",
            status_code=404,
        )

    user_data = user_in.model_dump(exclude_unset=True)

    password_changed = False
    if "password" in user_data:
        password = user_data.pop("password")
        user_data["hashed_password"] = security.get_password_hash(password)
        password_changed = True

    if "roles" in user_data:
        role_names = user_data.pop("roles")
        roles = []
        for role_name in role_names:
            role = await Role.filter(name=role_name).first()
            if role:
                roles.append(role)
        await user.roles.clear()
        await user.roles.add(*roles)

    await user.update_from_dict(user_data)
    await user.save()

    updated_user = await User.get(id=user_id).prefetch_related("roles__permissions")

    await AuditLogService.log(
        user=current_user,
        action="update_user",
        resource_type="user",
        resource_id=user.id,
        resource_name=user.username,
        operation="update",
        status="success",
        request=request,
        metadata={
            "fields_updated": list(user_in.model_dump(exclude_unset=True).keys())
        },
    )

    if password_changed:
        await AutoNotificationService.send_to_user(
            notification_type=AutoNotificationType.USER_PASSWORD_RESET,
            user_id=user.id,
            title=t("notify_user_password_reset_title", lang=user.locale),
            content=t("notify_user_password_reset_content", lang=user.locale),
        )

    return success(
        data=await serialize_user_with_sso(updated_user), msg_key="user_updated"
    )


@router.delete("/{user_id}", response_model=Response[UserSchema])
async def delete_user(
    request: Request,
    user_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("user:delete")),
) -> Any:
    user = await User.filter(id=user_id).prefetch_related("roles__permissions").first()
    if not user:
        raise BusinessError(
            code=ResponseCode.USER_NOT_FOUND,
            msg_key="user_with_id_not_exists",
            status_code=404,
        )

    if user.is_superuser:
        raise BusinessError(
            code=ResponseCode.CANNOT_DELETE_SUPERUSER,
            msg_key="cannot_delete_superuser",
        )

    await AuditLogService.log(
        user=current_user,
        action="delete_user",
        resource_type="user",
        resource_id=user.id,
        resource_name=user.username,
        operation="delete",
        status="success",
        request=request,
    )

    await user.delete()
    return success(data=await serialize_user_with_sso(user), msg_key="user_deleted")
