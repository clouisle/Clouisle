"""Lifecycle, authorization, and race behavior for persisted document text.

These tests drive the public read/search surface plus the bounded segment
reader with real assets, real storage, and real publication rows. Each one
asserts an observable outcome (returned bytes, cursor closure, persisted
state, or a typed error) instead of internal call wiring.
"""

import hashlib
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from tortoise.context import TortoiseContext
from tortoise.exceptions import IntegrityError

from app.models.asset import Asset, AssetSource, AssetStatus
from app.services import asset_document as document_module
from app.services.asset_document import (
    _decode_cursor,
    _encode_cursor,
    _read_segments,
    read_document,
    search_document,
)
from app.services.file_parser import file_parser_service
from app.services.upload_storage import LocalUploadStorage


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
    )


async def create_pending_representation(asset, *, token, storage_key=None):
    version = document_module._representation_version(asset)
    return await Asset.create(
        id=uuid4(),
        parent_id=asset.id,
        representation_key=document_module._representation_key(asset, version),
        storage_key=storage_key
        or document_module._attempt_storage_key(asset, version, token),
        original_filename="notes.txt.txt",
        display_filename="notes.txt.txt",
        content_type="text/plain; charset=utf-8",
        size=0,
        checksum="0" * 64,
        source=AssetSource.DERIVED_TEXT,
        status=AssetStatus.PENDING,
        provenance=document_module._pending_provenance(asset, version, token),
    )


class _FixedChunkStorage:
    """Storage stub that returns one fixed window for every range read."""

    def __init__(self, chunk):
        self.chunk = chunk

    async def read_range(self, key, start, length):
        return self.chunk


class _NoReadStorage:
    def __init__(self):
        self.calls = 0

    async def read_range(self, key, start, length):
        self.calls += 1
        raise AssertionError("empty representations must not touch storage")


# ---------------------------------------------------------------- publication


@pytest.mark.asyncio
async def test_extraction_title_is_persisted_with_the_ready_representation(
    database, storage, monkeypatch
):
    asset = await create_asset(storage, b"raw source\n")

    async def titled_extract(content, filename):
        return SimpleNamespace(text="Report body\n", title="Quarterly Report")

    monkeypatch.setattr(file_parser_service, "extract_file", titled_extract)
    page = await read_document(asset, storage=storage)

    assert [segment["text"] for segment in page["segments"]] == ["Report body", ""]
    assert page["eof"] is True
    row = await Asset.get(parent_id=asset.id)
    assert row.provenance["state"] == "ready"
    assert row.provenance["title"] == "Quarterly Report"


@pytest.mark.asyncio
async def test_representation_with_negative_size_is_rejected_as_corrupt(
    database, storage
):
    asset = await create_asset(storage, b"one\ntwo\n")
    await read_document(asset, storage=storage)
    row = await Asset.get(parent_id=asset.id)
    await Asset.filter(id=row.id).update(size=-1)

    with pytest.raises(ValueError, match="asset_document_representation_invalid"):
        await read_document(asset, storage=storage)


@pytest.mark.asyncio
async def test_lost_claim_is_retried_until_the_takeover_succeeds(
    database, storage, monkeypatch
):
    monkeypatch.setattr(document_module, "STALE_PENDING_SECONDS", 0)
    monkeypatch.setattr(document_module, "WAIT_SECONDS", 5.0)
    monkeypatch.setattr(document_module, "POLL_SECONDS", 0.01)
    asset = await create_asset(storage, b"claimed after retry\n")
    row = await create_pending_representation(asset, token="a" * 32)

    original_filter = Asset.filter
    claims = {"attempts": 0}

    class _ClaimProxy:
        def __init__(self, queryset):
            self._queryset = queryset

        async def update(self, **kwargs):
            if kwargs.get("status") == AssetStatus.PENDING:
                claims["attempts"] += 1
                if claims["attempts"] == 1:
                    # Another worker won the compare-and-set first.
                    return 0
            return await self._queryset.update(**kwargs)

        def __getattr__(self, name):
            return getattr(self._queryset, name)

    def claimed_filter(*args, **kwargs):
        return _ClaimProxy(original_filter(*args, **kwargs))

    monkeypatch.setattr(Asset, "filter", claimed_filter)

    page = await read_document(asset, storage=storage)

    assert claims["attempts"] == 2
    assert [segment["text"] for segment in page["segments"]] == [
        "claimed after retry",
        "",
    ]
    refreshed = await Asset.get(id=row.id)
    assert refreshed.status == AssetStatus.AVAILABLE
    assert refreshed.checksum != "0" * 64


@pytest.mark.asyncio
async def test_takeover_without_private_attempt_key_skips_cleanup(
    database, storage, monkeypatch
):
    monkeypatch.setattr(document_module, "STALE_PENDING_SECONDS", 0)
    asset = await create_asset(storage, b"legacy row\n")
    row = await create_pending_representation(
        asset, token="b" * 32, storage_key="legacy/location.txt"
    )

    page = await read_document(asset, storage=storage)

    assert page["eof"] is True
    refreshed = await Asset.get(id=row.id)
    assert refreshed.status == AssetStatus.AVAILABLE
    # The legacy location was never ours, so takeover leaves it untouched.
    assert refreshed.storage_key != "legacy/location.txt"


@pytest.mark.asyncio
async def test_integrity_race_exhausts_the_wait_budget(database, storage, monkeypatch):
    monkeypatch.setattr(document_module, "WAIT_SECONDS", 0.0)
    monkeypatch.setattr(document_module, "POLL_SECONDS", 0.01)
    asset = await create_asset(storage, b"never claimed\n")

    original_get_or_none = Asset.get_or_none

    async def lookup(*args, **kwargs):
        if kwargs.get("representation_key") is not None:
            return None
        return await original_get_or_none(*args, **kwargs)

    async def duplicate_create(**kwargs):
        raise IntegrityError("duplicate representation")

    monkeypatch.setattr(Asset, "get_or_none", lookup)
    monkeypatch.setattr(Asset, "create", duplicate_create)

    with pytest.raises(ValueError, match="asset_document_in_progress"):
        await read_document(asset, storage=storage)


@pytest.mark.asyncio
async def test_publication_update_matching_no_pending_row_is_a_conflict(
    database, storage, monkeypatch
):
    asset = await create_asset(storage, b"conflict after write\n")
    original_save = storage.save
    hijacked = {"key": None}

    async def saving(key, content, content_type=None):
        result = await original_save(key, content, content_type)
        if key.startswith(document_module.STORAGE_PREFIX):
            hijacked["key"] = "internal-asset-text/hijacked/content.txt"
            await Asset.filter(parent_id=asset.id).update(storage_key=hijacked["key"])
        return result

    monkeypatch.setattr(storage, "save", saving)

    with pytest.raises(ValueError, match="asset_document_publication_conflict"):
        await read_document(asset, storage=storage)

    row = await Asset.get(parent_id=asset.id)
    assert row.status == AssetStatus.PENDING
    assert row.storage_key == hijacked["key"]


@pytest.mark.asyncio
async def test_tampered_row_after_publish_is_rejected_without_rollback(
    database, storage, monkeypatch
):
    asset = await create_asset(storage, b"tamper target\n")
    original_get = Asset.get
    reads = {"count": 0}

    async def racing_get(*args, **kwargs):
        row_id = kwargs.get("id")
        if row_id is not None:
            reads["count"] += 1
            if reads["count"] == 2:
                # A concurrent writer corrupts metadata after the atomic
                # publication update but before verification.
                await Asset.filter(id=row_id).update(checksum="f" * 64)
        return await original_get(*args, **kwargs)

    monkeypatch.setattr(Asset, "get", racing_get)

    with pytest.raises(ValueError, match="asset_document_representation_invalid"):
        await read_document(asset, storage=storage)

    row = await Asset.get(parent_id=asset.id)
    assert row.status == AssetStatus.AVAILABLE
    assert row.checksum == "f" * 64


@pytest.mark.asyncio
async def test_source_change_during_publication_rebinds_the_representation(
    database, storage, monkeypatch
):
    asset = await create_asset(storage, b"stable bytes\n")
    original_extract = file_parser_service.extract_file
    calls = {"count": 0}

    async def changing_extract(content, filename):
        calls["count"] += 1
        result = await original_extract(content, filename)
        if calls["count"] == 1:
            await Asset.filter(id=asset.id).update(
                original_filename="renamed-source.txt",
                display_filename="renamed-source.txt",
            )
        return result

    monkeypatch.setattr(file_parser_service, "extract_file", changing_extract)
    page = await read_document(asset, storage=storage)

    assert calls["count"] == 2
    rows = await Asset.filter(parent_id=asset.id)
    assert len(rows) == 2
    assert len({row.representation_key for row in rows}) == 2
    parent = await Asset.get(id=asset.id)
    rebounded = await Asset.get(
        representation_key=document_module._representation_key(
            parent, document_module._representation_version(parent)
        )
    )
    assert rebounded.original_filename == "renamed-source.txt"
    assert page["representation_id"] == rebounded.checksum
    assert [segment["text"] for segment in page["segments"]] == [
        "stable bytes",
        "",
    ]


@pytest.mark.asyncio
async def test_parent_deleted_after_publication_is_never_served(
    database, storage, monkeypatch
):
    asset = await create_asset(storage, b"revoked bytes\n")
    original_save = storage.save

    async def revoking_save(key, content, content_type=None):
        result = await original_save(key, content, content_type)
        if key.startswith(document_module.STORAGE_PREFIX):
            # Authorization is rechecked after publication: deleting the parent
            # must revoke the derived text even though it is now AVAILABLE.
            await Asset.filter(id=asset.id).update(status=AssetStatus.DELETED)
        return result

    monkeypatch.setattr(storage, "save", revoking_save)

    with pytest.raises(ValueError, match="file_not_found"):
        await read_document(asset, storage=storage)

    row = await Asset.get(parent_id=asset.id)
    assert row.status == AssetStatus.AVAILABLE


# ---------------------------------------------------------------- cursors


@pytest.mark.asyncio
async def test_cursor_offset_past_published_size_is_stale(database, storage):
    asset = await create_asset(storage, b"a\nb\n")
    await read_document(asset, storage=storage)
    derived = await Asset.get(parent_id=asset.id)
    cursor = _encode_cursor(
        {
            "v": 1,
            "k": "read",
            "r": derived.checksum,
            "p": str(asset.id),
            "rv": document_module._representation_version(asset),
            "o": derived.size + 1,
            "l": 1,
        }
    )

    with pytest.raises(ValueError, match="asset_document_stale_cursor"):
        await read_document(asset, storage=storage, cursor=cursor)


@pytest.mark.asyncio
async def test_deep_start_line_scans_multiple_storage_windows(database, storage):
    lines = [f"{index:06d}" + "x" * 993 + "\n" for index in range(600)]
    asset = await create_asset(storage, "".join(lines).encode())

    # Line 256 sits 255 lines past the [1, 0] checkpoint; each 64 KiB window
    # only holds 65 of these 1000-byte lines, so the resolver must advance.
    page = await read_document(asset, storage=storage, start_line=256, line_count=1)

    assert page["start_line"] == 256
    assert page["segments"] == [
        {"line": 256, "text": "000255" + "x" * 993, "continuation": False}
    ]
    assert page["eof"] is False


# ---------------------------------------------------------------- segments


@pytest.mark.asyncio
async def test_empty_representation_returns_no_segments():
    storage = _NoReadStorage()
    segments, next_cursor, eof = await _read_segments(
        storage,
        "k",
        representation_id="a" * 64,
        parent_id="p",
        version="v",
        size=0,
        total_lines=1,
        offset=0,
        line=1,
        line_count=10,
    )

    assert segments == []
    assert next_cursor is None
    assert eof is True
    assert storage.calls == 0


@pytest.mark.asyncio
async def test_non_final_window_of_a_partial_code_point_is_truncated():
    with pytest.raises(RuntimeError, match="truncated"):
        await _read_segments(
            _FixedChunkStorage("你".encode("utf-8")[:2]),
            "k",
            representation_id="a" * 64,
            parent_id="p",
            version="v",
            size=10,
            total_lines=1,
            offset=0,
            line=1,
            line_count=5,
        )


@pytest.mark.asyncio
async def test_window_ending_on_newline_with_more_data_returns_cursor():
    data = (b"a" * 9 + b"\n") * 10
    segments, next_cursor, eof = await _read_segments(
        _FixedChunkStorage(data),
        "k",
        representation_id="a" * 64,
        parent_id="p",
        version="v",
        size=200,
        total_lines=20,
        offset=0,
        line=1,
        line_count=50,
    )

    assert [segment["line"] for segment in segments] == list(range(1, 11))
    assert all(segment["text"] == "a" * 9 for segment in segments)
    assert eof is False
    payload = _decode_cursor(
        next_cursor,
        kind="read",
        representation_id="a" * 64,
        parent_id="p",
        version="v",
    )
    assert payload["o"] == len(data)
    assert payload["l"] == 11


# ---------------------------------------------------------------- search


@pytest.mark.asyncio
async def test_search_finishing_on_an_exact_chunk_boundary_reports_eof(
    database, storage, monkeypatch
):
    monkeypatch.setattr(document_module, "SEARCH_CHUNK_BYTES", 4)
    asset = await create_asset(storage, b"abcdefgh")

    page = await search_document(asset, storage=storage, query="z")

    assert page["matches"] == []
    assert page["next_cursor"] is None
    assert page["eof"] is True


@pytest.mark.asyncio
async def test_search_limit_reached_at_end_of_document_closes_without_cursor(
    database, storage
):
    asset = await create_asset(storage, b"xneedle")

    page = await search_document(asset, storage=storage, query="needle", limit=1)

    assert len(page["matches"]) == 1
    assert page["matches"][0]["match_end"] == 7
    assert page["next_cursor"] is None
    assert page["eof"] is True


@pytest.mark.asyncio
async def test_search_resumes_after_an_overlapping_match_span(
    database, storage, monkeypatch
):
    monkeypatch.setattr(document_module, "SEARCH_CHUNK_BYTES", 4)
    asset = await create_asset(storage, b"abneedlezzzz")

    page = await search_document(asset, storage=storage, query="needle")

    assert len(page["matches"]) == 1
    assert page["matches"][0]["match_start"] == 2
    assert page["matches"][0]["match_end"] == 8
    assert page["eof"] is True


@pytest.mark.asyncio
async def test_search_snippet_truncates_a_long_matching_line(database, storage):
    text = "x" * 400 + "needle" + "y" * 400 + "\n"
    asset = await create_asset(storage, text.encode("utf-8"))

    page = await search_document(
        asset, storage=storage, query="needle", context_lines=0
    )

    match = page["matches"][0]
    assert match["truncated"] is True
    assert len(match["text"]) == document_module.MAX_SNIPPET_CHARS
    assert match["text"][match["match_start"] : match["match_end"]] == "needle"
    assert match["match_end"] - match["match_start"] == len("needle")
    assert match["context"] == []
