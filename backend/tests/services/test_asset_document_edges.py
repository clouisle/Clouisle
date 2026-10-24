"""Branch coverage for the complete document representation boundary."""

import asyncio
import builtins
import hashlib
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from botocore.exceptions import ClientError
from tortoise.context import TortoiseContext

from app.models.asset import Asset, AssetSource, AssetStatus
from app.services import asset_document as document_module
from app.services.asset_document import (
    _build_line_index,
    _clip,
    _decode_bytes,
    _decode_cursor,
    _decode_window,
    _derived_filename,
    _drop_incomplete_utf8,
    _encode_cursor,
    _fit_segment_text,
    _json_size,
    _line_start,
    _read_segments,
    _shrink_snippet,
    _utf8_prefix,
    _validate_offsets,
    read_document,
    search_document,
)
from app.services.file_parser import FileParserService, ParsedFile, file_parser_service
from app.services.upload_storage import (
    LocalUploadStorage,
    ObjectStorageConfig,
    ObjectUploadStorage,
    UploadStorageBackend,
)


@pytest_asyncio.fixture
async def database():
    async with TortoiseContext() as context:
        await context.init(
            db_url="sqlite://:memory:", modules={"models": ["app.models"]}
        )
        await context.generate_schemas()
        yield


@pytest.fixture
def storage(tmp_path):
    return LocalUploadStorage(tmp_path)


async def create_asset(
    storage,
    content,
    *,
    filename="notes.txt",
    content_type="text/plain",
    source=AssetSource.UPLOAD,
    status=AssetStatus.AVAILABLE,
    expires_at=None,
    parent_id=None,
):
    key = f"agent-attachments/2026/10/{uuid4()}-{filename}"
    await storage.save(key, content, content_type)
    return await Asset.create(
        id=uuid4(),
        storage_key=key,
        original_filename=filename,
        display_filename=filename,
        content_type=content_type,
        size=len(content),
        checksum=hashlib.sha256(content).hexdigest(),
        source=source,
        status=status,
        expires_at=expires_at,
        parent_id=parent_id,
    )


class _RangeStorage:
    def __init__(self, *chunks):
        self.chunks = list(chunks)

    async def read_range(self, key, start, length):
        return self.chunks.pop(0) if self.chunks else b""


# ---------------------------------------------------------------- pure helpers


def test_utf8_helpers_cover_boundaries():
    assert _utf8_prefix(b"abc", 10) == b"abc"
    assert _utf8_prefix(b"a\xe4\xbd\xa0", 2) == b"a"
    assert _utf8_prefix("你".encode(), 1) == "你".encode()
    assert _drop_incomplete_utf8(b"ok") == b"ok"
    assert _drop_incomplete_utf8("你".encode()[:2]) == b""
    with pytest.raises(RuntimeError, match="not valid UTF-8"):
        _drop_incomplete_utf8(b"\xff")
    with pytest.raises(RuntimeError, match="not valid UTF-8"):
        _decode_bytes(b"\xff")


def test_decode_window_trims_boundaries_and_rejects_corruption():
    assert _decode_window(b"\x80abc", drop_leading=True, drop_trailing=False) == "abc"
    assert (
        _decode_window("你".encode()[:2], drop_leading=False, drop_trailing=True) == ""
    )
    assert _decode_window(b"", drop_leading=True, drop_trailing=True) == ""
    with pytest.raises(RuntimeError, match="not valid UTF-8"):
        _decode_window(b"a\xffb", drop_leading=False, drop_trailing=False)


def test_clip_and_fit_segment_branches():
    assert _clip("abcdef", tail=False, limit=3) == ("abc", True)
    assert _clip("abcdef", tail=True, limit=3) == ("def", True)
    assert _clip("abc", tail=False, limit=5) == ("abc", False)
    assert _fit_segment_text("", 1, 10) == ("", True)
    assert _fit_segment_text("abc", 1, 0) == ("", False)
    assert _fit_segment_text("abc", 1, 10_000) == ("abc", True)
    clipped, complete = _fit_segment_text("x" * 100, 1, 60)
    assert clipped and not complete
    assert _json_size({"a": 1}) > 0


def test_line_index_and_derived_filename():
    data = ("x\n" * 600).encode()
    total_lines, offsets = _build_line_index(data)
    assert total_lines == 601
    assert offsets[0] == [1, 0]
    assert offsets[1] == [257, 512]
    assert _derived_filename(SimpleNamespace(display_filename="a.pdf")) == "a.txt"
    assert _derived_filename(SimpleNamespace(display_filename="a")) == "a.txt"
    long_name = "x" * 600
    assert len(_derived_filename(SimpleNamespace(display_filename=long_name))) <= 499


@pytest.mark.parametrize(
    ("raw", "total", "size"),
    [
        (None, 1, 1),
        ([], 1, 1),
        ([[1]], 1, 1),
        ([[1, "x"]], 1, 1),
        ([[2, 0]], 1, 1),
        ([[1, 0], [1, 1]], 2, 2),
        ([[1, 0], [2, 1]], 2, 0),
        ([[1, 0]], 0, 1),
    ],
)
def test_validate_offsets_rejects_corruption(raw, total, size):
    with pytest.raises(ValueError, match="asset_document_representation_invalid"):
        _validate_offsets(raw, total, size)


def _cursor_payload(**overrides):
    payload = {
        "v": 1,
        "k": "read",
        "r": "a" * 64,
        "p": "00000000-0000-0000-0000-000000000001",
        "rv": "b" * 64,
        "o": 0,
        "l": 1,
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    ("cursor", "message"),
    [
        (None, "asset_document_invalid_cursor"),
        ("", "asset_document_invalid_cursor"),
        ("x" * 3000, "asset_document_invalid_cursor"),
        ("!!!!", "asset_document_invalid_cursor"),
        (json.dumps([1]), "asset_document_invalid_cursor"),
        (_encode_cursor(_cursor_payload(v=2)), "asset_document_invalid_cursor"),
        (_encode_cursor(_cursor_payload(o=True)), "asset_document_invalid_cursor"),
        (_encode_cursor(_cursor_payload(o=-1)), "asset_document_invalid_cursor"),
        (_encode_cursor(_cursor_payload(l=0)), "asset_document_invalid_cursor"),
        (_encode_cursor(_cursor_payload(k="search")), "asset_document_stale_cursor"),
        (_encode_cursor(_cursor_payload(r="c" * 64)), "asset_document_stale_cursor"),
        (_encode_cursor(_cursor_payload(p="other")), "asset_document_stale_cursor"),
        (_encode_cursor(_cursor_payload(rv="d" * 64)), "asset_document_stale_cursor"),
    ],
)
def test_decode_cursor_rejects_tampering(cursor, message):
    with pytest.raises(ValueError, match=message):
        _decode_cursor(
            cursor,
            kind="read",
            representation_id="a" * 64,
            parent_id="00000000-0000-0000-0000-000000000001",
            version="b" * 64,
        )


def test_decode_cursor_accepts_valid_payload():
    payload = _decode_cursor(
        _encode_cursor(_cursor_payload()),
        kind="read",
        representation_id="a" * 64,
        parent_id="00000000-0000-0000-0000-000000000001",
        version="b" * 64,
    )
    assert payload["o"] == 0


def test_shrink_snippet_trims_context(monkeypatch):
    snippet = {
        "line": 3,
        "text": "needle",
        "match_start": 0,
        "match_end": 6,
        "truncated": False,
        "context": [
            {"line": 1, "text": "a" * 100, "truncated": False},
            {"line": 2, "text": "b" * 100, "truncated": False},
            {"line": 4, "text": "c" * 100, "truncated": False},
        ],
    }
    monkeypatch.setattr(document_module, "SNIPPET_JSON_BUDGET", 120)
    _shrink_snippet(snippet)
    assert snippet["truncated"] is True
    assert len(snippet["context"]) < 3
    assert all(entry["truncated"] for entry in snippet["context"])


@pytest.mark.asyncio
async def test_read_segments_direct_boundaries(monkeypatch):
    cursor = await _read_segments(
        _RangeStorage(b"a\n"),
        "k",
        representation_id="a" * 64,
        parent_id="p",
        version="v",
        size=2,
        total_lines=2,
        offset=0,
        line=1,
        line_count=10,
    )
    segments, next_cursor, eof = cursor
    assert [item["text"] for item in segments] == ["a", ""]
    assert eof is True and next_cursor is None

    segments, _, eof = await _read_segments(
        _RangeStorage(b"x"),
        "k",
        representation_id="a" * 64,
        parent_id="p",
        version="v",
        size=1,
        total_lines=1,
        offset=0,
        line=1,
        line_count=10,
    )
    assert [item["text"] for item in segments] == ["x"]
    assert eof is True

    segments, _, eof = await _read_segments(
        _RangeStorage(b"\n"),
        "k",
        representation_id="a" * 64,
        parent_id="p",
        version="v",
        size=2,
        total_lines=2,
        offset=2,
        line=2,
        line_count=10,
    )
    assert segments == [{"line": 2, "text": "", "continuation": False}]
    assert eof is True

    segments, _, eof = await _read_segments(
        _RangeStorage(b"x"),
        "k",
        representation_id="a" * 64,
        parent_id="p",
        version="v",
        size=2,
        total_lines=2,
        offset=2,
        line=2,
        line_count=10,
    )
    assert segments == [] and eof is True

    with pytest.raises(RuntimeError, match="truncated"):
        await _read_segments(
            _RangeStorage(b""),
            "k",
            representation_id="a" * 64,
            parent_id="p",
            version="v",
            size=10,
            total_lines=1,
            offset=0,
            line=1,
            line_count=10,
        )

    segments, next_cursor, eof = await _read_segments(
        _RangeStorage(b"abc"),
        "k",
        representation_id="a" * 64,
        parent_id="p",
        version="v",
        size=10,
        total_lines=1,
        offset=0,
        line=1,
        line_count=10,
    )
    assert segments[0]["continuation"] is True
    assert next_cursor and eof is False

    monkeypatch.setattr(document_module, "PAYLOAD_JSON_BUDGET", 70)
    segments, next_cursor, eof = await _read_segments(
        _RangeStorage(b"a\nb\n"),
        "k",
        representation_id="a" * 64,
        parent_id="p",
        version="v",
        size=4,
        total_lines=2,
        offset=0,
        line=1,
        line_count=10,
    )
    assert next_cursor and eof is False


@pytest.mark.asyncio
async def test_line_start_rejects_corrupt_ranges():
    representation = SimpleNamespace(offsets=[[1, 5]], size=5, total_lines=5)
    with pytest.raises(ValueError, match="asset_document_invalid_range"):
        await _line_start(_RangeStorage(), "k", representation, start_line=3)
    representation = SimpleNamespace(offsets=[[1, 0]], size=10, total_lines=5)
    with pytest.raises(ValueError, match="asset_document_invalid_range"):
        await _line_start(_RangeStorage(b""), "k", representation, start_line=2)


# ---------------------------------------------------------------- read paths


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"line_count": 0}, "asset_document_invalid_range"),
        ({"line_count": 501}, "asset_document_invalid_range"),
        ({"line_count": True}, "asset_document_invalid_range"),
        ({"line_count": "2"}, "asset_document_invalid_range"),
        ({"start_line": 0}, "asset_document_invalid_range"),
        ({"start_line": True}, "asset_document_invalid_range"),
        ({"start_line": "1"}, "asset_document_invalid_range"),
    ],
)
async def test_read_parameter_validation(database, storage, kwargs, message):
    asset = await create_asset(storage, b"a\n")
    with pytest.raises(ValueError, match=message):
        await read_document(asset, storage=storage, **kwargs)


@pytest.mark.asyncio
async def test_read_start_line_scan_checkpoints_and_edges(database, storage):
    text = "".join(f"{index:04d}-" + "x" * 195 + "\n" for index in range(400))
    asset = await create_asset(storage, text.encode())
    page = await read_document(asset, storage=storage, start_line=350, line_count=2)
    assert [segment["line"] for segment in page["segments"]] == [350, 351]
    assert page["segments"][0]["text"].startswith("0349-")

    with pytest.raises(ValueError, match="asset_document_invalid_range"):
        await read_document(asset, storage=storage, start_line=402)

    trailing = await create_asset(storage, b"only\n")
    page = await read_document(trailing, storage=storage, start_line=2)
    assert page["segments"] == [{"line": 2, "text": "", "continuation": False}]
    assert page["eof"] is True

    first = await read_document(trailing, storage=storage, line_count=1)
    with pytest.raises(ValueError, match="asset_document_invalid_cursor"):
        await read_document(
            trailing,
            storage=storage,
            start_line=2,
            cursor=first["next_cursor"],
        )


# ---------------------------------------------------------------- corruption


@pytest.mark.asyncio
async def test_missing_parent_row_is_not_found(database, storage):
    asset = await create_asset(storage, b"a\n")
    await Asset.filter(id=asset.id).delete()
    with pytest.raises(ValueError, match="file_not_found"):
        await read_document(asset, storage=storage)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status", [AssetStatus.FAILED, AssetStatus.PENDING, AssetStatus.EXPIRED]
)
async def test_unavailable_parent_statuses(database, storage, status):
    asset = await create_asset(storage, b"a\n", status=status)
    with pytest.raises(ValueError, match="file_not_found"):
        await read_document(asset, storage=storage)


@pytest.mark.asyncio
async def test_naive_parent_expiry_and_derived_source(database, storage):
    expired = await create_asset(
        storage,
        b"a\n",
        expires_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1),
    )
    with pytest.raises(ValueError, match="file_not_found"):
        await read_document(expired, storage=storage)

    source_only = await create_asset(storage, b"a\n", source=AssetSource.DERIVED_TEXT)
    with pytest.raises(ValueError, match="asset_document_derived_asset"):
        await read_document(source_only, storage=storage)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        lambda row: setattr(row, "storage_key", "public/2026/10/x.txt"),
        lambda row: setattr(row, "checksum", "0" * 64),
        lambda row: setattr(row, "size", row.size + 1),
        lambda row: setattr(row, "provenance", {**row.provenance, "state": "pending"}),
        lambda row: setattr(row, "provenance", {**row.provenance, "schema": "other"}),
        lambda row: setattr(
            row, "provenance", {**row.provenance, "representation_version": "v"}
        ),
        lambda row: setattr(
            row, "provenance", {**row.provenance, "representation_id": "1" * 64}
        ),
        lambda row: setattr(row, "provenance", {**row.provenance, "content_size": 999}),
        lambda row: setattr(row, "provenance", {**row.provenance, "total_lines": 0}),
        lambda row: setattr(row, "provenance", {**row.provenance, "line_offsets": []}),
        lambda row: setattr(
            row, "provenance", {**row.provenance, "line_offsets": [[2, 0]]}
        ),
    ],
)
async def test_corrupt_ready_metadata_is_explicit(database, storage, mutation):
    asset = await create_asset(storage, b"one\ntwo\n")
    await read_document(asset, storage=storage)
    row = await Asset.get(parent_id=asset.id)
    mutation(row)
    await row.save(update_fields=["storage_key", "checksum", "size", "provenance"])
    with pytest.raises(ValueError, match="asset_document_representation_invalid"):
        await read_document(asset, storage=storage)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [AssetStatus.DELETED, AssetStatus.EXPIRED])
async def test_deleted_or_expired_representation(database, storage, status):
    asset = await create_asset(storage, b"a\n")
    await read_document(asset, storage=storage)
    row = await Asset.get(parent_id=asset.id)
    row.status = status
    await row.save(update_fields=["status"])
    with pytest.raises(ValueError, match="file_not_found"):
        await read_document(asset, storage=storage)


# ---------------------------------------------------------------- publication


@pytest.mark.asyncio
async def test_failed_extraction_is_recorded_and_retried(
    database, storage, monkeypatch
):
    original = file_parser_service.extract_file
    calls = 0

    async def flaky(content, filename):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ValueError("document_extraction_empty")
        return await original(content, filename)

    monkeypatch.setattr(file_parser_service, "extract_file", flaky)
    asset = await create_asset(storage, b"retry\n")

    with pytest.raises(ValueError, match="document_extraction_empty"):
        await read_document(asset, storage=storage)
    row = await Asset.get(parent_id=asset.id)
    assert row.status == AssetStatus.FAILED
    assert row.provenance["state"] == "failed"
    assert "document_extraction_empty" in row.provenance["error"]

    page = await read_document(asset, storage=storage)
    assert page["eof"] is True
    row = await Asset.get(parent_id=asset.id)
    assert row.status == AssetStatus.AVAILABLE


@pytest.mark.asyncio
async def test_unsupported_source_marks_failure(database, storage):
    asset = await create_asset(
        storage, b"not-an-image", filename="photo.png", content_type="image/png"
    )
    with pytest.raises(ValueError, match="unsupported_file_type"):
        await read_document(asset, storage=storage)
    row = await Asset.get(parent_id=asset.id)
    assert row.status == AssetStatus.FAILED


@pytest.mark.asyncio
async def test_stale_pending_is_taken_over(database, storage, monkeypatch):
    monkeypatch.setattr(document_module, "STALE_PENDING_SECONDS", 0)
    asset = await create_asset(storage, b"claimed\n")
    version = document_module._representation_version(asset)
    token = "a" * 32
    row = await Asset.create(
        id=uuid4(),
        parent_id=asset.id,
        representation_key=document_module._representation_key(asset, version),
        storage_key=document_module._attempt_storage_key(asset, version, token),
        original_filename="notes.txt",
        display_filename="notes.txt",
        content_type="text/plain",
        size=0,
        checksum="0" * 64,
        source=AssetSource.DERIVED_TEXT,
        status=AssetStatus.PENDING,
        provenance=document_module._pending_provenance(asset, version, token),
    )
    page = await read_document(asset, storage=storage)
    assert page["eof"] is True
    refreshed = await Asset.get(id=row.id)
    assert refreshed.status == AssetStatus.AVAILABLE


@pytest.mark.asyncio
async def test_publication_row_vanishes(database, storage, monkeypatch):
    asset = await create_asset(storage, b"gone\n")
    version = document_module._representation_version(asset)
    token = "b" * 32
    await Asset.create(
        id=uuid4(),
        parent_id=asset.id,
        representation_key=document_module._representation_key(asset, version),
        storage_key=document_module._attempt_storage_key(asset, version, token),
        original_filename="notes.txt",
        display_filename="notes.txt",
        content_type="text/plain",
        size=0,
        checksum="0" * 64,
        source=AssetSource.DERIVED_TEXT,
        status=AssetStatus.PENDING,
        provenance=document_module._pending_provenance(asset, version, token),
    )
    original = Asset.get_or_none
    id_calls = 0

    async def vanishing(*args, **kwargs):
        nonlocal id_calls
        if kwargs.get("id") is not None:
            id_calls += 1
            if id_calls > 1:
                return None
        return await original(*args, **kwargs)

    monkeypatch.setattr(document_module.Asset, "get_or_none", vanishing)
    with pytest.raises(ValueError, match="asset_document_publication_restarted"):
        await read_document(asset, storage=storage)


@pytest.mark.asyncio
async def test_integrity_race_then_failed_takeover(database, storage, monkeypatch):
    asset = await create_asset(storage, b"race\n")
    version = document_module._representation_version(asset)
    original_create = Asset.create
    raced = False

    async def racing_create(**kwargs):
        nonlocal raced
        if not raced:
            raced = True
            kwargs = dict(kwargs)
            kwargs["status"] = AssetStatus.FAILED
            kwargs["provenance"] = document_module._failed_provenance(
                asset, version, kwargs["provenance"]["owner"], "race"
            )
            await original_create(**kwargs)
            from tortoise.exceptions import IntegrityError

            raise IntegrityError("duplicate representation")
        return await original_create(**kwargs)

    monkeypatch.setattr(document_module.Asset, "create", racing_create)
    monkeypatch.setattr(document_module, "POLL_SECONDS", 0.01)
    page = await read_document(asset, storage=storage)
    assert page["eof"] is True


@pytest.mark.asyncio
async def test_publication_conflict_raises_and_cleans_up(
    database, storage, monkeypatch
):
    original = file_parser_service.extract_file
    replaced_key = {"value": None, "old": None}

    async def conflict(content, filename):
        row = await Asset.get(representation_key=repr_key["value"])
        replaced_key["old"] = row.storage_key
        replaced_key["value"] = "internal-asset-text/other/text/content.txt"
        await Asset.filter(id=row.id).update(
            storage_key=replaced_key["value"],
            provenance={**row.provenance, "owner": "other"},
        )
        return await original(content, filename)

    asset = await create_asset(storage, b"conflict\n")
    repr_key = {
        "value": document_module._representation_key(
            asset, document_module._representation_version(asset)
        )
    }
    monkeypatch.setattr(file_parser_service, "extract_file", conflict)
    with pytest.raises(ValueError, match="asset_document_publication_conflict"):
        await read_document(asset, storage=storage)
    assert not await storage.exists(replaced_key["old"])


@pytest.mark.asyncio
async def test_available_row_without_asset_parent_is_invalid(database, storage):
    asset = await create_asset(storage, b"a\n")
    await read_document(asset, storage=storage)
    row = await Asset.get(parent_id=asset.id)
    row.parent_id = None
    await row.save(update_fields=["parent_id"])
    with pytest.raises(ValueError, match="asset_document_representation_invalid"):
        await read_document(asset, storage=storage)


# ---------------------------------------------------------------- search paths


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"query": ""}, "asset_document_invalid_query"),
        ({"query": 3}, "asset_document_invalid_query"),
        ({"query": "x" * 201}, "asset_document_invalid_query"),
        ({"query": "a\nb"}, "asset_document_invalid_query"),
        ({"query": "a\rb"}, "asset_document_invalid_query"),
        ({"query": "a", "context_lines": -1}, "asset_document_invalid_query"),
        ({"query": "a", "context_lines": 11}, "asset_document_invalid_query"),
        ({"query": "a", "context_lines": True}, "asset_document_invalid_query"),
        ({"query": "a", "limit": 0}, "asset_document_invalid_query"),
        ({"query": "a", "limit": 51}, "asset_document_invalid_query"),
        ({"query": "a", "limit": True}, "asset_document_invalid_query"),
    ],
)
async def test_search_parameter_validation(database, storage, kwargs, message):
    asset = await create_asset(storage, b"a\n")
    with pytest.raises(ValueError, match=message):
        await search_document(asset, storage=storage, **kwargs)


@pytest.mark.asyncio
async def test_search_empty_results_and_case_sensitivity(database, storage):
    asset = await create_asset(storage, b"Needle\nneedle\n")
    page = await search_document(asset, storage=storage, query="absent")
    assert page["matches"] == [] and page["eof"] is True
    page = await search_document(asset, storage=storage, query="needle")
    assert [match["line"] for match in page["matches"]] == [2]


@pytest.mark.asyncio
async def test_search_crosses_small_chunks_without_duplicates(
    database, storage, monkeypatch
):
    monkeypatch.setattr(document_module, "SEARCH_CHUNK_BYTES", 4)
    asset = await create_asset(storage, b"ababab\n")
    page = await search_document(asset, storage=storage, query="ab", limit=10)
    assert [match["line"] for match in page["matches"]] == [1, 1, 1]
    assert [match["match_end"] for match in page["matches"]] == [2, 4, 6]


@pytest.mark.asyncio
async def test_search_context_at_start_and_single_line(database, storage):
    asset = await create_asset(storage, b"needle here\nnext line\n")
    page = await search_document(
        asset, storage=storage, query="needle", context_lines=2
    )
    match = page["matches"][0]
    assert match["line"] == 1
    assert match["text"] == "needle here"
    assert [entry["line"] for entry in match["context"]] == [2, 3]

    single = await create_asset(storage, b"needle")
    page = await search_document(
        single, storage=storage, query="needle", context_lines=2
    )
    assert page["matches"][0]["text"] == "needle"
    assert page["matches"][0]["context"] == []


@pytest.mark.asyncio
async def test_search_cursor_query_context_and_limit_binding(database, storage):
    asset = await create_asset(storage, b"needle\nneedle\n")
    page = await search_document(
        asset, storage=storage, query="needle", limit=1, context_lines=1
    )
    cursor = page["next_cursor"]
    with pytest.raises(ValueError, match="asset_document_stale_cursor"):
        await search_document(
            asset, storage=storage, query="other", limit=1, cursor=cursor
        )
    with pytest.raises(ValueError, match="asset_document_stale_cursor"):
        await search_document(
            asset, storage=storage, query="needle", limit=2, cursor=cursor
        )
    with pytest.raises(ValueError, match="asset_document_stale_cursor"):
        await search_document(
            asset,
            storage=storage,
            query="needle",
            limit=1,
            context_lines=2,
            cursor=cursor,
        )


@pytest.mark.asyncio
async def test_search_budget_exhaustion_pages_every_match(
    database, storage, monkeypatch
):
    asset = await create_asset(storage, b"n\nn\nn\n")
    monkeypatch.setattr(document_module, "PAYLOAD_JSON_BUDGET", 90)
    cursor = None
    seen = []
    while True:
        page = await search_document(
            asset, storage=storage, query="n", limit=10, cursor=cursor
        )
        assert page["matches"] or page["eof"]
        seen.extend(match["line"] for match in page["matches"])
        if page["eof"]:
            break
        cursor = page["next_cursor"]
        assert cursor
    assert seen == [1, 2, 3]


@pytest.mark.asyncio
async def test_search_short_storage_read_is_truncated(database, storage, monkeypatch):
    asset = await create_asset(storage, b"needle\n")
    await read_document(asset, storage=storage)
    monkeypatch.setattr(storage, "read_range", AsyncMock(return_value=b""))
    with pytest.raises(RuntimeError, match="truncated"):
        await search_document(asset, storage=storage, query="needle")


@pytest.mark.asyncio
async def test_search_mid_character_cursor_is_invalid(database, storage):
    asset = await create_asset(storage, "你x\n".encode())
    await read_document(asset, storage=storage)
    derived = await Asset.get(parent_id=asset.id)
    cursor = _encode_cursor(
        {
            "v": 1,
            "k": "search",
            "r": derived.checksum,
            "p": str(asset.id),
            "rv": document_module._representation_version(asset),
            "o": 1,
            "l": 1,
            "q": hashlib.sha256(b"x").hexdigest()[:16],
            "c": 2,
            "n": 20,
        }
    )
    with pytest.raises(ValueError, match="asset_document_invalid_cursor"):
        await search_document(asset, storage=storage, query="x", cursor=cursor)


# ---------------------------------------------------------------- file parser


def test_markitdown_cached_instance_success_and_failures(monkeypatch):
    class _FakeMD:
        def convert(self, path):
            return SimpleNamespace(text_content="hello\r\nworld", title="Title")

    service = FileParserService()
    service._md = _FakeMD()
    assert service._get_markitdown() is service._md
    text, title = service.extract_text(b"x", "a.pdf")
    assert text == "hello\nworld"
    assert title == "Title"

    class _Broken:
        def convert(self, path):
            raise RuntimeError("broken parser")

    service._md = _Broken()
    with pytest.raises(ValueError, match="document_processing_failed_generic"):
        service.extract_text(b"x", "a.pdf")
    with pytest.raises(RuntimeError, match="broken parser"):
        asyncio.run(service.parse_file(b"x", "a.pdf"))

    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "markitdown":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    with pytest.raises(ValueError, match="document_processing_failed_generic"):
        FileParserService()._get_markitdown()


def test_plain_text_utf16_and_legacy_lenient_decode():
    service = FileParserService()
    utf16 = "hello".encode("utf-16")
    assert service.extract_text(utf16, "notes.txt") == ("hello", "")
    assert service._decode_plain_text(b"\xffbad", strict=False) == "bad"


def test_truncate_strategies_and_prompt_formatting():
    service = FileParserService()
    content = "abcdefghij"
    for strategy in ("start", "middle", "end"):
        truncated, was_truncated, length = service.truncate_content(
            content, 4, strategy
        )
        assert was_truncated and length == 10 and truncated
    assert service.truncate_content(content, 10) == (content, False, 10)
    assert service.format_files_for_prompt([]) == ""
    single = ParsedFile(
        filename="a.txt",
        content="body",
        mime_type="text/plain",
        size=4,
        truncated=True,
        original_length=99,
    )
    assert "a.txt" in service.format_files_for_prompt([single])
    assert "---" in service.format_files_for_prompt([single, single])


# ---------------------------------------------------------------- storage


class _ReadOnlyStorage(UploadStorageBackend):
    def __init__(self, content):
        self.content = content

    async def save(self, key, content, content_type=None):
        return key

    async def exists(self, key):
        return True

    async def read(self, key):
        return self.content

    async def read_range(self, key, start, length):
        return await super().read_range(key, start, length)

    async def response(self, key, content_type=None, filename=None):
        raise NotImplementedError

    async def delete(self, key):
        return None

    async def list(self, prefix):
        return []


@pytest.mark.asyncio
async def test_local_range_limits_and_limited_reads(tmp_path):
    storage = LocalUploadStorage(tmp_path)
    await storage.save("a/b.txt", b"0123456789")
    assert await storage.read_limited("a/b.txt", 10) == b"0123456789"
    with pytest.raises(ValueError, match="asset_view_size_limit_exceeded"):
        await storage.read_limited("a/b.txt", 9)
    with pytest.raises(ValueError, match="read_range_start_invalid"):
        await storage.read_range("a/b.txt", -1, 1)
    with pytest.raises(ValueError, match="read_range_length_invalid"):
        await storage.read_range("a/b.txt", 0, 0)


@pytest.mark.asyncio
async def test_base_limited_read_overflow():
    backend = _ReadOnlyStorage(b"x" * 20)
    assert await backend.read_limited("k", 20) == b"x" * 20
    with pytest.raises(ValueError, match="asset_view_size_limit_exceeded"):
        await backend.read_limited("k", 19)


class _Body:
    def __init__(self, content):
        self.content = content

    async def read(self, amount=-1):
        return self.content if amount < 0 else self.content[:amount]


class _ObjectClient:
    def __init__(self, content=None, error=None):
        self.content = content
        self.error = error
        self.calls = []

    async def get_object(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return {"Body": _Body(self.content or b"")}


class _ClientContext:
    def __init__(self, client):
        self.client = client

    async def __aenter__(self):
        return self.client

    async def __aexit__(self, *exc):
        return None


def _object_storage(monkeypatch, client):
    backend = ObjectUploadStorage(
        ObjectStorageConfig(
            endpoint="http://storage.test",
            bucket="assets",
            region=None,
            access_key="key",
            secret_key="secret",
            secure=False,
            force_path_style=True,
        )
    )
    monkeypatch.setattr(backend, "_client", lambda: _ClientContext(client))
    return backend


@pytest.mark.asyncio
async def test_object_range_and_limited_reads(monkeypatch):
    client = _ObjectClient(b"abcdef")
    backend = _object_storage(monkeypatch, client)
    assert await backend.read_limited("k", 6) == b"abcdef"
    with pytest.raises(ValueError, match="asset_view_size_limit_exceeded"):
        await backend.read_limited("k", 5)
    with pytest.raises(ValueError, match="read_range_start_invalid"):
        await backend.read_range("k", -1, 1)
    with pytest.raises(ValueError, match="read_range_length_invalid"):
        await backend.read_range("k", 0, 0)


@pytest.mark.asyncio
async def test_object_range_errors(monkeypatch):
    invalid = ClientError(
        {
            "Error": {"Code": "InvalidRange"},
            "ResponseMetadata": {"HTTPStatusCode": 416},
        },
        "GetObject",
    )
    backend = _object_storage(monkeypatch, _ObjectClient(None, invalid))
    assert await backend.read_range("k", 50, 1) == b""

    code_only = ClientError(
        {"Error": {"Code": "416"}, "ResponseMetadata": {}}, "GetObject"
    )
    backend = _object_storage(monkeypatch, _ObjectClient(None, code_only))
    assert await backend.read_range("k", 50, 1) == b""

    denied = ClientError(
        {
            "Error": {"Code": "AccessDenied"},
            "ResponseMetadata": {"HTTPStatusCode": 403},
        },
        "GetObject",
    )
    backend = _object_storage(monkeypatch, _ObjectClient(None, denied))
    with pytest.raises(ClientError):
        await backend.read_range("k", 0, 1)
