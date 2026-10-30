from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.services import kb_image_ingestion as ingestion


def _settings(**overrides):
    return {**ingestion.IMAGE_DEFAULTS, **overrides}


@pytest.mark.asyncio
async def test_enrich_inserts_ocr_and_description_at_matching_image():
    result = SimpleNamespace(
        ocr_text="<b>answer 42</b>",
        description="A red diagram",
        mime_type="image/jpeg",
        width=10,
        height=10,
    )
    asset = {"url": "/api/v1/kb/media/a.png", "path": "documents/kb/media/a.png"}
    settings = _settings(
        kb_image_understanding_enabled=True,
        kb_image_understanding_model_id=str(uuid4()),
    )
    with (
        patch.object(
            ingestion.document_processor, "read_file", AsyncMock(return_value=b"png")
        ),
        patch.object(
            ingestion.KBImageUnderstandingService,
            "analyze_images",
            AsyncMock(return_value=[result]),
        ),
    ):
        text, metadata = await ingestion.enrich_document_images(
            "before ![a](/api/v1/kb/media/a.png) after",
            {"media_assets": [asset]},
            team_id=uuid4(),
            settings=settings,
        )

    assert text == (
        "before ![a](/api/v1/kb/media/a.png)\n\n"
        "Image description: A red diagram\nImage text: answer 42 after"
    )
    assert metadata["image_understanding"]["images"] == [
        {
            "url": "/api/v1/kb/media/a.png",
            "description": "A red diagram",
            "ocr_text": "answer 42",
        }
    ]


@pytest.mark.asyncio
async def test_disabled_understanding_rejects_image_documents_only():
    settings = _settings()
    with pytest.raises(ValueError, match="image_understanding_disabled"):
        await ingestion.enrich_document_images(
            "text", {"doc_type": "image"}, team_id=uuid4(), settings=settings
        )

    assert await ingestion.enrich_document_images(
        "text", {"doc_type": "pdf"}, team_id=uuid4(), settings=settings
    ) == ("text", {"doc_type": "pdf"})


@pytest.mark.asyncio
async def test_external_images_require_both_site_switches():
    fetch = AsyncMock(return_value=(b"png", "image/png"))
    with patch("app.services.kb_external_images.fetch_external_image", fetch):
        for settings in (
            _settings(),
            _settings(kb_image_understanding_allow_external=True),
            _settings(kb_image_understanding_enabled=True),
        ):
            text, metadata = await ingestion.ingest_external_images(
                "![x](https://example.test/x.png)",
                {},
                kb_id=uuid4(),
                document_id=uuid4(),
                settings=settings,
            )
            assert text == "![x](https://example.test/x.png)"
            assert metadata == {}
        fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_enrich_uses_dedicated_ocr_model_when_configured():
    vision_model_id, ocr_model_id = uuid4(), uuid4()
    result = SimpleNamespace(
        ocr_text="OCR text",
        description="A red diagram",
        mime_type="image/jpeg",
        width=10,
        height=10,
    )
    asset = {"url": "/api/v1/kb/media/a.png", "path": "documents/kb/media/a.png"}
    settings = _settings(
        kb_image_understanding_enabled=True,
        kb_image_understanding_model_id=str(vision_model_id),
        kb_image_ocr_model_id=str(ocr_model_id),
    )
    split = AsyncMock(return_value=[result])
    combined = AsyncMock()
    with (
        patch.object(
            ingestion.document_processor, "read_file", AsyncMock(return_value=b"png")
        ),
        patch.object(
            ingestion.KBImageUnderstandingService, "analyze_images_split", split
        ),
        patch.object(ingestion.KBImageUnderstandingService, "analyze_images", combined),
    ):
        text, metadata = await ingestion.enrich_document_images(
            "![a](/api/v1/kb/media/a.png)",
            {"media_assets": [asset]},
            team_id=uuid4(),
            settings=settings,
        )

    split.assert_awaited_once()
    combined.assert_not_awaited()
    assert "Image text: OCR text" in text
    assert metadata["image_understanding"]["ocr_model_id"] == str(ocr_model_id)
    assert metadata["image_understanding"]["vision_model_id"] == str(vision_model_id)


@pytest.mark.asyncio
async def test_enrich_supports_ocr_only_mode():
    ocr_model_id = uuid4()
    result = SimpleNamespace(
        ocr_text="ONLY TEXT",
        description="",
        mime_type="image/jpeg",
        width=10,
        height=10,
    )
    asset = {"url": "/api/v1/kb/media/a.png", "path": "documents/kb/media/a.png"}
    settings = _settings(
        kb_image_understanding_enabled=True,
        kb_image_understanding_model_id="",
        kb_image_ocr_model_id=str(ocr_model_id),
    )
    extract = AsyncMock(return_value=[result])
    with (
        patch.object(
            ingestion.document_processor, "read_file", AsyncMock(return_value=b"png")
        ),
        patch.object(
            ingestion.KBImageUnderstandingService, "extract_ocr_images", extract
        ),
    ):
        text, metadata = await ingestion.enrich_document_images(
            "![a](/api/v1/kb/media/a.png)",
            {"media_assets": [asset]},
            team_id=uuid4(),
            settings=settings,
        )

    extract.assert_awaited_once()
    assert "Image text: ONLY TEXT" in text
    assert "Image description:" not in text
    assert metadata["image_understanding"]["vision_model_id"] == ""
    assert metadata["image_understanding"]["ocr_model_id"] == str(ocr_model_id)


@pytest.mark.asyncio
async def test_ocr_only_image_without_text_is_rejected():
    result = SimpleNamespace(
        ocr_text="",
        description="",
        mime_type="image/jpeg",
        width=10,
        height=10,
    )
    asset = {"url": "/api/v1/kb/media/a.png", "path": "documents/kb/media/a.png"}
    settings = _settings(
        kb_image_understanding_enabled=True,
        kb_image_ocr_model_id=str(uuid4()),
    )
    with (
        patch.object(
            ingestion.document_processor, "read_file", AsyncMock(return_value=b"png")
        ),
        patch.object(
            ingestion.KBImageUnderstandingService,
            "extract_ocr_images",
            AsyncMock(return_value=[result]),
        ),
    ):
        with pytest.raises(ingestion.KBImageValidationError) as exc_info:
            await ingestion.enrich_document_images(
                "![a](/api/v1/kb/media/a.png)",
                {"media_assets": [asset], "doc_type": "image"},
                team_id=uuid4(),
                settings=settings,
            )
    assert exc_info.value.code == "image_no_text_extracted"
