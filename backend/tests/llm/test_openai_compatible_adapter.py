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


def build_model(provider="openai_compatible", model_id="compatible-model", **extra):
    return SimpleNamespace(
        provider=provider,
        model_id=model_id,
        api_key=extra.pop("api_key", "test-key"),
        base_url=extra.pop("base_url", "https://example.com/v1"),
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
async def test_chat_builds_zhipu_request_and_normalizes_tool_response():
    response = SimpleNamespace(
        id="response-1",
        choices=[
            SimpleNamespace(
                finish_reason="tool_calls",
                message=SimpleNamespace(
                    content=None,
                    reasoning_content="Need to search.",
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
        usage=SimpleNamespace(prompt_tokens=3, completion_tokens=5, total_tokens=8),
    )
    client = FakeAsyncOpenAI(response)
    adapter = OpenAICompatibleAdapter(
        build_model(
            default_params={
                "temperature": 0.2,
                "top_p": 0.7,
                "max_tokens": 128,
                "thinking": {"type": "enabled", "effort": "high"},
                "extra_body": {"provider": {"order": ["zhipu"]}, "model": "ignored"},
            }
        ),
        provider_hint="zhipu",
    )
    tools = [
        ToolDefinition(
            function=FunctionDefinition(
                name="lookup", description="Search docs", parameters={"type": "object"}
            )
        )
    ]

    with patch("openai.AsyncOpenAI", return_value=client):
        result = await adapter.chat(
            [Message(role=MessageRole.USER, content="Find docs")],
            tools=tools,
            response_format={"type": "json_object"},
        )

    assert client.chat.completions.create.await_args.kwargs == {
        "model": "compatible-model",
        "messages": [{"role": "user", "content": "Find docs"}],
        "temperature": 0.2,
        "top_p": 0.7,
        "max_tokens": 128,
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
        "thinking": {"type": "enabled", "effort": "high"},
        "reasoning_effort": "high",
        "response_format": {"type": "json_object"},
        "extra_body": {"provider": {"order": ["zhipu"]}},
    }
    assert result.id == "response-1"
    assert result.reasoning_content == "Need to search."
    assert result.finish_reason is FinishReason.TOOL_CALLS
    assert result.tool_calls[0].function.arguments == '{"query":"docs"}'
    assert result.usage.total_tokens == 8
    client.close.assert_awaited_once()


def test_converts_deepseek_multimodal_history_and_tool_results():
    adapter = OpenAICompatibleAdapter(build_model(model_id="deepseek-chat"))

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
            Message(role=MessageRole.TOOL, content="Found", tool_call_id="call-1"),
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
            "reasoning_content": "Need a tool",
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "lookup", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "content": "Found", "tool_call_id": "call-1"},
    ]


@pytest.mark.anyio
async def test_chat_stream_normalizes_activity_reasoning_and_tool_calls():
    async def stream():
        yield SimpleNamespace(choices=[])
        yield SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(
                        content=None,
                        reasoning_content="Thinking",
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
                        content=None,
                        model_extra=None,
                        tool_calls=[
                            SimpleNamespace(
                                index=0,
                                id="call-1",
                                type="function",
                                function=SimpleNamespace(
                                    name="look", arguments='{"query":'
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
                        content="Answer",
                        model_extra=None,
                        tool_calls=[
                            SimpleNamespace(
                                index=0,
                                id=None,
                                type=None,
                                function=SimpleNamespace(
                                    name="up", arguments='"docs"}'
                                ),
                            )
                        ],
                    ),
                    finish_reason="tool_calls",
                )
            ]
        )

    client = FakeAsyncOpenAI(stream())
    adapter = OpenAICompatibleAdapter(
        build_model(default_params={"thinking": {"enabled": True, "effort": "low"}}),
        provider_hint="zhipu",
    )

    with patch("openai.AsyncOpenAI", return_value=client):
        chunks = [
            chunk
            async for chunk in adapter.chat_stream(
                [Message(role=MessageRole.USER, content="Hi")]
            )
        ]

    request = client.chat.completions.create.await_args.kwargs
    assert request["stream"] is True
    assert request["thinking"] == {"type": "enabled"}
    assert request["reasoning_effort"] == "low"
    assert [chunk.delta.stream_activity for chunk in chunks] == [
        True,
        False,
        True,
        False,
    ]
    assert chunks[1].delta.reasoning_content == "Thinking"
    assert chunks[3].delta.content == "Answer"
    assert chunks[3].finish_reason is FinishReason.TOOL_CALLS
    assert chunks[3].delta.tool_calls[0].function.name == "lookup"
    assert chunks[3].delta.tool_calls[0].function.arguments == '{"query":"docs"}'
    assert len({chunk.id for chunk in chunks}) == 1
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
                message=SimpleNamespace(
                    content="done", tool_calls=None, model_extra=None
                ),
            )
        ],
        usage=None,
    )
    client = FakeAsyncOpenAI(response)

    with patch("openai.AsyncOpenAI", return_value=client):
        result = await OpenAICompatibleAdapter(build_model()).chat(
            [Message(role=MessageRole.USER, content="Hi")]
        )

    assert result.finish_reason is expected
    assert result.usage.total_tokens == 0
    client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_chat_closes_client_when_request_fails():
    client = FakeAsyncOpenAI(error=RuntimeError("provider unavailable"))

    with (
        patch("openai.AsyncOpenAI", return_value=client),
        pytest.raises(RuntimeError, match="provider unavailable"),
    ):
        await OpenAICompatibleAdapter(build_model()).chat(
            [Message(role=MessageRole.USER, content="Hi")]
        )

    client.close.assert_awaited_once()
