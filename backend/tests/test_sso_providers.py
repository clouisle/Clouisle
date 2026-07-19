from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from urllib.parse import parse_qs, urlparse

import pytest

from app.sso.providers import oidc as oidc_module
from app.sso.providers.cas import CASProvider
from app.sso.providers.oidc import OIDCProvider


def provider(config: dict) -> SimpleNamespace:
    return SimpleNamespace(config=config, attribute_mapping={})


class AsyncClient:
    def __init__(self, response: Mock) -> None:
        self.get = AsyncMock(return_value=response)
        self.post = AsyncMock(return_value=response)

    async def __aenter__(self) -> "AsyncClient":
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None


@pytest.mark.asyncio
async def test_cas_builds_encoded_login_url() -> None:
    instance = CASProvider(provider({"server_url": "https://cas.example"}))

    assert await instance.get_authorization_url(
        "unused", "https://app.example/callback?next=/home"
    ) == (
        "https://cas.example/login?"
        "service=https%3A%2F%2Fapp.example%2Fcallback%3Fnext%3D%2Fhome"
    )


@pytest.mark.asyncio
async def test_cas_callback_requires_ticket() -> None:
    instance = CASProvider(provider({"server_url": "https://cas.example"}))

    with pytest.raises(ValueError):
        await instance.handle_callback({}, "https://app.example/callback")


@pytest.mark.parametrize(
    ("version", "body", "expected"),
    [
        ("1", "yes\nalice\n", {"provider_user_id": "alice", "username": "alice"}),
        (
            "2",
            """<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
              <cas:authenticationSuccess><cas:user>alice</cas:user></cas:authenticationSuccess>
            </cas:serviceResponse>""",
            {"provider_user_id": "alice", "username": "alice"},
        ),
        (
            "3",
            """<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
              <cas:authenticationSuccess><cas:user>alice</cas:user><cas:attributes>
                <cas:email>alice@example.com</cas:email><cas:department />
              </cas:attributes></cas:authenticationSuccess>
            </cas:serviceResponse>""",
            {
                "provider_user_id": "alice",
                "username": "alice",
                "email": "alice@example.com",
                "department": "",
            },
        ),
    ],
)
def test_cas_parses_success_responses(version: str, body: str, expected: dict) -> None:
    instance = CASProvider(provider({"server_url": "https://cas.example"}))

    assert instance._parse_cas_response(body, version) == expected


@pytest.mark.parametrize(
    ("version", "body"),
    [
        ("1", "no\n"),
        (
            "2",
            """<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
              <cas:authenticationFailure code="INVALID_TICKET">expired</cas:authenticationFailure>
            </cas:serviceResponse>""",
        ),
        ("3", "not xml"),
    ],
)
def test_cas_rejects_invalid_responses(version: str, body: str) -> None:
    instance = CASProvider(provider({"server_url": "https://cas.example"}))

    with pytest.raises(ValueError):
        instance._parse_cas_response(body, version)


@pytest.mark.parametrize(
    ("version", "path"),
    [("1", "/validate"), ("2", "/serviceValidate"), ("3", "/p3/serviceValidate")],
)
@pytest.mark.asyncio
async def test_cas_validates_ticket_at_version_endpoint(
    monkeypatch: pytest.MonkeyPatch, version: str, path: str
) -> None:
    response = Mock(text="yes\nalice\n")
    response.raise_for_status = Mock()
    client = AsyncClient(response)
    instance = CASProvider(
        provider({"server_url": "https://cas.example", "version": version})
    )
    instance._parse_cas_response = Mock(return_value={"provider_user_id": "alice"})
    monkeypatch.setattr("app.sso.providers.cas.httpx.AsyncClient", lambda: client)

    result = await instance._validate_ticket("ST-1", "https://app.example/callback")

    assert result == {"provider_user_id": "alice"}
    client.get.assert_awaited_once_with(
        f"https://cas.example{path}",
        params={"ticket": "ST-1", "service": "https://app.example/callback"},
    )
    response.raise_for_status.assert_called_once_with()


@pytest.mark.asyncio
async def test_oidc_builds_pkce_authorization_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = iter(["verifier", "nonce"])
    monkeypatch.setattr(
        oidc_module.secrets, "token_urlsafe", lambda _size: next(values)
    )
    instance = OIDCProvider(
        provider(
            {
                "client_id": "client id",
                "authorization_url": "https://id.example/authorize",
                "scopes": "openid email",
            }
        )
    )

    url, verifier, nonce = await instance.get_authorization_url(
        "state value", "https://app.example/callback"
    )
    query = parse_qs(urlparse(url).query)

    assert (verifier, nonce) == ("verifier", "nonce")
    assert query == {
        "client_id": ["client id"],
        "response_type": ["code"],
        "redirect_uri": ["https://app.example/callback"],
        "scope": ["openid email"],
        "state": ["state value"],
        "code_challenge": ["iMnq5o6zALKXGivsnlom_0F5_WYda32GHkxlV7mq7hQ"],
        "code_challenge_method": ["S256"],
        "nonce": ["nonce"],
    }


@pytest.mark.asyncio
async def test_oidc_callback_requires_code() -> None:
    instance = OIDCProvider(provider({}))

    with pytest.raises(ValueError):
        await instance.handle_callback({}, "https://app.example/callback")


@pytest.mark.parametrize(
    ("user_info", "provider_user_id"),
    [({"sub": "subject", "id": 12}, "subject"), ({"id": 12}, "12"), ({}, None)],
)
@pytest.mark.asyncio
async def test_oidc_callback_normalizes_provider_user_id(
    user_info: dict, provider_user_id: str | None
) -> None:
    instance = OIDCProvider(provider({}))
    instance._exchange_code = AsyncMock(return_value={"access_token": "token"})
    instance._get_user_info = AsyncMock(return_value=user_info)

    result = await instance.handle_callback(
        {"code": "code"},
        "https://app.example/callback",
        code_verifier="verifier",
    )

    assert result["provider_user_id"] == provider_user_id
    instance._exchange_code.assert_awaited_once_with(
        "code", "https://app.example/callback", "verifier"
    )
    instance._get_user_info.assert_awaited_once_with("token")


@pytest.mark.parametrize(
    ("content_type", "response_value", "expected"),
    [
        (
            "application/json; charset=utf-8",
            {"access_token": "json"},
            {"access_token": "json"},
        ),
        (
            "application/x-www-form-urlencoded",
            "access_token=form&scope=read&scope=write",
            {"access_token": "form", "scope": ["read", "write"]},
        ),
    ],
)
@pytest.mark.asyncio
async def test_oidc_exchanges_code_json_or_form_encoded(
    monkeypatch: pytest.MonkeyPatch,
    content_type: str,
    response_value: object,
    expected: dict,
) -> None:
    response = Mock(headers={"content-type": content_type})
    response.raise_for_status = Mock()
    response.json = Mock(return_value=response_value)
    response.text = response_value if isinstance(response_value, str) else ""
    client = AsyncClient(response)
    monkeypatch.setattr(oidc_module.httpx, "AsyncClient", lambda: client)
    instance = OIDCProvider(
        provider(
            {
                "token_url": "https://id.example/token",
                "client_id": "client",
                "client_secret": "secret",
            }
        )
    )

    result = await instance._exchange_code(
        "code", "https://app.example/callback", "verifier"
    )

    assert result == expected
    client.post.assert_awaited_once_with(
        "https://id.example/token",
        data={
            "grant_type": "authorization_code",
            "code": "code",
            "redirect_uri": "https://app.example/callback",
            "client_id": "client",
            "code_verifier": "verifier",
            "client_secret": "secret",
        },
        headers={"Accept": "application/json"},
    )
    response.raise_for_status.assert_called_once_with()


@pytest.mark.asyncio
async def test_oidc_gets_user_info_with_bearer_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = Mock()
    response.raise_for_status = Mock()
    response.json = Mock(return_value={"sub": "alice"})
    client = AsyncClient(response)
    monkeypatch.setattr(oidc_module.httpx, "AsyncClient", lambda: client)
    instance = OIDCProvider(provider({"userinfo_url": "https://id.example/userinfo"}))

    assert await instance._get_user_info("token") == {"sub": "alice"}
    client.get.assert_awaited_once_with(
        "https://id.example/userinfo",
        headers={"Authorization": "Bearer token"},
    )
    response.raise_for_status.assert_called_once_with()
