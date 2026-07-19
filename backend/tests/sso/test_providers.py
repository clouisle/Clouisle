from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from urllib.parse import parse_qs, urlparse

import pytest

from app.sso.providers import oidc as oidc_module
from app.sso.providers import saml as saml_module
from app.sso.providers.base import BaseSSOProvider
from app.sso.providers.cas import CASProvider
from app.sso.providers.oidc import OIDCProvider
from app.sso.providers.saml import SAMLProvider


class StubProvider(BaseSSOProvider):
    async def get_authorization_url(
        self, state: str, redirect_uri: str, **kwargs
    ) -> str:
        return redirect_uri

    async def handle_callback(self, callback_data, redirect_uri: str, **kwargs):
        return callback_data


def provider(config=None, attribute_mapping=None):
    return SimpleNamespace(
        config=config or {}, attribute_mapping=attribute_mapping or {}
    )


def test_base_maps_nested_and_jsonpath_attributes() -> None:
    instance = StubProvider(
        provider(
            attribute_mapping={
                "email": "profile.email",
                "first_email": "$.emails[0].value",
                "missing": "profile.missing",
                "empty": "profile.empty",
            }
        )
    )

    assert instance.map_user_attributes(
        {
            "profile": {"email": "alice@example.com", "empty": ""},
            "emails": [{"value": "first@example.com"}],
        }
    ) == {"email": "alice@example.com", "first_email": "first@example.com"}


@pytest.mark.parametrize("path", ["$.missing[", "profile.email.value"])
def test_base_invalid_attribute_paths_are_ignored(path: str) -> None:
    instance = StubProvider(provider(attribute_mapping={"email": path}))

    assert (
        instance.map_user_attributes({"profile": {"email": "alice@example.com"}}) == {}
    )


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


@pytest.mark.asyncio
async def test_cas_callback_returns_validated_user() -> None:
    instance = CASProvider(provider({"server_url": "https://cas.example"}))
    instance._validate_ticket = AsyncMock(return_value={"provider_user_id": "alice"})

    result = await instance.handle_callback(
        {"ticket": "ST-1"}, "https://app.example/callback"
    )

    assert result == {"provider_user_id": "alice"}
    instance._validate_ticket.assert_awaited_once_with(
        "ST-1", "https://app.example/callback"
    )


@pytest.mark.parametrize(
    ("version", "response", "expected"),
    [
        ("1", "yes\nalice", {"provider_user_id": "alice", "username": "alice"}),
        (
            "3",
            """<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
            <cas:authenticationSuccess><cas:user>alice</cas:user>
            <cas:attributes><cas:email>alice@example.com</cas:email></cas:attributes>
            </cas:authenticationSuccess></cas:serviceResponse>""",
            {
                "provider_user_id": "alice",
                "username": "alice",
                "email": "alice@example.com",
            },
        ),
    ],
)
def test_cas_parses_success_responses(
    version: str, response: str, expected: dict
) -> None:
    instance = CASProvider(provider({"server_url": "https://cas.example"}))

    assert instance._parse_cas_response(response, version) == expected


@pytest.mark.parametrize(
    "response",
    [
        "not xml",
        """<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
        <cas:authenticationFailure>bad ticket</cas:authenticationFailure>
        </cas:serviceResponse>""",
    ],
)
def test_cas_rejects_invalid_responses(response: str) -> None:
    instance = CASProvider(provider({"server_url": "https://cas.example"}))

    with pytest.raises(ValueError):
        instance._parse_cas_response(response, "3")


@pytest.mark.asyncio
async def test_oidc_builds_pkce_authorization_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance = OIDCProvider(
        provider(
            {
                "client_id": "client id",
                "authorization_url": "https://idp.example/authorize",
            }
        )
    )
    tokens = iter(["verifier", "nonce"])
    monkeypatch.setattr(
        oidc_module.secrets, "token_urlsafe", lambda _length: next(tokens)
    )

    url, verifier, nonce = await instance.get_authorization_url(
        "state", "https://app.example/callback"
    )
    query = parse_qs(urlparse(url).query)

    assert verifier == "verifier"
    assert nonce == "nonce"
    assert query["client_id"] == ["client id"]
    assert query["scope"] == ["openid email profile"]
    assert query["state"] == ["state"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["nonce"] == ["nonce"]


@pytest.mark.asyncio
async def test_oidc_callback_requires_code() -> None:
    instance = OIDCProvider(provider())

    with pytest.raises(ValueError):
        await instance.handle_callback({}, "https://app.example/callback")


@pytest.mark.parametrize(
    ("user_info", "provider_user_id"),
    [({"sub": "subject"}, "subject"), ({"id": 42}, "42"), ({}, None)],
)
@pytest.mark.asyncio
async def test_oidc_callback_normalizes_provider_user_id(
    user_info: dict, provider_user_id: str | None
) -> None:
    instance = OIDCProvider(provider())
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


@pytest.mark.asyncio
async def test_oidc_validates_id_token(monkeypatch: pytest.MonkeyPatch) -> None:
    instance = OIDCProvider(provider({"client_secret": "secret"}))
    decoded = SimpleNamespace(claims={"sub": "alice"})
    decode = Mock(return_value=decoded)
    monkeypatch.setattr(oidc_module.jwt, "decode", decode)

    assert await instance.validate_id_token("token") == {"sub": "alice"}
    decode.assert_called_once_with("token", "secret")


@pytest.mark.asyncio
async def test_saml_builds_login_url_with_relay_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth = Mock()
    auth.login.return_value = "https://idp.example/login"
    auth_class = Mock(return_value=auth)
    monkeypatch.setattr(saml_module, "OneLogin_Saml2_Auth", auth_class)
    instance = SAMLProvider(
        provider(
            {
                "sp_entity_id": "sp",
                "acs_url": "https://app.example/default",
                "idp_entity_id": "idp",
                "sso_url": "https://idp.example/sso",
                "x509_cert": "certificate",
            }
        )
    )

    result = await instance.get_authorization_url(
        "relay-state", "https://app.example/callback"
    )

    assert result == "https://idp.example/login"
    assert auth_class.call_args.args[1]["sp"]["assertionConsumerService"]["url"] == (
        "https://app.example/callback"
    )
    auth.login.assert_called_once_with(return_to="relay-state")


@pytest.mark.asyncio
async def test_saml_callback_requires_response() -> None:
    instance = SAMLProvider(provider())

    with pytest.raises(ValueError):
        await instance.handle_callback({}, "https://app.example/callback")


@pytest.mark.asyncio
async def test_saml_callback_rejects_failed_authentication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth = Mock()
    auth.is_authenticated.return_value = False
    auth.get_errors.return_value = ["invalid_response"]
    auth.get_last_error_reason.return_value = "invalid"
    monkeypatch.setattr(saml_module, "OneLogin_Saml2_Auth", Mock(return_value=auth))
    instance = SAMLProvider(provider())
    instance._get_saml_settings = Mock(return_value={})

    with pytest.raises(ValueError):
        await instance.handle_callback(
            {"SAMLResponse": "encoded"}, "https://app.example/callback"
        )

    auth.process_response.assert_called_once_with()


@pytest.mark.asyncio
async def test_saml_callback_flattens_attributes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth = Mock()
    auth.is_authenticated.return_value = True
    auth.get_attributes.return_value = {
        "email": ["alice@example.com", "other@example.com"],
        "groups": [],
        "role": "admin",
    }
    auth.get_nameid.return_value = "alice"
    auth.get_session_index.return_value = "session"
    monkeypatch.setattr(saml_module, "OneLogin_Saml2_Auth", Mock(return_value=auth))
    instance = SAMLProvider(provider())
    instance._get_saml_settings = Mock(return_value={})

    result = await instance.handle_callback(
        {"SAMLResponse": "encoded"}, "https://app.example/callback"
    )

    assert result == {
        "provider_user_id": "alice",
        "nameID": "alice",
        "session_index": "session",
        "attributes": {
            "email": "alice@example.com",
            "groups": [],
            "role": "admin",
        },
        "email": "alice@example.com",
        "groups": [],
        "role": "admin",
    }
