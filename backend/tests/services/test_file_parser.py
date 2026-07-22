from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.file_parser import FileParseConfig, FileParserService, ParsedFile


@pytest.mark.parametrize(
    ("filename", "supported", "mime_type"),
    [
        ("REPORT.PDF", True, "application/pdf"),
        ("notes.md", True, "text/markdown"),
        ("page.htm", True, "text/html"),
        ("archive.zip", False, "application/zip"),
        ("no-extension", False, "application/octet-stream"),
    ],
)
def test_file_type_detection(filename, supported, mime_type):
    parser = FileParserService()

    assert parser.is_supported(filename) is supported
    assert parser.get_mime_type(filename) == mime_type


@pytest.mark.anyio
@pytest.mark.parametrize("extension", ["txt", "md", "csv", "json"])
async def test_parse_file_dispatches_text_formats_without_markitdown(
    extension, monkeypatch
):
    parser = FileParserService()
    monkeypatch.setattr(
        parser,
        "_get_markitdown",
        lambda: pytest.fail("MarkItDown should not parse text formats"),
    )

    result = await parser.parse_file(b"hello \xffworld", f"input.{extension}")

    assert result.content == "hello world"
    assert result.size == 12
    assert result.title is None
    assert result.truncated is False
    assert result.original_length is None


@pytest.mark.anyio
async def test_parse_file_dispatches_binary_format_and_cleans_up(monkeypatch):
    parser = FileParserService()
    conversion = {}

    def convert(path):
        conversion["path"] = path
        conversion["content"] = Path(path).read_bytes()
        return SimpleNamespace(text_content="parsed content", title="Report")

    monkeypatch.setattr(
        parser, "_get_markitdown", lambda: SimpleNamespace(convert=convert)
    )

    result = await parser.parse_file(b"pdf bytes", "REPORT.PDF")

    assert result.content == "parsed content"
    assert result.title == "Report"
    assert result.mime_type == "application/pdf"
    assert conversion["content"] == b"pdf bytes"
    assert Path(conversion["path"]).suffix == ".pdf"
    assert not Path(conversion["path"]).exists()


@pytest.mark.anyio
async def test_parse_file_rejects_unsupported_input():
    with pytest.raises(ValueError, match="^unsupported_file_type$"):
        await FileParserService().parse_file(b"data", "input.zip")


@pytest.mark.anyio
async def test_parse_file_cleans_up_when_parser_raises(monkeypatch):
    parser = FileParserService()
    conversion = {}

    def convert(path):
        conversion["path"] = path
        raise RuntimeError("broken parser")

    monkeypatch.setattr(
        parser, "_get_markitdown", lambda: SimpleNamespace(convert=convert)
    )

    with pytest.raises(RuntimeError, match="broken parser"):
        await parser.parse_file(b"bad pdf", "input.pdf")

    assert not Path(conversion["path"]).exists()


def test_truncate_content_strategies(monkeypatch):
    parser = FileParserService()
    monkeypatch.setattr(
        "app.services.file_parser.t",
        lambda key, **kwargs: f"<{key}:{kwargs.get('count', '')}>",
    )

    assert parser.truncate_content("short", 5) == ("short", False, 5)
    assert parser.truncate_content("abcdefghij", 4, "end") == (
        "abcd\n\n<truncation_marker:>",
        True,
        10,
    )
    assert parser.truncate_content("abcdefghij", 4, "start") == (
        "<truncation_marker:>\n\nghij",
        True,
        10,
    )
    assert parser.truncate_content("abcdefghij", 4, "middle") == (
        "ab\n\n<truncation_middle_marker:6>\n\nij",
        True,
        10,
    )
    assert parser.truncate_content("abcdefghij", 4, "invalid") == (
        "abcd\n\n<truncation_marker:>",
        True,
        10,
    )


@pytest.mark.anyio
async def test_parse_file_applies_configured_truncation(monkeypatch):
    monkeypatch.setattr(
        "app.services.file_parser.t", lambda key, **kwargs: "<truncated>"
    )

    result = await FileParserService().parse_file(
        b"abcdefghij",
        "input.txt",
        FileParseConfig(max_content_length=4, truncate_strategy="start"),
    )

    assert result.content == "<truncated>\n\nghij"
    assert result.truncated is True
    assert result.original_length == 10


def test_format_files_for_prompt_handles_empty_single_and_multiple(monkeypatch):
    parser = FileParserService()
    monkeypatch.setattr(
        "app.services.file_parser.t",
        lambda key, **kwargs: (
            f"<{key}:{','.join(str(value) for value in kwargs.values() if value is not None)}>"
        ),
    )
    first = ParsedFile(
        filename="a.txt",
        content="alpha",
        mime_type="text/plain",
        size=5,
        truncated=True,
        original_length=20,
    )
    second = ParsedFile(
        filename="b.txt", content="beta", mime_type="text/plain", size=4
    )

    assert parser.format_files_for_prompt([]) == ""
    assert parser.format_files_for_prompt([first]) == (
        "<file_header:a.txt><file_header_truncated_suffix:20>\n\nalpha"
    )
    assert parser.format_files_for_prompt([first, second], separator=" | ") == (
        "<file_header_indexed:1,a.txt><file_header_truncated_suffix:20>\n\nalpha"
        " | <file_header_indexed:2,b.txt>\n\nbeta"
    )
