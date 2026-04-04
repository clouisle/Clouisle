import secrets
from datetime import timedelta
from typing import Optional
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse

from app.api import deps
from app.core import security
from app.core.timezone import now_utc
from app.models.site_setting import SiteSetting
from app.models.sso_provider import SSOProvider
from app.models.sso_session import SSOSession
from app.models.user import User
from app.schemas.response import BusinessError, Response, ResponseCode, success
from app.schemas.sso import SSOProviderPublic
from app.services.audit_log import AuditLogService
from app.services.sso import SSOService

router = APIRouter()


# Public endpoints (no auth required)


@router.get("/providers", response_model=Response[list[SSOProviderPublic]])
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

    session_id = secrets.token_urlsafe(32)
    expires_at = now_utc() + timedelta(minutes=10)

    provider_instance = SSOService.get_provider_instance(provider)

    # Build callback URL - use site_url or configured backend URL
    from app.core.config import settings

    site_url = await SiteSetting.get_value("site_url", "")
    backend_url = getattr(settings, "BACKEND_URL", None)
    if site_url:
        base_url = site_url.rstrip("/")
    elif backend_url:
        base_url = backend_url.rstrip("/")
    else:
        base_url = str(request.base_url).rstrip("/")
        if ":3000" in base_url:
            base_url = base_url.replace(":3000", ":8000")

    callback_url = f"{base_url}/api/v1/sso/callback/{provider.name}"

    try:
        if provider.protocol in ["oauth2", "oidc"]:
            auth_result = await provider_instance.get_authorization_url(
                state=session_id, redirect_uri=callback_url
            )
            if not isinstance(auth_result, tuple) or len(auth_result) != 3:
                raise BusinessError(
                    code=ResponseCode.SSO_INVALID_CONFIGURATION,
                    msg_key="unsupported_protocol",
                )
            auth_url, code_verifier, nonce = auth_result

            await SSOSession.create(
                session_id=session_id,
                provider=provider,
                code_verifier=code_verifier,
                nonce=nonce,
                redirect_url=redirect,
                expires_at=expires_at,
            )

        elif provider.protocol == "saml2":
            auth_result = await provider_instance.get_authorization_url(
                state=session_id, redirect_uri=callback_url
            )
            auth_url = auth_result if isinstance(auth_result, str) else auth_result[0]

            await SSOSession.create(
                session_id=session_id,
                provider=provider,
                redirect_url=redirect,
                expires_at=expires_at,
            )

        elif provider.protocol == "cas":
            auth_result = await provider_instance.get_authorization_url(
                state=session_id, redirect_uri=callback_url
            )
            auth_url = auth_result if isinstance(auth_result, str) else auth_result[0]

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
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    ticket: Optional[str] = Query(None),
):
    """Handle SSO callback"""
    provider = await SSOProvider.get_or_none(name=provider_name)
    if not provider:
        raise BusinessError(
            code=ResponseCode.SSO_PROVIDER_NOT_FOUND, msg_key="sso_provider_not_found"
        )

    if provider.protocol in ["oauth2", "oidc"]:
        session_id = state
    elif provider.protocol == "cas":
        session_id = request.query_params.get("state") or ticket
    else:
        session_id = request.query_params.get("RelayState")

    if not session_id:
        raise BusinessError(
            code=ResponseCode.SSO_SESSION_EXPIRED, msg_key="sso_session_expired"
        )

    session = await SSOSession.get_or_none(session_id=session_id, provider=provider)
    if not session or session.expires_at < now_utc():
        raise BusinessError(
            code=ResponseCode.SSO_SESSION_EXPIRED, msg_key="sso_session_expired"
        )

    provider_instance = SSOService.get_provider_instance(provider)

    try:
        # Build callback URL - use site_url or configured backend URL
        from app.core.config import settings

        site_url = await SiteSetting.get_value("site_url", "")
        backend_url = getattr(settings, "BACKEND_URL", None)
        if site_url:
            base_url = site_url.rstrip("/")
        elif backend_url:
            base_url = backend_url.rstrip("/")
        else:
            base_url = str(request.base_url).rstrip("/")
            if ":3000" in base_url:
                base_url = base_url.replace(":3000", ":8000")

        callback_url = f"{base_url}/api/v1/sso/callback/{provider.name}"

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
            form_data = await request.form()
            saml_value = form_data.get("SAMLResponse")
            saml_response = saml_value if isinstance(saml_value, str) else None
            callback_data = {"SAMLResponse": saml_response}
            user_info = await provider_instance.handle_callback(
                callback_data=callback_data, redirect_uri=callback_url
            )
        else:
            raise BusinessError(
                code=ResponseCode.SSO_INVALID_CONFIGURATION,
                msg_key="unsupported_protocol",
            )

        provider_user_id = user_info.get("provider_user_id")
        if not provider_user_id:
            raise BusinessError(
                code=ResponseCode.SSO_AUTHENTICATION_FAILED,
                msg_key="missing_user_id",
            )

        mapped_data = provider_instance.map_user_attributes(user_info)
        mapped_data.update(user_info)

        user, is_new = await SSOService.find_or_create_user(
            provider=provider, provider_user_id=provider_user_id, user_info=mapped_data
        )

        from app.core.config import settings

        # Use public site_url for browser redirect, fall back to FRONTEND_URL
        site_url = await SiteSetting.get_value("site_url", "")
        frontend_url = (site_url or settings.FRONTEND_URL).rstrip("/")
        final_redirect = session.redirect_url or "/dashboard"
        if final_redirect.startswith("http"):
            final_redirect = "/dashboard"

        if not user.is_active:
            await session.delete()
            redirect_url = f"{frontend_url}/sso-callback?error=inactive&redirect={quote(final_redirect)}"
            return RedirectResponse(url=redirect_url)

        user.last_login = now_utc()
        await user.save()

        session_timeout_days = await SiteSetting.get_value("session_timeout_days", 7)
        access_token_expires = timedelta(days=session_timeout_days)
        access_token = security.create_access_token(
            user.id, expires_delta=access_token_expires
        )

        single_session = await SiteSetting.get_value("single_session", False)
        if single_session:
            from app.core.redis import set_user_session

            expires_in_seconds = int(access_token_expires.total_seconds())
            await set_user_session(str(user.id), access_token, expires_in_seconds)

        await AuditLogService.log(
            user=user,
            action="sso_login_success",
            resource_type="user",
            resource_id=user.id,
            resource_name=user.username,
            operation="read",
            status="success",
            request=request,
            metadata={
                "provider": provider.name,
                "is_new_user": is_new,
            },
        )

        await session.delete()

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

    connection = await UserSSOConnection.get_or_none(
        id=connection_id, user=current_user
    ).prefetch_related("provider")

    if not connection:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND, msg_key="sso_connection_not_found"
        )

    if not current_user.hashed_password or current_user.hashed_password == "":
        connection_count = await UserSSOConnection.filter(user=current_user).count()
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
        resource_id=connection_id,
        resource_name=provider_name,
        operation="delete",
        status="success",
        request=request,
        metadata={"provider": provider_name},
    )

    return success()
