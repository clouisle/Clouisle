import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.llm.adapters.chat.anthropic_adapter import AnthropicAdapter
from app.llm.adapters.chat.gemini_adapter import GeminiAdapter
from app.llm.types import FunctionDefinition, Message, MessageRole, ToolDefinition


def obj(**values):
    return SimpleNamespace(**values)


def adapter(adapter_type, **overrides):
    values = {
        "model_id": "test-model",
        "api_key": "secret",
        "base_url": None,
        "config": {},
        "default_params": {},
        "max_output_tokens": None,
    }
    values.update(overrides)
    return adapter_type(obj(**values))


class AnthropicStream:
    def __init__(self, events):
        self.events = iter(events)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    def __aiter__(self):
        return self

    async def __anext__(self):
        event = next(self.events, None)
        if event is None:
            raise StopAsyncIteration
        return event


class GeminiStream:
    def __init__(self, chunks):
        self.chunks = iter(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        chunk = next(self.chunks, None)
        if chunk is None:
            raise StopAsyncIteration
        return chunk


def test_conversion_residual_false_paths():
    messages = [
        obj(role="assistant", content=17, reasoning_content=None, tool_calls=None),
        obj(role="assistant", content=[], reasoning_content=None, tool_calls=None),
        obj(
            role="assistant",
            content=None,
            reasoning_content=None,
            tool_calls=[obj(id="call", function=obj(name="lookup", arguments={}))],
        ),
        obj(
            role="tool",
            content=[{"ignored": True}, obj(text="result")],
            tool_call_id="call",
        ),
        obj(
            role="user",
            content=[obj(type="image"), obj(type="ignored"), object(), {}],
            reasoning_content=None,
            tool_calls=None,
        ),
    ]

    anthropic = adapter(AnthropicAdapter)
    _, anthropic_messages = anthropic._convert_messages(messages)
    _, gemini_messages = adapter(GeminiAdapter)._convert_messages(messages)

    assert anthropic._convert_messages(
        [
            obj(
                role="assistant",
                content="answer",
                reasoning_content=None,
                tool_calls=None,
            )
        ]
    )[1][0]["content"] == [{"type": "text", "text": "answer"}]
    assert anthropic_messages[0]["content"][-1]["input"] == {}
    assert anthropic_messages[1]["content"][0]["content"] == "result"
    assert anthropic_messages[-1]["content"] == [{}]
    assert gemini_messages[0]["parts"][-1]["function_call"]["args"] == {}
    assert gemini_messages[1]["parts"][0]["function_response"]["response"] == {
        "result": "result"
    }


@pytest.mark.anyio
async def test_anthropic_request_and_stream_residual_arcs(monkeypatch):
    response = obj(id="message", content=[], stop_reason="end_turn", usage=None)
    client = obj(
        messages=obj(
            create=AsyncMock(return_value=response),
            stream=lambda **kwargs: AnthropicStream(
                [
                    obj(
                        type="content_block_delta",
                        delta=obj(type="input_json_delta", partial_json="ignored"),
                    ),
                    obj(
                        type="content_block_delta",
                        delta=obj(type="unknown"),
                    ),
                    obj(
                        type="content_block_start",
                        content_block=obj(type="tool_use", id="call", name="lookup"),
                    ),
                    obj(type="content_block_stop"),
                ]
            ),
        ),
        close=AsyncMock(),
    )
    monkeypatch.setattr("anthropic.AsyncAnthropic", lambda **kwargs: client)
    anthropic = adapter(
        AnthropicAdapter, default_params={"thinking": {"enabled": True}}
    )

    await anthropic.chat(
        [Message(role=MessageRole.USER, content="hi")], response_format="ignored"
    )
    await adapter(AnthropicAdapter).chat(
        [Message(role=MessageRole.USER, content="hi")],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "schema": {"type": "object", "additionalProperties": False}
            },
        },
    )
    await anthropic.chat(
        [Message(role=MessageRole.USER, content="hi")],
        response_format={"type": "unsupported"},
    )

    empty = anthropic.create_response(content=None, reasoning_content=None)
    monkeypatch.setattr(anthropic, "chat", AsyncMock(return_value=empty))
    chunks = [
        chunk
        async for chunk in anthropic.chat_stream(
            [Message(role=MessageRole.USER, content="hi")],
            response_format={"type": "json_object"},
        )
    ]
    assert len(chunks) == 1

    chunks = [
        chunk
        async for chunk in anthropic.chat_stream(
            [Message(role=MessageRole.USER, content="hi")],
            tools=[ToolDefinition(function=FunctionDefinition(name="lookup"))],
        )
    ]
    assert chunks[-1].delta.stream_activity is True


def gemini_sdk(client):
    google = ModuleType("google")
    genai = ModuleType("google.genai")
    genai.Client = Mock(return_value=client)
    google.genai = genai
    return patch.dict(sys.modules, {"google": google, "google.genai": genai})


@pytest.mark.anyio
async def test_gemini_response_format_and_stream_residual_arcs():
    provider_response = obj(candidates=[], usage_metadata=None)
    stream = GeminiStream(
        [
            obj(
                candidates=[
                    obj(
                        content=obj(parts=[obj(thought=True, text="")]),
                        finish_reason=None,
                    )
                ]
            )
        ]
    )
    models = obj(
        generate_content=AsyncMock(return_value=provider_response),
        generate_content_stream=AsyncMock(return_value=stream),
    )
    client = obj(aio=obj(models=models))
    gemini = adapter(GeminiAdapter)

    with gemini_sdk(client):
        for response_format in (
            {"type": "json_schema", "json_schema": {}},
            {"type": "json_schema", "json_schema": {"schema": None}},
            {"type": "unsupported"},
        ):
            await gemini.chat(
                [Message(role=MessageRole.USER, content="hi")],
                response_format=response_format,
            )

        for response_format in (
            "ignored",
            {"type": "json_schema", "json_schema": {}},
            {"type": "json_schema", "json_schema": {"schema": None}},
            {"type": "unsupported"},
        ):
            stream.chunks = iter(
                [
                    obj(
                        candidates=[
                            obj(
                                content=obj(parts=[obj(thought=True, text="")]),
                                finish_reason=None,
                            )
                        ]
                    )
                ]
            )
            chunks = [
                chunk
                async for chunk in gemini.chat_stream(
                    [Message(role=MessageRole.USER, content="hi")],
                    tools=[ToolDefinition(function=FunctionDefinition(name="lookup"))],
                    response_format=response_format,
                )
            ]

    assert chunks == []
    assert models.generate_content_stream.await_args.kwargs["config"] == {
        "tools": [{"function_declarations": [{"name": "lookup", "description": ""}]}]
    }
