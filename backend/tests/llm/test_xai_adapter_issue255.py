from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.llm.adapters.chat.xai_adapter import XAIAdapter
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
        "model_id": "grok-test",
        "api_key": "secret",
        "base_url": None,
        "config": {},
        "default_params": {},
        "max_output_tokens": None,
    }
    values.update(overrides)
    return XAIAdapter(obj(**values))


def install_client(create):
    client = obj(chat=obj(completions=obj(create=create)), close=AsyncMock())
    return client, patch("openai.AsyncOpenAI", return_value=client)


class Stream:
    def __init__(self, chunks):
        self.chunks = iter(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        chunk = next(self.chunks, None)
        if chunk is None:
            raise StopAsyncIteration
        if isinstance(chunk, Exception):
            raise chunk
        return chunk


def stream_chunk(delta=None, finish_reason=None, *, choices=True):
    return obj(
        choices=(
            [
                obj(
                    delta=delta
                    or obj(content=None, reasoning_content=None, tool_calls=None),
                    finish_reason=finish_reason,
                )
            ]
            if choices
            else []
        )
    )


def tool_delta(*, index=0, id=None, name=None, arguments=None):
    return obj(
        index=index,
        id=id,
        type="function",
        function=obj(name=name, arguments=arguments),
    )


def test_config_and_message_conversion_cover_reasoning_media_and_tools():
    xai = adapter(
        default_params={
            "thinking": {"enabled": True},
            "extra_body": {
                "custom": {"response_format": "json"},
                "response_format": {"type": "json_object"},
            },
        }
    )
    messages = [
        obj(
            role=MessageRole.USER,
            content=[
                obj(type=obj(value="text"), text="hello"),
                obj(type="image", image=obj(base64="aGVsbG8=", format=None, url=None)),
                obj(
                    type="image",
                    image=obj(
                        base64=None,
                        format=None,
                        url="https://image.invalid/a.png",
                    ),
                ),
                obj(type="image", image=None),
                obj(type="audio"),
                {"type": "text", "text": "raw"},
                "ignored",
            ],
            reasoning_content=None,
            tool_calls=None,
            tool_call_id=None,
        ),
        Message(
            role=MessageRole.ASSISTANT,
            content=None,
            reasoning_content="thought",
            tool_calls=[
                ToolCall(
                    id="call-1",
                    function=FunctionCall(name="lookup", arguments='{"q":"x"}'),
                )
            ],
        ),
        Message(role=MessageRole.ASSISTANT, content="plain"),
        Message(role=MessageRole.TOOL, content=None, tool_call_id="call-1"),
    ]

    converted = xai._convert_messages(messages)

    assert xai.reasoning_effort == "medium"
    assert xai.get_passthrough_body() == {"custom": {"response_format": "json"}}
    assert converted[0]["content"] == [
        {"type": "text", "text": "hello"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,aGVsbG8="}},
        {"type": "image_url", "image_url": {"url": "https://image.invalid/a.png"}},
        {"type": "text", "text": "raw"},
    ]
    assert converted[1]["reasoning_content"] == "thought"
    assert converted[1]["tool_calls"][0]["function"]["name"] == "lookup"
    assert converted[2] == {"role": "assistant", "content": "plain"}
    assert converted[3] == {"role": "tool", "content": "", "tool_call_id": "call-1"}
    assert adapter().reasoning_effort is None
    assert (
        adapter(default_params={"reasoning_effort": "high"}).reasoning_effort == "high"
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("provider_reason", "expected"),
    [
        ("tool_calls", FinishReason.TOOL_CALLS),
        ("length", FinishReason.LENGTH),
        ("content_filter", FinishReason.CONTENT_FILTER),
        ("stop", FinishReason.STOP),
    ],
)
async def test_chat_builds_request_and_maps_responses(provider_reason, expected):
    response = obj(
        id="response-1",
        choices=[
            obj(
                finish_reason=provider_reason,
                message=obj(
                    content="answer",
                    reasoning_content="thought",
                    model_extra=None,
                    tool_calls=(
                        [obj(id="call-1", function=obj(name="lookup", arguments="{}"))]
                        if provider_reason == "tool_calls"
                        else None
                    ),
                ),
            )
        ],
        usage=obj(prompt_tokens=2, completion_tokens=3, total_tokens=5),
    )
    create = AsyncMock(return_value=response)
    client, client_patch = install_client(create)
    xai = adapter(
        base_url="https://xai.invalid/v1",
        default_params={
            "temperature": 0.2,
            "top_p": 0.8,
            "max_tokens": 100,
            "thinking": {"enabled": True, "effort": "high"},
            "extra_body": {"seed": 7, "model": "ignored"},
        },
    )
    tool = ToolDefinition(
        function=FunctionDefinition(
            name="lookup", description="Search", parameters={"type": "object"}
        )
    )

    with client_patch as factory:
        result = await xai.chat(
            [Message(role=MessageRole.USER, content="hello")], tools=[tool]
        )

    assert factory.call_args.kwargs["base_url"] == "https://xai.invalid/v1"
    assert create.await_args.kwargs == {
        "model": "grok-test",
        "messages": [{"role": "user", "content": "hello"}],
        "temperature": 0.2,
        "top_p": 0.8,
        "max_tokens": 100,
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "lookup",
                    "description": "Search",
                    "parameters": {"type": "object"},
                },
            }
        ],
        "reasoning_effort": "high",
        "extra_body": {"seed": 7},
    }
    assert result.finish_reason == expected
    assert result.reasoning_content == "thought"
    assert result.usage.total_tokens == 5
    assert bool(result.tool_calls) == (provider_reason == "tool_calls")
    client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_chat_handles_empty_usage_and_closes_on_sdk_error():
    response = obj(
        id="response-2",
        choices=[
            obj(
                finish_reason="stop",
                message=obj(
                    content=None,
                    reasoning_content=None,
                    model_extra=None,
                    tool_calls=None,
                ),
            )
        ],
        usage=None,
    )
    client, client_patch = install_client(AsyncMock(return_value=response))
    with client_patch:
        result = await adapter().chat([Message(role="user", content="hello")])
    assert result.usage.total_tokens == 0
    client.close.assert_awaited_once()

    client, client_patch = install_client(AsyncMock(side_effect=RuntimeError("failed")))
    with client_patch, pytest.raises(RuntimeError, match="failed"):
        await adapter().chat([Message(role="user", content="hello")])
    client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_chat_stream_covers_activity_content_reasoning_tools_and_finishes():
    chunks = [
        stream_chunk(choices=False),
        stream_chunk(obj(content="answer", reasoning_content=None, tool_calls=None)),
        stream_chunk(obj(content=None, reasoning_content="thought", tool_calls=None)),
        stream_chunk(
            obj(
                content=None,
                reasoning_content=None,
                tool_calls=[tool_delta(id="call-1", name="lookup", arguments="{")],
            )
        ),
        stream_chunk(
            obj(
                content=None,
                reasoning_content=None,
                tool_calls=[tool_delta(arguments="}")],
            ),
            "tool_calls",
        ),
        stream_chunk(finish_reason="stop"),
        stream_chunk(finish_reason="length"),
        stream_chunk(finish_reason="content_filter"),
        stream_chunk(finish_reason="unknown"),
        stream_chunk(),
    ]
    create = AsyncMock(return_value=Stream(chunks))
    client, client_patch = install_client(create)
    xai = adapter(
        default_params={
            "temperature": 0.1,
            "top_p": 0.9,
            "max_tokens": 50,
            "thinking": True,
            "extra_body": {"structured_outputs": True},
        }
    )
    tool = ToolDefinition(function=FunctionDefinition(name="lookup"))

    with client_patch:
        result = [
            chunk
            async for chunk in xai.chat_stream(
                [Message(role="user", content="hello")], tools=[tool]
            )
        ]

    request = create.await_args.kwargs
    assert request["stream"] is True
    assert request["temperature"] == 0.1
    assert request["top_p"] == 0.9
    assert request["max_tokens"] == 50
    assert request["tools"][0]["function"]["name"] == "lookup"
    assert request["reasoning_effort"] == "medium"
    assert request["extra_body"] == {"structured_outputs": True}
    assert result[0].delta.stream_activity is True
    assert result[1].delta.content == "answer"
    assert result[2].delta.reasoning_content == "thought"
    assert result[3].delta.stream_activity is True
    assert result[4].delta.tool_calls[0].function.arguments == "{}"
    assert [chunk.finish_reason for chunk in result[4:]] == [
        FinishReason.TOOL_CALLS,
        FinishReason.STOP,
        FinishReason.LENGTH,
        FinishReason.CONTENT_FILTER,
    ]
    client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_chat_stream_closes_client_on_sdk_error():
    client, client_patch = install_client(
        AsyncMock(return_value=Stream([RuntimeError("stream failed")]))
    )
    with client_patch, pytest.raises(RuntimeError, match="stream failed"):
        _ = [
            chunk
            async for chunk in adapter().chat_stream(
                [Message(role="user", content="hello")]
            )
        ]
    client.close.assert_awaited_once()
