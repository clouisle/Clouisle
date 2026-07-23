import base64
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.knowledge_base import DocumentType
from app.services.document_processor import DocumentProcessor


document_processor_module = importlib.import_module("app.services.document_processor")


@pytest.fixture
def processor(tmp_path: Path) -> DocumentProcessor:
    return DocumentProcessor(str(tmp_path / "uploads" / "documents"))


@pytest.mark.parametrize(
    ("filename", "content_type", "expected"),
    [
        ("report.unknown", "application/pdf", "pdf"),
        ("REPORT.MARKDOWN", None, "markdown"),
        ("report.unknown", None, None),
    ],
)
def test_document_type_detection(processor, filename, content_type, expected):
    assert processor.get_document_type(filename, content_type) == expected


def test_paths_and_media_resource_cleanup(processor):
    kb_id = uuid4()
    document_id = uuid4()

    short_path = processor.get_storage_path(kb_id, "../report.txt")
    long_path = processor.get_storage_path(kb_id, f"{'x' * 60}.pdf")
    assert short_path.endswith("_report.txt")
    assert Path(long_path).name.endswith(".pdf")
    assert "x" * 60 not in long_path
    assert processor._storage_key(f"s3://bucket/{short_path}") == short_path
    assert processor._storage_key(short_path) == short_path

    local_path = processor._storage_root() / short_path
    assert processor._storage_key(str(local_path)) == short_path
    for invalid in (
        str(processor._storage_root()),
        str(processor._storage_root() / ".."),
    ):
        with pytest.raises(ValueError, match="validation_error"):
            processor._storage_key(invalid)
    with pytest.raises(ValueError, match="validation_error"):
        processor._resolve_storage_path("..", "escape.txt")
    for invalid in ("", ".", ".."):
        with pytest.raises(ValueError, match="validation_error"):
            processor._sanitize_filename(invalid)

    asset = processor._save_media_asset(
        kb_id=kb_id,
        document_id=document_id,
        content_type="image/x-custom",
        content=b"asset",
    )
    assert asset["filename"].endswith(".bin")
    processor._save_media_asset(
        kb_id=kb_id,
        document_id=document_id,
        content_type="image/x-custom",
        content=b"asset",
    )
    processor.delete_media_assets(kb_id, document_id)
    assert not Path(asset["path"]).exists()


def test_media_replacement_ignores_unsupported_and_invalid_data(processor):
    invalid = "data:image/png;base64,not-valid=="
    unsupported = "data:image/bmp;base64," + base64.b64encode(b"bmp").decode()
    text = f"{invalid} {unsupported}"

    assert processor.replace_embedded_media_data_uris(
        text, kb_id=uuid4(), document_id=uuid4()
    ) == (text, [])


@pytest.mark.asyncio
async def test_storage_operations_cover_missing_and_existing_files(
    processor, monkeypatch
):
    storage = SimpleNamespace(
        save=AsyncMock(),
        read=AsyncMock(return_value=b"content"),
        exists=AsyncMock(side_effect=[False, True]),
        delete=AsyncMock(),
    )
    monkeypatch.setattr(
        document_processor_module,
        "get_upload_storage_backend",
        AsyncMock(return_value=storage),
    )

    assert await processor.save_file(b"content", "documents/file.txt") == 7
    assert await processor.read_file("documents/file.txt") == b"content"
    assert await processor.delete_file("documents/missing.txt") is False
    assert await processor.delete_file("documents/file.txt") is True
    storage.delete.assert_awaited_once_with("documents/file.txt")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("doc_type", "content", "expected"),
    [
        (DocumentType.TXT.value, b" a\r\n\r\n b\x00 ", "a\nb"),
        (DocumentType.CSV.value, b"name,value\na,1", "name | value\na | 1"),
        (
            DocumentType.JSON.value,
            b'{"user":{"name":"Ada"},"items":[1,true]}',
            "user.name: Ada\nitems[0]: 1\nitems[1]: True",
        ),
        ("unknown", b"raw\xff text", "raw text"),
    ],
)
async def test_extract_text_parsing_branches(
    processor, monkeypatch, doc_type, content, expected
):
    monkeypatch.setattr(processor, "read_file", AsyncMock(return_value=content))

    text, metadata = await processor.extract_text("documents/input.data", doc_type)

    assert text == expected
    assert metadata == {
        "file_size": len(content),
        "doc_type": doc_type,
        "char_count": len(expected),
    }


@pytest.mark.asyncio
async def test_extract_text_uses_temporary_parser_file_and_removes_it(
    processor, monkeypatch
):
    parser_call = {}

    def parse(path, doc_type):
        parser_call["path"] = path
        parser_call["content"] = Path(path).read_bytes()
        parser_call["type"] = doc_type
        return " parsed ", {"format": "markdown", "title": "Report"}

    monkeypatch.setattr(processor, "read_file", AsyncMock(return_value=b"binary"))
    monkeypatch.setattr(processor, "_extract_with_markitdown", parse)

    text, metadata = await processor.extract_text(
        "documents/report.pdf", DocumentType.PDF.value
    )

    assert text == "parsed"
    assert metadata["title"] == "Report"
    assert parser_call["content"] == b"binary"
    assert parser_call["type"] == DocumentType.PDF.value
    assert not Path(parser_call["path"]).exists()


@pytest.mark.asyncio
async def test_extract_text_normalizes_parser_errors(processor, monkeypatch):
    monkeypatch.setattr(processor, "read_file", AsyncMock(return_value=b"bad json"))

    with pytest.raises(ValueError, match="document_processing_failed_generic"):
        await processor.extract_text("documents/input.json", DocumentType.JSON.value)


def test_markitdown_parser_success_and_missing_dependency(processor, monkeypatch):
    class FakeMarkItDown:
        def convert(self, path, **kwargs):
            assert kwargs == {"keep_data_uris": True}
            return SimpleNamespace(text_content="body", title="Title")

    with monkeypatch.context() as scoped:
        scoped.setitem(
            sys.modules, "markitdown", SimpleNamespace(MarkItDown=FakeMarkItDown)
        )
        assert processor._extract_with_markitdown("input.pdf", "pdf") == (
            "body",
            {"format": "markdown", "title": "Title"},
        )

    with monkeypatch.context() as scoped:
        scoped.setitem(sys.modules, "markitdown", None)
        with pytest.raises(ValueError, match="document_processing_failed_generic"):
            processor._extract_with_markitdown("input.pdf", "pdf")


@pytest.mark.asyncio
async def test_fetch_url_content_with_markitdown(processor, monkeypatch):
    class FakeMarkItDown:
        def convert(self, url):
            return SimpleNamespace(text_content="  fetched  ", title="Page")

    monkeypatch.setitem(
        sys.modules, "markitdown", SimpleNamespace(MarkItDown=FakeMarkItDown)
    )

    text, metadata = await processor.fetch_url_content("https://example.test")

    assert text == "fetched"
    assert metadata == {
        "source_url": "https://example.test",
        "format": "markdown",
        "title": "Page",
        "char_count": 7,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content_type", "content", "response_text", "expected"),
    [
        ("application/json; charset=utf-8", b'{"ok":true}', "unused", "ok: True"),
        ("text/html", b"unused", "  page text  ", "page text"),
    ],
)
async def test_fetch_url_content_http_fallback(
    processor, monkeypatch, content_type, content, response_text, expected
):
    response = SimpleNamespace(
        headers={"content-type": content_type},
        content=content,
        text=response_text,
        raise_for_status=lambda: None,
    )
    client = SimpleNamespace(get=AsyncMock(return_value=response))

    class ClientContext:
        async def __aenter__(self):
            return client

        async def __aexit__(self, *args):
            return None

    with monkeypatch.context() as scoped:
        scoped.setitem(sys.modules, "markitdown", None)
        scoped.setattr("httpx.AsyncClient", lambda **kwargs: ClientContext())
        text, metadata = await processor.fetch_url_content("https://example.test")

    assert text == expected
    assert metadata["content_type"] == content_type
    assert metadata["char_count"] == len(expected)
