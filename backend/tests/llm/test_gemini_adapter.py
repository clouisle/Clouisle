import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.llm.adapters.chat.gemini_adapter import GeminiAdapter
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


def build_adapter(**overrides):
    values = {
        "provider": "gemini",
        "model_id": "gemini-2.0-flash",
        "api_key": "test-key",
        "base_url": "https://gemini.example.com",
        "config": {},
        "default_params": {},
        "max_output_tokens": None,
    }
    values.update(overrides)
    return GeminiAdapter(SimpleNamespace(**values))


def part(**values):
    return SimpleNamespace(**values)


def response(parts=None, *, finish_reason="STOP", usage=True):
    candidates = (
        [
            SimpleNamespace(
                content=SimpleNamespace(parts=parts),
                finish_reason=finish_reason,
            )
        ]
        if parts is not None
        else []
    )
    metadata = (
        SimpleNamespace(
            prompt_token_count=7,
            candidates_token_count=3,
            total_token_count=10,
            cached_content_token_count=5,
        )
        if usage
        else None
    )
    return SimpleNamespace(candidates=candidates, usage_metadata=metadata)


def build_client(*, result=None, stream=None, error=None):
    generate_content = AsyncMock(return_value=result, side_effect=error)
    generate_content_stream = AsyncMock(return_value=stream)
    return SimpleNamespace(
        aio=SimpleNamespace(
            models=SimpleNamespace(
                generate_content=generate_content,
                generate_content_stream=generate_content_stream,
            )
        )
    )


class AsyncChunks:
    def __init__(self, chunks):
        self.chunks = iter(chunks)
        self.requested = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        self.requested += 1
        try:
            return next(self.chunks)
        except StopIteration:
            raise StopAsyncIteration from None


def test_converts_multimodal_history_tool_results_and_declarations():
    adapter = build_adapter()
    tool_call = ToolCall(
        id="call-1",
        function=FunctionCall(name="lookup", arguments="not-json"),
    )
    messages = [
        Message(
            role=MessageRole.SYSTEM,
            content=[ContentPart(type=ContentType.TEXT, text="Be concise")],
        ),
        Message(
            role=MessageRole.USER,
            content=[
                ContentPart(type=ContentType.TEXT, text="Describe"),
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
            content="Working",
            reasoning_content="Inspect image",
            tool_calls=[tool_call],
        ),
        Message(role=MessageRole.TOOL, content="plain result", tool_call_id="lookup"),
    ]

    system, contents = adapter._convert_messages(messages)

    assert system == "Be concise"
    assert contents == [
        {
            "role": "user",
            "parts": [
                {"text": "Describe"},
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": "aW1hZ2U=",
                    }
                },
                {"file_data": {"file_uri": "https://example.com/image.png"}},
            ],
        },
        {
            "role": "model",
            "parts": [
                {"thought": True, "text": "Inspect image"},
                {"text": "Working"},
                {"function_call": {"name": "lookup", "args": {}}},
            ],
        },
        {
            "role": "user",
            "parts": [
                {
                    "function_response": {
                        "name": "lookup",
                        "response": {"result": "plain result"},
                    }
                }
            ],
        },
    ]
    assert adapter.convert_tools(
        [
            ToolDefinition(
                function=FunctionDefinition(
                    name="lookup",
                    description="Search docs",
                    parameters={"type": "object"},
                )
            )
        ]
    ) == [
        {
            "function_declarations": [
                {
                    "name": "lookup",
                    "description": "Search docs",
                    "parameters": {"type": "object"},
                }
            ]
        }
    ]


@pytest.mark.anyio
async def test_chat_builds_request_and_normalizes_reasoning_tool_and_usage():
    adapter = build_adapter(
        default_params={
            "temperature": 0.2,
            "top_p": 0.8,
            "thinking": {"enabled": True, "budget_tokens": 2048},
        },
        max_output_tokens=321,
    )
    provider_response = response(
        [
            part(thought=True, text="consider"),
            part(thought=False, text=" result "),
            part(
                thought=False,
                function_call=part(name="lookup", args={"query": "docs"}),
            ),
        ],
        finish_reason="STOP",
    )
    client = build_client(result=provider_response)
    tool = ToolDefinition(
        function=FunctionDefinition(name="lookup", parameters={"type": "object"})
    )
    schema = {"type": "object", "properties": {"answer": {"type": "string"}}}

    with patch("google.genai.Client", return_value=client) as client_class:
        result = await adapter.chat(
            [
                Message(role=MessageRole.SYSTEM, content="Follow policy"),
                Message(role=MessageRole.USER, content="Find docs"),
            ],
            tools=[tool],
            response_format={"type": "json_schema", "json_schema": {"schema": schema}},
        )

    client_class.assert_called_once_with(
        api_key="test-key",
        http_options={"base_url": "https://gemini.example.com"},
    )
    request = client.aio.models.generate_content.await_args.kwargs
    assert request == {
        "model": "gemini-2.0-flash",
        "contents": [{"role": "user", "parts": [{"text": "Find docs"}]}],
        "config": {
            "system_instruction": "Follow policy",
            "generation_config": {
                "temperature": 0.2,
                "top_p": 0.8,
                "max_output_tokens": 321,
                "thinking_config": {"thinking_budget": 2048},
                "response_schema": schema,
                "response_mime_type": "application/json",
            },
            "tools": [
                {
                    "function_declarations": [
                        {
                            "name": "lookup",
                            "description": "",
                            "parameters": {"type": "object"},
                        }
                    ]
                }
            ],
        },
    }
    assert result.content == "result"
    assert result.reasoning_content == "consider"
    assert result.finish_reason is FinishReason.TOOL_CALLS
    assert result.tool_calls[0].function.name == "lookup"
    assert json.loads(result.tool_calls[0].function.arguments) == {"query": "docs"}
    assert result.usage.model_dump() == {
        "prompt_tokens": 7,
        "completion_tokens": 3,
        "total_tokens": 10,
        "cache_read_tokens": 5,
        "cache_creation_tokens": 0,
        "total_input_tokens": 7,
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("provider_reason", "expected"),
    [
        ("MAX_TOKENS", FinishReason.LENGTH),
        ("SAFETY", FinishReason.CONTENT_FILTER),
        ("FUNCTION_CALL", FinishReason.TOOL_CALLS),
        (None, FinishReason.STOP),
        ("UNKNOWN", FinishReason.STOP),
    ],
)
async def test_chat_maps_finish_reasons_and_empty_responses(provider_reason, expected):
    provider_response = response([], finish_reason=provider_reason, usage=False)
    client = build_client(result=provider_response)

    with patch("google.genai.Client", return_value=client):
        result = await build_adapter(base_url=None).chat(
            [Message(role=MessageRole.USER, content="Hi")]
        )

    assert result.content is None
    assert result.reasoning_content is None
    assert result.tool_calls is None
    assert result.finish_reason is expected
    assert result.usage.total_tokens == 0


@pytest.mark.anyio
async def test_chat_propagates_provider_failure():
    client = build_client(error=RuntimeError("provider failed"))

    with (
        patch("google.genai.Client", return_value=client),
        pytest.raises(RuntimeError, match="provider failed"),
    ):
        await build_adapter().chat([Message(role=MessageRole.USER, content="Hi")])


@pytest.mark.anyio
async def test_chat_stream_normalizes_reasoning_content_tool_activity_and_finish():
    stream = AsyncChunks(
        [
            SimpleNamespace(candidates=[]),
            response([part(thought=True, text="think")], finish_reason=None),
            response(
                [
                    part(
                        thought=False,
                        function_call=part(name="lookup", args={"query": "docs"}),
                    )
                ],
                finish_reason=None,
            ),
            response([part(thought=False, text="answer")], finish_reason="STOP"),
        ]
    )
    client = build_client(stream=stream)
    adapter = build_adapter(default_params={"thinking": False})

    with patch("google.genai.Client", return_value=client):
        chunks = [
            chunk
            async for chunk in adapter.chat_stream(
                [Message(role=MessageRole.USER, content="Hi")],
                response_format={"type": "json_object"},
            )
        ]

    request = client.aio.models.generate_content_stream.await_args.kwargs
    assert request["config"]["generation_config"] == {
        "thinking_config": {"thinking_budget": 0},
        "response_mime_type": "application/json",
    }
    assert chunks[0].delta.reasoning_content == "think"
    assert chunks[1].delta.stream_activity is True
    assert chunks[2].delta.content == "answer"
    assert chunks[3].finish_reason is FinishReason.TOOL_CALLS
    assert chunks[3].delta.tool_calls[0].function.name == "lookup"
    assert json.loads(chunks[3].delta.tool_calls[0].function.arguments) == {
        "query": "docs"
    }
    assert len({chunk.id for chunk in chunks}) == 1


@pytest.mark.anyio
async def test_chat_stream_can_be_closed_after_first_chunk():
    stream = AsyncChunks(
        [
            response([part(thought=False, text="first")], finish_reason=None),
            response([part(thought=False, text="second")], finish_reason="STOP"),
        ]
    )
    client = build_client(stream=stream)
    generator = build_adapter().chat_stream(
        [Message(role=MessageRole.USER, content="Hi")]
    )

    with patch("google.genai.Client", return_value=client):
        first = await anext(generator)
        await generator.aclose()

    assert first.delta.content == "first"
    assert stream.requested == 1


@pytest.mark.anyio
async def test_chat_stream_captures_usage_metadata_from_terminal_chunk():
    stream = AsyncChunks(
        [
            response([part(thought=False, text="answer")], finish_reason="STOP"),
        ]
    )
    client = build_client(stream=stream)

    with patch("google.genai.Client", return_value=client):
        chunks = [
            chunk
            async for chunk in build_adapter().chat_stream(
                [Message(role=MessageRole.USER, content="Hi")]
            )
        ]

    assert chunks[-1].finish_reason is FinishReason.STOP
    assert chunks[-1].usage.model_dump() == {
        "prompt_tokens": 7,
        "completion_tokens": 3,
        "total_tokens": 10,
        "cache_read_tokens": 5,
        "cache_creation_tokens": 0,
        "total_input_tokens": 7,
    }
