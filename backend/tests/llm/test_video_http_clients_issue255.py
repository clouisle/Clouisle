from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from app.llm.adapters import kling_client, luma_client, pika_client, siliconflow_client
from app.llm.errors import (
    AuthenticationError,
    InvalidRequestError,
    ProviderError,
    RateLimitError,
    TaskNotFoundError,
)

CLIENTS = [
    (kling_client, kling_client.KlingClient, "https://api.test/v1"),
    (luma_client, luma_client.LumaClient, "https://api.test/v1"),
    (pika_client, pika_client.PikaClient, "https://api.test/v1"),
    (siliconflow_client, siliconflow_client.SiliconFlowClient, "https://api.test/v1"),
]


def model(base_url="https://api.test/v1"):
    return SimpleNamespace(
        model_id="video-model",
        api_key="secret",
        base_url=base_url,
        config={"timeout": 12},
    )


def mock_transport(monkeypatch, module, result):
    request = AsyncMock(side_effect=result if isinstance(result, Exception) else None)
    if not isinstance(result, Exception):
        request.return_value = result

    class Transport:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    transport = Transport()
    transport.request = request
    factory = Mock(return_value=transport)
    monkeypatch.setattr(module.httpx, "AsyncClient", factory)
    return factory, request


@pytest.mark.asyncio
@pytest.mark.parametrize(("module", "client_type", "base_url"), CLIENTS)
async def test_request_sends_payload_and_returns_json(
    monkeypatch, module, client_type, base_url
):
    response = Mock(status_code=200)
    response.json.return_value = {"id": "task-1"}
    factory, request = mock_transport(monkeypatch, module, response)
    client = client_type(model(base_url))

    result = await client._request("POST", "/v1/jobs", json={"prompt": "ocean"})

    assert result == {"id": "task-1"}
    factory.assert_called_once_with(timeout=12)
    request.assert_awaited_once_with(
        "POST",
        "https://api.test/v1/jobs",
        json={"prompt": "ocean"},
        headers={"Authorization": "Bearer secret", "Content-Type": "application/json"},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(("module", "client_type", "base_url"), CLIENTS)
@pytest.mark.parametrize(
    ("transport_error", "message"),
    [
        (httpx.TimeoutException("slow"), "timeout"),
        (httpx.RequestError("offline"), "request failed"),
    ],
)
async def test_request_maps_transport_errors(
    monkeypatch, module, client_type, base_url, transport_error, message
):
    mock_transport(monkeypatch, module, transport_error)

    with pytest.raises(ProviderError, match=message):
        await client_type(model(base_url))._request("POST", "/jobs")


@pytest.mark.asyncio
@pytest.mark.parametrize(("module", "client_type", "base_url"), CLIENTS)
@pytest.mark.parametrize(
    ("status", "error_type"),
    [
        (401, AuthenticationError),
        (404, InvalidRequestError),
        (429, RateLimitError),
    ],
)
async def test_request_validates_provider_statuses(
    monkeypatch, module, client_type, base_url, status, error_type
):
    response = Mock(status_code=status, text="rejected")
    mock_transport(monkeypatch, module, response)

    with pytest.raises(error_type):
        await client_type(model(base_url))._request("POST", "/jobs")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("module", "client_type"),
    [
        (kling_client, kling_client.KlingClient),
        (luma_client, luma_client.LumaClient),
        (pika_client, pika_client.PikaClient),
    ],
)
async def test_get_404_identifies_missing_task(monkeypatch, module, client_type):
    response = Mock(status_code=404, text="missing")
    mock_transport(monkeypatch, module, response)

    with pytest.raises(TaskNotFoundError) as exc_info:
        await client_type(model())._request("GET", "/jobs/task-1")

    assert exc_info.value.task_id == "task-1"


@pytest.mark.asyncio
@pytest.mark.parametrize(("module", "client_type", "base_url"), CLIENTS)
async def test_request_preserves_provider_error_message(
    monkeypatch, module, client_type, base_url
):
    response = Mock(status_code=503, text="fallback")
    response.json.return_value = {"message": "provider unavailable"}
    mock_transport(monkeypatch, module, response)

    with pytest.raises(ProviderError, match="provider unavailable") as exc_info:
        await client_type(model(base_url))._request("POST", "/jobs")

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_client_helpers_send_provider_specific_payloads():
    kling = kling_client.KlingClient(model())
    kling._request = AsyncMock(return_value={"task_id": "k-1"})
    luma = luma_client.LumaClient(model())
    luma._request = AsyncMock(return_value={"id": "l-1"})
    pika = pika_client.PikaClient(model())
    pika._request = AsyncMock(return_value={"id": "p-1"})
    siliconflow = siliconflow_client.SiliconFlowClient(model())
    siliconflow._request = AsyncMock(return_value={"requestId": "s-1"})

    assert await kling.create_task("/v1/videos/text2video", {"prompt": "x"}) == {
        "task_id": "k-1"
    }
    await kling.get_task("k-1", task_type="image2video")
    assert await luma.create_generation("/generations", {"prompt": "x"}) == {
        "id": "l-1"
    }
    await luma.get_generation("l-1")
    assert await pika.create_generation("/generate", {"prompt": "x"}) == {"id": "p-1"}
    await pika.get_generation("p-1")
    assert await siliconflow.create_task({"prompt": "x"}) == {"requestId": "s-1"}
    await siliconflow.get_task("s-1")

    kling._request.assert_any_await("GET", "/v1/videos/image2video/k-1")
    luma._request.assert_any_await("GET", "/generations/l-1")
    pika._request.assert_any_await("GET", "/generate/p-1")
    siliconflow._request.assert_any_await(
        "POST", "/video/status", json={"requestId": "s-1"}
    )
