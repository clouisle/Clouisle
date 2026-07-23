from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from app.llm.adapters import volcengine_client as client_module
from app.llm.adapters.volcengine_client import VolcengineClient
from app.llm.errors import (
    AuthenticationError,
    InvalidRequestError,
    ProviderError,
    RateLimitError,
    TaskNotFoundError,
)


def make_client(**config: float) -> VolcengineClient:
    model = SimpleNamespace(
        model_id="seedance-1-0-pro",
        api_key="secret",
        base_url="https://ark.example/api/v3/",
        config=config,
    )
    return VolcengineClient(model)


class AsyncClient:
    def __init__(self, response: Mock | None = None, error: Exception | None = None):
        self.request = AsyncMock(return_value=response, side_effect=error)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


@pytest.mark.asyncio
async def test_generate_image_sends_normalized_authenticated_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = Mock(status_code=200)
    response.json.return_value = {"data": [{"url": "https://cdn.example/image.png"}]}
    transport = AsyncClient(response)
    monkeypatch.setattr(client_module.httpx, "AsyncClient", lambda **_kwargs: transport)

    payload = {"model": "seedream", "prompt": "A lighthouse"}
    result = await make_client(timeout=12).generate_image(payload)

    assert result == {"data": [{"url": "https://cdn.example/image.png"}]}
    transport.request.assert_awaited_once_with(
        "POST",
        "https://ark.example/api/v3/images/generations",
        json=payload,
        headers={
            "Authorization": "Bearer secret",
            "Content-Type": "application/json",
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
        await make_client()._request(method, "/contents/generations/tasks/task-7")

    if attribute:
        assert getattr(exc_info.value, attribute[0]) == attribute[1]


@pytest.mark.asyncio
async def test_request_deduplicates_v3_and_uses_text_for_non_json_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = Mock(status_code=502, text="bad gateway")
    response.json.side_effect = ValueError
    transport = AsyncClient(response)
    monkeypatch.setattr(client_module.httpx, "AsyncClient", lambda **_kwargs: transport)

    with pytest.raises(ProviderError, match="bad gateway"):
        await make_client()._request("POST", "/v3/images/generations")

    assert transport.request.await_args.args[1] == (
        "https://ark.example/api/v3/images/generations"
    )


@pytest.mark.parametrize(
    "error",
    [httpx.ReadTimeout("slow"), httpx.ConnectError("offline")],
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
        await make_client().create_task({"prompt": "A lighthouse"})

    assert exc_info.value.provider == "volcengine"
    assert exc_info.value.model == "seedance-1-0-pro"
    assert exc_info.value.__cause__ is error


@pytest.mark.parametrize("terminal_status", ["succeeded", "EXPIRED"])
@pytest.mark.asyncio
async def test_wait_for_task_polls_until_terminal_status(
    monkeypatch: pytest.MonkeyPatch, terminal_status: str
) -> None:
    client = make_client(poll_interval_seconds=0, task_timeout_seconds=0)
    pending = {"status": "running"}
    terminal = {"status": terminal_status}
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
    client.get_task = AsyncMock(return_value={"status": "running"})
    monkeypatch.setattr(client_module.asyncio, "sleep", AsyncMock())

    with pytest.raises(ProviderError):
        await client.wait_for_task("task-1")

    assert client.get_task.await_count == 2
