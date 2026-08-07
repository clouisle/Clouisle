from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.llm.adapters.chat.ollama_adapter import OllamaAdapter
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
        "model_id": "qwen-test",
        "api_key": None,
        "base_url": None,
        "config": {},
        "default_params": {},
        "max_output_tokens": None,
    }
    values.update(overrides)
    return OllamaAdapter(obj(**values))


def install_client(monkeypatch, create):
    client = obj(chat=obj(completions=obj(create=create)), close=AsyncMock())
    monkeypatch.setattr("openai.AsyncOpenAI", lambda **kwargs: client)
    return client


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
                    or obj(
                        content=None, thinking=None, model_extra=None, tool_calls=None
                    ),
                    finish_reason=finish_reason,
                )
            ]
            if choices
            else []
        )
    )


def tool_delta(*, call_id=None, name=None, arguments=None):
    return obj(
        index=0,
        id=call_id,
        type="function",
        function=obj(name=name, arguments=arguments),
    )


def test_converts_multimodal_assistant_and_tool_history():
    converted = adapter()._convert_messages(
        [
            obj(
                role=MessageRole.USER,
                content=[
                    obj(type=obj(value="text"), text="hello"),
                    obj(type="image", image=obj(base64="aW1n", format=None, url=None)),
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
            Message(role=MessageRole.TOOL, content=None, tool_call_id="call-1"),
            Message(role=MessageRole.ASSISTANT, content="plain"),
            Message(role=MessageRole.USER, content=[]),
        ]
    )

    assert converted == [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "hello"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,aW1n"},
                },
                {
                    "type": "image_url",
                    "image_url": {"url": "https://image.invalid/a.png"},
                },
                {"type": "text", "text": "raw"},
            ],
        },
        {
            "role": "assistant",
            "content": "",
            "thinking": "thought",
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "lookup", "arguments": '{"q":"x"}'},
                }
            ],
        },
        {"role": "tool", "content": "", "tool_call_id": "call-1"},
        {"role": "assistant", "content": "plain"},
        {"role": "user", "content": ""},
    ]


@pytest.mark.parametrize(
    ("provider_reason", "expected"),
    [
        ("stop", FinishReason.STOP),
        ("tool_calls", FinishReason.TOOL_CALLS),
        ("length", FinishReason.LENGTH),
        ("content_filter", FinishReason.CONTENT_FILTER),
    ],
)
@pytest.mark.anyio
async def test_chat_builds_request_and_maps_response(
    monkeypatch, provider_reason, expected
):
    response = obj(
        id="response-1",
        choices=[
            obj(
                finish_reason=provider_reason,
                message=obj(
                    content="answer",
                    thinking=None,
                    model_extra={"thinking": "thought"},
                    tool_calls=(
                        [
                            obj(
                                id="call-1",
                                function=obj(name="lookup", arguments="{}"),
                            )
                        ]
                        if provider_reason == "tool_calls"
                        else None
                    ),
                ),
            )
        ],
        usage=obj(prompt_tokens=2, completion_tokens=3, total_tokens=5),
    )
    create = AsyncMock(return_value=response)
    client = install_client(monkeypatch, create)
    ollama = adapter(
        api_key="secret",
        base_url="https://ollama.invalid/v1",
        default_params={
            "temperature": 0.2,
            "top_p": 0.8,
            "max_tokens": 100,
            "thinking": {"enabled": True},
            "extra_body": {"keep_alive": "5m"},
        },
    )
    tool = ToolDefinition(function=FunctionDefinition(name="lookup"))

    result = await ollama.chat(
        [Message(role=MessageRole.USER, content="hello")], tools=[tool]
    )

    request = create.await_args.kwargs
    assert request["temperature"] == 0.2
    assert request["top_p"] == 0.8
    assert request["max_tokens"] == 100
    assert request["tools"][0]["function"]["name"] == "lookup"
    assert "think" not in request
    assert request["extra_body"] == {"keep_alive": "5m", "think": True}
    assert result.finish_reason == expected
    assert result.reasoning_content == "thought"
    if provider_reason == "tool_calls":
        assert result.tool_calls[0].function.name == "lookup"
    else:
        assert result.tool_calls is None
    assert result.usage.total_tokens == 5
    client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_chat_defaults_usage_and_closes_client_on_sdk_error(monkeypatch):
    response = obj(
        id="response-2",
        choices=[
            obj(
                finish_reason=None,
                message=obj(
                    content=None,
                    thinking=None,
                    model_extra=None,
                    tool_calls=None,
                ),
            )
        ],
        usage=None,
    )
    client = install_client(monkeypatch, AsyncMock(return_value=response))

    result = await adapter().chat([Message(role=MessageRole.USER, content="hello")])

    assert result.finish_reason == FinishReason.STOP
    assert result.usage.total_tokens == 0
    client.close.assert_awaited_once()

    client = install_client(
        monkeypatch, AsyncMock(side_effect=RuntimeError("request failed"))
    )
    with pytest.raises(RuntimeError, match="request failed"):
        await adapter().chat([Message(role=MessageRole.USER, content="hello")])
    client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_stream_emits_activity_content_reasoning_tools_and_finish_reasons(
    monkeypatch,
):
    chunks = [
        stream_chunk(choices=False),
        stream_chunk(
            obj(content="answer", thinking=None, model_extra=None, tool_calls=None)
        ),
        stream_chunk(
            obj(content=None, thinking="thought", model_extra=None, tool_calls=None)
        ),
        stream_chunk(
            obj(
                content=None,
                thinking=None,
                model_extra=None,
                tool_calls=[tool_delta(call_id="call-1", name="lookup", arguments="{")],
            )
        ),
        stream_chunk(
            obj(
                content=None,
                thinking=None,
                model_extra=None,
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
    ollama = adapter(
        default_params={
            "temperature": 0.1,
            "top_p": 0.9,
            "max_tokens": 50,
            "thinking": {"enabled": True},
        }
    )

    result = [
        chunk
        async for chunk in ollama.chat_stream(
            [Message(role=MessageRole.USER, content="hello")],
            tools=[ToolDefinition(function=FunctionDefinition(name="lookup"))],
        )
    ]

    request = create.await_args.kwargs
    assert request["stream"] is True
    assert request["temperature"] == 0.1
    assert request["top_p"] == 0.9
    assert request["max_tokens"] == 50
    assert request["tools"][0]["function"]["name"] == "lookup"
    assert "think" not in request
    assert request["extra_body"] == {"think": True}
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
async def test_stream_closes_client_on_sdk_error(monkeypatch):
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
