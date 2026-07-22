from pathlib import Path

import pytest

from app.services import file_parse_cache
from app.services.file_parser import ParsedFile


@pytest.fixture
def cache_paths(tmp_path: Path, monkeypatch):
    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    monkeypatch.setattr(file_parse_cache, "UPLOAD_ROOT", upload_root)
    monkeypatch.setattr(
        file_parse_cache,
        "CACHE_DIR",
        upload_root / ".cache" / "file-parses",
    )
    return upload_root


@pytest.mark.anyio
async def test_cache_round_trip_preserves_input_and_parsed_file(cache_paths):
    file_path = cache_paths / "documents" / "report.txt"
    file_path.parent.mkdir()
    file_path.write_text("source", encoding="utf-8")
    file_item = {"filename": "report.txt"}
    parsed_file = ParsedFile(
        filename="report.txt",
        content="parsed content",
        mime_type="text/plain",
        size=6,
    )

    updated = await file_parse_cache.write_cached_file(
        file_item,
        parsed_file,
        file_path=file_path,
        url="/files/report.txt",
        parser_hash="parser-hash",
    )
    cached = await file_parse_cache.read_cached_file(
        updated,
        file_path=file_path,
        url="/files/report.txt",
        parser_hash="parser-hash",
    )

    assert cached == parsed_file
    assert file_item == {"filename": "report.txt"}
    assert updated["parse_cache"]["status"] == "success"


@pytest.mark.anyio
async def test_cache_misses_for_stale_metadata_and_malformed_payload(cache_paths):
    file_path = cache_paths / "report.txt"
    file_path.write_text("source", encoding="utf-8")
    parsed_file = ParsedFile(
        filename="report.txt",
        content="parsed content",
        mime_type="text/plain",
        size=6,
    )
    updated = await file_parse_cache.write_cached_file(
        {},
        parsed_file,
        file_path=file_path,
        url="/files/report.txt",
        parser_hash="parser-hash",
    )

    assert (
        await file_parse_cache.read_cached_file(
            updated,
            file_path=file_path,
            url="/files/report.txt",
            parser_hash="changed-parser",
        )
        is None
    )

    cache_key = updated["parse_cache"]["key"]
    file_parse_cache._cache_path(cache_key).write_text("not json", encoding="utf-8")
    assert (
        await file_parse_cache.read_cached_file(
            updated,
            file_path=file_path,
            url="/files/report.txt",
            parser_hash="parser-hash",
        )
        is None
    )


def test_cache_key_rejects_source_outside_upload_root(cache_paths, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("private", encoding="utf-8")

    with pytest.raises(ValueError):
        file_parse_cache.build_cache_key(
            url="/files/outside.txt",
            file_path=outside,
            parser_hash="parser-hash",
            source_signature=file_parse_cache.build_source_signature(outside),
        )
