from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints.chat_tools import build_file_content_for_context
from app.services.file_parse_cache import (
    build_parser_hash,
    read_cached_file,
    write_cached_file,
)
from app.services.file_parser import FileParseConfig, FileParserService, ParsedFile


def _agent():
    return SimpleNamespace(
        id=uuid4(),
        enable_attachments=True,
        attachment_config={
            "parser": {"type": "builtin", "name": "markitdown"},
            "max_content_length": 100000,
            "truncate_strategy": "end",
        },
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

    assert content == ""
    assert updated_file_urls is None


def _configure_cache(tmp_path, monkeypatch):
    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    file_path = upload_root / "report.txt"
    file_path.write_text("source", encoding="utf-8")
    monkeypatch.setattr("app.services.file_parse_cache.UPLOAD_ROOT", upload_root)
    monkeypatch.setattr(
        "app.services.file_parse_cache.CACHE_DIR", upload_root / ".cache"
    )
    return file_path


@pytest.mark.anyio
async def test_file_parse_cache_miss_for_missing_or_stale_metadata(
    tmp_path, monkeypatch
):
    file_path = _configure_cache(tmp_path, monkeypatch)
    parser_hash = build_parser_hash(
        {"name": "markitdown"}, FileParseConfig(max_content_length=10)
    )

    assert (
        await read_cached_file(
            {}, file_path=file_path, url="/report.txt", parser_hash=parser_hash
        )
        is None
    )
    assert (
        await read_cached_file(
            {
                "parse_cache": {
                    "status": "success",
                    "key": "stale",
                    "parser_hash": parser_hash,
                }
            },
            file_path=file_path,
            url="/report.txt",
            parser_hash=parser_hash,
        )
        is None
    )


@pytest.mark.anyio
async def test_file_parse_cache_store_and_hit(tmp_path, monkeypatch):
    file_path = _configure_cache(tmp_path, monkeypatch)
    parser_hash = build_parser_hash({"name": "markitdown"}, FileParseConfig())
    original = {"filename": "report.txt", "url": "/report.txt"}
    parsed = ParsedFile(
        filename="report.txt", content="parsed", mime_type="text/plain", size=6
    )

    updated = await write_cached_file(
        original,
        parsed,
        file_path=file_path,
        url="/report.txt",
        parser_hash=parser_hash,
    )

    assert "parse_cache" not in original
    assert updated["parse_cache"]["status"] == "success"
    assert (
        await read_cached_file(
            updated,
            file_path=file_path,
            url="/report.txt",
            parser_hash=parser_hash,
        )
        == parsed
    )


@pytest.mark.anyio
async def test_file_parse_cache_corrupt_payload_is_miss(tmp_path, monkeypatch):
    file_path = _configure_cache(tmp_path, monkeypatch)
    parser_hash = build_parser_hash({"name": "markitdown"}, FileParseConfig())
    parsed = ParsedFile(
        filename="report.txt", content="parsed", mime_type="text/plain", size=6
    )
    metadata = await write_cached_file(
        {}, parsed, file_path=file_path, url="/report.txt", parser_hash=parser_hash
    )
    cache_key = metadata["parse_cache"]["key"]
    cache_path = tmp_path / "uploads" / ".cache" / cache_key[:2] / f"{cache_key}.json"
    cache_path.write_text("not-json", encoding="utf-8")

    assert (
        await read_cached_file(
            metadata,
            file_path=file_path,
            url="/report.txt",
            parser_hash=parser_hash,
        )
        is None
    )


@pytest.mark.anyio
async def test_file_parse_cache_store_propagates_storage_error(tmp_path, monkeypatch):
    file_path = _configure_cache(tmp_path, monkeypatch)
    parsed = ParsedFile(
        filename="report.txt", content="parsed", mime_type="text/plain", size=6
    )

    async def fail_storage(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("app.services.file_parse_cache.run_in_threadpool", fail_storage)

    with pytest.raises(OSError, match="disk full"):
        await write_cached_file(
            {},
            parsed,
            file_path=file_path,
            url="/report.txt",
            parser_hash="parser-hash",
        )


def test_parser_hash_changes_at_config_boundaries():
    parser = {"name": "markitdown"}

    assert build_parser_hash(parser, FileParseConfig(max_content_length=0)) != (
        build_parser_hash(parser, FileParseConfig(max_content_length=1))
    )
    assert build_parser_hash(parser, FileParseConfig(truncate_strategy="end")) != (
        build_parser_hash(parser, FileParseConfig(truncate_strategy="start"))
    )
