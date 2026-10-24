"""Complete persisted document representations with bounded range access."""

import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from botocore.exceptions import ClientError
from tortoise.context import TortoiseContext

from app.models.asset import (
    Asset,
    AssetScopeRef,
    AssetSource,
    AssetStatus,
)
from app.services import asset_document as document_module
from app.services import file_parser as parser_module
from app.services.asset_document import (
    MAX_READ_BYTES,
    MAX_RESPONSE_BYTES,
    _encode_cursor,
    read_document,
    search_document,
)
from app.services.file_parser import (
    FileParseConfig,
    FileParserService,
    file_parser_service,
)
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
    storage: UploadStorageBackend,
    content: bytes,
    *,
    filename: str = "notes.txt",
    content_type: str = "text/plain",
    source: AssetSource = AssetSource.UPLOAD,
    status: AssetStatus = AssetStatus.AVAILABLE,
    expires_at: datetime | None = None,
    parent_id=None,
) -> Asset:
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


async def drain_document(asset, storage, *, line_count: int = 100) -> str:
    lines: dict[int, str] = {}
    cursor = None
    while True:
        page = await read_document(
            asset,
            storage=storage,
            line_count=line_count,
            cursor=cursor,
        )
        for segment in page["segments"]:
            lines[segment["line"]] = lines.get(segment["line"], "") + segment["text"]
        if page["eof"]:
            break
        cursor = page["next_cursor"]
        assert cursor
    return "\n".join(lines[number] for number in sorted(lines))


@pytest.mark.asyncio
async def test_complete_extraction_never_truncates_and_normalizes(database):
    service = FileParserService()
    text = ("line-" + "x" * 80 + "\r\n") * 4000
    extracted = await service.extract_file(text.encode("utf-8"), "notes.txt")

    assert extracted.text == text.replace("\r\n", "\n")
    assert len(extracted.text) > FileParseConfig().max_content_length

    legacy = await service.parse_file(text.encode("utf-8"), "notes.txt")
    assert legacy.truncated is True
    assert len(legacy.content) < len(extracted.text)


@pytest.mark.asyncio
async def test_complete_extraction_rejects_empty_undecodable_and_oversized(
    database, monkeypatch
):
    service = FileParserService()
    with pytest.raises(ValueError, match="document_extraction_empty"):
        await service.extract_file(b"   \n\t", "notes.txt")
    with pytest.raises(ValueError, match="document_extraction_decode_failed"):
        await service.extract_file(b"\xff\xfe\xfa", "notes.txt")
    with pytest.raises(ValueError, match="unsupported_file_type"):
        await service.extract_file(b"data", "photo.png")

    monkeypatch.setattr(parser_module, "MAX_EXTRACTED_CHARS", 5)
    with pytest.raises(ValueError, match="asset_document_resource_limit_exceeded"):
        await service.extract_file(b"123456", "notes.txt")


@pytest.mark.asyncio
async def test_read_document_reconstructs_complete_text(database, storage):
    text = "alpha\nbeta\n\ngamma\nlast line\n"
    asset = await create_asset(storage, text.encode("utf-8"))

    assert await drain_document(asset, storage) == text

    derived = await Asset.get(parent_id=asset.id)
    assert derived.source == AssetSource.DERIVED_TEXT
    assert derived.status == AssetStatus.AVAILABLE
    assert derived.parent_id == asset.id
    assert len(derived.storage_key.split("/")) >= 5
    assert not await AssetScopeRef.filter(asset_id=derived.id).exists()


@pytest.mark.asyncio
async def test_read_reuses_single_representation(database, storage):
    asset = await create_asset(storage, b"one\ntwo\n")

    first = await read_document(asset, storage=storage)
    second = await read_document(asset, storage=storage)

    assert first["representation_id"] == second["representation_id"]
    rows = await Asset.filter(parent_id=asset.id)
    assert len(rows) == 1
    # Security invariant: the derived key is not addressable by the public
    # /files/{category}/{year}/{month}/{filename} route.
    assert len(rows[0].storage_key.split("/")) > 4


@pytest.mark.asyncio
async def test_oversized_line_continues_without_loading_full_text(database, storage):
    text = "你" * 40_000
    asset = await create_asset(storage, text.encode("utf-8"))

    pages = []
    cursor = None
    reconstructed = ""
    while True:
        page = await read_document(asset, storage=storage, line_count=1, cursor=cursor)
        pages.append(page)
        for segment in page["segments"]:
            assert segment["line"] == 1
            reconstructed += segment["text"]
            assert len(segment["text"].encode("utf-8")) <= MAX_READ_BYTES + 4
        if page["eof"]:
            break
        assert page["next_cursor"]
        cursor = page["next_cursor"]

    assert reconstructed == text
    assert len(pages) > 1
    assert pages[0]["segments"][0]["continuation"] is True
    assert pages[-1]["segments"][-1]["continuation"] is False


@pytest.mark.asyncio
async def test_cursor_validation_rejects_foreign_and_mid_character_offsets(
    database, storage
):
    asset = await create_asset(storage, "你好\nworld\n".encode("utf-8"))
    page = await read_document(asset, storage=storage, line_count=1)
    derived = await Asset.get(parent_id=asset.id)
    version = document_module._representation_version(asset)

    with pytest.raises(ValueError, match="asset_document_invalid_cursor"):
        await read_document(asset, storage=storage, cursor="not-a-cursor")
    with pytest.raises(ValueError, match="asset_document_stale_cursor"):
        await read_document(
            asset,
            storage=storage,
            cursor=_encode_cursor(
                {
                    "v": 1,
                    "k": "read",
                    "r": "0" * 64,
                    "p": str(asset.id),
                    "rv": version,
                    "o": 0,
                    "l": 1,
                }
            ),
        )
    mid_character = _encode_cursor(
        {
            "v": 1,
            "k": "read",
            "r": derived.checksum,
            "p": str(asset.id),
            "rv": version,
            "o": 1,
            "l": 1,
        }
    )
    with pytest.raises(ValueError, match="asset_document_invalid_cursor"):
        await read_document(asset, storage=storage, cursor=mid_character)
    assert page["start_line"] == 1


@pytest.mark.asyncio
async def test_asset_with_parent_id_is_still_a_valid_document(database, storage):
    original = await create_asset(storage, b"root\n")
    derivative = await create_asset(
        storage,
        b"generated document\n",
        filename="artifact.txt",
        source=AssetSource.SANDBOX_ARTIFACT,
        parent_id=original.id,
    )

    page = await read_document(derivative, storage=storage)
    assert (
        "\n".join(segment["text"] for segment in page["segments"])
        == "generated document\n"
    )
    assert page["eof"] is True


@pytest.mark.asyncio
async def test_cursor_is_bound_to_the_parent_asset(database, storage):
    first = await create_asset(storage, b"same\nsame\n")
    second = await create_asset(storage, b"same\nsame\n")

    page = await read_document(first, storage=storage, line_count=1)
    assert page["next_cursor"]
    with pytest.raises(ValueError, match="asset_document_stale_cursor"):
        await read_document(second, storage=storage, cursor=page["next_cursor"])

    search_page = await search_document(first, storage=storage, query="same", limit=1)
    assert search_page["next_cursor"]
    with pytest.raises(ValueError, match="asset_document_stale_cursor"):
        await search_document(
            second,
            storage=storage,
            query="same",
            limit=1,
            cursor=search_page["next_cursor"],
        )


@pytest.mark.asyncio
async def test_read_serialized_output_stays_bounded_with_escapes(database, storage):
    text = (
        "\n".join(f'"quoted" \\slash\\ \t\x01 {index}' for index in range(4000)) + "\n"
    )
    asset = await create_asset(storage, text.encode("utf-8"))

    cursor = None
    lines: dict[int, str] = {}
    while True:
        page = await read_document(
            asset, storage=storage, line_count=200, cursor=cursor
        )
        serialized = json.dumps(page, ensure_ascii=False).encode("utf-8")
        assert len(serialized) <= MAX_RESPONSE_BYTES
        for segment in page["segments"]:
            lines[segment["line"]] = lines.get(segment["line"], "") + segment["text"]
        if page["eof"]:
            break
        assert page["next_cursor"]
        cursor = page["next_cursor"]

    assert "\n".join(lines[number] for number in sorted(lines)) == text
    assert len(lines) > 1


@pytest.mark.asyncio
async def test_search_serialized_output_and_context_are_bounded(database, storage):
    lines = [f'line {index} needle "escaped" 你好 ' + "x" * 40 for index in range(120)]
    asset = await create_asset(storage, ("\n".join(lines) + "\n").encode())

    cursor = None
    seen: list[int] = []
    pages = 0
    while True:
        page = await search_document(
            asset,
            storage=storage,
            query="needle",
            context_lines=10,
            limit=50,
            cursor=cursor,
        )
        pages += 1
        serialized = json.dumps(page, ensure_ascii=False).encode("utf-8")
        assert len(serialized) <= MAX_RESPONSE_BYTES
        seen.extend(match["line"] for match in page["matches"])
        if page["eof"]:
            break
        assert page["next_cursor"]
        assert page["matches"], "budgeted pages must make progress"
        cursor = page["next_cursor"]

    assert pages > 1
    assert seen == list(range(1, 121))


@pytest.mark.asyncio
async def test_search_first_escaped_control_snippet_is_bounded(database, storage):
    lines = ["\x01" * 400 for _ in range(30)]
    lines[15] = "needle"
    asset = await create_asset(storage, ("\n".join(lines) + "\n").encode())

    page = await search_document(
        asset,
        storage=storage,
        query="needle",
        context_lines=10,
        limit=1,
    )

    assert page["matches"]
    match = page["matches"][0]
    assert match["line"] == 16
    assert match["context"]
    assert all(entry["truncated"] for entry in match["context"])
    serialized = json.dumps(page, ensure_ascii=False).encode("utf-8")
    assert len(serialized) <= MAX_RESPONSE_BYTES


@pytest.mark.asyncio
async def test_parent_deleted_during_publication_is_not_returned(
    database, storage, monkeypatch
):
    original = file_parser_service.extract_file
    asset = await create_asset(storage, b"secret\n")

    async def delete_then_extract(content, filename):
        await Asset.filter(id=asset.id).update(status=AssetStatus.DELETED)
        return await original(content, filename)

    monkeypatch.setattr(file_parser_service, "extract_file", delete_then_extract)
    with pytest.raises(ValueError, match="file_not_found"):
        await read_document(asset, storage=storage)


@pytest.mark.asyncio
async def test_parent_gate_blocks_expired_deleted_and_derived_inputs(database, storage):
    expired = await create_asset(
        storage,
        b"gone\n",
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    with pytest.raises(ValueError, match="file_not_found"):
        await read_document(expired, storage=storage)

    deleted = await create_asset(storage, b"gone\n")
    deleted.deleted_at = datetime.now(UTC)
    await deleted.save(update_fields=["deleted_at"])
    with pytest.raises(ValueError, match="file_not_found"):
        await search_document(deleted, storage=storage, query="gone")

    parent = await create_asset(storage, b"keep\n")
    await read_document(parent, storage=storage)
    parent.status = AssetStatus.DELETED
    await parent.save(update_fields=["status"])
    with pytest.raises(ValueError, match="file_not_found"):
        await read_document(parent, storage=storage)

    derived = await Asset.get(parent_id=parent.id)
    with pytest.raises(ValueError, match="asset_document_derived_asset"):
        await read_document(derived, storage=storage)


@pytest.mark.asyncio
async def test_search_streams_pages_context_and_binds_query(database, storage):
    lines = ["filler " * 10 for _ in range(6000)]
    lines[1] = "first needle here"
    lines[3000] = "middle needle here"
    lines[-2] = "late needle here"
    text = "\n".join(lines) + "\n"
    asset = await create_asset(storage, text.encode("utf-8"))

    first = await search_document(
        asset, storage=storage, query="needle", context_lines=1, limit=2
    )
    assert [m["line"] for m in first["matches"]] == [2, 3001]
    assert first["eof"] is False
    assert first["next_cursor"]
    assert "needle" in first["matches"][0]["text"]
    assert first["matches"][0]["context"][0]["line"] == 1
    assert first["matches"][0]["context"][-1]["line"] == 3

    with pytest.raises(ValueError, match="asset_document_stale_cursor"):
        await search_document(
            asset,
            storage=storage,
            query="filler",
            limit=2,
            context_lines=1,
            cursor=first["next_cursor"],
        )

    second = await search_document(
        asset,
        storage=storage,
        query="needle",
        context_lines=1,
        limit=2,
        cursor=first["next_cursor"],
    )
    assert [m["line"] for m in second["matches"]] == [len(lines) - 1]
    assert second["eof"] is True
    assert second["next_cursor"] is None


@pytest.mark.asyncio
async def test_concurrent_readers_share_one_publication(database, storage, monkeypatch):
    original = file_parser_service.extract_file

    async def slow_extract(content, filename):
        await asyncio.sleep(0.05)
        return await original(content, filename)

    monkeypatch.setattr(file_parser_service, "extract_file", slow_extract)
    monkeypatch.setattr(document_module, "WAIT_SECONDS", 5.0)
    asset = await create_asset(storage, b"shared\ntext\n")

    first, second = await asyncio.gather(
        read_document(asset, storage=storage),
        read_document(asset, storage=storage),
    )

    assert first["representation_id"] == second["representation_id"]
    assert await Asset.filter(parent_id=asset.id).count() == 1
    assert await Asset.filter(representation_key__isnull=False).count() == 1


@pytest.mark.asyncio
async def test_pending_publication_times_out_without_false_success(
    database, storage, monkeypatch
):
    monkeypatch.setattr(document_module, "WAIT_SECONDS", 0.2)
    monkeypatch.setattr(document_module, "POLL_SECONDS", 0.01)
    asset = await create_asset(storage, b"pending\n")
    version = document_module._representation_version(asset)
    attempt_key = document_module._attempt_storage_key(asset, version, "a" * 32)
    pending = await Asset.create(
        id=uuid4(),
        parent_id=asset.id,
        representation_key=document_module._representation_key(asset, version),
        storage_key=attempt_key,
        original_filename="notes.txt.txt",
        display_filename="notes.txt.txt",
        content_type="text/plain; charset=utf-8",
        size=0,
        checksum="0" * 64,
        source=AssetSource.DERIVED_TEXT,
        status=AssetStatus.PENDING,
        provenance=document_module._pending_provenance(asset, version, "a" * 32),
    )

    with pytest.raises(ValueError, match="asset_document_in_progress"):
        await read_document(asset, storage=storage)
    refreshed = await Asset.get(id=pending.id)
    assert refreshed.status == AssetStatus.PENDING


@pytest.mark.asyncio
async def test_local_range_reads_are_bounded(storage):
    await storage.save("internal-asset-text/a/b/text.txt", b"0123456789")
    key = "internal-asset-text/a/b/text.txt"

    assert await storage.read_range(key, 2, 3) == b"234"
    assert await storage.read_range(key, 8, 10) == b"89"
    assert await storage.read_range(key, 10, 5) == b""
    with pytest.raises(ValueError, match="read_range_length_invalid"):
        await storage.read_range(key, 0, 0)


class _FallbackStorage(UploadStorageBackend):
    def __init__(self) -> None:
        self.content = b"fallback-bytes"

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
async def test_range_read_has_no_full_read_fallback():
    backend = _FallbackStorage()
    with pytest.raises(NotImplementedError):
        await backend.read_range("key", 9, 5)


class _Body:
    def __init__(self, content: bytes) -> None:
        self.content = content

    async def read(self, amount: int = -1) -> bytes:
        if amount < 0:
            return self.content
        return self.content[:amount]


class _ObjectClient:
    def __init__(self, content: bytes | None, error: ClientError | None) -> None:
        self.content = content
        self.error = error
        self.calls: list[dict] = []

    async def get_object(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return {"Body": _Body(self.content or b"")}


class _ClientContext:
    def __init__(self, client: _ObjectClient) -> None:
        self.client = client

    async def __aenter__(self):
        return self.client

    async def __aexit__(self, *exc_info):
        return None


def _object_storage(monkeypatch, client: _ObjectClient) -> ObjectUploadStorage:
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
async def test_object_range_read_uses_range_header(monkeypatch):
    client = _ObjectClient(b"abcdef", None)
    backend = _object_storage(monkeypatch, client)

    assert await backend.read_range("key", 2, 3) == b"abcdef"
    assert client.calls[0]["Range"] == "bytes=2-4"


@pytest.mark.asyncio
async def test_object_range_beyond_eof_returns_empty(monkeypatch):
    error = ClientError(
        {
            "Error": {"Code": "InvalidRange"},
            "ResponseMetadata": {"HTTPStatusCode": 416},
        },
        "GetObject",
    )
    client = _ObjectClient(None, error)
    backend = _object_storage(monkeypatch, client)

    assert await backend.read_range("key", 100, 10) == b""


@pytest.mark.asyncio
async def test_compressed_cursor_rejects_oversized_decode_and_trailing_data(
    database, storage
):
    import base64
    import zlib

    asset = await create_asset(storage, b"first\nlast\n")
    page = await read_document(asset, storage=storage, line_count=1)
    packed = base64.urlsafe_b64decode(
        page["next_cursor"] + "=" * (-len(page["next_cursor"]) % 4)
    )
    malformed = [zlib.compress(b"x" * 100000), packed + b"trailing", packed[:-2]]
    for raw in malformed:
        cursor = base64.urlsafe_b64encode(raw).decode().rstrip("=")
        with pytest.raises(ValueError, match="asset_document_invalid_cursor"):
            await read_document(asset, storage=storage, cursor=cursor)
