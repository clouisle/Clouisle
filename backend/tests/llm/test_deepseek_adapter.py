from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.llm.adapters.chat.deepseek_adapter import DeepSeekAdapter
from app.llm.types import (
    FinishReason,
    FunctionDefinition,
    Message,
    MessageRole,
    ToolDefinition,
)


def build_adapter(**default_params):
    return DeepSeekAdapter(
        SimpleNamespace(
            provider="deepseek",
            model_id="deepseek-reasoner",
            api_key="test-key",
            base_url="https://example.com/v1",
            config={},
            default_params=default_params,
            max_output_tokens=None,
        )
    )


def build_client(result):
    return SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=AsyncMock(return_value=result))
        ),
        close=AsyncMock(),
    )


class AsyncChunks:
    def __init__(self, chunks):
        self.chunks = iter(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self.chunks)
        except StopIteration:
            raise StopAsyncIteration from None


@pytest.mark.anyio
async def test_chat_builds_request_and_normalizes_reasoning_tool_response():
    response = SimpleNamespace(
        id="response-1",
        choices=[
            SimpleNamespace(
                finish_reason="tool_calls",
                message=SimpleNamespace(
                    content=None,
                    reasoning_content="reasoning",
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
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=4, total_tokens=14),
    )
    client = build_client(response)
    tools = [
        ToolDefinition(
            function=FunctionDefinition(
                name="lookup", description="Search docs", parameters={"type": "object"}
            )
        )
    ]

    with patch("openai.AsyncOpenAI", return_value=client):
        result = await build_adapter(
            temperature=0.2,
            top_p=0.8,
            max_tokens=321,
            thinking={"type": "enabled"},
            reasoning_effort="high",
        ).chat([Message(role=MessageRole.USER, content="Find docs")], tools=tools)

    assert client.chat.completions.create.await_args.kwargs == {
        "model": "deepseek-reasoner",
        "messages": [{"role": "user", "content": "Find docs"}],
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
        "extra_body": {"thinking": {"type": "enabled"}},
    }
    assert result.id == "response-1"
    assert result.reasoning_content == "reasoning"
    assert result.finish_reason is FinishReason.TOOL_CALLS
    assert result.tool_calls[0].function.name == "lookup"
    assert result.usage.total_tokens == 14
    client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_chat_stream_normalizes_reasoning_and_accumulated_tool_calls():
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
    client = build_client(
        AsyncChunks(
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
                            delta=SimpleNamespace(
                                content=None, tool_calls=[tool_start]
                            ),
                            finish_reason=None,
                        )
                    ]
                ),
                SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(
                                content="answer", tool_calls=[tool_end]
                            ),
                            finish_reason="tool_calls",
                        )
                    ]
                ),
            ]
        )
    )

    with patch("openai.AsyncOpenAI", return_value=client):
        result = [
            chunk
            async for chunk in build_adapter().chat_stream(
                [Message(role=MessageRole.USER, content="Hi")]
            )
        ]

    assert client.chat.completions.create.await_args.kwargs["stream"] is True
    assert result[0].delta.stream_activity is True
    assert result[1].delta.reasoning_content == "thinking"
    assert result[2].delta.stream_activity is True
    assert result[3].delta.content == "answer"
    assert result[3].finish_reason is FinishReason.TOOL_CALLS
    assert result[3].delta.tool_calls[0].function.arguments == '{"query":"docs"}'
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


@pytest.mark.anyio
async def test_chat_stream_closes_client_when_iteration_fails():
    class FailingChunks:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise RuntimeError("stream failed")

    client = build_client(FailingChunks())

    with (
        patch("openai.AsyncOpenAI", return_value=client),
        pytest.raises(RuntimeError, match="stream failed"),
    ):
        async for _ in build_adapter().chat_stream(
            [Message(role=MessageRole.USER, content="Hi")]
        ):
            pass

    client.close.assert_awaited_once()
