import base64
import io
import json

from PIL import Image

from app.llm.types import FunctionCall, Message, MessageRole, ToolCall
from app.services import chat_context


def _encoded_image(mode: str, size: tuple[int, int] = (2, 2)) -> str:
    source = io.BytesIO()
    image = Image.new(mode, size)
    image.save(source, format="PNG")
    return base64.b64encode(source.getvalue()).decode()


def test_normalize_vision_image_keeps_small_images_and_handles_non_alpha_modes():
    small = _encoded_image("RGB")
    normalized, image_format = chat_context._normalize_vision_image(small, "png")

    assert normalized == small
    assert image_format == "png"

    palette = _encoded_image("P", (3000, 2))
    normalized_palette, normalized_format = chat_context._normalize_vision_image(
        palette,
        "png",
    )

    assert normalized_format == "jpeg"
    with Image.open(io.BytesIO(base64.b64decode(normalized_palette))) as image:
        assert image.mode == "RGB"
        assert max(image.size) <= 2048


def test_selective_tool_result_compaction_summarizes_json_and_truncates_plain_text(
    monkeypatch,
):
    monkeypatch.setattr(
        chat_context,
        "_estimate_single_message_tokens",
        lambda *args, **kwargs: 999,
    )
    tool_call = ToolCall(
        id="call-1",
        type="function",
        function=FunctionCall(name="render", arguments="{}"),
    )
    messages = [
        Message(role=MessageRole.SYSTEM, content="system"),
        Message(role=MessageRole.USER, content="old request"),
        Message(role=MessageRole.ASSISTANT, content="", tool_calls=[tool_call]),
        Message(
            role=MessageRole.TOOL,
            tool_call_id="call-1",
            content=json.dumps({"kind": "media.image", "images": ["one"]}),
        ),
        Message(role=MessageRole.TOOL, tool_call_id="call-1", content="x" * 1300),
        Message(role=MessageRole.USER, content="newer tool request"),
        Message(role=MessageRole.ASSISTANT, content="", tool_calls=[tool_call]),
        Message(role=MessageRole.TOOL, tool_call_id="call-1", content="kept raw"),
        Message(role=MessageRole.USER, content="recent request"),
    ]

    compacted, trimmed, protected = (
        chat_context._apply_selective_tool_result_compaction(
            messages,
            model_id="gpt-4",
            provider=None,
            keep_recent_tool_results=0,
            tool_result_compact_min_tokens=1,
            recent_raw_turns=1,
            recent_tool_turns=0,
        )
    )

    assert trimmed is True
    assert protected == set()
    assert compacted[3].content == "Image generation succeeded. Generated 1 image."
    assert compacted[4].content.endswith("...")
    assert len(compacted[4].content) == 1200
