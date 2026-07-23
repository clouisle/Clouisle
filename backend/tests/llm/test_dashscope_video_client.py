from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from app.llm.adapters import dashscope_video_client as client_module
from app.llm.adapters.dashscope_video_client import DashScopeVideoClient
from app.llm.errors import (
    AuthenticationError,
    InvalidRequestError,
    ProviderError,
    RateLimitError,
    TaskNotFoundError,
)


def make_client(**config: float) -> DashScopeVideoClient:
    model = SimpleNamespace(
        model_id="wan-video",
        api_key="secret",
        base_url="https://dashscope.example/api/",
        config=config,
    )
    return DashScopeVideoClient(model)


class AsyncClient:
    def __init__(self, response: Mock | None = None, error: Exception | None = None):
        self.request = AsyncMock(return_value=response, side_effect=error)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


@pytest.mark.asyncio
async def test_create_task_sends_async_request(monkeypatch: pytest.MonkeyPatch) -> None:
    response = Mock(status_code=200)
    response.json.return_value = {"output": {"task_id": "task-1"}}
    transport = AsyncClient(response)
    monkeypatch.setattr(client_module.httpx, "AsyncClient", lambda **_kwargs: transport)

    result = await make_client(timeout=12).create_task({"model": "wan-video"})

    assert result == {"output": {"task_id": "task-1"}}
    transport.request.assert_awaited_once_with(
        "POST",
        "https://dashscope.example/api/services/aigc/video-generation/generation",
        json={"model": "wan-video"},
        headers={
            "Authorization": "Bearer secret",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        },
    )


@pytest.mark.parametrize(
    ("status", "method", "expected", "attribute"),
    [
        (401, "POST", AuthenticationError, None),
        (404, "GET", TaskNotFoundError, ("task_id", "task-7")),
        (404, "POST", InvalidRequestError, None),
        (429, "POST", RateLimitError, None),
        (503, "POST", ProviderError, ("status_code", 503)),
    ],
)
@pytest.mark.asyncio
async def test_request_maps_http_errors(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    method: str,
    expected: type[Exception],
    attribute: tuple[str, object] | None,
) -> None:
    response = Mock(status_code=status, text="unavailable")
    response.json.return_value = {"message": "provider message"}
    monkeypatch.setattr(
        client_module.httpx,
        "AsyncClient",
        lambda **_kwargs: AsyncClient(response),
    )

    with pytest.raises(expected) as exc_info:
        await make_client()._request(method, "/tasks/task-7")

    if attribute:
        assert getattr(exc_info.value, attribute[0]) == attribute[1]


@pytest.mark.asyncio
async def test_request_uses_text_for_non_json_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = Mock(status_code=502, text="bad gateway")
    response.json.side_effect = ValueError
    monkeypatch.setattr(
        client_module.httpx,
        "AsyncClient",
        lambda **_kwargs: AsyncClient(response),
    )

    with pytest.raises(ProviderError, match="bad gateway"):
        await make_client()._request("POST", "/generation")


@pytest.mark.parametrize(
    "error",
    [
        httpx.ReadTimeout("slow"),
        httpx.ConnectError("offline"),
    ],
)
@pytest.mark.asyncio
async def test_request_maps_transport_errors(
    monkeypatch: pytest.MonkeyPatch, error: httpx.RequestError
) -> None:
    monkeypatch.setattr(
        client_module.httpx,
        "AsyncClient",
        lambda **_kwargs: AsyncClient(error=error),
    )

    with pytest.raises(ProviderError) as exc_info:
        await make_client().get_task("task-1")

    assert exc_info.value.provider == "qwen"
    assert exc_info.value.model == "wan-video"
    assert exc_info.value.__cause__ is error


@pytest.mark.parametrize("terminal_status", ["succeeded", "FAILED"])
@pytest.mark.asyncio
async def test_wait_for_task_polls_until_terminal_status(
    monkeypatch: pytest.MonkeyPatch, terminal_status: str
) -> None:
    client = make_client(poll_interval_seconds=0, task_timeout_seconds=0)
    pending = {"output": {"task_status": "RUNNING"}}
    terminal = {"output": {"task_status": terminal_status}}
    client.get_task = AsyncMock(side_effect=[pending, terminal])
    sleep = AsyncMock()
    monkeypatch.setattr(client_module.asyncio, "sleep", sleep)

    assert await client.wait_for_task("task-1") == terminal
    sleep.assert_awaited_once_with(1)


@pytest.mark.asyncio
async def test_wait_for_task_times_out_after_boundary_poll(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = make_client(poll_interval_seconds=5, task_timeout_seconds=5)
    client.get_task = AsyncMock(return_value={"output": {"task_status": "RUNNING"}})
    monkeypatch.setattr(client_module.asyncio, "sleep", AsyncMock())

    with pytest.raises(ProviderError):
        await client.wait_for_task("task-1")

    assert client.get_task.await_count == 2
