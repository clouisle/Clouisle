from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.llm.adapters.chat.anthropic_adapter import AnthropicAdapter
from app.llm.types import (
    ChatResponse,
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
    Usage,
)


def build_adapter(**default_params):
    model = SimpleNamespace(
        model_id="claude-test",
        api_key="test-key",
        base_url="https://anthropic.invalid",
        config={},
        default_params=default_params,
        max_output_tokens=None,
    )
    return AnthropicAdapter(model)


class FakeStream:
    def __init__(self, events):
        self.events = events

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for event in self.events:
            yield event


def fake_client(response=None, events=()):
    return SimpleNamespace(
        messages=SimpleNamespace(
            create=AsyncMock(return_value=response),
            stream=Mock(return_value=FakeStream(events)),
        ),
        close=AsyncMock(),
    )


def test_converts_all_message_content_variants():
    adapter = build_adapter(thinking={"enabled": True})
    messages = [
        Message(
            role=MessageRole.SYSTEM,
            content=[ContentPart(type=ContentType.TEXT, text="rules")],
        ),
        Message(
            role=MessageRole.ASSISTANT,
            content=[ContentPart(type=ContentType.TEXT, text="answer")],
            reasoning_content="thought",
            tool_calls=[
                ToolCall(
                    id="valid",
                    function=FunctionCall(name="search", arguments='{"q": "x"}'),
                ),
                ToolCall(
                    id="invalid",
                    function=FunctionCall(name="broken", arguments="not-json"),
                ),
            ],
        ),
        Message(
            role=MessageRole.TOOL,
            tool_call_id="valid",
            content=[ContentPart(type=ContentType.TEXT, text="result")],
        ),
        Message(
            role=MessageRole.USER,
            content=[
                ContentPart(type=ContentType.TEXT, text="look"),
                ContentPart(
                    type=ContentType.IMAGE,
                    image=ImageContent(base64="aW1hZ2U=", format="jpeg"),
                ),
                ContentPart(
                    type=ContentType.IMAGE,
                    image=ImageContent(url="https://example.invalid/image.png"),
                ),
            ],
        ),
    ]

    system, converted = adapter._convert_messages(messages)

    assert system == "rules"
    assert converted[0]["content"] == [
        {"type": "thinking", "thinking": "thought"},
        {"type": "text", "text": "answer"},
        {"type": "tool_use", "id": "valid", "name": "search", "input": {"q": "x"}},
        {"type": "tool_use", "id": "invalid", "name": "broken", "input": {}},
    ]
    assert converted[1]["content"][0] == {
        "type": "tool_result",
        "tool_use_id": "valid",
        "content": "result",
    }
    assert converted[2]["content"] == [
        {"type": "text", "text": "look"},
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": "aW1hZ2U=",
            },
        },
        {
            "type": "image",
            "source": {
                "type": "url",
                "url": "https://example.invalid/image.png",
            },
        },
    ]


def test_converts_dict_parts_empty_messages_and_tools():
    adapter = build_adapter()
    system_message = Message.model_construct(
        role="system", content=[{"text": "one"}, {"text": "two"}]
    )
    user_message = Message.model_construct(
        role="user", content=[{"type": "custom", "value": 1}]
    )
    tool_message = Message.model_construct(
        role="tool", content=[{"text": "done"}], tool_call_id="call-1"
    )
    empty_assistant = Message(role=MessageRole.ASSISTANT)

    system, converted = adapter._convert_messages(
        [system_message, empty_assistant, user_message, tool_message]
    )

    assert system == "one\ntwo"
    assert converted == [
        {"role": "user", "content": [{"type": "custom", "value": 1}]},
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "call-1",
                    "content": "done",
                }
            ],
        },
    ]
    assert adapter.convert_tools(None) is None
    assert adapter.convert_tools(
        [
            ToolDefinition(
                function=FunctionDefinition(
                    name="lookup", parameters={"type": "object"}
                )
            )
        ]
    ) == [
        {
            "name": "lookup",
            "description": "",
            "input_schema": {"type": "object"},
        }
    ]


def test_extracts_response_blocks_and_finish_reasons():
    adapter = build_adapter()
    response = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text=" hello "),
            SimpleNamespace(type="thinking", thinking=" reason "),
            SimpleNamespace(
                type="tool_use", id="call-1", name="lookup", input={"x": 1}
            ),
            SimpleNamespace(type="tool_use", id="call-2", name="raw", input="value"),
            SimpleNamespace(type="unknown"),
        ]
    )

    content, reasoning, tool_calls = adapter._extract_response(response)

    assert content == "hello"
    assert reasoning == "reason"
    assert tool_calls is not None
    assert [call.function.arguments for call in tool_calls] == ['{"x": 1}', "value"]
    assert adapter._extract_response(SimpleNamespace(content=[])) == (None, None, None)
    assert adapter._map_finish_reason("tool_use") == FinishReason.TOOL_CALLS
    assert adapter._map_finish_reason("max_tokens") == FinishReason.LENGTH
    assert adapter._map_finish_reason("stop_sequence") == FinishReason.STOP
    assert adapter._map_finish_reason(None) == FinishReason.STOP


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("response_format", "expected_schema"),
    [
        (
            {"type": "json_schema", "json_schema": {"schema": {"type": "object"}}},
            {"type": "object", "additionalProperties": False},
        ),
        (
            {"type": "json_object"},
            {"type": "object", "additionalProperties": False},
        ),
    ],
)
async def test_chat_builds_structured_output_without_thinking(
    response_format, expected_schema
):
    adapter = build_adapter(
        thinking={"enabled": True, "budget_tokens": 2048},
        temperature=0.2,
        top_p=0.8,
        extra_body={"service_tier": "standard"},
    )
    response = SimpleNamespace(
        id="response-1",
        content=[SimpleNamespace(type="text", text='{"ok": true}')],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=3, output_tokens=2),
    )
    client = fake_client(response=response)

    with patch("anthropic.AsyncAnthropic", return_value=client):
        result = await adapter.chat(
            [Message(role=MessageRole.USER, content="Hi")],
            response_format=response_format,
        )

    request = client.messages.create.await_args.kwargs
    assert request["output_config"]["format"]["schema"] == expected_schema
    assert "thinking" not in request
    assert request["temperature"] == 0.2
    assert request["top_p"] == 0.8
    assert request["extra_body"] == {"service_tier": "standard"}
    assert result.content == '{"ok": true}'
    assert result.usage == Usage(
        prompt_tokens=3,
        completion_tokens=2,
        total_tokens=5,
        total_input_tokens=3,
    )
    client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_chat_closes_client_when_request_fails():
    adapter = build_adapter()
    client = fake_client()
    client.messages.create.side_effect = RuntimeError("request failed")

    with (
        patch("anthropic.AsyncAnthropic", return_value=client),
        pytest.raises(RuntimeError, match="request failed"),
    ):
        await adapter.chat([Message(role=MessageRole.USER, content="Hi")])

    client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_structured_stream_simulates_content_reasoning_and_final_chunk():
    adapter = build_adapter()
    adapter.chat = AsyncMock(
        return_value=ChatResponse(
            id="response-1",
            model="claude-test",
            content="abcdefghijkl",
            reasoning_content="reason",
            tool_calls=None,
            finish_reason=FinishReason.STOP,
            usage=Usage(prompt_tokens=1, completion_tokens=2, total_tokens=3),
        )
    )

    chunks = [
        chunk
        async for chunk in adapter.chat_stream(
            [Message(role=MessageRole.USER, content="Hi")],
            response_format={"type": "json_object"},
        )
    ]

    assert [chunk.delta.content for chunk in chunks[:2]] == ["abcdefghij", "kl"]
    assert chunks[2].delta.reasoning_content == "reason"
    assert chunks[-1].finish_reason == FinishReason.STOP
    assert chunks[-1].usage.total_tokens == 3


@pytest.mark.anyio
async def test_regular_stream_handles_text_thinking_tool_and_stop_events():
    adapter = build_adapter(
        thinking={"enabled": True, "budget_tokens": 1024},
        temperature=0.3,
        top_p=0.7,
    )
    events = [
        SimpleNamespace(
            type="content_block_start",
            content_block=SimpleNamespace(type="tool_use", id="call-1", name="lookup"),
        ),
        SimpleNamespace(
            type="content_block_delta",
            delta=SimpleNamespace(type="input_json_delta", partial_json='{"x":'),
        ),
        SimpleNamespace(
            type="content_block_delta",
            delta=SimpleNamespace(type="input_json_delta", partial_json="1}"),
        ),
        SimpleNamespace(type="content_block_stop"),
        SimpleNamespace(
            type="content_block_delta",
            delta=SimpleNamespace(type="text_delta", text="hello"),
        ),
        SimpleNamespace(
            type="content_block_delta",
            delta=SimpleNamespace(type="thinking_delta", thinking="reason"),
        ),
        SimpleNamespace(type="message_stop"),
        SimpleNamespace(
            type="message_delta", delta=SimpleNamespace(stop_reason="tool_use")
        ),
    ]
    client = fake_client(events=events)

    with patch("anthropic.AsyncAnthropic", return_value=client):
        chunks = [
            chunk
            async for chunk in adapter.chat_stream(
                [Message(role=MessageRole.USER, content="Hi")]
            )
        ]

    request = client.messages.stream.call_args.kwargs
    assert request["thinking"] == {"type": "enabled", "budget_tokens": 1024}
    assert request["temperature"] == 0.3
    assert request["top_p"] == 0.7
    assert any(chunk.delta.content == "hello" for chunk in chunks)
    assert any(chunk.delta.reasoning_content == "reason" for chunk in chunks)
    final = chunks[-1]
    assert final.finish_reason == FinishReason.TOOL_CALLS
    assert final.delta.tool_calls[0].function.arguments == '{"x":1}'
    client.close.assert_awaited_once()
