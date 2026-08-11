from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.model_endpoint_policy import (
    ModelEndpointPolicyError,
    ensure_model_endpoint_allowed,
    model_endpoint_origin_is_allowed,
    normalize_model_endpoint_allowlist,
    normalize_model_endpoint_origin,
)
from app.llm.manager import ModelManager
from app.models.model import (
    ModelProvider,
    ModelType,
    get_effective_model_base_url,
)
from app.schemas.response import BusinessError, ResponseCode
from app.models.site_setting import SiteSetting


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://API.Example.COM/v1/", "https://api.example.com"),
        ("https://api.example.com:443/models", "https://api.example.com"),
        ("http://10.0.0.20:11434/api/tags", "http://10.0.0.20:11434"),
        ("http://[2001:db8::1]:8080/v1", "http://[2001:db8::1]:8080"),
    ],
)
def test_normalize_model_endpoint_origin(value: str, expected: str) -> None:
    assert normalize_model_endpoint_origin(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "ftp://api.example.com",
        "https://user:secret@api.example.com",
        "https://api.example.com/v1?key=secret",
        "https://api.example.com/v1#fragment",
        "https://api.example.com:invalid",
    ],
)
def test_normalize_model_endpoint_origin_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ModelEndpointPolicyError) as error:
        normalize_model_endpoint_origin(value)

    assert error.value.msg_key == "model_endpoint_base_url_invalid"


def test_normalize_allowlist_deduplicates_canonical_origins() -> None:
    assert normalize_model_endpoint_allowlist(
        [
            "https://api.example.com/v1",
            "https://API.EXAMPLE.COM:443/models",
            "http://ollama:11434",
        ]
    ) == ["https://api.example.com", "http://ollama:11434"]


@pytest.mark.parametrize("value", [None, "https://api.example.com", [1]])
def test_normalize_allowlist_rejects_invalid_shapes(value: object) -> None:
    with pytest.raises(ModelEndpointPolicyError) as error:
        normalize_model_endpoint_allowlist(value)

    assert error.value.msg_key == "model_endpoint_allowlist_invalid"


def test_model_endpoint_origin_requires_exact_scheme_host_and_port() -> None:
    allowlist = ["https://api.example.com", "http://ollama:11434"]

    assert (
        model_endpoint_origin_is_allowed("https://api.example.com/v1", allowlist)
        == "https://api.example.com"
    )
    assert (
        model_endpoint_origin_is_allowed("http://ollama:11434/api/tags", allowlist)
        == "http://ollama:11434"
    )
    with pytest.raises(ModelEndpointPolicyError, match="http://api.example.com"):
        model_endpoint_origin_is_allowed("http://api.example.com/v1", allowlist)
    with pytest.raises(ModelEndpointPolicyError, match="http://ollama:11435"):
        model_endpoint_origin_is_allowed("http://ollama:11435", allowlist)


@pytest.mark.parametrize(
    ("provider", "model_type", "base_url", "expected"),
    [
        (
            "unknown",
            None,
            " https://gateway.example.test/v1 ",
            "https://gateway.example.test/v1",
        ),
        ("unknown", None, None, None),
        (
            ModelProvider.OPENAI,
            "unknown",
            None,
            "https://api.openai.com/v1",
        ),
        (
            ModelProvider.OPENAI,
            None,
            None,
            "https://api.openai.com/v1",
        ),
        (ModelProvider.CUSTOM, None, None, None),
    ],
)
def test_effective_model_endpoint_fallbacks(
    provider: ModelProvider | str,
    model_type: ModelType | str | None,
    base_url: str | None,
    expected: str | None,
) -> None:
    assert get_effective_model_base_url(provider, model_type, base_url) == expected


def test_effective_model_endpoint_matches_runtime_adapter_defaults() -> None:
    assert (
        get_effective_model_base_url(
            ModelProvider.VOLCENGINE,
            ModelType.TTS,
            None,
        )
        == "https://openspeech.bytedance.com/api/v3/tts/unidirectional/sse"
    )
    assert (
        get_effective_model_base_url(
            ModelProvider.VOLCENGINE,
            ModelType.AUDIO_GENERATION,
            None,
        )
        == "https://openspeech.bytedance.com/api/v3/tts/create"
    )
    assert (
        get_effective_model_base_url(
            ModelProvider.VOLCENGINE,
            ModelType.CHAT,
            None,
        )
        == "https://ark.cn-beijing.volces.com/api/v3"
    )


@pytest.mark.asyncio
async def test_ensure_model_endpoint_allowed_reads_current_site_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = AsyncMock(
        return_value=SimpleNamespace(
            value='["https://api.example.com"]',
            value_type="json",
        )
    )
    monkeypatch.setattr(
        SiteSetting,
        "filter",
        lambda **_kwargs: SimpleNamespace(first=first),
    )

    assert (
        await ensure_model_endpoint_allowed("https://api.example.com/v1")
        == "https://api.example.com"
    )
    with pytest.raises(ModelEndpointPolicyError) as error:
        await ensure_model_endpoint_allowed("https://unlisted.example.com/v1")
    assert error.value.msg_key == "model_endpoint_not_allowlisted"


@pytest.mark.asyncio
async def test_ensure_model_endpoint_allowed_handles_missing_and_invalid_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_value = AsyncMock(side_effect=[None, "invalid"])
    monkeypatch.setattr(SiteSetting, "get_value", get_value)

    assert await ensure_model_endpoint_allowed(None) is None
    with pytest.raises(ModelEndpointPolicyError):
        await ensure_model_endpoint_allowed("https://api.example.com")


@pytest.mark.asyncio
async def test_model_manager_checks_endpoint_when_loading_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = SimpleNamespace(is_enabled=True)
    query = SimpleNamespace(first=AsyncMock(return_value=model))
    monkeypatch.setattr("app.llm.manager.Model.filter", lambda **_kwargs: query)
    manager = ModelManager()
    manager._ensure_model_endpoint_allowed = AsyncMock()

    assert await manager._get_model_config() is model
    manager._ensure_model_endpoint_allowed.assert_awaited_once_with(model)


@pytest.mark.asyncio
async def test_model_manager_translates_endpoint_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoint = "http://metadata.internal:80"
    check = AsyncMock(
        side_effect=ModelEndpointPolicyError(
            "model_endpoint_not_allowlisted", origin=endpoint
        )
    )
    monkeypatch.setattr("app.llm.manager.ensure_model_endpoint_allowed", check)
    model = SimpleNamespace(get_effective_base_url=lambda: endpoint)

    with pytest.raises(BusinessError) as error:
        await ModelManager()._ensure_model_endpoint_allowed(model)

    assert error.value.code == ResponseCode.VALIDATION_ERROR
    assert error.value.msg_key == "model_endpoint_not_allowlisted"
    assert error.value.kwargs == {"origin": endpoint}
    check.assert_awaited_once_with(endpoint)
