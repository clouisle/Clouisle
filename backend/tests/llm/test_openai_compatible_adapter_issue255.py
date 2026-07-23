from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.llm.adapters.chat.openai_compatible_adapter import OpenAICompatibleAdapter
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


def adapter(model_id="gpt-test", provider_hint=None, **overrides):
    values = {
        "model_id": model_id,
        "api_key": "test-key",
        "base_url": None,
        "config": {},
        "default_params": {},
        "max_output_tokens": None,
    }
    values.update(overrides)
    return OpenAICompatibleAdapter(SimpleNamespace(**values), provider_hint)


def install_client(response):
    create = AsyncMock(
        side_effect=response if isinstance(response, Exception) else None
    )
    if not isinstance(response, Exception):
        create.return_value = response
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
        close=AsyncMock(),
    )
    return client, patch("openai.AsyncOpenAI", return_value=client)


class Stream:
    def __init__(self, chunks):
        self.chunks = iter(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            item = next(self.chunks)
        except StopIteration:
            raise StopAsyncIteration from None
        if isinstance(item, Exception):
            raise item
        return item


def stream_chunk(delta=None, finish_reason=None, choices=True):
    return SimpleNamespace(
        choices=(
            [
                SimpleNamespace(
                    delta=delta
                    or SimpleNamespace(content=None, tool_calls=None, model_extra=None),
                    finish_reason=finish_reason,
                )
            ]
            if choices
            else []
        )
    )


def test_base_url_provider_detection_and_message_conversion():
    assert (
        adapter(provider_hint="Ollama")._get_base_url() == "http://localhost:11434/v1"
    )
    assert adapter(provider_hint="unknown")._get_base_url() is None
    assert adapter(base_url="https://custom.invalid")._get_base_url() == (
        "https://custom.invalid"
    )
    assert adapter("anthropic/claude-3")._actual_provider == "anthropic"
    assert adapter("google/gemini-pro")._actual_provider == "google"
    assert adapter("deepseek-chat")._actual_provider == "deepseek"
    assert adapter()._actual_provider == "openai"

    instance = adapter("deepseek-chat")
    messages = [
        Message(
            role=MessageRole.USER,
            content=[
                ContentPart(type=ContentType.TEXT, text="look"),
                ContentPart(
                    type=ContentType.IMAGE,
                    image=ImageContent(base64="aW1n", format="jpeg"),
                ),
                ContentPart(
                    type=ContentType.IMAGE,
                    image=ImageContent(url="https://image.invalid/a.png"),
                ),
            ],
        ),
        Message(
            role=MessageRole.ASSISTANT,
            content=None,
            tool_calls=[
                ToolCall(
                    id="call-1",
                    function=FunctionCall(name="weather", arguments='{"city":"Paris"}'),
                )
            ],
        ),
        Message(role=MessageRole.TOOL, content="sunny", tool_call_id="call-1"),
        Message(role=MessageRole.ASSISTANT, content="plain"),
    ]
    messages.append(
        SimpleNamespace(
            role="user",
            content=[
                ContentPart(type=ContentType.VIDEO),
                ContentPart(type=ContentType.IMAGE, image=ImageContent()),
                {"type": "text", "text": "raw"},
            ],
            tool_calls=None,
            tool_call_id=None,
        )
    )

    converted = instance._convert_messages(messages)
    assert converted[0]["content"] == [
        {"type": "text", "text": "look"},
        {
            "type": "image_url",
            "image_url": {"url": "data:image/jpeg;base64,aW1n"},
        },
        {
            "type": "image_url",
            "image_url": {"url": "https://image.invalid/a.png"},
        },
    ]
    assert converted[1]["reasoning_content"] == ""
    assert converted[1]["tool_calls"][0]["function"]["name"] == "weather"
    assert converted[2]["tool_call_id"] == "call-1"
    assert "reasoning_content" not in converted[3]
    assert converted[4]["content"] == [{"type": "text", "text": "raw"}]


@pytest.mark.anyio
async def test_chat_sends_config_tools_and_structured_format():
    sdk_tool = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(name="weather", arguments='{"city":"Paris"}'),
    )
    response = SimpleNamespace(
        id="response-1",
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[sdk_tool],
                    reasoning_content="checking",
                    model_extra=None,
                ),
                finish_reason="tool_calls",
            )
        ],
        usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5),
    )
    client, patched = install_client(response)
    instance = adapter(
        provider_hint="zhipu",
        default_params={
            "temperature": 0.2,
            "top_p": 0.8,
            "thinking": {"type": "enabled", "effort": "high"},
            "extra_body": {"seed": 7, "model": "ignored"},
        },
        max_output_tokens=99,
    )
    tools = [
        ToolDefinition(
            function=FunctionDefinition(
                name="weather",
                description="Forecast",
                parameters={"type": "object"},
            )
        )
    ]

    with patched as factory:
        result = await instance.chat(
            [Message(role=MessageRole.USER, content="Weather?")],
            tools,
            response_format={"type": "json_object"},
        )

    factory.assert_called_once()
    assert (
        factory.call_args.kwargs["base_url"] == "https://open.bigmodel.cn/api/paas/v4"
    )
    request = client.chat.completions.create.await_args.kwargs
    assert request["temperature"] == 0.2
    assert request["top_p"] == 0.8
    assert request["max_tokens"] == 99
    assert request["tools"][0]["function"]["name"] == "weather"
    assert request["thinking"] == {"type": "enabled", "effort": "high"}
    assert request["reasoning_effort"] == "high"
    assert request["response_format"] == {"type": "json_object"}
    assert request["extra_body"] == {"seed": 7}
    assert result.finish_reason is FinishReason.TOOL_CALLS
    assert result.reasoning_content == "checking"
    assert result.tool_calls[0].function.name == "weather"
    assert result.usage.total_tokens == 5
    client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_chat_defaults_ollama_key_and_closes_after_error():
    error = RuntimeError("SDK failed")
    client, patched = install_client(error)
    with patched as factory, pytest.raises(RuntimeError, match="SDK failed"):
        await adapter(provider_hint="ollama", api_key=None).chat(
            [Message(role=MessageRole.USER, content="hello")]
        )

    assert factory.call_args.kwargs["api_key"] == "ollama"
    client.close.assert_awaited_once()

    client, patched = install_client(error)
    with patched, pytest.raises(RuntimeError, match="SDK failed"):
        await adapter(provider_hint="zhipu", default_params={"thinking": False}).chat(
            [Message(role=MessageRole.USER, content="hello")]
        )
    assert client.chat.completions.create.await_args.kwargs["thinking"] == {
        "type": "disabled"
    }


@pytest.mark.anyio
async def test_chat_maps_finish_reasons_without_usage():
    for sdk_reason, expected in [
        ("length", FinishReason.LENGTH),
        ("content_filter", FinishReason.CONTENT_FILTER),
        ("stop", FinishReason.STOP),
    ]:
        response = SimpleNamespace(
            id="response",
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="done", tool_calls=None, model_extra=None
                    ),
                    finish_reason=sdk_reason,
                )
            ],
            usage=None,
        )
        client, patched = install_client(response)
        with patched:
            result = await adapter().chat(
                [Message(role=MessageRole.USER, content="hello")]
            )
        assert result.finish_reason is expected
        assert result.usage.total_tokens == 0
        client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_stream_covers_activity_content_tools_and_finish_reasons():
    tool_start = SimpleNamespace(
        index=0,
        id="call-1",
        function=SimpleNamespace(name="weather", arguments='{"city":'),
    )
    tool_end = SimpleNamespace(
        index=0,
        id=None,
        function=SimpleNamespace(name=None, arguments='"Paris"}'),
    )
    stream = Stream(
        [
            stream_chunk(choices=False),
            stream_chunk(SimpleNamespace(content=None, tool_calls=[tool_start])),
            stream_chunk(SimpleNamespace(content=None, tool_calls=[tool_end])),
            stream_chunk(
                SimpleNamespace(
                    content="hello", tool_calls=None, reasoning_content="thinking"
                )
            ),
            stream_chunk(SimpleNamespace(content=None, tool_calls=None), "tool_calls"),
            stream_chunk(SimpleNamespace(content=None, tool_calls=None), "length"),
            stream_chunk(
                SimpleNamespace(content=None, tool_calls=None), "content_filter"
            ),
            stream_chunk(SimpleNamespace(content=None, tool_calls=None), "stop"),
            stream_chunk(SimpleNamespace(content=None, tool_calls=None), "unknown"),
            stream_chunk(SimpleNamespace(content=None, tool_calls=None)),
        ]
    )
    client, patched = install_client(stream)
    instance = adapter(
        provider_hint="zhipu",
        default_params={
            "temperature": 0.3,
            "top_p": 0.7,
            "max_tokens": 55,
            "thinking": {"enabled": True, "effort": "medium"},
        },
    )

    with patched:
        chunks = [
            chunk
            async for chunk in instance.chat_stream(
                [Message(role=MessageRole.USER, content="hello")],
                [
                    ToolDefinition(
                        function=FunctionDefinition(name="weather", parameters={})
                    )
                ],
                response_format={"type": "json_object"},
            )
        ]

    request = client.chat.completions.create.await_args.kwargs
    assert request["stream"] is True
    assert request["temperature"] == 0.3
    assert request["top_p"] == 0.7
    assert request["max_tokens"] == 55
    assert request["tool_stream"] is True
    assert request["thinking"] == {"type": "enabled"}
    assert request["reasoning_effort"] == "medium"
    assert request["response_format"] == {"type": "json_object"}
    assert chunks[0].delta.stream_activity is True
    assert chunks[1].delta.stream_activity is True
    assert chunks[2].delta.stream_activity is True
    assert chunks[3].delta.content == "hello"
    assert chunks[3].delta.reasoning_content == "thinking"
    assert chunks[4].finish_reason is FinishReason.TOOL_CALLS
    assert chunks[4].delta.tool_calls[0].function.arguments == '{"city":"Paris"}'
    assert [chunk.finish_reason for chunk in chunks[-3:]] == [
        FinishReason.LENGTH,
        FinishReason.CONTENT_FILTER,
        FinishReason.STOP,
    ]
    client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_stream_closes_client_when_iteration_fails():
    client, patched = install_client(Stream([RuntimeError("stream failed")]))
    with patched as factory, pytest.raises(RuntimeError, match="stream failed"):
        async for _ in adapter(provider_hint="ollama", api_key=None).chat_stream(
            [Message(role=MessageRole.USER, content="hello")]
        ):
            pass

    assert factory.call_args.kwargs["api_key"] == "ollama"
    client.close.assert_awaited_once()
