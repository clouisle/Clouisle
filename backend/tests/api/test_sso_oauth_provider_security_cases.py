"""Provider and connection failure semantics for OAuth-style sign-in.

Each case pins a decision that either a browser-visible redirect or a stored
credential depends on: the configured callback origin, unsupported protocols
failing closed, one-time link staging, single-session issuance, public-client
token exchange, and provider HTTP error normalization. No outbound network
calls are made.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import pytest
from tortoise import Tortoise
from tortoise.exceptions import IntegrityError

from app.api.v1.endpoints import sso
from app.core import redis as redis_module
from app.core.timezone import now_utc
from app.schemas.response import BusinessError, ResponseCode
from app.services import sso as sso_service
from app.services import team_role_sync
from app.services import tool_oauth as oauth
from app.sso.providers import oidc as oidc_module
from app.sso.providers.cas import CASProvider
from app.sso.providers.oidc import OIDCProvider

pytestmark = pytest.mark.asyncio


class _Request:
    def __init__(self, query_params=None, base_url="http://api.test/"):
        self.query_params = query_params or {}
        self.base_url = base_url


def _redirect_query(response) -> dict[str, list[str]]:
    return parse_qs(urlparse(response.headers["location"]).query)


def _frontend_settings(monkeypatch, **overrides):
    values = {"sso_enabled": True, "site_url": "https://frontend.example"}
    values.update(overrides)

    async def get_value(key, default=None):
        return values.get(key, default)

    monkeypatch.setattr(sso.SiteSetting, "get_value", get_value)


async def _link_settings(key, default=None):
    return True if key == "sso_enabled" else default


def _assert_sso_error(response, error_code: str, redirect: str = "/app") -> None:
    assert response.status_code in {302, 303, 307}
    assert _redirect_query(response) == {
        "error": [error_code],
        "redirect": [redirect],
    }


# ---------------------------------------------------------------------------
# SSO login/callback fail-closed behavior
# ---------------------------------------------------------------------------


async def test_login_fails_closed_for_capability_without_protocol_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _frontend_settings(monkeypatch)
    provider = SimpleNamespace(name="company", provider_type="ldap")
    instance = SimpleNamespace(get_authorization_url=AsyncMock())
    create_session = AsyncMock()
    monkeypatch.setattr(sso, "_supports_login", lambda _provider: True)
    monkeypatch.setattr(
        sso.Integration, "get_or_none", AsyncMock(return_value=provider)
    )
    monkeypatch.setattr(
        sso.SSOService, "get_provider_instance", MagicMock(return_value=instance)
    )
    monkeypatch.setattr(sso.SSOSession, "create", create_session)

    response = await sso.sso_login("company", _Request(), redirect=None)

    _assert_sso_error(response, "sso_login_failed")
    instance.get_authorization_url.assert_not_awaited()
    create_session.assert_not_awaited()


async def test_callback_fails_closed_for_capability_without_protocol_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _frontend_settings(monkeypatch)
    provider = SimpleNamespace(
        name="company",
        provider_type="ldap",
        is_enabled=True,
        enabled_capabilities=["user_login"],
    )
    session = SimpleNamespace(
        link_user_id=None,
        redirect_url=None,
        expires_at=now_utc() + timedelta(minutes=5),
        delete=AsyncMock(),
    )
    instance = SimpleNamespace(
        handle_callback=AsyncMock(return_value={"provider_user_id": "subject"})
    )
    monkeypatch.setattr(sso, "_supports_login", lambda _provider: True)
    monkeypatch.setattr(
        sso.Integration, "get_or_none", AsyncMock(return_value=provider)
    )
    monkeypatch.setattr(sso.SSOSession, "get_or_none", AsyncMock(return_value=session))
    monkeypatch.setattr(
        sso.SSOService, "get_provider_instance", MagicMock(return_value=instance)
    )
    monkeypatch.setattr(sso.AuditLogService, "log", AsyncMock())

    response = await sso.sso_callback(
        "company",
        _Request(query_params={"RelayState": "session-id"}),
        code="code",
        state=None,
    )

    _assert_sso_error(response, "sso_login_failed")
    instance.handle_callback.assert_not_awaited()


async def test_callback_rejects_link_session_that_cannot_be_staged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _frontend_settings(monkeypatch)
    provider = SimpleNamespace(
        name="feishu",
        provider_type="feishu",
        is_enabled=True,
        enabled_capabilities=["user_login"],
    )
    session = SimpleNamespace(
        id=uuid4(),
        session_id="session-id",
        link_user_id=uuid4(),
        link_user_info=None,
        code_verifier="verifier",
        redirect_url="/app",
        expires_at=now_utc() + timedelta(minutes=5),
        delete=AsyncMock(),
    )
    instance = SimpleNamespace(
        handle_callback=AsyncMock(return_value={"provider_user_id": "subject"}),
        map_user_attributes=MagicMock(return_value={}),
    )
    update = AsyncMock(return_value=0)
    monkeypatch.setattr(
        sso.Integration, "get_or_none", AsyncMock(return_value=provider)
    )
    monkeypatch.setattr(sso.SSOSession, "get_or_none", AsyncMock(return_value=session))
    monkeypatch.setattr(
        sso.SSOSession, "filter", MagicMock(return_value=SimpleNamespace(update=update))
    )
    monkeypatch.setattr(
        sso.SSOService, "get_provider_instance", MagicMock(return_value=instance)
    )
    monkeypatch.setattr(sso.AuditLogService, "log", AsyncMock())

    response = await sso.sso_callback(
        "feishu", _Request(), code="code", state="session-id"
    )

    assert urlparse(response.headers["location"]).path == "/sso-link-callback"
    assert _redirect_query(response) == {"error": ["sso_login_failed"]}
    update.assert_awaited_once()
    session.delete.assert_awaited_once()


async def test_callback_registers_single_session_for_issued_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _frontend_settings(monkeypatch, session_timeout_days=2, single_session=True)
    provider = SimpleNamespace(
        name="company",
        provider_type="oidc",
        is_enabled=True,
        enabled_capabilities=["user_login"],
    )
    session = SimpleNamespace(
        link_user_id=None,
        code_verifier="verifier",
        redirect_url="/app",
        expires_at=now_utc() + timedelta(minutes=5),
        delete=AsyncMock(),
    )
    instance = SimpleNamespace(
        handle_callback=AsyncMock(return_value={"provider_user_id": "subject"}),
        map_user_attributes=MagicMock(return_value={}),
    )
    user = SimpleNamespace(
        id=uuid4(),
        username="alice",
        is_active=True,
        last_login=None,
        save=AsyncMock(),
    )
    store_session = AsyncMock()
    monkeypatch.setattr(
        sso.Integration, "get_or_none", AsyncMock(return_value=provider)
    )
    monkeypatch.setattr(sso.SSOSession, "get_or_none", AsyncMock(return_value=session))
    monkeypatch.setattr(
        sso.SSOService, "get_provider_instance", MagicMock(return_value=instance)
    )
    monkeypatch.setattr(
        sso.SSOService,
        "find_or_create_user",
        AsyncMock(return_value=(user, True)),
    )
    monkeypatch.setattr(
        sso.security, "create_access_token", MagicMock(return_value="issued-token")
    )
    monkeypatch.setattr(sso.AuditLogService, "log", AsyncMock())
    monkeypatch.setattr(redis_module, "set_user_session", store_session)

    response = await sso.sso_callback("company", _Request(), code="code", state="sid")

    assert _redirect_query(response) == {
        "token": ["issued-token"],
        "redirect": ["/app"],
    }
    store_session.assert_awaited_once_with(str(user.id), "issued-token", 172800)
    session.delete.assert_awaited_once()


# ---------------------------------------------------------------------------
# Account-link completion against real rows
# ---------------------------------------------------------------------------


async def _sso_database():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    await Tortoise.generate_schemas()


async def _actor_and_provider():
    from app.models.integration import Integration
    from app.models.user import User

    actor = await User.create(
        username=f"actor_{uuid4().hex[:8]}",
        email=f"actor_{uuid4().hex[:8]}@example.com",
        hashed_password="hash",
    )
    provider = await Integration.create(
        name=f"feishu_{uuid4().hex[:8]}",
        provider_type="feishu",
        display_name="Feishu",
        enabled_capabilities=["user_login"],
    )
    return actor, provider


async def test_complete_link_rejects_non_mapping_staged_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models.sso_session import SSOSession

    await _sso_database()
    try:
        actor, provider = await _actor_and_provider()
        state = "tampered-link"
        await SSOSession.create(
            session_id=state,
            integration=provider,
            link_user=actor,
            link_user_info=["provider_user_id"],
            expires_at=now_utc() + timedelta(minutes=5),
        )
        monkeypatch.setattr(
            sso.SiteSetting,
            "get_value",
            _link_settings,
        )
        monkeypatch.setattr(sso.AuditLogService, "log", AsyncMock())

        with pytest.raises(BusinessError) as caught:
            await sso.complete_account_link(
                sso.SSOAccountLinkRequest(session_id=state),
                _Request(),
                actor,
            )

        assert caught.value.code == ResponseCode.SSO_AUTHENTICATION_FAILED
        assert caught.value.msg_key == "sso_login_failed"
    finally:
        await Tortoise.close_connections()


async def test_complete_link_maps_concurrent_identity_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models.sso_session import SSOSession

    await _sso_database()
    try:
        actor, provider = await _actor_and_provider()
        state = "raced-link"
        await SSOSession.create(
            session_id=state,
            integration=provider,
            link_user=actor,
            link_user_info={"provider_user_id": "subject"},
            expires_at=now_utc() + timedelta(minutes=5),
        )
        monkeypatch.setattr(sso.SiteSetting, "get_value", _link_settings)
        monkeypatch.setattr(sso.AuditLogService, "log", AsyncMock())
        monkeypatch.setattr(
            sso.UserSSOConnection,
            "create",
            AsyncMock(side_effect=IntegrityError("duplicate identity")),
        )

        with pytest.raises(BusinessError) as caught:
            await sso.complete_account_link(
                sso.SSOAccountLinkRequest(session_id=state),
                _Request(),
                actor,
            )

        assert caught.value.code == ResponseCode.ALREADY_EXISTS
        assert caught.value.msg_key == "sso_connection_exists"
    finally:
        await Tortoise.close_connections()


async def test_complete_link_accepts_existing_self_service_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models.sso_session import SSOSession
    from app.models.user_sso_connection import UserSSOConnection

    await _sso_database()
    try:
        actor, provider = await _actor_and_provider()
        existing = await UserSSOConnection.create(
            user=actor,
            integration=provider,
            provider_user_id="already-self-service",
            self_service_linked=True,
        )
        state = "repeat-link"
        await SSOSession.create(
            session_id=state,
            integration=provider,
            link_user=actor,
            link_user_info={"provider_user_id": "already-self-service"},
            expires_at=now_utc() + timedelta(minutes=5),
        )
        monkeypatch.setattr(sso.SiteSetting, "get_value", _link_settings)
        monkeypatch.setattr(sso.AuditLogService, "log", AsyncMock())
        create_connection = AsyncMock()
        monkeypatch.setattr(sso.UserSSOConnection, "create", create_connection)

        result = await sso.complete_account_link(
            sso.SSOAccountLinkRequest(session_id=state),
            _Request(),
            actor,
        )

        assert result["code"] == 0
        create_connection.assert_not_awaited()
        assert await SSOSession.filter(session_id=state).count() == 0
        assert (await UserSSOConnection.get(id=existing.id)).self_service_linked is True
    finally:
        await Tortoise.close_connections()


async def test_disconnect_allows_passwordless_user_with_another_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models.user_sso_connection import UserSSOConnection

    class AwaitableQuery:
        def __init__(self, result):
            self.result = result

        def prefetch_related(self, *_relations):
            return self

        def __await__(self):
            async def resolve():
                return self.result

            return resolve().__await__()

    user = SimpleNamespace(id=uuid4(), hashed_password="")
    connection = SimpleNamespace(
        integration=SimpleNamespace(name="company"), delete=AsyncMock()
    )
    monkeypatch.setattr(
        UserSSOConnection,
        "get_or_none",
        MagicMock(return_value=AwaitableQuery(connection)),
    )
    count_query = SimpleNamespace(count=AsyncMock(return_value=2))
    monkeypatch.setattr(
        UserSSOConnection, "filter", MagicMock(return_value=count_query)
    )
    audit = AsyncMock()
    monkeypatch.setattr(sso.AuditLogService, "log", audit)

    result = await sso.disconnect_sso(uuid4(), _Request(), user)

    assert result["code"] == 0
    connection.delete.assert_awaited_once()
    assert audit.await_args.kwargs["resource_name"] == "company"


# ---------------------------------------------------------------------------
# SSO service protocol and role edge cases
# ---------------------------------------------------------------------------


async def test_provider_factory_rejects_integration_without_login_capability() -> None:
    with pytest.raises(ValueError, match="does not support login: email"):
        sso_service.SSOService.get_provider_instance(
            SimpleNamespace(provider_type="email")
        )


async def test_provider_factory_rejects_login_protocol_without_implementation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sso_service.integration_registry,
        "get",
        lambda _protocol: SimpleNamespace(capabilities=["user_login"]),
    )

    with pytest.raises(ValueError, match="Unsupported protocol: ldap"):
        sso_service.SSOService.get_provider_instance(
            SimpleNamespace(provider_type="ldap")
        )


async def test_find_or_create_user_skips_stale_configured_default_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _ConnectionQuery:
        def prefetch_related(self, *_args):
            return self

        async def first(self):
            return None

    new_user = SimpleNamespace(id="user-id", roles=SimpleNamespace(add=AsyncMock()))
    user_create = AsyncMock(return_value=new_user)
    assign_default_role = AsyncMock()
    assign_default_team = AsyncMock()
    create_connection = AsyncMock()

    async def get_value(key, default=None):
        values = {
            "sso_match_by_email": False,
            "sso_auto_create_users": True,
            "sso_require_approval": False,
            "default_language": "en",
        }
        return values.get(key, default)

    monkeypatch.setattr(sso_service.SiteSetting, "get_value", get_value)
    monkeypatch.setattr(
        sso_service.User,
        "filter",
        lambda **_kwargs: SimpleNamespace(exists=AsyncMock(return_value=False)),
    )
    monkeypatch.setattr(sso_service.User, "create", user_create)
    monkeypatch.setattr(sso_service.Role, "get_or_none", AsyncMock(return_value=None))
    monkeypatch.setattr(
        sso_service.UserSSOConnection, "filter", lambda **_kwargs: _ConnectionQuery()
    )
    monkeypatch.setattr(sso_service.UserSSOConnection, "create", create_connection)
    monkeypatch.setattr(team_role_sync, "assign_default_role", assign_default_role)
    monkeypatch.setattr(team_role_sync, "assign_default_team", assign_default_team)

    user, is_new = await sso_service.SSOService.find_or_create_user(
        provider=SimpleNamespace(
            name="oidc",
            login_config={
                "allow_signup": True,
                "default_role_id": "stale-role",
            },
        ),
        provider_user_id="provider-user-id",
        user_info={"email": "alice@example.com"},
    )

    assert (user, is_new) == (new_user, True)
    new_user.roles.add.assert_not_awaited()
    assign_default_role.assert_not_awaited()
    assign_default_team.assert_awaited_once_with(new_user)
    create_connection.assert_awaited_once()


# ---------------------------------------------------------------------------
# Provider-level token exchange and response parsing
# ---------------------------------------------------------------------------


def _provider_runtime(config: dict, credentials: dict | None = None):
    return SimpleNamespace(
        config=dict(config),
        credentials=dict(credentials or {}),
        attribute_mapping={},
    )


async def test_oidc_public_client_omits_pkce_and_empty_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = Mock(headers={"content-type": "application/json"})
    response.raise_for_status = Mock()
    response.json = Mock(return_value={"access_token": "token"})
    client = SimpleNamespace(post=AsyncMock(return_value=response))

    class _Client:
        async def __aenter__(self):
            return client

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(oidc_module.httpx, "AsyncClient", lambda: _Client())
    instance = OIDCProvider(
        _provider_runtime(
            {
                "token_url": "https://id.example/token",
                "client_id": "public-client",
            }
        )
    )

    result = await instance._exchange_code("code", "https://app.example/callback")

    assert result == {"access_token": "token"}
    assert client.post.await_args.kwargs["data"] == {
        "grant_type": "authorization_code",
        "code": "code",
        "redirect_uri": "https://app.example/callback",
        "client_id": "public-client",
    }


async def test_cas_version_three_without_attributes_returns_identity() -> None:
    instance = CASProvider(_provider_runtime({"server_url": "https://cas.example"}))
    body = """<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
      <cas:authenticationSuccess><cas:user>alice</cas:user></cas:authenticationSuccess>
    </cas:serviceResponse>"""

    assert instance._parse_cas_response(body, "3") == {
        "provider_user_id": "alice",
        "username": "alice",
    }


# ---------------------------------------------------------------------------
# Tool OAuth discovery and HTTP error normalization
# ---------------------------------------------------------------------------


async def test_try_json_skips_absent_endpoints_but_propagates_server_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def endpoint_error(url, **kwargs):
        raise oauth._OAuthEndpointError("http_error", status=endpoint_error.status)

    monkeypatch.setattr(oauth.ToolOAuthService, "_http_json", endpoint_error)

    for status in (400, 401, 403, 404, 410):
        endpoint_error.status = status
        assert (
            await oauth.ToolOAuthService._try_json("https://as.example/metadata")
            is None
        )

    endpoint_error.status = 500
    with pytest.raises(oauth._OAuthEndpointError) as failed:
        await oauth.ToolOAuthService._try_json("https://as.example/metadata")
    assert failed.value.error == "http_error"


async def test_http_json_normalizes_error_bodies_without_leaking_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(oauth, "ensure_external_http_url_allowed", AsyncMock())
    handler_holder: dict[str, object] = {}
    real_client = httpx.AsyncClient

    def client_factory(*_args, **_kwargs):
        return real_client(
            transport=httpx.MockTransport(handler_holder["handler"]),
            follow_redirects=False,
        )

    monkeypatch.setattr(oauth.httpx, "AsyncClient", client_factory)

    # Empty, non-JSON body: no payload shape is trusted, so only the status is.
    handler_holder["handler"] = lambda request: httpx.Response(
        503, content=b"", headers={"content-type": "text/plain"}
    )
    with pytest.raises(oauth._OAuthEndpointError) as empty:
        await oauth.ToolOAuthService._http_json(
            "https://as.example.test/token", method="POST"
        )
    assert (empty.value.error, empty.value.description, empty.value.status) == (
        "http_error",
        None,
        503,
    )

    # Non-string error/description fields must not reach the redirect surface.
    handler_holder["handler"] = lambda request: httpx.Response(
        400, json={"error": 5, "error_description": ["secret"]}
    )
    with pytest.raises(oauth._OAuthEndpointError) as typed:
        await oauth.ToolOAuthService._http_json(
            "https://as.example.test/token", method="POST"
        )
    assert (typed.value.error, typed.value.description, typed.value.status) == (
        "http_error",
        None,
        400,
    )


async def test_consume_flow_treats_lost_update_as_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flow = SimpleNamespace(
        id=uuid4(),
        consumed_at=None,
        expires_at=now_utc() + timedelta(minutes=5),
    )

    class FirstQuery:
        async def first(self):
            return flow

    class UpdateQuery:
        async def update(self, **_kwargs):
            return 0

    queries = iter([FirstQuery(), UpdateQuery()])
    monkeypatch.setattr(oauth.ToolOAuthFlow, "filter", lambda **_kwargs: next(queries))

    with pytest.raises(BusinessError) as caught:
        await oauth.ToolOAuthService._consume_flow("state-value")

    assert caught.value.code == ResponseCode.TOOL_OAUTH_STATE_INVALID
    assert caught.value.msg_key == "tool_oauth_state_invalid"
