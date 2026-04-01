"""
TOTP (Two-Factor Authentication) endpoints for platform users
"""

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.api import deps
from app.core.security import verify_password
from app.core.timezone import now_utc
from app.models.user import User
from app.schemas.response import Response, ResponseCode, BusinessError, success
from app.services import totp as totp_service
from app.services.audit_log import AuditLogService

router = APIRouter()


class TOTPSetupResponse(BaseModel):
    secret: str
    qr_code: str
    backup_codes: list[str]


class TOTPStatusResponse(BaseModel):
    enabled: bool
    enabled_at: str | None
    remaining_backup_codes: int


class TOTPEnableRequest(BaseModel):
    code: str


class TOTPDisableRequest(BaseModel):
    password: str
    code: str
    is_backup_code: bool = False


class TOTPRegenerateRequest(BaseModel):
    code: str


@router.post("/setup", response_model=Response[TOTPSetupResponse])
async def setup_totp(
    request: Request,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Generate TOTP secret and QR code for setup
    Does not enable 2FA yet - user must verify code first
    """
    if current_user.totp_enabled:
        raise BusinessError(
            code=ResponseCode.TOTP_ALREADY_ENABLED,
            msg_key="totp_already_enabled",
        )

    # Generate new secret
    secret = totp_service.generate_totp_secret()

    # Generate QR code
    qr_code = totp_service.generate_qr_code(
        secret=secret,
        username=current_user.email,
        issuer="Clouisle",
    )

    # Generate backup codes
    backup_codes = totp_service.generate_backup_codes(count=10)
    hashed_codes = totp_service.hash_backup_codes(backup_codes)

    # Store encrypted secret and hashed backup codes temporarily
    encrypted_secret = totp_service.encrypt_secret(secret)
    current_user.totp_secret = encrypted_secret  # type: ignore[assignment]
    current_user.totp_backup_codes_hash = hashed_codes  # type: ignore[assignment]
    await current_user.save()

    return success(
        data=TOTPSetupResponse(
            secret=secret,
            qr_code=qr_code,
            backup_codes=backup_codes,
        )
    )


@router.post("/enable", response_model=Response[None])
async def enable_totp(
    request: Request,
    data: TOTPEnableRequest,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Enable TOTP 2FA by verifying the code
    """
    if current_user.totp_enabled:
        raise BusinessError(
            code=ResponseCode.TOTP_ALREADY_ENABLED,
            msg_key="totp_already_enabled",
        )

    if not current_user.totp_secret:
        raise BusinessError(
            code=ResponseCode.TOTP_SETUP_EXPIRED,
            msg_key="totp_setup_expired",
        )

    # Decrypt secret
    secret = totp_service.decrypt_secret(current_user.totp_secret)

    # Verify code
    if not totp_service.verify_totp_code(secret, data.code):
        raise BusinessError(
            code=ResponseCode.TOTP_INVALID,
            msg_key="totp_invalid",
        )

    # Enable TOTP
    current_user.totp_enabled = True  # type: ignore[assignment]
    current_user.totp_enabled_at = now_utc()  # type: ignore[assignment]
    await current_user.save()

    # Log audit
    await AuditLogService.log(
        user=current_user,
        action="enable_totp",
        resource_type="user",
        resource_id=current_user.id,
        resource_name=current_user.username,
        operation="update",
        status="success",
        request=request,
    )

    return success(msg_key="totp_enabled")


@router.post("/disable", response_model=Response[None])
async def disable_totp(
    request: Request,
    data: TOTPDisableRequest,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Disable TOTP 2FA (requires password + current TOTP code)
    """
    if not current_user.totp_enabled:
        raise BusinessError(
            code=ResponseCode.TOTP_NOT_ENABLED,
            msg_key="totp_not_enabled",
        )

    # Verify password
    if not verify_password(data.password, current_user.hashed_password):
        raise BusinessError(
            code=ResponseCode.INVALID_CREDENTIALS,
            msg_key="current_password_incorrect",
        )

    # Decrypt secret
    if not current_user.totp_secret:
        raise BusinessError(
            code=ResponseCode.TOTP_NOT_ENABLED,
            msg_key="totp_not_enabled",
        )
    secret = totp_service.decrypt_secret(current_user.totp_secret)

    # Verify TOTP code or backup code
    is_valid = False
    if data.is_backup_code:
        # Verify backup code
        is_valid, remaining_codes = totp_service.verify_backup_code(current_user, data.code)
        if is_valid:
            # Note: backup codes will be deleted when TOTP is disabled below
            pass
    else:
        # Verify TOTP code
        is_valid = totp_service.verify_totp_code(secret, data.code)

    if not is_valid:
        raise BusinessError(
            code=ResponseCode.TOTP_INVALID,
            msg_key="totp_invalid",
        )

    # Disable TOTP
    current_user.totp_enabled = False  # type: ignore[assignment]
    current_user.totp_secret = None  # type: ignore[assignment]
    current_user.totp_enabled_at = None  # type: ignore[assignment]
    current_user.totp_backup_codes_hash = None  # type: ignore[assignment]
    await current_user.save()

    # Log audit
    await AuditLogService.log(
        user=current_user,
        action="disable_totp",
        resource_type="user",
        resource_id=current_user.id,
        resource_name=current_user.username,
        operation="update",
        status="success",
        request=request,
    )

    return success(msg_key="totp_disabled")


@router.post("/regenerate-backup-codes", response_model=Response[dict[str, Any]])
async def regenerate_backup_codes(
    request: Request,
    data: TOTPRegenerateRequest,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Regenerate backup codes (requires TOTP code verification)
    """
    if not current_user.totp_enabled:
        raise BusinessError(
            code=ResponseCode.TOTP_NOT_ENABLED,
            msg_key="totp_not_enabled",
        )

    # Decrypt secret
    if not current_user.totp_secret:
        raise BusinessError(
            code=ResponseCode.TOTP_NOT_ENABLED,
            msg_key="totp_not_enabled",
        )
    secret = totp_service.decrypt_secret(current_user.totp_secret)

    # Verify TOTP code
    if not totp_service.verify_totp_code(secret, data.code):
        raise BusinessError(
            code=ResponseCode.TOTP_INVALID,
            msg_key="totp_invalid",
        )

    # Generate new backup codes
    backup_codes = totp_service.generate_backup_codes(count=10)
    hashed_codes = totp_service.hash_backup_codes(backup_codes)

    # Save hashed codes
    current_user.totp_backup_codes_hash = hashed_codes  # type: ignore[assignment]
    await current_user.save()

    # Log audit
    await AuditLogService.log(
        user=current_user,
        action="regenerate_backup_codes",
        resource_type="user",
        resource_id=current_user.id,
        resource_name=current_user.username,
        operation="update",
        status="success",
        request=request,
    )

    return success(
        data={"codes": backup_codes},
        msg_key="backup_codes_regenerated",
    )


@router.get("/status", response_model=Response[TOTPStatusResponse])
async def get_totp_status(
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get user's TOTP 2FA status
    """
    remaining_codes = await totp_service.get_remaining_backup_codes(current_user)

    return success(
        data=TOTPStatusResponse(
            enabled=current_user.totp_enabled,
            enabled_at=current_user.totp_enabled_at.isoformat()
            if current_user.totp_enabled_at
            else None,
            remaining_backup_codes=remaining_codes,
        )
    )
