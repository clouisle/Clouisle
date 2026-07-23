from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.llm.adapters import minimax_client as client_module
from app.llm.adapters.minimax_client import MiniMaxClient
from app.llm.errors import (
    AuthenticationError,
    ContentFilterError,
    InsufficientQuotaError,
    InvalidRequestError,
    ProviderError,
    RateLimitError,
    TaskNotFoundError,
)


def model(**kwargs):
    return SimpleNamespace(
        model_id="fake-model",
        api_key="fake-key",
        base_url=kwargs.pop("base_url", None),
        **kwargs,
    )


def install_response(monkeypatch, *, status_code=200, data=None, error=None):
    response = SimpleNamespace(status_code=status_code, json=lambda: data)
    request = AsyncMock(side_effect=error, return_value=response)
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.request = request
    monkeypatch.setattr(client_module.httpx, "AsyncClient", lambda **_kwargs: client)
    return request


def test_configuration_url_and_headers_cover_defaults_and_normalization():
    default = MiniMaxClient(model())
    custom = MiniMaxClient(
        model(base_url="https://minimax.invalid/api/", config={"timeout": "12.5"})
    )

    assert default.timeout == 300
    assert default._build_url("v1/image_generation") == (
        "https://api.minimax.chat/v1/image_generation"
    )
    assert default._build_url("tasks") == "https://api.minimax.chat/v1/tasks"
    assert custom.timeout == 12.5
    assert custom.base_url == "https://minimax.invalid/api"
    assert custom._build_url("/v1/tasks") == "https://minimax.invalid/api/v1/tasks"
    assert custom._headers() == {
        "Authorization": "Bearer fake-key",
        "Content-Type": "application/json",
    }


@pytest.mark.anyio
async def test_request_returns_json_and_forwards_all_arguments(monkeypatch):
    request = install_response(
        monkeypatch,
        data={"base_resp": {"status_code": "0"}, "task_id": "task-1"},
    )
    client = MiniMaxClient(model(config={"timeout": 9}))

    result = await client.request(
        "POST", "v1/video_generation", json={"prompt": "fake"}, params={"x": 1}
    )

    assert result["task_id"] == "task-1"
    request.assert_awaited_once_with(
        "POST",
        "https://api.minimax.chat/v1/video_generation",
        json={"prompt": "fake"},
        params={"x": 1},
        headers={
            "Authorization": "Bearer fake-key",
            "Content-Type": "application/json",
        },
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("error", "message_key"),
    [
        (httpx.ReadTimeout("slow"), "minimax_request_timeout"),
        (httpx.ConnectError("offline"), "minimax_api_error"),
    ],
)
async def test_request_maps_transport_errors(monkeypatch, error, message_key):
    install_response(monkeypatch, error=error)
    monkeypatch.setattr(client_module, "t", lambda key: key)

    with pytest.raises(ProviderError, match=message_key):
        await MiniMaxClient(model()).request("GET", "/tasks")


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status_code", "task_id", "error_type"),
    [
        (401, None, AuthenticationError),
        (404, "missing-task", TaskNotFoundError),
        (404, None, InvalidRequestError),
        (429, None, RateLimitError),
        (503, None, ProviderError),
    ],
)
async def test_request_maps_http_errors(monkeypatch, status_code, task_id, error_type):
    install_response(monkeypatch, status_code=status_code)

    with pytest.raises(error_type):
        await MiniMaxClient(model()).request("GET", "/tasks", task_id=task_id)


@pytest.mark.anyio
@pytest.mark.parametrize("payload", [ValueError("bad json"), ["not", "an", "object"]])
async def test_request_rejects_invalid_json(monkeypatch, payload):
    if isinstance(payload, Exception):
        response = SimpleNamespace(
            status_code=200, json=lambda: (_ for _ in ()).throw(payload)
        )
        request = AsyncMock(return_value=response)
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.request = request
        monkeypatch.setattr(
            client_module.httpx, "AsyncClient", lambda **_kwargs: client
        )
    else:
        install_response(monkeypatch, data=payload)

    with pytest.raises(ProviderError):
        await MiniMaxClient(model()).request("GET", "/tasks")


@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [
        (1004, AuthenticationError),
        (2049, AuthenticationError),
        (1002, RateLimitError),
        (1039, RateLimitError),
        (1008, InsufficientQuotaError),
        (1026, ContentFilterError),
        (1027, ContentFilterError),
        (2013, InvalidRequestError),
        (9999, ProviderError),
        (None, ProviderError),
        ("invalid", ProviderError),
    ],
)
def test_application_error_mapping(status_code, error_type):
    client = MiniMaxClient(model())

    with pytest.raises(error_type):
        client._raise_for_application_error({"base_resp": {"status_code": status_code}})


def test_application_response_without_error_is_accepted():
    client = MiniMaxClient(model())

    client._raise_for_application_error({})
    client._raise_for_application_error({"base_resp": "invalid"})
    client._raise_for_application_error({"base_resp": {}})
