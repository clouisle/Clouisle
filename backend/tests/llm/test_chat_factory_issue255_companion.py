import sys
import types
from types import SimpleNamespace

import pytest

from app.llm.adapters.chat.factory import create_chat_model
from app.models.model import ModelProvider


class FakeChatModel:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def config(provider, **overrides):
    values = {
        "provider": provider,
        "model_id": "model-test",
        "api_key": "secret",
        "base_url": None,
        "default_params": {},
        "config": {},
        "max_output_tokens": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def install(monkeypatch, module_name, class_name):
    module = types.ModuleType(module_name)
    setattr(module, class_name, FakeChatModel)
    monkeypatch.setitem(sys.modules, module_name, module)


def test_anthropic_requires_key_and_prefers_config_thinking(monkeypatch):
    install(monkeypatch, "langchain_anthropic", "ChatAnthropic")

    model = create_chat_model(
        config(
            ModelProvider.ANTHROPIC,
            default_params={"thinking": {"enabled": False}, "max_tokens": "2048"},
            config={"thinking": {"enabled": True}, "timeout": 12},
        )
    )

    assert model.kwargs["anthropic_api_key"].get_secret_value() == "secret"
    assert model.kwargs["thinking"] == {"enabled": True}
    assert model.kwargs["max_tokens"] == 2048
    assert model.kwargs["default_request_timeout"] == 12

    with pytest.raises(ValueError, match="Anthropic requires api_key"):
        create_chat_model(config(ModelProvider.ANTHROPIC, api_key=None))


def test_google_endpoint_sampling_and_missing_key_branches(monkeypatch):
    install(monkeypatch, "langchain_google_genai", "ChatGoogleGenerativeAI")

    model = create_chat_model(
        config(
            ModelProvider.GOOGLE,
            base_url="https://google.invalid",
            default_params={"temperature": 0.2, "top_p": 0.8},
            max_output_tokens="321",
        )
    )

    assert model.kwargs == {
        "model": "model-test",
        "google_api_key": model.kwargs["google_api_key"],
        "max_output_tokens": 321,
        "timeout": 60,
        "client_options": {"api_endpoint": "https://google.invalid"},
        "temperature": 0.2,
        "top_p": 0.8,
    }
    assert model.kwargs["google_api_key"].get_secret_value() == "secret"

    no_sampling = create_chat_model(config(ModelProvider.GOOGLE))
    assert "temperature" not in no_sampling.kwargs
    assert "top_p" not in no_sampling.kwargs
    assert "client_options" not in no_sampling.kwargs

    with pytest.raises(ValueError, match="Google requires api_key"):
        create_chat_model(config(ModelProvider.GOOGLE, api_key=None))


def test_custom_requires_base_url_and_unsupported_provider(monkeypatch):
    install(monkeypatch, "langchain_openai", "ChatOpenAI")

    with pytest.raises(ValueError, match="Custom provider requires base_url"):
        create_chat_model(config(ModelProvider.CUSTOM))

    custom = create_chat_model(
        config(ModelProvider.CUSTOM, base_url="https://custom.invalid/v1")
    )
    assert custom.kwargs["base_url"] == "https://custom.invalid/v1"
    assert custom.kwargs["model"] == "model-test"

    with pytest.raises(ValueError, match="Unsupported provider for chat"):
        create_chat_model(config(ModelProvider.VOLCENGINE))
