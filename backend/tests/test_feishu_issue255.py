from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core import feishu


class Client:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.post = AsyncMock(side_effect=self._post)

    async def _post(self, *_args, **_kwargs):
        if self.error:
            raise self.error
        return SimpleNamespace(json=lambda: self.result)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


def config(**overrides):
    values = {
        "enabled": True,
        "notification_type": "webhook",
        "webhook_url": "https://hooks.example.test/feishu",
        "secret": "secret",
        "app_id": "app-id",
        "app_secret": "app-secret",
    }
    values.update(overrides)
    return values


def install_client(monkeypatch, result=None, error=None):
    client = Client(result, error)
    monkeypatch.setattr(feishu.httpx, "AsyncClient", lambda **_kwargs: client)
    return client


@pytest.mark.anyio
async def test_config_and_signature(monkeypatch):
    get_value = AsyncMock(
        side_effect=[True, "app", "hook", "secret", "app-id", "app-secret"]
    )
    monkeypatch.setattr(feishu.SiteSetting, "get_value", get_value)

    assert await feishu.get_feishu_config() == {
        "enabled": True,
        "notification_type": "app",
        "webhook_url": "hook",
        "secret": "secret",
        "app_id": "app-id",
        "app_secret": "app-secret",
    }
    assert (
        feishu._generate_sign("secret", 1)
        == "6o+SjynWLFd+QtSzfgy9uvrayMJ+/S8z4k5MmO7xW68="
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "settings",
    [config(enabled=False), config(webhook_url="")],
)
async def test_webhook_rejects_disabled_or_unconfigured(monkeypatch, settings):
    monkeypatch.setattr(feishu, "get_feishu_config", AsyncMock(return_value=settings))
    client = install_client(monkeypatch, {"code": 0})

    assert await feishu.send_feishu_webhook("Title", "Body") is False
    client.post.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize("response", [{"code": 0}, {"StatusCode": 0}])
async def test_webhook_posts_signed_card(monkeypatch, response):
    monkeypatch.setattr(feishu, "get_feishu_config", AsyncMock(return_value=config()))
    monkeypatch.setattr(feishu.time, "time", lambda: 123)
    client = install_client(monkeypatch, response)

    assert (
        await feishu.send_feishu_webhook(
            "Title", "Body", "https://app.example.test/details"
        )
        is True
    )

    message = client.post.await_args.kwargs["json"]
    assert client.post.await_args.args == ("https://hooks.example.test/feishu",)
    assert message["timestamp"] == "123"
    assert message["sign"] == feishu._generate_sign("secret", 123)
    assert message["card"]["elements"][1]["actions"][0]["url"] == (
        "https://app.example.test/details"
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "result,error", [({"code": 1}, None), (None, RuntimeError("offline"))]
)
async def test_webhook_reports_provider_failures(monkeypatch, result, error):
    monkeypatch.setattr(
        feishu, "get_feishu_config", AsyncMock(return_value=config(secret=""))
    )
    install_client(monkeypatch, result, error)

    assert await feishu.send_feishu_webhook("Title", "Body") is False


@pytest.mark.anyio
async def test_tenant_token_credentials_and_provider_results(monkeypatch):
    monkeypatch.setattr(
        feishu,
        "get_feishu_config",
        AsyncMock(side_effect=[config(app_id=""), config(), config()]),
    )
    client = install_client(monkeypatch, {"code": 0, "tenant_access_token": "token"})

    assert await feishu.get_feishu_tenant_access_token() is None
    assert await feishu.get_feishu_tenant_access_token() == "token"
    client.result = {"code": 1}
    assert await feishu.get_feishu_tenant_access_token() is None
    client.post.assert_awaited_with(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": "app-id", "app_secret": "app-secret"},
    )


@pytest.mark.anyio
async def test_app_message_guards_and_posts_card(monkeypatch):
    monkeypatch.setattr(
        feishu,
        "get_feishu_config",
        AsyncMock(side_effect=[config(enabled=False), config(), config(), config()]),
    )
    token = AsyncMock(side_effect=[None, "token"])
    monkeypatch.setattr(feishu, "get_feishu_tenant_access_token", token)
    client = install_client(monkeypatch, {"code": 0})

    assert (
        await feishu.send_feishu_app_message("Title", "Body", receive_id="user")
        is False
    )
    assert await feishu.send_feishu_app_message("Title", "Body") is False
    assert (
        await feishu.send_feishu_app_message("Title", "Body", receive_id="user")
        is False
    )
    assert (
        await feishu.send_feishu_app_message(
            "Title", "Body", "https://app.test", "chat", "chat_id"
        )
        is True
    )

    args = client.post.await_args
    assert args.args == (
        "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
    )
    assert args.kwargs["headers"]["Authorization"] == "Bearer token"
    assert args.kwargs["json"]["receive_id"] == "chat"
    assert "https://app.test" in args.kwargs["json"]["content"]


@pytest.mark.anyio
async def test_notification_routes_to_selected_delivery(monkeypatch):
    webhook = AsyncMock(return_value=True)
    app = AsyncMock(return_value=False)
    monkeypatch.setattr(feishu, "send_feishu_webhook", webhook)
    monkeypatch.setattr(feishu, "send_feishu_app_message", app)
    monkeypatch.setattr(
        feishu,
        "get_feishu_config",
        AsyncMock(side_effect=[config(notification_type="app"), config()]),
    )

    assert await feishu.send_feishu_notification("T", "C", receive_id="user") is False
    assert await feishu.send_feishu_notification("T", "C") is True
    app.assert_awaited_once_with("T", "C", None, "user", "open_id")
    webhook.assert_awaited_once_with("T", "C", None)
