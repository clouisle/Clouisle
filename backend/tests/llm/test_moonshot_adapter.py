from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.llm.adapters.chat.moonshot_adapter import MoonshotAdapter
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
        provider="moonshot",
        model_id="kimi-k2.6",
        api_key="test-key",
        base_url="https://moonshot.test/v1",
        config=extra.pop("config", {}),
        default_params=extra.pop("default_params", {}),
        max_output_tokens=extra.pop("max_output_tokens", None),
        **extra,
    )


class FakeAsyncOpenAI:
    def __init__(self, response=None):
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=AsyncMock()))
        self.chat.completions.create.return_value = response
        self.close = AsyncMock()


def response_with_message(message, finish_reason="stop"):
    return SimpleNamespace(
        id="response-1",
        choices=[SimpleNamespace(message=message, finish_reason=finish_reason)],
        usage=SimpleNamespace(prompt_tokens=3, completion_tokens=5, total_tokens=8),
    )


@pytest.mark.anyio
async def test_chat_builds_multimodal_request_and_normalizes_response():
    adapter = MoonshotAdapter(
        build_model(
            default_params={
                "temperature": 0.2,
                "top_p": 0.7,
                "extra_body": {"metadata": {"source": "test"}, "model": "ignored"},
            },
            max_output_tokens=99,
        )
    )
    message = SimpleNamespace(
        content="done",
        tool_calls=None,
        model_extra={"reasoning_content": "reasoning"},
    )
    client = FakeAsyncOpenAI(response_with_message(message))

    with patch("openai.AsyncOpenAI", return_value=client):
        response = await adapter.chat(
            [
                Message(
                    role=MessageRole.USER,
                    content=[
                        ContentPart(type=ContentType.TEXT, text="describe"),
                        ContentPart(
                            type=ContentType.IMAGE,
                            image=ImageContent(base64="aW1hZ2U=", format="jpeg"),
                        ),
                    ],
                )
            ]
        )

    kwargs = client.chat.completions.create.await_args.kwargs
    assert kwargs["model"] == "kimi-k2.6"
    assert kwargs["messages"] == [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "describe"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/jpeg;base64,aW1hZ2U="},
                },
            ],
        }
    ]
    assert kwargs["temperature"] == 0.2
    assert kwargs["top_p"] == 0.7
    assert kwargs["max_tokens"] == 99
    assert kwargs["thinking"] == {"type": "disabled"}
    assert kwargs["extra_body"] == {"metadata": {"source": "test"}}
    assert response.content == "done"
    assert response.reasoning_content == "reasoning"
    assert response.usage.total_tokens == 8
    client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_chat_normalizes_tool_calls_and_tool_finish_reason():
    adapter = MoonshotAdapter(build_model(default_params={"thinking": True}))
    message = SimpleNamespace(
        content=None,
        model_extra=None,
        tool_calls=[
            SimpleNamespace(
                id="call-1",
                function=SimpleNamespace(name="weather", arguments='{"city":"Paris"}'),
            )
        ],
    )
    client = FakeAsyncOpenAI(response_with_message(message, finish_reason="tool_calls"))
    tool = ToolDefinition(
        function=FunctionDefinition(
            name="weather", description="Get weather", parameters={"type": "object"}
        )
    )

    with patch("openai.AsyncOpenAI", return_value=client):
        response = await adapter.chat(
            [Message(role=MessageRole.USER, content="Weather?")], [tool]
        )

    kwargs = client.chat.completions.create.await_args.kwargs
    assert kwargs["thinking"] == {"type": "enabled"}
    assert kwargs["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "weather",
                "description": "Get weather",
                "parameters": {"type": "object"},
            },
        }
    ]
    assert response.finish_reason.value == "tool_calls"
    assert response.tool_calls == [
        ToolCall(
            id="call-1",
            function=FunctionCall(name="weather", arguments='{"city":"Paris"}'),
        )
    ]


@pytest.mark.anyio
async def test_chat_stream_normalizes_activity_reasoning_and_tool_call():
    async def stream():
        yield SimpleNamespace(choices=[])
        yield SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(
                        content="Hello",
                        reasoning_content="Think",
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
                        content=None,
                        tool_calls=[
                            SimpleNamespace(
                                index=0,
                                id="call-1",
                                type="function",
                                function=SimpleNamespace(
                                    name="weather", arguments='{"city":"Paris"}'
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
                    delta=SimpleNamespace(content=None, tool_calls=None),
                    finish_reason="tool_calls",
                )
            ]
        )

    adapter = MoonshotAdapter(build_model())
    client = FakeAsyncOpenAI(stream())

    with patch("openai.AsyncOpenAI", return_value=client):
        chunks = [
            chunk
            async for chunk in adapter.chat_stream(
                [Message(role=MessageRole.USER, content="Weather?")]
            )
        ]

    kwargs = client.chat.completions.create.await_args.kwargs
    assert kwargs["stream"] is True
    assert chunks[0].delta.stream_activity is True
    assert chunks[1].delta.content == "Hello"
    assert chunks[1].delta.reasoning_content == "Think"
    assert chunks[2].delta.stream_activity is True
    assert chunks[3].finish_reason.value == "tool_calls"
    assert chunks[3].delta.tool_calls == [
        ToolCall(
            id="call-1",
            function=FunctionCall(name="weather", arguments='{"city":"Paris"}'),
        )
    ]
    client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_chat_closes_client_when_request_fails():
    adapter = MoonshotAdapter(build_model())
    client = FakeAsyncOpenAI()
    client.chat.completions.create.side_effect = RuntimeError("provider unavailable")

    with patch("openai.AsyncOpenAI", return_value=client):
        with pytest.raises(RuntimeError, match="provider unavailable"):
            await adapter.chat([Message(role=MessageRole.USER, content="Hi")])

    client.close.assert_awaited_once()
