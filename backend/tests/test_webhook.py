from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core import webhook


class FakeAsyncClient:
    def __init__(self, response):
        self.response = response
        self.get = AsyncMock(return_value=response)
        self.request = AsyncMock(return_value=response)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def test_render_template_replaces_spaced_placeholders_and_generates_signature():
    rendered = webhook._render_template(
        '{"title": "{{ title }}", "content": "{{content}}", "link": "{{link_url}}"}',
        {"title": "Alert", "content": None, "link_url": ""},
    )

    assert rendered == '{"title": "Alert", "content": "", "link": ""}'
    assert (
        webhook._generate_signature("secret", rendered)
        == "4f3cd005dcddbc1276ccace7606e9fd173534c35d708cd6af05f4ab5ded7bf9b"
    )


@pytest.mark.asyncio
async def test_send_webhook_notification_posts_json_with_signature(monkeypatch):
    config = {
        "enabled": True,
        "url": "https://example.test/webhook",
        "method": "POST",
        "headers": {"X-Custom": "value"},
        "body_template": '{"title": "{{title}}", "content": "{{content}}"}',
        "secret": "secret",
    }
    client = FakeAsyncClient(SimpleNamespace(status_code=201, text="created"))
    monkeypatch.setattr(webhook, "get_webhook_config", AsyncMock(return_value=config))
    monkeypatch.setattr(webhook.httpx, "AsyncClient", lambda timeout: client)

    assert await webhook.send_webhook_notification("Alert", "Details") is True

    client.request.assert_awaited_once_with(
        "POST",
        "https://example.test/webhook",
        json={"title": "Alert", "content": "Details"},
        headers={
            "X-Custom": "value",
            "X-Webhook-Signature": "sha256=2c7622d11fd3f7068dc5f42b531a1fbd86f36dfbce2094534a0d5819e9fef460",
            "X-Webhook-Signature-256": "2c7622d11fd3f7068dc5f42b531a1fbd86f36dfbce2094534a0d5819e9fef460",
        },
    )


@pytest.mark.asyncio
async def test_send_webhook_notification_returns_false_for_error_response(monkeypatch):
    client = FakeAsyncClient(SimpleNamespace(status_code=503, text="unavailable"))
    monkeypatch.setattr(
        webhook,
        "get_webhook_config",
        AsyncMock(
            return_value={
                "enabled": True,
                "url": "https://example.test/webhook",
                "method": "GET",
                "headers": {},
                "body_template": "ignored",
                "secret": "",
            }
        ),
    )
    monkeypatch.setattr(webhook.httpx, "AsyncClient", lambda timeout: client)

    assert (
        await webhook.send_webhook_notification("Alert", "Details", "/detail") is False
    )
    client.get.assert_awaited_once_with(
        "https://example.test/webhook",
        params={"title": "Alert", "content": "Details", "link_url": "/detail"},
        headers={},
    )
