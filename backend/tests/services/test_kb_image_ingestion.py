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


@pytest.mark.asyncio
async def test_image_settings_accepts_valid_values():
    with patch.object(
        ingestion.SiteSetting,
        "get_values",
        AsyncMock(return_value=_settings()),
    ):
        assert await ingestion.image_settings() == _settings()


@pytest.mark.asyncio
async def test_external_images_with_enabled_settings_and_no_links_are_untouched():
    settings = _settings(
        kb_image_understanding_enabled=True,
        kb_image_understanding_allow_external=True,
    )
    assert await ingestion.ingest_external_images(
        "plain text",
        {},
        kb_id=uuid4(),
        document_id=uuid4(),
        settings=settings,
    ) == ("plain text", {})


@pytest.mark.asyncio
async def test_pdf_pages_without_rendered_image_skip_media_assets():
    page = SimpleNamespace(
        needs_visual_recognition=False,
        text="text only",
        page_number=1,
        image_png=None,
    )
    text, metadata = await ingestion.ingest_pdf_pages(
        {},
        content=b"pdf",
        kb_id=uuid4(),
        document_id=uuid4(),
        settings=_settings(),
        pages=[page],
    )
    assert text == "## Page 1\n\ntext only"
    assert metadata["media_assets"] == []


@pytest.mark.asyncio
async def test_enrich_records_empty_annotation_without_touching_text():
    result = SimpleNamespace(
        ocr_text="",
        description="",
        mime_type="image/png",
        width=1,
        height=1,
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
            "![a](/api/v1/kb/media/a.png)",
            {
                "media_assets": [
                    {"url": "/api/v1/kb/media/a.png", "path": "documents/a.png"}
                ]
            },
            team_id=uuid4(),
            settings=_settings(
                kb_image_understanding_enabled=True,
                kb_image_understanding_model_id=str(uuid4()),
            ),
        )
    assert text == "![a](/api/v1/kb/media/a.png)"
    assert metadata["image_understanding"]["images"][0]["description"] == ""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"kb_image_understanding_max_images": 0},
        {"kb_image_understanding_concurrency": "two"},
        {"kb_image_understanding_enabled": "yes"},
    ],
)
async def test_image_settings_reject_invalid_values(overrides):
    with patch.object(
        ingestion.SiteSetting,
        "get_values",
        AsyncMock(return_value=_settings(**overrides)),
    ):
        with pytest.raises(ValueError, match="invalid_image_understanding_settings"):
            await ingestion.image_settings()


@pytest.mark.asyncio
async def test_prepare_document_extracts_plain_file_and_skips_disabled_pdf_pages():
    document = SimpleNamespace(
        knowledge_base=SimpleNamespace(id=uuid4(), team_id=uuid4()),
        file_path="documents/a.pdf",
        doc_type="pdf",
        id=uuid4(),
    )
    with (
        patch.object(
            ingestion.document_processor,
            "extract_text",
            AsyncMock(return_value=("plain", {})),
        ),
        patch.object(
            ingestion,
            "ingest_external_images",
            AsyncMock(side_effect=lambda text, metadata, **_: (text, metadata)),
        ),
        patch.object(
            ingestion,
            "enrich_document_images",
            AsyncMock(side_effect=lambda text, metadata, **_: (text, metadata)),
        ),
    ):
        assert await ingestion.prepare_document(
            document, clean_text=True, settings=_settings()
        ) == ("plain", {})


@pytest.mark.asyncio
async def test_prepare_document_uses_visual_pdf_pages_only_when_needed():
    document = SimpleNamespace(
        knowledge_base=SimpleNamespace(id=uuid4(), team_id=uuid4()),
        file_path="documents/a.pdf",
        doc_type="pdf",
        id=uuid4(),
    )
    pages = [
        SimpleNamespace(
            needs_visual_recognition=True, text="Scan", page_number=1, image_png=b"png"
        ),
        SimpleNamespace(
            needs_visual_recognition=False, text="Text", page_number=2, image_png=None
        ),
    ]
    with (
        patch("app.services.kb_pdf_images.iter_pdf_pages", return_value=pages),
        patch.object(
            ingestion.document_processor, "read_file", AsyncMock(return_value=b"pdf")
        ),
        patch.object(
            ingestion,
            "ingest_pdf_pages",
            AsyncMock(return_value=("merged", {"media_assets": []})),
        ) as ingest_pdf,
        patch.object(
            ingestion,
            "ingest_external_images",
            AsyncMock(side_effect=lambda text, metadata, **_: (text, metadata)),
        ),
        patch.object(
            ingestion,
            "enrich_document_images",
            AsyncMock(side_effect=lambda text, metadata, **_: (text, metadata)),
        ),
    ):
        await ingestion.prepare_document(
            document,
            clean_text=True,
            settings=_settings(kb_image_understanding_enabled=True),
        )
    ingest_pdf.assert_awaited_once()


@pytest.mark.asyncio
async def test_prepare_document_rejects_too_many_pdf_images_while_reading():
    document = SimpleNamespace(
        knowledge_base=SimpleNamespace(id=uuid4(), team_id=uuid4()),
        file_path="documents/a.pdf",
        doc_type="pdf",
        id=uuid4(),
    )
    pages = [
        SimpleNamespace(
            needs_visual_recognition=True, text="1", page_number=1, image_png=b"1"
        ),
        SimpleNamespace(
            needs_visual_recognition=True, text="2", page_number=2, image_png=b"2"
        ),
    ]
    with (
        patch("app.services.kb_pdf_images.iter_pdf_pages", return_value=pages),
        patch.object(
            ingestion.document_processor, "read_file", AsyncMock(return_value=b"pdf")
        ),
    ):
        with pytest.raises(ValueError, match="image_count_exceeded"):
            await ingestion.prepare_document(
                document,
                clean_text=True,
                settings=_settings(
                    kb_image_understanding_enabled=True,
                    kb_image_understanding_max_images=1,
                ),
            )


@pytest.mark.asyncio
async def test_prepare_document_extracts_xlsx_images_when_enabled():
    document = SimpleNamespace(
        knowledge_base=SimpleNamespace(id=uuid4(), team_id=uuid4()),
        file_path="documents/a.xlsx",
        doc_type="xlsx",
        id=uuid4(),
    )
    with (
        patch.object(
            ingestion.document_processor,
            "extract_text",
            AsyncMock(return_value=("sheet", {})),
        ),
        patch.object(
            ingestion.document_processor, "read_file", AsyncMock(return_value=b"xlsx")
        ),
        patch.object(
            ingestion,
            "ingest_xlsx_images",
            AsyncMock(return_value=("sheet+image", {"media_assets": []})),
        ) as ingest_xlsx,
        patch.object(
            ingestion,
            "ingest_external_images",
            AsyncMock(side_effect=lambda text, metadata, **_: (text, metadata)),
        ),
        patch.object(
            ingestion,
            "enrich_document_images",
            AsyncMock(side_effect=lambda text, metadata, **_: (text, metadata)),
        ),
    ):
        await ingestion.prepare_document(
            document,
            clean_text=False,
            settings=_settings(kb_image_understanding_enabled=True),
        )
    ingest_xlsx.assert_awaited_once()


@pytest.mark.asyncio
async def test_prepare_document_handles_url_and_missing_sources():
    document = SimpleNamespace(
        knowledge_base=SimpleNamespace(id=uuid4(), team_id=uuid4()),
        file_path=None,
        source_url="https://example.test/page",
        doc_type="html",
        id=uuid4(),
    )
    with (
        patch.object(
            ingestion.document_processor,
            "fetch_url_content",
            AsyncMock(return_value=("url body", {})),
        ),
        patch.object(
            ingestion,
            "ingest_external_images",
            AsyncMock(side_effect=lambda text, metadata, **_: (text, metadata)),
        ),
        patch.object(
            ingestion,
            "enrich_document_images",
            AsyncMock(side_effect=lambda text, metadata, **_: (text, metadata)),
        ),
    ):
        assert await ingestion.prepare_document(
            document, clean_text=True, settings=_settings()
        ) == ("url body", {})

    document.source_url = None
    with pytest.raises(ValueError, match="document_missing_source"):
        await ingestion.prepare_document(
            document, clean_text=True, settings=_settings()
        )


@pytest.mark.asyncio
async def test_external_images_are_downloaded_and_recorded():
    asset = {"url": "/api/v1/kb/media/x.png", "path": "documents/x.png"}
    fetch = AsyncMock(return_value=(b"image", "image/png"))
    replace = AsyncMock(return_value=("![x](data:image/png;base64,aW1hZ2U=)", [asset]))
    with (
        patch("app.services.kb_external_images.fetch_external_image", fetch),
        patch.object(
            ingestion.document_processor,
            "replace_embedded_media_data_uris",
            replace,
        ),
    ):
        text, metadata = await ingestion.ingest_external_images(
            "before ![x](https://example.test/x.png) after",
            {},
            kb_id=uuid4(),
            document_id=uuid4(),
            settings=_settings(
                kb_image_understanding_enabled=True,
                kb_image_understanding_allow_external=True,
            ),
        )
    fetch.assert_awaited_once()
    assert text.startswith("before ![x](data:image/png")
    assert metadata["media_assets"] == [asset]


@pytest.mark.asyncio
async def test_external_images_reject_excess_and_keep_existing_assets():
    settings = _settings(
        kb_image_understanding_enabled=True,
        kb_image_understanding_allow_external=True,
        kb_image_understanding_max_images=1,
    )
    with pytest.raises(ValueError, match="image_count_exceeded"):
        await ingestion.ingest_external_images(
            "![a](https://e.test/a.png) ![b](https://e.test/b.png)",
            {},
            kb_id=uuid4(),
            document_id=uuid4(),
            settings=settings,
        )

    existing = [{"url": "/api/v1/kb/media/a.png", "path": "documents/a.png"}]
    assert await ingestion.ingest_external_images(
        "no links",
        {"media_assets": existing},
        kb_id=uuid4(),
        document_id=uuid4(),
        settings=settings,
    ) == ("no links", {"media_assets": existing})


@pytest.mark.asyncio
async def test_xlsx_images_are_attached_with_sheet_metadata():
    image = SimpleNamespace(
        sheet_name="Sheet1", anchor="A1", content_type="image/png", data=b"png"
    )
    asset = {"url": "/api/v1/kb/media/x.png", "path": "documents/x.png"}
    with (
        patch("app.services.kb_xlsx_images.extract_xlsx_images", return_value=[image]),
        patch.object(
            ingestion.document_processor,
            "replace_embedded_media_data_uris",
            AsyncMock(return_value=("![Sheet1](data:image/png;base64,cG5n)", [asset])),
        ),
    ):
        text, metadata = await ingestion.ingest_xlsx_images(
            "sheet",
            {},
            content=b"xlsx",
            kb_id=uuid4(),
            document_id=uuid4(),
            settings=_settings(kb_image_understanding_enabled=True),
        )
    assert "![Sheet1]" in text
    assert metadata["media_assets"][0]["sheet"] == "Sheet1"
    assert metadata["media_assets"][0]["anchor"] == "A1"


@pytest.mark.asyncio
async def test_xlsx_images_disabled_or_empty_are_passthrough():
    assert await ingestion.ingest_xlsx_images(
        "sheet",
        {},
        content=b"xlsx",
        kb_id=uuid4(),
        document_id=uuid4(),
        settings=_settings(),
    ) == ("sheet", {})

    with patch("app.services.kb_xlsx_images.extract_xlsx_images", return_value=[]):
        assert await ingestion.ingest_xlsx_images(
            "sheet",
            {},
            content=b"xlsx",
            kb_id=uuid4(),
            document_id=uuid4(),
            settings=_settings(kb_image_understanding_enabled=True),
        ) == ("sheet", {})


@pytest.mark.asyncio
async def test_pdf_pages_build_markdown_and_bound_images():
    page = SimpleNamespace(
        needs_visual_recognition=True,
        text="hello",
        page_number=3,
        image_png=b"png",
    )

    def fake_pages(_content):
        yield page

    asset = {"url": "/api/v1/kb/media/page.png", "path": "documents/page.png"}
    with (
        patch("app.services.kb_pdf_images.iter_pdf_pages", fake_pages),
        patch.object(
            ingestion.document_processor,
            "replace_embedded_media_data_uris",
            AsyncMock(return_value=("![Page 3](data:image/png;base64,cG5n)", [asset])),
        ),
    ):
        text, metadata = await ingestion.ingest_pdf_pages(
            {},
            content=b"pdf",
            kb_id=uuid4(),
            document_id=uuid4(),
            settings=_settings(kb_image_understanding_enabled=True),
        )
    assert "## Page 3\n\nhello" in text
    assert metadata["format"] == "markdown"
    assert metadata["media_assets"][0]["page"] == 3
    assert metadata["media_assets"][0]["native_text"] is True


@pytest.mark.asyncio
async def test_pdf_pages_enforce_image_limit_in_both_modes():
    settings = _settings(
        kb_image_understanding_enabled=True,
        kb_image_understanding_max_images=1,
    )
    page = SimpleNamespace(
        needs_visual_recognition=True,
        text="",
        page_number=1,
        image_png=None,
    )
    with patch(
        "app.services.kb_pdf_images.iter_pdf_pages",
        lambda _content: iter([page, page]),
    ):
        with pytest.raises(ValueError, match="image_count_exceeded"):
            await ingestion.ingest_pdf_pages(
                {},
                content=b"pdf",
                kb_id=uuid4(),
                document_id=uuid4(),
                settings=settings,
            )

    with pytest.raises(ValueError, match="image_count_exceeded"):
        await ingestion.ingest_pdf_pages(
            {},
            content=b"pdf",
            kb_id=uuid4(),
            document_id=uuid4(),
            settings=settings,
            pages=[page, page],
        )


@pytest.mark.asyncio
async def test_enrich_without_assets_or_models_is_safe():
    settings = _settings(kb_image_understanding_enabled=True)
    assert await ingestion.enrich_document_images(
        "text", {}, team_id=uuid4(), settings=settings
    ) == ("text", {})

    with pytest.raises(ValueError, match="image_model_required"):
        await ingestion.enrich_document_images(
            "text",
            {"media_assets": [{"url": "/a.png", "path": "a.png"}]},
            team_id=uuid4(),
            settings=settings,
        )

    with pytest.raises(ValueError, match="invalid_image_understanding_settings"):
        await ingestion.enrich_document_images(
            "text",
            {"media_assets": [{"url": "/a.png", "path": "a.png"}]},
            team_id=uuid4(),
            settings=_settings(
                kb_image_understanding_enabled=True,
                kb_image_understanding_model_id="not-a-uuid",
            ),
        )

    with pytest.raises(ValueError, match="image_count_exceeded"):
        await ingestion.enrich_document_images(
            "text",
            {"media_assets": [{"url": "/a.png", "path": "a.png"}]},
            team_id=uuid4(),
            settings=_settings(
                kb_image_understanding_enabled=True,
                kb_image_understanding_model_id=str(uuid4()),
                kb_image_understanding_max_images=0,
            ),
        )


@pytest.mark.asyncio
async def test_enrich_uses_single_vision_model_and_records_location_metadata():
    model_id = uuid4()
    result = SimpleNamespace(
        ocr_text="TEXT",
        description="DESC",
        mime_type="image/png",
        width=1,
        height=1,
    )
    asset = {
        "url": "/api/v1/kb/media/a.png",
        "path": "documents/a.png",
        "page": 2,
        "sheet": "Sheet1",
        "anchor": "B2",
    }
    with (
        patch.object(
            ingestion.document_processor, "read_file", AsyncMock(return_value=b"png")
        ),
        patch.object(
            ingestion.KBImageUnderstandingService,
            "analyze_images",
            AsyncMock(return_value=[result]),
        ) as combined,
    ):
        text, metadata = await ingestion.enrich_document_images(
            "![a](/api/v1/kb/media/a.png)",
            {"media_assets": [asset]},
            team_id=uuid4(),
            settings=_settings(
                kb_image_understanding_enabled=True,
                kb_image_understanding_model_id=str(model_id),
                kb_image_ocr_model_id=str(model_id),
            ),
        )
    combined.assert_awaited_once()
    record = metadata["image_understanding"]["images"][0]
    assert record["page"] == 2
    assert record["sheet"] == "Sheet1"
    assert record["anchor"] == "B2"
    assert "Image description: DESC" in text


@pytest.mark.asyncio
async def test_enrich_rejects_missing_image_reference():
    result = SimpleNamespace(
        ocr_text="TEXT",
        description="",
        mime_type="image/png",
        width=1,
        height=1,
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
        with pytest.raises(ValueError, match="image_reference_missing"):
            await ingestion.enrich_document_images(
                "no image here",
                {
                    "media_assets": [
                        {"url": "/api/v1/kb/media/a.png", "path": "documents/a.png"}
                    ]
                },
                team_id=uuid4(),
                settings=_settings(
                    kb_image_understanding_enabled=True,
                    kb_image_understanding_model_id=str(uuid4()),
                ),
            )


@pytest.mark.asyncio
async def test_prepare_document_uses_plain_extraction_for_text_only_pdf():
    document = SimpleNamespace(
        knowledge_base=SimpleNamespace(id=uuid4(), team_id=uuid4()),
        file_path="documents/a.pdf",
        doc_type="pdf",
        id=uuid4(),
    )
    page = SimpleNamespace(
        needs_visual_recognition=False,
        text="enough text",
        page_number=1,
        image_png=None,
    )
    with (
        patch("app.services.kb_pdf_images.iter_pdf_pages", return_value=[page]),
        patch.object(
            ingestion.document_processor, "read_file", AsyncMock(return_value=b"pdf")
        ),
        patch.object(
            ingestion.document_processor,
            "extract_text",
            AsyncMock(return_value=("plain pdf", {})),
        ) as extract,
        patch.object(
            ingestion,
            "ingest_external_images",
            AsyncMock(side_effect=lambda text, metadata, **_: (text, metadata)),
        ),
        patch.object(
            ingestion,
            "enrich_document_images",
            AsyncMock(side_effect=lambda text, metadata, **_: (text, metadata)),
        ),
    ):
        assert await ingestion.prepare_document(
            document,
            clean_text=True,
            settings=_settings(kb_image_understanding_enabled=True),
        ) == ("plain pdf", {})
    extract.assert_awaited_once()


@pytest.mark.asyncio
async def test_pdf_pages_without_visual_need_are_collected_without_rendering():
    page = SimpleNamespace(
        needs_visual_recognition=False,
        text="text",
        page_number=1,
        image_png=None,
    )
    with patch(
        "app.services.kb_pdf_images.iter_pdf_pages", lambda _content: iter([page])
    ):
        text, metadata = await ingestion.ingest_pdf_pages(
            {},
            content=b"pdf",
            kb_id=uuid4(),
            document_id=uuid4(),
            settings=_settings(),
        )
    assert text == "## Page 1\n\ntext"
    assert metadata["media_assets"] == []


@pytest.mark.asyncio
async def test_external_images_preserve_markdown_title():
    asset = {"url": "/api/v1/kb/media/x.png", "path": "documents/x.png"}
    with (
        patch(
            "app.services.kb_external_images.fetch_external_image",
            AsyncMock(return_value=(b"image", "image/png")),
        ),
        patch.object(
            ingestion.document_processor,
            "replace_embedded_media_data_uris",
            AsyncMock(
                return_value=(
                    '![x](data:image/png;base64,aW1hZ2U= "Quarterly chart")',
                    [asset],
                )
            ),
        ) as replace,
    ):
        text, metadata = await ingestion.ingest_external_images(
            '![x](https://example.test/x.png "Quarterly chart")',
            {},
            kb_id=uuid4(),
            document_id=uuid4(),
            settings=_settings(
                kb_image_understanding_enabled=True,
                kb_image_understanding_allow_external=True,
            ),
        )
    assert '"Quarterly chart"' in text
    assert metadata["media_assets"] == [asset]
    assert replace.await_args.args[0].endswith(' "Quarterly chart")')
