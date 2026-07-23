import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.llm.adapters.chat.deepseek_adapter import DeepSeekAdapter
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


def build_adapter(*, thinking=None, **params):
    default_params = {**params}
    if thinking is not None:
        default_params["thinking"] = thinking
    return DeepSeekAdapter(
        SimpleNamespace(
            model_id="deepseek-reasoner",
            api_key="test-key",
            base_url=None,
            config={},
            default_params=default_params,
            max_output_tokens=None,
        )
    )


def install_client(create):
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
        close=AsyncMock(),
    )
    return client, patch("openai.AsyncOpenAI", return_value=client)


class Stream:
    def __init__(self, chunks):
        self._chunks = chunks

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._chunks:
            raise StopAsyncIteration
        chunk = self._chunks.pop(0)
        if isinstance(chunk, Exception):
            raise chunk
        return chunk


def chunk(delta=None, finish_reason=None, *, choices=True):
    return SimpleNamespace(
        choices=(
            [
                SimpleNamespace(
                    delta=delta or SimpleNamespace(content=None, tool_calls=None),
                    finish_reason=finish_reason,
                )
            ]
            if choices
            else []
        )
    )


def test_converts_multimodal_tool_history_and_tools():
    adapter = build_adapter()
    tool_call = ToolCall(
        id="call-1",
        function=FunctionCall(name="weather", arguments='{"city":"Paris"}'),
    )
    messages = [
        Message(
            role=MessageRole.USER,
            content=[
                ContentPart(type=ContentType.TEXT, text="Look"),
                ContentPart(
                    type=ContentType.IMAGE,
                    image=ImageContent(base64="aW1hZ2U=", format="jpeg"),
                ),
                ContentPart(
                    type=ContentType.IMAGE,
                    image=ImageContent(url="https://example.com/image.png"),
                ),
            ],
        ),
        Message(
            role=MessageRole.ASSISTANT,
            content=None,
            reasoning_content="",
            tool_calls=[tool_call],
        ),
        Message(
            role=MessageRole.TOOL,
            content="sunny",
            tool_call_id="call-1",
        ),
    ]

    converted = adapter._convert_messages(messages)

    assert converted == [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Look"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/jpeg;base64,aW1hZ2U="},
                },
                {
                    "type": "image_url",
                    "image_url": {"url": "https://example.com/image.png"},
                },
            ],
        },
        {
            "role": "assistant",
            "content": "",
            "reasoning_content": "",
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {
                        "name": "weather",
                        "arguments": '{"city":"Paris"}',
                    },
                }
            ],
        },
        {"role": "tool", "content": "sunny", "tool_call_id": "call-1"},
    ]
    assert adapter.convert_tools(
        [
            ToolDefinition(
                function=FunctionDefinition(
                    name="weather",
                    description=None,
                    parameters={"type": "object"},
                )
            )
        ]
    ) == [
        {
            "type": "function",
            "function": {
                "name": "weather",
                "description": "",
                "parameters": {"type": "object"},
            },
        }
    ]


def test_converts_raw_parts_and_empty_multimodal_content():
    adapter = build_adapter()
    raw_message = Message.model_construct(
        role="user",
        content=[
            {"type": "text", "text": "raw"},
            SimpleNamespace(type="image", image=ImageContent()),
            SimpleNamespace(type="ignored"),
        ],
        reasoning_content=None,
        tool_calls=None,
        tool_call_id=None,
    )

    assert adapter._convert_messages([raw_message]) == [
        {"role": "user", "content": [{"type": "text", "text": "raw"}]}
    ]
    assert adapter._convert_messages([Message(role=MessageRole.USER, content=[])]) == [
        {"role": "user", "content": ""}
    ]


@pytest.mark.parametrize(
    ("thinking", "expected"),
    [
        (None, {"type": "disabled"}),
        (True, {"type": "enabled"}),
        ({"enabled": True, "effort": "high"}, {"type": "enabled"}),
        ({"type": "enabled", "effort": "max"}, {"type": "enabled", "effort": "max"}),
    ],
)
def test_builds_reasoning_passthrough_body(thinking, expected):
    assert (
        build_adapter(thinking=thinking).get_passthrough_body()["thinking"] == expected
    )


@pytest.mark.parametrize(
    ("sdk_finish_reason", "expected"),
    [
        ("stop", FinishReason.STOP),
        ("length", FinishReason.LENGTH),
        ("content_filter", FinishReason.CONTENT_FILTER),
    ],
)
def test_chat_builds_request_and_maps_plain_finish_reasons(sdk_finish_reason, expected):
    response = SimpleNamespace(
        id="response-1",
        choices=[
            SimpleNamespace(
                finish_reason=sdk_finish_reason,
                message=SimpleNamespace(
                    content="answer", reasoning_content=None, tool_calls=None
                ),
            )
        ],
        usage=None,
    )
    create = AsyncMock(return_value=response)
    client, mocked = install_client(create)
    adapter = build_adapter(
        thinking={"type": "enabled", "effort": "high"},
        temperature=0.2,
        top_p=0.8,
        max_tokens=64,
    )

    with mocked:
        result = asyncio.run(
            adapter.chat([Message(role=MessageRole.USER, content="Hi")])
        )

    assert result.finish_reason == expected
    assert result.usage.total_tokens == 0
    request = create.await_args.kwargs
    assert request["temperature"] == 0.2
    assert request["top_p"] == 0.8
    assert request["max_tokens"] == 64
    assert request["reasoning_effort"] == "high"
    assert request["extra_body"]["thinking"]["type"] == "enabled"
    client.close.assert_awaited_once()


def test_chat_normalizes_reasoning_tools_usage_and_closes_on_error():
    sdk_tool = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(name="weather", arguments='{"city":"Paris"}'),
    )
    response = SimpleNamespace(
        id="response-1",
        choices=[
            SimpleNamespace(
                finish_reason="tool_calls",
                message=SimpleNamespace(
                    content=None,
                    reasoning_content="checking weather",
                    tool_calls=[sdk_tool],
                ),
            )
        ],
        usage=SimpleNamespace(prompt_tokens=4, completion_tokens=3, total_tokens=7),
    )
    create = AsyncMock(return_value=response)
    client, mocked = install_client(create)

    with mocked:
        result = asyncio.run(
            build_adapter().chat(
                [Message(role=MessageRole.USER, content="Weather?")],
                tools=[
                    ToolDefinition(
                        function=FunctionDefinition(name="weather", parameters={})
                    )
                ],
            )
        )

    assert result.reasoning_content == "checking weather"
    assert result.finish_reason == FinishReason.TOOL_CALLS
    assert result.tool_calls[0].function.name == "weather"
    assert result.usage.total_tokens == 7
    assert "reasoning_effort" not in create.await_args.kwargs
    assert create.await_args.kwargs["tools"][0]["function"]["name"] == "weather"
    client.close.assert_awaited_once()

    failed_create = AsyncMock(side_effect=RuntimeError("sdk failed"))
    failed_client, failed_mock = install_client(failed_create)
    with failed_mock, pytest.raises(RuntimeError, match="sdk failed"):
        asyncio.run(
            build_adapter().chat([Message(role=MessageRole.USER, content="Hi")])
        )
    failed_client.close.assert_awaited_once()


def test_stream_emits_activity_content_reasoning_tools_and_finish_reasons():
    first_tool_delta = SimpleNamespace(
        index=0,
        id="call-1",
        type="function",
        function=SimpleNamespace(name="weather", arguments="{"),
    )
    second_tool_delta = SimpleNamespace(
        index=0,
        id=None,
        type=None,
        function=SimpleNamespace(name=None, arguments='"city":"Paris"}'),
    )
    stream = Stream(
        [
            chunk(choices=False),
            chunk(
                SimpleNamespace(
                    content=None, reasoning_content=None, tool_calls=[first_tool_delta]
                )
            ),
            chunk(
                SimpleNamespace(
                    content="answer", reasoning_content="thinking", tool_calls=None
                )
            ),
            chunk(
                SimpleNamespace(
                    content=None, reasoning_content=None, tool_calls=[second_tool_delta]
                ),
                "tool_calls",
            ),
            chunk(finish_reason="length"),
            chunk(finish_reason="content_filter"),
            chunk(finish_reason="stop"),
        ]
    )
    create = AsyncMock(return_value=stream)
    client, mocked = install_client(create)

    async def collect():
        with mocked:
            return [
                item
                async for item in build_adapter(
                    thinking={"type": "enabled", "effort": "high"},
                    temperature=0.2,
                    top_p=0.8,
                    max_tokens=64,
                ).chat_stream(
                    [Message(role=MessageRole.USER, content="Hi")],
                    tools=[
                        ToolDefinition(
                            function=FunctionDefinition(name="weather", parameters={})
                        )
                    ],
                )
            ]

    chunks = asyncio.run(collect())

    assert chunks[0].delta.stream_activity is True
    assert chunks[1].delta.stream_activity is True
    assert chunks[2].delta.content == "answer"
    assert chunks[2].delta.reasoning_content == "thinking"
    assert chunks[3].finish_reason == FinishReason.TOOL_CALLS
    assert chunks[3].delta.tool_calls[0].function.arguments == '{"city":"Paris"}'
    assert [item.finish_reason for item in chunks[-3:]] == [
        FinishReason.LENGTH,
        FinishReason.CONTENT_FILTER,
        FinishReason.STOP,
    ]
    assert len({item.id for item in chunks}) == 1
    request = create.await_args.kwargs
    assert request["stream"] is True
    assert request["temperature"] == 0.2
    assert request["top_p"] == 0.8
    assert request["max_tokens"] == 64
    assert request["reasoning_effort"] == "high"
    assert request["tools"][0]["function"]["name"] == "weather"
    client.close.assert_awaited_once()


def test_stream_closes_client_when_iteration_fails():
    create = AsyncMock(return_value=Stream([RuntimeError("stream failed")]))
    client, mocked = install_client(create)

    async def collect():
        with mocked:
            return [
                item
                async for item in build_adapter().chat_stream(
                    [Message(role=MessageRole.USER, content="Hi")]
                )
            ]

    with pytest.raises(RuntimeError, match="stream failed"):
        asyncio.run(collect())
    client.close.assert_awaited_once()
