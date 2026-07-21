from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from app.llm.adapters import runway_client
from app.llm.errors import (
    AuthenticationError,
    InvalidRequestError,
    ProviderError,
    RateLimitError,
    TaskNotFoundError,
)


def model(base_url="https://api.test/v1", config=None):
    return SimpleNamespace(
        model_id="video-model",
        api_key="fake-runway-key",
        base_url=base_url,
        config=config,
    )


def mock_transport(monkeypatch, result):
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
    monkeypatch.setattr(runway_client.httpx, "AsyncClient", factory)
    return factory, request


def test_configuration_url_and_headers():
    client = runway_client.RunwayClient(
        model(
            base_url="https://api.test/v1/",
            config={
                "runway_api_version": "2025-01-01",
                "timeout": "12",
                "poll_interval_seconds": 0,
                "task_timeout_seconds": 0,
            },
        )
    )

    assert client.timeout == 12
    assert client.poll_interval == 1
    assert client.task_timeout == 5
    assert client._build_url("v1/tasks") == "https://api.test/v1/tasks"
    assert client._build_url("tasks") == "https://api.test/v1/tasks"
    assert client._headers() == {
        "Authorization": "Bearer fake-runway-key",
        "Content-Type": "application/json",
        "X-Runway-Version": "2025-01-01",
    }

    default_client = runway_client.RunwayClient(model(base_url=None))
    assert default_client.base_url == "https://api.dev.runwayml.com"
    assert default_client.api_version == "2024-11-06"
    assert default_client.timeout == 180
    assert default_client.poll_interval == 5
    assert default_client.task_timeout == 300
    assert default_client._build_url("v1/tasks") == (
        "https://api.dev.runwayml.com/v1/tasks"
    )


@pytest.mark.asyncio
async def test_request_and_task_helpers_send_expected_http(monkeypatch):
    response = Mock(status_code=200)
    response.json.return_value = {"id": "task-1"}
    factory, request = mock_transport(monkeypatch, response)
    client = runway_client.RunwayClient(model(config={"timeout": 12}))

    assert await client.create_task("/v1/tasks", {"prompt": "ocean"}) == {
        "id": "task-1"
    }
    factory.assert_called_once_with(timeout=12.0)
    request.assert_awaited_once_with(
        "POST",
        "https://api.test/v1/tasks",
        json={"prompt": "ocean"},
        headers={
            "Authorization": "Bearer fake-runway-key",
            "Content-Type": "application/json",
            "X-Runway-Version": "2024-11-06",
        },
    )

    client._request = AsyncMock(return_value={"status": "RUNNING"})
    assert await client.get_task("task-1") == {"status": "RUNNING"}
    client._request.assert_awaited_once_with("GET", "/v1/tasks/task-1")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("transport_error", "message"),
    [
        (httpx.TimeoutException("slow"), "request timeout"),
        (httpx.RequestError("offline"), "request failed: offline"),
    ],
)
async def test_request_maps_transport_errors(monkeypatch, transport_error, message):
    mock_transport(monkeypatch, transport_error)

    with pytest.raises(ProviderError, match=message):
        await runway_client.RunwayClient(model())._request("POST", "/v1/tasks")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "method", "error_type"),
    [
        (401, "POST", AuthenticationError),
        (404, "GET", TaskNotFoundError),
        (404, "POST", InvalidRequestError),
        (429, "POST", RateLimitError),
    ],
)
async def test_request_maps_known_statuses(monkeypatch, status, method, error_type):
    mock_transport(monkeypatch, Mock(status_code=status))

    with pytest.raises(error_type) as exc_info:
        await runway_client.RunwayClient(model())._request(method, "/v1/tasks/task-1")

    if error_type is TaskNotFoundError:
        assert exc_info.value.task_id == "task-1"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("json_result", "text", "message"),
    [
        ({"message": "provider unavailable"}, "fallback", "provider unavailable"),
        ({"error": "bad payload"}, "fallback", "bad payload"),
        ({}, "plain failure", "plain failure"),
        ({}, "", "Runway API error"),
        (ValueError("invalid json"), "plain failure", "plain failure"),
    ],
)
async def test_request_preserves_provider_error_details(
    monkeypatch, json_result, text, message
):
    response = Mock(status_code=503, text=text)
    if isinstance(json_result, Exception):
        response.json.side_effect = json_result
    else:
        response.json.return_value = json_result
    mock_transport(monkeypatch, response)

    with pytest.raises(ProviderError, match=message) as exc_info:
        await runway_client.RunwayClient(model())._request("POST", "/v1/tasks")

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "terminal_status", ["succeeded", "FAILED", "cancelled", "CANCELED"]
)
async def test_wait_for_task_polls_until_terminal(monkeypatch, terminal_status):
    client = runway_client.RunwayClient(model())
    client.get_task = AsyncMock(
        side_effect=[{"status": "running"}, {"status": terminal_status}]
    )
    sleep = AsyncMock()
    monkeypatch.setattr(runway_client.asyncio, "sleep", sleep)

    assert await client.wait_for_task("task-1") == {"status": terminal_status}
    assert client.get_task.await_count == 2
    sleep.assert_awaited_once_with(5)


@pytest.mark.asyncio
async def test_wait_for_task_times_out(monkeypatch):
    client = runway_client.RunwayClient(model())
    client.poll_interval = 1
    client.task_timeout = 1
    client.get_task = AsyncMock(return_value={})
    sleep = AsyncMock()
    monkeypatch.setattr(runway_client.asyncio, "sleep", sleep)

    with pytest.raises(ProviderError, match="timed out"):
        await client.wait_for_task("task-1")

    assert client.get_task.await_count == 2
    assert sleep.await_count == 2
