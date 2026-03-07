from typing import Any, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from pydantic import EmailStr

from app.api import deps
from app.core import security
from app.core.i18n import t
from app.core.password import validate_password
from app.models.user import User
from app.models.site_setting import SiteSetting
from app.models.notification import AutoNotificationType, NotificationLevel
from app.schemas.user import User as UserSchema
from app.schemas.response import (
    Response,
    ResponseCode,
    BusinessError,
    success,
)
from app.services.audit_log import AuditLogService
from app.services.auto_notification import AutoNotificationService
from app.services.password_expiration import PasswordExpirationService

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


@router.get("/me", response_model=Response[UserSchema])
async def read_user_me(
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get current user.
    """
    user = await User.get(id=current_user.id).prefetch_related(
        "roles__permissions", "sso_connections__provider"
    )
    return success(data=await serialize_user_with_sso(user))


class UpdateProfileRequest(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    avatar_url: Optional[str] = None
    locale: Optional[str] = None


@router.put("/me", response_model=Response[UserSchema])
async def update_user_me(
    *,
    request: Request,
    data: UpdateProfileRequest,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Update current user profile.
    """
    update_data = data.model_dump(exclude_unset=True)

    if "username" in update_data and update_data["username"] != current_user.username:
        existing = await User.filter(username=update_data["username"]).first()
        if existing:
            raise BusinessError(
                code=ResponseCode.USERNAME_EXISTS,
                msg_key="user_with_username_exists",
            )

    if "email" in update_data and update_data["email"] != current_user.email:
        existing = await User.filter(email=update_data["email"]).first()
        if existing:
            raise BusinessError(
                code=ResponseCode.EMAIL_EXISTS,
                msg_key="user_with_email_exists",
            )
        update_data["email_verified"] = False

    await current_user.update_from_dict(update_data)
    await current_user.save()

    updated_user = await User.get(id=current_user.id).prefetch_related(
        "roles__permissions"
    )

    await AuditLogService.log(
        user=current_user,
        action="update_user",
        resource_type="user",
        resource_id=current_user.id,
        resource_name=current_user.username,
        operation="update",
        status="success",
        request=request,
        metadata={"fields_updated": list(update_data.keys())},
    )

    return success(
        data=await serialize_user_with_sso(updated_user), msg_key="profile_updated"
    )


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/me/change-password", response_model=Response[None])
async def change_password(
    *,
    request: Request,
    data: ChangePasswordRequest,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Change current user password.
    """
    # Verify current password
    if not security.verify_password(
        data.current_password, current_user.hashed_password
    ):
        raise BusinessError(
            code=ResponseCode.INVALID_CREDENTIALS,
            msg_key="current_password_incorrect",
        )

    # Check minimum password age
    can_change, days_remaining = await PasswordExpirationService.can_change_password(
        current_user
    )
    if not can_change:
        raise BusinessError(
            code=ResponseCode.PASSWORD_MIN_AGE_NOT_MET,
            msg_key="password_min_age_not_met",
            days=days_remaining,
        )

    # Validate new password (including history check)
    is_valid, errors = await validate_password(data.new_password, current_user)
    if not is_valid:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg=", ".join([t(err) for err in errors]),
        )

    # Update password with expiration logic
    new_hashed_password = security.get_password_hash(data.new_password)
    await PasswordExpirationService.update_password_with_expiration(
        current_user, new_hashed_password
    )

    await AuditLogService.log(
        user=current_user,
        action="change_password",
        resource_type="user",
        resource_id=current_user.id,
        resource_name=current_user.username,
        operation="update",
        status="success",
        request=request,
    )

    await AutoNotificationService.send_to_user(
        notification_type=AutoNotificationType.SECURITY_PASSWORD_CHANGED,
        user_id=current_user.id,
        title=t("notify_password_changed_title", lang=current_user.locale),
        content=t("notify_password_changed_content", lang=current_user.locale),
        level=NotificationLevel.HIGH,
    )

    return success(msg_key="password_changed")


class PasswordStatusResponse(BaseModel):
    is_exempt: bool
    password_changed_at: Optional[str] = None
    password_expires_at: Optional[str] = None
    is_expired: bool
    days_until_expiration: Optional[int] = None
    force_change_required: bool


@router.get("/me/password-status", response_model=Response[PasswordStatusResponse])
async def get_password_status(
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get password expiration status for current user.
    """
    is_exempt = await PasswordExpirationService.is_user_exempt(current_user)
    is_expired = await PasswordExpirationService.is_password_expired(current_user)
    days_until_expiration = await PasswordExpirationService.days_until_expiration(
        current_user
    )
    expiration_date = await PasswordExpirationService.calculate_expiration_date(
        current_user
    )

    status = PasswordStatusResponse(
        is_exempt=is_exempt,
        password_changed_at=(
            current_user.password_changed_at.isoformat()
            if current_user.password_changed_at
            else None
        ),
        password_expires_at=expiration_date.isoformat() if expiration_date else None,
        is_expired=is_expired,
        days_until_expiration=days_until_expiration,
        force_change_required=current_user.force_password_change,
    )

    return success(data=status)


class DeleteAccountRequest(BaseModel):
    password: str


@router.delete("/me", response_model=Response[None])
async def delete_account(
    *,
    request: Request,
    data: DeleteAccountRequest,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Delete current user account.
    """
    allow_deletion = await SiteSetting.get_value("allow_account_deletion", True)
    if not allow_deletion:
        raise BusinessError(
            code=ResponseCode.PERMISSION_DENIED,
            msg_key="account_deletion_disabled",
        )

    if current_user.is_superuser:
        raise BusinessError(
            code=ResponseCode.PERMISSION_DENIED,
            msg_key="cannot_delete_superuser_account",
        )

    if not security.verify_password(data.password, current_user.hashed_password):
        raise BusinessError(
            code=ResponseCode.INVALID_CREDENTIALS,
            msg_key="current_password_incorrect",
        )

    await AuditLogService.log(
        user=current_user,
        action="delete_user",
        resource_type="user",
        resource_id=current_user.id,
        resource_name=current_user.username,
        operation="delete",
        status="success",
        request=request,
        metadata={"self_deletion": True},
    )

    await current_user.delete()

    return success(msg_key="account_deleted")
