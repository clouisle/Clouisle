import json

import pytest
from types import SimpleNamespace

from app.api.v1.endpoints.chat_sse import (
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


def test_final_and_error_event_type_contracts():
    assert SSEEventType.MESSAGE_END == "message_end"
    assert SSEEventType.ERROR == "error"
