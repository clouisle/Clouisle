import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import file_parse_cache
from app.services.file_parse_cache import (
    build_parser_hash,
    read_cached_file,
    write_cached_file,
)
from app.services.file_parser import ParsedFile


def _parsed_file() -> ParsedFile:
    return ParsedFile(
        filename="report.txt",
        content="report body",
        mime_type="text/plain",
        size=11,
    )


def test_parser_hash_is_order_independent_and_includes_parse_boundaries():
    config = SimpleNamespace(max_content_length=100, truncate_strategy="end")

    assert build_parser_hash({"type": "builtin", "name": "text"}, config) == (
        build_parser_hash({"name": "text", "type": "builtin"}, config)
    )
    assert build_parser_hash({"type": "builtin", "name": "text"}, config) != (
        build_parser_hash(
            {"type": "builtin", "name": "text"},
            SimpleNamespace(max_content_length=99, truncate_strategy="end"),
        )
    )


@pytest.mark.anyio
async def test_cache_round_trip_preserves_input(tmp_path, monkeypatch):
    upload_root = tmp_path / "uploads"
    file_path = upload_root / "report.txt"
    file_path.parent.mkdir()
    file_path.write_text("report body", encoding="utf-8")
    monkeypatch.setattr(file_parse_cache, "UPLOAD_ROOT", upload_root)
    monkeypatch.setattr(file_parse_cache, "CACHE_DIR", upload_root / ".cache")
    file_item = {"url": "/files/report.txt"}

    updated = await write_cached_file(
        file_item,
        _parsed_file(),
        file_path=file_path,
        url=file_item["url"],
        parser_hash="parser-v1",
    )

    assert "parse_cache" not in file_item
    assert updated["parse_cache"]["status"] == "success"
    assert (
        await read_cached_file(
            updated,
            file_path=file_path,
            url=file_item["url"],
            parser_hash="parser-v1",
        )
        == _parsed_file()
    )


@pytest.mark.anyio
async def test_cache_rejects_missing_stale_and_corrupt_entries(tmp_path, monkeypatch):
    upload_root = tmp_path / "uploads"
    file_path = upload_root / "report.txt"
    file_path.parent.mkdir()
    file_path.write_text("report body", encoding="utf-8")
    monkeypatch.setattr(file_parse_cache, "UPLOAD_ROOT", upload_root)
    monkeypatch.setattr(file_parse_cache, "CACHE_DIR", upload_root / ".cache")
    kwargs = {
        "file_path": file_path,
        "url": "/files/report.txt",
        "parser_hash": "parser-v1",
    }

    assert await read_cached_file({}, **kwargs) is None

    updated = await write_cached_file({}, _parsed_file(), **kwargs)
    assert (
        await read_cached_file(updated, **(kwargs | {"parser_hash": "parser-v2"}))
        is None
    )

    cache_key = updated["parse_cache"]["key"]
    cache_path = file_parse_cache._cache_path(cache_key)
    stale = updated | {
        "parse_cache": updated["parse_cache"] | {"source": {"size": 0, "mtime_ns": 0}}
    }
    assert await read_cached_file(stale, **kwargs) is None

    cache_path.unlink()
    assert await read_cached_file(updated, **kwargs) is None

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps({"parsed_file": {"filename": "missing-fields"}}))
    assert await read_cached_file(updated, **kwargs) is None


@pytest.mark.anyio
async def test_cache_write_propagates_storage_error(tmp_path, monkeypatch):
    upload_root = tmp_path / "uploads"
    file_path = upload_root / "report.txt"
    file_path.parent.mkdir()
    file_path.write_text("report body", encoding="utf-8")
    monkeypatch.setattr(file_parse_cache, "UPLOAD_ROOT", upload_root)
    monkeypatch.setattr(file_parse_cache, "CACHE_DIR", upload_root / ".cache")
    run_in_threadpool = AsyncMock(side_effect=[None, OSError("disk full")])
    monkeypatch.setattr(file_parse_cache, "run_in_threadpool", run_in_threadpool)

    with pytest.raises(OSError, match="disk full"):
        await write_cached_file(
            {},
            _parsed_file(),
            file_path=file_path,
            url="/files/report.txt",
            parser_hash="parser-v1",
        )
