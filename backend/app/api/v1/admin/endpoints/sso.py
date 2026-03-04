"""
Admin-only SSO management endpoints.
Public endpoints (providers list, login, callback, user disconnect) remain in the platform router.
"""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.api.deps import get_current_active_superuser
from app.core.i18n import t
from app.models.sso_provider import SSOProvider
from app.models.user import User
from app.schemas.response import BusinessError, Response, ResponseCode, success
from app.schemas.sso import (
    SSOProviderAdmin,
    SSOProviderCreate,
    SSOProviderUpdate,
)
from app.services.audit_log import AuditLogService
from app.services.sso import SSOService

router = APIRouter()


@router.delete("/connections/{connection_id}", response_model=Response[None])
async def admin_disconnect_sso(
    connection_id: UUID,
    request: Request,
    current_user: User = Depends(get_current_active_superuser),
):
    """Disconnect SSO connection (admin can disconnect any user's connections)"""
    from app.models.user_sso_connection import UserSSOConnection

    connection = await UserSSOConnection.get_or_none(id=connection_id).prefetch_related(
        "provider", "user"
    )

    if not connection:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="sso_connection_not_found",
        )

    target_user = connection.user

    if not target_user.hashed_password or target_user.hashed_password == "":
        connection_count = await UserSSOConnection.filter(user=target_user).count()
        if connection_count <= 1:
            raise BusinessError(
                code=ResponseCode.FORBIDDEN,
                msg_key="cannot_disconnect_only_auth_method",
            )

    provider_name = connection.provider.name

    await connection.delete()

    await AuditLogService.log(
        user=current_user,
        action="disconnect_sso",
        resource_type="sso_connection",
        resource_id=str(connection_id),
        resource_name=provider_name,
        operation="delete",
        status="success",
        request=request,
        metadata={"provider": provider_name, "target_user_id": str(target_user.id)},
    )

    return success()


@router.get("/providers", response_model=Response[List[SSOProviderAdmin]])
async def list_providers_admin(
    current_user: User = Depends(get_current_active_superuser),
):
    """List all SSO providers (admin)"""
    providers = await SSOProvider.all()
    return success(
        data=[
            SSOProviderAdmin(
                id=p.id,
                name=p.name,
                protocol=p.protocol,
                display_name=p.display_name,
                icon_url=p.icon_url,
                button_text=p.button_text,
                config=p.config,
                attribute_mapping=p.attribute_mapping,
                is_enabled=p.is_enabled,
                allow_signup=p.allow_signup,
                require_approval=p.require_approval,
                default_role_id=p.default_role_id,
                created_at=p.created_at,
                updated_at=p.updated_at,
            )
            for p in providers
        ]
    )


@router.post("/providers", response_model=Response[SSOProviderAdmin])
async def create_provider(
    request: Request,
    data: SSOProviderCreate,
    current_user: User = Depends(get_current_active_superuser),
):
    """Create SSO provider (admin)"""
    existing = await SSOProvider.filter(name=data.name).first()
    if existing:
        raise BusinessError(
            code=ResponseCode.SSO_PROVIDER_NAME_EXISTS,
            msg_key="sso_provider_name_exists",
        )

    provider = await SSOProvider.create(**data.model_dump(), created_by=current_user)

    await AuditLogService.log(
        user=current_user,
        action="create_sso_provider",
        resource_type="sso_provider",
        resource_id=str(provider.id),
        resource_name=provider.name,
        operation="create",
        status="success",
        request=request,
    )

    return success(data=SSOProviderAdmin.model_validate(provider))


@router.put("/providers/{provider_id}", response_model=Response[SSOProviderAdmin])
async def update_provider(
    provider_id: UUID,
    request: Request,
    data: SSOProviderUpdate,
    current_user: User = Depends(get_current_active_superuser),
):
    """Update SSO provider (admin)"""
    provider = await SSOProvider.get_or_none(id=provider_id)
    if not provider:
        raise BusinessError(
            code=ResponseCode.SSO_PROVIDER_NOT_FOUND, msg_key="sso_provider_not_found"
        )

    if data.name and data.name != provider.name:
        existing = await SSOProvider.filter(name=data.name).first()
        if existing:
            raise BusinessError(
                code=ResponseCode.SSO_PROVIDER_NAME_EXISTS,
                msg_key="sso_provider_name_exists",
            )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(provider, field, value)

    await provider.save()

    await AuditLogService.log(
        user=current_user,
        action="update_sso_provider",
        resource_type="sso_provider",
        resource_id=str(provider.id),
        resource_name=provider.name,
        operation="update",
        status="success",
        request=request,
    )

    return success(data=SSOProviderAdmin.model_validate(provider))


@router.delete("/providers/{provider_id}", response_model=Response[None])
async def delete_provider(
    provider_id: UUID,
    request: Request,
    current_user: User = Depends(get_current_active_superuser),
):
    """Delete SSO provider (admin)"""
    provider = await SSOProvider.get_or_none(id=provider_id)
    if not provider:
        raise BusinessError(
            code=ResponseCode.SSO_PROVIDER_NOT_FOUND, msg_key="sso_provider_not_found"
        )

    provider_name = provider.name
    await provider.delete()

    await AuditLogService.log(
        user=current_user,
        action="delete_sso_provider",
        resource_type="sso_provider",
        resource_id=str(provider_id),
        resource_name=provider_name,
        operation="delete",
        status="success",
        request=request,
    )

    return success()


@router.post("/providers/{provider_id}/test", response_model=Response[dict])
async def test_provider_connection(
    provider_id: UUID,
    current_user: User = Depends(get_current_active_superuser),
):
    """Test SSO provider connection (admin)"""
    provider = await SSOProvider.get_or_none(id=provider_id)
    if not provider:
        raise BusinessError(
            code=ResponseCode.SSO_PROVIDER_NOT_FOUND, msg_key="sso_provider_not_found"
        )

    try:
        provider_instance = SSOService.get_provider_instance(provider)

        test_state = "test_state"
        test_redirect = "http://localhost/callback"

        if provider.protocol in ["oauth2", "oidc"]:
            auth_url, _, _ = await provider_instance.get_authorization_url(
                state=test_state, redirect_uri=test_redirect
            )
        else:
            auth_url = await provider_instance.get_authorization_url(
                state=test_state, redirect_uri=test_redirect
            )

        return success(
            data={
                "status": "success",
                "message": t("sso_provider_config_valid"),
                "authorization_url": auth_url[:100] + "...",
            }
        )

    except Exception as e:
        return success(
            data={
                "status": "error",
                "message": t("sso_provider_config_error", error=str(e)),
            }
        )
