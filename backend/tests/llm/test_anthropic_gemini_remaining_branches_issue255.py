import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.llm.adapters.chat.anthropic_adapter import AnthropicAdapter
from app.llm.adapters.chat.gemini_adapter import GeminiAdapter
from app.llm.types import FinishReason, FunctionCall, Message, MessageRole, ToolCall


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


def test_remaining_conversion_and_extraction_branches():
    messages = [
        obj(
            role="system", content=[obj(text="rules"), {"text": "more"}, obj(text=None)]
        ),
        obj(
            role="user",
            content=[
                obj(type=obj(value="text"), text="hello"),
                obj(type="image", image=obj(base64="aW1n", format=None, url=None)),
                obj(
                    type="image",
                    image=obj(base64=None, format=None, url="https://image.invalid/a"),
                ),
                obj(type="image", image=None),
                {"text": "raw"},
            ],
            reasoning_content=None,
            tool_calls=None,
        ),
        obj(
            role="assistant",
            content=[obj(text="answer"), obj(text=None)],
            reasoning_content="thought",
            tool_calls=[
                ToolCall(
                    id="call-1",
                    function=FunctionCall(name="lookup", arguments='{"q": 1}'),
                ),
                ToolCall(
                    id="call-2",
                    function=FunctionCall(name="broken", arguments="not-json"),
                ),
            ],
        ),
        obj(
            role="tool",
            content=[obj(text="result"), {"text": "more"}, obj(text=None)],
            tool_call_id=None,
        ),
        obj(role="assistant", content=None, reasoning_content=None, tool_calls=None),
        obj(role="user", content=[], reasoning_content=None, tool_calls=None),
    ]

    anthropic = adapter(
        AnthropicAdapter, default_params={"thinking": {"enabled": True}}
    )
    system, converted = anthropic._convert_messages(messages)
    assert system == "rules\nmore"
    assert converted[0]["content"][1]["source"]["media_type"] == "image/png"
    assert converted[0]["content"][2]["source"]["type"] == "url"
    assert converted[1]["content"][-1]["input"] == {}
    assert converted[2]["content"][0]["content"] == "result\nmore"
    assert converted[-1]["content"] == ""

    gemini = adapter(GeminiAdapter)
    system, converted = gemini._convert_messages(messages)
    assert system == "rules\nmore"
    assert converted[0]["parts"][1]["inline_data"]["mime_type"] == "image/png"
    assert converted[0]["parts"][2]["file_data"]["file_uri"].startswith("https://")
    assert converted[1]["parts"][-1]["function_call"]["args"] == {}
    assert converted[2]["parts"][0]["function_response"] == {
        "name": "unknown",
        "response": {"result": "result\nmore"},
    }

    assert gemini._extract_response(obj(candidates=[])) == (None, None, None)
    assert gemini._extract_response(obj(candidates=[obj(content=None)])) == (
        None,
        None,
        None,
    )
    assert gemini._extract_response(obj(candidates=[obj(content=obj(parts=[]))])) == (
        None,
        None,
        None,
    )
    content, reasoning, calls = gemini._extract_response(
        obj(
            candidates=[
                obj(
                    content=obj(
                        parts=[
                            obj(thought=True, text=" thought "),
                            obj(
                                thought=False,
                                function_call=obj(name="lookup", args=None),
                            ),
                            obj(thought=False, function_call=None, text=" answer "),
                        ]
                    )
                )
            ]
        )
    )
    assert (content, reasoning) == ("answer", "thought")
    assert calls and json.loads(calls[0].function.arguments) == {}
    assert gemini._map_finish_reason("MAX_TOKENS") == FinishReason.LENGTH
    assert gemini._map_finish_reason("SAFETY") == FinishReason.CONTENT_FILTER
    assert gemini._map_finish_reason("FUNCTION") == FinishReason.TOOL_CALLS
    assert gemini._map_finish_reason("OTHER") == FinishReason.STOP


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


@pytest.mark.anyio
async def test_remaining_sdk_and_stream_branches(monkeypatch):
    anthropic_client = obj(
        messages=obj(
            create=AsyncMock(
                return_value=obj(
                    id="message-1", content=[], stop_reason="end_turn", usage=None
                )
            ),
            stream=lambda **kwargs: AnthropicStream(
                [
                    obj(type="content_block_start", content_block=None),
                    obj(type="content_block_start", content_block=obj(type="text")),
                    obj(type="content_block_delta", delta=None),
                    obj(
                        type="content_block_delta",
                        delta=obj(type="text_delta", text=None),
                    ),
                    obj(
                        type="content_block_delta",
                        delta=obj(type="thinking_delta", thinking=None),
                    ),
                    obj(
                        type="content_block_delta",
                        delta=obj(type="input_json_delta", partial_json="ignored"),
                    ),
                    obj(type="content_block_stop"),
                    obj(type="message_stop"),
                    obj(type="message_delta", delta=None),
                ]
            ),
        ),
        close=AsyncMock(),
    )
    monkeypatch.setattr("anthropic.AsyncAnthropic", lambda **kwargs: anthropic_client)
    anthropic = adapter(AnthropicAdapter)

    result = await anthropic.chat(
        [Message(role=MessageRole.USER, content="hello")],
        response_format={"type": "json_schema", "json_schema": {}},
    )
    assert result.usage.total_tokens == 0
    assert anthropic_client.messages.create.await_args.kwargs["thinking"] == {
        "type": "disabled"
    }

    chunks = [
        chunk
        async for chunk in anthropic.chat_stream(
            [Message(role=MessageRole.USER, content="hello")]
        )
    ]
    assert chunks == []
    assert anthropic_client.close.await_count == 2

    empty_chunks = [
        obj(candidates=[]),
        obj(candidates=[obj(content=None)]),
        obj(candidates=[obj(content=obj(parts=[]))]),
        obj(
            candidates=[
                obj(
                    content=obj(
                        parts=[
                            obj(thought=True, text=""),
                            obj(thought=False, function_call=None, text=""),
                        ]
                    ),
                    finish_reason=None,
                )
            ]
        ),
    ]
    models = obj(
        generate_content=AsyncMock(
            return_value=obj(candidates=[], usage_metadata=None)
        ),
        generate_content_stream=AsyncMock(return_value=GeminiStream(empty_chunks)),
    )
    client_calls = []

    def gemini_client(**kwargs):
        client_calls.append(kwargs)
        return obj(aio=obj(models=models))

    monkeypatch.setattr("google.genai.Client", gemini_client)
    gemini = adapter(GeminiAdapter, config={"thinking": False})

    result = await gemini.chat([Message(role=MessageRole.USER, content="hello")])
    assert result.finish_reason == FinishReason.STOP
    assert result.usage.total_tokens == 0

    chunks = [
        chunk
        async for chunk in gemini.chat_stream(
            [Message(role=MessageRole.USER, content="hello")],
            response_format={"type": "json_schema", "json_schema": {}},
        )
    ]
    assert chunks == []
    assert client_calls == [{"api_key": "secret"}, {"api_key": "secret"}]
