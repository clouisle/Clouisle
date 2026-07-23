from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.llm.adapters.chat.openai_adapter import OpenAIAdapter
from app.llm.types import (
    FinishReason,
    FunctionDefinition,
    Message,
    MessageRole,
    ToolDefinition,
)


def build_adapter(**default_params):
    model = SimpleNamespace(
        provider="openai",
        model_id="gpt-4.1",
        api_key="test-key",
        base_url="https://example.com/v1",
        config={},
        default_params=default_params,
        max_output_tokens=None,
    )
    return OpenAIAdapter(model)


def build_client(result):
    return SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=AsyncMock(return_value=result))
        ),
        close=AsyncMock(),
    )


class AsyncChunks:
    def __init__(self, chunks):
        self.chunks = chunks

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.chunks:
            raise StopAsyncIteration
        return self.chunks.pop(0)


@pytest.mark.anyio
async def test_chat_builds_request_and_normalizes_tool_response():
    adapter = build_adapter(temperature=0.2, top_p=0.8, max_tokens=321)
    response = SimpleNamespace(
        id="response-1",
        choices=[
            SimpleNamespace(
                finish_reason="tool_calls",
                message=SimpleNamespace(
                    content=None,
                    reasoning_content="reasoning",
                    model_extra=None,
                    tool_calls=[
                        SimpleNamespace(
                            id="call-1",
                            function=SimpleNamespace(
                                name="lookup", arguments='{"query":"docs"}'
                            ),
                        )
                    ],
                ),
            )
        ],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=4, total_tokens=14),
    )
    client = build_client(response)
    tools = [
        ToolDefinition(
            function=FunctionDefinition(
                name="lookup",
                description="Search docs",
                parameters={"type": "object"},
            )
        )
    ]

    with patch("openai.AsyncOpenAI", return_value=client) as client_class:
        result = await adapter.chat(
            [Message(role=MessageRole.USER, content="Find docs")],
            tools=tools,
            response_format={"type": "json_object"},
        )

    request = client.chat.completions.create.await_args.kwargs
    assert request == {
        "model": "gpt-4.1",
        "messages": [{"role": "user", "content": "Find docs"}],
        "temperature": 0.2,
        "top_p": 0.8,
        "max_completion_tokens": 321,
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "lookup",
                    "description": "Search docs",
                    "parameters": {"type": "object"},
                },
            }
        ],
        "response_format": {"type": "json_object"},
        "extra_body": None,
    }
    assert result.id == "response-1"
    assert result.reasoning_content == "reasoning"
    assert result.finish_reason is FinishReason.TOOL_CALLS
    assert result.tool_calls[0].id == "call-1"
    assert result.tool_calls[0].function.name == "lookup"
    assert result.tool_calls[0].function.arguments == '{"query":"docs"}'
    assert result.usage.model_dump() == {
        "prompt_tokens": 10,
        "completion_tokens": 4,
        "total_tokens": 14,
    }
    client_class.assert_called_once()
    client.close.assert_awaited_once()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("provider_reason", "expected"),
    [
        ("stop", FinishReason.STOP),
        ("length", FinishReason.LENGTH),
        ("content_filter", FinishReason.CONTENT_FILTER),
        ("unknown", FinishReason.STOP),
    ],
)
async def test_chat_maps_finish_reason_without_usage(provider_reason, expected):
    response = SimpleNamespace(
        id="response-1",
        choices=[
            SimpleNamespace(
                finish_reason=provider_reason,
                message=SimpleNamespace(content="done", tool_calls=None),
            )
        ],
        usage=None,
    )
    client = build_client(response)

    with patch("openai.AsyncOpenAI", return_value=client):
        result = await build_adapter().chat(
            [Message(role=MessageRole.USER, content="Hi")]
        )

    assert result.finish_reason is expected
    assert result.usage.total_tokens == 0
    client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_chat_closes_client_when_request_fails():
    client = build_client(None)
    client.chat.completions.create.side_effect = RuntimeError("provider failed")

    with (
        patch("openai.AsyncOpenAI", return_value=client),
        pytest.raises(RuntimeError, match="provider failed"),
    ):
        await build_adapter().chat([Message(role=MessageRole.USER, content="Hi")])

    client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_chat_stream_builds_request_and_normalizes_activity_content_and_tools():
    tool_start = SimpleNamespace(
        index=0,
        id="call-1",
        type="function",
        function=SimpleNamespace(name="lookup", arguments='{"query":'),
    )
    tool_end = SimpleNamespace(
        index=0,
        id=None,
        type=None,
        function=SimpleNamespace(name=None, arguments='"docs"}'),
    )
    chunks = AsyncChunks(
        [
            SimpleNamespace(choices=[]),
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(
                            content=None,
                            reasoning_content="thinking",
                            tool_calls=None,
                        ),
                        finish_reason=None,
                    )
                ]
            ),
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content=None, tool_calls=[tool_start]),
                        finish_reason=None,
                    )
                ]
            ),
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content="answer", tool_calls=[tool_end]),
                        finish_reason="tool_calls",
                    )
                ]
            ),
        ]
    )
    client = build_client(chunks)
    adapter = build_adapter(temperature=0.1, max_tokens=50)

    with patch("openai.AsyncOpenAI", return_value=client):
        result = [
            chunk
            async for chunk in adapter.chat_stream(
                [Message(role=MessageRole.USER, content="Hi")],
                response_format={"type": "json_object"},
            )
        ]

    request = client.chat.completions.create.await_args.kwargs
    assert request["stream"] is True
    assert request["temperature"] == 0.1
    assert request["max_completion_tokens"] == 50
    assert request["response_format"] == {"type": "json_object"}
    assert result[0].delta.stream_activity is True
    assert result[1].delta.reasoning_content == "thinking"
    assert result[2].delta.stream_activity is True
    assert result[3].delta.content == "answer"
    assert result[3].finish_reason is FinishReason.TOOL_CALLS
    assert result[3].delta.tool_calls[0].id == "call-1"
    assert result[3].delta.tool_calls[0].function.arguments == '{"query":"docs"}'
    assert len({chunk.id for chunk in result}) == 1
    client.close.assert_awaited_once()
