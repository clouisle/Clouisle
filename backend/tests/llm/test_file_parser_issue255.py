"""markitdown builtin: scoped Assets, bounded previews, and URL validation."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.llm.tools import tool_registry
from app.llm.tools.builtin import file_parser
from app.schemas.response import BusinessError
from app.services.asset_url_import import ExternalDocument, InternalDocument
from app.services.citations import stable_citation_id
from app.services.file_parser import file_parser_service as document_parser_service


def _document(segments, *, total_lines=2, eof=True, filename="notes.md"):
    return {
        "filename": filename,
        "start_line": 1,
        "total_lines": total_lines,
        "segments": segments,
        "next_cursor": None if eof else "cursor",
        "eof": eof,
    }


def _patch_scope(monkeypatch, scope_id=None):
    from app.services import asset_url_import

    scope_id = scope_id or uuid4()
    resolve = Mock(return_value=(SimpleNamespace(), scope_id))
    monkeypatch.setattr(asset_url_import, "resolve_document_scope", resolve)
    return resolve


def test_url_helpers():
    url = "https://example.test/reports/My%20Report.PDF?download=1"
    assert file_parser.get_filename_from_url(url) == "My Report.PDF"
    assert file_parser.get_extension_from_url(url) == ".pdf"


@pytest.mark.anyio
async def test_parse_files_returns_scoped_previews_for_external_documents(
    monkeypatch,
):
    from app.services import asset_url_import

    _patch_scope(monkeypatch)
    load = AsyncMock(
        return_value=ExternalDocument(
            content=b"pdf-bytes",
            content_type="application/pdf",
            filename="report.pdf",
            url="https://example.test/report.pdf",
            final_url="https://example.test/report.pdf",
        )
    )
    monkeypatch.setattr(asset_url_import, "load_url_document", load)
    asset_id = uuid4()
    persist = AsyncMock(
        return_value=SimpleNamespace(
            asset=SimpleNamespace(id=asset_id, content_type="text/markdown"),
            ref="beef",
        )
    )
    monkeypatch.setattr(asset_url_import, "persist_scoped_document", persist)
    extract = AsyncMock(
        return_value=SimpleNamespace(
            text="Title\nbody", title="Report", mime_type="application/pdf", size=9
        )
    )
    monkeypatch.setattr(document_parser_service, "extract_file", extract)
    monkeypatch.setattr(
        file_parser,
        "_read_preview",
        AsyncMock(
            return_value=_document(
                [
                    {"line": 1, "text": "Title", "continuation": False},
                    {"line": 2, "text": "body", "continuation": False},
                ],
                filename="report.md",
            )
        ),
    )

    result = await file_parser.parse_files(
        ["https://example.test/report.pdf"],
        agent=None,
        user=None,
        conversation_id=uuid4(),
    )

    assert result["kind"] == "document.files"
    assert result["success"] is True
    entry = result["files"][0]
    assert entry["ref"] == "beef"
    assert entry["filename"] == "report.md"
    assert entry["title"] == "Report"
    assert entry["citation_id"] == stable_citation_id("asset", asset_id)
    assert entry["segments"][0]["text"] == "Title"
    assert entry["total_lines"] == 2
    assert entry["eof"] is True
    persist.assert_awaited_once()
    assert persist.await_args.kwargs["content_type"] == "text/markdown"
    assert persist.await_args.args[0] == b"Title\nbody"
    assert persist.await_args.kwargs["provenance"]["original_filename"] == (
        "report.pdf"
    )
    extract.assert_awaited_once()


@pytest.mark.anyio
async def test_parse_files_reuses_internal_asset_without_network_or_persist(
    monkeypatch,
):
    from app.services import asset_url_import

    _patch_scope(monkeypatch)
    asset = SimpleNamespace(
        id=uuid4(),
        display_filename="uploaded.md",
        content_type="text/markdown",
        size=12,
        provenance={"title": "Original"},
    )
    load = AsyncMock(
        return_value=InternalDocument(
            asset=asset,
            ref="cafe",
            url="/api/v1/upload/files/agent-attachments/2026/10/uploaded.md",
        )
    )
    monkeypatch.setattr(asset_url_import, "load_url_document", load)
    persist = AsyncMock()
    monkeypatch.setattr(asset_url_import, "persist_scoped_document", persist)
    monkeypatch.setattr(
        file_parser,
        "_read_preview",
        AsyncMock(
            return_value=_document(
                [{"line": 1, "text": "Original", "continuation": False}],
                total_lines=1,
                filename="uploaded.md",
            )
        ),
    )

    result = await file_parser.parse_files(
        ["/api/v1/upload/files/agent-attachments/2026/10/uploaded.md"],
        agent=None,
        user=None,
        workflow_run_id=uuid4(),
    )

    entry = result["files"][0]
    assert entry["ref"] == "cafe"
    assert entry["title"] == "Original"
    assert entry["url"] == (
        "/api/v1/upload/files/agent-attachments/2026/10/uploaded.md"
    )
    persist.assert_not_awaited()


@pytest.mark.anyio
async def test_parse_files_rejects_unsupported_extension_before_io(monkeypatch):
    from app.services import asset_url_import

    _patch_scope(monkeypatch)
    load = AsyncMock()
    monkeypatch.setattr(asset_url_import, "load_url_document", load)
    monkeypatch.setattr(file_parser, "t", lambda key, **kwargs: key)

    result = await file_parser.parse_files(
        ["https://example.test/archive.exe"], user=None, conversation_id=uuid4()
    )

    entry = result["files"][0]
    assert entry["success"] is False
    assert entry["error"] == "unsupported_file_type"
    assert result["success"] is False
    load.assert_not_awaited()


@pytest.mark.anyio
async def test_parse_files_reports_business_and_parser_errors(monkeypatch):
    from app.services import asset_url_import

    _patch_scope(monkeypatch)
    load = AsyncMock(
        side_effect=BusinessError(msg_key="fetch_webpage_http_error", status_code=404)
    )
    monkeypatch.setattr(asset_url_import, "load_url_document", load)

    result = await file_parser.parse_files(
        ["https://example.test/missing.pdf"], user=None, conversation_id=uuid4()
    )
    entry = result["files"][0]
    assert entry["success"] is False
    assert "404" in entry["error"]


@pytest.mark.anyio
async def test_parse_files_requires_scope_and_urls(monkeypatch):
    from app.services import asset_url_import

    monkeypatch.setattr(
        asset_url_import,
        "resolve_document_scope",
        Mock(side_effect=BusinessError(msg_key="validation_error")),
    )

    missing_scope = await file_parser.parse_files(
        ["https://example.test/a.pdf"], user=None
    )
    assert missing_scope["success"] is False
    assert missing_scope["files"] == []

    empty = await file_parser.parse_files([])
    assert empty["success"] is False

    invalid = await file_parser.parse_files(["", 3])
    assert invalid["success"] is False


@pytest.mark.anyio
async def test_parse_files_omits_preview_when_call_budget_is_exhausted(monkeypatch):
    from app.services import asset_url_import

    _patch_scope(monkeypatch)
    monkeypatch.setattr(file_parser, "MAX_CALL_PREVIEW_BYTES", 1)
    monkeypatch.setattr(
        asset_url_import,
        "load_url_document",
        AsyncMock(
            return_value=ExternalDocument(
                content=b"text",
                content_type="text/plain",
                filename="a.txt",
                url="https://example.test/a.txt",
                final_url="https://example.test/a.txt",
            )
        ),
    )
    monkeypatch.setattr(
        asset_url_import,
        "persist_scoped_document",
        AsyncMock(
            return_value=SimpleNamespace(asset=SimpleNamespace(id=uuid4()), ref="beef")
        ),
    )
    monkeypatch.setattr(
        document_parser_service,
        "extract_file",
        AsyncMock(
            return_value=SimpleNamespace(
                text="line", title=None, mime_type="text/plain", size=4
            )
        ),
    )
    preview = AsyncMock(
        return_value=_document(
            [{"line": 1, "text": "line", "continuation": False}], total_lines=1
        )
    )
    monkeypatch.setattr(file_parser, "_read_preview", preview)

    result = await file_parser.parse_files(
        ["https://example.test/a.txt", "https://example.test/b.txt"],
        user=None,
        conversation_id=uuid4(),
    )

    first, second = result["files"]
    assert first["preview_omitted"] is True
    assert "segments" not in first
    assert first["ref"] == "beef"
    assert second["preview_omitted"] is True
    assert "segments" not in second
    assert second["ref"] == "beef"


@pytest.mark.anyio
async def test_parse_files_rejects_too_many_urls(monkeypatch):
    _patch_scope(monkeypatch)

    result = await file_parser.parse_files(
        [f"https://example.test/{index}.txt" for index in range(11)],
        user=None,
        conversation_id=uuid4(),
    )

    assert result["success"] is False
    assert result["files"] == []
    assert result["detail"]


def test_register_file_parser_tool():
    file_parser.register_file_parser_tools()
    tool = tool_registry.get_tool("markitdown")

    assert tool is not None
    assert tool.handler is file_parser.parse_files
    assert [parameter.name for parameter in tool.parameters] == ["files_url"]
    assert tool.parameters[0].items == {"type": "string"}
