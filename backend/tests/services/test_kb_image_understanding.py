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
