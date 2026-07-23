from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest

from app.api.v1.endpoints import sso
from app.core.timezone import now_utc
from app.schemas.response import BusinessError, ResponseCode


class AwaitableQuery:
    def __init__(self, result):
        self.result = result

    def prefetch_related(self, *_relations):
        return self

    def __await__(self):
        async def resolve():
            return self.result

        return resolve().__await__()


class ListQuery:
    def __init__(self, result):
        self.result = result

    async def all(self):
        return self.result


class Request:
    def __init__(self, query_params=None, form=None, base_url="http://localhost:3000/"):
        self.query_params = query_params or {}
        self.base_url = base_url
        self._form = form or {}

    async def form(self):
        return self._form


def provider(protocol="oidc"):
    return SimpleNamespace(name="company", protocol=protocol)


def session(**overrides):
    values = {
        "code_verifier": "verifier",
        "redirect_url": "/agents",
        "expires_at": now_utc() + timedelta(minutes=5),
        "delete": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def redirect_query(response):
    return parse_qs(urlparse(response.headers["location"]).query)


@pytest.fixture(autouse=True)
def site_settings(monkeypatch):
    async def get_value(key, default=None):
        return {"site_url": "https://frontend.example"}.get(key, default)

    monkeypatch.setattr(sso.SiteSetting, "get_value", get_value)


@pytest.mark.asyncio
async def test_public_provider_matrix(monkeypatch):
    monkeypatch.setattr(sso.SiteSetting, "get_value", AsyncMock(return_value=False))
    assert (await sso.list_public_providers())["data"] == []

    item = SimpleNamespace(
        id=uuid4(),
        name="company",
        display_name="Company",
        icon_url=None,
        button_text=None,
        protocol="oidc",
    )
    monkeypatch.setattr(sso.SiteSetting, "get_value", AsyncMock(return_value=True))
    filter_mock = MagicMock(return_value=ListQuery([item]))
    monkeypatch.setattr(sso.SSOProvider, "filter", filter_mock)

    result = await sso.list_public_providers()

    assert result["data"][0].name == "company"
    filter_mock.assert_called_once_with(is_enabled=True)


@pytest.mark.parametrize(
    ("protocol", "authorization_result", "session_fields"),
    [
        (
            "oidc",
            ("https://idp.example/auth", "pkce", "nonce"),
            {"code_verifier": "pkce", "nonce": "nonce"},
        ),
        ("saml2", ("https://idp.example/saml", "ignored"), {}),
        ("cas", "https://idp.example/cas", {}),
    ],
)
@pytest.mark.asyncio
async def test_login_protocol_matrix(
    monkeypatch, protocol, authorization_result, session_fields
):
    configured = provider(protocol)
    instance = SimpleNamespace(
        get_authorization_url=AsyncMock(return_value=authorization_result)
    )
    monkeypatch.setattr(
        sso.SSOProvider, "get_or_none", AsyncMock(return_value=configured)
    )
    monkeypatch.setattr(
        sso.SSOService, "get_provider_instance", MagicMock(return_value=instance)
    )
    create = AsyncMock()
    monkeypatch.setattr(sso.SSOSession, "create", create)
    monkeypatch.setattr(sso.secrets, "token_urlsafe", MagicMock(return_value="state"))

    response = await sso.sso_login("company", Request(), redirect="/agents")

    assert (
        response.headers["location"] == authorization_result[0]
        if isinstance(authorization_result, tuple)
        else authorization_result
    )
    assert create.await_args.kwargs["session_id"] == "state"
    assert create.await_args.kwargs["redirect_url"] == "/agents"
    for key, value in session_fields.items():
        assert create.await_args.kwargs[key] == value
    assert instance.get_authorization_url.await_args.kwargs["redirect_uri"] == (
        "http://localhost:8000/api/v1/sso/callback/company"
    )


@pytest.mark.parametrize(
    ("protocol", "authorization_result"),
    [("oidc", "not-a-three-tuple"), ("unknown", "unused")],
)
@pytest.mark.asyncio
async def test_login_configuration_failures_redirect(
    monkeypatch, protocol, authorization_result
):
    instance = SimpleNamespace(
        get_authorization_url=AsyncMock(return_value=authorization_result)
    )
    monkeypatch.setattr(
        sso.SSOProvider, "get_or_none", AsyncMock(return_value=provider(protocol))
    )
    monkeypatch.setattr(
        sso.SSOService, "get_provider_instance", MagicMock(return_value=instance)
    )
    monkeypatch.setattr(sso.SSOSession, "create", AsyncMock())

    response = await sso.sso_login(
        "company", Request(), redirect="https://evil.example"
    )

    assert redirect_query(response) == {
        "error": ["sso_login_failed"],
        "redirect": ["/dashboard"],
    }


@pytest.mark.parametrize(
    ("protocol", "query_params", "state", "ticket", "expected_data"),
    [
        ("oidc", {}, "state-1", None, {"code": "code-1"}),
        ("cas", {"state": "state-1"}, None, "ticket-1", {"ticket": "ticket-1"}),
        ("saml2", {"RelayState": "state-1"}, None, None, {"SAMLResponse": None}),
    ],
)
@pytest.mark.asyncio
async def test_callback_protocol_success_matrix(
    monkeypatch, protocol, query_params, state, ticket, expected_data
):
    configured = provider(protocol)
    active_user = SimpleNamespace(
        id=uuid4(), username="alice", is_active=True, last_login=None, save=AsyncMock()
    )
    current_session = session()
    instance = SimpleNamespace(
        handle_callback=AsyncMock(
            return_value={"provider_user_id": "subject", "email": "alice@example.com"}
        ),
        map_user_attributes=MagicMock(return_value={"username": "alice"}),
    )
    monkeypatch.setattr(
        sso.SSOProvider, "get_or_none", AsyncMock(return_value=configured)
    )
    monkeypatch.setattr(
        sso.SSOSession, "get_or_none", AsyncMock(return_value=current_session)
    )
    monkeypatch.setattr(
        sso.SSOService, "get_provider_instance", MagicMock(return_value=instance)
    )
    find_user = AsyncMock(return_value=(active_user, True))
    monkeypatch.setattr(sso.SSOService, "find_or_create_user", find_user)
    monkeypatch.setattr(
        sso.security, "create_access_token", MagicMock(return_value="token")
    )
    monkeypatch.setattr(sso.AuditLogService, "log", AsyncMock())

    response = await sso.sso_callback(
        "company",
        Request(query_params=query_params),
        code="code-1",
        state=state,
        ticket=ticket,
    )

    assert redirect_query(response) == {"token": ["token"], "redirect": ["/agents"]}
    assert instance.handle_callback.await_args.kwargs["callback_data"] == expected_data
    assert find_user.await_args.kwargs["user_info"] == {
        "username": "alice",
        "provider_user_id": "subject",
        "email": "alice@example.com",
    }
    active_user.save.assert_awaited_once()
    current_session.delete.assert_awaited_once()


@pytest.mark.parametrize("approval_status", ["pending", "approved"])
@pytest.mark.asyncio
async def test_callback_inactive_user_redirects_and_deletes_session(
    monkeypatch, approval_status
):
    configured = provider()
    current_session = session(redirect_url="//evil.example")
    instance = SimpleNamespace(
        handle_callback=AsyncMock(return_value={"provider_user_id": "subject"}),
        map_user_attributes=MagicMock(return_value={}),
    )
    user = SimpleNamespace(is_active=False, approval_status=approval_status)
    monkeypatch.setattr(
        sso.SSOProvider, "get_or_none", AsyncMock(return_value=configured)
    )
    monkeypatch.setattr(
        sso.SSOSession, "get_or_none", AsyncMock(return_value=current_session)
    )
    monkeypatch.setattr(
        sso.SSOService, "get_provider_instance", MagicMock(return_value=instance)
    )
    monkeypatch.setattr(
        sso.SSOService, "find_or_create_user", AsyncMock(return_value=(user, False))
    )

    response = await sso.sso_callback("company", Request(), code="code", state="state")

    assert redirect_query(response) == {
        "error": ["pending_approval" if approval_status == "pending" else "inactive"],
        "redirect": ["/dashboard"],
    }
    current_session.delete.assert_awaited_once()


@pytest.mark.parametrize(
    "current_session",
    [None, session(expires_at=now_utc() - timedelta(seconds=1))],
)
@pytest.mark.asyncio
async def test_callback_rejects_missing_or_expired_session(
    monkeypatch, current_session
):
    monkeypatch.setattr(
        sso.SSOProvider, "get_or_none", AsyncMock(return_value=provider())
    )
    monkeypatch.setattr(
        sso.SSOSession, "get_or_none", AsyncMock(return_value=current_session)
    )

    response = await sso.sso_callback("company", Request(), state="state")

    assert redirect_query(response)["error"] == ["sso_session_expired"]


@pytest.mark.parametrize("provider_user_id", [None, ""])
@pytest.mark.asyncio
async def test_callback_rejects_missing_provider_identity(
    monkeypatch, provider_user_id
):
    configured = provider()
    current_session = session()
    instance = SimpleNamespace(
        handle_callback=AsyncMock(return_value={"provider_user_id": provider_user_id})
    )
    monkeypatch.setattr(
        sso.SSOProvider, "get_or_none", AsyncMock(return_value=configured)
    )
    monkeypatch.setattr(
        sso.SSOSession, "get_or_none", AsyncMock(return_value=current_session)
    )
    monkeypatch.setattr(
        sso.SSOService, "get_provider_instance", MagicMock(return_value=instance)
    )

    response = await sso.sso_callback("company", Request(), state="state")

    assert redirect_query(response)["error"] == ["sso_login_failed"]


@pytest.mark.asyncio
async def test_callback_generic_failure_is_audited(monkeypatch):
    configured = provider()
    current_session = session()
    monkeypatch.setattr(
        sso.SSOProvider, "get_or_none", AsyncMock(return_value=configured)
    )
    monkeypatch.setattr(
        sso.SSOSession, "get_or_none", AsyncMock(return_value=current_session)
    )
    monkeypatch.setattr(
        sso.SSOService,
        "get_provider_instance",
        MagicMock(side_effect=RuntimeError("offline")),
    )
    audit = AsyncMock()
    monkeypatch.setattr(sso.AuditLogService, "log", audit)

    response = await sso.sso_callback("company", Request(), state="state")

    assert redirect_query(response)["error"] == ["sso_login_failed"]
    assert audit.await_args.kwargs["error_message"] == "offline"


@pytest.mark.asyncio
async def test_disconnect_matrix(monkeypatch):
    from app.models.user_sso_connection import UserSSOConnection

    connection_id = uuid4()
    user = SimpleNamespace(id=uuid4(), hashed_password="hash")
    connection = SimpleNamespace(
        provider=SimpleNamespace(name="company"), delete=AsyncMock()
    )
    monkeypatch.setattr(
        UserSSOConnection,
        "get_or_none",
        MagicMock(return_value=AwaitableQuery(connection)),
    )
    audit = AsyncMock()
    monkeypatch.setattr(sso.AuditLogService, "log", audit)

    result = await sso.disconnect_sso(connection_id, Request(), user)

    assert result["code"] == 0
    connection.delete.assert_awaited_once()
    assert audit.await_args.kwargs["resource_name"] == "company"

    monkeypatch.setattr(
        UserSSOConnection, "get_or_none", MagicMock(return_value=AwaitableQuery(None))
    )
    with pytest.raises(BusinessError) as missing:
        await sso.disconnect_sso(connection_id, Request(), user)
    assert missing.value.code == ResponseCode.NOT_FOUND


@pytest.mark.asyncio
async def test_disconnect_preserves_only_passwordless_auth_method(monkeypatch):
    from app.models.user_sso_connection import UserSSOConnection

    user = SimpleNamespace(id=uuid4(), hashed_password="")
    connection = SimpleNamespace(provider=SimpleNamespace(name="company"))
    monkeypatch.setattr(
        UserSSOConnection,
        "get_or_none",
        MagicMock(return_value=AwaitableQuery(connection)),
    )
    count_query = SimpleNamespace(count=AsyncMock(return_value=1))
    monkeypatch.setattr(
        UserSSOConnection, "filter", MagicMock(return_value=count_query)
    )

    with pytest.raises(BusinessError) as caught:
        await sso.disconnect_sso(uuid4(), Request(), user)

    assert caught.value.code == ResponseCode.FORBIDDEN
