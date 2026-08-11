from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.api.v1.admin.endpoints import models
from app.schemas.model import ModelDiscoveryRequest, ModelProvider


class AsyncClient:
    def __init__(
        self, response: httpx.Response | None = None, error: Exception | None = None
    ):
        self.get = AsyncMock()
        if error is not None:
            self.get.side_effect = error
        else:
            self.get.return_value = response

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
            base_url="https://api.example.test/v1/",
            api_key="secret",
        ),
        current_user=SimpleNamespace(),
    )

    factory.assert_called_once_with(timeout=15.0, follow_redirects=False)
    client.get.assert_awaited_once_with(
        "https://api.example.test/v1/models",
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

    client.get.assert_awaited_once_with(endpoint, headers=headers, params=params)
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


@pytest.mark.parametrize(
    ("provider", "base_url", "api_key", "endpoint", "headers", "params"),
    [
        (
            ModelProvider.CUSTOM,
            "https://api.example.test/v1/models",
            "key",
            "https://api.example.test/v1/models",
            {"Authorization": "Bearer key"},
            None,
        ),
        (
            ModelProvider.ANTHROPIC,
            "https://api.anthropic.test/v1/models",
            "key",
            "https://api.anthropic.test/v1/models",
            {"anthropic-version": "2023-06-01", "x-api-key": "key"},
            None,
        ),
        (
            ModelProvider.ANTHROPIC,
            "https://api.anthropic.test/v1",
            "key",
            "https://api.anthropic.test/v1/models",
            {"anthropic-version": "2023-06-01", "x-api-key": "key"},
            None,
        ),
    ],
)
def test_model_discovery_reuses_existing_model_paths(
    provider,
    base_url,
    api_key,
    endpoint,
    headers,
    params,
):
    assert models._build_model_discovery_request(provider, base_url, api_key) == (
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
