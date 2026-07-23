from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.llm.adapters.chat.xai_adapter import XAIAdapter
from app.llm.types import (
    ContentPart,
    ContentType,
    FinishReason,
    FunctionCall,
    FunctionDefinition,
    ImageContent,
    Message,
    MessageRole,
    ToolCall,
    ToolDefinition,
)


def build_adapter(**default_params):
    model = SimpleNamespace(
        provider="xai",
        model_id="grok-3",
        api_key="test-key",
        base_url="https://example.com/v1",
        config={},
        default_params=default_params,
        max_output_tokens=None,
    )
    return XAIAdapter(model)


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
async def test_chat_builds_xai_request_and_normalizes_reasoning_tools_and_usage():
    response = SimpleNamespace(
        id="response-1",
        choices=[
            SimpleNamespace(
                finish_reason="tool_calls",
                message=SimpleNamespace(
                    content=None,
                    model_extra={"reasoning_content": "reasoning"},
                    tool_calls=[
                        SimpleNamespace(
                            id="call-2",
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
    adapter = build_adapter(
        temperature=0.2,
        top_p=0.8,
        max_tokens=321,
        thinking={"enabled": True, "effort": "high"},
        extra_body={"metadata": {"source": "test"}, "model": "ignored"},
    )
    tools = [
        ToolDefinition(
            function=FunctionDefinition(
                name="lookup", description="Search docs", parameters={"type": "object"}
            )
        )
    ]
    messages = [
        Message(role=MessageRole.USER, content="Find docs"),
        Message(
            role=MessageRole.ASSISTANT,
            content=[
                ContentPart(type=ContentType.TEXT, text="Previous"),
                ContentPart(
                    type=ContentType.IMAGE,
                    image=ImageContent(base64="image-data", format="webp"),
                ),
            ],
            reasoning_content="previous reasoning",
            tool_calls=[
                ToolCall(
                    id="call-1",
                    function=FunctionCall(name="lookup", arguments='{"query":"old"}'),
                )
            ],
        ),
    ]

    with patch("openai.AsyncOpenAI", return_value=client):
        result = await adapter.chat(messages, tools=tools)

    request = client.chat.completions.create.await_args.kwargs
    assert request == {
        "model": "grok-3",
        "messages": [
            {"role": "user", "content": "Find docs"},
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Previous"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/webp;base64,image-data"},
                    },
                ],
                "reasoning_content": "previous reasoning",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "lookup", "arguments": '{"query":"old"}'},
                    }
                ],
            },
        ],
        "temperature": 0.2,
        "top_p": 0.8,
        "max_tokens": 321,
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
        "reasoning_effort": "high",
        "extra_body": {"metadata": {"source": "test"}},
    }
    assert result.reasoning_content == "reasoning"
    assert result.finish_reason is FinishReason.TOOL_CALLS
    assert result.tool_calls[0].id == "call-2"
    assert result.tool_calls[0].function.arguments == '{"query":"docs"}'
    assert result.usage.total_tokens == 14
    client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_chat_defaults_reasoning_effort_to_medium_when_thinking_enabled():
    response = SimpleNamespace(
        id="response-1",
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(
                    content="done", model_extra=None, tool_calls=None
                ),
            )
        ],
        usage=None,
    )
    client = build_client(response)

    with patch("openai.AsyncOpenAI", return_value=client):
        await build_adapter(thinking={"enabled": True}).chat(
            [Message(role=MessageRole.USER, content="Hi")]
        )

    assert (
        client.chat.completions.create.await_args.kwargs["reasoning_effort"] == "medium"
    )
    client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_chat_stream_normalizes_reasoning_tool_activity_and_completion():
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
    stream = AsyncChunks(
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
    client = build_client(stream)

    with patch("openai.AsyncOpenAI", return_value=client):
        result = [
            chunk
            async for chunk in build_adapter(
                temperature=0.1, max_tokens=50
            ).chat_stream([Message(role=MessageRole.USER, content="Hi")])
        ]

    request = client.chat.completions.create.await_args.kwargs
    assert request["stream"] is True
    assert request["temperature"] == 0.1
    assert request["max_tokens"] == 50
    assert result[0].delta.stream_activity is True
    assert result[1].delta.reasoning_content == "thinking"
    assert result[2].delta.stream_activity is True
    assert result[3].delta.content == "answer"
    assert result[3].finish_reason is FinishReason.TOOL_CALLS
    assert result[3].delta.tool_calls[0].function.arguments == '{"query":"docs"}'
    assert len({chunk.id for chunk in result}) == 1
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
