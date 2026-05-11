from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.llm.adapters.chat.anthropic_adapter import AnthropicAdapter
from app.llm.adapters.chat.deepseek_adapter import DeepSeekAdapter
from app.llm.adapters.chat.moonshot_adapter import MoonshotAdapter
from app.llm.adapters.chat.ollama_adapter import OllamaAdapter
from app.llm.adapters.chat.openai_adapter import OpenAIAdapter
from app.llm.adapters.chat.openai_compatible_adapter import OpenAICompatibleAdapter
from app.llm.adapters.chat.xai_adapter import XAIAdapter
from app.llm.types import Message, MessageRole


def build_model(provider: str, model_id: str, **extra):
    return SimpleNamespace(
        provider=provider,
        model_id=model_id,
        api_key=extra.pop("api_key", "test-key"),
        base_url=extra.pop("base_url", "https://example.com"),
        config=extra.pop("config", {}),
        default_params=extra.pop("default_params", {}),
        max_output_tokens=extra.pop("max_output_tokens", None),
        **extra,
    )


class _FakeAsyncOpenAI:
    def __init__(self, *args, **kwargs):
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=AsyncMock()))
        self.chat.completions.create.return_value = SimpleNamespace(
            id="resp-1",
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(content="hello", tool_calls=None),
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=1,
                completion_tokens=1,
                total_tokens=2,
            ),
        )

    async def close(self):
        return None


class _FakeAsyncAnthropic:
    def __init__(self, *args, **kwargs):
        self.messages = SimpleNamespace(create=AsyncMock())
        self.messages.create.return_value = SimpleNamespace(
            id="resp-1",
            content=[SimpleNamespace(type="text", text="hello")],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        )

    async def close(self):
        return None


@pytest.mark.anyio
async def test_openai_adapter_passes_reasoning_effort_and_extra_body():
    adapter = OpenAIAdapter(
        build_model(
            "openai",
            "o3-mini",
            default_params={
                "thinking": {"enabled": True},
                "reasoning_effort": "high",
                "extra_body": {
                    "metadata": {"source": "test"},
                    "model": "should-not-pass",
                },
            },
        )
    )

    with patch("openai.AsyncOpenAI", _FakeAsyncOpenAI):
        await adapter.chat([Message(role=MessageRole.USER, content="Hi")])

    # Recreate client to inspect captured call via patched class instance
    with patch("openai.AsyncOpenAI", _FakeAsyncOpenAI) as _:
        fake_client = _FakeAsyncOpenAI()
        with patch("openai.AsyncOpenAI", return_value=fake_client):
            await adapter.chat([Message(role=MessageRole.USER, content="Hi")])

        kwargs = fake_client.chat.completions.create.await_args.kwargs
        assert kwargs["reasoning_effort"] == "high"
        assert kwargs["extra_body"] == {"metadata": {"source": "test"}}
        assert kwargs["model"] == "o3-mini"


@pytest.mark.anyio
async def test_openai_compatible_adapter_passes_top_p_reasoning_effort_and_extra_body():
    adapter = OpenAICompatibleAdapter(
        build_model(
            "custom",
            "deepseek-v4-pro",
            default_params={
                "top_p": 0.8,
                "thinking": {"enabled": True},
                "reasoning_effort": "high",
                "extra_body": {"thinking": {"type": "enabled"}},
            },
        ),
        provider_hint="custom",
    )

    fake_client = _FakeAsyncOpenAI()
    with patch("openai.AsyncOpenAI", return_value=fake_client):
        await adapter.chat([Message(role=MessageRole.USER, content="Hi")])

    kwargs = fake_client.chat.completions.create.await_args.kwargs
    assert kwargs["top_p"] == 0.8
    assert kwargs["reasoning_effort"] == "high"
    assert kwargs["extra_body"] == {"thinking": {"type": "enabled"}}


@pytest.mark.anyio
async def test_deepseek_adapter_passes_thinking_top_p_reasoning_effort_and_extra_body():
    adapter = DeepSeekAdapter(
        build_model(
            "deepseek",
            "deepseek-v4-pro",
            default_params={
                "top_p": 0.75,
                "thinking": {"enabled": True},
                "reasoning_effort": "high",
                "extra_body": {"metadata": {"source": "test"}},
            },
        )
    )

    fake_client = _FakeAsyncOpenAI()
    with patch("openai.AsyncOpenAI", return_value=fake_client):
        await adapter.chat([Message(role=MessageRole.USER, content="Hi")])

    kwargs = fake_client.chat.completions.create.await_args.kwargs
    assert kwargs["top_p"] == 0.75
    assert kwargs["reasoning_effort"] == "high"
    assert kwargs["extra_body"] == {
        "metadata": {"source": "test"},
        "thinking": {"type": "enabled"},
    }


@pytest.mark.anyio
async def test_xai_adapter_defaults_reasoning_effort_when_thinking_enabled():
    adapter = XAIAdapter(
        build_model(
            "xai",
            "grok-3",
            default_params={"thinking": {"enabled": True}},
        )
    )

    fake_client = _FakeAsyncOpenAI()
    with patch("openai.AsyncOpenAI", return_value=fake_client):
        await adapter.chat([Message(role=MessageRole.USER, content="Hi")])

    kwargs = fake_client.chat.completions.create.await_args.kwargs
    assert kwargs["reasoning_effort"] == "medium"


@pytest.mark.anyio
async def test_anthropic_adapter_passes_extra_body_and_prefers_default_params_thinking():
    adapter = AnthropicAdapter(
        build_model(
            "anthropic",
            "claude-sonnet-4-5",
            default_params={
                "thinking": {"enabled": True, "budget_tokens": 2048},
                "extra_body": {"service_tier": "standard"},
            },
            config={
                "thinking": {"enabled": True, "budget_tokens": 1024},
            },
        )
    )

    fake_client = _FakeAsyncAnthropic()
    with patch("anthropic.AsyncAnthropic", return_value=fake_client):
        await adapter.chat([Message(role=MessageRole.USER, content="Hi")])

    kwargs = fake_client.messages.create.await_args.kwargs
    assert kwargs["thinking"] == {"type": "enabled", "budget_tokens": 2048}
    assert kwargs["extra_body"] == {"service_tier": "standard"}


@pytest.mark.anyio
async def test_moonshot_adapter_passes_thinking_and_preserves_reasoning_history():
    adapter = MoonshotAdapter(
        build_model(
            "moonshot",
            "kimi-k2.6",
            default_params={
                "thinking": {"type": "enabled", "keep": "all"},
            },
        )
    )

    fake_client = _FakeAsyncOpenAI()
    with patch("openai.AsyncOpenAI", return_value=fake_client):
        await adapter.chat(
            [
                Message(role=MessageRole.USER, content="Hi"),
                Message(
                    role=MessageRole.ASSISTANT,
                    content="Answer",
                    reasoning_content="internal thoughts",
                ),
            ]
        )

    kwargs = fake_client.chat.completions.create.await_args.kwargs
    assert kwargs["thinking"] == {"type": "enabled", "keep": "all"}
    assert kwargs["messages"][1]["reasoning_content"] == "internal thoughts"


@pytest.mark.anyio
async def test_ollama_adapter_passes_think_and_uses_dummy_api_key():
    adapter = OllamaAdapter(
        build_model(
            "ollama",
            "qwen3",
            api_key=None,
            default_params={"thinking": {"enabled": True}},
            base_url="http://localhost:11434/v1",
        )
    )

    fake_client = _FakeAsyncOpenAI()
    captured_init: dict[str, object] = {}

    def build_client(*args, **kwargs):
        captured_init.update(kwargs)
        return fake_client

    with patch("openai.AsyncOpenAI", side_effect=build_client):
        await adapter.chat(
            [
                Message(role=MessageRole.USER, content="Hi"),
                Message(
                    role=MessageRole.ASSISTANT,
                    content="Answer",
                    reasoning_content="chain of thought",
                ),
            ]
        )

    kwargs = fake_client.chat.completions.create.await_args.kwargs
    assert captured_init["api_key"] == "ollama"
    assert kwargs["think"] is True
    assert kwargs["messages"][1]["thinking"] == "chain of thought"
