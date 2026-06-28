from datetime import timedelta
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from app.api.v1.endpoints import sso as sso_endpoints
from app.core.timezone import now_utc
from app.schemas.response import BusinessError, ResponseCode


def make_request(query_string: bytes = b"") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/sso/callback/provider",
            "headers": [],
            "query_string": query_string,
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )


@pytest.fixture(autouse=True)
def frontend_url(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_value(key: str, default=None):
        if key == "site_url":
            return "http://frontend"
        return default

    monkeypatch.setattr(sso_endpoints.SiteSetting, "get_value", fake_get_value)


def assert_redirect(response, error_code: str, redirect: str = "/dashboard") -> None:
    assert response.status_code in {302, 303, 307}
    assert response.headers["location"] == (
        f"http://frontend/sso-callback?error={error_code}&redirect={redirect}"
    )


@pytest.mark.parametrize(
    "unsafe_redirect",
    [
        "https://evil.example/path",
        "//evil.example/path",
        "javascript:alert(1)",
        "HTTP://evil.example/path",
        "/\\evil.example/path",
        "",
    ],
)
@pytest.mark.asyncio
async def test_sso_error_redirect_sanitizes_external_redirects(
    unsafe_redirect: str,
) -> None:
    response = await sso_endpoints._sso_error_redirect(
        "sso_session_expired", unsafe_redirect
    )

    assert_redirect(response, "sso_session_expired")


@pytest.mark.asyncio
async def test_sso_login_missing_provider_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_or_none(**kwargs):
        return None

    monkeypatch.setattr(sso_endpoints.SSOProvider, "get_or_none", fake_get_or_none)

    response = await sso_endpoints.sso_login("missing", make_request(), redirect=None)

    assert_redirect(response, "sso_provider_not_found")


@pytest.mark.asyncio
async def test_sso_callback_missing_provider_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_or_none(**kwargs):
        return None

    monkeypatch.setattr(sso_endpoints.SSOProvider, "get_or_none", fake_get_or_none)

    response = await sso_endpoints.sso_callback("missing", make_request())

    assert_redirect(response, "sso_provider_not_found")


@pytest.mark.asyncio
async def test_sso_callback_missing_session_id_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_or_none(**kwargs):
        return SimpleNamespace(name="oidc", protocol="oidc")

    monkeypatch.setattr(sso_endpoints.SSOProvider, "get_or_none", fake_get_or_none)

    response = await sso_endpoints.sso_callback("oidc", make_request(), state=None)

    assert_redirect(response, "sso_session_expired")


@pytest.mark.asyncio
async def test_sso_callback_provider_exception_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = SimpleNamespace(name="oidc", protocol="oidc")
    session = SimpleNamespace(
        code_verifier="verifier",
        redirect_url="/app",
        expires_at=now_utc() + timedelta(minutes=1),
    )

    async def fake_provider_get_or_none(**kwargs):
        return provider

    async def fake_session_get_or_none(**kwargs):
        return session

    class FailingProvider:
        async def handle_callback(self, **kwargs):
            raise BusinessError(
                code=ResponseCode.SSO_AUTHENTICATION_FAILED,
                msg_key="sso_login_failed",
            )

    async def fake_log(**kwargs):
        return None

    monkeypatch.setattr(
        sso_endpoints.SSOProvider, "get_or_none", fake_provider_get_or_none
    )
    monkeypatch.setattr(
        sso_endpoints.SSOSession, "get_or_none", fake_session_get_or_none
    )
    monkeypatch.setattr(
        sso_endpoints.SSOService,
        "get_provider_instance",
        lambda provider: FailingProvider(),
    )
    monkeypatch.setattr(sso_endpoints.AuditLogService, "log", fake_log)

    response = await sso_endpoints.sso_callback(
        "oidc", make_request(b"state=session-id"), state="session-id", code="code"
    )

    assert_redirect(response, "sso_login_failed", "/app")
