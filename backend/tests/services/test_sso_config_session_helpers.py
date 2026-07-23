from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from starlette.requests import Request

from app.api.v1.endpoints import sso as sso_endpoints
from app.core.timezone import now_utc
from app.services import sso as sso_service
from app.services.sso import SSOService
from app.sso.providers.cas import CASProvider
from app.sso.providers.oidc import OIDCProvider
from app.sso.providers.saml import SAMLProvider


def make_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/sso/callback/oidc",
            "headers": [],
            "query_string": b"state=state-id&code=code",
            "server": ("api.example", 443),
            "scheme": "https",
            "client": ("testclient", 50000),
        }
    )


@pytest.mark.parametrize(
    ("protocol", "provider_type"),
    [
        ("OIDC", OIDCProvider),
        ("oauth2", OIDCProvider),
        ("saml2", SAMLProvider),
        ("cas", CASProvider),
    ],
)
def test_get_provider_instance_selects_supported_protocol(
    protocol: str, provider_type: type[object]
) -> None:
    provider = SimpleNamespace(protocol=protocol, config={})

    assert isinstance(SSOService.get_provider_instance(provider), provider_type)


def test_get_provider_instance_rejects_unsupported_protocol() -> None:
    with pytest.raises(ValueError, match="Unsupported protocol: ldap"):
        SSOService.get_provider_instance(SimpleNamespace(protocol="ldap"))


@pytest.mark.asyncio
async def test_cleanup_expired_sessions_deletes_persisted_expired_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query = SimpleNamespace(delete=AsyncMock())
    filter_sessions = AsyncMock(return_value=query)
    current_time = now_utc()

    monkeypatch.setattr("app.models.sso_session.SSOSession.filter", filter_sessions)
    monkeypatch.setattr(sso_service, "now_utc", lambda: current_time)

    await SSOService.cleanup_expired_sessions()

    filter_sessions.assert_called_once_with(expires_at__lt=current_time)
    query.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_login_persists_oidc_state_and_pkce_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = SimpleNamespace(name="oidc", protocol="oidc")
    provider_instance = SimpleNamespace(
        get_authorization_url=AsyncMock(
            return_value=("https://idp.example/authorize", "verifier", "nonce")
        )
    )
    create_session = AsyncMock()

    monkeypatch.setattr(
        sso_endpoints.SSOProvider, "get_or_none", AsyncMock(return_value=provider)
    )
    monkeypatch.setattr(
        sso_endpoints.SSOService,
        "get_provider_instance",
        lambda _provider: provider_instance,
    )
    monkeypatch.setattr(sso_endpoints.SSOSession, "create", create_session)

    response = await sso_endpoints.sso_login("oidc", make_request(), redirect="/work")

    assert response.headers["location"] == "https://idp.example/authorize"
    session_values = create_session.await_args.kwargs
    assert session_values["provider"] is provider
    assert session_values["code_verifier"] == "verifier"
    assert session_values["nonce"] == "nonce"
    assert session_values["redirect_url"] == "/work"
    assert session_values["expires_at"] > now_utc()


@pytest.mark.asyncio
async def test_callback_expired_session_returns_safe_default_redirect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = SimpleNamespace(name="oidc", protocol="oidc")
    session = SimpleNamespace(
        redirect_url="https://evil.example", expires_at=now_utc() - timedelta(seconds=1)
    )

    monkeypatch.setattr(
        sso_endpoints.SSOProvider, "get_or_none", AsyncMock(return_value=provider)
    )
    monkeypatch.setattr(
        sso_endpoints.SSOSession, "get_or_none", AsyncMock(return_value=session)
    )
    monkeypatch.setattr(
        sso_endpoints.SiteSetting,
        "get_value",
        AsyncMock(return_value="https://app.example"),
    )

    response = await sso_endpoints.sso_callback(
        "oidc", make_request(), state="state-id"
    )

    assert response.headers["location"] == (
        "https://app.example/sso-callback?error=sso_session_expired&redirect=/dashboard"
    )


@pytest.mark.asyncio
async def test_callback_success_sanitizes_stored_redirect_and_deletes_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = SimpleNamespace(name="oidc", protocol="oidc")
    session = SimpleNamespace(
        code_verifier="verifier",
        redirect_url="https://evil.example",
        expires_at=now_utc() + timedelta(minutes=1),
        delete=AsyncMock(),
    )
    user = SimpleNamespace(
        id="user-id",
        username="alice",
        is_active=True,
        last_login=None,
        save=AsyncMock(),
    )
    provider_instance = SimpleNamespace(
        handle_callback=AsyncMock(return_value={"provider_user_id": "provider-id"}),
        map_user_attributes=lambda values: {"email": "alice@example.com"},
    )

    async def get_provider(**_kwargs: object) -> object:
        return provider

    async def get_session(**_kwargs: object) -> object:
        return session

    async def get_value(key: str, default: object = None) -> object:
        return {"site_url": "https://app.example", "session_timeout_days": 7}.get(
            key, default
        )

    monkeypatch.setattr(sso_endpoints.SSOProvider, "get_or_none", get_provider)
    monkeypatch.setattr(sso_endpoints.SSOSession, "get_or_none", get_session)
    monkeypatch.setattr(
        sso_endpoints.SSOService,
        "get_provider_instance",
        lambda _provider: provider_instance,
    )
    monkeypatch.setattr(
        sso_endpoints.SSOService,
        "find_or_create_user",
        AsyncMock(return_value=(user, False)),
    )
    monkeypatch.setattr(sso_endpoints.SiteSetting, "get_value", get_value)
    monkeypatch.setattr(
        sso_endpoints.security, "create_access_token", lambda *_args, **_kwargs: "token"
    )
    monkeypatch.setattr(sso_endpoints.AuditLogService, "log", AsyncMock())

    response = await sso_endpoints.sso_callback(
        "oidc", make_request(), state="state-id", code="code"
    )

    assert response.headers["location"] == (
        "https://app.example/sso-callback?token=token&redirect=/dashboard"
    )
    provider_instance.handle_callback.assert_awaited_once()
    user.save.assert_awaited_once()
    session.delete.assert_awaited_once()
