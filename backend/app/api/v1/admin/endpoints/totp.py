"""
Admin TOTP (Two-Factor Authentication) endpoints
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.api import deps
from app.models.user import User
from app.schemas.response import Response, ResponseCode, BusinessError, success
from app.services.audit_log import AuditLogService

router = APIRouter()


class TOTPStatsResponse(BaseModel):
    total_users: int
    totp_enabled: int
    adoption_rate: float


class TOTPUserStatusResponse(BaseModel):
    enabled: bool
    enabled_at: str | None


@router.get("/stats", response_model=Response[TOTPStatsResponse])
async def get_totp_stats(
    current_user: User = Depends(deps.PermissionChecker("admin:dashboard:access")),
) -> Any:
    """
    Get TOTP 2FA statistics (admin only)
    """
    total_users = await User.filter(is_active=True).count()
    totp_enabled = await User.filter(is_active=True, totp_enabled=True).count()

    adoption_rate = (totp_enabled / total_users * 100) if total_users > 0 else 0.0

    return success(
        data=TOTPStatsResponse(
            total_users=total_users,
            totp_enabled=totp_enabled,
            adoption_rate=round(adoption_rate, 2),
        )
    )


@router.post("/users/{user_id}/disable", response_model=Response[None])
async def admin_disable_user_totp(
    request: Request,
    user_id: UUID,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Force disable user's TOTP 2FA (admin only, for emergency access)
    """
    user = await User.get_or_none(id=user_id)
    if not user:
        raise BusinessError(
            code=ResponseCode.USER_NOT_FOUND,
            msg_key="user_not_found",
        )

    if not user.totp_enabled:
        raise BusinessError(
            code=ResponseCode.TOTP_NOT_ENABLED,
            msg_key="totp_not_enabled",
        )

    # Disable TOTP
    user.totp_enabled = False  # type: ignore[assignment]
    user.totp_secret = None  # type: ignore[assignment]
    user.totp_enabled_at = None  # type: ignore[assignment]
    user.totp_backup_codes_hash = None  # type: ignore[assignment]
    await user.save()

    # Log audit
    await AuditLogService.log(
        user=current_user,
        action="admin_disable_totp",
        resource_type="user",
        resource_id=user.id,
        resource_name=user.username,
        operation="update",
        status="success",
        request=request,
        metadata={"target_user_id": str(user.id), "target_username": user.username},
    )

    return success(msg_key="totp_disabled")


@router.get("/users/{user_id}/status", response_model=Response[TOTPUserStatusResponse])
async def get_user_totp_status(
    user_id: UUID,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Get user's TOTP 2FA status (admin only)
    """
    user = await User.get_or_none(id=user_id)
    if not user:
        raise BusinessError(
            code=ResponseCode.USER_NOT_FOUND,
            msg_key="user_not_found",
        )

    return success(
        data=TOTPUserStatusResponse(
            enabled=user.totp_enabled,
            enabled_at=user.totp_enabled_at.isoformat()
            if user.totp_enabled_at
            else None,
        )
    )
