from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.llm.adapters.chat.moonshot_adapter import MoonshotAdapter
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
        "model_id": "kimi-test",
        "api_key": "secret",
        "base_url": None,
        "config": {},
        "default_params": {},
        "max_output_tokens": None,
    }
    values.update(overrides)
    return MoonshotAdapter(obj(**values))


def install_client(monkeypatch, create):
    client = obj(chat=obj(completions=obj(create=create)), close=AsyncMock())
    monkeypatch.setattr("openai.AsyncOpenAI", lambda **kwargs: client)
    return client


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


def tool_delta(*, id=None, name=None, arguments=None):
    return obj(
        index=0,
        id=id,
        type="function",
        function=obj(name=name, arguments=arguments),
    )


def test_converts_multimodal_reasoning_and_tool_history():
    call = ToolCall(
        id="call-1",
        function=FunctionCall(name="lookup", arguments='{"q":"moon"}'),
    )
    messages = [
        obj(
            role=MessageRole.USER,
            content=[
                obj(type=obj(value="text"), text="look"),
                obj(type="image", image=obj(base64="aW1n", format=None, url=None)),
                obj(
                    type="image",
                    image=obj(
                        base64=None,
                        format=None,
                        url="https://image.invalid/moon.png",
                    ),
                ),
                obj(type="image", image=None),
                {"type": "text", "text": "raw"},
                None,
                obj(type="ignored"),
            ],
            reasoning_content=None,
            tool_calls=None,
            tool_call_id=None,
        ),
        Message(
            role=MessageRole.ASSISTANT,
            content=None,
            reasoning_content="preserved thought",
            tool_calls=[call],
        ),
        Message(role=MessageRole.TOOL, content="result", tool_call_id="call-1"),
        Message(role=MessageRole.ASSISTANT, content="plain answer"),
        Message(role=MessageRole.USER, content=[]),
    ]

    converted = adapter()._convert_messages(messages)

    assert converted == [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "look"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,aW1n"},
                },
                {
                    "type": "image_url",
                    "image_url": {"url": "https://image.invalid/moon.png"},
                },
                {"type": "text", "text": "raw"},
            ],
        },
        {
            "role": "assistant",
            "content": "",
            "reasoning_content": "preserved thought",
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {
                        "name": "lookup",
                        "arguments": '{"q":"moon"}',
                    },
                }
            ],
        },
        {"role": "tool", "content": "result", "tool_call_id": "call-1"},
        {"role": "assistant", "content": "plain answer"},
        {"role": "user", "content": ""},
    ]


@pytest.mark.anyio
async def test_chat_sends_tools_thinking_and_structured_passthrough(monkeypatch):
    response = obj(
        id="response-1",
        choices=[
            obj(
                message=obj(
                    content='{"answer":true}',
                    reasoning_content=None,
                    model_extra={"reasoning_content": "thought"},
                    tool_calls=[
                        obj(
                            id="call-1",
                            function=obj(name="lookup", arguments='{"q":"moon"}'),
                        )
                    ],
                ),
                finish_reason="tool_calls",
            )
        ],
        usage=obj(prompt_tokens=2, completion_tokens=3, total_tokens=5),
    )
    create = AsyncMock(return_value=response)
    client = install_client(monkeypatch, create)
    moonshot = adapter(
        base_url="https://moonshot.invalid/v1",
        default_params={
            "temperature": 0.2,
            "top_p": 0.8,
            "max_tokens": 100,
            "thinking": {"type": "enabled", "keep": "all"},
            "extra_body": {
                "response_format": {"type": "json_object"},
                "structured_outputs": True,
            },
        },
    )
    tool = ToolDefinition(
        function=FunctionDefinition(
            name="lookup", description="Search", parameters={"type": "object"}
        )
    )

    result = await moonshot.chat(
        [Message(role=MessageRole.USER, content="hello")], tools=[tool]
    )

    assert create.await_args.kwargs == {
        "model": "kimi-test",
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
        "thinking": {"type": "enabled", "keep": "all"},
        "extra_body": {"structured_outputs": True},
    }
    assert result.content == '{"answer":true}'
    assert result.reasoning_content == "thought"
    assert result.finish_reason == FinishReason.TOOL_CALLS
    assert result.tool_calls[0].function.name == "lookup"
    assert result.usage.total_tokens == 5
    client.close.assert_awaited_once()


@pytest.mark.parametrize(
    ("provider_reason", "expected"),
    [
        ("stop", FinishReason.STOP),
        ("length", FinishReason.LENGTH),
        ("content_filter", FinishReason.CONTENT_FILTER),
    ],
)
@pytest.mark.anyio
async def test_chat_maps_finish_reasons_without_optional_fields(
    monkeypatch, provider_reason, expected
):
    response = obj(
        id="response-2",
        choices=[
            obj(
                message=obj(
                    content=None,
                    reasoning_content=None,
                    model_extra=None,
                    tool_calls=None,
                ),
                finish_reason=provider_reason,
            )
        ],
        usage=None,
    )
    client = install_client(monkeypatch, AsyncMock(return_value=response))

    result = await adapter().chat([Message(role=MessageRole.USER, content="hello")])

    assert result.finish_reason == expected
    assert result.usage.total_tokens == 0
    assert client.chat.completions.create.await_args.kwargs["thinking"] == {
        "type": "disabled"
    }
    assert client.chat.completions.create.await_args.kwargs["extra_body"] is None
    client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_stream_emits_activity_content_reasoning_tools_and_finishes(monkeypatch):
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
    moonshot = adapter(
        default_params={
            "temperature": 0.1,
            "top_p": 0.9,
            "max_tokens": 50,
            "thinking": True,
        }
    )

    tool = ToolDefinition(function=FunctionDefinition(name="lookup"))
    result = [
        chunk
        async for chunk in moonshot.chat_stream(
            [Message(role=MessageRole.USER, content="hello")], tools=[tool]
        )
    ]

    request = create.await_args.kwargs
    assert request["stream"] is True
    assert request["tools"][0]["function"]["name"] == "lookup"
    assert request["thinking"] == {"type": "enabled"}
    assert request["temperature"] == 0.1
    assert request["top_p"] == 0.9
    assert request["max_tokens"] == 50
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
    assert len({chunk.id for chunk in result}) == 1
    client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_chat_and_stream_close_clients_on_sdk_errors(monkeypatch):
    client = install_client(
        monkeypatch, AsyncMock(side_effect=RuntimeError("request failed"))
    )
    with pytest.raises(RuntimeError, match="request failed"):
        await adapter().chat([Message(role=MessageRole.USER, content="hello")])
    client.close.assert_awaited_once()

    client = install_client(
        monkeypatch, AsyncMock(return_value=Stream([RuntimeError("stream failed")]))
    )
    with pytest.raises(RuntimeError, match="stream failed"):
        _ = [
            chunk
            async for chunk in adapter().chat_stream(
                [Message(role=MessageRole.USER, content="hello")]
            )
        ]
    client.close.assert_awaited_once()
