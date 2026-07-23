from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.llm.adapters.chat.base import BaseChatAdapter
from app.llm.types import (
    ChatResponse,
    ChatStreamChunk,
    FinishReason,
    FunctionDefinition,
    Message,
    ToolDefinition,
    Usage,
)


class StubChatAdapter(BaseChatAdapter):
    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        **kwargs,
    ) -> ChatResponse:
        raise NotImplementedError

    async def chat_stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        **kwargs,
    ) -> AsyncIterator[ChatStreamChunk]:
        if False:
            yield ChatStreamChunk(**{})
        raise NotImplementedError


def build_adapter(
    model_id: str = "plain-model",
    *,
    default_params: dict | None = None,
    config: dict | None = None,
    max_output_tokens: int | None = None,
) -> StubChatAdapter:
    return StubChatAdapter(
        SimpleNamespace(
            model_id=model_id,
            api_key="key",
            base_url="https://example.com",
            default_params=default_params,
            config=config,
            max_output_tokens=max_output_tokens,
        )
    )


def test_parameter_precedence_and_typed_properties():
    adapter = build_adapter(
        default_params={
            "temperature": "0.4",
            "max_tokens": "200",
            "timeout": "30",
        },
        config={"temperature": 0.2, "top_p": "0.8", "max_tokens": 100},
    )

    assert adapter.model_id == "plain-model"
    assert adapter.api_key == "key"
    assert adapter.base_url == "https://example.com"
    assert adapter.get_effective_param("temperature", temperature=0) == 0
    assert adapter.get_effective_param("temperature") == "0.4"
    assert adapter.get_effective_param("top_p") == "0.8"
    assert adapter.get_effective_param("missing") is None
    assert adapter.temperature == 0.4
    assert adapter.top_p == 0.8
    assert adapter.max_tokens == 200
    assert adapter.timeout == 30

    capped = build_adapter(default_params={"max_tokens": 200}, max_output_tokens=75)
    assert capped.max_tokens == 75

    empty = build_adapter(default_params=None, config=None)
    assert empty.default_params == {}
    assert empty.config == {}
    assert empty.temperature is None
    assert empty.top_p is None
    assert empty.max_tokens is None
    assert empty.timeout == settings.STREAM_HTTP_READ_TIMEOUT


@pytest.mark.parametrize(
    ("thinking", "enabled", "budget", "effort"),
    [
        (None, False, None, None),
        (False, False, None, None),
        ("enabled", True, None, None),
        ({"enabled": False}, False, None, None),
        ({"budget_tokens": "512", "effort": "high"}, True, 512, "high"),
        ({"budget": 256, "reasoning_effort": "low"}, True, 256, "low"),
    ],
)
def test_thinking_shapes(thinking, enabled, budget, effort):
    params = {} if thinking is None else {"thinking": thinking}
    adapter = build_adapter(default_params=params)

    assert adapter.thinking_enabled is enabled
    assert adapter.thinking_budget == budget
    assert adapter.reasoning_effort == effort


def test_thinking_precedence_and_reasoning_timeout_detection():
    adapter = build_adapter(
        default_params={"thinking": {"enabled": True}},
        config={"thinking": False},
    )
    assert adapter.get_effective_thinking(thinking=False) is False
    assert adapter.get_effective_thinking() == {"enabled": True}
    assert adapter.model_uses_reasoning_timeout is True

    configured_effort = build_adapter(config={"reasoning_effort": 3})
    assert configured_effort.reasoning_effort == "3"
    assert configured_effort.model_uses_reasoning_timeout is True

    assert build_adapter("O3-mini").model_uses_reasoning_timeout is True
    assert build_adapter("custom-reasoning-model").model_uses_reasoning_timeout is True
    assert build_adapter().model_uses_reasoning_timeout is False


def test_http_timeout_precedence_and_defaults():
    normal = build_adapter()
    assert normal.http_read_timeout == float(settings.STREAM_HTTP_READ_TIMEOUT)
    assert normal.http_timeout.connect == settings.STREAM_HTTP_CONNECT_TIMEOUT
    assert normal.http_timeout.read == settings.STREAM_HTTP_READ_TIMEOUT
    assert normal.http_timeout.write == settings.STREAM_HTTP_WRITE_TIMEOUT
    assert normal.http_timeout.pool is None

    reasoning = build_adapter("o1-preview")
    assert reasoning.http_read_timeout == float(
        settings.STREAM_HTTP_REASONING_READ_TIMEOUT
    )

    legacy = build_adapter(default_params={"timeout": "44"})
    assert legacy.http_read_timeout == 44.0

    explicit = build_adapter(
        default_params={
            "read_timeout": "55",
            "timeout": "44",
            "connect_timeout": "2.5",
            "write_timeout": 7,
        }
    )
    assert explicit.http_read_timeout == 55.0
    assert explicit.http_timeout.connect == 2.5
    assert explicit.http_timeout.write == 7.0


def test_tools_passthrough_and_response_factories():
    adapter = build_adapter(
        default_params={
            "extra_body": {
                "metadata": {"source": "test"},
                "model": "reserved",
                "messages": [],
            }
        }
    )
    tool = ToolDefinition(
        function=FunctionDefinition(
            name="lookup", description=None, parameters={"type": "object"}
        )
    )

    assert adapter.get_passthrough_body() == {"metadata": {"source": "test"}}
    assert build_adapter(config={"extra_body": "invalid"}).extra_body == {}
    assert adapter.convert_tools(None) is None
    assert adapter.convert_tools([]) is None
    assert adapter.convert_tools([tool]) == [
        {
            "type": "function",
            "function": {
                "name": "lookup",
                "description": "",
                "parameters": {"type": "object"},
            },
        }
    ]

    generated_call = adapter.create_tool_call(None, "lookup", {"query": "x"})
    preserved_call = adapter.create_tool_call("call-1", "lookup", "{}")
    assert generated_call.id
    assert generated_call.function.arguments == '{"query": "x"}'
    assert preserved_call.id == "call-1"
    assert preserved_call.function.arguments == "{}"

    response = adapter.create_response(content="ok", response_id="response-1")
    assert response.id == "response-1"
    assert response.finish_reason == FinishReason.STOP
    assert response.usage == Usage()

    tool_response = adapter.create_response(
        tool_calls=[preserved_call], finish_reason=FinishReason.LENGTH
    )
    assert tool_response.finish_reason == FinishReason.TOOL_CALLS
    assert tool_response.model == "plain-model"

    usage = Usage(prompt_tokens=1, completion_tokens=2, total_tokens=3)
    chunk = adapter.create_stream_chunk(
        content="part",
        reasoning_content="thought",
        tool_calls=[preserved_call],
        finish_reason=FinishReason.STOP,
        usage=usage,
        response_id="chunk-1",
        stream_activity=True,
    )
    assert chunk.id == "chunk-1"
    assert chunk.delta.content == "part"
    assert chunk.delta.reasoning_content == "thought"
    assert chunk.delta.tool_calls == [preserved_call]
    assert chunk.delta.stream_activity is True
    assert chunk.finish_reason == FinishReason.STOP
    assert chunk.usage == usage
