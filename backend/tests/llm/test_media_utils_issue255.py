from pathlib import Path

import pytest

from app.llm.adapters.media_utils import (
    append_prompt_directives,
    closest_aspect_ratio,
    image_content_to_data_uri,
    image_content_to_raw_base64,
    infer_format,
    infer_image_format_from_mime,
    media_content_to_data_uri,
    parse_image_data_url,
    require_remote_url,
)
from app.llm.errors import InvalidRequestError
from app.llm.types.base import ImageContent, MediaContent


def test_prompt_format_and_ratio_helpers_cover_fallbacks():
    assert append_prompt_directives("prompt", None, " ") == "prompt"
    assert append_prompt_directives("prompt", " cinematic ", "4k") == (
        "prompt\n\ncinematic\n4k"
    )
    assert closest_aspect_ratio(None, 10) == "1:1"
    assert closest_aspect_ratio(-1, 10) == "1:1"
    assert closest_aspect_ratio(1920, 1080) == "16:9"
    assert infer_format(None, "mp4") == "mp4"
    assert infer_format("https://cdn.example.test/file.WEBP", "png") == "webp"
    assert infer_format("https://cdn.example.test/file", "png") == "png"


@pytest.mark.parametrize(
    ("mime_type", "expected"),
    [
        (None, None),
        (" image/jpeg; charset=binary ", "jpg"),
        ("image/svg+xml", "svg+xml"),
        ("application/octet-stream", None),
    ],
)
def test_infer_image_format_from_mime(mime_type, expected):
    assert infer_image_format_from_mime(mime_type) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://example.test/image.png", None),
        ("data:image/png;base64", None),
        ("data:image/png,raw", None),
        ("data:image/PNG;BASE64,abc", ("abc", "png")),
    ],
)
def test_parse_image_data_url(value, expected):
    assert parse_image_data_url(value) == expected


def test_media_content_prefers_url_and_normalizes_base64():
    assert (
        media_content_to_data_uri(
            MediaContent(url="https://example.test/a.mp3", base64="ignored"),
            default_mime="audio/mpeg",
            provider="provider",
            model="model",
            field_name="audio",
        )
        == "https://example.test/a.mp3"
    )
    assert (
        media_content_to_data_uri(
            MediaContent(base64="YWJj"),
            default_mime="audio/mpeg",
            provider="provider",
            model="model",
            field_name="audio",
        )
        == "data:audio/mpeg;base64,YWJj"
    )
    assert (
        media_content_to_data_uri(
            MediaContent(base64="data:audio/wav;base64,YWJj"),
            default_mime="audio/mpeg",
            provider="provider",
            model="model",
            field_name="audio",
        )
        == "data:audio/wav;base64,YWJj"
    )


def test_media_content_reads_file_and_reports_missing_content(tmp_path: Path):
    image = tmp_path / "image.png"
    image.write_bytes(b"abc")

    assert (
        media_content_to_data_uri(
            MediaContent(file_path=str(image)),
            default_mime="application/octet-stream",
            provider="provider",
            model="model",
            field_name="image",
        )
        == "data:image/png;base64,YWJj"
    )
    unknown = tmp_path / "image"
    unknown.write_bytes(b"abc")
    assert (
        media_content_to_data_uri(
            MediaContent(file_path=str(unknown)),
            default_mime="application/octet-stream",
            provider="provider",
            model="model",
            field_name="image",
        )
        == "data:application/octet-stream;base64,YWJj"
    )

    with pytest.raises(InvalidRequestError) as exc_info:
        media_content_to_data_uri(
            MediaContent(),
            default_mime="image/png",
            provider="provider",
            model="model",
            field_name="image",
        )
    assert exc_info.value.details == {"field": "image"}


def test_image_content_converters_cover_jpeg_data_and_remote_url():
    jpeg = ImageContent(base64="YWJj", format="jpeg")
    assert (
        image_content_to_data_uri(
            jpeg, provider="provider", model="model", field_name="image"
        )
        == "data:image/jpeg;base64,YWJj"
    )
    assert (
        image_content_to_raw_base64(
            jpeg, provider="provider", model="model", field_name="image"
        )
        == "YWJj"
    )
    assert (
        image_content_to_raw_base64(
            ImageContent(url="https://example.test/image.png"),
            provider="provider",
            model="model",
            field_name="image",
        )
        == "https://example.test/image.png"
    )


def test_require_remote_url_accepts_url_and_rejects_inline_content(monkeypatch):
    assert (
        require_remote_url(
            MediaContent(url="https://example.test/image.png"),
            provider="provider",
            model="model",
            field_name="image",
        )
        == "https://example.test/image.png"
    )

    monkeypatch.setattr(
        "app.llm.adapters.media_utils.t",
        lambda key, **kwargs: f"{key}:{kwargs['provider']}",
    )
    with pytest.raises(InvalidRequestError) as exc_info:
        require_remote_url(
            MediaContent(base64="YWJj"),
            provider="provider",
            model="model",
            field_name="image",
        )
    assert exc_info.value.message == (
        "video_reference_image_requires_remote_url:provider"
    )
