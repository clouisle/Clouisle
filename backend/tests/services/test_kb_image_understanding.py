from __future__ import annotations

import asyncio
import io
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from PIL import Image

from app.llm.types import ContentType
from app.models.model import ModelProvider, ModelType
from app.services import kb_image_understanding as image_service_module
from app.services.kb_image_understanding import (
    KBImageUnderstandingError,
    KBImageUnderstandingService,
    KBImageValidationError,
    normalize_kb_image,
)


def _png_bytes(*, size: tuple[int, int] = (3, 2), mode: str = "RGB") -> bytes:
    image = Image.new(mode, size, "red")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _service(**overrides) -> KBImageUnderstandingService:
    options = {
        "max_images": 3,
        "max_image_bytes": 1024 * 1024,
        "max_image_pixels": 100,
        "concurrency": 2,
    }
    options.update(overrides)
    return KBImageUnderstandingService(**options)


def _vision_model():
    return SimpleNamespace(
        model_type=ModelType.CHAT,
        provider=ModelProvider.OPENAI,
        base_url=None,
        capabilities={"input_modalities": ["text", "image"]},
    )


def test_normalize_png_to_jpeg_and_reject_svg_and_size_limits() -> None:
    normalized = normalize_kb_image(
        _png_bytes(), max_image_bytes=1024 * 1024, max_image_pixels=100
    )
    assert normalized.mime_type == "image/jpeg"
    assert (normalized.width, normalized.height) == (3, 2)
    with Image.open(io.BytesIO(normalized.image_bytes)) as decoded:
        assert decoded.format == "JPEG"

    with pytest.raises(KBImageValidationError, match="SVG"):
        normalize_kb_image(
            b'<svg xmlns="http://www.w3.org/2000/svg"></svg>',
            max_image_bytes=1024,
            max_image_pixels=100,
        )
    with pytest.raises(KBImageValidationError, match="byte limit"):
        normalize_kb_image(_png_bytes(), max_image_bytes=1, max_image_pixels=100)
    with pytest.raises(KBImageValidationError, match="pixel limit"):
        normalize_kb_image(
            _png_bytes(size=(11, 10)), max_image_bytes=1024, max_image_pixels=100
        )


@pytest.mark.asyncio
async def test_duplicate_inputs_make_one_call_and_map_results(monkeypatch):
    model_id = uuid4()
    payload = _png_bytes()
    monkeypatch.setattr(
        image_service_module.model_manager,
        "resolve_team_chat_model",
        AsyncMock(return_value=(_vision_model(), SimpleNamespace())),
    )
    model_call = AsyncMock(
        return_value=SimpleNamespace(
            content='```json\n{"ocr_text":"Words","description":"A red square."}\n```'
        )
    )
    monkeypatch.setattr(image_service_module.model_manager, "team_chat", model_call)

    results = await _service().analyze_images(
        [payload, payload], team_id="team-1", model_id=model_id
    )

    model_call.assert_awaited_once()
    assert len(results) == 2
    assert results[0] == results[1]


@pytest.mark.asyncio
async def test_batch_rejects_count_and_non_vision_models_before_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_id = uuid4()
    resolve = AsyncMock(
        return_value=(
            SimpleNamespace(
                model_type=ModelType.CHAT,
                provider=ModelProvider.OPENAI,
                base_url=None,
                capabilities={"input_modalities": ["text"]},
            ),
            SimpleNamespace(),
        )
    )
    model_call = AsyncMock()
    monkeypatch.setattr(
        image_service_module.model_manager, "resolve_team_chat_model", resolve
    )
    monkeypatch.setattr(image_service_module.model_manager, "team_chat", model_call)

    with pytest.raises(KBImageValidationError, match="count"):
        await _service(max_images=1).analyze_images(
            [_png_bytes(), _png_bytes()], team_id="team-1", model_id=model_id
        )
    resolve.assert_not_awaited()

    with pytest.raises(KBImageUnderstandingError):
        await _service().analyze_image(
            _png_bytes(), team_id="team-1", model_id=model_id
        )
    model_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_analyze_images_checks_authorized_vision_model_and_returns_safe_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_id = uuid4()
    resolve = AsyncMock(return_value=(_vision_model(), SimpleNamespace()))
    model_call = AsyncMock(
        return_value=SimpleNamespace(
            content='{"ocr_text":"Visible words","description":"A red square."}'
        )
    )
    monkeypatch.setattr(
        image_service_module.model_manager, "resolve_team_chat_model", resolve
    )
    monkeypatch.setattr(image_service_module.model_manager, "team_chat", model_call)

    result = await _service().analyze_image(
        _png_bytes(), team_id="team-1", model_id=model_id
    )

    resolve.assert_awaited_once_with(team_id="team-1", model_id=str(model_id))
    model_call.assert_awaited_once()
    assert model_call.await_args.kwargs["team_id"] == "team-1"
    assert model_call.await_args.kwargs["model_id"] == str(model_id)
    assert model_call.await_args.kwargs["temperature"] == 0
    assert model_call.await_args.kwargs["max_tokens"] > 0
    messages = model_call.await_args.kwargs["messages"]
    assert "untrusted" in messages[0].content.lower()
    user_content = messages[1].content
    assert [part.type for part in user_content] == [ContentType.TEXT, ContentType.IMAGE]
    assert result.ocr_text == "Visible words"
    assert result.description == "A red square."
    assert result.to_metadata() == {
        "ocr_text": "Visible words",
        "description": "A red square.",
        "mime_type": "image/jpeg",
        "width": 3,
        "height": 2,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "expected_code"),
    [
        ("", "empty_vision_response"),
        ('{"ocr_text":"", "description":"  "}', "invalid_vision_response"),
        ("x" * 16_385, "vision_response_too_large"),
    ],
)
async def test_model_empty_invalid_or_oversized_response_fails_explicitly(
    monkeypatch: pytest.MonkeyPatch, content: str, expected_code: str
) -> None:
    model_id = uuid4()
    monkeypatch.setattr(
        image_service_module.model_manager,
        "resolve_team_chat_model",
        AsyncMock(return_value=(_vision_model(), SimpleNamespace())),
    )
    monkeypatch.setattr(
        image_service_module.model_manager,
        "team_chat",
        AsyncMock(return_value=SimpleNamespace(content=content)),
    )

    with pytest.raises(KBImageUnderstandingError) as error:
        await _service().analyze_image(
            _png_bytes(), team_id="team-1", model_id=model_id
        )
    assert error.value.code == expected_code


@pytest.mark.asyncio
async def test_model_call_timeout_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    model_id = uuid4()
    monkeypatch.setattr(
        image_service_module.model_manager,
        "resolve_team_chat_model",
        AsyncMock(return_value=(_vision_model(), SimpleNamespace())),
    )

    async def wait_forever(**_kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(image_service_module, "_MODEL_TIMEOUT_SECONDS", 0.001)
    monkeypatch.setattr(
        image_service_module.model_manager,
        "team_chat",
        AsyncMock(side_effect=wait_forever),
    )
    with pytest.raises(KBImageUnderstandingError) as error:
        await _service().analyze_image(
            _png_bytes(), team_id="team-1", model_id=model_id
        )
    assert error.value.code == "vision_timeout"


@pytest.mark.asyncio
async def test_split_models_extract_ocr_and_description_separately(monkeypatch):
    ocr_model_id, vision_model_id = uuid4(), uuid4()
    monkeypatch.setattr(
        image_service_module.model_manager,
        "resolve_team_chat_model",
        AsyncMock(return_value=(_vision_model(), SimpleNamespace())),
    )
    calls: list[str] = []

    async def team_chat(**kwargs):
        calls.append(kwargs["model_id"])
        system = kwargs["messages"][0].content.lower()
        if "transcribe visible text" in system:
            return SimpleNamespace(content="")
        return SimpleNamespace(content="A red square with a border.")

    monkeypatch.setattr(image_service_module.model_manager, "team_chat", team_chat)

    results = await _service().analyze_images_split(
        [_png_bytes()],
        team_id="team-1",
        ocr_model_id=ocr_model_id,
        vision_model_id=vision_model_id,
    )

    assert len(results) == 1
    assert results[0].ocr_text == ""
    assert results[0].description == "A red square with a border."
    assert sorted(calls) == sorted([str(ocr_model_id), str(vision_model_id)])


@pytest.mark.asyncio
async def test_ocr_only_extracts_text_without_description(monkeypatch):
    model_id = uuid4()
    monkeypatch.setattr(
        image_service_module.model_manager,
        "resolve_team_chat_model",
        AsyncMock(return_value=(_vision_model(), SimpleNamespace())),
    )
    monkeypatch.setattr(
        image_service_module.model_manager,
        "team_chat",
        AsyncMock(return_value=SimpleNamespace(content="ONLY OCR TEXT")),
    )

    results = await _service().extract_ocr_images(
        [_png_bytes()], team_id="team-1", model_id=model_id
    )

    assert results[0].ocr_text == "ONLY OCR TEXT"
    assert results[0].description == ""


def test_normalize_rejects_empty_limits_formats_and_covers_transparency() -> None:
    with pytest.raises(KBImageValidationError, match="non-empty bytes"):
        normalize_kb_image(b"", max_image_bytes=10, max_image_pixels=10)
    with pytest.raises(KBImageValidationError, match="limits must be positive"):
        normalize_kb_image(_png_bytes(), max_image_bytes=0, max_image_pixels=10)

    bmp = io.BytesIO()
    Image.new("RGB", (2, 2), "red").save(bmp, format="BMP")
    with pytest.raises(KBImageValidationError, match="Unsupported raster"):
        normalize_kb_image(bmp.getvalue(), max_image_bytes=1024, max_image_pixels=100)

    gif = io.BytesIO()
    Image.new("P", (2, 2)).save(gif, format="GIF")
    assert (
        normalize_kb_image(
            gif.getvalue(), max_image_bytes=1024, max_image_pixels=100
        ).mime_type
        == "image/jpeg"
    )

    rgba = io.BytesIO()
    Image.new("RGBA", (2, 2), (255, 0, 0, 0)).save(rgba, format="PNG")
    normalized = normalize_kb_image(
        rgba.getvalue(), max_image_bytes=1024, max_image_pixels=100
    )
    assert normalized.mime_type == "image/jpeg"


def test_normalize_rejects_output_larger_than_byte_limit() -> None:
    tiny = io.BytesIO()
    Image.new("RGB", (1, 1), "red").save(tiny, format="PNG")
    payload = tiny.getvalue()
    with pytest.raises(KBImageValidationError, match="Normalized image"):
        normalize_kb_image(payload, max_image_bytes=len(payload), max_image_pixels=100)


def test_service_constructor_rejects_non_positive_limits() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        KBImageUnderstandingService(
            max_images=0,
            max_image_bytes=1,
            max_image_pixels=1,
            concurrency=1,
        )


@pytest.mark.asyncio
async def test_batch_validation_paths_return_early_or_reject_bad_payloads() -> None:
    service = _service(max_image_bytes=4)
    model_id = uuid4()

    assert await service.analyze_images([], team_id="t", model_id=model_id) == []
    assert (
        await service.analyze_images_split(
            [], team_id="t", ocr_model_id=model_id, vision_model_id=model_id
        )
        == []
    )
    assert await service.extract_ocr_images([], team_id="t", model_id=model_id) == []

    with pytest.raises(KBImageValidationError, match="model UUID"):
        await service.analyze_images([_png_bytes()], team_id="t", model_id="not-a-uuid")
    with pytest.raises(KBImageValidationError, match="model UUIDs"):
        await service.analyze_images_split(
            [_png_bytes()], team_id="t", ocr_model_id="x", vision_model_id=model_id
        )
    with pytest.raises(KBImageValidationError, match="model UUID"):
        await service.extract_ocr_images(
            [_png_bytes()], team_id="t", model_id="not-a-uuid"
        )

    with pytest.raises(KBImageValidationError, match="non-empty bytes"):
        await service.analyze_images([""], team_id="t", model_id=model_id)
    with pytest.raises(KBImageValidationError, match="byte limit"):
        await service.analyze_images([b"x" * 5], team_id="t", model_id=model_id)

    with pytest.raises(KBImageValidationError, match="count"):
        await _service(max_images=1).analyze_images_split(
            [_png_bytes(), _png_bytes()],
            team_id="t",
            ocr_model_id=model_id,
            vision_model_id=model_id,
        )
    with pytest.raises(KBImageValidationError, match="count"):
        await _service(max_images=1).extract_ocr_images(
            [_png_bytes(), _png_bytes()], team_id="t", model_id=model_id
        )


@pytest.mark.asyncio
async def test_batch_cancellation_paths_cancel_pending_tasks(monkeypatch) -> None:
    model_id = uuid4()
    monkeypatch.setattr(
        image_service_module.model_manager,
        "resolve_team_chat_model",
        AsyncMock(return_value=(_vision_model(), SimpleNamespace())),
    )

    async def analyze(self, payload, **_kwargs):
        if payload == _png_bytes(size=(3, 2)):
            raise KBImageUnderstandingError("boom")
        await asyncio.Event().wait()

    async def split(self, payload, **_kwargs):
        if payload == _png_bytes(size=(3, 2)):
            raise KBImageUnderstandingError("boom")
        await asyncio.Event().wait()

    async def ocr(self, payload, **_kwargs):
        if payload == _png_bytes(size=(3, 2)):
            raise KBImageUnderstandingError("boom")
        await asyncio.Event().wait()

    for method, kwargs in (
        ("_analyze_payload", {}),
        ("_analyze_split_payload", {}),
        ("_analyze_ocr_payload", {}),
    ):
        monkeypatch.setattr(
            KBImageUnderstandingService,
            method,
            analyze
            if method == "_analyze_payload"
            else split
            if method == "_analyze_split_payload"
            else ocr,
        )
        service = _service()
        payloads = [_png_bytes(size=(3, 2)), _png_bytes(size=(2, 2))]
        with pytest.raises(KBImageUnderstandingError):
            if method == "_analyze_payload":
                await service.analyze_images(payloads, team_id="t", model_id=model_id)
            elif method == "_analyze_split_payload":
                await service.analyze_images_split(
                    payloads,
                    team_id="t",
                    ocr_model_id=model_id,
                    vision_model_id=model_id,
                )
            else:
                await service.extract_ocr_images(
                    payloads, team_id="t", model_id=model_id
                )


@pytest.mark.asyncio
async def test_split_payload_cancels_peer_when_one_call_fails(monkeypatch) -> None:
    async def team_chat(**kwargs):
        if "transcribe visible text" in kwargs["messages"][0].content.lower():
            raise KBImageUnderstandingError("ocr failed")
        await asyncio.Event().wait()

    monkeypatch.setattr(image_service_module.model_manager, "team_chat", team_chat)
    with pytest.raises(KBImageUnderstandingError):
        await _service()._analyze_split_payload(
            _png_bytes(),
            team_id="t",
            ocr_model_id=uuid4(),
            vision_model_id=uuid4(),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "allow_empty", "expected_code"),
    [
        (None, True, "invalid_ocr_response"),
        ("x" * 16_385, True, "ocr_response_too_large"),
        ("```text```", True, None),
        ("", False, "empty_description_response"),
    ],
)
async def test_image_prompt_response_validation(
    monkeypatch, content, allow_empty, expected_code
) -> None:
    monkeypatch.setattr(
        image_service_module.model_manager,
        "team_chat",
        AsyncMock(return_value=SimpleNamespace(content=content)),
    )
    normalized = normalize_kb_image(
        _png_bytes(), max_image_bytes=1024, max_image_pixels=100
    )
    if expected_code:
        with pytest.raises(KBImageUnderstandingError) as error:
            await _service()._call_image_prompt(
                normalized,
                team_id="t",
                model_id=uuid4(),
                system_prompt="s",
                user_prompt="u",
                label="ocr" if allow_empty else "description",
                allow_empty=allow_empty,
            )
        assert error.value.code == expected_code
    else:
        assert (
            await _service()._call_image_prompt(
                normalized,
                team_id="t",
                model_id=uuid4(),
                system_prompt="s",
                user_prompt="u",
                label="ocr",
                allow_empty=True,
            )
            == "text"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "expected_code"),
    [
        ("[]", "invalid_vision_response"),
        ('```json{"ocr_text":"a","description":"b"}', None),
        ('```json\n{"ocr_text":"a","description":"b"}', None),
    ],
)
async def test_vision_response_json_shapes(monkeypatch, content, expected_code) -> None:
    model_id = uuid4()
    monkeypatch.setattr(
        image_service_module.model_manager,
        "resolve_team_chat_model",
        AsyncMock(return_value=(_vision_model(), SimpleNamespace())),
    )
    monkeypatch.setattr(
        image_service_module.model_manager,
        "team_chat",
        AsyncMock(return_value=SimpleNamespace(content=content)),
    )
    if expected_code:
        with pytest.raises(KBImageUnderstandingError) as error:
            await _service().analyze_image(_png_bytes(), team_id="t", model_id=model_id)
        assert error.value.code == expected_code
    else:
        result = await _service().analyze_image(
            _png_bytes(), team_id="t", model_id=model_id
        )
        assert result.description == "b"
