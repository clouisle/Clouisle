from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.llm.adapters.chat.anthropic_adapter import AnthropicAdapter
from app.llm.types import (
    FinishReason,
    FunctionDefinition,
    Message,
    MessageRole,
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
            SimpleNamespace(type="tool_use", id="call-1", name="lookup", input={"q": "docs"}),
        ],
        usage=SimpleNamespace(input_tokens=9, output_tokens=4),
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
