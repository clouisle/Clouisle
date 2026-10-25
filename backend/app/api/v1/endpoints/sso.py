import logging
import secrets
from datetime import timedelta
from typing import Optional
from urllib.parse import quote, urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from app.api import deps
from app.core import security
from app.core.timezone import now_utc
from app.models.site_setting import SiteSetting
from app.models.integration import Integration
from app.models.sso_session import SSOSession
from app.models.user import User
from app.models.user_sso_connection import UserSSOConnection
from app.integrations.feishu import FeishuAPIError
from app.models.feishu_user import FeishuUser
from app.schemas.response import BusinessError, Response, ResponseCode, success
from app.schemas.integration import IntegrationLoginPublic
from app.integrations.registry import IntegrationCapability, integration_registry
from app.services.audit_log import AuditLogService
from app.services.sso import PKCE_PROVIDER_TYPES, SSOService

logger = logging.getLogger(__name__)

router = APIRouter()


def _supports_login(integration: Integration) -> bool:
    try:
        definition = integration_registry.get(integration.provider_type)
    except ValueError:
        return False
    return (
        IntegrationCapability.USER_LOGIN in definition.capabilities
        and IntegrationCapability.USER_LOGIN in integration.enabled_capabilities
    )


async def _frontend_url() -> str:
    from app.core.config import settings

    site_url = await SiteSetting.get_value("site_url", "")
    return (site_url or settings.FRONTEND_URL).rstrip("/")


def _backend_url(request: Request) -> str:
    from app.core.config import settings

    backend_url = getattr(settings, "BACKEND_URL", None)
    if backend_url:
        return backend_url.rstrip("/")

    base_url = str(request.base_url).rstrip("/")
    if ":3000" in base_url:
        return base_url.replace(":3000", ":8000")
    return base_url


def _safe_sso_redirect(redirect_url: Optional[str]) -> str:
    """Sanitized post-login path; every role lands on the same default."""
    final_redirect = redirect_url.strip() if isinstance(redirect_url, str) else ""
    parsed = urlsplit(final_redirect)
    if (
        not final_redirect
        or not final_redirect.startswith("/")
        or final_redirect.startswith("//")
        or parsed.scheme
        or parsed.netloc
        or "\\" in final_redirect
    ):
        return "/app"
    return final_redirect


async def _sso_error_redirect(
    error_code: str, redirect_url: Optional[str] = None
) -> RedirectResponse:
    frontend_url = await _frontend_url()
    return RedirectResponse(
        url=f"{frontend_url}/sso-callback?error={quote(error_code)}&redirect={quote(_safe_sso_redirect(redirect_url))}"
    )


# Public endpoints (no auth required)


@router.get("/integrations", response_model=Response[list[IntegrationLoginPublic]])
async def list_public_integrations():
    """List enabled login integrations without configuration or credentials."""
    sso_enabled = await SiteSetting.get_value("sso_enabled", False)
    if not sso_enabled:
        return success(data=[])

    providers = await Integration.filter(is_enabled=True).all()
    return success(
        data=[
            IntegrationLoginPublic(
                id=p.id,
                name=p.name,
                display_name=p.display_name,
                icon_url=p.icon_url,
                button_text=p.button_text,
                provider_type=p.provider_type,
            )
            for p in providers
            if _supports_login(p)
        ]
    )


@router.get("/login/{provider_name}")
async def sso_login(
    provider_name: str,
    request: Request,
    redirect: Optional[str] = Query(None),
):
    """Initiate SSO login flow"""
    provider = await Integration.get_or_none(name=provider_name, is_enabled=True)
    if not provider or not _supports_login(provider):
        return await _sso_error_redirect("sso_provider_not_found")

    session_id = secrets.token_urlsafe(32)
    expires_at = now_utc() + timedelta(minutes=10)
    safe_redirect = _safe_sso_redirect(redirect)

    try:
        provider_instance = SSOService.get_provider_instance(provider)

        # Build callback URL from backend/API origin for IdP redirects.
        callback_url = f"{_backend_url(request)}/api/v1/sso/callback/{provider.name}"

        if provider.provider_type in PKCE_PROVIDER_TYPES:
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
                integration=provider,
                code_verifier=code_verifier,
                nonce=nonce,
                redirect_url=safe_redirect,
                expires_at=expires_at,
            )

        elif provider.provider_type == "saml2":
            auth_result = await provider_instance.get_authorization_url(
                state=session_id, redirect_uri=callback_url
            )
            auth_url = auth_result if isinstance(auth_result, str) else auth_result[0]

            await SSOSession.create(
                session_id=session_id,
                integration=provider,
                redirect_url=safe_redirect,
                expires_at=expires_at,
            )

        elif provider.provider_type == "cas":
            auth_result = await provider_instance.get_authorization_url(
                state=session_id, redirect_uri=callback_url
            )
            auth_url = auth_result if isinstance(auth_result, str) else auth_result[0]

            await SSOSession.create(
                session_id=session_id,
                integration=provider,
                redirect_url=safe_redirect,
                expires_at=expires_at,
            )

        else:
            raise BusinessError(
                code=ResponseCode.SSO_INVALID_CONFIGURATION,
                msg_key="unsupported_protocol",
            )

        return RedirectResponse(url=auth_url)

    except Exception:
        logger.exception(
            "Failed to initialize SSO login for provider %s", provider_name
        )
        return await _sso_error_redirect("sso_login_failed")


@router.get("/callback/{provider_name}")
async def sso_callback(
    provider_name: str,
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    ticket: Optional[str] = Query(None),
):
    """Handle SSO callback"""
    provider = await Integration.get_or_none(name=provider_name)
    if not provider:
        return await _sso_error_redirect("sso_provider_not_found")
    if not _supports_login(provider):
        if provider.provider_type == "feishu" and isinstance(state, str) and state:
            pending = await SSOSession.get_or_none(
                session_id=state, integration=provider
            )
            if pending and getattr(pending, "link_user_id", None) is not None:
                return RedirectResponse(
                    url=f"{await _frontend_url()}/sso-link-callback?error=sso_provider_not_found",
                    status_code=303,
                )
        return await _sso_error_redirect("sso_provider_not_found")

    if provider.provider_type in PKCE_PROVIDER_TYPES:
        session_id = state
    elif provider.provider_type == "cas":
        session_id = request.query_params.get("state") or ticket
    else:
        session_id = request.query_params.get("RelayState")

    if not session_id:
        return await _sso_error_redirect("sso_session_expired")

    session = await SSOSession.get_or_none(session_id=session_id, integration=provider)
    if not session:
        return await _sso_error_redirect("sso_session_expired")
    linking = getattr(session, "link_user_id", None) is not None
    if session.expires_at < now_utc():
        if linking:
            return RedirectResponse(
                url=f"{await _frontend_url()}/sso-link-callback?error=sso_session_expired",
                status_code=303,
            )
        return await _sso_error_redirect("sso_session_expired", session.redirect_url)

    if linking and (
        not provider.is_enabled
        or provider.provider_type != "feishu"
        or session.link_user_info is not None
        or not await SiteSetting.get_value("sso_enabled", False)
    ):
        return RedirectResponse(
            url=f"{await _frontend_url()}/sso-link-callback?error=sso_session_expired",
            status_code=303,
        )

    try:
        provider_instance = SSOService.get_provider_instance(provider)

        # Build callback URL from backend/API origin for IdP redirects.
        callback_url = f"{_backend_url(request)}/api/v1/sso/callback/{provider.name}"

        if provider.provider_type in PKCE_PROVIDER_TYPES:
            callback_data = {"code": code}
            user_info = await provider_instance.handle_callback(
                callback_data=callback_data,
                redirect_uri=callback_url,
                code_verifier=session.code_verifier,
            )
        elif provider.provider_type == "cas":
            callback_data = {"ticket": ticket}
            user_info = await provider_instance.handle_callback(
                callback_data=callback_data, redirect_uri=callback_url
            )
        elif provider.provider_type == "saml2":
            form_data = await request.form()
            saml_value = form_data.get("SAMLResponse")
            saml_response = saml_value if isinstance(saml_value, str) else None
            callback_data = {"SAMLResponse": saml_response}
            user_info = await provider_instance.handle_callback(
                callback_data=callback_data, redirect_uri=callback_url
            )
        else:
            return await _sso_error_redirect("sso_login_failed", session.redirect_url)

        provider_user_id = user_info.get("provider_user_id")
        if not isinstance(provider_user_id, str) or not provider_user_id:
            if not linking:
                return await _sso_error_redirect(
                    "sso_login_failed", session.redirect_url
                )
            raise BusinessError(
                code=ResponseCode.SSO_AUTHENTICATION_FAILED,
                msg_key="sso_login_failed",
            )

        mapped_data = provider_instance.map_user_attributes(user_info)
        mapped_data.update(user_info)
        if linking:
            staged = await SSOSession.filter(
                id=session.id,
                link_user_id=session.link_user_id,
                link_user_info__isnull=True,
                expires_at__gt=now_utc(),
            ).update(link_user_info=mapped_data, code_verifier=None)
            if staged != 1:
                raise BusinessError(
                    code=ResponseCode.SSO_SESSION_EXPIRED,
                    msg_key="sso_session_expired",
                )
            return RedirectResponse(
                url=f"{await _frontend_url()}/sso-link-callback?session_id={quote(session.session_id)}",
                status_code=303,
            )

        user, is_new = await SSOService.find_or_create_user(
            provider=provider, provider_user_id=provider_user_id, user_info=mapped_data
        )

        # Use public site_url for browser redirect, fall back to FRONTEND_URL
        frontend_url = await _frontend_url()
        final_redirect = _safe_sso_redirect(session.redirect_url)

        if not user.is_active:
            await session.delete()
            error_code = (
                "pending_approval"
                if getattr(user, "approval_status", "approved") == "pending"
                else "inactive"
            )
            redirect_url = f"{frontend_url}/sso-callback?error={error_code}&redirect={quote(final_redirect)}"
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

    except BusinessError as e:
        if linking:
            await session.delete()
            return RedirectResponse(
                url=f"{await _frontend_url()}/sso-link-callback?error=sso_login_failed",
                status_code=303,
            )
        await AuditLogService.log(
            user=None,
            action="sso_login_failed",
            resource_type="user",
            resource_id=None,
            resource_name=None,
            operation="read",
            status="failed",
            request=request,
            error_message=e.msg_key,
            metadata={"provider": provider.name},
        )
        return await _sso_error_redirect("sso_login_failed", session.redirect_url)
    except Exception:
        if linking:
            logger.exception("Feishu account-link authorization failed")
            await session.delete()
            return RedirectResponse(
                url=f"{await _frontend_url()}/sso-link-callback?error=sso_login_failed",
                status_code=303,
            )
        await AuditLogService.log(
            user=None,
            action="sso_login_failed",
            resource_type="user",
            resource_id=None,
            resource_name=None,
            operation="read",
            status="failed",
            request=request,
            error_message="sso_login_failed",
            metadata={"provider": provider.name},
        )
        return await _sso_error_redirect("sso_login_failed", session.redirect_url)


class SSOAccountLinkRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=255)


@router.get(
    "/links/integrations", response_model=Response[list[IntegrationLoginPublic]]
)
async def list_linkable_integrations(
    current_user: User = Depends(deps.get_current_active_user),
):
    """Return enabled Feishu sign-in integrations not yet linked by this user."""
    if not await SiteSetting.get_value("sso_enabled", False):
        return success(data=[])

    providers = await Integration.filter(is_enabled=True, provider_type="feishu").all()
    linked_ids = set(
        await UserSSOConnection.filter(user=current_user).values_list(
            "integration_id", flat=True
        )
    )
    return success(
        data=[
            IntegrationLoginPublic(
                id=provider.id,
                name=provider.name,
                display_name=provider.display_name,
                icon_url=provider.icon_url,
                button_text=provider.button_text,
                provider_type=provider.provider_type,
            )
            for provider in providers
            if _supports_login(provider) and provider.id not in linked_ids
        ]
    )


@router.post("/links", response_model=Response[dict[str, str]])
async def start_account_link(
    request: Request,
    provider_name: str = Query(..., min_length=1, max_length=100),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Start linking a Feishu identity to the authenticated account."""
    provider = await Integration.get_or_none(
        name=provider_name, is_enabled=True, provider_type="feishu"
    )
    if (
        not provider
        or not _supports_login(provider)
        or not await SiteSetting.get_value("sso_enabled", False)
    ):
        raise BusinessError(
            code=ResponseCode.SSO_PROVIDER_NOT_FOUND,
            msg_key="sso_provider_not_found",
        )
    if await UserSSOConnection.filter(user=current_user, integration=provider).exists():
        raise BusinessError(
            code=ResponseCode.ALREADY_EXISTS, msg_key="sso_connection_exists"
        )

    state = secrets.token_urlsafe(32)
    callback_url = f"{_backend_url(request)}/api/v1/sso/callback/{provider.name}"
    try:
        authorization = await SSOService.get_provider_instance(
            provider
        ).get_authorization_url(state=state, redirect_uri=callback_url)
    except (FeishuAPIError, ValueError) as exc:
        logger.warning("Failed to initialize Feishu account link: %s", exc)
        raise BusinessError(
            code=ResponseCode.SSO_INVALID_CONFIGURATION,
            msg_key="sso_invalid_configuration",
        ) from exc
    if not isinstance(authorization, tuple) or len(authorization) != 3:
        raise BusinessError(
            code=ResponseCode.SSO_INVALID_CONFIGURATION,
            msg_key="sso_invalid_configuration",
        )
    auth_url, code_verifier, _nonce = authorization
    if not isinstance(auth_url, str):
        raise BusinessError(
            code=ResponseCode.SSO_INVALID_CONFIGURATION,
            msg_key="sso_invalid_configuration",
        )

    await SSOSession.create(
        session_id=state,
        integration=provider,
        link_user=current_user,
        code_verifier=code_verifier,
        redirect_url="/app",
        expires_at=now_utc() + timedelta(minutes=10),
    )
    await AuditLogService.log(
        user=current_user,
        action="start_sso_link",
        resource_type="integration",
        resource_id=provider.id,
        resource_name=provider.name,
        operation="create",
        status="success",
        request=request,
    )
    return success(data={"authorization_url": auth_url, "session_id": state})


@router.post("/links/complete", response_model=Response[None])
async def complete_account_link(
    data: SSOAccountLinkRequest,
    request: Request,
    current_user: User = Depends(deps.get_current_active_user),
):
    """Finalize the pending provider identity for the authenticated owner."""
    try:
        if not await SiteSetting.get_value("sso_enabled", False):
            raise BusinessError(
                code=ResponseCode.SSO_PROVIDER_NOT_FOUND,
                msg_key="sso_provider_not_found",
            )
        async with in_transaction() as db:
            # Serialize this actor's pending links without changing their account.
            actor = (
                await User.filter(id=current_user.id, is_active=True)
                .using_db(db)
                .select_for_update()
                .first()
            )
            if actor is None:
                raise BusinessError(
                    code=ResponseCode.INACTIVE_USER, msg_key="inactive_user"
                )
            session = (
                await SSOSession.filter(
                    session_id=data.session_id,
                    link_user_id=current_user.id,
                    link_user_info__isnull=False,
                )
                .using_db(db)
                .select_for_update()
                .prefetch_related("integration")
                .first()
            )
            if (
                session is None
                or session.expires_at < now_utc()
                or not session.integration.is_enabled
                or not _supports_login(session.integration)
                or session.integration.provider_type != "feishu"
            ):
                raise BusinessError(
                    code=ResponseCode.SSO_SESSION_EXPIRED,
                    msg_key="sso_session_expired",
                )

            identity = session.link_user_info
            if not isinstance(identity, dict):
                raise BusinessError(
                    code=ResponseCode.SSO_AUTHENTICATION_FAILED,
                    msg_key="sso_login_failed",
                )
            provider_user_id = identity.get("provider_user_id")
            if not isinstance(provider_user_id, str) or not provider_user_id:
                raise BusinessError(
                    code=ResponseCode.SSO_AUTHENTICATION_FAILED,
                    msg_key="sso_login_failed",
                )
            existing = (
                await UserSSOConnection.filter(
                    integration_id=session.integration_id,
                    provider_user_id=provider_user_id,
                )
                .using_db(db)
                .first()
            )
            if existing is not None and existing.user_id != current_user.id:
                raise BusinessError(
                    code=ResponseCode.ALREADY_EXISTS,
                    msg_key="sso_connection_exists",
                )
            if (
                existing is None
                and await UserSSOConnection.filter(
                    integration_id=session.integration_id, user_id=current_user.id
                )
                .using_db(db)
                .exists()
            ):
                raise BusinessError(
                    code=ResponseCode.ALREADY_EXISTS, msg_key="sso_connection_exists"
                )
            # OAuth and directory sign-in must resolve to the same actor.
            if (
                identity.get("user_id")
                and await FeishuUser.filter(feishu_user_id=identity["user_id"])
                .exclude(user_id=current_user.id)
                .using_db(db)
                .exists()
            ):
                raise BusinessError(
                    code=ResponseCode.ALREADY_EXISTS, msg_key="sso_connection_exists"
                )
            email = identity.get("email")
            if (
                isinstance(email, str)
                and email
                and await User.filter(email=email)
                .exclude(id=current_user.id)
                .using_db(db)
                .exists()
            ):
                raise BusinessError(
                    code=ResponseCode.ALREADY_EXISTS, msg_key="sso_connection_exists"
                )
            if existing is None:
                await UserSSOConnection.create(
                    user_id=current_user.id,
                    integration_id=session.integration_id,
                    provider_user_id=provider_user_id,
                    provider_username=identity.get("username"),
                    provider_email=identity.get("email"),
                    provider_data=identity,
                    self_service_linked=True,
                    using_db=db,
                )
            elif not existing.self_service_linked:
                existing.self_service_linked = True
                await existing.save(using_db=db, update_fields=["self_service_linked"])
            provider_name = session.integration.name
            await session.delete(using_db=db)
    except IntegrityError as exc:
        raise BusinessError(
            code=ResponseCode.ALREADY_EXISTS, msg_key="sso_connection_exists"
        ) from exc

    await AuditLogService.log(
        user=current_user,
        action="link_sso",
        resource_type="sso_connection",
        resource_id=None,
        resource_name=provider_name,
        operation="create",
        status="success",
        request=request,
        metadata={"provider": provider_name},
    )
    return success()


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
    ).prefetch_related("integration")

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

    provider_name = connection.integration.name
    audit_before = AuditLogService.snapshot(connection, "sso_connection")

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
        changes={"before": audit_before},
        metadata={"provider": provider_name},
    )

    return success()
