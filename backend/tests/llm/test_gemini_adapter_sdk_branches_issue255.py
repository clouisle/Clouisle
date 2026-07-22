import json
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

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


def ns(**values):
    return SimpleNamespace(**values)


def build_adapter(**overrides):
    config = {
        "model_id": "gemini-test",
        "api_key": "secret",
        "base_url": "https://gemini.invalid",
        "config": {},
        "default_params": {},
    }
    config.update(overrides)
    return GeminiAdapter(ns(**config))


def response(parts=None, *, finish_reason="STOP", usage=True):
    return ns(
        candidates=[ns(content=ns(parts=parts), finish_reason=finish_reason)],
        usage_metadata=ns(
            prompt_token_count=2,
            candidates_token_count=3,
            total_token_count=5,
        )
        if usage
        else None,
    )


def sdk_client(*, result=None, stream=None, error=None):
    models = ns(
        generate_content=AsyncMock(return_value=result, side_effect=error),
        generate_content_stream=AsyncMock(return_value=stream, side_effect=error),
    )
    return ns(aio=ns(models=models)), models


def mock_sdk(client):
    google = ModuleType("google")
    genai = ModuleType("google.genai")
    genai.Client = Mock(return_value=client)
    google.genai = genai
    return patch.dict(
        sys.modules, {"google": google, "google.genai": genai}
    ), genai.Client


class AsyncChunks:
    def __init__(self, chunks):
        self._chunks = iter(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._chunks)
        except StopIteration:
            raise StopAsyncIteration from None


def test_request_conversion_covers_multimodal_tools_and_fallbacks():
    adapter = build_adapter()
    system, contents = adapter._convert_messages(
        [
            Message(
                role=MessageRole.SYSTEM,
                content=[ContentPart(type=ContentType.TEXT, text="rules")],
            ),
            Message(
                role=MessageRole.USER,
                content=[
                    ContentPart(type=ContentType.TEXT, text="look"),
                    ContentPart(
                        type=ContentType.IMAGE,
                        image=ImageContent(base64="aGVsbG8=", format="jpeg"),
                    ),
                    ContentPart(
                        type=ContentType.IMAGE,
                        image=ImageContent(url="gs://bucket/image.png"),
                    ),
                ],
            ),
            Message(
                role=MessageRole.ASSISTANT,
                content="answer",
                reasoning_content="thought",
                tool_calls=[
                    ToolCall(
                        id="call-1",
                        function=FunctionCall(name="lookup", arguments="not-json"),
                    )
                ],
            ),
            Message(role=MessageRole.TOOL, content="plain", tool_call_id=None),
        ]
    )

    assert system == "rules"
    assert contents[0]["parts"] == [
        {"text": "look"},
        {"inline_data": {"mime_type": "image/jpeg", "data": "aGVsbG8="}},
        {"file_data": {"file_uri": "gs://bucket/image.png"}},
    ]
    assert contents[1]["parts"][-1] == {"function_call": {"name": "lookup", "args": {}}}
    assert contents[2]["parts"][0]["function_response"] == {
        "name": "unknown",
        "response": {"result": "plain"},
    }
    assert adapter.convert_tools(None) is None


@pytest.mark.anyio
async def test_chat_builds_structured_tool_thinking_request_and_response():
    provider_response = response(
        [
            ns(thought=True, text=" think "),
            ns(thought=False, function_call=ns(name="lookup", args={"q": 1})),
            ns(thought=False, function_call=None, text=" answer "),
        ],
        finish_reason="MAX_TOKENS",
    )
    client, models = sdk_client(result=provider_response)
    adapter = build_adapter(
        default_params={
            "temperature": 0.2,
            "top_p": 0.8,
            "max_tokens": 100,
            "thinking": {"enabled": True, "budget": 256},
        }
    )
    tool = ToolDefinition(
        function=FunctionDefinition(
            name="lookup", description="Search", parameters={"type": "object"}
        )
    )

    sdk_patch, factory = mock_sdk(client)
    with sdk_patch:
        result = await adapter.chat(
            [
                Message(role=MessageRole.SYSTEM, content="rules"),
                Message(role=MessageRole.USER, content="hi"),
            ],
            tools=[tool],
            response_format={
                "type": "json_schema",
                "json_schema": {"schema": {"type": "object"}},
            },
        )

    factory.assert_called_once_with(
        api_key="secret", http_options={"base_url": "https://gemini.invalid"}
    )
    config = models.generate_content.await_args.kwargs["config"]
    assert config == {
        "system_instruction": "rules",
        "generation_config": {
            "temperature": 0.2,
            "top_p": 0.8,
            "max_output_tokens": 100,
            "thinking_config": {"thinking_budget": 256},
            "response_schema": {"type": "object"},
            "response_mime_type": "application/json",
        },
        "tools": [
            {
                "function_declarations": [
                    {
                        "name": "lookup",
                        "description": "Search",
                        "parameters": {"type": "object"},
                    }
                ]
            }
        ],
    }
    assert result.content == "answer"
    assert result.reasoning_content == "think"
    assert json.loads(result.tool_calls[0].function.arguments) == {"q": 1}
    assert result.finish_reason is FinishReason.TOOL_CALLS
    assert result.usage.total_tokens == 5


@pytest.mark.anyio
async def test_stream_skips_empty_chunks_and_emits_thinking_tool_text_and_finish():
    stream = AsyncChunks(
        [
            ns(candidates=[]),
            ns(candidates=[ns(content=None)]),
            response([], finish_reason=None, usage=False),
            response(
                [
                    ns(thought=True, text="reason"),
                    ns(thought=False, function_call=ns(name="lookup", args=None)),
                    ns(thought=False, function_call=None, text="answer"),
                ],
                finish_reason="SAFETY",
                usage=False,
            ),
        ]
    )
    client, models = sdk_client(stream=stream)

    sdk_patch, _ = mock_sdk(client)
    with sdk_patch:
        chunks = [
            chunk
            async for chunk in build_adapter(
                base_url=None, config={"thinking": False}
            ).chat_stream(
                [Message(role=MessageRole.USER, content="hi")],
                response_format={"type": "json_object"},
            )
        ]

    assert models.generate_content_stream.await_args.kwargs["config"] == {
        "generation_config": {
            "thinking_config": {"thinking_budget": 0},
            "response_mime_type": "application/json",
        }
    }
    assert chunks[0].delta.reasoning_content == "reason"
    assert chunks[1].delta.stream_activity is True
    assert chunks[2].delta.content == "answer"
    assert chunks[3].finish_reason is FinishReason.TOOL_CALLS
    assert chunks[3].delta.tool_calls[0].function.name == "lookup"


def test_conversion_and_response_empty_sdk_shapes_and_finish_mappings():
    adapter = build_adapter()
    system, contents = adapter._convert_messages(
        [
            Message.model_construct(
                role=MessageRole.SYSTEM,
                content=[ns(text=None), {"text": "dict rules"}],
            ),
            Message.model_construct(
                role=MessageRole.TOOL,
                content=[ns(text="one"), {"text": "two"}],
                tool_call_id="lookup",
            ),
            Message.model_construct(
                role=MessageRole.USER,
                content=[
                    ContentPart(type=ContentType.IMAGE, image=None),
                    {"text": "dict text"},
                ],
            ),
            Message(
                role=MessageRole.ASSISTANT,
                tool_calls=[
                    ToolCall(
                        id="call-2",
                        function=FunctionCall(name="lookup", arguments='{"q": 2}'),
                    )
                ],
            ),
            Message(role=MessageRole.USER, content=""),
        ]
    )

    assert system == "dict rules"
    assert contents[0]["parts"][0]["function_response"] == {
        "name": "lookup",
        "response": {"result": "one\ntwo"},
    }
    assert contents[1]["parts"] == [{"text": "dict text"}]
    assert contents[2]["parts"] == [
        {"function_call": {"name": "lookup", "args": {"q": 2}}}
    ]
    assert adapter.convert_tools(
        [ToolDefinition(function=FunctionDefinition(name="ping"))]
    ) == [{"function_declarations": [{"name": "ping", "description": ""}]}]

    assert adapter._extract_response(ns(candidates=[])) == (None, None, None)
    assert adapter._extract_response(ns(candidates=[ns(content=None)])) == (
        None,
        None,
        None,
    )
    assert adapter._extract_response(response([])) == (None, None, None)
    assert (
        adapter._extract_response(
            response(
                [
                    ns(thought=True, text=""),
                    ns(thought=False, function_call=ns(args=None)),
                    ns(thought=False, function_call=None, text=""),
                ]
            )
        )[2][0].function.name
        == ""
    )

    assert adapter._map_finish_reason(None) is FinishReason.STOP
    assert adapter._map_finish_reason("STOP") is FinishReason.STOP
    assert adapter._map_finish_reason("LENGTH") is FinishReason.LENGTH
    assert adapter._map_finish_reason("SAFETY") is FinishReason.CONTENT_FILTER
    assert adapter._map_finish_reason("FUNCTION_CALL") is FinishReason.TOOL_CALLS
    assert adapter._map_finish_reason("UNKNOWN") is FinishReason.STOP


@pytest.mark.anyio
async def test_chat_minimal_request_without_usage_or_candidates():
    provider_response = ns(candidates=[], usage_metadata=None)
    client, models = sdk_client(result=provider_response)
    adapter = build_adapter(base_url=None)
    sdk_patch, factory = mock_sdk(client)

    with sdk_patch:
        result = await adapter.chat(
            [Message(role=MessageRole.USER, content="hi")],
            tools=[ToolDefinition(function=FunctionDefinition(name="ping"))],
            response_format="ignored",
        )

    factory.assert_called_once_with(api_key="secret")
    assert models.generate_content.await_args.kwargs["config"] == {
        "tools": [{"function_declarations": [{"name": "ping", "description": ""}]}]
    }
    assert result.content is None
    assert result.finish_reason is FinishReason.STOP
    assert result.usage.total_tokens == 0


@pytest.mark.anyio
async def test_chat_json_mode_disables_thinking_without_system_or_tools():
    client, models = sdk_client(result=response([ns(thought=False, text="json")]))
    adapter = build_adapter(config={"thinking": False})
    sdk_patch, _ = mock_sdk(client)

    with sdk_patch:
        result = await adapter.chat(
            [Message(role=MessageRole.USER, content="hi")],
            response_format={"type": "json_object"},
        )

    assert models.generate_content.await_args.kwargs["config"] == {
        "generation_config": {
            "thinking_config": {"thinking_budget": 0},
            "response_mime_type": "application/json",
        }
    }
    assert result.content == "json"


@pytest.mark.anyio
async def test_stream_builds_full_schema_request_and_finishes_without_tools():
    stream = AsyncChunks(
        [
            response(
                [
                    ns(thought=True, text=""),
                    ns(thought=False, function_call=None, text=""),
                    ns(thought=False, function_call=None, text="done"),
                ],
                finish_reason="STOP",
                usage=False,
            )
        ]
    )
    client, models = sdk_client(stream=stream)
    adapter = build_adapter(
        default_params={
            "temperature": 0.1,
            "top_p": 0.9,
            "max_tokens": 64,
            "thinking": {"enabled": True},
        }
    )
    sdk_patch, _ = mock_sdk(client)

    with sdk_patch:
        chunks = [
            chunk
            async for chunk in adapter.chat_stream(
                [
                    Message(role=MessageRole.SYSTEM, content="rules"),
                    Message(role=MessageRole.USER, content="hi"),
                ],
                tools=[ToolDefinition(function=FunctionDefinition(name="ping"))],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"schema": {"type": "string"}},
                },
            )
        ]

    assert models.generate_content_stream.await_args.kwargs["config"] == {
        "system_instruction": "rules",
        "generation_config": {
            "temperature": 0.1,
            "top_p": 0.9,
            "max_output_tokens": 64,
            "thinking_config": {"thinking_budget": 8192},
            "response_schema": {"type": "string"},
            "response_mime_type": "application/json",
        },
        "tools": [{"function_declarations": [{"name": "ping", "description": ""}]}],
    }
    assert chunks[0].delta.content == "done"
    assert chunks[1].delta.tool_calls is None
    assert chunks[1].finish_reason is FinishReason.STOP


@pytest.mark.anyio
@pytest.mark.parametrize("streaming", [False, True])
async def test_provider_errors_propagate_from_mocked_sdk(streaming):
    client, _ = sdk_client(error=RuntimeError("provider failed"))
    adapter = build_adapter()

    sdk_patch, _ = mock_sdk(client)
    with sdk_patch, pytest.raises(RuntimeError, match="provider failed"):
        if streaming:
            await anext(
                adapter.chat_stream([Message(role=MessageRole.USER, content="hi")])
            )
        else:
            await adapter.chat([Message(role=MessageRole.USER, content="hi")])
