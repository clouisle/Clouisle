"""Behavioral boundaries for OpenRouter-native multimodal serialization."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.llm.adapters.chat.openai_compatible_adapter import OpenAICompatibleAdapter
from app.llm.errors import InvalidRequestError
from app.llm.types import (
    AudioContent,
    ContentPart,
    ContentType,
    FileContent,
    ImageContent,
    Message,
    MessageRole,
    VideoContent,
)


def _adapter(provider_hint="custom", base_url=None, **overrides):
    values = {
        "model_id": "anthropic/claude-sonnet-4",
        "api_key": "test-key",
        "base_url": base_url,
        "config": {},
        "default_params": {},
        "max_output_tokens": None,
    }
    values.update(overrides)
    return OpenAICompatibleAdapter(SimpleNamespace(**values), provider_hint)


def _openrouter(**overrides):
    return _adapter(base_url="https://openrouter.ai/api/v1", **overrides)


def _message(parts):
    return SimpleNamespace(
        role=MessageRole.USER, content=parts, tool_calls=None, tool_call_id=None
    )


def _part(part_type, payload):
    return ContentPart(type=part_type, **{part_type.value: payload})


def _audio(**overrides):
    values = {"base64": "YXVkaW8=", "mime_type": "audio/wav", "format": "wav"}
    values.update(overrides)
    return AudioContent(**values)


def _video(**overrides):
    values = {"base64": "dmlkZW8=", "mime_type": "video/mp4", "format": "mp4"}
    values.update(overrides)
    return VideoContent(**values)


def _file(**overrides):
    values = {
        "base64": "cGRm",
        "mime_type": "application/pdf",
        "filename": "report.pdf",
    }
    values.update(overrides)
    return FileContent(**values)


def test_openrouter_detection_requires_the_custom_provider_and_official_host():
    assert _openrouter()._is_openrouter() is True
    # The custom provider alone is not a gateway.
    assert _adapter(provider_hint="custom")._is_openrouter() is False
    # Only the documented API paths are recognized.
    assert (
        _adapter(
            provider_hint="custom", base_url="https://openrouter.ai/api/v1/chat"
        )._is_openrouter()
        is False
    )
    assert (
        _adapter(
            provider_hint="custom", base_url="https://openrouter.ai.evil.test/api/v1"
        )._is_openrouter()
        is False
    )


def test_data_uri_requires_a_resolvable_payload():
    with pytest.raises(InvalidRequestError, match="Unresolved asset reference"):
        _openrouter()._payload_data_uri(
            VideoContent(asset_ref="a1b2", mime_type="video/mp4")
        )
    with pytest.raises(InvalidRequestError, match="Media MIME type is required"):
        _openrouter()._payload_data_uri(VideoContent(base64="dmlkZW8="))
    with pytest.raises(InvalidRequestError, match="Media payload is missing"):
        _openrouter()._payload_data_uri(VideoContent(mime_type="video/mp4"))
    assert (
        _openrouter()._payload_data_uri(
            VideoContent(base64="dmlkZW8=", mime_type="video/mp4")
        )
        == "data:video/mp4;base64,dmlkZW8="
    )
    assert (
        _openrouter()._payload_data_uri(
            VideoContent(url="https://video.invalid/a.mp4", mime_type="video/mp4")
        )
        == "https://video.invalid/a.mp4"
    )


@pytest.mark.parametrize(
    "audio,expected_format",
    [
        (_audio(), "wav"),
        (_audio(mime_type="audio/mp3", format="mp3"), "mp3"),
        (_audio(mime_type="audio/mpeg", format="mpeg"), "mp3"),
        (_audio(mime_type="audio/aiff", format="aiff"), "aiff"),
        (_audio(mime_type="audio/aac", format="aac"), "aac"),
        (_audio(mime_type="audio/ogg", format="ogg"), "ogg"),
        (_audio(mime_type="audio/flac", format="flac"), "flac"),
        (_audio(mime_type="audio/mp4", format="mp4"), "m4a"),
        (_audio(mime_type="audio/x-m4a", format="x-m4a"), "m4a"),
        (_audio(mime_type=None, format="mp3"), "mp3"),
    ],
)
def test_openrouter_audio_maps_supported_mimes_to_wire_formats(audio, expected_format):
    part = _openrouter()._openrouter_audio_part(audio)
    assert part == {
        "type": "input_audio",
        "input_audio": {"data": "YXVkaW8=", "format": expected_format},
    }


@pytest.mark.parametrize(
    "audio",
    [
        _audio(mime_type="audio/opus"),
        _audio(base64=None),
        _audio(asset_ref="a1b2"),
    ],
)
def test_openrouter_audio_rejects_unsupported_payloads(audio):
    with pytest.raises(InvalidRequestError, match="OpenRouter audio"):
        _openrouter()._openrouter_audio_part(audio)


def test_openrouter_audio_rejects_missing_content():
    with pytest.raises(InvalidRequestError, match="Audio content is missing"):
        _openrouter()._openrouter_audio_part(None)


def test_openrouter_video_serializes_supported_mimes_as_video_url():
    for mime in ("video/mp4", "video/mpeg", "video/mov", "video/webm"):
        part = _openrouter()._openrouter_video_part(_video(mime_type=mime))
        assert part == {
            "type": "video_url",
            "video_url": {"url": f"data:{mime};base64,dmlkZW8="},
        }
    part = _openrouter()._openrouter_video_part(
        _video(base64=None, url="https://video.invalid/a.mp4")
    )
    assert part["video_url"]["url"] == "https://video.invalid/a.mp4"
    # The format fallback still has to be a serializable MIME type.
    with pytest.raises(InvalidRequestError, match="Unsupported OpenRouter video"):
        _openrouter()._openrouter_video_part(_video(mime_type=None, format="avi"))


def test_openrouter_video_rejects_missing_or_unsupported_payloads():
    with pytest.raises(InvalidRequestError, match="Video content is missing"):
        _openrouter()._openrouter_video_part(None)
    with pytest.raises(InvalidRequestError, match="Unsupported OpenRouter video"):
        _openrouter()._openrouter_video_part(_video(mime_type="video/avi"))
    with pytest.raises(InvalidRequestError, match="Unresolved asset reference"):
        _openrouter()._openrouter_video_part(_video(asset_ref="a1b2"))


def test_openrouter_file_prefers_extracted_text_over_a_native_payload():
    part = _openrouter()._openrouter_file_part(
        _file(extracted_text="Body text", base64=None)
    )
    assert part == {"type": "text", "text": "report.pdf:\nBody text"}
    # The filename falls back to a generic document label.
    part = _openrouter()._openrouter_file_part(
        _file(filename=None, extracted_text="Body text", base64=None)
    )
    assert part == {"type": "text", "text": "Document:\nBody text"}


def test_openrouter_file_serializes_pdf_and_rejects_other_mimes():
    part = _openrouter()._openrouter_file_part(_file())
    assert part == {
        "type": "file",
        "file": {
            "filename": "report.pdf",
            "file_data": "data:application/pdf;base64,cGRm",
        },
    }
    part = _openrouter()._openrouter_file_part(_file(filename=None))
    assert part["file"]["filename"] == "document.pdf"
    with pytest.raises(InvalidRequestError, match="File content is missing"):
        _openrouter()._openrouter_file_part(None)
    with pytest.raises(InvalidRequestError, match="Unsupported OpenRouter file"):
        _openrouter()._openrouter_file_part(
            _file(
                mime_type="application/vnd.openxmlformats-officedocument"
                ".wordprocessingml.document"
            )
        )
    with pytest.raises(InvalidRequestError, match="Unresolved asset reference"):
        _openrouter()._openrouter_file_part(_file(base64=None, asset_ref="a1b2"))


def test_generic_gateway_rejects_audio_video_and_file_parts():
    generic = _adapter(provider_hint="custom", base_url="https://gateway.invalid/v1")
    for part_type, payload in (
        (ContentType.AUDIO, _audio()),
        (ContentType.VIDEO, _video()),
        (ContentType.FILE, _file()),
    ):
        with pytest.raises(
            InvalidRequestError,
            match=f"{part_type.value.capitalize()} input is unsupported",
        ):
            generic._convert_messages([_message([_part(part_type, payload)])])


def test_openrouter_message_conversion_emits_native_multimodal_parts():
    converted = _openrouter()._convert_messages(
        [
            _message(
                [
                    ContentPart(type=ContentType.TEXT, text="describe these"),
                    _part(ContentType.IMAGE, ImageContent(base64="aW1n", format="png")),
                    _part(ContentType.AUDIO, _audio()),
                    _part(ContentType.VIDEO, _video()),
                    _part(ContentType.FILE, _file()),
                    {"type": "text", "text": "raw dict"},
                ]
            )
        ]
    )

    assert converted[0]["content"] == [
        {"type": "text", "text": "describe these"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,aW1n"}},
        {
            "type": "input_audio",
            "input_audio": {"data": "YXVkaW8=", "format": "wav"},
        },
        {"type": "video_url", "video_url": {"url": "data:video/mp4;base64,dmlkZW8="}},
        {
            "type": "file",
            "file": {
                "filename": "report.pdf",
                "file_data": "data:application/pdf;base64,cGRm",
            },
        },
        {"type": "text", "text": "raw dict"},
    ]


def test_message_conversion_rejects_missing_and_invalid_parts():
    generic = _adapter(provider_hint="custom", base_url="https://gateway.invalid/v1")
    with pytest.raises(InvalidRequestError, match="Image content is missing"):
        generic._convert_messages([_message([_part(ContentType.IMAGE, None)])])
    with pytest.raises(InvalidRequestError, match="Unsupported image MIME type"):
        generic._convert_messages(
            [
                _message(
                    [
                        _part(
                            ContentType.IMAGE,
                            ImageContent(base64="aW1n", mime_type="image/bmp"),
                        )
                    ]
                )
            ]
        )
    with pytest.raises(InvalidRequestError, match="Image payload is missing"):
        generic._convert_messages(
            [
                _message(
                    [
                        _part(
                            ContentType.IMAGE,
                            ImageContent(mime_type="image/png"),
                        )
                    ]
                )
            ]
        )
    with pytest.raises(InvalidRequestError, match="Invalid multimodal content part"):
        generic._convert_messages([_message([object()])])


def test_empty_multimodal_content_serializes_as_an_empty_string():
    converted = _adapter()._convert_messages([_message([])])
    assert converted == [{"role": "user", "content": ""}]


def test_tool_result_messages_may_only_carry_text():
    tool_message = SimpleNamespace(
        role=MessageRole.TOOL,
        content=[_part(ContentType.IMAGE, ImageContent(base64="aW1n"))],
        tool_calls=None,
        tool_call_id="call-1",
    )
    with pytest.raises(InvalidRequestError, match="may contain text only"):
        _adapter()._convert_messages([tool_message])

    text_tool_message = SimpleNamespace(
        role=MessageRole.TOOL,
        content=[_part(ContentType.TEXT, "sunny")],
        tool_calls=None,
        tool_call_id="call-1",
    )
    converted = _adapter()._convert_messages([text_tool_message])
    assert converted[0]["content"] == [{"type": "text", "text": "sunny"}]


def test_deepseek_reasoning_content_is_emitted_for_assistant_messages():
    deepseek = _adapter(provider_hint=None, model_id="deepseek-chat")
    converted = deepseek._convert_messages(
        [
            Message(role=MessageRole.ASSISTANT, content="answer"),
            Message(
                role=MessageRole.ASSISTANT,
                content=None,
                reasoning_content="thinking",
            ),
        ]
    )
    assert "reasoning_content" not in converted[0]
    assert converted[1]["reasoning_content"] == "thinking"

    other = _adapter(model_id="gpt-test")
    converted = other._convert_messages(
        [Message(role=MessageRole.ASSISTANT, content="answer", reasoning_content="x")]
    )
    assert "reasoning_content" not in converted[0]


@pytest.mark.anyio
async def test_openrouter_serialization_survives_a_full_chat_round_trip(monkeypatch):
    """The serialized payloads are accepted end to end by the SDK request body."""
    response = SimpleNamespace(
        id="response-1",
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="done", tool_calls=None, model_extra=None
                ),
                finish_reason="stop",
            )
        ],
        usage=None,
    )
    create = AsyncMock(return_value=response)
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
        close=AsyncMock(),
    )
    monkeypatch.setattr("openai.AsyncOpenAI", lambda **kwargs: client)

    result = await _openrouter().chat(
        [
            _message(
                [
                    _part(ContentType.AUDIO, _audio()),
                    _part(ContentType.VIDEO, _video()),
                    _part(ContentType.FILE, _file()),
                ]
            )
        ]
    )

    sent = create.await_args.kwargs["messages"][0]["content"]
    assert sent[0]["type"] == "input_audio"
    assert sent[1]["type"] == "video_url"
    assert sent[2]["type"] == "file"
    assert result.finish_reason.value == "stop"
    client.close.assert_awaited_once()
