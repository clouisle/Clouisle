from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.wechat import (
    get_wechat_access_token,
    get_wechat_config,
    send_wechat_app_message,
    send_wechat_notification,
    send_wechat_webhook,
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
async def test_get_wechat_config_reads_site_settings():
    values = {
        "wechat_enabled": True,
        "wechat_notification_type": "app",
        "wechat_webhook_url": "https://hooks.wechat.test",
        "wechat_corp_id": "corp-id",
        "wechat_agent_id": "42",
        "wechat_secret": "secret",
    }

    with patch(
        "app.core.wechat.SiteSetting.get_value",
        new=AsyncMock(side_effect=lambda key, default: values.get(key, default)),
    ):
        assert await get_wechat_config() == {
            "enabled": True,
            "notification_type": "app",
            "webhook_url": "https://hooks.wechat.test",
            "corp_id": "corp-id",
            "agent_id": "42",
            "secret": "secret",
        }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "config",
    [
        {"enabled": False, "webhook_url": "https://hooks.wechat.test"},
        {"enabled": True, "webhook_url": ""},
    ],
)
async def test_wechat_webhook_skips_disabled_or_unconfigured_channels(config):
    with patch("app.core.wechat.get_wechat_config", new=AsyncMock(return_value=config)):
        assert await send_wechat_webhook("Title", "Content") is False


@pytest.mark.asyncio
async def test_wechat_webhook_posts_markdown_and_handles_errors():
    client, context = _http_client(_Response({"errcode": 0}))
    config = {"enabled": True, "webhook_url": "https://hooks.wechat.test"}

    with (
        patch("app.core.wechat.get_wechat_config", new=AsyncMock(return_value=config)),
        patch("app.core.wechat.httpx.AsyncClient", return_value=context),
    ):
        assert await send_wechat_webhook("Title", "Content", "https://app.test/item")

    client.post.assert_awaited_once_with(
        "https://hooks.wechat.test",
        json={
            "msgtype": "markdown",
            "markdown": {
                "content": "### Title\n\nContent\n\n[查看详情](https://app.test/item)"
            },
        },
    )

    failed_client, failed_context = _http_client(_Response({"errcode": 1}))
    with (
        patch("app.core.wechat.get_wechat_config", new=AsyncMock(return_value=config)),
        patch("app.core.wechat.httpx.AsyncClient", return_value=failed_context),
    ):
        assert await send_wechat_webhook("Title", "Content") is False
    failed_client.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_wechat_access_token_validates_credentials_and_response():
    with patch(
        "app.core.wechat.get_wechat_config",
        new=AsyncMock(return_value={"corp_id": "", "secret": ""}),
    ):
        assert await get_wechat_access_token() is None

    client, context = _http_client(_Response({"errcode": 0, "access_token": "token"}))
    config = {"corp_id": "corp-id", "secret": "secret"}
    with (
        patch("app.core.wechat.get_wechat_config", new=AsyncMock(return_value=config)),
        patch("app.core.wechat.httpx.AsyncClient", return_value=context),
    ):
        assert await get_wechat_access_token() == "token"
    client.get.assert_awaited_once_with(
        "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
        params={"corpid": "corp-id", "corpsecret": "secret"},
    )


@pytest.mark.asyncio
async def test_wechat_app_delivery_and_notification_routing():
    config = {"enabled": True, "agent_id": "42"}
    client, context = _http_client(_Response({"errcode": 0}))
    with (
        patch("app.core.wechat.get_wechat_config", new=AsyncMock(return_value=config)),
        patch(
            "app.core.wechat.get_wechat_access_token",
            new=AsyncMock(return_value="token"),
        ),
        patch("app.core.wechat.httpx.AsyncClient", return_value=context),
    ):
        assert await send_wechat_app_message("Title", "Content", to_user="user-1")
    client.post.assert_awaited_once_with(
        "https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token=token",
        json={
            "touser": "user-1",
            "msgtype": "markdown",
            "agentid": 42,
            "markdown": {"content": "### Title\n\nContent"},
        },
    )

    app_sender = AsyncMock(return_value=True)
    webhook_sender = AsyncMock(return_value=True)
    with (
        patch(
            "app.core.wechat.get_wechat_config",
            new=AsyncMock(return_value={"notification_type": "app"}),
        ),
        patch("app.core.wechat.send_wechat_app_message", app_sender),
        patch("app.core.wechat.send_wechat_webhook", webhook_sender),
    ):
        assert await send_wechat_notification("Title", "Content", to_user="user-1")
    app_sender.assert_awaited_once_with("Title", "Content", None, "user-1")
    webhook_sender.assert_not_awaited()
