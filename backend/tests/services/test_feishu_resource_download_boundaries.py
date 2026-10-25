from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import httpx
import pytest

from app.integrations.feishu import FeishuAPIError, FeishuClient
from app.schemas.response import BusinessError


@pytest.fixture
def client(monkeypatch):
    instance = FeishuClient.__new__(FeishuClient)
    instance.app_id, instance.app_secret = "app", "secret"
    monkeypatch.setattr(instance, "_token", AsyncMock(return_value="token"))
    return instance


def transport_for(monkeypatch, client, status, content, headers=None):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(status, content=content, headers=headers)

    @asynccontextmanager
    async def transport():
        async with httpx.AsyncClient(
            base_url="https://open.feishu.cn/open-apis",
            transport=httpx.MockTransport(handle),
        ) as session:
            yield session

    monkeypatch.setattr(client, "_transport", transport)
    return requests


@pytest.mark.asyncio
async def test_download_preserves_original_bytes_mime_and_authorization(
    monkeypatch, client
):
    raw = b"\x89PNG\r\n\x1a\noriginal-image"
    requests = transport_for(
        monkeypatch, client, 200, raw, {"content-type": "image/png; charset=binary"}
    )
    result = await client.download_message_resource(
        "message/id", "resource/key", kind="image", max_bytes=len(raw)
    )
    assert result == (raw, "", "image/png")
    assert requests[0].headers["authorization"] == "Bearer token"
    assert requests[0].url.params["type"] == "image"
    assert "message%2Fid" in requests[0].url.raw_path.decode()


@pytest.mark.asyncio
async def test_download_defaults_unknown_mime_and_accepts_empty_resource(
    monkeypatch, client
):
    transport_for(monkeypatch, client, 200, b"")
    assert await client.download_message_resource(
        "message", "key", kind="file", max_bytes=1
    ) == (b"", "", "application/octet-stream")


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [302, 401, 500])
async def test_download_never_returns_redirect_or_error_body_as_file(
    monkeypatch, client, status
):
    transport_for(
        monkeypatch,
        client,
        status,
        b'{"code":401,"msg":"denied"}',
        {"location": "https://outside.test/file"},
    )
    with pytest.raises(FeishuAPIError):
        await client.download_message_resource(
            "message", "key", kind="file", max_bytes=100
        )


@pytest.mark.asyncio
async def test_download_rejects_bytes_beyond_limit(monkeypatch, client):
    transport_for(monkeypatch, client, 200, b"oversized")
    with pytest.raises(BusinessError):
        await client.download_message_resource(
            "message", "key", kind="file", max_bytes=2
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,limit", [("video", 10), ("file", 0)])
async def test_invalid_download_parameters_fail_before_network(client, kind, limit):
    with pytest.raises(ValueError):
        await client.download_message_resource(
            "message", "key", kind=kind, max_bytes=limit
        )
    client._token.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,kwargs",
    [
        ("upload_image", {"filename": "", "content_type": "image/png"}),
        ("upload_file", {"filename": "file", "content_type": ""}),
        ("reply_markdown", {"text": "", "uuid": "id"}),
    ],
)
async def test_invalid_upload_or_reply_metadata_never_reaches_network(
    client, method, kwargs
):
    with pytest.raises(ValueError):
        await getattr(client, method)(
            b"image" if method.startswith("upload") else "message", **kwargs
        )
    client._token.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_file_rejects_missing_provider_key(monkeypatch, client):
    transport_for(monkeypatch, client, 200, b'{"code":0,"data":{}}')
    with pytest.raises(FeishuAPIError):
        await client.upload_file(
            b"file", filename="report.txt", content_type="text/plain"
        )
