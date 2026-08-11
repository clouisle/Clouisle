from types import SimpleNamespace
from urllib.parse import urlsplit

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.core.model_endpoint_policy import ModelEndpointPolicyError

from app.api.v1.admin.endpoints import models
from app.schemas.model import ModelDiscoveryRequest, ModelProvider


@pytest.fixture(autouse=True)
def allow_model_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        models,
        "ensure_model_endpoint_allowed",
        AsyncMock(return_value="https://api.example.test"),
    )


class StreamContext:
    def __init__(self, response: httpx.Response | None, error: Exception | None = None):
        self.response = response
        self.error = error

    async def __aenter__(self):
        if self.error is not None:
            raise self.error
        return self.response

    async def __aexit__(self, *_args):
        return False


class ChunkedStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes]):
        self.chunks = chunks

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk


class AsyncClient:
    def __init__(
        self, response: httpx.Response | None = None, error: Exception | None = None
    ):
        self.stream = MagicMock(return_value=StreamContext(response, error))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


def install_client(
    monkeypatch: pytest.MonkeyPatch,
    response: httpx.Response | None = None,
    error: Exception | None = None,
) -> tuple[AsyncClient, MagicMock]:
    client = AsyncClient(response=response, error=error)
    factory = MagicMock(return_value=client)
    monkeypatch.setattr(models.httpx, "AsyncClient", factory)
    return client, factory


@pytest.mark.anyio
async def test_discover_models_requests_openai_compatible_api(monkeypatch):
    response = httpx.Response(
        200,
        json={
            "data": [
                {"id": "gpt-4o", "display_name": "GPT-4o"},
                {"id": "gpt-4o"},
                {"id": "x" * 101},
                {"name": "fallback-model"},
                {},
            ]
        },
        request=httpx.Request("GET", "https://api.example.test/v1/models"),
    )
    client, factory = install_client(monkeypatch, response)

    result = await models.discover_models(
        ModelDiscoveryRequest(
            provider=ModelProvider.CUSTOM,
            base_url="https://api.example.test/https://evil.example.test",
            api_key="secret",
        ),
        current_user=SimpleNamespace(),
    )

    factory.assert_called_once_with(
        base_url="https://api.example.test",
        timeout=15.0,
        follow_redirects=False,
    )
    client.stream.assert_called_once_with(
        "GET",
        "/v1/models",
        headers={"Authorization": "Bearer secret"},
        params=None,
    )
    assert result["data"].success is True
    assert [(item.id, item.name) for item in result["data"].models] == [
        ("gpt-4o", "GPT-4o"),
        ("fallback-model", "fallback-model"),
    ]


@pytest.mark.anyio
async def test_discover_models_normalizes_safe_remote_metadata(monkeypatch):
    response = httpx.Response(
        200,
        json={
            "data": [
                {
                    "id": "metadata-model",
                    "contextLength": "128000",
                    "top_provider": {"max_completion_tokens": 8192},
                    "capabilities": {
                        "supports_vision": True,
                        "streaming": False,
                    },
                    "supported_parameters": ["tools", "response_format"],
                    "architecture": {"input_modalities": ["text", "image"]},
                },
                {
                    "id": "invalid-metadata-model",
                    "context_length": True,
                    "max_tokens": "0",
                    "capabilities": {"vision": "true"},
                },
            ]
        },
        request=httpx.Request("GET", "https://api.example.test/v1/models"),
    )
    install_client(monkeypatch, response)

    result = await models.discover_models(
        ModelDiscoveryRequest(
            provider=ModelProvider.CUSTOM,
            base_url="https://api.example.test/v1",
            api_key="secret",
        ),
        current_user=SimpleNamespace(),
    )

    rich, invalid = result["data"].models
    assert rich.context_length == 128000
    assert rich.max_output_tokens == 8192
    assert rich.capabilities == {
        "vision": True,
        "streaming": False,
        "function_call": True,
        "json_mode": True,
    }
    assert invalid.context_length is None
    assert invalid.max_output_tokens is None
    assert invalid.capabilities is None


@pytest.mark.anyio
@pytest.mark.parametrize(
    (
        "provider",
        "base_url",
        "api_key",
        "payload",
        "endpoint",
        "headers",
        "params",
        "expected",
    ),
    [
        (
            ModelProvider.ANTHROPIC,
            "https://api.anthropic.test",
            "anthropic-key",
            {"data": [{"id": "claude-sonnet", "display_name": "Claude Sonnet"}]},
            "https://api.anthropic.test/v1/models",
            {"anthropic-version": "2023-06-01", "x-api-key": "anthropic-key"},
            None,
            ("claude-sonnet", "Claude Sonnet"),
        ),
        (
            ModelProvider.GOOGLE,
            "https://generativelanguage.example.test/v1beta",
            "google-key",
            {
                "models": [
                    {"name": "models/gemini-2.5-pro", "displayName": "Gemini 2.5 Pro"}
                ]
            },
            "https://generativelanguage.example.test/v1beta/models",
            {},
            {"key": "google-key"},
            ("gemini-2.5-pro", "Gemini 2.5 Pro"),
        ),
        (
            ModelProvider.OLLAMA,
            "http://ollama.example.test:11434",
            None,
            {"models": [{"name": "llama3.2:latest"}]},
            "http://ollama.example.test:11434/api/tags",
            {},
            None,
            ("llama3.2:latest", "llama3.2:latest"),
        ),
    ],
)
async def test_discover_models_uses_provider_specific_protocol(
    monkeypatch,
    provider,
    base_url,
    api_key,
    payload,
    endpoint,
    headers,
    params,
    expected,
):
    response = httpx.Response(
        200,
        json=payload,
        request=httpx.Request("GET", endpoint),
    )
    client, _ = install_client(monkeypatch, response)

    result = await models.discover_models(
        ModelDiscoveryRequest(
            provider=provider,
            base_url=base_url,
            api_key=api_key,
        ),
        current_user=SimpleNamespace(),
    )

    client.stream.assert_called_once_with(
        "GET",
        urlsplit(endpoint).path,
        headers=headers,
        params=params,
    )
    assert result["data"].success is True
    assert [(item.id, item.name) for item in result["data"].models] == [expected]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("discovery_request", "expected_key"),
    [
        (
            ModelDiscoveryRequest(
                provider=ModelProvider.AZURE_OPENAI,
                base_url="https://azure.example.test",
                api_key="key",
            ),
            "model_discovery_not_supported",
        ),
        (
            ModelDiscoveryRequest(
                provider=ModelProvider.OPENAI,
                base_url="https://api.example.test/v1",
            ),
            "model_discovery_api_key_required",
        ),
        (
            ModelDiscoveryRequest(
                provider=ModelProvider.OPENAI,
                base_url="ftp://api.example.test/v1",
                api_key="secret",
            ),
            "model_discovery_base_url_invalid",
        ),
        (
            ModelDiscoveryRequest(
                provider=ModelProvider.OPENAI,
                base_url="https://api.example.test//unexpected-authority",
                api_key="secret",
            ),
            "model_discovery_base_url_invalid",
        ),
    ],
)
async def test_discover_models_rejects_unusable_configuration(
    monkeypatch,
    discovery_request,
    expected_key,
):
    monkeypatch.setattr(models, "t", lambda key, **_kwargs: key)
    factory = MagicMock()
    monkeypatch.setattr(models.httpx, "AsyncClient", factory)

    result = await models.discover_models(
        discovery_request, current_user=SimpleNamespace()
    )

    assert result["data"].success is False
    assert result["data"].message == expected_key
    assert result["data"].models == []
    factory.assert_not_called()


@pytest.mark.anyio
async def test_discover_models_rejects_endpoint_outside_allowlist(monkeypatch):
    monkeypatch.setattr(models, "t", lambda key, **_kwargs: key)
    monkeypatch.setattr(
        models,
        "ensure_model_endpoint_allowed",
        AsyncMock(
            side_effect=ModelEndpointPolicyError(
                "model_endpoint_not_allowlisted",
                origin="https://blocked.example.test",
            )
        ),
    )
    factory = MagicMock()
    monkeypatch.setattr(models.httpx, "AsyncClient", factory)

    result = await models.discover_models(
        ModelDiscoveryRequest(
            provider=ModelProvider.CUSTOM,
            base_url="https://blocked.example.test/v1",
            api_key="secret",
        ),
        current_user=SimpleNamespace(),
    )

    assert result["data"].success is False
    assert result["data"].message == "model_endpoint_not_allowlisted"
    factory.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("response", "error"),
    [
        (None, httpx.ConnectError("offline")),
        (
            httpx.Response(
                200,
                json={"unexpected": []},
                request=httpx.Request("GET", "https://api.example.test/v1/models"),
            ),
            None,
        ),
    ],
)
async def test_discover_models_returns_safe_failure_for_remote_errors(
    monkeypatch,
    response,
    error,
):
    monkeypatch.setattr(models, "t", lambda key, **_kwargs: key)
    install_client(monkeypatch, response=response, error=error)

    result = await models.discover_models(
        ModelDiscoveryRequest(
            provider=ModelProvider.OPENAI,
            base_url="https://api.example.test/v1",
            api_key="sk-live-secret",
        ),
        current_user=SimpleNamespace(),
    )

    assert result["data"].success is False
    assert result["data"].message == "model_discovery_failed"
    assert "sk-live-secret" not in result["data"].message


@pytest.mark.anyio
async def test_discover_models_rejects_oversized_chunked_response(monkeypatch):
    prefix = b'{"data": []}'
    response = httpx.Response(
        200,
        stream=ChunkedStream(
            [
                prefix,
                b" " * (models._MODEL_DISCOVERY_MAX_RESPONSE_BYTES - len(prefix) + 1),
            ]
        ),
        request=httpx.Request("GET", "https://api.example.test/v1/models"),
    )
    install_client(monkeypatch, response=response)
    monkeypatch.setattr(models, "t", lambda key, **_kwargs: key)

    result = await models.discover_models(
        ModelDiscoveryRequest(
            provider=ModelProvider.OPENAI,
            base_url="https://api.example.test/v1",
            api_key="secret",
        ),
        current_user=SimpleNamespace(),
    )

    assert result["data"].success is False
    assert result["data"].message == "model_discovery_failed"


@pytest.mark.parametrize(
    ("provider", "api_key", "endpoint", "headers", "params"),
    [
        (
            ModelProvider.CUSTOM,
            "key",
            "/v1/models",
            {"Authorization": "Bearer key"},
            None,
        ),
        (
            ModelProvider.ANTHROPIC,
            "key",
            "/v1/models",
            {"anthropic-version": "2023-06-01", "x-api-key": "key"},
            None,
        ),
        (
            ModelProvider.GOOGLE,
            "key",
            "/v1beta/models",
            {},
            {"key": "key"},
        ),
    ],
)
def test_model_discovery_uses_fixed_provider_paths(
    provider,
    api_key,
    endpoint,
    headers,
    params,
):
    assert models._build_model_discovery_request(provider, api_key) == (
        endpoint,
        headers,
        params,
    )


def test_parse_discovered_models_skips_unusable_items_and_labels():
    result = models._parse_discovered_models(
        ModelProvider.OPENAI,
        {
            "data": [
                "not-an-object",
                {"id": "usable", "displayName": "x" * 101},
            ]
        },
    )

    assert [(item.id, item.name) for item in result] == [("usable", "usable")]


def test_parse_google_discovery_token_limits():
    result = models._parse_discovered_models(
        ModelProvider.GOOGLE,
        {
            "models": [
                {
                    "name": "models/gemini-2.5-pro",
                    "displayName": "Gemini 2.5 Pro",
                    "inputTokenLimit": 1_048_576,
                    "outputTokenLimit": "65536",
                }
            ]
        },
    )

    assert result[0].id == "gemini-2.5-pro"
    assert result[0].context_length == 1_048_576
    assert result[0].max_output_tokens == 65_536


def test_parse_discovered_models_rejects_non_object_payload():
    with pytest.raises(ValueError, match="not an object"):
        models._parse_discovered_models(ModelProvider.OPENAI, [])


def test_parse_discovered_models_limits_results():
    result = models._parse_discovered_models(
        ModelProvider.OPENAI,
        {"data": [{"id": f"model-{index}"} for index in range(201)]},
    )

    assert len(result) == 200
    assert result[-1].id == "model-199"
