import base64
import io
import zipfile
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.integrations.feishu import FeishuAPIError
from app.integrations.feishu_content import FeishuContent
from app.services import feishu_rich_content as service
from app.services.document_processor import DocumentProcessor
from app.services import upload_storage


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1Pe"
    "AAAADUlEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)


@pytest.fixture(autouse=True)
def content_limit(monkeypatch):
    monkeypatch.setattr(
        service, "content_limit_bytes", AsyncMock(return_value=1024 * 1024)
    )


def text_block(block_id, text, kind=2, **extra):
    key = {1: "page", 2: "text", 3: "heading1", 12: "bullet"}[kind]
    return {
        "block_id": block_id,
        "block_type": kind,
        key: {"elements": [{"text_run": {"content": text}}]},
        **extra,
    }


@pytest.mark.asyncio
async def test_docx_downloads_actual_images_and_keeps_rich_structure(monkeypatch):
    blocks = [
        text_block("page", "", 1, children=["heading", "list", "table"]),
        text_block("heading", "Heading", 3),
        text_block("list", "List", 12, children=["image"]),
        {
            "block_id": "image",
            "block_type": 27,
            "image": {"token": "picture", "caption": {"content": "A [chart]"}},
        },
        {
            "block_id": "table",
            "block_type": 31,
            "table": {"property": {"column_size": 1}, "cells": ["cell"]},
        },
        {"block_id": "cell", "block_type": 32, "children": ["again"]},
        {"block_id": "again", "block_type": 27, "image": {"token": "picture"}},
    ]
    blocks[1]["heading1"]["elements"][0]["text_run"]["text_element_style"] = {
        "bold": True
    }
    original = deepcopy(blocks)
    client = SimpleNamespace(get_docx_blocks=AsyncMock(return_value=blocks))
    download = AsyncMock(return_value=(PNG, "application/octet-stream"))
    monkeypatch.setattr(service, "download_media", download)

    result = await service.load_rich_content(client, "docx", "document", "Title")

    markdown = result.content.decode()
    uri = "data:image/png;base64," + base64.b64encode(PNG).decode()
    assert "# **Heading**" in markdown
    assert f"- List\n\n  ![A \\[chart\\]]({uri})" in markdown
    assert f"| ![Image]({uri}) |" in markdown
    assert result.filename == "Title.md"
    assert result.warnings == []
    assert blocks == original
    download.assert_awaited_once_with(client, "picture")


@pytest.fixture
def local_processor(tmp_path, monkeypatch):
    import importlib

    module = importlib.import_module("app.services.document_processor")
    processor = DocumentProcessor(upload_dir=str(tmp_path / "documents"))

    async def local_storage(root):
        return upload_storage.LocalUploadStorage(root)

    monkeypatch.setattr(module, "get_upload_storage_backend", local_storage)
    monkeypatch.setattr(processor, "_remote_mode", lambda: False)
    monkeypatch.setattr(service, "document_processor", processor)
    return processor


@pytest.mark.asyncio
async def test_embedded_attachment_is_extracted_using_real_processor(
    monkeypatch, local_processor, tmp_path
):
    blocks = [
        text_block("page", "", 1, children=["file"]),
        {
            "block_id": "file",
            "block_type": 23,
            "file": {"token": "attached", "name": "notes.md"},
        },
    ]
    uri = "data:image/png;base64," + base64.b64encode(PNG).decode()
    payload = f"## Attachment heading\n\n**Important**\n\n![Image]({uri})".encode()
    monkeypatch.setattr(
        service, "download_media", AsyncMock(return_value=(payload, "text/markdown"))
    )
    client = SimpleNamespace(get_docx_blocks=AsyncMock(return_value=blocks))

    result = await service.load_rich_content(client, "docx", "doc", "Title")

    markdown = result.content.decode()
    assert "Attachment: notes.md" in markdown
    assert "## Attachment heading\n\n**Important**" in markdown
    assert uri in markdown
    assert result.warnings == []
    # Extraction does not resourceize images under permanent/random document IDs.
    assert not list(tmp_path.rglob("*.png"))
    assert not list(tmp_path.rglob("*.md"))


@pytest.mark.asyncio
async def test_attachment_parser_passes_office_bytes_and_never_final_ids(monkeypatch):
    processor = SimpleNamespace(
        get_document_type=lambda *_: "docx",
        _remote_mode=lambda: False,
        save_file=AsyncMock(),
        extract_text=AsyncMock(return_value=("Office **content**", {})),
        delete_file=AsyncMock(),
    )
    monkeypatch.setattr(service, "document_processor", processor)
    payload = b"PK-office-payload"

    text = await service.extract_attachment_text(payload, "report.docx")

    assert text == "Office **content**"
    path = processor.save_file.await_args.args[1]
    assert path.startswith("documents/feishu-attachments/")
    assert path.endswith(".docx")
    processor.save_file.assert_awaited_once_with(payload, path)
    processor.extract_text.assert_awaited_once_with(path, "docx", clean_text=False)
    processor.delete_file.assert_awaited_once_with(path)


@pytest.mark.asyncio
async def test_attachment_staging_cleanup_on_conversion_failure(monkeypatch):
    processor = SimpleNamespace(
        get_document_type=lambda *_: "pdf",
        _remote_mode=lambda: False,
        save_file=AsyncMock(),
        extract_text=AsyncMock(side_effect=ValueError("conversion failed")),
        delete_file=AsyncMock(),
    )
    monkeypatch.setattr(service, "document_processor", processor)
    with pytest.raises(ValueError, match="conversion failed"):
        await service.extract_attachment_text(b"%PDF", "report.pdf")
    processor.delete_file.assert_awaited_once_with(
        processor.save_file.await_args.args[1]
    )


@pytest.mark.asyncio
async def test_attachment_staging_uses_gateway_in_remote_mode(monkeypatch):
    processor = SimpleNamespace(
        get_document_type=lambda *_: "txt",
        _remote_mode=lambda: True,
        save_file=AsyncMock(),
        extract_text=AsyncMock(return_value=("Remote text", {})),
        delete_file=AsyncMock(),
    )
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200)

    monkeypatch.setattr(service, "document_processor", processor)
    monkeypatch.setattr(
        service.upload_gateway,
        "client",
        lambda: httpx.AsyncClient(
            base_url="http://gateway", transport=httpx.MockTransport(handler)
        ),
    )

    assert (
        await service.extract_attachment_text(b"Remote text", "report.txt")
        == "Remote text"
    )
    assert requests[0].url.path == "/internal/uploads/save"
    assert requests[0].content == b"Remote text"
    path = requests[0].url.params["key"]
    processor.extract_text.assert_awaited_once_with(path, "txt", clean_text=False)
    processor.delete_file.assert_awaited_once_with(path)
    processor.save_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_inline_attachment_uses_media_payload_without_mutating_text_styles(
    monkeypatch,
):
    blocks = [text_block("paragraph", "before ")]
    blocks[0]["text"]["elements"] += [
        {"file": {"file_token": "inline"}},
        {"text_run": {"content": " after", "text_element_style": {"italic": True}}},
    ]
    monkeypatch.setattr(
        service, "download_media", AsyncMock(return_value=(PNG, "image/png"))
    )
    result = await service.load_rich_content(
        SimpleNamespace(get_docx_blocks=AsyncMock(return_value=blocks)),
        "docx",
        "doc",
        "Title",
    )
    assert "before ![Attachment](data:image/png;base64," in result.content.decode()
    assert "* after*" in result.content.decode()
    assert result.warnings == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("extracted", "error", "warning"),
    [
        (None, None, "unsupported_attachment:file"),
        ("", None, "empty_attachment:file"),
        (None, ValueError("failed"), "attachment_extraction_failed:file"),
    ],
)
async def test_attachment_limitations_are_explicit(
    monkeypatch, extracted, error, warning
):
    blocks = [
        {
            "block_id": "file",
            "block_type": 23,
            "file": {"token": "binary", "name": "archive.zip"},
        }
    ]
    monkeypatch.setattr(
        service,
        "download_media",
        AsyncMock(return_value=(b"binary", "application/zip")),
    )
    monkeypatch.setattr(
        service,
        "extract_attachment_text",
        AsyncMock(return_value=extracted, side_effect=error),
    )
    result = await service.load_rich_content(
        SimpleNamespace(get_docx_blocks=AsyncMock(return_value=blocks)),
        "docx",
        "doc",
        "Title",
    )
    assert result.warnings == [warning]
    assert "Attachment: archive.zip" in result.content.decode()
    assert "binary" not in result.content.decode()


@pytest.mark.asyncio
async def test_unknown_attachment_format_is_not_decoded_as_binary_text(local_processor):
    assert (
        await service.extract_attachment_text(
            b"PK binary", "archive.zip", "application/zip"
        )
        is None
    )


@pytest.mark.asyncio
async def test_media_permission_failure_aborts_instead_of_successful_partial_import(
    monkeypatch,
):
    blocks = [
        {
            "block_id": "file",
            "block_type": 23,
            "file": {"token": "revoked", "name": "notes.txt"},
        }
    ]
    error = FeishuAPIError("permission denied", code=99991672)
    monkeypatch.setattr(service, "download_media", AsyncMock(side_effect=error))
    with pytest.raises(FeishuAPIError) as raised:
        await service.load_rich_content(
            SimpleNamespace(get_docx_blocks=AsyncMock(return_value=blocks)),
            "docx",
            "doc",
            "Title",
        )
    assert raised.value is error


@pytest.mark.asyncio
async def test_doc_export_uses_supported_docx_format(monkeypatch):
    client = object()
    export = AsyncMock(
        return_value=FeishuContent("provider.docx", b"PK-office", ["provider-warning"])
    )
    monkeypatch.setattr(service, "export_document", export)
    result = await service.load_rich_content(client, "doc", "old-doc", "Title")
    assert result == FeishuContent("Title.docx", b"PK-office", ["provider-warning"])
    export.assert_awaited_once_with(client, "old-doc", "doc", "docx")


@pytest.mark.asyncio
async def test_mindnote_is_not_sent_to_unsupported_export_api(monkeypatch):
    export = AsyncMock()
    monkeypatch.setattr(service, "export_document", export)
    with pytest.raises(service.UnsupportedContentError, match="public API"):
        await service.load_rich_content(object(), "mindnote", "mindnote", "Title")
    export.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "block",
    [
        {"block_id": "image", "block_type": 27, "image": {}},
        {"block_id": "file", "block_type": 23, "file": {}},
    ],
)
async def test_missing_media_payload_fails_instead_of_empty_import(block):
    from app.services.feishu_knowledge import ImportProcessingError

    with pytest.raises(ImportProcessingError, match="media token"):
        await service.load_rich_content(
            SimpleNamespace(get_docx_blocks=AsyncMock(return_value=[block])),
            "docx",
            "doc",
            "Title",
        )


@pytest.mark.asyncio
async def test_image_unsupported_mime_is_reported(monkeypatch):
    blocks = [{"block_id": "image", "block_type": 27, "image": {"token": "tiff"}}]
    monkeypatch.setattr(
        service, "download_media", AsyncMock(return_value=(b"TIFF-data", "image/tiff"))
    )
    result = await service.load_rich_content(
        SimpleNamespace(get_docx_blocks=AsyncMock(return_value=blocks)),
        "docx",
        "doc",
        "Title",
    )
    assert result.warnings == ["unsupported_image:image"]
    assert "unsupported format" in result.content.decode()
    assert "data:image/tiff" not in result.content.decode()


@pytest.mark.asyncio
async def test_transformed_image_retains_incomplete_graph_failure(monkeypatch):
    from app.services.feishu_knowledge import ImportProcessingError

    blocks = [
        {
            "block_id": "image",
            "block_type": 27,
            "image": {"token": "image"},
            "children": ["missing"],
        }
    ]
    monkeypatch.setattr(
        service, "download_media", AsyncMock(return_value=(PNG, "image/png"))
    )
    with pytest.raises(ImportProcessingError, match="Incomplete"):
        await service.load_rich_content(
            SimpleNamespace(get_docx_blocks=AsyncMock(return_value=blocks)),
            "docx",
            "doc",
            "Title",
        )


@pytest.mark.asyncio
async def test_aggregate_downloads_are_bounded(monkeypatch):
    blocks = [
        {"block_id": "a", "block_type": 27, "image": {"token": "a"}},
        {"block_id": "b", "block_type": 27, "image": {"token": "b"}},
    ]
    monkeypatch.setattr(service, "content_limit_bytes", AsyncMock(return_value=6))
    monkeypatch.setattr(
        service, "download_media", AsyncMock(return_value=(b"1234", "image/png"))
    )
    with pytest.raises(FeishuAPIError, match="media exceeds"):
        await service.load_rich_content(
            SimpleNamespace(get_docx_blocks=AsyncMock(return_value=blocks)),
            "docx",
            "doc",
            "Title",
        )


@pytest.mark.asyncio
async def test_expanded_markdown_is_bounded(monkeypatch):
    monkeypatch.setattr(service, "content_limit_bytes", AsyncMock(return_value=20))
    blocks = [text_block("text", "body" * 10)]
    with pytest.raises(FeishuAPIError, match="content exceeds"):
        await service.load_rich_content(
            SimpleNamespace(get_docx_blocks=AsyncMock(return_value=blocks)),
            "docx",
            "doc",
            "Title",
        )


@pytest.mark.asyncio
async def test_office_attachment_preserves_embedded_media_without_allocating_assets(
    local_processor, tmp_path
):
    content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="png" ContentType="image/png"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    root_rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    document_rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.png"/>
</Relationships>"""
    document_xml = """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
  <w:body>
    <w:p><w:r><w:t>Attachment content</w:t></w:r></w:p>
    <w:p><w:r><w:drawing><wp:inline><wp:docPr id="1" name="Picture 1" descr="red pixel"/><a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic><pic:nvPicPr><pic:cNvPr id="0" name="sample.png" descr="red pixel"/></pic:nvPicPr><pic:blipFill><a:blip r:embed="rId1"/></pic:blipFill><pic:spPr/></pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>
  </w:body>
</w:document>"""
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("word/_rels/document.xml.rels", document_rels)
        archive.writestr("word/media/image1.png", PNG)

    text = await service.extract_attachment_text(payload.getvalue(), "embedded.docx")

    assert "Attachment content" in text
    assert "data:image/png;base64," in text
    assert "/api/v1/knowledge-bases/" not in text
    assert not list(tmp_path.rglob("*.docx"))
    assert not list(tmp_path.rglob("*.png"))


@pytest.mark.asyncio
async def test_attachment_storage_errors_are_not_partial_success_warnings(monkeypatch):
    blocks = [
        {
            "block_id": "file",
            "block_type": 23,
            "file": {"token": "notes", "name": "notes.txt"},
        }
    ]
    monkeypatch.setattr(
        service, "download_media", AsyncMock(return_value=(b"text", "text/plain"))
    )
    monkeypatch.setattr(
        service,
        "extract_attachment_text",
        AsyncMock(side_effect=OSError("storage unavailable")),
    )
    with pytest.raises(OSError, match="storage unavailable"):
        await service.load_rich_content(
            SimpleNamespace(get_docx_blocks=AsyncMock(return_value=blocks)),
            "docx",
            "doc",
            "Title",
        )
