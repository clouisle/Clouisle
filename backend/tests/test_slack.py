from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.slack import get_slack_config, send_slack_notification


class _Response:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text


def _http_client(response: _Response):
    client = MagicMock()
    client.post = AsyncMock(return_value=response)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=None)
    return client, context


@pytest.mark.asyncio
async def test_get_slack_config_reads_site_settings():
    values = {"slack_enabled": True, "slack_webhook_url": "https://hooks.slack.test"}

    with patch(
        "app.core.slack.SiteSetting.get_value",
        new=AsyncMock(side_effect=lambda key, default: values.get(key, default)),
    ):
        assert await get_slack_config() == {
            "enabled": True,
            "webhook_url": "https://hooks.slack.test",
        }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "config",
    [
        {"enabled": False, "webhook_url": "https://hooks.slack.test"},
        {"enabled": True, "webhook_url": ""},
    ],
)
async def test_send_slack_skips_disabled_or_unconfigured_channels(config):
    with patch("app.core.slack.get_slack_config", new=AsyncMock(return_value=config)):
        assert await send_slack_notification("Title", "Content") is False


@pytest.mark.asyncio
async def test_send_slack_posts_blocks_with_optional_link():
    client, context = _http_client(_Response(200, "ok"))

    with (
        patch(
            "app.core.slack.get_slack_config",
            new=AsyncMock(
                return_value={
                    "enabled": True,
                    "webhook_url": "https://hooks.slack.test",
                }
            ),
        ),
        patch("app.core.slack.httpx.AsyncClient", return_value=context),
    ):
        assert await send_slack_notification(
            "Title", "Content", "https://app.test/item"
        )

    client.post.assert_awaited_once_with(
        "https://hooks.slack.test",
        json={
            "text": "Title",
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": "Title", "emoji": True},
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "Content"},
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "View Details",
                                "emoji": True,
                            },
                            "url": "https://app.test/item",
                            "style": "primary",
                        }
                    ],
                },
            ],
        },
    )


@pytest.mark.asyncio
async def test_send_slack_rejects_failed_responses_and_network_errors():
    client, context = _http_client(_Response(200, "invalid_payload"))
    config = {"enabled": True, "webhook_url": "https://hooks.slack.test"}

    with (
        patch("app.core.slack.get_slack_config", new=AsyncMock(return_value=config)),
        patch("app.core.slack.httpx.AsyncClient", return_value=context),
    ):
        assert await send_slack_notification("Title", "Content") is False

    failed_context = MagicMock()
    failed_context.__aenter__ = AsyncMock(side_effect=RuntimeError("network down"))
    with (
        patch("app.core.slack.get_slack_config", new=AsyncMock(return_value=config)),
        patch("app.core.slack.httpx.AsyncClient", return_value=failed_context),
    ):
        assert await send_slack_notification("Title", "Content") is False
