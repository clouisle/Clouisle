"""Media extraction boundaries: tool failures, model gating and section assembly.

Every external boundary (ffmpeg/ffprobe, vision/STT models, quota tracker) is
faked; the module's own decisions — which error is raised, what is sent to a
model, which sections are produced — run for real.
"""

import asyncio
import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from PIL import Image

from app.services import wechat_media as media


def _png(size=(8, 8)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (10, 20, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


class _OversizedImage:
    """Stands in for a decoded image beyond the pixel budget."""

    width = 10_000
    height = 10_000

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


_REAL_IMAGE_OPEN = Image.open
_REAL_WAIT_FOR = asyncio.wait_for


@pytest.mark.asyncio
async def test_media_tool_reports_failure_and_kills_on_cancellation(monkeypatch):
    async def subprocess(*args, **kwargs):
        return SimpleNamespace(
            communicate=AsyncMock(return_value=(b"ok", b"")),
            returncode=1,
            kill=lambda: killed.append(True),
            wait=AsyncMock(),
        )

    killed: list[bool] = []
    monkeypatch.setattr(media.asyncio, "create_subprocess_exec", subprocess)
    with pytest.raises(Exception) as exc_info:
        await media.run_media_tool("ffmpeg")
    assert getattr(exc_info.value, "msg_key", None) == "wechat_media_conversion_failed"
    assert killed == []

    async def timeout(coro, timeout=None):
        coro.close()
        raise asyncio.TimeoutError()

    monkeypatch.setattr(media.asyncio, "wait_for", timeout)
    with pytest.raises(asyncio.TimeoutError):
        await media.run_media_tool("ffmpeg")
    assert killed == [True]

    async def succeeding(*args, **kwargs):
        return SimpleNamespace(
            communicate=AsyncMock(return_value=(b"converted", b"")),
            returncode=0,
            kill=lambda: killed.append("unexpected"),
            wait=AsyncMock(),
        )

    monkeypatch.setattr(media.asyncio, "create_subprocess_exec", succeeding)
    monkeypatch.setattr(media.asyncio, "wait_for", _REAL_WAIT_FOR)
    assert await media.run_media_tool("ffmpeg") == b"converted"
    assert killed == [True]


@pytest.mark.asyncio
async def test_image_text_requires_vision_and_normalizes_the_image(monkeypatch):
    with pytest.raises(Exception) as missing:
        await media.image_text(b"x", "team", None)
    assert missing.value.msg_key == "wechat_vision_required"

    monkeypatch.setattr(
        media.model_manager,
        "resolve_team_chat_model",
        AsyncMock(return_value=(SimpleNamespace(capabilities={}), None)),
    )
    with pytest.raises(Exception) as no_vision:
        await media.image_text(b"x", "team", uuid4())
    assert no_vision.value.msg_key == "wechat_model_unavailable"

    monkeypatch.setattr(
        media.model_manager,
        "resolve_team_chat_model",
        AsyncMock(return_value=(SimpleNamespace(capabilities={"vision": True}), None)),
    )
    chat = AsyncMock(return_value=SimpleNamespace(content="  extracted text  "))
    monkeypatch.setattr(media.model_manager, "team_chat", chat)

    text = await media.image_text(_png(), "team", uuid4())

    assert text == "extracted text"
    payload = chat.await_args.kwargs
    assert payload["temperature"] == 0
    parts = payload["messages"][0]["content"]
    assert parts[1]["image"]["format"] == "jpg"
    # The encoded payload is the normalized JPEG, not the original PNG bytes.
    decoded = Image.open(
        io.BytesIO(__import__("base64").b64decode(parts[1]["image"]["base64"]))
    )
    assert decoded.format == "JPEG"


@pytest.mark.asyncio
async def test_image_text_rejects_oversized_pixels_and_empty_answers(monkeypatch):
    monkeypatch.setattr(
        media.model_manager,
        "resolve_team_chat_model",
        AsyncMock(return_value=(SimpleNamespace(capabilities={"vision": True}), None)),
    )
    monkeypatch.setattr(media.Image, "open", lambda _: _OversizedImage())
    with pytest.raises(Exception) as oversized:
        await media.image_text(b"x", "team", uuid4())
    assert oversized.value.msg_key == "wechat_media_conversion_failed"

    monkeypatch.setattr(media.Image, "open", _REAL_IMAGE_OPEN)
    monkeypatch.setattr(
        media.model_manager,
        "team_chat",
        AsyncMock(return_value=SimpleNamespace(content="   ")),
    )
    with pytest.raises(Exception) as empty:
        await media.image_text(_png(), "team", uuid4())
    assert empty.value.msg_key == "wechat_empty_content"


@pytest.mark.asyncio
async def test_audio_text_checks_quota_records_usage_and_rejects_empty(monkeypatch):
    with pytest.raises(Exception) as missing:
        await media.audio_text(Path("/tmp/a.mp3"), "team", None)
    assert missing.value.msg_key == "wechat_stt_required"

    model = SimpleNamespace(id=uuid4())
    grant = object()
    monkeypatch.setattr(
        media.model_manager, "_get_team_model", AsyncMock(return_value=(model, grant))
    )
    quota = AsyncMock()
    monkeypatch.setattr(media.usage_tracker, "check_quota_with_model", quota)
    record = AsyncMock()
    monkeypatch.setattr(media.model_manager, "_check_and_record_usage", record)
    monkeypatch.setattr(
        media.model_manager,
        "speech_to_text",
        AsyncMock(return_value=SimpleNamespace(text="  hi there  ")),
    )

    assert await media.audio_text(Path("/tmp/a.mp3"), "team", uuid4()) == "hi there"
    quota.assert_awaited_once_with(grant)
    record.assert_awaited_once_with("team", str(model.id), 0)

    monkeypatch.setattr(
        media.model_manager,
        "speech_to_text",
        AsyncMock(return_value=SimpleNamespace(text=" \n ")),
    )
    with pytest.raises(Exception) as empty:
        await media.audio_text(Path("/tmp/a.mp3"), "team", uuid4())
    assert empty.value.msg_key == "wechat_empty_content"


@pytest.mark.asyncio
async def test_extract_media_routes_images_and_requires_ffmpeg(monkeypatch):
    seen = []

    async def fake_image(content, team_id, model_id):
        seen.append(content)
        return "image text"

    monkeypatch.setattr(media, "image_text", fake_image)
    assert (
        await media.extract_media(b"png", "a.png", "image/png", 2, "team", 1, None)
        == "image text"
    )
    assert seen == [b"png"]

    monkeypatch.setattr(media.shutil, "which", lambda name: None)
    with pytest.raises(Exception) as no_ffmpeg:
        await media.extract_media(b"data", "a.mp3", "audio/mpeg", 3, "team", None, 1)
    assert no_ffmpeg.value.msg_key == "wechat_ffmpeg_required"


@pytest.mark.asyncio
async def test_extract_media_validates_duration_and_builds_sections(monkeypatch):
    monkeypatch.setattr(media.shutil, "which", lambda name: f"/usr/bin/{name}")
    metadata = {"format": {"duration": "0"}, "streams": []}

    async def probe(*args):
        return json.dumps(metadata).encode()

    monkeypatch.setattr(media, "run_media_tool", probe)
    with pytest.raises(Exception) as bad_duration:
        await media.extract_media(b"data", "a.mp3", "audio/mpeg", 3, "team", None, 1)
    assert bad_duration.value.msg_key == "wechat_media_duration"

    metadata.clear()
    metadata.update(
        {"format": {"duration": "90"}, "streams": [{"codec_type": "audio"}]}
    )
    calls: list[tuple] = []

    async def tools(*args):
        calls.append(args)
        if args[0].endswith("ffprobe"):
            return json.dumps(metadata).encode()
        Path(args[-1]).write_bytes(_png())
        return b""

    monkeypatch.setattr(media, "run_media_tool", tools)
    monkeypatch.setattr(
        media, "audio_text", AsyncMock(return_value="transcribed audio")
    )
    sections = await media.extract_media(
        b"data", "a.mp3", "audio/mpeg", 3, "team", None, 1
    )
    assert sections == "## Transcript\n\ntranscribed audio"
    assert any(str(arg).endswith("audio.mp3") for arg in calls[-1])


@pytest.mark.asyncio
async def test_extract_media_samples_video_frames_at_the_documented_cadence(
    monkeypatch,
):
    monkeypatch.setattr(media.shutil, "which", lambda name: f"/usr/bin/{name}")
    metadata = {"format": {"duration": "90"}, "streams": [{"codec_type": "audio"}]}
    calls: list[tuple] = []

    async def tools(*args):
        calls.append(args)
        if args[0].endswith("ffprobe"):
            return json.dumps(metadata).encode()
        Path(args[-1]).write_bytes(_png())
        return b""

    monkeypatch.setattr(media, "run_media_tool", tools)
    monkeypatch.setattr(
        media, "audio_text", AsyncMock(return_value="transcribed audio")
    )
    images = AsyncMock(return_value="frame text")
    monkeypatch.setattr(media, "image_text", images)

    sections = await media.extract_media(b"data", "a.mp4", "video/mp4", 5, "team", 7, 1)

    assert sections.startswith("## Transcript\n\ntranscribed audio")
    # 90 seconds yields 4 samples at 0.0/22.5/45.0/67.5 seconds, never one per frame.
    assert [
        line for line in sections.splitlines() if line.startswith("## Frame at")
    ] == [
        "## Frame at 0.0s",
        "## Frame at 22.5s",
        "## Frame at 45.0s",
        "## Frame at 67.5s",
    ]
    assert images.await_count == 4


@pytest.mark.asyncio
async def test_extract_media_requires_vision_for_video_and_content(monkeypatch):
    monkeypatch.setattr(media.shutil, "which", lambda name: f"/usr/bin/{name}")
    metadata = {"format": {"duration": "60"}, "streams": [{"codec_type": "video"}]}

    async def tools(*args):
        if args[0].endswith("ffprobe"):
            return json.dumps(metadata).encode()
        Path(args[-1]).write_bytes(_png())
        return b""

    monkeypatch.setattr(media, "run_media_tool", tools)
    with pytest.raises(Exception) as no_vision:
        await media.extract_media(b"data", "a.mp4", "video/mp4", 5, "team", None, None)
    assert no_vision.value.msg_key == "wechat_vision_required"

    # Recognized media without an audio stream or a vision model has nothing to
    # extract, and must fail explicitly instead of returning an empty document.
    metadata["streams"] = [{"codec_type": "data"}]
    with pytest.raises(Exception) as empty:
        await media.extract_media(
            b"data", "a.bin", "application/octet-stream", 4, "team", 7, None
        )
    assert empty.value.msg_key == "wechat_empty_content"
