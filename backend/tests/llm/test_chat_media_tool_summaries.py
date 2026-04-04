from app.api.v1.endpoints.chat import (
    extract_media_display_payload,
    summarize_tool_result_for_llm,
)


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
