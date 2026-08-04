import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.api.v1.endpoints.chat_sse import (
    build_compression_events,
    build_media_result_sse_event,
    build_tool_result_sse_event,
    extract_media_display_payload,
    infer_tool_result_is_error,
)
from app.schemas.agent import SSEEventType


def parse_sse(event: str) -> tuple[str, dict]:
    event_line, data_line = event.strip().splitlines()
    return event_line.removeprefix("event: "), json.loads(
        data_line.removeprefix("data: ")
    )


@pytest.mark.parametrize(
    ("display_result", "expected"),
    [
        ("not-json", False),
        ('{"success":true}', False),
        ('{"error":"   "}', False),
        ('{"error":{"message":"failed"}}', False),
        ('{"success":false}', True),
        ('{"error":"provider failed"}', True),
    ],
)
def test_tool_error_inference_covers_non_failure_shapes(display_result, expected):
    assert infer_tool_result_is_error(display_result) is expected


def test_tool_and_media_events_preserve_types_and_payloads():
    tool_event = build_tool_result_sse_event(
        tool_call_id="call-1",
        tool_name="render_video",
        tool_display_name="生成视频",
        display_result='{"success":true}',
    )
    media_result = '{"kind":"media.video","success":true,"task_id":"vid-1"}'
    media_event = build_media_result_sse_event(media_result)

    assert parse_sse(tool_event) == (
        SSEEventType.TOOL_RESULT,
        {
            "tool_call_id": "call-1",
            "tool_name": "render_video",
            "tool_display_name": "生成视频",
            "result": '{"success":true}',
            "is_error": False,
        },
    )
    assert media_event is not None
    assert parse_sse(media_event) == (
        SSEEventType.MEDIA_RESULT,
        {"kind": "media.video", "success": True, "task_id": "vid-1"},
    )
    assert extract_media_display_payload("not-json") is None
    assert extract_media_display_payload('{"kind":"other"}') is None
    assert build_media_result_sse_event("not-json") is None


def compression(**overrides):
    values = {
        "stage": "proactive",
        "before_tokens": 120,
        "after_tokens": 70,
        "input_budget": 100,
        "summary_turns": 2,
        "reasoning_trimmed": True,
        "tool_results_trimmed": True,
        "file_content_trimmed": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_compression_events_can_be_disabled_or_skipped(monkeypatch):
    config = Mock(return_value={"emit_sse_events": False})
    monkeypatch.setattr(
        "app.services.chat_context.get_context_compression_config", config
    )

    assert build_compression_events(
        agent=object(), compression=compression(), trigger="token_pressure"
    ) == (None, None)

    config.return_value = {}
    assert build_compression_events(
        agent=object(),
        compression=compression(stage="none"),
        trigger="token_pressure",
    ) == (None, None)


@pytest.mark.parametrize(
    ("trigger", "stage", "note"),
    [
        ("context_length_error", "reactive_retry", "Retried with more aggressive"),
        ("token_pressure", "reactive_retry", "Retried with more aggressive"),
        ("blocking_threshold", "blocking", "blocking-level compaction"),
        ("token_pressure", "proactive", "proactive context compaction"),
    ],
)
def test_compression_events_cover_trigger_and_terminal_usage_payloads(
    monkeypatch, trigger, stage, note
):
    monkeypatch.setattr(
        "app.services.chat_context.get_context_compression_config",
        lambda _agent: {"emit_sse_events": True},
    )

    start, end = build_compression_events(
        agent=object(),
        compression=compression(),
        trigger=trigger,
        retry_index=3,
        stage_override=stage,
    )

    assert start is not None and end is not None
    assert parse_sse(start) == (
        SSEEventType.COMPRESSION_START,
        {"stage": stage, "trigger": trigger},
    )
    event_type, payload = parse_sse(end)
    assert event_type == SSEEventType.COMPRESSION_END
    assert payload["before_tokens"] == 120
    assert payload["after_tokens"] == 70
    assert payload["input_budget"] == payload["hard_budget"] == 100
    assert payload["retry_index"] == 3
    assert note in payload["note"]
    assert "summarized 2 older turns" in payload["note"]
    assert "trimmed historical reasoning" in payload["note"]
    assert "compacted older tool results" in payload["note"]
    assert "trimmed file content" in payload["note"]
    assert payload["pressure_level"] is None
    assert payload["actions"] is None


def test_compression_end_omits_optional_note_fragments(monkeypatch):
    monkeypatch.setattr(
        "app.services.chat_context.get_context_compression_config", lambda _agent: {}
    )

    _, end = build_compression_events(
        agent=object(),
        compression=compression(
            summary_turns=0,
            reasoning_trimmed=False,
            tool_results_trimmed=False,
            file_content_trimmed=False,
        ),
        trigger="token_pressure",
    )

    assert end is not None
    _, payload = parse_sse(end)
    assert (
        payload["note"]
        == "Applied proactive context compaction before the next model call"
    )


@pytest.mark.parametrize(
    ("actions", "expected_note"),
    [
        (["checkpoint_summary"], "generated a model context checkpoint"),
        (["macro_summary"], "applied deterministic macro-summary fallback"),
    ],
)
def test_compression_events_identify_summary_strategy(
    monkeypatch, actions, expected_note
):
    monkeypatch.setattr(
        "app.services.chat_context.get_context_compression_config", lambda _agent: {}
    )

    _, end = build_compression_events(
        agent=object(),
        compression=compression(actions=actions),
        trigger="token_pressure",
    )

    assert end is not None
    _, payload = parse_sse(end)
    assert expected_note in payload["note"]


def test_final_and_error_event_type_contracts():
    assert SSEEventType.MESSAGE_END == "message_end"
    assert SSEEventType.ERROR == "error"
