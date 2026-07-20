from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core import webhook


class AsyncClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.get = AsyncMock(side_effect=self._respond)
        self.request = AsyncMock(side_effect=self._respond)

    def _respond(self, *_args, **_kwargs):
        if self.error:
            raise self.error
        return self.response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


def config(**overrides):
    return {
        "enabled": True,
        "url": "https://hooks.example/notify",
        "method": "POST",
        "headers": {},
        "body_template": '{"title": "{{ title }}", "content": "{{content}}", "link": "{{link_url}}"}',
        "secret": "",
        **overrides,
    }


def install(monkeypatch, settings, client):
    monkeypatch.setattr(webhook, "get_webhook_config", AsyncMock(return_value=settings))
    monkeypatch.setattr(webhook.httpx, "AsyncClient", lambda **_kwargs: client)


@pytest.mark.asyncio
async def test_get_webhook_config_reads_all_settings(monkeypatch):
    get_value = AsyncMock(side_effect=[True, "url", "put", {"X": "1"}, "body", "key"])
    monkeypatch.setattr(webhook.SiteSetting, "get_value", get_value)

    assert await webhook.get_webhook_config() == {
        "enabled": True,
        "url": "url",
        "method": "put",
        "headers": {"X": "1"},
        "body_template": "body",
        "secret": "key",
    }
    assert get_value.await_count == 6


def test_template_rendering_and_signature_cover_value_boundaries():
    rendered = webhook._render_template(
        "{{text}}|{{ number }}|{{missing}}|{{none}}",
        {"text": 'quote"\n', "number": 0, "none": None},
    )

    assert rendered == 'quote\\"\\n|0|{{missing}}|'
    assert webhook._generate_signature("secret", "payload") == (
        "b82fcb791acec57859b989b430a826488ce2e479fdf92326bd0a2e8375a42ba4"
    )


@pytest.mark.parametrize(
    "settings",
    [config(enabled=False), config(url="")],
)
@pytest.mark.asyncio
async def test_skips_disabled_or_unconfigured_webhook(monkeypatch, settings):
    client = AsyncClient()
    install(monkeypatch, settings, client)

    assert await webhook.send_webhook_notification("title", "body") is False
    client.get.assert_not_awaited()
    client.request.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_sends_variables_and_accepts_lower_success_boundary(monkeypatch):
    response = SimpleNamespace(status_code=200, text="ok")
    client = AsyncClient(response)
    settings = config(method="get", headers={"Authorization": "token"})
    install(monkeypatch, settings, client)

    assert await webhook.send_webhook_notification("title", "body", None) is True
    client.get.assert_awaited_once_with(
        settings["url"],
        params={"title": "title", "content": "body", "link_url": ""},
        headers={"Authorization": "token"},
    )


@pytest.mark.asyncio
async def test_json_request_adds_signatures_and_accepts_upper_success_boundary(
    monkeypatch,
):
    response = SimpleNamespace(status_code=299, text="ok")
    client = AsyncClient(response)
    settings = config(secret="secret", headers={"X-Custom": "value"})
    install(monkeypatch, settings, client)

    assert await webhook.send_webhook_notification("title", "body", "/item/1") is True

    body = {"title": "title", "content": "body", "link": "/item/1"}
    body_str = '{"title": "title", "content": "body", "link": "/item/1"}'
    signature = webhook._generate_signature("secret", body_str)
    client.request.assert_awaited_once_with(
        "POST",
        settings["url"],
        json=body,
        headers={
            "X-Custom": "value",
            "X-Webhook-Signature": f"sha256={signature}",
            "X-Webhook-Signature-256": signature,
        },
    )


@pytest.mark.asyncio
async def test_text_request_sets_content_type_and_rejects_status_300(monkeypatch):
    response = SimpleNamespace(status_code=300, text="redirect")
    client = AsyncClient(response)
    settings = config(method="patch", body_template="Title: {{title}}")
    install(monkeypatch, settings, client)

    assert await webhook.send_webhook_notification("notice", "body") is False
    client.request.assert_awaited_once_with(
        "PATCH",
        settings["url"],
        content="Title: notice",
        headers={"Content-Type": "text/plain"},
    )


@pytest.mark.asyncio
async def test_request_errors_return_false(monkeypatch):
    client = AsyncClient(error=RuntimeError("network down"))
    install(monkeypatch, config(), client)

    assert await webhook.send_webhook_notification("title", "body") is False
