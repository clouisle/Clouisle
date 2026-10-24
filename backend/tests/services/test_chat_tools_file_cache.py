import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints.chat_tools import build_file_content_for_context
from app.services.file_parser import FileParserService


def _agent():
    return SimpleNamespace(
        id=uuid4(),
        enable_attachments=True,
        attachment_config={"parser": {"type": "builtin", "name": "markitdown"}},
    )


@pytest.mark.parametrize("filename", ["report.PDF", "notes.md", "data.csv", "page.htm"])
def test_file_parser_recognizes_supported_formats(filename):
    service = FileParserService()

    assert service.is_supported(filename)
    assert service.get_mime_type(filename) != "application/octet-stream"


@pytest.mark.anyio
async def test_file_parser_rejects_unsupported_format():
    service = FileParserService()

    assert not service.is_supported("archive.zip")
    with pytest.raises(ValueError, match="unsupported_file_type"):
        await service.parse_file(b"data", "archive.zip")


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("filename", "content"),
    [("notes.txt", b"hello"), ("notes.md", b"hello"), ("data.csv", b"hello")],
)
async def test_file_parser_reads_text_formats_without_markitdown(
    filename, content, monkeypatch
):
    service = FileParserService()
    monkeypatch.setattr(
        service,
        "_get_markitdown",
        lambda: pytest.fail("MarkItDown should not parse text formats"),
    )

    parsed = await service.parse_file(content, filename)

    assert parsed.content == "hello"
    assert parsed.size == len(content)
    assert parsed.title is None


@pytest.mark.anyio
async def test_file_parser_uses_markitdown_and_removes_temporary_file(monkeypatch):
    service = FileParserService()
    converter = MagicMock()
    converter.convert.return_value = SimpleNamespace(
        text_content="converted", title="Title"
    )
    monkeypatch.setattr(service, "_get_markitdown", lambda: converter)

    parsed = await service.parse_file(b"pdf", "report.pdf")

    temp_path = Path(converter.convert.call_args.args[0])
    assert parsed.content == "converted"
    assert parsed.title == "Title"
    assert not temp_path.exists()


@pytest.mark.parametrize(
    ("strategy", "expected"),
    [
        ("end", "abcd\n\n[truncated]"),
        ("start", "[truncated]\n\nghij"),
        ("middle", "ab\n\n[6 omitted]\n\nij"),
    ],
)
def test_file_parser_truncation_strategies(strategy, expected, monkeypatch):
    markers = {
        "truncation_marker": "[truncated]",
        "truncation_middle_marker": "[6 omitted]",
    }
    monkeypatch.setattr(
        "app.services.file_parser.t", lambda key, **kwargs: markers[key]
    )

    assert FileParserService().truncate_content("abcdefghij", 4, strategy) == (
        expected,
        True,
        10,
    )


def test_file_parser_does_not_truncate_at_limit():
    assert FileParserService().truncate_content("abcd", 4) == ("abcd", False, 4)


@pytest.mark.anyio
async def test_asset_file_urls_are_not_automatically_parsed():
    content, updated_file_urls = await build_file_content_for_context(
        agent=_agent(),
        file_urls=[
            {
                "filename": "report.txt",
                "url": "/api/v1/upload/files/documents/2026/05/report.txt",
                "size": 11,
                "mime_type": "text/plain",
            }
        ],
        legacy_files=None,
        user_locale="en",
        tool_timeouts=None,
        user=None,
    )

    documents = json.loads(content)["documents"]
    assert documents[0]["filename"] == "report.txt"
    assert documents[0]["mime_type"] == "text/plain"
    assert documents[0]["size"] == 11
    assert updated_file_urls is None
