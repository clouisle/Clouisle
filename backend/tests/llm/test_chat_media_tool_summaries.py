from app.api.v1.endpoints.chat_sse import (
    build_media_result_sse_event,
    build_tool_result_sse_event,
    extract_media_display_payload,
    infer_tool_result_is_error,
)
from app.services.chat_context import summarize_tool_result_for_llm


def test_summarize_tool_result_for_llm_compacts_media_image_payload():
    content = '{"kind":"media.image","success":true,"model":"google/gemini-2.5-flash-image","images":[{"image":{"url":"/api/v1/upload/files/generated-images/2026/03/test.png","base64":null,"file_path":null}}],"error":null}'

    summary = summarize_tool_result_for_llm("generate_image", content)

    assert (
        summary
        == "Image generation succeeded. Generated 1 image using model google/gemini-2.5-flash-image."
    )


def test_summarize_tool_result_for_llm_compacts_media_video_payload():
    content = '{"kind":"media.video","success":true,"model":"runway/gen4.5","task_id":"vid_123","status":"processing","video":null,"error":null}'

    summary = summarize_tool_result_for_llm("generate_video", content)

    assert summary == "Video generation started. Task vid_123 is processing."


def test_summarize_tool_result_for_llm_keeps_non_media_payload_unchanged():
    content = '{"result":"plain tool output"}'

    summary = summarize_tool_result_for_llm("search_memory", content)

    assert summary == content


def test_summarize_tool_result_for_llm_compacts_skill_instruction_payload():
    content = (
        '{"success":true,"result":{"type":"skill_instructions",'
        '"skill":{"name":"impeccable","display_name":"impeccable"},'
        '"instructions":"very long internal instructions",'
        '"arguments":{"prompt":"build UI"},"config":{},"status":"loaded"},'
        '"error":null}'
    )

    summary = summarize_tool_result_for_llm("skill_impeccable_12345678", content)

    assert summary == "Skill instructions for impeccable were loaded."
    assert "very long internal instructions" not in summary


def test_extract_media_display_payload_returns_media_payload_for_image():
    content = '{"kind":"media.image","success":true,"model":"google/gemini-2.5-flash-image","images":[{"image":{"url":"/api/v1/upload/files/generated-images/2026/03/test.png","base64":null,"file_path":null}}],"error":null}'

    payload = extract_media_display_payload(content)

    assert payload is not None
    assert payload["kind"] == "media.image"
    assert (
        payload["images"][0]["image"]["url"]
        == "/api/v1/upload/files/generated-images/2026/03/test.png"
    )


def test_extract_media_display_payload_returns_none_for_non_media():
    content = '{"result":"plain tool output"}'

    payload = extract_media_display_payload(content)

    assert payload is None


def test_infer_tool_result_is_error_detects_failed_media_payload():
    content = '{"kind":"media.image","success":false,"images":[],"error":"provider rejected quality"}'

    assert infer_tool_result_is_error(content) is True


def test_build_tool_result_sse_event_includes_is_error_flag():
    content = '{"kind":"media.image","success":false,"images":[],"error":"provider rejected quality"}'

    event = build_tool_result_sse_event(
        tool_call_id="call_123",
        tool_name="generate_image",
        tool_display_name="Generate Image",
        display_result=content,
    )

    assert "event: tool_result" in event
    assert '"tool_call_id": "call_123"' in event
    assert '"is_error": true' in event


def test_build_media_result_sse_event_returns_media_event_for_media_payload():
    content = '{"kind":"media.image","success":false,"images":[],"error":"provider rejected quality"}'

    event = build_media_result_sse_event(content)

    assert event is not None
    assert "event: media_result" in event
    assert '"kind": "media.image"' in event


def test_build_media_result_sse_event_returns_none_for_non_media_payload():
    content = '{"result":"plain tool output"}'

    event = build_media_result_sse_event(content)

    assert event is None
