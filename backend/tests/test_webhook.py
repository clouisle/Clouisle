from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.webhook import (
    _generate_signature,
    _render_template,
    get_webhook_config,
    send_webhook_notification,
)


class _Response:
    def __init__(self, status_code: int, text: str = "error"):
        self.status_code = status_code
        self.text = text


def _http_client(response: _Response):
    client = MagicMock()
    client.get = AsyncMock(return_value=response)
    client.request = AsyncMock(return_value=response)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=None)
    return client, context


@pytest.mark.asyncio
async def test_get_webhook_config_reads_all_settings():
    values = {
        "webhook_enabled": True,
        "webhook_url": "https://hooks.example.com",
        "webhook_method": "PUT",
        "webhook_headers": {"X-Test": "yes"},
        "webhook_body_template": "body",
        "webhook_secret": "secret",
    }

    with patch(
        "app.core.webhook.SiteSetting.get_value",
        new=AsyncMock(side_effect=lambda key, default: values.get(key, default)),
    ):
        config = await get_webhook_config()

    assert config == {
        "enabled": True,
        "url": "https://hooks.example.com",
        "method": "PUT",
        "headers": {"X-Test": "yes"},
        "body_template": "body",
        "secret": "secret",
    }


def test_template_escapes_strings_and_replaces_whitespace_placeholders():
    assert (
        _render_template(
            '{"title":"{{ title }}","count":"{{count}}","empty":"{{missing}}"}',
            {"title": 'A "quote"', "count": 3},
        )
        == '{"title":"A \\"quote\\"","count":"3","empty":"{{missing}}"}'
    )


def test_signature_is_hmac_sha256_hex_digest():
    assert (
        _generate_signature("secret", "payload")
        == "b82fcb791acec57859b989b430a826488ce2e479fdf92326bd0a2e8375a42ba4"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "config",
    [
        {"enabled": False, "url": "https://hooks.example.com"},
        {"enabled": True, "url": ""},
    ],
)
async def test_send_skips_disabled_or_unconfigured_webhooks(config):
    with patch(
        "app.core.webhook.get_webhook_config", new=AsyncMock(return_value=config)
    ):
        assert await send_webhook_notification("title", "content") is False


@pytest.mark.asyncio
async def test_send_json_request_adds_signature_and_returns_success():
    client, context = _http_client(_Response(201))
    config = {
        "enabled": True,
        "url": "https://hooks.example.com",
        "method": "post",
        "headers": {"X-Test": "yes"},
        "body_template": '{"title":"{{title}}","content":"{{content}}","link":"{{link_url}}"}',
        "secret": "secret",
    }

    with (
        patch(
            "app.core.webhook.get_webhook_config", new=AsyncMock(return_value=config)
        ),
        patch("app.core.webhook.httpx.AsyncClient", return_value=context),
    ):
        assert await send_webhook_notification(
            'A "title"', "content", "https://example.com"
        )

    body = '{"title":"A \\"title\\"","content":"content","link":"https://example.com"}'
    client.request.assert_awaited_once_with(
        "POST",
        "https://hooks.example.com",
        json={
            "title": 'A "title"',
            "content": "content",
            "link": "https://example.com",
        },
        headers={
            "X-Test": "yes",
            "X-Webhook-Signature": f"sha256={_generate_signature('secret', body)}",
            "X-Webhook-Signature-256": _generate_signature("secret", body),
        },
    )


@pytest.mark.asyncio
async def test_send_get_uses_template_variables_as_query_parameters():
    client, context = _http_client(_Response(200))
    config = {
        "enabled": True,
        "url": "https://hooks.example.com",
        "method": "GET",
        "headers": None,
        "body_template": "ignored",
        "secret": "",
    }

    with (
        patch(
            "app.core.webhook.get_webhook_config", new=AsyncMock(return_value=config)
        ),
        patch("app.core.webhook.httpx.AsyncClient", return_value=context),
    ):
        assert await send_webhook_notification("title", "content")

    client.get.assert_awaited_once_with(
        "https://hooks.example.com",
        params={"title": "title", "content": "content", "link_url": ""},
        headers={},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status_code,expected", [(199, False), (200, True), (299, True), (300, False)]
)
async def test_send_treats_only_2xx_responses_as_success(status_code, expected):
    client, context = _http_client(_Response(status_code))
    config = {
        "enabled": True,
        "url": "https://hooks.example.com",
        "method": "PATCH",
        "headers": {},
        "body_template": "plain text",
        "secret": "",
    }

    with (
        patch(
            "app.core.webhook.get_webhook_config", new=AsyncMock(return_value=config)
        ),
        patch("app.core.webhook.httpx.AsyncClient", return_value=context),
    ):
        assert await send_webhook_notification("title", "content") is expected

    client.request.assert_awaited_once_with(
        "PATCH",
        "https://hooks.example.com",
        content="plain text",
        headers={"Content-Type": "text/plain"},
    )


@pytest.mark.asyncio
async def test_send_returns_false_when_http_client_raises():
    context = MagicMock()
    context.__aenter__ = AsyncMock(side_effect=RuntimeError("network down"))
    config = {
        "enabled": True,
        "url": "https://hooks.example.com",
        "method": "POST",
        "headers": {},
        "body_template": "{}",
        "secret": "",
    }

    with (
        patch(
            "app.core.webhook.get_webhook_config", new=AsyncMock(return_value=config)
        ),
        patch("app.core.webhook.httpx.AsyncClient", return_value=context),
    ):
        assert await send_webhook_notification("title", "content") is False
