"""Behavioral boundaries for multimodal asset views and model input capabilities."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.llm.capabilities import (
    InputCapabilities,
    InputModalityLimits,
    get_effective_input_capabilities,
    is_openrouter_url,
    normalize_mime_type,
)
from app.llm.errors import InvalidRequestError
from app.llm.types import ContentType
from app.models.asset import AssetScopeType
from app.models.model import ModelProvider, ModelType
from app.services.asset_view import (
    MAX_SELECTION_SECONDS,
    MAX_TEXT_CHARS,
    MAX_VIEW_BYTES,
    resolve_view_content,
)

PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _asset(
    *,
    content_type="image/png",
    original_filename="photo.png",
    size=None,
    checksum=None,
):
    return SimpleNamespace(
        id=uuid4(),
        display_filename=original_filename,
        original_filename=original_filename,
        content_type=content_type,
        size=size if size is not None else 12,
        checksum=checksum if checksum is not None else "a" * 64,
        source=SimpleNamespace(value="upload"),
        storage_key=f"private/{uuid4()}",
    )


def _agent(team_id=None, attachment_config=None):
    return SimpleNamespace(
        id=uuid4(),
        team_id=team_id,
        attachment_config=attachment_config or {},
    )


def _model(
    *,
    provider=ModelProvider.GOOGLE,
    model_type=ModelType.CHAT,
    base_url=None,
    capabilities=None,
):
    return SimpleNamespace(
        provider=provider,
        model_type=model_type,
        base_url=base_url,
        capabilities=capabilities if capabilities is not None else {},
    )


def _openrouter_model(**capabilities):
    return _model(
        provider=ModelProvider.CUSTOM,
        base_url="https://openrouter.ai/api/v1",
        capabilities=capabilities,
    )


def _capabilities(modalities, *, mime_types=None, max_bytes=None):
    limits = {}
    if max_bytes is not None:
        for modality in modalities:
            limits[modality] = InputModalityLimits(max_bytes)
    return InputCapabilities(frozenset(modalities), dict(mime_types or {}), limits)


def _patch_resolved_asset(monkeypatch, content: bytes, *, size=None, **asset_fields):
    """Authorize one asset whose stored bytes verify against its metadata."""
    checksum = hashlib.sha256(content).hexdigest()
    asset = _asset(
        checksum=checksum,
        size=size if size is not None else len(content),
        **asset_fields,
    )
    storage = MagicMock()
    storage.read_limited = AsyncMock(return_value=content)
    monkeypatch.setattr(
        "app.services.asset_view.resolve_authorized_asset_ref",
        AsyncMock(return_value=asset),
    )
    monkeypatch.setattr(
        "app.services.upload_storage.get_upload_storage_backend",
        AsyncMock(return_value=storage),
    )
    # The asset stays visible on the active conversation branch.
    active = SimpleNamespace(exists=AsyncMock(return_value=True))
    monkeypatch.setattr(
        "app.models.asset.MessageAsset.filter",
        lambda **_kwargs: SimpleNamespace(
            exists=AsyncMock(return_value=True),
            filter=MagicMock(return_value=active),
        ),
    )
    return asset


def _call(
    *,
    input_capabilities=None,
    extracted_text=False,
    selection=None,
    materialize=True,
    model_config=None,
    agent=None,
    ref="a1b2",
):
    return resolve_view_content(
        ref,
        scope_type=AssetScopeType.CONVERSATION,
        scope_id=uuid4(),
        user=SimpleNamespace(id=uuid4()),
        model_config=model_config or _model(),
        agent=agent or _agent(),
        extracted_text=extracted_text,
        input_capabilities=input_capabilities,
        selection=selection,
        materialize=materialize,
    )


def _pdf(pages: int = 1) -> bytes:
    from io import BytesIO

    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _fake_ffmpeg(monkeypatch, *, returncode=0, payload=b"selected-bytes"):
    """Stub ffmpeg discovery and execution; the stub writes the real output file."""
    proc = MagicMock()
    proc.returncode = None
    proc.kill = MagicMock()

    async def wait():
        proc.returncode = returncode
        return returncode

    proc.wait = wait

    async def create_subprocess_exec(*args, **kwargs):
        output_path = args[-1]
        if returncode == 0:
            Path(output_path).write_bytes(payload)
        return proc

    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr("asyncio.create_subprocess_exec", create_subprocess_exec)
    return proc


def _fake_ffmpeg_timeout(monkeypatch, error, *, returncode=None):
    """Stub ffmpeg so that awaiting the process raises ``error``."""
    proc = MagicMock()
    proc.returncode = returncode
    proc.wait = AsyncMock(return_value=returncode)
    proc.kill = MagicMock()

    async def create_subprocess_exec(*args, **kwargs):
        return proc

    async def wait_for(awaitable, timeout):
        awaitable.close()
        raise error

    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr("asyncio.create_subprocess_exec", create_subprocess_exec)
    monkeypatch.setattr("asyncio.wait_for", wait_for)
    return proc


# --------------------------------------------------------------------------
# Capability resolution
# --------------------------------------------------------------------------


def test_is_openrouter_url_matches_only_the_official_host_and_paths():
    assert is_openrouter_url("https://openrouter.ai/api/v1") is True
    assert is_openrouter_url("https://openrouter.ai/v1") is True
    assert is_openrouter_url("https://openrouter.ai/v1/") is True
    assert is_openrouter_url(None) is False
    assert is_openrouter_url("") is False
    assert is_openrouter_url("https://openrouter.ai") is False
    assert is_openrouter_url("https://openrouter.ai/other") is False
    assert is_openrouter_url("http://openrouter.ai/api/v1") is False
    assert is_openrouter_url("https://openrouter.ai.evil.test/api/v1") is False


def test_normalize_mime_type_only_rewrites_aliases_for_openrouter_wire_formats():
    openrouter = _openrouter_model()
    other = _model(provider=ModelProvider.GOOGLE)
    assert (
        normalize_mime_type("audio/x-m4a", ContentType.AUDIO, openrouter) == "audio/mp4"
    )
    assert (
        normalize_mime_type("AUDIO/M4A ; charset=utf-8", ContentType.AUDIO, openrouter)
        == "audio/mp4"
    )
    assert (
        normalize_mime_type("video/quicktime", ContentType.VIDEO, openrouter)
        == "video/mov"
    )
    # An alias is only rewritten for the modality whose wire format needs it.
    assert normalize_mime_type("audio/x-m4a", ContentType.FILE, openrouter) == (
        "audio/x-m4a"
    )
    assert normalize_mime_type("audio/x-m4a", ContentType.AUDIO, other) == "audio/x-m4a"


@pytest.mark.parametrize(
    "model_type",
    [
        ModelType.EMBEDDING,
        ModelType.RERANK,
        ModelType.TTS,
        ModelType.STT,
        ModelType.AUDIO_GENERATION,
        ModelType.TEXT_TO_IMAGE,
        ModelType.TEXT_TO_VIDEO,
        ModelType.DECISION,
    ],
)
def test_non_chat_models_have_no_input_modalities(model_type):
    capabilities = get_effective_input_capabilities(_model(model_type=model_type))
    assert capabilities.modalities == frozenset()
    assert capabilities.mime_types == {}
    assert capabilities.limits == {}


def test_chat_model_without_declaration_is_text_only():
    assert get_effective_input_capabilities(_model(capabilities={})).modalities == (
        frozenset({ContentType.TEXT})
    )
    # Legacy ``vision`` flags never resurrect modalities.
    assert get_effective_input_capabilities(
        _model(capabilities={"vision": True})
    ).modalities == frozenset({ContentType.TEXT})
    # A non-list declaration is undeclared, never a modality set.
    assert get_effective_input_capabilities(
        _model(capabilities={"input_modalities": "image"})
    ).modalities == frozenset({ContentType.TEXT})


def test_declared_google_modalities_intersect_with_adapter_support():
    capabilities = get_effective_input_capabilities(
        _model(
            capabilities={
                "input_modalities": ["image", "audio", "video"],
                "input_limits": {
                    "audio": {"max_bytes": 2048},
                    "video": {"mime_types": ["video/mp4"]},
                },
            }
        )
    )
    assert capabilities.modalities == frozenset(
        {ContentType.TEXT, ContentType.IMAGE, ContentType.AUDIO, ContentType.VIDEO}
    )
    # Google documents are declared through the adapter map only, so a chat model
    # that never declares them stays file-less.
    assert ContentType.FILE not in capabilities.modalities
    assert capabilities.mime_types[ContentType.VIDEO] == frozenset({"video/mp4"})
    assert capabilities.limits[ContentType.AUDIO].max_bytes == 2048
    assert capabilities.limits[ContentType.VIDEO].max_bytes is None
    assert capabilities.limits[ContentType.IMAGE].max_bytes is None


def test_declared_mime_filter_that_excludes_every_adapter_mime_drops_the_modality():
    capabilities = get_effective_input_capabilities(
        _model(
            capabilities={
                "input_modalities": ["image", "audio"],
                "input_limits": {"image": {"mime_types": ["image/bmp"]}},
            }
        )
    )
    assert ContentType.IMAGE not in capabilities.modalities
    assert ContentType.IMAGE not in capabilities.mime_types
    assert ContentType.AUDIO in capabilities.modalities


def test_openrouter_gateway_adds_audio_video_and_file_serializers():
    capabilities = get_effective_input_capabilities(
        _openrouter_model(input_modalities=["audio", "video", "file"])
    )
    assert capabilities.mime_types[ContentType.AUDIO] == frozenset(
        {
            "audio/wav",
            "audio/mp3",
            "audio/mpeg",
            "audio/aiff",
            "audio/aac",
            "audio/ogg",
            "audio/flac",
            "audio/mp4",
            "audio/x-m4a",
        }
    )
    assert capabilities.mime_types[ContentType.VIDEO] == frozenset(
        {"video/mp4", "video/mpeg", "video/mov", "video/webm"}
    )
    assert capabilities.mime_types[ContentType.FILE] == frozenset({PDF_MIME})


def test_openrouter_declared_limits_are_normalized_before_intersection():
    capabilities = get_effective_input_capabilities(
        _openrouter_model(
            input_modalities=["audio"],
            input_limits={"audio": {"mime_types": ["audio/x-m4a"], "max_bytes": 4096}},
        )
    )
    # The declared alias is rewritten to the wire MIME before the intersection.
    assert capabilities.mime_types[ContentType.AUDIO] == frozenset({"audio/mp4"})
    assert capabilities.limits[ContentType.AUDIO].max_bytes == 4096


def test_unknown_provider_declares_no_adapter_inputs():
    capabilities = get_effective_input_capabilities(
        _model(
            provider="not-a-real-provider", capabilities={"input_modalities": ["image"]}
        )
    )
    assert capabilities.modalities == frozenset({ContentType.TEXT})


@pytest.mark.parametrize("bad_bytes", ["512", 0, -1, True, 1.5])
def test_non_positive_or_non_integer_byte_limits_are_rejected(bad_bytes):
    with pytest.raises(ValueError, match="input_limits.image.max_bytes"):
        get_effective_input_capabilities(
            _model(
                capabilities={
                    "input_modalities": ["image"],
                    "input_limits": {"image": {"max_bytes": bad_bytes}},
                }
            )
        )


# --------------------------------------------------------------------------
# Native materialization
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_image_asset_materializes_a_native_image_part(monkeypatch):
    asset = _patch_resolved_asset(monkeypatch, b"png-bytes")
    capabilities = _capabilities(
        [ContentType.IMAGE], mime_types={ContentType.IMAGE: frozenset({"image/png"})}
    )
    resolved, part, marker = await _call(input_capabilities=capabilities)

    assert resolved is asset
    assert part.type is ContentType.IMAGE
    assert part.image.base64 == base64.b64encode(b"png-bytes").decode("ascii")
    assert part.image.mime_type == "image/png"
    assert part.image.format == "png"
    payload = json.loads(marker)
    assert payload["modality"] == "image"
    assert payload["representation"] == {"kind": "native", "selection": None}
    assert payload["extracted_text"] is False
    assert payload["scope_type"] == AssetScopeType.CONVERSATION.value
    assert payload["size"] == asset.size
    assert payload["checksum"] == asset.checksum


@pytest.mark.asyncio
async def test_audio_asset_serializes_audio_content(monkeypatch):
    _patch_resolved_asset(monkeypatch, b"wav-bytes", content_type="audio/wav")
    capabilities = _capabilities(
        [ContentType.AUDIO], mime_types={ContentType.AUDIO: frozenset({"audio/wav"})}
    )
    _, part, marker = await _call(input_capabilities=capabilities)

    assert part.type is ContentType.AUDIO
    assert part.audio.base64 == base64.b64encode(b"wav-bytes").decode("ascii")
    assert part.audio.format == "wav"
    assert json.loads(marker)["modality"] == "audio"


@pytest.mark.asyncio
async def test_video_asset_serializes_video_content(monkeypatch):
    _patch_resolved_asset(monkeypatch, b"mp4-bytes", content_type="video/mp4")
    capabilities = _capabilities(
        [ContentType.VIDEO], mime_types={ContentType.VIDEO: frozenset({"video/mp4"})}
    )
    _, part, marker = await _call(input_capabilities=capabilities)

    assert part.type is ContentType.VIDEO
    assert part.video.base64 == base64.b64encode(b"mp4-bytes").decode("ascii")
    assert part.video.format == "mp4"
    assert json.loads(marker)["wire_mime_type"] == "video/mp4"


@pytest.mark.asyncio
async def test_content_type_parameters_and_casing_are_ignored(monkeypatch):
    _patch_resolved_asset(
        monkeypatch, b"png-bytes", content_type="IMAGE/PNG; charset=binary"
    )
    capabilities = _capabilities([ContentType.IMAGE])
    _, part, marker = await _call(input_capabilities=capabilities)

    assert part.image.mime_type == "image/png"
    assert json.loads(marker)["mime_type"] == "image/png"


@pytest.mark.asyncio
async def test_openrouter_alias_normalizes_the_wire_mime_for_audio(monkeypatch):
    _patch_resolved_asset(monkeypatch, b"m4a-bytes", content_type="audio/x-m4a")
    _, part, marker = await _call(
        model_config=_openrouter_model(input_modalities=["audio"])
    )

    assert part.type is ContentType.AUDIO
    assert part.audio.mime_type == "audio/mp4"
    assert part.audio.format == "mp4"
    payload = json.loads(marker)
    assert payload["mime_type"] == "audio/x-m4a"
    assert payload["wire_mime_type"] == "audio/mp4"


# --------------------------------------------------------------------------
# Extracted-text fallbacks
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pdf_asset_falls_back_to_extracted_text_without_native_files(
    monkeypatch,
):
    _patch_resolved_asset(
        monkeypatch, b"pdf-bytes", content_type=PDF_MIME, original_filename="report.pdf"
    )
    parsed = SimpleNamespace(content="Extracted report body", truncated=False)
    monkeypatch.setattr(
        "app.services.file_parser.file_parser_service.parse_file",
        AsyncMock(return_value=parsed),
    )
    capabilities = _capabilities([ContentType.TEXT])
    _, part, marker = await _call(input_capabilities=capabilities)

    assert part.type is ContentType.TEXT
    assert part.text.startswith(
        f"[Extracted text from report.pdf ({PDF_MIME}); truncated=False]"
    )
    assert part.text.endswith("Extracted report body")
    payload = json.loads(marker)
    assert payload["modality"] == "text"
    assert payload["extracted_text"] is True
    assert payload["representation"] == {"kind": "extracted_text", "truncated": False}


@pytest.mark.asyncio
async def test_truncated_extracted_text_is_flagged_in_part_and_marker(monkeypatch):
    _patch_resolved_asset(
        monkeypatch, b"pdf-bytes", content_type=PDF_MIME, original_filename="report.pdf"
    )
    long_text = "x" * (MAX_TEXT_CHARS + 10)
    parsed = SimpleNamespace(content=long_text, truncated=True)
    monkeypatch.setattr(
        "app.services.file_parser.file_parser_service.parse_file",
        AsyncMock(return_value=parsed),
    )
    capabilities = _capabilities([ContentType.TEXT])
    _, part, marker = await _call(input_capabilities=capabilities)

    assert "truncated=True" in part.text
    assert part.text.endswith("x" * MAX_TEXT_CHARS)
    assert json.loads(marker)["representation"]["truncated"] is True


@pytest.mark.asyncio
async def test_agent_attachment_config_drives_document_parsing(monkeypatch):
    _patch_resolved_asset(
        monkeypatch, b"pdf-bytes", content_type=PDF_MIME, original_filename="report.pdf"
    )
    parsed = SimpleNamespace(content="body", truncated=False)
    parse_file = AsyncMock(return_value=parsed)
    monkeypatch.setattr(
        "app.services.file_parser.file_parser_service.parse_file", parse_file
    )
    capabilities = _capabilities([ContentType.TEXT])
    agent = _agent(
        attachment_config={"max_content_length": 77, "truncate_strategy": "start"}
    )
    await _call(input_capabilities=capabilities, agent=agent)

    config = parse_file.await_args.args[2]
    assert config.max_content_length == 77
    assert config.truncate_strategy == "start"


@pytest.mark.asyncio
async def test_office_document_without_native_serializer_is_extracted_as_text(
    monkeypatch,
):
    _patch_resolved_asset(
        monkeypatch,
        b"docx-bytes",
        content_type=DOCX_MIME,
        original_filename="notes.docx",
    )
    parsed = SimpleNamespace(content="Notes body", truncated=False)
    monkeypatch.setattr(
        "app.services.file_parser.file_parser_service.parse_file",
        AsyncMock(return_value=parsed),
    )
    capabilities = _capabilities([ContentType.TEXT])
    _, part, marker = await _call(input_capabilities=capabilities)

    assert part.type is ContentType.TEXT
    assert json.loads(marker)["extracted_text"] is True


@pytest.mark.asyncio
async def test_unsupported_mime_type_is_rejected_when_not_parseable(monkeypatch):
    _patch_resolved_asset(monkeypatch, b"zip-bytes", content_type="application/zip")
    capabilities = _capabilities([ContentType.TEXT, ContentType.IMAGE])
    with pytest.raises(InvalidRequestError, match="Unsupported asset MIME type"):
        await _call(input_capabilities=capabilities)


@pytest.mark.asyncio
async def test_extracted_text_requires_a_parseable_asset(monkeypatch):
    _patch_resolved_asset(monkeypatch, b"png-bytes", content_type="image/png")
    capabilities = _capabilities([ContentType.TEXT, ContentType.IMAGE])
    with pytest.raises(InvalidRequestError, match="Asset cannot be extracted as text"):
        await _call(input_capabilities=capabilities, extracted_text=True)


# --------------------------------------------------------------------------
# Capability, MIME and size gates
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_model_without_the_modality_rejects_the_asset(monkeypatch):
    _patch_resolved_asset(monkeypatch, b"png-bytes", content_type="image/png")
    capabilities = _capabilities([ContentType.TEXT])
    with pytest.raises(InvalidRequestError, match="does not support image input"):
        await _call(input_capabilities=capabilities)


@pytest.mark.asyncio
async def test_declared_byte_limit_caps_the_asset_size(monkeypatch):
    _patch_resolved_asset(monkeypatch, b"png-bytes", size=100)
    capabilities = _capabilities([ContentType.IMAGE], max_bytes=50)
    with pytest.raises(InvalidRequestError, match="exceeds model input byte limit"):
        await _call(input_capabilities=capabilities)


@pytest.mark.asyncio
async def test_platform_byte_cap_applies_without_a_declared_limit(monkeypatch):
    _patch_resolved_asset(monkeypatch, b"png-bytes", size=MAX_VIEW_BYTES + 1)
    capabilities = _capabilities([ContentType.IMAGE])
    with pytest.raises(InvalidRequestError, match="exceeds model input byte limit"):
        await _call(input_capabilities=capabilities)


@pytest.mark.asyncio
async def test_adapter_mime_rejection_uses_the_declared_mime_set(monkeypatch):
    _patch_resolved_asset(monkeypatch, b"gif-bytes", content_type="image/gif")
    capabilities = _capabilities(
        [ContentType.IMAGE], mime_types={ContentType.IMAGE: frozenset({"image/png"})}
    )
    with pytest.raises(
        InvalidRequestError, match="does not support MIME type image/gif"
    ):
        await _call(input_capabilities=capabilities)


# --------------------------------------------------------------------------
# Selection validation
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_selection_rejects_non_objects_and_unsupported_modalities(monkeypatch):
    _patch_resolved_asset(monkeypatch, b"png-bytes", content_type="image/png")
    capabilities = _capabilities([ContentType.IMAGE])
    with pytest.raises(InvalidRequestError, match="Selection must be an object"):
        await _call(input_capabilities=capabilities, selection=["nope"])
    with pytest.raises(
        InvalidRequestError, match="Selection is supported only for audio, video"
    ):
        await _call(
            input_capabilities=capabilities,
            selection={"start_seconds": 0, "end_seconds": 1},
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "selection",
    [
        {"page_start": 0, "page_end": 1},
        {"page_start": "1", "page_end": 2},
        {"page_start": True, "page_end": 2},
        {"page_start": 1, "page_end": 0},
        {"page_start": 1},
        {"page_start": 1, "page_end": 51},
    ],
)
async def test_document_selection_validates_page_ranges(monkeypatch, selection):
    _patch_resolved_asset(
        monkeypatch, _pdf(1), content_type=PDF_MIME, original_filename="report.pdf"
    )
    capabilities = _capabilities(
        [ContentType.FILE], mime_types={ContentType.FILE: frozenset({PDF_MIME})}
    )
    with pytest.raises(InvalidRequestError, match="selection"):
        await _call(input_capabilities=capabilities, selection=selection)


@pytest.mark.asyncio
async def test_document_selection_rejects_pages_beyond_the_document(monkeypatch):
    _patch_resolved_asset(
        monkeypatch, _pdf(1), content_type=PDF_MIME, original_filename="report.pdf"
    )
    capabilities = _capabilities(
        [ContentType.FILE], mime_types={ContentType.FILE: frozenset({PDF_MIME})}
    )
    with pytest.raises(InvalidRequestError, match="exceeds page count"):
        await _call(
            input_capabilities=capabilities, selection={"page_start": 1, "page_end": 2}
        )


@pytest.mark.asyncio
async def test_document_selection_extracts_only_the_requested_pages(monkeypatch):
    _patch_resolved_asset(
        monkeypatch, _pdf(3), content_type=PDF_MIME, original_filename="report.pdf"
    )
    capabilities = _capabilities(
        [ContentType.FILE], mime_types={ContentType.FILE: frozenset({PDF_MIME})}
    )
    _, part, marker = await _call(
        input_capabilities=capabilities, selection={"page_start": 2, "page_end": 3}
    )

    from io import BytesIO

    from pypdf import PdfReader

    extracted = PdfReader(BytesIO(base64.b64decode(part.file.base64)))
    assert len(extracted.pages) == 2
    payload = json.loads(marker)
    assert payload["selection"] == {"page_start": 2, "page_end": 3}
    assert payload["representation"]["selection"] == {"page_start": 2, "page_end": 3}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "selection",
    [
        {"start_seconds": -1, "end_seconds": 1},
        {"start_seconds": True, "end_seconds": 2},
        {"start_seconds": "0", "end_seconds": 2},
        {"start_seconds": float("nan"), "end_seconds": 2},
        {"start_seconds": 0, "end_seconds": 0},
        {"start_seconds": 0, "end_seconds": "5"},
        {"start_seconds": 0, "end_seconds": True},
        {"start_seconds": 0, "end_seconds": float("inf")},
        {"start_seconds": 0, "end_seconds": MAX_SELECTION_SECONDS + 1},
        {"start_seconds": 0},
    ],
)
async def test_media_selection_validates_the_time_range(monkeypatch, selection):
    _patch_resolved_asset(monkeypatch, b"mp4-bytes", content_type="video/mp4")
    capabilities = _capabilities([ContentType.VIDEO])
    with pytest.raises(InvalidRequestError, match="Selection"):
        await _call(input_capabilities=capabilities, selection=selection)


@pytest.mark.asyncio
async def test_time_range_selection_rewrites_the_wire_mime(monkeypatch):
    _patch_resolved_asset(monkeypatch, b"mp4-bytes", content_type="video/mp4")
    _fake_ffmpeg(monkeypatch, payload=b"trimmed")
    capabilities = _capabilities([ContentType.VIDEO])
    _, part, marker = await _call(
        input_capabilities=capabilities,
        selection={"start_seconds": 0, "end_seconds": 5},
    )

    assert part.type is ContentType.VIDEO
    assert part.video.base64 == base64.b64encode(b"trimmed").decode("ascii")
    assert part.video.mime_type == "video/mp4"
    payload = json.loads(marker)
    assert payload["wire_mime_type"] == "video/mp4"
    assert payload["selection"] == {"start_seconds": 0, "end_seconds": 5}


@pytest.mark.asyncio
async def test_audio_time_range_selection_rewrites_the_wire_mime(monkeypatch):
    _patch_resolved_asset(monkeypatch, b"wav-bytes", content_type="audio/wav")
    _fake_ffmpeg(monkeypatch, payload=b"trimmed-audio")
    capabilities = _capabilities([ContentType.AUDIO])
    _, part, marker = await _call(
        input_capabilities=capabilities,
        selection={"start_seconds": 1.5, "end_seconds": 2.5},
    )

    assert part.type is ContentType.AUDIO
    assert part.audio.mime_type == "audio/mp4"
    assert part.audio.format == "mp4"
    assert json.loads(marker)["selection"] == {"start_seconds": 1.5, "end_seconds": 2.5}


@pytest.mark.asyncio
async def test_time_range_selection_requires_ffmpeg(monkeypatch):
    _patch_resolved_asset(monkeypatch, b"mp4-bytes", content_type="video/mp4")
    monkeypatch.setattr("shutil.which", lambda name: None)
    capabilities = _capabilities([ContentType.VIDEO])
    with pytest.raises(InvalidRequestError, match="requires ffmpeg"):
        await _call(
            input_capabilities=capabilities,
            selection={"start_seconds": 0, "end_seconds": 5},
        )


@pytest.mark.asyncio
async def test_time_range_selection_reports_failed_derivation(monkeypatch):
    _patch_resolved_asset(monkeypatch, b"mp4-bytes", content_type="video/mp4")
    _fake_ffmpeg(monkeypatch, returncode=1)
    capabilities = _capabilities([ContentType.VIDEO])
    with pytest.raises(InvalidRequestError, match="Unable to derive requested media"):
        await _call(
            input_capabilities=capabilities,
            selection={"start_seconds": 0, "end_seconds": 5},
        )


@pytest.mark.asyncio
async def test_time_range_selection_reports_timeout(monkeypatch):
    _patch_resolved_asset(monkeypatch, b"mp4-bytes", content_type="video/mp4")
    proc = _fake_ffmpeg_timeout(monkeypatch, TimeoutError)
    capabilities = _capabilities([ContentType.VIDEO])
    with pytest.raises(InvalidRequestError, match="Media range processing timed out"):
        await _call(
            input_capabilities=capabilities,
            selection={"start_seconds": 0, "end_seconds": 5},
        )
    proc.kill.assert_called_once()


@pytest.mark.asyncio
async def test_time_range_selection_timeout_skips_kill_for_exited_process(monkeypatch):
    _patch_resolved_asset(monkeypatch, b"mp4-bytes", content_type="video/mp4")
    proc = _fake_ffmpeg_timeout(monkeypatch, TimeoutError, returncode=-9)
    capabilities = _capabilities([ContentType.VIDEO])
    with pytest.raises(InvalidRequestError, match="Media range processing timed out"):
        await _call(
            input_capabilities=capabilities,
            selection={"start_seconds": 0, "end_seconds": 5},
        )
    proc.kill.assert_not_called()


@pytest.mark.asyncio
async def test_time_range_selection_propagates_cancellation(monkeypatch):
    _patch_resolved_asset(monkeypatch, b"mp4-bytes", content_type="video/mp4")
    proc = _fake_ffmpeg_timeout(monkeypatch, asyncio.CancelledError)
    capabilities = _capabilities([ContentType.VIDEO])
    with pytest.raises(asyncio.CancelledError):
        await _call(
            input_capabilities=capabilities,
            selection={"start_seconds": 0, "end_seconds": 5},
        )
    proc.kill.assert_called_once()


@pytest.mark.asyncio
async def test_time_range_selection_rejects_oversized_output(monkeypatch):
    _patch_resolved_asset(monkeypatch, b"mp4-bytes", content_type="video/mp4")
    _fake_ffmpeg(monkeypatch, payload=b"x" * MAX_VIEW_BYTES)
    capabilities = _capabilities([ContentType.VIDEO])
    with pytest.raises(InvalidRequestError, match="Selected media exceeds"):
        await _call(
            input_capabilities=capabilities,
            selection={"start_seconds": 0, "end_seconds": 5},
        )


# --------------------------------------------------------------------------
# Non-materialized inspection and scope gating
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_inspection_returns_only_the_marker_representation(monkeypatch):
    asset = _patch_resolved_asset(monkeypatch, b"", content_type="video/mp4")
    capabilities = _capabilities([ContentType.VIDEO])
    _, part, marker = await _call(
        input_capabilities=capabilities,
        selection={"start_seconds": 0, "end_seconds": 1},
        materialize=False,
    )

    assert part is None
    payload = json.loads(marker)
    assert payload["representation"] == {
        "kind": "native",
        "selection": {"start_seconds": 0, "end_seconds": 1},
    }
    assert payload["size"] == asset.size
    assert payload["checksum"] == asset.checksum


@pytest.mark.asyncio
async def test_inspection_reports_extracted_text_representation(monkeypatch):
    _patch_resolved_asset(
        monkeypatch, b"", content_type=PDF_MIME, original_filename="report.pdf"
    )
    capabilities = _capabilities([ContentType.TEXT])
    _, part, marker = await _call(
        input_capabilities=capabilities, extracted_text=True, materialize=False
    )

    assert part is None
    payload = json.loads(marker)
    assert payload["modality"] == "text"
    assert payload["extracted_text"] is True
    assert payload["representation"] == {"kind": "extracted_text", "selection": None}


@pytest.mark.asyncio
async def test_conversation_scope_rejects_assets_hidden_by_the_active_branch(
    monkeypatch,
):
    _patch_resolved_asset(monkeypatch, b"png-bytes", content_type="image/png")
    monkeypatch.setattr(
        "app.models.asset.MessageAsset.filter",
        lambda **_kwargs: SimpleNamespace(
            exists=AsyncMock(return_value=True),
            filter=MagicMock(
                return_value=SimpleNamespace(exists=AsyncMock(return_value=False))
            ),
        ),
    )
    capabilities = _capabilities([ContentType.IMAGE])
    with pytest.raises(InvalidRequestError, match="current conversation branch"):
        await _call(input_capabilities=capabilities)


@pytest.mark.asyncio
async def test_conversation_scope_allows_assets_without_message_links(monkeypatch):
    _patch_resolved_asset(monkeypatch, b"png-bytes", content_type="image/png")
    monkeypatch.setattr(
        "app.models.asset.MessageAsset.filter",
        lambda **_kwargs: SimpleNamespace(exists=AsyncMock(return_value=False)),
    )
    capabilities = _capabilities([ContentType.IMAGE])
    _, part, _ = await _call(input_capabilities=capabilities)

    assert part.type is ContentType.IMAGE


@pytest.mark.asyncio
async def test_workflow_scope_skips_the_conversation_branch_check(monkeypatch):
    _patch_resolved_asset(monkeypatch, b"png-bytes", content_type="image/png")
    conversation_filter = MagicMock()
    monkeypatch.setattr("app.models.asset.MessageAsset.filter", conversation_filter)
    capabilities = _capabilities([ContentType.IMAGE])
    _, part, _ = await resolve_view_content(
        "a1b2",
        scope_type=AssetScopeType.WORKFLOW_RUN,
        scope_id=uuid4(),
        user=SimpleNamespace(id=uuid4()),
        model_config=_model(),
        agent=_agent(),
        input_capabilities=capabilities,
    )

    assert part.type is ContentType.IMAGE
    conversation_filter.assert_not_called()
