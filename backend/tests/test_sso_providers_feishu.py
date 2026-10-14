from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from urllib.parse import parse_qs, urlparse

import pytest

from app.integrations import feishu as feishu_module
from app.integrations.credentials import encrypt_secret
from app.integrations.feishu import FeishuAPIError
from app.sso.providers.feishu import FeishuProvider


def provider(config: dict) -> SimpleNamespace:
    runtime_config = dict(config)
    credentials = {}
    if "app_secret" in runtime_config:
        credentials["app_secret"] = encrypt_secret(runtime_config.pop("app_secret"))
    return SimpleNamespace(
        config=runtime_config, credentials=credentials, attribute_mapping={}
    )


def response(status_code: int = 200, *, json_body=None, text: str = "") -> Mock:
    result = Mock()
    result.status_code = status_code
    result.text = text
    if json_body is None:
        result.json = Mock(side_effect=ValueError("not json"))
    else:
        result.json = Mock(return_value=json_body)
    return result


class AsyncClient:
    def __init__(self, result: Mock) -> None:
        self.get = AsyncMock(return_value=result)
        self.post = AsyncMock(return_value=result)

    async def __aenter__(self) -> "AsyncClient":
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None


def install_client(monkeypatch: pytest.MonkeyPatch, result: Mock) -> AsyncClient:
    client = AsyncClient(result)
    monkeypatch.setattr(feishu_module.httpx, "AsyncClient", lambda **_kwargs: client)
    return client


def test_registry_declares_both_feishu_capabilities() -> None:
    from app.integrations.registry import (
        IntegrationCapability,
        implicit_builtin_capabilities,
        integration_registry,
    )

    definition = integration_registry.get("feishu")
    assert definition.capabilities == (
        IntegrationCapability.DIRECTORY_SYNC,
        IntegrationCapability.USER_LOGIN,
    )
    # Enabling the builtin must never hand out a new sign-in path on its own.
    assert implicit_builtin_capabilities(definition) == [
        IntegrationCapability.DIRECTORY_SYNC
    ]


@pytest.mark.asyncio
async def test_authorization_url_uses_pkce_and_feishu_defaults() -> None:
    instance = FeishuProvider(provider({"app_id": "cli_test", "app_secret": "secret"}))

    url, code_verifier, nonce = await instance.get_authorization_url(
        "state-1", "https://app.example/api/v1/sso/callback/feishu"
    )

    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    assert (
        f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        == feishu_module.DEFAULT_AUTHORIZATION_URL
    )
    assert params["client_id"] == ["cli_test"]
    assert params["response_type"] == ["code"]
    assert params["redirect_uri"] == ["https://app.example/api/v1/sso/callback/feishu"]
    assert params["scope"] == [feishu_module.DEFAULT_LOGIN_SCOPES]
    assert params["state"] == ["state-1"]
    assert params["code_challenge_method"] == ["S256"]
    assert len(code_verifier) >= 43
    assert nonce == ""


@pytest.mark.asyncio
async def test_configured_endpoints_and_scopes_override_the_defaults() -> None:
    instance = FeishuProvider(
        provider(
            {
                "app_id": "cli_test",
                "app_secret": "secret",
                "authorization_url": "https://lark.example/authorize",
                "scopes": "contact:user.base:readonly",
            }
        )
    )

    url, _verifier, _nonce = await instance.get_authorization_url(
        "s", "https://app.example/cb"
    )

    params = parse_qs(urlparse(url).query)
    assert url.startswith("https://lark.example/authorize?")
    assert params["scope"] == ["contact:user.base:readonly"]


@pytest.mark.asyncio
async def test_callback_requires_an_authorization_code() -> None:
    instance = FeishuProvider(provider({"app_id": "cli_test", "app_secret": "secret"}))

    with pytest.raises(ValueError):
        await instance.handle_callback({}, "https://app.example/cb")


@pytest.mark.asyncio
async def test_callback_reports_identity_from_the_user_info_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.sso.providers.feishu.exchange_user_access_token",
        AsyncMock(return_value="u-token"),
    )
    monkeypatch.setattr(
        "app.sso.providers.feishu.fetch_user_info",
        AsyncMock(
            return_value={
                "name": "Ada",
                "en_name": "Ada Lovelace",
                "avatar_url": "https://cdn.example/ada.png",
                "open_id": "ou_1",
                "union_id": "on_1",
                "user_id": "u_1",
                "email": "Ada@Example.COM",
            }
        ),
    )
    instance = FeishuProvider(provider({"app_id": "cli_test", "app_secret": "secret"}))

    info = await instance.handle_callback(
        {"code": "code-1"}, "https://app.example/cb", code_verifier="v"
    )

    assert info["provider_user_id"] == "on_1"
    assert info["username"] == "Ada"
    assert info["email"] == "ada@example.com"
    assert info["avatar_url"] == "https://cdn.example/ada.png"
    assert info["open_id"] == "ou_1"


@pytest.mark.asyncio
async def test_callback_falls_back_to_open_id_and_enterprise_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.sso.providers.feishu.exchange_user_access_token",
        AsyncMock(return_value="u-token"),
    )
    monkeypatch.setattr(
        "app.sso.providers.feishu.fetch_user_info",
        AsyncMock(
            return_value={
                "open_id": "ou_1",
                "email": "",
                "enterprise_email": "Ada@Corp.COM",
                "user_id": "u_1",
            }
        ),
    )
    instance = FeishuProvider(provider({"app_id": "cli_test", "app_secret": "secret"}))

    info = await instance.handle_callback(
        {"code": "code-1"}, "https://app.example/cb", code_verifier="v"
    )

    assert info["provider_user_id"] == "ou_1"
    assert info["email"] == "ada@corp.com"


@pytest.mark.asyncio
async def test_callback_uses_the_directory_placeholder_without_an_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.feishu_directory import is_placeholder_email, placeholder_email

    monkeypatch.setattr(
        "app.sso.providers.feishu.exchange_user_access_token",
        AsyncMock(return_value="u-token"),
    )
    monkeypatch.setattr(
        "app.sso.providers.feishu.fetch_user_info",
        AsyncMock(return_value={"open_id": "ou_1", "user_id": "u_1"}),
    )
    instance = FeishuProvider(provider({"app_id": "cli_test", "app_secret": "secret"}))

    info = await instance.handle_callback(
        {"code": "code-1"}, "https://app.example/cb", code_verifier="v"
    )

    assert info["email"] == placeholder_email("u_1")
    assert is_placeholder_email(info["email"])


@pytest.mark.asyncio
async def test_callback_leaves_email_unset_when_feishu_returns_no_identity_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.sso.providers.feishu.exchange_user_access_token",
        AsyncMock(return_value="u-token"),
    )
    monkeypatch.setattr(
        "app.sso.providers.feishu.fetch_user_info",
        AsyncMock(return_value={"open_id": "ou_1"}),
    )
    instance = FeishuProvider(provider({"app_id": "cli_test", "app_secret": "secret"}))

    info = await instance.handle_callback(
        {"code": "code-1"}, "https://app.example/cb", code_verifier="v"
    )

    assert info["email"] is None


@pytest.mark.asyncio
async def test_callback_rejects_user_info_without_any_identifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.sso.providers.feishu.exchange_user_access_token",
        AsyncMock(return_value="u-token"),
    )
    monkeypatch.setattr(
        "app.sso.providers.feishu.fetch_user_info",
        AsyncMock(return_value={"name": "Ada"}),
    )
    instance = FeishuProvider(provider({"app_id": "cli_test", "app_secret": "secret"}))

    with pytest.raises(FeishuAPIError):
        await instance.handle_callback(
            {"code": "code-1"}, "https://app.example/cb", code_verifier="v"
        )


@pytest.mark.asyncio
async def test_authorization_url_requires_the_app_id() -> None:
    with pytest.raises(FeishuAPIError):
        await FeishuProvider(provider({"app_secret": "secret"})).get_authorization_url(
            "s", "https://app.example/cb"
        )


@pytest.mark.asyncio
async def test_callback_requires_the_app_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exchange = AsyncMock()
    monkeypatch.setattr("app.sso.providers.feishu.exchange_user_access_token", exchange)

    with pytest.raises(FeishuAPIError):
        await FeishuProvider(provider({"app_id": "cli_test"})).handle_callback(
            {"code": "code-1"}, "https://app.example/cb", code_verifier="v"
        )

    exchange.assert_not_awaited()


@pytest.mark.asyncio
async def test_token_exchange_reads_the_top_level_access_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = install_client(
        monkeypatch,
        response(json_body={"code": 0, "access_token": "u-token", "expires_in": 7200}),
    )

    token = await feishu_module.exchange_user_access_token(
        token_url=feishu_module.DEFAULT_TOKEN_URL,
        app_id="cli_test",
        app_secret="secret",
        code="code-1",
        redirect_uri="https://app.example/cb",
        code_verifier="verifier",
    )

    assert token == "u-token"
    payload = client.post.await_args.kwargs["data"]
    assert payload["grant_type"] == "authorization_code"
    assert payload["client_id"] == "cli_test"
    assert payload["code_verifier"] == "verifier"
    assert client.post.await_args.args[0] == feishu_module.DEFAULT_TOKEN_URL


@pytest.mark.asyncio
async def test_token_exchange_accepts_the_nested_legacy_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_client(
        monkeypatch,
        response(json_body={"code": 0, "data": {"user_access_token": "u-nested"}}),
    )

    token = await feishu_module.exchange_user_access_token(
        token_url="https://open.feishu.cn/open-apis/authen/v1/access_token",
        app_id="cli_test",
        app_secret="secret",
        code="code-1",
        redirect_uri="https://app.example/cb",
        code_verifier="verifier",
    )

    assert token == "u-nested"


@pytest.mark.asyncio
async def test_token_exchange_surfaces_feishu_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_client(
        monkeypatch,
        response(
            json_body={
                "code": 20050,
                "error": "server_error",
                "error_description": "retry later",
            }
        ),
    )

    with pytest.raises(FeishuAPIError) as exc:
        await feishu_module.exchange_user_access_token(
            token_url=feishu_module.DEFAULT_TOKEN_URL,
            app_id="cli_test",
            app_secret="secret",
            code="code-1",
            redirect_uri="https://app.example/cb",
            code_verifier="verifier",
        )
    assert "20050" in str(exc.value)

    install_client(monkeypatch, response(json_body={"code": 0}))
    with pytest.raises(FeishuAPIError):
        await feishu_module.exchange_user_access_token(
            token_url=feishu_module.DEFAULT_TOKEN_URL,
            app_id="cli_test",
            app_secret="secret",
            code="code-1",
            redirect_uri="https://app.example/cb",
            code_verifier="verifier",
        )


@pytest.mark.asyncio
async def test_token_exchange_rejects_transport_level_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_client(
        monkeypatch, response(400, json_body={"code": 20010, "msg": "no permission"})
    )

    with pytest.raises(FeishuAPIError):
        await feishu_module.exchange_user_access_token(
            token_url=feishu_module.DEFAULT_TOKEN_URL,
            app_id="cli_test",
            app_secret="secret",
            code="code-1",
            redirect_uri="https://app.example/cb",
            code_verifier="verifier",
        )

    install_client(monkeypatch, response(200, text="<html>gateway</html>"))
    with pytest.raises(FeishuAPIError):
        await feishu_module.exchange_user_access_token(
            token_url=feishu_module.DEFAULT_TOKEN_URL,
            app_id="cli_test",
            app_secret="secret",
            code="code-1",
            redirect_uri="https://app.example/cb",
            code_verifier="verifier",
        )


@pytest.mark.asyncio
async def test_user_info_reads_the_data_envelope_and_sends_the_bearer_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = install_client(
        monkeypatch,
        response(json_body={"code": 0, "data": {"open_id": "ou_1", "name": "Ada"}}),
    )

    info = await feishu_module.fetch_user_info(
        userinfo_url=feishu_module.DEFAULT_USERINFO_URL, user_access_token="u-token"
    )

    assert info == {"open_id": "ou_1", "name": "Ada"}
    assert client.get.await_args.kwargs["headers"]["Authorization"] == "Bearer u-token"


@pytest.mark.asyncio
async def test_user_info_tolerates_top_level_fields_and_rejects_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_client(monkeypatch, response(json_body={"code": 0, "open_id": "ou_1"}))

    info = await feishu_module.fetch_user_info(
        userinfo_url=feishu_module.DEFAULT_USERINFO_URL, user_access_token="u-token"
    )

    assert info == {"code": 0, "open_id": "ou_1"}

    install_client(
        monkeypatch, response(json_body={"code": 99991663, "msg": "invalid token"})
    )
    with pytest.raises(FeishuAPIError):
        await feishu_module.fetch_user_info(
            userinfo_url=feishu_module.DEFAULT_USERINFO_URL, user_access_token="expired"
        )
