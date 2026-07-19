from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.dingtalk import (
    _generate_sign,
    get_dingtalk_access_token,
    get_dingtalk_config,
    send_dingtalk_app_message,
    send_dingtalk_notification,
    send_dingtalk_webhook,
)


class _Response:
    def __init__(self, payload: dict):
        self.json = MagicMock(return_value=payload)


def _http_client(response: _Response):
    client = MagicMock()
    client.get = AsyncMock(return_value=response)
    client.post = AsyncMock(return_value=response)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=None)
    return client, context


@pytest.mark.asyncio
async def test_get_dingtalk_config_and_signature():
    values = {
        "dingtalk_enabled": True,
        "dingtalk_webhook_url": "https://hooks.dingtalk.test",
        "dingtalk_secret": "secret",
        "dingtalk_app_key": "app-key",
        "dingtalk_app_secret": "app-secret",
        "dingtalk_agent_id": "42",
        "dingtalk_notification_type": "app",
    }
    with patch(
        "app.core.dingtalk.SiteSetting.get_value",
        new=AsyncMock(side_effect=lambda key, default: values.get(key, default)),
    ):
        config = await get_dingtalk_config()

    assert config == {
        "enabled": True,
        "webhook_url": "https://hooks.dingtalk.test",
        "secret": "secret",
        "app_key": "app-key",
        "app_secret": "app-secret",
        "agent_id": "42",
        "notification_type": "app",
    }
    assert _generate_sign("secret", 1) == _generate_sign("secret", 1)
    assert _generate_sign("secret", 1) != _generate_sign("secret", 2)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "config",
    [
        {
            "enabled": False,
            "webhook_url": "https://hooks.dingtalk.test",
            "secret": "",
        },
        {"enabled": True, "webhook_url": "", "secret": ""},
    ],
)
async def test_dingtalk_webhook_skips_disabled_or_unconfigured_channels(config):
    with patch(
        "app.core.dingtalk.get_dingtalk_config", new=AsyncMock(return_value=config)
    ):
        assert await send_dingtalk_webhook("Title", "Content") is False


@pytest.mark.asyncio
async def test_dingtalk_webhook_signs_and_posts_markdown():
    client, context = _http_client(_Response({"errcode": 0}))
    config = {
        "enabled": True,
        "webhook_url": "https://hooks.dingtalk.test?access_token=value",
        "secret": "secret",
    }
    with (
        patch(
            "app.core.dingtalk.get_dingtalk_config", new=AsyncMock(return_value=config)
        ),
        patch("app.core.dingtalk.time.time", return_value=1.5),
        patch("app.core.dingtalk.httpx.AsyncClient", return_value=context),
    ):
        assert await send_dingtalk_webhook("Title", "Content", "https://app.test/item")

    client.post.assert_awaited_once_with(
        f"{config['webhook_url']}&timestamp=1500&sign={_generate_sign('secret', 1500)}",
        json={
            "msgtype": "markdown",
            "markdown": {
                "title": "Title",
                "text": "### Title\n\nContent\n\n[查看详情](https://app.test/item)",
            },
        },
    )


@pytest.mark.asyncio
async def test_dingtalk_access_token_and_app_delivery_handle_boundaries():
    with patch(
        "app.core.dingtalk.get_dingtalk_config",
        new=AsyncMock(return_value={"app_key": "", "app_secret": ""}),
    ):
        assert await get_dingtalk_access_token() is None

    client, context = _http_client(_Response({"errcode": 0, "access_token": "token"}))
    with (
        patch(
            "app.core.dingtalk.get_dingtalk_config",
            new=AsyncMock(return_value={"app_key": "key", "app_secret": "secret"}),
        ),
        patch("app.core.dingtalk.httpx.AsyncClient", return_value=context),
    ):
        assert await get_dingtalk_access_token() == "token"

    app_config = {"enabled": True, "agent_id": "42"}
    client, context = _http_client(_Response({"errcode": 0}))
    with (
        patch(
            "app.core.dingtalk.get_dingtalk_config",
            new=AsyncMock(return_value=app_config),
        ),
        patch(
            "app.core.dingtalk.get_dingtalk_access_token",
            new=AsyncMock(return_value="token"),
        ),
        patch("app.core.dingtalk.httpx.AsyncClient", return_value=context),
    ):
        assert await send_dingtalk_app_message(["user-1", "user-2"], "Title", "Content")

    client.post.assert_awaited_once_with(
        "https://oapi.dingtalk.com/topapi/message/corpconversation/asyncsend_v2?access_token=token",
        json={
            "agent_id": "42",
            "userid_list": "user-1,user-2",
            "msg": {
                "msgtype": "markdown",
                "markdown": {"title": "Title", "text": "### Title\n\nContent"},
            },
        },
    )


@pytest.mark.asyncio
async def test_dingtalk_notification_routes_app_only_with_recipients():
    app_sender = AsyncMock(return_value=True)
    webhook_sender = AsyncMock(return_value=True)
    with (
        patch(
            "app.core.dingtalk.get_dingtalk_config",
            new=AsyncMock(return_value={"notification_type": "app"}),
        ),
        patch("app.core.dingtalk.send_dingtalk_app_message", app_sender),
        patch("app.core.dingtalk.send_dingtalk_webhook", webhook_sender),
    ):
        assert await send_dingtalk_notification(
            "Title", "Content", user_id_list=["user-1"]
        )
        assert await send_dingtalk_notification("Title", "Content")

    app_sender.assert_awaited_once_with(["user-1"], "Title", "Content", None)
    webhook_sender.assert_awaited_once_with("Title", "Content", None)
