from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.llm.adapters.chat.ollama_adapter import OllamaAdapter
from app.llm.types import (
    ContentPart,
    ContentType,
    FunctionCall,
    FunctionDefinition,
    ImageContent,
    Message,
    MessageRole,
    ToolCall,
    ToolDefinition,
)


def build_model(**extra):
    return SimpleNamespace(
        provider="ollama",
        model_id="qwen3",
        api_key=extra.pop("api_key", None),
        base_url=extra.pop("base_url", "http://localhost:11434/v1"),
        config=extra.pop("config", {}),
        default_params=extra.pop("default_params", {}),
        max_output_tokens=extra.pop("max_output_tokens", None),
        **extra,
    )


class FakeAsyncOpenAI:
    def __init__(self, response=None, error=None):
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=AsyncMock()))
        self.chat.completions.create.return_value = response
        if error:
            self.chat.completions.create.side_effect = error
        self.close = AsyncMock()


@pytest.mark.anyio
async def test_chat_builds_request_and_normalizes_tool_response():
    response = SimpleNamespace(
        id="resp-1",
        choices=[
            SimpleNamespace(
                finish_reason="tool_calls",
                message=SimpleNamespace(
                    content=None,
                    thinking="I should check the weather.",
                    model_extra=None,
                    tool_calls=[
                        SimpleNamespace(
                            id="call-1",
                            function=SimpleNamespace(
                                name="weather", arguments='{"city":"Paris"}'
                            ),
                        )
                    ],
                ),
            )
        ],
        usage=SimpleNamespace(prompt_tokens=3, completion_tokens=5, total_tokens=8),
    )
    client = FakeAsyncOpenAI(response)
    adapter = OllamaAdapter(
        build_model(
            default_params={
                "temperature": 0.2,
                "top_p": 0.7,
                "max_tokens": 128,
                "thinking": {"enabled": True},
                "extra_body": {"keep_alive": "5m", "model": "ignored"},
            }
        )
    )
    tools = [
        ToolDefinition(
            function=FunctionDefinition(
                name="weather",
                description="Get weather",
                parameters={"type": "object"},
            )
        )
    ]

    with patch("openai.AsyncOpenAI", return_value=client):
        result = await adapter.chat(
            [Message(role=MessageRole.USER, content="Weather?")], tools
        )

    request = client.chat.completions.create.await_args.kwargs
    assert request == {
        "model": "qwen3",
        "messages": [{"role": "user", "content": "Weather?"}],
        "temperature": 0.2,
        "top_p": 0.7,
        "max_tokens": 128,
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "weather",
                    "description": "Get weather",
                    "parameters": {"type": "object"},
                },
            }
        ],
        "think": True,
        "extra_body": {"keep_alive": "5m"},
    }
    assert result.id == "resp-1"
    assert result.reasoning_content == "I should check the weather."
    assert result.finish_reason == "tool_calls"
    assert result.tool_calls[0].function.arguments == '{"city":"Paris"}'
    assert result.usage.total_tokens == 8
    client.close.assert_awaited_once()


def test_converts_multimodal_history_and_tool_results():
    adapter = OllamaAdapter(build_model())

    result = adapter._convert_messages(
        [
            Message(
                role=MessageRole.USER,
                content=[
                    ContentPart(type=ContentType.TEXT, text="Look"),
                    ContentPart(
                        type=ContentType.IMAGE,
                        image=ImageContent(base64="YWJj", format="jpeg"),
                    ),
                ],
            ),
            Message(
                role=MessageRole.ASSISTANT,
                content=None,
                reasoning_content="Need a tool",
                tool_calls=[
                    ToolCall(
                        id="call-1",
                        function=FunctionCall(name="lookup", arguments="{}"),
                    )
                ],
            ),
            Message(role=MessageRole.TOOL, content="Sunny", tool_call_id="call-1"),
        ]
    )

    assert result == [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Look"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/jpeg;base64,YWJj"},
                },
            ],
        },
        {
            "role": "assistant",
            "content": "",
            "thinking": "Need a tool",
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "lookup", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "content": "Sunny", "tool_call_id": "call-1"},
    ]


@pytest.mark.anyio
async def test_chat_stream_normalizes_activity_reasoning_and_stop():
    async def stream():
        yield SimpleNamespace(choices=[])
        yield SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(
                        content=None,
                        thinking="Thinking",
                        model_extra=None,
                        tool_calls=None,
                    ),
                    finish_reason=None,
                )
            ]
        )
        yield SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(
                        content="Answer", model_extra=None, tool_calls=None
                    ),
                    finish_reason="stop",
                )
            ]
        )

    client = FakeAsyncOpenAI(stream())
    adapter = OllamaAdapter(build_model(default_params={"thinking": False}))

    with patch("openai.AsyncOpenAI", return_value=client):
        chunks = [
            chunk
            async for chunk in adapter.chat_stream(
                [Message(role=MessageRole.USER, content="Hi")]
            )
        ]

    request = client.chat.completions.create.await_args.kwargs
    assert request["stream"] is True
    assert request["think"] is False
    assert [chunk.delta.stream_activity for chunk in chunks] == [True, False, False]
    assert chunks[1].delta.reasoning_content == "Thinking"
    assert chunks[2].delta.content == "Answer"
    assert chunks[2].finish_reason == "stop"
    assert len({chunk.id for chunk in chunks}) == 1
    client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_chat_stream_accumulates_tool_call_before_finish():
    async def stream():
        yield SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(
                        content=None,
                        model_extra=None,
                        tool_calls=[
                            SimpleNamespace(
                                index=0,
                                id="call-1",
                                type="function",
                                function=SimpleNamespace(
                                    name="wea", arguments='{"city":'
                                ),
                            )
                        ],
                    ),
                    finish_reason=None,
                )
            ]
        )
        yield SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(
                        content=None,
                        model_extra=None,
                        tool_calls=[
                            SimpleNamespace(
                                index=0,
                                id=None,
                                type=None,
                                function=SimpleNamespace(
                                    name="ther", arguments='"Paris"}'
                                ),
                            )
                        ],
                    ),
                    finish_reason="tool_calls",
                )
            ]
        )

    client = FakeAsyncOpenAI(stream())
    adapter = OllamaAdapter(build_model())

    with patch("openai.AsyncOpenAI", return_value=client):
        chunks = [
            chunk
            async for chunk in adapter.chat_stream(
                [Message(role=MessageRole.USER, content="Weather?")]
            )
        ]

    assert chunks[0].delta.stream_activity is True
    assert chunks[1].finish_reason == "tool_calls"
    assert chunks[1].delta.tool_calls[0].id == "call-1"
    assert chunks[1].delta.tool_calls[0].function.name == "weather"
    assert chunks[1].delta.tool_calls[0].function.arguments == '{"city":"Paris"}'
    client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_chat_closes_client_when_request_fails():
    client = FakeAsyncOpenAI(error=RuntimeError("provider unavailable"))
    adapter = OllamaAdapter(build_model())

    with (
        patch("openai.AsyncOpenAI", return_value=client),
        pytest.raises(RuntimeError, match="provider unavailable"),
    ):
        await adapter.chat([Message(role=MessageRole.USER, content="Hi")])

    client.close.assert_awaited_once()
