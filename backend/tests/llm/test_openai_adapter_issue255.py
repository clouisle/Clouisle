from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.llm.adapters.chat.openai_adapter import OpenAIAdapter
from app.llm.types import (
    ContentType,
    FinishReason,
    FunctionCall,
    FunctionDefinition,
    Message,
    MessageRole,
    ToolCall,
    ToolDefinition,
)


def adapter(**overrides):
    values = {
        "model_id": "gpt-test",
        "api_key": "secret",
        "base_url": "https://openai.invalid",
        "config": {},
        "default_params": {},
        "max_output_tokens": None,
    }
    values.update(overrides)
    return OpenAIAdapter(SimpleNamespace(**values))


def obj(**values):
    return SimpleNamespace(**values)


def install_client(monkeypatch, create):
    client = obj(
        chat=obj(completions=obj(create=create)),
        close=AsyncMock(),
    )

    def factory(**kwargs):
        return client

    monkeypatch.setattr("openai.AsyncOpenAI", factory)
    return client


def tool_delta(*, index=0, id=None, name=None, arguments=None):
    return obj(
        index=index,
        id=id,
        type="function",
        function=obj(name=name, arguments=arguments),
    )


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


class Stream:
    def __init__(self, chunks):
        self.chunks = chunks

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.chunks:
            raise StopAsyncIteration
        chunk = self.chunks.pop(0)
        if isinstance(chunk, Exception):
            raise chunk
        return chunk


def test_convert_messages_covers_multimodal_tools_and_empty_content():
    openai = adapter()
    messages = [
        obj(
            role=MessageRole.USER,
            content=[
                obj(type=ContentType.TEXT, text="hello"),
                obj(
                    type="image", image=obj(base64="aGVsbG8=", format="jpeg", url=None)
                ),
                obj(
                    type="image",
                    image=obj(base64=None, url="https://image.invalid/a.png"),
                ),
                obj(type="image_url", image_url={"url": "https://image.invalid/b.png"}),
                {"type": "text", "text": "raw"},
            ],
            tool_calls=None,
            tool_call_id=None,
        ),
        obj(
            role="assistant",
            content=[],
            tool_calls=[
                ToolCall(
                    id="call-1",
                    function=FunctionCall(name="lookup", arguments='{"q":"x"}'),
                )
            ],
            tool_call_id=None,
        ),
        obj(
            role=MessageRole.TOOL,
            content=None,
            tool_calls=None,
            tool_call_id="call-1",
        ),
    ]

    converted = openai._convert_messages(messages)

    assert converted[0] == {
        "role": "user",
        "content": [
            {"type": "text", "text": "hello"},
            {
                "type": "image_url",
                "image_url": {"url": "data:image/jpeg;base64,aGVsbG8="},
            },
            {
                "type": "image_url",
                "image_url": {"url": "https://image.invalid/a.png"},
            },
            {"type": "image_url", "image_url": {"url": "https://image.invalid/b.png"}},
            {"type": "text", "text": "raw"},
        ],
    }
    assert converted[1]["content"] == ""
    assert converted[1]["tool_calls"][0]["function"]["name"] == "lookup"
    assert converted[2] == {"role": "tool", "content": "", "tool_call_id": "call-1"}


@pytest.mark.anyio
async def test_chat_builds_full_request_and_extracts_tool_reasoning_usage(monkeypatch):
    message = obj(
        content="answer",
        reasoning_content=None,
        model_extra={"reasoning_content": "thought"},
        tool_calls=[obj(id="call-1", function=obj(name="lookup", arguments="{}"))],
    )
    response = obj(
        id="response-1",
        choices=[obj(message=message, finish_reason="tool_calls")],
        usage=obj(prompt_tokens=2, completion_tokens=3, total_tokens=5),
    )
    create = AsyncMock(return_value=response)
    client = install_client(monkeypatch, create)
    openai = adapter(
        default_params={
            "temperature": 0.2,
            "top_p": 0.8,
            "max_tokens": 100,
            "thinking": {"enabled": True, "effort": "high"},
            "extra_body": {"seed": 7, "model": "ignored"},
        }
    )
    tool = ToolDefinition(
        function=FunctionDefinition(
            name="lookup", description="Search", parameters={"type": "object"}
        )
    )
    response_format = {"type": "json_schema", "json_schema": {"name": "answer"}}

    result = await openai.chat(
        [Message(role=MessageRole.USER, content="hello")],
        tools=[tool],
        response_format=response_format,
    )

    request = create.await_args.kwargs
    assert request == {
        "model": "gpt-test",
        "messages": [{"role": "user", "content": "hello"}],
        "temperature": 0.2,
        "top_p": 0.8,
        "max_completion_tokens": 100,
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
        "response_format": response_format,
        "extra_body": {"seed": 7},
    }
    assert result.id == "response-1"
    assert result.reasoning_content == "thought"
    assert result.finish_reason == FinishReason.TOOL_CALLS
    assert result.tool_calls and result.tool_calls[0].function.name == "lookup"
    assert result.usage.total_tokens == 5
    client.close.assert_awaited_once()


@pytest.mark.parametrize(
    ("provider_reason", "expected"),
    [
        ("length", FinishReason.LENGTH),
        ("content_filter", FinishReason.CONTENT_FILTER),
        ("stop", FinishReason.STOP),
    ],
)
@pytest.mark.anyio
async def test_chat_maps_finish_reasons_without_usage(
    monkeypatch, provider_reason, expected
):
    response = obj(
        id="response-2",
        choices=[
            obj(
                message=obj(content=None, reasoning_content=None, tool_calls=None),
                finish_reason=provider_reason,
            )
        ],
        usage=None,
    )
    client = install_client(monkeypatch, AsyncMock(return_value=response))

    result = await adapter().chat([Message(role="user", content="hello")])

    assert result.finish_reason == expected
    assert result.usage.total_tokens == 0
    client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_chat_stream_emits_activity_content_reasoning_tools_and_finishes(
    monkeypatch,
):
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
    client = install_client(monkeypatch, create)
    openai = adapter(
        default_params={
            "temperature": 0.1,
            "top_p": 0.9,
            "max_tokens": 50,
            "thinking": {"enabled": True, "reasoning_effort": "medium"},
        }
    )

    result = [
        chunk
        async for chunk in openai.chat_stream(
            [Message(role="user", content="hello")],
            tools=[
                ToolDefinition(
                    function=FunctionDefinition(name="lookup", description="Search")
                )
            ],
            response_format={"type": "json_object"},
        )
    ]

    request = create.await_args.kwargs
    assert request["stream"] is True
    assert request["tools"][0]["function"]["name"] == "lookup"
    assert request["reasoning_effort"] == "medium"
    assert request["response_format"] == {"type": "json_object"}
    assert result[0].delta.stream_activity is True
    assert result[1].delta.content == "answer"
    assert result[2].delta.reasoning_content == "thought"
    assert result[3].delta.stream_activity is True
    assert result[4].finish_reason == FinishReason.TOOL_CALLS
    assert result[4].delta.tool_calls
    assert result[4].delta.tool_calls[0].function.arguments == "{}"
    assert [chunk.finish_reason for chunk in result[5:]] == [
        FinishReason.STOP,
        FinishReason.LENGTH,
        FinishReason.CONTENT_FILTER,
    ]
    client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_chat_and_stream_close_clients_on_sdk_errors(monkeypatch):
    create = AsyncMock(side_effect=RuntimeError("request failed"))
    client = install_client(monkeypatch, create)
    with pytest.raises(RuntimeError, match="request failed"):
        await adapter().chat([Message(role="user", content="hello")])
    client.close.assert_awaited_once()

    create = AsyncMock(return_value=Stream([RuntimeError("stream failed")]))
    client = install_client(monkeypatch, create)
    with pytest.raises(RuntimeError, match="stream failed"):
        _ = [
            chunk
            async for chunk in adapter().chat_stream(
                [Message(role="user", content="hello")]
            )
        ]
    client.close.assert_awaited_once()
