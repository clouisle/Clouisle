from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.llm.errors import (
    AuthenticationError,
    ContentFilterError,
    ContextLengthError,
    InsufficientQuotaError,
    ModelDisabledError,
    ModelNotFoundError,
    ProviderError,
    RateLimitError,
)
from app.llm.manager import ModelManager
from app.schemas.response import BusinessError, ResponseCode
from app.models.model import ModelProvider, ModelType


@pytest.fixture(autouse=True)
def allow_model_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ModelManager, "_ensure_model_endpoint_allowed", AsyncMock())


@pytest.mark.parametrize(
    ("identifier", "expected"),
    [
        (str(uuid4()), "uuid"),
        ("openai/gpt-4o", "invalid"),
        ("gpt-4o", "invalid"),
    ],
)
def test_parse_model_identifier_accepts_only_uuid(identifier, expected):
    result = ModelManager()._parse_model_identifier(identifier)

    if expected == "uuid":
        assert result == identifier
    else:
        assert result is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("identifier", "expected_filter"),
    [
        (str(uuid4()), lambda value: {"id": value, "model_type": ModelType.EMBEDDING}),
        (None, lambda _value: {"model_type": ModelType.EMBEDDING, "is_default": True}),
    ],
)
async def test_get_model_config_selects_uuid_or_type_default(
    identifier, expected_filter
):
    model = SimpleNamespace(is_enabled=True)
    query = SimpleNamespace(first=AsyncMock(return_value=model))

    with patch("app.llm.manager.Model.filter", return_value=query) as model_filter:
        result = await ModelManager()._get_model_config(identifier, ModelType.EMBEDDING)

    assert result is model
    model_filter.assert_called_once_with(**expected_filter(identifier))


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [None, False])
async def test_get_model_config_rejects_missing_or_disabled_models(enabled):
    model = (
        SimpleNamespace(id="model-id", name="Disabled", is_enabled=False)
        if enabled is False
        else None
    )
    query = SimpleNamespace(first=AsyncMock(return_value=model))

    with patch("app.llm.manager.Model.filter", return_value=query):
        error = ModelDisabledError if enabled is False else ModelNotFoundError
        with pytest.raises(error):
            await ModelManager()._get_model_config(None)


@pytest.mark.asyncio
async def test_get_model_config_rejects_ambiguous_identifier_without_querying():
    with patch("app.llm.manager.Model.filter") as model_filter:
        with pytest.raises(BusinessError) as exc_info:
            await ModelManager()._get_model_config("gpt-4o")

    assert exc_info.value.code == ResponseCode.MODEL_NOT_FOUND
    assert exc_info.value.msg_key == "model_not_found"
    model_filter.assert_not_called()


@pytest.mark.parametrize(
    ("provider", "adapter_name"),
    [
        (ModelProvider.OPENAI, "OpenAIAdapter"),
        (ModelProvider.ANTHROPIC, "AnthropicAdapter"),
        (ModelProvider.GOOGLE, "GeminiAdapter"),
        (ModelProvider.DEEPSEEK, "DeepSeekAdapter"),
        (ModelProvider.MOONSHOT, "MoonshotAdapter"),
        (ModelProvider.OLLAMA, "OllamaAdapter"),
        (ModelProvider.XAI, "XAIAdapter"),
    ],
)
def test_get_chat_adapter_selects_native_provider(provider, adapter_name):
    model = SimpleNamespace(provider=provider)

    with patch(f"app.llm.manager.{adapter_name}") as adapter:
        result = ModelManager()._get_chat_adapter(model)

    assert result is adapter.return_value
    adapter.assert_called_once_with(model)


@pytest.mark.parametrize(
    ("provider", "hint"),
    [
        (ModelProvider.AZURE_OPENAI, "azure"),
        (ModelProvider.ZHIPU, "zhipu"),
        (ModelProvider.QWEN, "qwen"),
        (ModelProvider.BAICHUAN, "baichuan"),
        (ModelProvider.MINIMAX, "minimax"),
        (ModelProvider.VOLCENGINE, "volcengine"),
        (ModelProvider.SILICONFLOW, "siliconflow"),
        (ModelProvider.CUSTOM, "custom"),
    ],
)
def test_get_chat_adapter_configures_compatible_provider_hint(provider, hint):
    model = SimpleNamespace(provider=provider)

    with patch("app.llm.manager.OpenAICompatibleAdapter") as adapter:
        result = ModelManager()._get_chat_adapter(model)

    assert result is adapter.return_value
    adapter.assert_called_once_with(model, provider_hint=hint)


def test_get_chat_adapter_falls_back_for_unknown_provider():
    model = SimpleNamespace(provider="other")

    with patch("app.llm.manager.OpenAICompatibleAdapter") as adapter:
        ModelManager()._get_chat_adapter(model)

    adapter.assert_called_once_with(model)


@pytest.mark.parametrize(
    ("exception", "error_type"),
    [
        (type("NotFoundError", (Exception,), {})("missing"), ModelNotFoundError),
        (Exception("invalid API key"), AuthenticationError),
        (Exception("payment required: insufficient balance"), InsufficientQuotaError),
        (Exception("rate_limit reached"), RateLimitError),
        (Exception("token count exceeds max"), ContextLengthError),
        (Exception("blocked by safety policy"), ContentFilterError),
        (Exception("upstream disconnected"), ProviderError),
    ],
)
def test_handle_error_classifies_provider_failures(exception, error_type):
    error = ModelManager()._handle_error(exception, "provider", "model")

    assert isinstance(error, error_type)
    assert str(exception) in str(error)
