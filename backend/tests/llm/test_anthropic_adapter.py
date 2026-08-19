from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

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


def build_adapter(**default_params):
    model = SimpleNamespace(
        provider="anthropic",
        model_id="claude-test",
        api_key="test-key",
        base_url="https://example.com",
        config={},
        default_params=default_params,
        max_output_tokens=None,
    )
    return AnthropicAdapter(model)


def build_client(*, response=None, stream=None):
    return SimpleNamespace(
        messages=SimpleNamespace(
            create=AsyncMock(return_value=response),
            stream=lambda **kwargs: stream,
        ),
        close=AsyncMock(),
    )


class AsyncStream:
    def __init__(self, events, error=None):
        self.events = list(events)
        self.error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.events:
            return self.events.pop(0)
        if self.error:
            error, self.error = self.error, None
            raise error
        raise StopAsyncIteration


@pytest.mark.anyio
async def test_chat_builds_request_and_normalizes_mixed_response():
    response = SimpleNamespace(
        id="message-1",
        stop_reason="tool_use",
        content=[
            SimpleNamespace(type="thinking", thinking="considering "),
            SimpleNamespace(type="text", text="answer "),
            SimpleNamespace(
                type="tool_use", id="call-1", name="lookup", input={"q": "docs"}
            ),
        ],
        usage=SimpleNamespace(
            input_tokens=9,
            output_tokens=4,
            cache_read_input_tokens=6,
            cache_creation_input_tokens=3,
        ),
    )
    client = build_client(response=response)
    adapter = build_adapter(
        temperature=0.2,
        top_p=0.8,
        max_tokens=321,
        thinking={"enabled": True, "budget_tokens": 1000},
    )
    tools = [
        ToolDefinition(
            function=FunctionDefinition(
                name="lookup", description="Search docs", parameters={"type": "object"}
            )
        )
    ]

    with patch("anthropic.AsyncAnthropic", return_value=client):
        result = await adapter.chat(
            [
                Message(role=MessageRole.SYSTEM, content="Be concise"),
                Message(role=MessageRole.USER, content="Find docs"),
            ],
            tools=tools,
        )

    assert client.messages.create.await_args.kwargs == {
        "model": "claude-test",
        "messages": [{"role": "user", "content": "Find docs"}],
        "max_tokens": 321,
        "system": "Be concise",
        "temperature": 0.2,
        "top_p": 0.8,
        "tools": [
            {
                "name": "lookup",
                "description": "Search docs",
                "input_schema": {"type": "object"},
            }
        ],
        "thinking": {"type": "enabled", "budget_tokens": 1000},
        "extra_body": None,
    }
    assert result.id == "message-1"
    assert result.content == "answer"
    assert result.reasoning_content == "considering"
    assert result.finish_reason is FinishReason.TOOL_CALLS
    assert result.tool_calls[0].function.arguments == '{"q": "docs"}'
    assert result.usage.model_dump() == {
        "prompt_tokens": 9,
        "completion_tokens": 4,
        "total_tokens": 13,
        "cache_read_tokens": 6,
        "cache_creation_tokens": 3,
        "total_input_tokens": 18,
    }
    client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_chat_uses_output_config_without_thinking():
    response = SimpleNamespace(
        id="message-1",
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text='{"ok":true}')],
        usage=None,
    )
    client = build_client(response=response)
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}

    with patch("anthropic.AsyncAnthropic", return_value=client):
        result = await build_adapter(thinking=True).chat(
            [Message(role=MessageRole.USER, content="Reply as JSON")],
            response_format={"type": "json_schema", "json_schema": {"schema": schema}},
        )

    request = client.messages.create.await_args.kwargs
    assert request["output_config"] == {
        "format": {
            "type": "json_schema",
            "schema": {**schema, "additionalProperties": False},
        }
    }
    assert "thinking" not in request
    assert result.finish_reason is FinishReason.STOP
    assert result.usage.total_tokens == 0
    client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_chat_closes_client_when_provider_fails():
    client = build_client()
    client.messages.create.side_effect = RuntimeError("provider failed")

    with (
        patch("anthropic.AsyncAnthropic", return_value=client),
        pytest.raises(RuntimeError, match="provider failed"),
    ):
        await build_adapter().chat([Message(role=MessageRole.USER, content="Hi")])

    client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_chat_stream_normalizes_text_thinking_tool_and_finish_reason():
    events = [
        SimpleNamespace(
            type="content_block_delta",
            delta=SimpleNamespace(type="thinking_delta", thinking="reasoning"),
        ),
        SimpleNamespace(
            type="content_block_delta",
            delta=SimpleNamespace(type="text_delta", text="answer"),
        ),
        SimpleNamespace(
            type="content_block_start",
            content_block=SimpleNamespace(type="tool_use", id="call-1", name="lookup"),
        ),
        SimpleNamespace(
            type="content_block_delta",
            delta=SimpleNamespace(type="input_json_delta", partial_json='{"q":'),
        ),
        SimpleNamespace(
            type="content_block_delta",
            delta=SimpleNamespace(type="input_json_delta", partial_json='"docs"}'),
        ),
        SimpleNamespace(type="content_block_stop"),
        SimpleNamespace(
            type="message_delta", delta=SimpleNamespace(stop_reason="tool_use")
        ),
    ]
    stream = AsyncStream(events)
    client = build_client(stream=stream)

    with patch("anthropic.AsyncAnthropic", return_value=client):
        chunks = [
            chunk
            async for chunk in build_adapter().chat_stream(
                [Message(role=MessageRole.USER, content="Hi")]
            )
        ]

    assert chunks[0].delta.reasoning_content == "reasoning"
    assert chunks[1].delta.content == "answer"
    assert chunks[2].delta.stream_activity is True
    assert chunks[3].delta.stream_activity is True
    assert chunks[4].delta.stream_activity is True
    assert chunks[-1].finish_reason is FinishReason.TOOL_CALLS
    assert chunks[-1].delta.tool_calls[0].id == "call-1"
    assert chunks[-1].delta.tool_calls[0].function.name == "lookup"
    assert chunks[-1].delta.tool_calls[0].function.arguments == '{"q":"docs"}'
    assert len({chunk.id for chunk in chunks}) == 1
    client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_chat_stream_closes_client_when_iteration_fails():
    stream = AsyncStream([], error=RuntimeError("stream failed"))
    client = build_client(stream=stream)

    with (
        patch("anthropic.AsyncAnthropic", return_value=client),
        pytest.raises(RuntimeError, match="stream failed"),
    ):
        async for _ in build_adapter().chat_stream(
            [Message(role=MessageRole.USER, content="Hi")]
        ):
            pass

    client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_chat_stream_captures_usage_from_message_delta():
    events = [
        SimpleNamespace(
            type="content_block_delta",
            delta=SimpleNamespace(type="text_delta", text="answer"),
        ),
        SimpleNamespace(
            type="message_delta",
            delta=SimpleNamespace(stop_reason="end_turn"),
            usage=SimpleNamespace(
                input_tokens=9,
                output_tokens=4,
                cache_read_input_tokens=6,
                cache_creation_input_tokens=3,
            ),
        ),
    ]
    stream = AsyncStream(events)
    client = build_client(stream=stream)

    with patch("anthropic.AsyncAnthropic", return_value=client):
        chunks = [
            chunk
            async for chunk in build_adapter().chat_stream(
                [Message(role=MessageRole.USER, content="Hi")]
            )
        ]

    assert chunks[-1].finish_reason is FinishReason.STOP
    assert chunks[-1].usage.model_dump() == {
        "prompt_tokens": 9,
        "completion_tokens": 4,
        "total_tokens": 13,
        "cache_read_tokens": 6,
        "cache_creation_tokens": 3,
        "total_input_tokens": 18,
    }
    client.close.assert_awaited_once()


LONG_TEXT = "cache me " * 2000  # cl100k 估算远超 1024 token 缓存门槛


def _tool_def():
    return ToolDefinition(
        type="function",
        function=FunctionDefinition(
            name="lookup",
            description="lookup",
            parameters={"type": "object", "properties": {"q": {"type": "string"}}},
        ),
    )


def _tool_use_message():
    return Message(
        role=MessageRole.ASSISTANT,
        content="first answer",
        tool_calls=[
            ToolCall(
                id="call-1",
                type="function",
                function=FunctionCall(name="lookup", arguments='{"q":"x"}'),
            )
        ],
    )


def _tool_result_message():
    return Message(role=MessageRole.TOOL, tool_call_id="call-1", content="tool result")


@pytest.mark.anyio
async def test_chat_adds_cache_breakpoints_to_system_tools_and_history():
    messages = [
        Message(role=MessageRole.SYSTEM, content=LONG_TEXT),
        Message(role=MessageRole.USER, content="first question " + LONG_TEXT),
        _tool_use_message(),
        _tool_result_message(),
        Message(role=MessageRole.USER, content="second question " + LONG_TEXT),
        _tool_use_message(),
        _tool_result_message(),
        Message(role=MessageRole.USER, content="third question " + LONG_TEXT),
    ]
    response = SimpleNamespace(
        id="response-1",
        content=[SimpleNamespace(type="text", text="done")],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=9, output_tokens=4),
    )
    client = build_client(response=response)
    adapter = build_adapter()

    with patch("anthropic.AsyncAnthropic", return_value=client):
        await adapter.chat(messages, tools=[_tool_def()])

    request = client.messages.create.await_args.kwargs
    # system → 块数组 + cache_control
    assert request["system"] == [
        {"type": "text", "text": LONG_TEXT, "cache_control": {"type": "ephemeral"}}
    ]
    # tools → 最后一个工具带 cache_control
    assert request["tools"][-1]["cache_control"] == {"type": "ephemeral"}
    # 第一条 + 倒数第二条真 user 消息打点，当前请求的最后一条 user 不打点
    user_contents = [
        msg["content"] for msg in request["messages"] if msg["role"] == "user"
    ]
    assert len(user_contents) == 5  # 3 真 user + 2 tool_result
    assert user_contents[0][0]["cache_control"] == {"type": "ephemeral"}
    assert user_contents[2][0]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in user_contents[3][0]  # tool_result 不打点
    assert "cache_control" not in user_contents[4][0]  # 当前请求 user 不打点
    client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_chat_stream_adds_cache_breakpoints():
    events = [
        SimpleNamespace(
            type="content_block_delta",
            delta=SimpleNamespace(type="text_delta", text="answer"),
        ),
        SimpleNamespace(
            type="message_delta",
            delta=SimpleNamespace(stop_reason="end_turn"),
            usage=SimpleNamespace(input_tokens=9, output_tokens=4),
        ),
    ]
    stream = AsyncStream(events)
    client = build_client(stream=stream)
    client.messages.stream = Mock(return_value=stream)

    with patch("anthropic.AsyncAnthropic", return_value=client):
        chunks = [
            chunk
            async for chunk in build_adapter().chat_stream(
                [
                    Message(role=MessageRole.SYSTEM, content=LONG_TEXT),
                    Message(role=MessageRole.USER, content="question " + LONG_TEXT),
                ],
                tools=[_tool_def()],
            )
        ]

    request = client.messages.stream.call_args.kwargs
    assert request["system"] == [
        {"type": "text", "text": LONG_TEXT, "cache_control": {"type": "ephemeral"}}
    ]
    assert request["tools"][-1]["cache_control"] == {"type": "ephemeral"}
    assert request["messages"][0]["content"][0]["cache_control"] == {
        "type": "ephemeral"
    }
    assert chunks[-1].finish_reason is FinishReason.STOP
    client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_chat_skips_cache_breakpoints_when_disabled_or_too_short():
    # 开关关闭：即使长前缀也不打点
    adapter = build_adapter()
    adapter.model_config.config = {"cache_control": False}
    response = SimpleNamespace(
        id="response-1",
        content=[SimpleNamespace(type="text", text="done")],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=9, output_tokens=4),
    )
    client = build_client(response=response)
    with patch("anthropic.AsyncAnthropic", return_value=client):
        await adapter.chat(
            [
                Message(role=MessageRole.SYSTEM, content=LONG_TEXT),
                Message(role=MessageRole.USER, content="question"),
            ]
        )
    request = client.messages.create.await_args.kwargs
    assert request["system"] == LONG_TEXT
    assert "cache_control" not in request["messages"][0]["content"]
    client.close.assert_awaited_once()

    # 前缀过短：即使开关开启也不打点
    client = build_client(response=response)
    with patch("anthropic.AsyncAnthropic", return_value=client):
        await build_adapter().chat(
            [
                Message(role=MessageRole.SYSTEM, content="short"),
                Message(role=MessageRole.USER, content="hi"),
            ]
        )
    request = client.messages.create.await_args.kwargs
    assert request["system"] == "short"
    assert request["messages"][0]["content"] == "hi"
    client.close.assert_awaited_once()
