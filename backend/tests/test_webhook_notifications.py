"""Behavioral coverage for generic webhook notifications."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core import webhook


@pytest.mark.anyio
@pytest.mark.parametrize(
    "config",
    [
        {"enabled": False, "url": "https://hooks.example.test"},
        {"enabled": True, "url": ""},
    ],
)
async def test_send_webhook_skips_disabled_or_unconfigured_webhooks(
    monkeypatch, config
):
    monkeypatch.setattr(webhook, "get_webhook_config", AsyncMock(return_value=config))

    assert await webhook.send_webhook_notification("Title", "Content") is False


@pytest.mark.anyio
async def test_send_webhook_posts_rendered_json_with_signature(monkeypatch):
    request = AsyncMock(return_value=SimpleNamespace(status_code=201, text="created"))

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

    client = Client()
    client.request = request

    monkeypatch.setattr(
        webhook,
        "get_webhook_config",
        AsyncMock(
            return_value={
                "enabled": True,
                "url": "https://hooks.example.test/events",
                "method": "PATCH",
                "headers": {"X-Source": "clouisle"},
                "body_template": '{"title":"{{ title }}","content":"{{content}}"}',
                "secret": "secret",
            }
        ),
    )
    monkeypatch.setattr(webhook.httpx, "AsyncClient", lambda **kwargs: client)

    assert await webhook.send_webhook_notification('A "title"', "Content") is True

    payload = '{"title":"A \\"title\\"","content":"Content"}'
    request.assert_awaited_once_with(
        "PATCH",
        "https://hooks.example.test/events",
        json={"title": 'A "title"', "content": "Content"},
        headers={
            "X-Source": "clouisle",
            "X-Webhook-Signature": f"sha256={webhook._generate_signature('secret', payload)}",
            "X-Webhook-Signature-256": webhook._generate_signature("secret", payload),
        },
    )


@pytest.mark.anyio
async def test_send_webhook_uses_get_parameters_and_reports_non_success(monkeypatch):
    get = AsyncMock(return_value=SimpleNamespace(status_code=503, text="unavailable"))

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

    client = Client()
    client.get = get

    monkeypatch.setattr(
        webhook,
        "get_webhook_config",
        AsyncMock(
            return_value={
                "enabled": True,
                "url": "https://hooks.example.test/events",
                "method": "GET",
                "headers": {},
                "body_template": "unused",
                "secret": "",
            }
        ),
    )
    monkeypatch.setattr(webhook.httpx, "AsyncClient", lambda **kwargs: client)

    assert (
        await webhook.send_webhook_notification("Title", "Content", "https://app.test")
        is False
    )
    get.assert_awaited_once_with(
        "https://hooks.example.test/events",
        params={
            "title": "Title",
            "content": "Content",
            "link_url": "https://app.test",
        },
        headers={},
    )
