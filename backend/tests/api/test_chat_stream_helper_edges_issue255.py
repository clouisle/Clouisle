from app.api.v1.endpoints.chat import (
    _extract_llm_error_message,
    _format_llm_error_message,
    _is_model_stream_activity,
)
from app.llm.types import (
    ChatStreamChunk,
    ChatStreamDelta,
    FinishReason,
    FunctionCall,
    ToolCall,
)


def chunk(**values):
    return ChatStreamChunk(
        id="chunk-1",
        model="model-1",
        delta=ChatStreamDelta(**values.pop("delta", {})),
        **values,
    )


def test_stream_activity_predicate_covers_all_activity_sources():
    tool_call = ToolCall(
        id="tool-1",
        function=FunctionCall(name="lookup", arguments="{}"),
    )

    assert not _is_model_stream_activity(chunk())
    assert _is_model_stream_activity(chunk(delta={"content": "hello"}))
    assert _is_model_stream_activity(chunk(delta={"reasoning_content": "think"}))
    assert _is_model_stream_activity(chunk(delta={"tool_calls": [tool_call]}))
    assert _is_model_stream_activity(chunk(delta={"stream_activity": True}))
    assert _is_model_stream_activity(chunk(finish_reason=FinishReason.STOP))


def test_llm_error_message_extraction_handles_provider_payloads_and_fallbacks(
    monkeypatch,
):
    calls = []

    def fake_t(key, **kwargs):
        calls.append((key, kwargs))
        return f"{key}:{kwargs.get('message', '')}"

    monkeypatch.setattr("app.api.v1.endpoints.chat.t", fake_t)

    provider_error = Exception("400 - {'error': {'message': 'bad request'}}")
    malformed_error = Exception("400 - not-a-dict")

    class EmptyMessageError(Exception):
        message = ""

        def __str__(self):
            return ""

    empty_error = EmptyMessageError()

    assert _extract_llm_error_message(provider_error) == "bad request"
    assert _extract_llm_error_message(malformed_error) == "400 - not-a-dict"
    assert _format_llm_error_message(provider_error) == (
        "model_service_request_failed:bad request"
    )
    assert _format_llm_error_message(empty_error) == "model_call_failed:"
    assert calls[-2:] == [
        ("model_service_request_failed", {"message": "bad request"}),
        ("model_call_failed", {}),
    ]
