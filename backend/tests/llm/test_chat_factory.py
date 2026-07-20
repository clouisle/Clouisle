from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.llm.adapters.chat.factory import create_chat_model


def build_model(provider: str, **overrides: object) -> SimpleNamespace:
    values = {
        "provider": provider,
        "model_id": "test-model",
        "api_key": "test-key",
        "base_url": None,
        "default_params": {},
        "config": {},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


<<<<<<< HEAD
@pytest.mark.parametrize(
    ("provider", "expected_base_url"),
    [
        ("openai", None),
        ("xai", "https://api.x.ai/v1"),
        ("deepseek", "https://api.deepseek.com/v1"),
        ("moonshot", "https://api.moonshot.cn/v1"),
        ("zhipu", "https://open.bigmodel.cn/api/paas/v4"),
        ("qwen", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        ("baichuan", "https://api.baichuan-ai.com/v1"),
        ("minimax", "https://api.minimax.chat/v1"),
        ("ollama", "http://localhost:11434/v1"),
    ],
)
def test_openai_compatible_providers_select_model_and_default_endpoint(
    provider: str, expected_base_url: str | None
):
    with patch("langchain_openai.ChatOpenAI") as chat_model:
        result = create_chat_model(build_model(provider))

    assert result is chat_model.return_value
    assert chat_model.call_args.kwargs["model"] == "test-model"
    assert chat_model.call_args.kwargs["base_url"] == expected_base_url


def test_openai_propagates_generation_and_transport_configuration():
    model = build_model(
        "openai",
        base_url="https://proxy.example/v1",
        max_output_tokens="2048",
        default_params={"temperature": 0.2, "top_p": 0.8, "max_tokens": 1024},
        config={"max_tokens": 512, "timeout": 90},
    )

    with patch("langchain_openai.ChatOpenAI") as chat_model:
        create_chat_model(model)

    kwargs = chat_model.call_args.kwargs
    assert kwargs == {
        "model": "test-model",
        "api_key": kwargs["api_key"],
        "base_url": "https://proxy.example/v1",
        "temperature": 0.2,
        "top_p": 0.8,
        "max_completion_tokens": 2048,
        "timeout": 90,
    }
    assert kwargs["api_key"].get_secret_value() == "test-key"


def test_anthropic_prefers_config_thinking_and_defaults_max_tokens():
    model = build_model(
        "anthropic",
        default_params={"thinking": {"type": "disabled"}},
        config={"thinking": {"type": "enabled", "budget_tokens": 1000}},
    )

    with patch("langchain_anthropic.ChatAnthropic") as chat_model:
        create_chat_model(model)

    kwargs = chat_model.call_args.kwargs
    assert kwargs["model"] == "test-model"
    assert kwargs["max_tokens"] == 4096
    assert kwargs["thinking"] == {"type": "enabled", "budget_tokens": 1000}


def test_google_and_azure_receive_provider_specific_configuration():
    with patch("langchain_google_genai.ChatGoogleGenerativeAI") as google:
        create_chat_model(
            build_model(
                "google",
                base_url="https://google-proxy.example",
                default_params={"temperature": 0, "top_p": 0.7},
                config={"max_tokens": "300", "timeout": 45},
            )
        )
    assert google.call_args.kwargs["client_options"] == {
        "api_endpoint": "https://google-proxy.example"
    }
    assert google.call_args.kwargs["max_output_tokens"] == 300
    assert google.call_args.kwargs["temperature"] == 0
    assert google.call_args.kwargs["top_p"] == 0.7

    with patch("langchain_openai.AzureChatOpenAI") as azure:
        create_chat_model(
            build_model(
                "azure_openai",
                base_url="https://azure.example",
                config={"azure": {"api_version": "2025-01-01"}},
            )
        )
    assert azure.call_args.kwargs["azure_deployment"] == "test-model"
    assert azure.call_args.kwargs["azure_endpoint"] == "https://azure.example"
    assert azure.call_args.kwargs["api_version"] == "2025-01-01"


@pytest.mark.parametrize(
    ("model", "message"),
    [
        (build_model("anthropic", api_key=None), "Anthropic requires api_key"),
        (build_model("google", api_key=None), "Google requires api_key"),
        (build_model("custom"), "Custom provider requires base_url"),
        (build_model("unknown"), "Unsupported provider for chat: unknown"),
    ],
)
def test_invalid_provider_configuration_fails_before_provider_call(
    model: SimpleNamespace, message: str
):
    with pytest.raises(ValueError, match=message):
        create_chat_model(model)


def test_custom_provider_uses_supplied_endpoint_and_preserves_constructor_errors():
    with patch(
        "langchain_openai.ChatOpenAI", side_effect=RuntimeError("provider setup failed")
    ) as chat_model:
        with pytest.raises(RuntimeError, match="provider setup failed"):
            create_chat_model(
                build_model("custom", base_url="https://custom.example/v1")
            )

    assert chat_model.call_args.kwargs["base_url"] == "https://custom.example/v1"
