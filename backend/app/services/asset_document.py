"""Complete, bounded document access for authorized Assets.

The extracted text of a document is persisted as a private derived Asset
(``AssetSource.DERIVED_TEXT``) whose ``storage_key`` is never addressable by
the public upload route (it has more path segments than ``/files`` accepts).
A unique ``representation_key`` makes publication idempotent across processes:
the first worker claims a PENDING row, writes the complete text, and only then
flips it to AVAILABLE. Other workers wait for that row instead of overwriting
it. Every read re-authorizes through the original parent Asset, so a derived
representation can never outlive or bypass its parent.

Reads and searches are byte-range based; they never load the full stored text
for a request. Line positions come from a sparse offset index persisted with
the representation, and cursors are bound to the representation identity (and
for search, to the literal query).
"""

from __future__ import annotations

import asyncio
import base64
import bisect
import codecs
import hashlib
import json
import secrets
import zlib
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from tortoise.exceptions import IntegrityError

from app.models.asset import Asset, AssetSource, AssetStatus
from app.services.asset import asset_service
from app.services.file_parser import EXTRACTION_VERSION, file_parser_service
from app.services.upload_storage import UploadStorageBackend

REPRESENTATION_SCHEMA = "asset-document-text-v1"
STORAGE_PREFIX = "internal-asset-text"

# A line offset checkpoint is stored every interval; locating an arbitrary
# line scans at most that many lines instead of the whole document.
CHECKPOINT_INTERVAL = 256

MAX_READ_BYTES = 32 * 1024
# Shared hard ceiling for one serialized read/search response, with headroom
# for top-level metadata and tool adapter fields.
MAX_RESPONSE_BYTES = 32 * 1024
RESPONSE_HEADROOM_BYTES = 4 * 1024
PAYLOAD_JSON_BUDGET = MAX_RESPONSE_BYTES - RESPONSE_HEADROOM_BYTES
MAX_LINE_COUNT = 500
MAX_SEARCH_LIMIT = 50
MAX_CONTEXT_LINES = 10
MAX_QUERY_CHARS = 200
MAX_SNIPPET_CHARS = 512
MAX_CONTEXT_SNIPPET_CHARS = 128
SNIPPET_JSON_BUDGET = 24 * 1024
SEARCH_CHUNK_BYTES = 256 * 1024
CONTEXT_WINDOW_BYTES = 8 * 1024

WAIT_SECONDS = 30.0
POLL_SECONDS = 0.1
STALE_PENDING_SECONDS = 300
_ZERO_CHECKSUM = "0" * 64


class _ReadyRepresentation:
    """Validated persisted representation metadata."""

    __slots__ = ("asset", "checksum", "offsets", "size", "total_lines")

    def __init__(
        self,
        asset: Asset,
        *,
        checksum: str,
        size: int,
        total_lines: int,
        offsets: list[list[int]],
    ) -> None:
        self.asset = asset
        self.checksum = checksum
        self.size = size
        self.total_lines = total_lines
        self.offsets = offsets

    @property
    def storage_key(self) -> str:
        return self.asset.storage_key


def _now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _is_expired(expires_at: datetime | None) -> bool:
    if expires_at is None:
        return False
    return _as_utc(expires_at) <= _now()


async def _require_current_parent(asset: Asset) -> Asset:
    """Reload the parent so deletion/expiry is rechecked before returning data."""
    current = await Asset.get_or_none(id=asset.id)
    if current is None:
        raise ValueError("file_not_found")
    _ensure_parent_available(current)
    return current


def _json_size(value: Any) -> int:
    # Default separators match the json.dumps used by tool response adapters.
    return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))


def _ensure_parent_available(asset: Asset) -> None:
    """Reject deleted, expired, or private text representations as input.

    Assets with a ``parent_id`` are legitimate content in their own right
    (generated images, sandbox artifacts, workflow outputs). Only the private
    document-text representation itself is non-source input.
    """
    if asset.source == AssetSource.DERIVED_TEXT:
        raise ValueError("asset_document_derived_asset")
    if asset.status != AssetStatus.AVAILABLE or asset.deleted_at is not None:
        raise ValueError("file_not_found")
    if _is_expired(asset.expires_at):
        raise ValueError("file_not_found")


def _representation_version(asset: Asset) -> str:
    """Identity of the exact source bytes and extraction contract."""
    payload = "\0".join(
        (
            REPRESENTATION_SCHEMA,
            EXTRACTION_VERSION,
            (asset.checksum or "").lower(),
            str(asset.size),
            (asset.original_filename or "").lower(),
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _representation_key(asset: Asset, version: str) -> str:
    return f"{asset.id}:{version}"


def _derived_filename(asset: Asset) -> str:
    name = asset.display_filename or asset.original_filename or "document"
    stem = name.rsplit(".", 1)[0] if "." in name else name
    return f"{stem[:495]}.txt"


def _attempt_storage_key(asset: Asset, version: str, token: str) -> str:
    # Six path segments: the public /files route only accepts four, and the
    # token makes each attempt's bytes immutable instead of a shared slot.
    return f"{STORAGE_PREFIX}/{asset.id}/{version}/{token}/text/content.txt"


def _pending_provenance(asset: Asset, version: str, token: str) -> dict[str, Any]:
    return {
        "kind": "asset_document",
        "schema": REPRESENTATION_SCHEMA,
        "state": "pending",
        "owner": token,
        "extractor_version": EXTRACTION_VERSION,
        "representation_version": version,
        "parent_checksum": (asset.checksum or "").lower(),
    }


def _failed_provenance(
    asset: Asset, version: str, token: str, error: str
) -> dict[str, Any]:
    provenance = _pending_provenance(asset, version, token)
    provenance["state"] = "failed"
    provenance["error"] = error
    return provenance


def _ready_provenance(
    provenance: dict[str, Any],
    *,
    checksum: str,
    size: int,
    total_lines: int,
    offsets: list[list[int]],
    title: str | None,
) -> dict[str, Any]:
    ready = dict(provenance)
    ready.update(
        {
            "state": "ready",
            "representation_id": checksum,
            "content_size": size,
            "total_lines": total_lines,
            "line_offsets": offsets,
            "line_checkpoint_interval": CHECKPOINT_INTERVAL,
        }
    )
    if title:
        ready["title"] = title
    else:
        ready.pop("title", None)
    return ready


def _validate_offsets(raw: Any, total_lines: int, size: int) -> list[list[int]]:
    if not isinstance(raw, list) or not raw:
        raise ValueError("asset_document_representation_invalid")
    offsets: list[list[int]] = []
    previous_line = 0
    previous_offset = -1
    for item in raw:
        if (
            not isinstance(item, (list, tuple))
            or len(item) != 2
            or type(item[0]) is not int
            or type(item[1]) is not int
        ):
            raise ValueError("asset_document_representation_invalid")
        line, offset = item
        if (
            line < 1
            or line <= previous_line
            or offset < previous_offset
            or offset > size
        ):
            raise ValueError("asset_document_representation_invalid")
        offsets.append([line, offset])
        previous_line = line
        previous_offset = offset
    if offsets[0][0] != 1 or offsets[0][1] != 0:
        raise ValueError("asset_document_representation_invalid")
    if total_lines < 1:
        raise ValueError("asset_document_representation_invalid")
    return offsets


def _ready_representation(
    parent: Asset, version: str, row: Asset
) -> _ReadyRepresentation | None:
    if row.status != AssetStatus.AVAILABLE:
        return None
    if row.parent_id != parent.id or row.source != AssetSource.DERIVED_TEXT:
        return None
    provenance = row.provenance if isinstance(row.provenance, dict) else {}
    if (
        provenance.get("kind") != "asset_document"
        or provenance.get("state") != "ready"
        or provenance.get("schema") != REPRESENTATION_SCHEMA
        or provenance.get("representation_version") != version
    ):
        return None
    expected_prefix = f"{STORAGE_PREFIX}/{parent.id}/{version}/"
    if not str(row.storage_key).startswith(expected_prefix):
        return None
    representation_id = provenance.get("representation_id")
    if (
        not isinstance(representation_id, str)
        or len(representation_id) != 64
        or representation_id != row.checksum
    ):
        return None
    if type(row.size) is not int or row.size < 0:
        return None
    if provenance.get("content_size") != row.size:
        return None
    total_lines = provenance.get("total_lines")
    if type(total_lines) is not int or total_lines < 1:
        return None
    try:
        offsets = _validate_offsets(
            provenance.get("line_offsets"), total_lines, row.size
        )
    except ValueError:
        return None
    return _ReadyRepresentation(
        row,
        checksum=representation_id,
        size=row.size,
        total_lines=total_lines,
        offsets=offsets,
    )


async def _settle_existing(
    row: Asset,
    *,
    parent: Asset,
    storage: UploadStorageBackend,
    version: str,
    deadline: float,
) -> _ReadyRepresentation:
    """Wait for, take over, or report an existing publication row."""
    while True:
        refreshed = await Asset.get_or_none(id=row.id)
        if refreshed is None:
            raise ValueError("asset_document_publication_restarted")
        ready = _ready_representation(parent, version, refreshed)
        if ready is not None:
            return ready
        if refreshed.status == AssetStatus.AVAILABLE:
            # AVAILABLE with invalid metadata is corruption, not a race.
            raise ValueError("asset_document_representation_invalid")
        if refreshed.status in {
            AssetStatus.DELETED,
            AssetStatus.EXPIRED,
        }:
            raise ValueError("file_not_found")
        can_take_over = refreshed.status == AssetStatus.FAILED
        if refreshed.status == AssetStatus.PENDING:
            can_take_over = refreshed.updated_at is not None and _as_utc(
                refreshed.updated_at
            ) <= _now() - timedelta(seconds=STALE_PENDING_SECONDS)
        if can_take_over:
            token = secrets.token_hex(16)
            attempt_key = _attempt_storage_key(parent, version, token)
            claimed = await Asset.filter(
                id=refreshed.id,
                status=refreshed.status,
                storage_key=refreshed.storage_key,
            ).update(
                status=AssetStatus.PENDING,
                storage_key=attempt_key,
                size=0,
                checksum=_ZERO_CHECKSUM,
                provenance=_pending_provenance(parent, version, token),
                updated_at=_now(),
            )
            if claimed:
                previous_key = refreshed.storage_key
                if (
                    previous_key
                    and previous_key != attempt_key
                    and str(previous_key).startswith(f"{STORAGE_PREFIX}/")
                ):
                    try:
                        await storage.delete(previous_key)
                    except Exception:  # pragma: no cover - best effort cleanup
                        pass
                return await _extract_and_publish(
                    parent,
                    storage,
                    version=version,
                    row_id=refreshed.id,
                    token=token,
                    attempt_key=attempt_key,
                )
        if asyncio.get_running_loop().time() >= deadline:
            raise ValueError("asset_document_in_progress")
        await asyncio.sleep(POLL_SECONDS)


async def _get_ready_representation(
    parent: Asset, storage: UploadStorageBackend
) -> _ReadyRepresentation:
    version = _representation_version(parent)
    representation_key = _representation_key(parent, version)
    derived_filename = _derived_filename(parent)
    deadline = asyncio.get_running_loop().time() + WAIT_SECONDS

    while True:
        row = await Asset.get_or_none(representation_key=representation_key)
        if row is not None:
            break
        token = secrets.token_hex(16)
        attempt_key = _attempt_storage_key(parent, version, token)
        try:
            row = await Asset.create(
                id=uuid4(),
                team_id=parent.team_id,
                created_by_id=parent.created_by_id,
                parent_id=parent.id,
                representation_key=representation_key,
                storage_key=attempt_key,
                original_filename=derived_filename,
                display_filename=derived_filename,
                content_type="text/plain; charset=utf-8",
                size=0,
                checksum=_ZERO_CHECKSUM,
                source=AssetSource.DERIVED_TEXT,
                status=AssetStatus.PENDING,
                expires_at=parent.expires_at,
                provenance=_pending_provenance(parent, version, token),
            )
        except IntegrityError:
            # Another process claimed the representation between our lookup
            # and insert. Loop to read its row. Bound the loop so a vanished
            # row cannot spin forever.
            if asyncio.get_running_loop().time() >= deadline:
                raise ValueError("asset_document_in_progress") from None
            await asyncio.sleep(POLL_SECONDS)
            continue
        return await _extract_and_publish(
            parent,
            storage,
            version=version,
            row_id=row.id,
            token=token,
            attempt_key=attempt_key,
        )

    return await _settle_existing(
        row,
        parent=parent,
        storage=storage,
        version=version,
        deadline=deadline,
    )


async def _extract_and_publish(
    parent: Asset,
    storage: UploadStorageBackend,
    *,
    version: str,
    row_id: UUID,
    token: str,
    attempt_key: str,
) -> _ReadyRepresentation:
    """Extract, write immutable text, then atomically mark the row ready."""
    written = False
    published = False
    try:
        source = await asset_service.read(parent, storage=storage)
        extracted = await file_parser_service.extract_file(
            source, parent.original_filename
        )
        data = extracted.text.encode("utf-8")
        checksum = hashlib.sha256(data).hexdigest()
        total_lines, offsets = _build_line_index(data)

        await storage.save(attempt_key, data, "text/plain; charset=utf-8")
        written = True

        pending = await Asset.get(id=row_id)
        pending_provenance = (
            pending.provenance if isinstance(pending.provenance, dict) else {}
        )
        if (
            pending.status != AssetStatus.PENDING
            or pending_provenance.get("owner") != token
        ):
            raise ValueError("asset_document_publication_conflict")
        provenance = _ready_provenance(
            pending_provenance,
            checksum=checksum,
            size=len(data),
            total_lines=total_lines,
            offsets=offsets,
            title=extracted.title,
        )
        updated = await Asset.filter(
            id=row_id,
            status=AssetStatus.PENDING,
            storage_key=attempt_key,
        ).update(
            status=AssetStatus.AVAILABLE,
            storage_key=attempt_key,
            size=len(data),
            checksum=checksum,
            provenance=provenance,
            expires_at=parent.expires_at,
            updated_at=_now(),
        )
        if updated != 1:
            raise ValueError("asset_document_publication_conflict")
        published = True
        row = await Asset.get(id=row_id)
        ready = _ready_representation(parent, version, row)
        if ready is None:
            raise ValueError("asset_document_representation_invalid")
        return ready
    except Exception as exc:
        if written and not published:
            try:
                await storage.delete(attempt_key)
            except Exception:  # pragma: no cover - best effort cleanup
                pass
        if not published:
            try:
                await Asset.filter(
                    id=row_id,
                    status=AssetStatus.PENDING,
                    storage_key=attempt_key,
                ).update(
                    status=AssetStatus.FAILED,
                    checksum=_ZERO_CHECKSUM,
                    provenance=_failed_provenance(
                        parent,
                        version,
                        token,
                        str(exc)[:200] or type(exc).__name__,
                    ),
                    updated_at=_now(),
                )
            except Exception:  # pragma: no cover - preserving original error
                pass
        raise


def _build_line_index(data: bytes) -> tuple[int, list[list[int]]]:
    """Return (total_lines, sparse [line, byte_offset] checkpoints)."""
    offsets: list[list[int]] = [[1, 0]]
    line = 1
    position = 0
    while True:
        newline = data.find(b"\n", position)
        if newline < 0:
            break
        position = newline + 1
        line += 1
        if (line - 1) % CHECKPOINT_INTERVAL == 0:
            offsets.append([line, position])
    return line, offsets


def _utf8_prefix(raw: bytes, limit: int) -> bytes:
    """Longest valid UTF-8 prefix of raw that fits limit bytes."""
    if len(raw) <= limit:
        return raw
    end = limit
    while end > 0 and 0x80 <= raw[end] <= 0xBF:
        end -= 1
    if end > 0:
        return raw[:end]
    # A single code point may exceed the remaining budget at the very end of
    # a read. Emit it whole so progress is guaranteed.
    for size in range(1, min(4, len(raw)) + 1):
        try:
            raw[:size].decode("utf-8")
            return raw[:size]
        except UnicodeDecodeError:
            continue
    return raw[:1]


def _encode_cursor(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(zlib.compress(raw)).decode("ascii").rstrip("=")


def _decode_cursor(
    cursor: Any,
    *,
    kind: str,
    representation_id: str,
    parent_id: str,
    version: str,
) -> dict:
    if not isinstance(cursor, str) or not cursor or len(cursor) > 2048:
        raise ValueError("asset_document_invalid_cursor")
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        compressed = base64.b64decode(
            padded.encode("ascii"), altchars=b"-_", validate=True
        )
        decoder = zlib.decompressobj()
        raw = decoder.decompress(compressed, 2049)
        if len(raw) > 2048 or not decoder.eof or decoder.unused_data:
            raise ValueError("asset_document_invalid_cursor")
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        raise ValueError("asset_document_invalid_cursor") from None
    if not isinstance(payload, dict) or payload.get("v") != 1:
        raise ValueError("asset_document_invalid_cursor")
    if (
        payload.get("k") != kind
        or payload.get("r") != representation_id
        or payload.get("p") != parent_id
        or payload.get("rv") != version
    ):
        raise ValueError("asset_document_stale_cursor")
    offset = payload.get("o")
    line = payload.get("l")
    if type(offset) is not int or offset < 0 or type(line) is not int or line < 1:
        raise ValueError("asset_document_invalid_cursor")
    return payload


async def _validate_offset(
    storage: UploadStorageBackend,
    key: str,
    size: int,
    offset: int,
    line: int,
    total_lines: int,
) -> None:
    if offset > size or line > total_lines:
        raise ValueError("asset_document_stale_cursor")
    if offset >= size:
        return
    probe = await storage.read_range(key, offset, 1)
    if probe and 0x80 <= probe[0] <= 0xBF:
        raise ValueError("asset_document_invalid_cursor")


async def _line_start(
    storage: UploadStorageBackend,
    key: str,
    representation: _ReadyRepresentation,
    start_line: int,
) -> tuple[int, int]:
    """Resolve a one-based line number to its byte offset."""
    if start_line > representation.total_lines:
        raise ValueError("asset_document_invalid_range")
    lines = [item[0] for item in representation.offsets]
    index = bisect.bisect_right(lines, start_line) - 1
    checkpoint_line, position = representation.offsets[max(index, 0)]
    remaining = start_line - checkpoint_line
    while remaining > 0:
        if position >= representation.size:
            raise ValueError("asset_document_invalid_range")
        chunk = await storage.read_range(
            key, position, min(64 * 1024, representation.size - position)
        )
        if not chunk:
            raise ValueError("asset_document_invalid_range")
        newlines = chunk.count(b"\n")
        if newlines >= remaining:
            cursor = -1
            for _ in range(remaining):
                cursor = chunk.find(b"\n", cursor + 1)
            return position + cursor + 1, start_line
        position += len(chunk)
        remaining -= newlines
    return position, start_line


async def _resolve_representation(
    asset: Asset, storage: UploadStorageBackend
) -> tuple[Asset, str, _ReadyRepresentation]:
    parent = await _require_current_parent(asset)
    version = _representation_version(parent)
    representation = await _get_ready_representation(parent, storage)
    # Publication may have waited for another process; never return data for a
    # parent that was deleted or expired in the meantime.
    parent = await _require_current_parent(parent)
    current_version = _representation_version(parent)
    if current_version != version:
        version = current_version
        representation = await _get_ready_representation(parent, storage)
        parent = await _require_current_parent(parent)
    return parent, version, representation


async def read_document(
    asset: Asset,
    *,
    storage: UploadStorageBackend,
    start_line: int = 1,
    line_count: int = 100,
    cursor: str | None = None,
) -> dict[str, Any]:
    """Read at most one bounded window of complete document lines."""
    if type(line_count) is not int or not 1 <= line_count <= MAX_LINE_COUNT:
        raise ValueError("asset_document_invalid_range")
    if type(start_line) is not int or start_line < 1:
        raise ValueError("asset_document_invalid_range")

    parent, version, representation = await _resolve_representation(asset, storage)
    key = representation.storage_key

    if cursor is None:
        offset, line = await _line_start(storage, key, representation, start_line)
    else:
        if start_line != 1:
            raise ValueError("asset_document_invalid_cursor")
        payload = _decode_cursor(
            cursor,
            kind="read",
            representation_id=representation.checksum,
            parent_id=str(parent.id),
            version=version,
        )
        offset = payload["o"]
        line = payload["l"]
        await _validate_offset(
            storage,
            key,
            representation.size,
            offset,
            line,
            representation.total_lines,
        )

    first_line = line
    segments, next_cursor, eof = await _read_segments(
        storage,
        key,
        representation_id=representation.checksum,
        parent_id=str(parent.id),
        version=version,
        size=representation.size,
        total_lines=representation.total_lines,
        offset=offset,
        line=line,
        line_count=line_count,
    )
    return {
        "asset_id": str(parent.id),
        "filename": parent.display_filename,
        "representation_id": representation.checksum,
        "start_line": first_line,
        "total_lines": representation.total_lines,
        "segments": segments,
        "next_cursor": next_cursor,
        "eof": eof,
    }


async def _read_segments(
    storage: UploadStorageBackend,
    key: str,
    *,
    representation_id: str,
    parent_id: str,
    version: str,
    size: int,
    total_lines: int,
    offset: int,
    line: int,
    line_count: int,
) -> tuple[list[dict[str, Any]], str | None, bool]:
    segments: list[dict[str, Any]] = []
    serialized_used = 2  # enclosing []
    if offset >= size:
        ends_with_newline = False
        if size:
            tail = await storage.read_range(key, size - 1, 1)
            ends_with_newline = tail == b"\n"
        if ends_with_newline and line == total_lines:
            segments.append({"line": line, "text": "", "continuation": False})
        return segments, None, True

    want = min(size - offset, MAX_READ_BYTES + 4)
    data = await storage.read_range(key, offset, want)
    if not data:
        raise RuntimeError("Stored document representation is truncated")
    reached_eof = offset + len(data) >= size
    if not reached_eof:
        # The window may end inside a multi-byte code point. Trim only the
        # partial tail; the retained byte offset makes the next cursor resume
        # exactly there.
        data = _drop_incomplete_utf8(data)
        if not data:
            raise RuntimeError("Stored document representation is truncated")

    position = 0
    eof = False

    while len(segments) < line_count:
        remaining_json = PAYLOAD_JSON_BUDGET - serialized_used
        if remaining_json <= 0 or position >= len(data):
            break
        newline = data.find(b"\n", position)
        line_ended = newline >= 0
        raw = data[position:newline] if line_ended else data[position:]
        text = _decode_bytes(raw)
        allowed = remaining_json - (2 if segments else 0)
        fitted, fits_all = _fit_segment_text(text, line, allowed)
        if not fitted and text:
            # Always make progress, even if a single escaped character needs
            # slightly more than the remaining serialized budget.
            fitted = text[:1]
            fits_all = len(fitted) == len(text)
        segment = {
            "line": line,
            "text": fitted,
            "continuation": not fits_all or (not line_ended and not reached_eof),
        }
        segment_size = _json_size(segment)
        if segments and serialized_used + 2 + segment_size > PAYLOAD_JSON_BUDGET:
            break
        serialized_used += segment_size + (2 if segments else 0)
        segments.append(segment)

        if segment["continuation"]:
            position += len(fitted.encode("utf-8"))
            break
        if line_ended:
            position = newline + 1
            line += 1
            if offset + position >= size:
                eof = True
                break
        else:
            position = len(data)
            line += 1
            eof = True
            break

    if eof and reached_eof and data.endswith(b"\n") and position == len(data):
        # A trailing newline creates a final empty line; include it so that
        # joining segments with "\n" reproduces the text exactly.
        empty_segment = {"line": line, "text": "", "continuation": False}
        separator = 2 if segments else 0
        if (
            len(segments) < line_count
            and serialized_used + separator + _json_size(empty_segment)
            <= PAYLOAD_JSON_BUDGET
        ):
            segments.append(empty_segment)
        else:
            eof = False

    next_cursor = None
    if not eof:
        next_cursor = _encode_cursor(
            {
                "v": 1,
                "k": "read",
                "r": representation_id,
                "p": parent_id,
                "rv": version,
                "o": offset + position,
                "l": line,
            }
        )
    return segments, next_cursor, eof


def _fit_segment_text(text: str, line: int, max_serialized: int) -> tuple[str, bool]:
    """Longest text prefix whose serialized segment fits the byte budget."""
    if max_serialized <= 0 or not text:
        return "", not text
    low = 0
    high = len(text)
    while low < high:
        middle = (low + high + 1) // 2
        candidate = {
            "line": line,
            "text": text[:middle],
            "continuation": True,
        }
        if _json_size(candidate) <= max_serialized:
            low = middle
        else:
            high = middle - 1
    return text[:low], low == len(text)


def _drop_incomplete_utf8(raw: bytes) -> bytes:
    """Drop a trailing partial code point from a non-final storage window."""
    decoder = codecs.getincrementaldecoder("utf-8")()
    try:
        decoder.decode(raw, final=False)
    except UnicodeDecodeError as exc:  # pragma: no cover - stored text is UTF-8
        raise RuntimeError("Stored document representation is not valid UTF-8") from exc
    pending, _ = decoder.getstate()
    return raw[: len(raw) - len(pending)] if pending else raw


def _decode_bytes(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:  # pragma: no cover - published text is UTF-8
        raise RuntimeError("Stored document representation is not valid UTF-8")


async def search_document(
    asset: Asset,
    *,
    storage: UploadStorageBackend,
    query: str,
    context_lines: int = 2,
    limit: int = 20,
    cursor: str | None = None,
) -> dict[str, Any]:
    """Streaming literal search with bounded snippets and continuation."""
    if (
        not isinstance(query, str)
        or not query
        or len(query) > MAX_QUERY_CHARS
        or "\n" in query
        or "\r" in query
    ):
        raise ValueError("asset_document_invalid_query")
    if type(context_lines) is not int or not 0 <= context_lines <= MAX_CONTEXT_LINES:
        raise ValueError("asset_document_invalid_query")
    if type(limit) is not int or not 1 <= limit <= MAX_SEARCH_LIMIT:
        raise ValueError("asset_document_invalid_query")

    parent, version, representation = await _resolve_representation(asset, storage)
    key = representation.storage_key
    query_bytes = query.encode("utf-8")
    query_hash = hashlib.sha256(query_bytes).hexdigest()[:16]

    if cursor is None:
        offset = 0
        line = 1
    else:
        payload = _decode_cursor(
            cursor,
            kind="search",
            representation_id=representation.checksum,
            parent_id=str(parent.id),
            version=version,
        )
        if (
            payload.get("q") != query_hash
            or payload.get("c") != context_lines
            or payload.get("n") != limit
        ):
            raise ValueError("asset_document_stale_cursor")
        offset = payload["o"]
        line = payload["l"]
        await _validate_offset(
            storage,
            key,
            representation.size,
            offset,
            line,
            representation.total_lines,
        )

    matches: list[dict[str, Any]] = []
    scan = offset
    base_line = line
    eof = False
    serialized_used = 2
    emitted_end = offset
    emitted_line = line
    budget_exhausted = False
    matches_budget = PAYLOAD_JSON_BUDGET

    while len(matches) < limit:
        if scan >= representation.size:
            eof = True
            break
        request = SEARCH_CHUNK_BYTES + len(query_bytes) - 1
        chunk = await storage.read_range(key, scan, request)
        if not chunk:
            raise RuntimeError("Stored document representation is truncated")
        chunk_final = len(chunk) < request
        index = 0
        last_end = 0
        while len(matches) < limit:
            found = chunk.find(query_bytes, index)
            if found < 0:
                break
            absolute = scan + found
            match_line = base_line + chunk.count(b"\n", 0, found)
            snippet = await _match_context(
                storage,
                key,
                size=representation.size,
                start=absolute,
                query=query,
                query_length=len(query_bytes),
                line=match_line,
                context_lines=context_lines,
            )
            snippet_size = _json_size(snippet) + (2 if matches else 0)
            if matches and serialized_used + snippet_size > matches_budget:
                budget_exhausted = True
                break
            matches.append(snippet)
            serialized_used += snippet_size
            emitted_end = absolute + len(query_bytes)
            emitted_line = match_line
            last_end = emitted_end
            index = found + len(query_bytes)

        if budget_exhausted:
            if emitted_end < representation.size:
                next_cursor = _encode_cursor(
                    {
                        "v": 1,
                        "k": "search",
                        "r": representation.checksum,
                        "p": str(parent.id),
                        "rv": version,
                        "o": emitted_end,
                        "l": emitted_line,
                        "q": query_hash,
                        "c": context_lines,
                        "n": limit,
                    }
                )
            else:
                next_cursor = None
                eof = True
            return _search_result(
                parent,
                representation,
                query,
                matches,
                next_cursor,
                eof,
            )

        if len(matches) >= limit:
            if emitted_end < representation.size:
                next_cursor = _encode_cursor(
                    {
                        "v": 1,
                        "k": "search",
                        "r": representation.checksum,
                        "p": str(parent.id),
                        "rv": version,
                        "o": emitted_end,
                        "l": emitted_line,
                        "q": query_hash,
                        "c": context_lines,
                        "n": limit,
                    }
                )
            else:
                eof = True
                next_cursor = None
            return _search_result(
                parent, representation, query, matches, next_cursor, eof
            )

        if chunk_final:
            eof = True
            break

        next_scan = scan + SEARCH_CHUNK_BYTES
        if last_end > next_scan:
            next_scan = last_end
        base_line += chunk.count(b"\n", 0, next_scan - scan)
        scan = next_scan

    return _search_result(
        parent, representation, query, matches, None, True if eof else False
    )


def _search_result(
    parent: Asset,
    representation: _ReadyRepresentation,
    query: str,
    matches: list[dict[str, Any]],
    next_cursor: str | None,
    eof: bool,
) -> dict[str, Any]:
    return {
        "asset_id": str(parent.id),
        "filename": parent.display_filename,
        "representation_id": representation.checksum,
        "query": query,
        "total_lines": representation.total_lines,
        "matches": matches,
        "next_cursor": next_cursor,
        "eof": eof,
    }


async def _match_context(
    storage: UploadStorageBackend,
    key: str,
    *,
    size: int,
    start: int,
    query: str,
    query_length: int,
    line: int,
    context_lines: int,
) -> dict[str, Any]:
    back_start = max(0, start - CONTEXT_WINDOW_BYTES)
    back_raw = (
        await storage.read_range(key, back_start, start - back_start)
        if start > back_start
        else b""
    )
    back_text = _decode_window(
        back_raw, drop_leading=back_start > 0, drop_trailing=False
    )
    last_newline = back_text.rfind("\n")
    if last_newline >= 0:
        prefix = back_text[last_newline + 1 :]
        before_block = back_text[:last_newline]
        before_lines = before_block.split("\n") if before_block else []
    else:
        prefix = back_text
        before_lines = []

    forward_start = start + query_length
    forward_length = min(CONTEXT_WINDOW_BYTES, size - forward_start)
    forward_raw = (
        await storage.read_range(key, forward_start, forward_length)
        if forward_length > 0
        else b""
    )
    forward_text = _decode_window(
        forward_raw,
        drop_leading=False,
        drop_trailing=forward_start + forward_length < size,
    )
    newline = forward_text.find("\n")
    if newline >= 0:
        suffix = forward_text[:newline]
        after_lines = forward_text[newline + 1 :].split("\n")
    else:
        suffix = forward_text
        after_lines = []

    center = prefix + query + suffix
    match_start = len(prefix)
    truncated = False
    if len(center) > MAX_SNIPPET_CHARS:
        window_start = max(0, match_start - MAX_SNIPPET_CHARS // 3)
        center = center[window_start : window_start + MAX_SNIPPET_CHARS]
        match_start -= window_start
        truncated = True
    match_end = min(len(center), match_start + len(query))

    before = before_lines[-context_lines:] if context_lines else []
    after = after_lines[:context_lines] if context_lines else []
    context: list[dict[str, Any]] = []
    for offset, text in enumerate(before):
        clipped, was_clipped = _clip(text, tail=True, limit=MAX_CONTEXT_SNIPPET_CHARS)
        context.append(
            {
                "line": line - len(before) + offset,
                "text": clipped,
                "truncated": was_clipped,
            }
        )
    for offset, text in enumerate(after):
        clipped, was_clipped = _clip(text, tail=False, limit=MAX_CONTEXT_SNIPPET_CHARS)
        context.append(
            {
                "line": line + 1 + offset,
                "text": clipped,
                "truncated": was_clipped,
            }
        )
    snippet = {
        "line": line,
        "text": center,
        "match_start": match_start,
        "match_end": match_end,
        "truncated": truncated,
        "context": context,
    }
    _shrink_snippet(snippet)
    return snippet


def _shrink_snippet(snippet: dict[str, Any]) -> None:
    """Trim context until even the first escaped snippet fits the payload budget."""
    if _json_size(snippet) <= SNIPPET_JSON_BUDGET:
        return
    snippet["truncated"] = True
    for entry in snippet["context"]:
        entry["text"] = entry["text"][:64]
        entry["truncated"] = True
    while snippet["context"] and _json_size(snippet) > SNIPPET_JSON_BUDGET:
        snippet["context"].pop()


def _clip(text: str, *, tail: bool, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    if tail:
        return text[-limit:], True
    return text[:limit], True


def _decode_window(raw: bytes, *, drop_leading: bool, drop_trailing: bool) -> str:
    if drop_leading:
        while raw and 0x80 <= raw[0] <= 0xBF:
            raw = raw[1:]
    if drop_trailing:
        raw = _drop_incomplete_utf8(raw)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("Stored document representation is not valid UTF-8") from exc
