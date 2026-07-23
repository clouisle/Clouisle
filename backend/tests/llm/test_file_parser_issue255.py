import tempfile
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.llm.tools import tool_registry
from app.llm.tools.builtin import file_parser


def test_url_helpers_and_truncation_strategies():
    url = "https://example.test/reports/My%20Report.PDF?download=1"
    assert file_parser.get_filename_from_url(url) == "My Report.PDF"
    assert file_parser.get_extension_from_url(url) == ".pdf"

    content = "abcdefghij"
    assert file_parser.truncate_content(content, 10) == content

    long_content = content * 10
    assert file_parser.truncate_content(long_content, 30, "start").endswith("hij")
    assert file_parser.truncate_content(long_content, 30, "middle").startswith("abc")
    assert file_parser.truncate_content(long_content, 30, "unknown").startswith("abc")


@pytest.mark.anyio
async def test_parse_files_handles_download_parse_and_validation(tmp_path, monkeypatch):
    requested = []
    responses = {
        "https://api.test/files/note.txt": b"plain text",
        "https://example.test/no-extension": b"binary",
        "https://example.test/empty.md": b"empty",
    }

    class Response:
        def __init__(self, url):
            self.content = responses[url]

        def raise_for_status(self):
            return None

    class Client:
        def __init__(self, **kwargs):
            assert kwargs == {"timeout": 60, "follow_redirects": True}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url):
            requested.append(url)
            return Response(url)

    converted = []

    class Converter:
        def convert(self, path):
            converted.append(path)
            assert tmp_path in Path(path).parents
            content = Path(path).read_bytes()
            if content == b"empty":
                return None
            return SimpleNamespace(
                text_content="0123456789" if content == b"plain text" else "parsed"
            )

    real_named_temporary_file = tempfile.NamedTemporaryFile
    monkeypatch.setattr(file_parser.httpx, "AsyncClient", Client)
    monkeypatch.setattr(file_parser, "MarkItDown", Converter)
    monkeypatch.setattr(file_parser.settings, "API_BASE_URL", "https://api.test/")
    monkeypatch.setattr(
        file_parser.tempfile,
        "NamedTemporaryFile",
        lambda **kwargs: real_named_temporary_file(dir=tmp_path, **kwargs),
    )

    result = await file_parser.parse_files(
        [
            "/files/note.txt",
            "https://example.test/archive.exe",
            "https://example.test/no-extension",
            "https://example.test/empty.md",
        ],
        max_content_length=8,
        truncate_strategy="middle",
    )

    assert requested == [
        "https://api.test/files/note.txt",
        "https://example.test/no-extension",
        "https://example.test/empty.md",
    ]
    assert len(converted) == 3
    assert "--- note.txt ---\n" in result
    assert "... [内容已截断] ..." in result
    assert "--- archive.exe ---\n[不支持的文件格式: .exe]" in result
    assert "--- no-extension ---\nparsed" in result
    assert result.endswith("--- empty.md ---\n")


@pytest.mark.anyio
async def test_parse_files_reports_http_and_parser_failures(monkeypatch):
    class Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url):
            request = httpx.Request("GET", url)
            if url.endswith("missing.pdf"):
                response = httpx.Response(404, request=request)
                raise httpx.HTTPStatusError(
                    "missing", request=request, response=response
                )
            raise RuntimeError("offline")

    monkeypatch.setattr(file_parser.httpx, "AsyncClient", Client)

    result = await file_parser.parse_files(
        [
            "https://example.test/missing.pdf",
            "https://example.test/broken.docx",
        ]
    )

    assert "--- missing.pdf ---\n[下载失败: HTTP 404]" in result
    assert "--- broken.docx ---\n[解析失败: offline]" in result
    assert await file_parser.parse_files([]) == "错误：未提供文件 URL"


def test_register_file_parser_tool():
    file_parser.register_file_parser_tools()
    tool = tool_registry.get_tool("markitdown")

    assert tool is not None
    assert tool.handler is file_parser.parse_files
    assert tool.parameters[0].items == {"type": "string"}
