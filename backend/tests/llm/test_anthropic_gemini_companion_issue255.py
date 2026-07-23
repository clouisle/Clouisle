import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.llm.adapters.chat.anthropic_adapter import AnthropicAdapter
from app.llm.adapters.chat.gemini_adapter import GeminiAdapter
from app.llm.types import FinishReason, Message, MessageRole


def obj(**values):
    return SimpleNamespace(**values)


def model_config(model_id="test-model", **overrides):
    values = {
        "model_id": model_id,
        "api_key": "test-key",
        "base_url": None,
        "config": {},
        "default_params": {},
        "max_output_tokens": None,
    }
    values.update(overrides)
    return obj(**values)


class AsyncChunks:
    def __init__(self, chunks):
        self.chunks = list(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.chunks:
            raise StopAsyncIteration
        chunk = self.chunks.pop(0)
        if isinstance(chunk, Exception):
            raise chunk
        return chunk


def test_anthropic_conversion_and_empty_extraction_edges():
    anthropic = AnthropicAdapter(model_config(default_params={"thinking": True}))
    messages = [
        obj(role=MessageRole.SYSTEM, content=[{"text": "rules"}, obj(text="more")]),
        obj(role=MessageRole.USER, content=[]),
        obj(role=MessageRole.USER, content=[{"type": "text", "text": "raw"}]),
        obj(
            role=MessageRole.TOOL,
            content=[{"text": "tool"}, obj(text=" result")],
            tool_call_id="call-1",
        ),
    ]

    system, converted = anthropic._convert_messages(messages)
    content, reasoning, tool_calls = anthropic._extract_response(
        obj(
            content=[
                obj(type="text", text=""),
                obj(type="thinking", thinking=""),
                obj(type="tool_use", id="tool-1", name="lookup", input=None),
                obj(type="unknown"),
            ]
        )
    )

    assert system == "rules\nmore"
    assert converted[0] == {"role": "user", "content": ""}
    assert converted[1] == {
        "role": "user",
        "content": [{"type": "text", "text": "raw"}],
    }
    assert converted[2]["content"][0] == {
        "type": "tool_result",
        "tool_use_id": "call-1",
        "content": "tool\n result",
    }
    assert content is None
    assert reasoning is None
    assert tool_calls[0].function.arguments == "{}"


@pytest.mark.anyio
async def test_anthropic_chat_closes_mock_sdk_client_on_error(monkeypatch):
    client = obj(
        messages=obj(create=AsyncMock(side_effect=RuntimeError("anthropic failed"))),
        close=AsyncMock(),
    )
    monkeypatch.setattr("anthropic.AsyncAnthropic", lambda **_kwargs: client)

    with pytest.raises(RuntimeError, match="anthropic failed"):
        await AnthropicAdapter(model_config()).chat(
            [Message(role=MessageRole.USER, content="hi")]
        )

    client.close.assert_awaited_once()


def test_gemini_conversion_extract_and_finish_edges():
    gemini = GeminiAdapter(model_config())
    system, contents = gemini._convert_messages(
        [
            obj(
                role=MessageRole.SYSTEM,
                content=[{"text": "sys"}, obj(text="tem")],
                tool_calls=None,
            ),
            obj(
                role=MessageRole.TOOL,
                content="",
                tool_call_id="call-1",
                tool_calls=None,
            ),
            obj(
                role=MessageRole.ASSISTANT,
                content="",
                reasoning_content="thought",
                tool_calls=[obj(function=obj(name="fn", arguments={"x": 1}))],
            ),
            obj(
                role=MessageRole.USER,
                content=[],
                reasoning_content=None,
                tool_calls=None,
            ),
        ]
    )
    content, reasoning, tool_calls = gemini._extract_response(
        obj(
            candidates=[
                obj(
                    content=obj(
                        parts=[
                            obj(thought=True, text=""),
                            obj(function_call=obj(name="", args=None)),
                            obj(text="  "),
                        ]
                    )
                )
            ]
        )
    )

    assert system == "sys\ntem"
    assert contents[0]["parts"][0]["function_response"] == {
        "name": "call-1",
        "response": {},
    }
    assert contents[1]["parts"] == [
        {"thought": True, "text": "thought"},
        {"function_call": {"name": "fn", "args": {"x": 1}}},
    ]
    assert content is None
    assert reasoning is None
    assert json.loads(tool_calls[0].function.arguments) == {}
    assert gemini._map_finish_reason("OTHER") is FinishReason.STOP


@pytest.mark.anyio
async def test_gemini_stream_skips_empty_chunks_and_propagates_error(monkeypatch):
    models = obj(
        generate_content_stream=AsyncMock(
            return_value=AsyncChunks(
                [
                    obj(candidates=[]),
                    obj(candidates=[obj(content=None)]),
                    RuntimeError("gemini stream failed"),
                ]
            )
        )
    )
    monkeypatch.setattr(
        "google.genai.Client", lambda **_kwargs: obj(aio=obj(models=models))
    )

    with pytest.raises(RuntimeError, match="gemini stream failed"):
        _ = [
            chunk
            async for chunk in GeminiAdapter(model_config()).chat_stream(
                [Message(role=MessageRole.USER, content="hi")]
            )
        ]

    models.generate_content_stream.assert_awaited_once()
