from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.llm.adapters.chat.anthropic_adapter import AnthropicAdapter
from app.llm.types import (
    FinishReason,
    FunctionCall,
    FunctionDefinition,
    Message,
    MessageRole,
    ToolCall,
    ToolDefinition,
)


def obj(**values):
    return SimpleNamespace(**values)


def adapter(**overrides):
    values = {
        "model_id": "claude-test",
        "api_key": "secret",
        "base_url": None,
        "config": {},
        "default_params": {},
        "max_output_tokens": None,
    }
    values.update(overrides)
    return AnthropicAdapter(obj(**values))


def install_client(monkeypatch, *, create=None, stream=None):
    client = obj(
        messages=obj(
            create=create or AsyncMock(),
            stream=stream or AsyncMock(),
        ),
        close=AsyncMock(),
    )
    monkeypatch.setattr("anthropic.AsyncAnthropic", lambda **kwargs: client)
    return client


class Stream:
    def __init__(self, events):
        self.events = iter(events)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    def __aiter__(self):
        return self

    async def __anext__(self):
        event = next(self.events, None)
        if event is None:
            raise StopAsyncIteration
        if isinstance(event, Exception):
            raise event
        return event


def test_converts_message_variants_tools_and_response_blocks():
    anthropic = adapter(default_params={"thinking": True})
    messages = [
        obj(
            role=MessageRole.SYSTEM,
            content=[obj(text="first"), {"text": "second"}, obj(text=None)],
        ),
        obj(
            role=MessageRole.USER,
            content=[
                obj(type=obj(value="text"), text="hello"),
                obj(
                    type="image",
                    image=obj(base64="aW1n", format=None, url=None),
                ),
                obj(
                    type="image",
                    image=obj(base64=None, format="png", url="https://image.invalid/a"),
                ),
                obj(type="image", image=None),
                {"type": "text", "text": "raw"},
            ],
        ),
        obj(
            role=MessageRole.ASSISTANT,
            content=[obj(text="answer"), obj(text=None)],
            reasoning_content="thought",
            tool_calls=[
                ToolCall(
                    id="call-1",
                    function=FunctionCall(name="lookup", arguments='{"q":"x"}'),
                ),
                ToolCall(
                    id="call-2",
                    function=FunctionCall(name="broken", arguments="not-json"),
                ),
            ],
        ),
        obj(
            role=MessageRole.TOOL,
            content=[obj(text="result"), {"text": "more"}],
            tool_call_id="call-1",
        ),
        obj(
            role=MessageRole.ASSISTANT,
            content=None,
            reasoning_content=None,
            tool_calls=None,
        ),
        obj(role=MessageRole.USER, content=[], reasoning_content=None, tool_calls=None),
    ]

    system, converted = anthropic._convert_messages(messages)

    assert system == "first\nsecond"
    assert converted[0]["content"] == [
        {"type": "text", "text": "hello"},
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": "aW1n",
            },
        },
        {
            "type": "image",
            "source": {"type": "url", "url": "https://image.invalid/a"},
        },
        {"type": "text", "text": "raw"},
    ]
    assert converted[1]["content"][-2]["input"] == {"q": "x"}
    assert converted[1]["content"][-1]["input"] == {}
    assert converted[2]["content"][0]["content"] == "result\nmore"
    assert converted[-1] == {"role": "user", "content": ""}

    content, reasoning, calls = anthropic._extract_response(
        obj(
            content=[
                obj(type="text", text=" hello "),
                obj(type="text", text=""),
                obj(type="thinking", thinking=" thought "),
                obj(type="thinking", thinking=""),
                obj(type="tool_use", id="call-3", name="search", input={"q": 1}),
                obj(type="tool_use", id="call-4", name="raw", input="value"),
                obj(type="ignored"),
            ]
        )
    )
    assert content == "hello"
    assert reasoning == "thought"
    assert calls[0].function.arguments == '{"q": 1}'
    assert calls[1].function.arguments == "value"
    assert adapter()._extract_response(obj(content=[])) == (None, None, None)


def test_converts_tools_and_finish_reasons():
    tool = ToolDefinition(
        function=FunctionDefinition(
            name="lookup", description=None, parameters={"type": "object"}
        )
    )
    anthropic = adapter()

    assert anthropic.convert_tools(None) is None
    assert anthropic.convert_tools([tool]) == [
        {
            "name": "lookup",
            "description": "",
            "input_schema": {"type": "object"},
        }
    ]
    assert anthropic._map_finish_reason("tool_use") == FinishReason.TOOL_CALLS
    assert anthropic._map_finish_reason("max_tokens") == FinishReason.LENGTH
    assert anthropic._map_finish_reason("end_turn") == FinishReason.STOP
    assert anthropic._map_finish_reason("stop_sequence") == FinishReason.STOP
    assert anthropic._map_finish_reason("unknown") == FinishReason.STOP


@pytest.mark.anyio
async def test_chat_builds_thinking_request_and_extracts_response(monkeypatch):
    response = obj(
        id="message-1",
        content=[
            obj(type="thinking", thinking="thought"),
            obj(type="text", text="answer"),
            obj(type="tool_use", id="call-1", name="lookup", input={"q": "x"}),
        ],
        stop_reason="tool_use",
        usage=obj(input_tokens=2, output_tokens=3),
    )
    create = AsyncMock(return_value=response)
    client = install_client(monkeypatch, create=create)
    anthropic = adapter(
        base_url="https://anthropic.invalid",
        default_params={
            "temperature": 0.2,
            "top_p": 0.8,
            "max_tokens": 100,
            "thinking": {"enabled": True, "budget_tokens": 50},
            "extra_body": {"custom": True, "response_format": {"type": "json"}},
        },
    )
    tool = ToolDefinition(function=FunctionDefinition(name="lookup"))

    result = await anthropic.chat(
        [
            Message(role=MessageRole.SYSTEM, content="system"),
            Message(role=MessageRole.USER, content="hello"),
        ],
        tools=[tool],
    )

    assert create.await_args.kwargs == {
        "model": "claude-test",
        "messages": [{"role": "user", "content": "hello"}],
        "max_tokens": 100,
        "system": "system",
        "temperature": 0.2,
        "top_p": 0.8,
        "tools": [{"name": "lookup", "description": "", "input_schema": {}}],
        "thinking": {"type": "enabled", "budget_tokens": 50},
        "extra_body": {"custom": True},
    }
    assert result.content == "answer"
    assert result.reasoning_content == "thought"
    assert result.finish_reason == FinishReason.TOOL_CALLS
    assert result.usage.total_tokens == 5
    client.close.assert_awaited_once()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("response_format", "expected_schema"),
    [
        (
            {"type": "json_schema", "json_schema": {"schema": {"type": "object"}}},
            {"type": "object", "additionalProperties": False},
        ),
        (
            {"type": "json_object"},
            {"type": "object", "additionalProperties": False},
        ),
    ],
)
async def test_chat_uses_structured_output_without_thinking(
    monkeypatch, response_format, expected_schema
):
    response = obj(id="message-2", content=[], stop_reason="end_turn", usage=None)
    create = AsyncMock(return_value=response)
    client = install_client(monkeypatch, create=create)

    result = await adapter(default_params={"thinking": True}).chat(
        [Message(role=MessageRole.USER, content="hello")],
        response_format=response_format,
    )

    request = create.await_args.kwargs
    assert request["output_config"]["format"]["schema"] == expected_schema
    assert "thinking" not in request
    assert result.usage.total_tokens == 0
    client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_structured_stream_chunks_content_reasoning_and_final(monkeypatch):
    anthropic = adapter()
    response = anthropic.create_response(
        content="abcdefghijklmnop",
        reasoning_content="thought",
        tool_calls=None,
        finish_reason=FinishReason.STOP,
        response_id="message-3",
    )
    monkeypatch.setattr(anthropic, "chat", AsyncMock(return_value=response))

    chunks = [
        chunk
        async for chunk in anthropic.chat_stream(
            [Message(role=MessageRole.USER, content="hello")],
            response_format={"type": "json_object"},
        )
    ]

    assert [chunk.delta.content for chunk in chunks[:2]] == ["abcdefghij", "klmnop"]
    assert chunks[2].delta.reasoning_content == "thought"
    assert chunks[-1].finish_reason == FinishReason.STOP
    assert chunks[-1].usage.total_tokens == 0


@pytest.mark.anyio
async def test_regular_stream_handles_all_events_and_closes_on_errors(monkeypatch):
    events = [
        obj(type="content_block_start", content_block=None),
        obj(type="content_block_start", content_block=obj(type="text")),
        obj(
            type="content_block_start",
            content_block=obj(type="tool_use", id="call-1", name="lookup"),
        ),
        obj(type="content_block_delta", delta=None),
        obj(type="content_block_delta", delta=obj(type="text_delta", text="answer")),
        obj(type="content_block_delta", delta=obj(type="text_delta", text=None)),
        obj(
            type="content_block_delta",
            delta=obj(type="thinking_delta", thinking="thought"),
        ),
        obj(
            type="content_block_delta", delta=obj(type="thinking_delta", thinking=None)
        ),
        obj(
            type="content_block_delta",
            delta=obj(type="input_json_delta", partial_json='{"q":'),
        ),
        obj(
            type="content_block_delta",
            delta=obj(type="input_json_delta", partial_json='"x"}'),
        ),
        obj(type="content_block_stop"),
        obj(type="content_block_stop"),
        obj(type="message_stop"),
        obj(type="unknown"),
        obj(type="message_delta", delta=None),
        obj(type="message_delta", delta=obj(stop_reason="tool_use")),
    ]
    stream = Stream(events)
    client = install_client(monkeypatch, stream=lambda **kwargs: stream)
    anthropic = adapter(default_params={"thinking": True})

    chunks = [
        chunk
        async for chunk in anthropic.chat_stream(
            [
                Message(role=MessageRole.SYSTEM, content="system"),
                Message(role=MessageRole.USER, content="hello"),
            ]
        )
    ]

    assert chunks[0].delta.stream_activity is True
    assert chunks[1].delta.content == "answer"
    assert chunks[2].delta.reasoning_content == "thought"
    assert chunks[-1].finish_reason == FinishReason.TOOL_CALLS
    assert chunks[-1].delta.tool_calls[0].function.arguments == '{"q":"x"}'
    assert len({chunk.id for chunk in chunks}) == 1
    client.close.assert_awaited_once()

    failing_client = install_client(
        monkeypatch, stream=lambda **kwargs: Stream([RuntimeError("stream failed")])
    )
    with pytest.raises(RuntimeError, match="stream failed"):
        _ = [
            chunk
            async for chunk in adapter().chat_stream(
                [Message(role=MessageRole.USER, content="hello")]
            )
        ]
    failing_client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_chat_closes_client_on_sdk_error(monkeypatch):
    client = install_client(
        monkeypatch, create=AsyncMock(side_effect=RuntimeError("request failed"))
    )

    with pytest.raises(RuntimeError, match="request failed"):
        await adapter().chat([Message(role=MessageRole.USER, content="hello")])

    client.close.assert_awaited_once()
