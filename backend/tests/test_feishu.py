from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.feishu import (
    _generate_sign,
    get_feishu_config,
    get_feishu_tenant_access_token,
    send_feishu_app_message,
    send_feishu_notification,
    send_feishu_webhook,
)


class _Response:
    def __init__(self, payload: dict):
        self.json = MagicMock(return_value=payload)


def _http_client(response: _Response):
    client = MagicMock()
    client.post = AsyncMock(return_value=response)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=None)
    return client, context


@pytest.mark.asyncio
async def test_get_feishu_config_and_signature():
    values = {
        "feishu_enabled": True,
        "feishu_notification_type": "app",
        "feishu_webhook_url": "https://hooks.feishu.test",
        "feishu_secret": "secret",
        "feishu_app_id": "app-id",
        "feishu_app_secret": "app-secret",
    }
    with patch(
        "app.core.feishu.SiteSetting.get_value",
        new=AsyncMock(side_effect=lambda key, default: values.get(key, default)),
    ):
        assert await get_feishu_config() == {
            "enabled": True,
            "notification_type": "app",
            "webhook_url": "https://hooks.feishu.test",
            "secret": "secret",
            "app_id": "app-id",
            "app_secret": "app-secret",
        }

    assert _generate_sign("secret", 1) == _generate_sign("secret", 1)
    assert _generate_sign("secret", 1) != _generate_sign("secret", 2)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "config",
    [
        {"enabled": False, "webhook_url": "https://hooks.feishu.test"},
        {"enabled": True, "webhook_url": ""},
    ],
)
async def test_feishu_webhook_skips_disabled_or_unconfigured_channels(config):
    with patch("app.core.feishu.get_feishu_config", new=AsyncMock(return_value=config)):
        assert await send_feishu_webhook("Title", "Content") is False


@pytest.mark.asyncio
async def test_feishu_webhook_posts_signed_card_with_link():
    client, context = _http_client(_Response({"code": 0}))
    config = {
        "enabled": True,
        "webhook_url": "https://hooks.feishu.test",
        "secret": "secret",
    }
    with (
        patch("app.core.feishu.get_feishu_config", new=AsyncMock(return_value=config)),
        patch("app.core.feishu.time.time", return_value=1500),
        patch("app.core.feishu.httpx.AsyncClient", return_value=context),
    ):
        assert await send_feishu_webhook("Title", "Content", "https://app.test/item")

    client.post.assert_awaited_once_with(
        "https://hooks.feishu.test",
        json={
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": "Title"},
                    "template": "blue",
                },
                "elements": [
                    {"tag": "markdown", "content": "Content"},
                    {
                        "tag": "action",
                        "actions": [
                            {
                                "tag": "button",
                                "text": {"tag": "plain_text", "content": "查看详情"},
                                "type": "primary",
                                "url": "https://app.test/item",
                            }
                        ],
                    },
                ],
            },
            "timestamp": "1500",
            "sign": _generate_sign("secret", 1500),
        },
    )


@pytest.mark.asyncio
async def test_feishu_tenant_token_and_app_delivery_handle_boundaries():
    with patch(
        "app.core.feishu.get_feishu_config",
        new=AsyncMock(return_value={"app_id": "", "app_secret": ""}),
    ):
        assert await get_feishu_tenant_access_token() is None

    client, context = _http_client(
        _Response({"code": 0, "tenant_access_token": "token"})
    )
    with (
        patch(
            "app.core.feishu.get_feishu_config",
            new=AsyncMock(
                return_value={"app_id": "app-id", "app_secret": "app-secret"}
            ),
        ),
        patch("app.core.feishu.httpx.AsyncClient", return_value=context),
    ):
        assert await get_feishu_tenant_access_token() == "token"

    config = {"enabled": True}
    client, context = _http_client(_Response({"code": 0}))
    with (
        patch("app.core.feishu.get_feishu_config", new=AsyncMock(return_value=config)),
        patch(
            "app.core.feishu.get_feishu_tenant_access_token",
            new=AsyncMock(return_value="token"),
        ),
        patch("app.core.feishu.httpx.AsyncClient", return_value=context),
    ):
        assert await send_feishu_app_message("Title", "Content", receive_id="user-1")

    client.post.assert_awaited_once_with(
        "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
        json={
            "receive_id": "user-1",
            "msg_type": "interactive",
            "content": str(
                {
                    "card": {
                        "header": {
                            "title": {"tag": "plain_text", "content": "Title"},
                            "template": "blue",
                        },
                        "elements": [{"tag": "markdown", "content": "Content"}],
                    }
                }
            ),
        },
        headers={"Authorization": "Bearer token", "Content-Type": "application/json"},
    )


@pytest.mark.asyncio
async def test_feishu_notification_routes_app_only_with_recipient():
    app_sender = AsyncMock(return_value=True)
    webhook_sender = AsyncMock(return_value=True)
    with (
        patch(
            "app.core.feishu.get_feishu_config",
            new=AsyncMock(return_value={"notification_type": "app"}),
        ),
        patch("app.core.feishu.send_feishu_app_message", app_sender),
        patch("app.core.feishu.send_feishu_webhook", webhook_sender),
    ):
        assert await send_feishu_notification("Title", "Content", receive_id="user-1")
        assert await send_feishu_notification("Title", "Content")

    app_sender.assert_awaited_once_with("Title", "Content", None, "user-1", "open_id")
    webhook_sender.assert_awaited_once_with("Title", "Content", None)
