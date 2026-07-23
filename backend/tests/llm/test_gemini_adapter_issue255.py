import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

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


def adapter(**overrides):
    values = {
        "model_id": "gemini-test",
        "api_key": "secret",
        "base_url": "https://gemini.invalid",
        "config": {},
        "default_params": {},
    }
    values.update(overrides)
    return GeminiAdapter(SimpleNamespace(**values))


def part(**values):
    return SimpleNamespace(**values)


def response(parts=None, finish_reason="STOP", usage=True):
    candidate = part(content=part(parts=parts), finish_reason=finish_reason)
    return part(
        candidates=[candidate],
        usage_metadata=part(
            prompt_token_count=2, candidates_token_count=3, total_token_count=5
        )
        if usage
        else None,
    )


def install_client(monkeypatch, *, result=None, stream=None):
    models = SimpleNamespace(
        generate_content=AsyncMock(return_value=result),
        generate_content_stream=AsyncMock(return_value=stream),
    )
    factory = AsyncMock()
    factory.side_effect = None
    client_calls = []

    def client(**kwargs):
        client_calls.append(kwargs)
        return SimpleNamespace(aio=SimpleNamespace(models=models))

    monkeypatch.setattr("google.genai.Client", client)
    return models, client_calls


def test_convert_messages_and_tools_cover_multimodal_and_fallbacks():
    gemini = adapter()
    messages = [
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
                    function=FunctionCall(name="search", arguments="not-json"),
                )
            ],
        ),
        Message(role=MessageRole.TOOL, content="plain result", tool_call_id=None),
    ]

    system, contents = gemini._convert_messages(messages)

    assert system == "rules"
    assert contents[0]["parts"] == [
        {"text": "look"},
        {"inline_data": {"mime_type": "image/jpeg", "data": "aGVsbG8="}},
        {"file_data": {"file_uri": "gs://bucket/image.png"}},
    ]
    assert contents[1]["parts"][-1] == {"function_call": {"name": "search", "args": {}}}
    assert contents[2]["parts"][0]["function_response"] == {
        "name": "unknown",
        "response": {"result": "plain result"},
    }
    assert gemini.convert_tools(None) is None
    assert gemini.convert_tools(
        [ToolDefinition(function=FunctionDefinition(name="ping"))]
    ) == [{"function_declarations": [{"name": "ping", "description": ""}]}]


def test_extract_response_and_finish_reason_edges():
    gemini = adapter()
    assert gemini._extract_response(part(candidates=[])) == (None, None, None)
    assert gemini._extract_response(part(candidates=[part(content=None)])) == (
        None,
        None,
        None,
    )
    assert gemini._extract_response(response(parts=[])) == (None, None, None)

    content, reasoning, calls = gemini._extract_response(
        response(
            parts=[
                part(thought=True, text=" think "),
                part(thought=False, function_call=part(name="lookup", args={"q": 1})),
                part(thought=False, function_call=None, text=" answer "),
            ]
        )
    )
    assert content == "answer"
    assert reasoning == "think"
    assert calls and calls[0].function.name == "lookup"
    assert json.loads(calls[0].function.arguments) == {"q": 1}

    assert gemini._map_finish_reason(None) == FinishReason.STOP
    assert gemini._map_finish_reason("MAX_TOKENS") == FinishReason.LENGTH
    assert gemini._map_finish_reason("SAFETY") == FinishReason.CONTENT_FILTER
    assert gemini._map_finish_reason("FUNCTION_CALL") == FinishReason.TOOL_CALLS
    assert gemini._map_finish_reason("OTHER") == FinishReason.STOP


@pytest.mark.anyio
async def test_chat_builds_config_and_parses_tool_response(monkeypatch):
    provider_response = response(
        parts=[part(thought=False, function_call=part(name="lookup", args=None))],
        finish_reason="STOP",
    )
    models, client_calls = install_client(monkeypatch, result=provider_response)
    gemini = adapter(
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

    result = await gemini.chat(
        [
            Message(role=MessageRole.SYSTEM, content="rules"),
            Message(role="user", content="hi"),
        ],
        tools=[tool],
        response_format={
            "type": "json_schema",
            "json_schema": {"schema": {"type": "object"}},
        },
    )

    assert client_calls == [
        {"api_key": "secret", "http_options": {"base_url": "https://gemini.invalid"}}
    ]
    request = models.generate_content.await_args.kwargs
    config = request["config"]
    assert config["system_instruction"] == "rules"
    assert config["generation_config"] == {
        "temperature": 0.2,
        "top_p": 0.8,
        "max_output_tokens": 100,
        "thinking_config": {"thinking_budget": 256},
        "response_schema": {"type": "object"},
        "response_mime_type": "application/json",
    }
    assert config["tools"][0]["function_declarations"][0]["name"] == "lookup"
    assert result.finish_reason == FinishReason.TOOL_CALLS
    assert result.usage.total_tokens == 5


class Stream:
    def __init__(self, chunks):
        self.chunks = chunks

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.chunks:
            raise StopAsyncIteration
        return self.chunks.pop(0)


@pytest.mark.anyio
async def test_chat_stream_skips_empty_chunks_and_emits_all_part_types(monkeypatch):
    chunks = [
        part(candidates=[]),
        part(candidates=[part(content=None)]),
        part(candidates=[part(content=part(parts=[]))]),
        response(
            parts=[
                part(thought=True, text="reason"),
                part(thought=False, function_call=part(name="lookup", args={"q": "x"})),
                part(thought=False, function_call=None, text="answer"),
            ],
            finish_reason="MAX_TOKENS",
            usage=False,
        ),
    ]
    models, _ = install_client(monkeypatch, stream=Stream(chunks))
    gemini = adapter(base_url=None, config={"thinking": False})

    result = [
        chunk
        async for chunk in gemini.chat_stream(
            [Message(role="user", content="hi")],
            response_format={"type": "json_object"},
        )
    ]

    models.generate_content_stream.assert_awaited_once()
    config = models.generate_content_stream.await_args.kwargs["config"][
        "generation_config"
    ]
    assert config == {
        "thinking_config": {"thinking_budget": 0},
        "response_mime_type": "application/json",
    }
    assert result[0].delta.reasoning_content == "reason"
    assert result[1].delta.stream_activity is True
    assert result[2].delta.content == "answer"
    assert result[3].finish_reason == FinishReason.TOOL_CALLS
    assert result[3].delta.tool_calls[0].function.name == "lookup"
