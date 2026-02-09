import secrets
from datetime import timedelta
from typing import List, Optional
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse

from app.api import deps
from app.api.deps import get_current_active_superuser
from app.core import security
from app.core.i18n import t
from app.core.timezone import now_utc
from app.models.site_setting import SiteSetting
from app.models.sso_provider import SSOProvider
from app.models.sso_session import SSOSession
from app.models.user import User
from app.schemas.response import BusinessError, Response, ResponseCode, success
from app.schemas.sso import (
    SSOProviderAdmin,
    SSOProviderCreate,
    SSOProviderPublic,
    SSOProviderUpdate,
)
from app.services.audit_log import AuditLogService
from app.services.sso import SSOService

router = APIRouter()


# Public endpoints (no auth required)


@router.get("/providers", response_model=Response[List[SSOProviderPublic]])
async def list_public_providers():
    """List enabled SSO providers (public endpoint for login page)"""
    sso_enabled = await SiteSetting.get_value("sso_enabled", False)
    if not sso_enabled:
        return success(data=[])

    providers = await SSOProvider.filter(is_enabled=True).all()
    return success(
        data=[
            SSOProviderPublic(
                id=p.id,
                name=p.name,
                display_name=p.display_name,
                icon_url=p.icon_url,
                button_text=p.button_text,
                protocol=p.protocol,
            )
            for p in providers
        ]
    )


@router.get("/login/{provider_name}")
async def sso_login(
    provider_name: str,
    request: Request,
    redirect: Optional[str] = Query(None),
):
    """Initiate SSO login flow"""
    provider = await SSOProvider.get_or_none(name=provider_name, is_enabled=True)
    if not provider:
        raise BusinessError(
            code=ResponseCode.SSO_PROVIDER_NOT_FOUND, msg_key="sso_provider_not_found"
        )

    # Generate state/session
    session_id = secrets.token_urlsafe(32)
    expires_at = now_utc() + timedelta(minutes=10)

    provider_instance = SSOService.get_provider_instance(provider)

    # Build callback URL - use configured backend URL or request base_url
    # For development, hardcode to avoid proxy issues
    from app.core.config import settings

    backend_url = getattr(settings, "BACKEND_URL", None)
    if backend_url:
        base_url = backend_url.rstrip("/")
    else:
        base_url = str(request.base_url).rstrip("/")
        # If base_url is from frontend proxy, use backend port
        if ":3000" in base_url:
            base_url = base_url.replace(":3000", ":8000")

    callback_url = f"{base_url}/api/v1/sso/callback/{provider.name}"

    try:
        if provider.protocol in ["oauth2", "oidc"]:
            # OIDC returns tuple with code_verifier and nonce
            (
                auth_url,
                code_verifier,
                nonce,
            ) = await provider_instance.get_authorization_url(
                state=session_id, redirect_uri=callback_url
            )

            # Store session
            await SSOSession.create(
                session_id=session_id,
                provider=provider,
                code_verifier=code_verifier,
                nonce=nonce,
                redirect_url=redirect,
                expires_at=expires_at,
            )

        elif provider.protocol == "saml2":
            # SAML returns just the URL
            auth_url = await provider_instance.get_authorization_url(
                state=session_id, redirect_uri=callback_url
            )

            await SSOSession.create(
                session_id=session_id,
                provider=provider,
                redirect_url=redirect,
                expires_at=expires_at,
            )

        elif provider.protocol == "cas":
            # CAS returns just the URL
            auth_url = await provider_instance.get_authorization_url(
                state=session_id, redirect_uri=callback_url
            )

            await SSOSession.create(
                session_id=session_id,
                provider=provider,
                redirect_url=redirect,
                expires_at=expires_at,
            )

        else:
            raise BusinessError(
                code=ResponseCode.SSO_INVALID_CONFIGURATION,
                msg_key="unsupported_protocol",
            )

        return RedirectResponse(url=auth_url)

    except Exception as e:
        raise BusinessError(
            code=ResponseCode.SSO_AUTHENTICATION_FAILED,
            msg_key="sso_login_failed",
            data={"error": str(e)},
        )


@router.get("/callback/{provider_name}")
async def sso_callback(
    provider_name: str,
    request: Request,
    code: Optional[str] = Query(None),  # OAuth2/OIDC
    state: Optional[str] = Query(None),  # OAuth2/OIDC
    ticket: Optional[str] = Query(None),  # CAS
):
    """Handle SSO callback"""
    provider = await SSOProvider.get_or_none(name=provider_name)
    if not provider:
        raise BusinessError(
            code=ResponseCode.SSO_PROVIDER_NOT_FOUND, msg_key="sso_provider_not_found"
        )

    # Determine session_id based on protocol
    if provider.protocol in ["oauth2", "oidc"]:
        session_id = state
    elif provider.protocol == "cas":
        # For CAS, we need to get session from query or use ticket as fallback
        session_id = request.query_params.get("state") or ticket
    else:
        # SAML uses RelayState
        session_id = request.query_params.get("RelayState")

    if not session_id:
        raise BusinessError(
            code=ResponseCode.SSO_SESSION_EXPIRED, msg_key="sso_session_expired"
        )

    # Validate session
    session = await SSOSession.get_or_none(session_id=session_id, provider=provider)
    if not session or session.expires_at < now_utc():
        raise BusinessError(
            code=ResponseCode.SSO_SESSION_EXPIRED, msg_key="sso_session_expired"
        )

    provider_instance = SSOService.get_provider_instance(provider)

    try:
        # Build callback URL - use configured backend URL or request base_url
        from app.core.config import settings

        backend_url = getattr(settings, "BACKEND_URL", None)
        if backend_url:
            base_url = backend_url.rstrip("/")
        else:
            base_url = str(request.base_url).rstrip("/")
            # If base_url is from frontend proxy, use backend port
            if ":3000" in base_url:
                base_url = base_url.replace(":3000", ":8000")

        callback_url = f"{base_url}/api/v1/sso/callback/{provider.name}"

        # Prepare callback data based on protocol
        if provider.protocol in ["oauth2", "oidc"]:
            callback_data = {"code": code}
            user_info = await provider_instance.handle_callback(
                callback_data=callback_data,
                redirect_uri=callback_url,
                code_verifier=session.code_verifier,
            )
        elif provider.protocol == "cas":
            callback_data = {"ticket": ticket}
            user_info = await provider_instance.handle_callback(
                callback_data=callback_data, redirect_uri=callback_url
            )
        elif provider.protocol == "saml2":
            # SAML uses POST, get SAMLResponse from form data
            form_data = await request.form()
            saml_response = form_data.get("SAMLResponse")
            callback_data = {"SAMLResponse": saml_response}
            user_info = await provider_instance.handle_callback(
                callback_data=callback_data, redirect_uri=callback_url
            )
        else:
            raise BusinessError(
                code=ResponseCode.SSO_INVALID_CONFIGURATION,
                msg_key="unsupported_protocol",
            )

        # Extract provider_user_id
        provider_user_id = user_info.get("provider_user_id")
        if not provider_user_id:
            raise BusinessError(
                code=ResponseCode.SSO_AUTHENTICATION_FAILED,
                msg_key="missing_user_id",
            )

        # Map attributes
        mapped_data = provider_instance.map_user_attributes(user_info)
        # Merge with original user_info
        mapped_data.update(user_info)

        # Find or create user
        user, is_new = await SSOService.find_or_create_user(
            provider=provider, provider_user_id=provider_user_id, user_info=mapped_data
        )

        from app.core.config import settings

        frontend_url = settings.FRONTEND_URL.rstrip("/")
        final_redirect = session.redirect_url or "/dashboard"
        if final_redirect.startswith("http"):
            final_redirect = "/dashboard"

        if not user.is_active:
            await session.delete()
            redirect_url = f"{frontend_url}/sso-callback?error=inactive&redirect={quote(final_redirect)}"
            return RedirectResponse(url=redirect_url)

        # Update last login
        user.last_login = now_utc()
        await user.save()

        # Generate JWT token
        session_timeout_days = await SiteSetting.get_value("session_timeout_days", 7)
        access_token_expires = timedelta(days=session_timeout_days)
        access_token = security.create_access_token(
            user.id, expires_delta=access_token_expires
        )

        # Store session if single session mode is enabled
        single_session = await SiteSetting.get_value("single_session", False)
        if single_session:
            from app.core.redis import set_user_session

            expires_in_seconds = int(access_token_expires.total_seconds())
            await set_user_session(str(user.id), access_token, expires_in_seconds)

        # Audit log
        await AuditLogService.log(
            user=user,
            action="sso_login_success",
            resource_type="user",
            resource_id=str(user.id),
            resource_name=user.username,
            operation="read",
            status="success",
            request=request,
            metadata={
                "provider": provider.name,
                "is_new_user": is_new,
            },
        )

        # Clean up session
        await session.delete()

        # Redirect to SSO callback page, which will handle token storage
        # and then redirect to the final destination
        redirect_url = f"{frontend_url}/sso-callback?token={access_token}&redirect={quote(final_redirect)}"

        return RedirectResponse(url=redirect_url)

    except BusinessError:
        raise
    except Exception as e:
        await AuditLogService.log(
            user=None,
            action="sso_login_failed",
            resource_type="user",
            resource_id=None,
            resource_name=None,
            operation="read",
            status="failed",
            request=request,
            error_message=str(e),
            metadata={"provider": provider.name},
        )
        raise BusinessError(
            code=ResponseCode.SSO_AUTHENTICATION_FAILED,
            msg_key="sso_login_failed",
            data={"error": str(e)},
        )


@router.delete("/connections/{connection_id}", response_model=Response[None])
async def disconnect_sso(
    connection_id: UUID,
    request: Request,
    current_user: User = Depends(deps.get_current_active_user),
):
    """Disconnect SSO connection (user can disconnect their own connections)"""
    from app.models.user_sso_connection import UserSSOConnection

    # Get the connection
    connection = await UserSSOConnection.get_or_none(
        id=connection_id, user=current_user
    ).prefetch_related("provider")

    if not connection:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND, msg_key="sso_connection_not_found"
        )

    # Check if user has a password (can't disconnect if SSO is the only auth method)
    if not current_user.hashed_password or current_user.hashed_password == "":
        # Check if this is the only SSO connection
        connection_count = await UserSSOConnection.filter(user=current_user).count()
        if connection_count <= 1:
            raise BusinessError(
                code=ResponseCode.FORBIDDEN,
                msg_key="cannot_disconnect_only_auth_method",
            )

    provider_name = connection.provider.name

    # Delete the connection
    await connection.delete()

    # Audit log
    await AuditLogService.log(
        user=current_user,
        action="disconnect_sso",
        resource_type="sso_connection",
        resource_id=str(connection_id),
        resource_name=provider_name,
        operation="delete",
        status="success",
        request=request,
        metadata={"provider": provider_name},
    )

    return success()


@router.delete("/admin/connections/{connection_id}", response_model=Response[None])
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


# Admin endpoints (require superuser)


@router.get("/admin/providers", response_model=Response[List[SSOProviderAdmin]])
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


@router.post("/admin/providers", response_model=Response[SSOProviderAdmin])
async def create_provider(
    request: Request,
    data: SSOProviderCreate,
    current_user: User = Depends(get_current_active_superuser),
):
    """Create SSO provider (admin)"""
    # Check if name already exists
    existing = await SSOProvider.filter(name=data.name).first()
    if existing:
        raise BusinessError(
            code=ResponseCode.SSO_PROVIDER_NAME_EXISTS,
            msg_key="sso_provider_name_exists",
        )

    # Create provider
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


@router.put("/admin/providers/{provider_id}", response_model=Response[SSOProviderAdmin])
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

    # Check name uniqueness if changing name
    if data.name and data.name != provider.name:
        existing = await SSOProvider.filter(name=data.name).first()
        if existing:
            raise BusinessError(
                code=ResponseCode.SSO_PROVIDER_NAME_EXISTS,
                msg_key="sso_provider_name_exists",
            )

    # Update fields
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


@router.delete("/admin/providers/{provider_id}", response_model=Response[None])
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


@router.post("/admin/providers/{provider_id}/test", response_model=Response[dict])
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

        # Basic validation - check if we can create authorization URL
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
                "authorization_url": auth_url[:100] + "...",  # Truncate for display
            }
        )

    except Exception as e:
        return success(
            data={
                "status": "error",
                "message": t("sso_provider_config_error", error=str(e)),
            }
        )
