from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.llm.adapters.rerank import factory
from app.models.model import ModelProvider


def model(provider="openai", **overrides):
    values = {
        "provider": provider,
        "model_id": "rerank-model",
        "api_key": "test-key",
        "base_url": None,
        "default_params": None,
        "config": None,
        "max_output_tokens": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.parametrize(
    ("provider", "adapter_name", "provider_hint"),
    [
        (ModelProvider.OPENAI, "OpenAIAdapter", None),
        (ModelProvider.ANTHROPIC, "AnthropicAdapter", None),
        (ModelProvider.GOOGLE, "GeminiAdapter", None),
        (ModelProvider.DEEPSEEK, "DeepSeekAdapter", None),
        (ModelProvider.XAI, "XAIAdapter", None),
        (ModelProvider.AZURE_OPENAI, "OpenAICompatibleAdapter", "azure"),
        (ModelProvider.MOONSHOT, "OpenAICompatibleAdapter", "moonshot"),
        (ModelProvider.ZHIPU, "OpenAICompatibleAdapter", "zhipu"),
        (ModelProvider.QWEN, "OpenAICompatibleAdapter", "qwen"),
        (ModelProvider.BAICHUAN, "OpenAICompatibleAdapter", "baichuan"),
        (ModelProvider.MINIMAX, "OpenAICompatibleAdapter", "minimax"),
        (ModelProvider.VOLCENGINE, "OpenAICompatibleAdapter", "volcengine"),
        (ModelProvider.OLLAMA, "OpenAICompatibleAdapter", "ollama"),
        (ModelProvider.CUSTOM, "OpenAICompatibleAdapter", "custom"),
        ("other", "OpenAICompatibleAdapter", "other"),
    ],
)
def test_selects_chat_adapter_and_wraps_it(provider, adapter_name, provider_hint):
    config = model(provider)
    chat_adapter = object()
    rerank_adapter = object()

    with (
        patch.object(factory, adapter_name, return_value=chat_adapter) as constructor,
        patch.object(
            factory, "LLMRerankAdapter", return_value=rerank_adapter
        ) as wrapper,
    ):
        result = factory.create_rerank_adapter(config)

    if provider_hint is None:
        constructor.assert_called_once_with(config)
    else:
        constructor.assert_called_once_with(config, provider_hint=provider_hint)
    wrapper.assert_called_once_with(config, chat_adapter)
    assert result is rerank_adapter


@pytest.mark.parametrize(
    "overrides",
    [
        {"config": {"rerank_api": "native"}},
        {"base_url": "https://API.SILICONFLOW.COM/v1"},
    ],
)
def test_native_selection_returns_mocked_adapter(overrides):
    config = model(**overrides)
    native_adapter = object()

    with patch.object(
        factory, "OpenAICompatibleRerankAdapter", return_value=native_adapter
    ) as constructor:
        assert factory.create_rerank_adapter(config) is native_adapter

    constructor.assert_called_once_with(config)


@pytest.mark.parametrize(
    "config_value",
    [
        {"native_rerank": 1},
        {"rerank_api": "NATIVE"},
    ],
)
def test_native_config_requires_exact_values(config_value):
    config = model(config=config_value)

    with (
        patch.object(factory, "OpenAIAdapter", return_value=object()),
        patch.object(factory, "LLMRerankAdapter", return_value=object()) as wrapper,
        patch.object(factory, "OpenAICompatibleRerankAdapter") as native,
    ):
        factory.create_rerank_adapter(config)

    native.assert_not_called()
    wrapper.assert_called_once()


@pytest.mark.parametrize(
    ("target", "config"),
    [
        ("OpenAICompatibleRerankAdapter", model(config={"rerank_api": "native"})),
        ("OpenAIAdapter", model()),
        ("LLMRerankAdapter", model()),
    ],
)
def test_constructor_errors_propagate(target, config):
    with patch.object(factory, target, side_effect=RuntimeError(target)):
        with pytest.raises(RuntimeError, match=target):
            factory.create_rerank_adapter(config)
