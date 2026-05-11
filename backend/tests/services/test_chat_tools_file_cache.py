from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.v1.endpoints.chat_tools import build_file_content_for_context


def _agent():
    return SimpleNamespace(
        id=uuid4(),
        enable_file_upload=True,
        file_upload_config={
            "parser": {"type": "builtin", "name": "markitdown"},
            "max_content_length": 100000,
            "truncate_strategy": "end",
        },
    )


@pytest.mark.anyio
async def test_builtin_file_parser_writes_cache_metadata(tmp_path, monkeypatch):
    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    file_path = upload_root / "documents" / "2026" / "05" / "report.txt"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("report body", encoding="utf-8")

    monkeypatch.setattr("app.api.v1.endpoints.upload.UPLOAD_ROOT", upload_root)
    monkeypatch.setattr("app.services.file_parse_cache.UPLOAD_ROOT", upload_root)
    monkeypatch.setattr(
        "app.services.file_parse_cache.CACHE_DIR",
        upload_root / ".cache" / "file-parses",
    )

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

    assert "report body" in content
    assert updated_file_urls is not None
    assert updated_file_urls[0]["parse_cache"]["status"] == "success"
    assert updated_file_urls[0]["parse_cache"]["key"]


@pytest.mark.anyio
async def test_builtin_file_parser_reuses_cache_without_reparse(tmp_path, monkeypatch):
    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    file_path = upload_root / "documents" / "2026" / "05" / "report.txt"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("report body", encoding="utf-8")

    monkeypatch.setattr("app.api.v1.endpoints.upload.UPLOAD_ROOT", upload_root)
    monkeypatch.setattr("app.services.file_parse_cache.UPLOAD_ROOT", upload_root)
    monkeypatch.setattr(
        "app.services.file_parse_cache.CACHE_DIR",
        upload_root / ".cache" / "file-parses",
    )

    file_urls = [
        {
            "filename": "report.txt",
            "url": "/api/v1/upload/files/documents/2026/05/report.txt",
            "size": 11,
            "mime_type": "text/plain",
        }
    ]
    _, updated_file_urls = await build_file_content_for_context(
        agent=_agent(),
        file_urls=file_urls,
        legacy_files=None,
        user_locale="en",
        tool_timeouts=None,
        user=None,
    )

    async def fail_parse_file(*args, **kwargs):
        raise AssertionError("parser should not run when cache is valid")

    monkeypatch.setattr(
        "app.services.file_parser.file_parser_service.parse_file",
        fail_parse_file,
    )

    content, second_updated_file_urls = await build_file_content_for_context(
        agent=_agent(),
        file_urls=updated_file_urls,
        legacy_files=None,
        user_locale="en",
        tool_timeouts=None,
        user=None,
    )

    assert "report body" in content
    assert second_updated_file_urls == updated_file_urls
