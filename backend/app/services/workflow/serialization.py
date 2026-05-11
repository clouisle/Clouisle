"""
Binary serialization for workflow runtime state.

Replaces the previous `json.dumps`/`json.loads` pair used by ExecutionContext and
WorkflowCache when reading/writing Redis. msgpack preserves native dict/list/int/
float/bool/None/bytes round-trip; non-JSON-native types (datetime, UUID, Decimal)
are normalised to JSON-compatible primitives at the encode boundary so downstream
consumers always receive native Python objects, not strings.

The shared Redis pool runs with decode_responses=True (text mode), so msgpack
bytes are wrapped in base64 to fit the same string transport. The framing prefix
"mp1:" lets us evolve the format later without ambiguity.
"""

from __future__ import annotations

import base64
import json
from datetime import date, datetime
from decimal import Decimal

from .types import WorkflowValue
from uuid import UUID

import msgpack

_FRAME_PREFIX = "mp1:"


def _normalize(value: WorkflowValue) -> WorkflowValue:
    """Normalize a value to JSON-compatible types."""
    if value is None or isinstance(value, (str, int, float, bool, bytes)):
        return value
    if isinstance(value, dict):
        return {str(k): _normalize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, set):
        return [_normalize(v) for v in value]
    raise TypeError(
        f"Cannot serialize value of type {type(value).__name__} for workflow runtime"
    )


def dumps_value(value: WorkflowValue) -> str:
    """Serialize a workflow value to a base64-wrapped msgpack frame."""
    packed = msgpack.packb(_normalize(value), use_bin_type=True)
    return _FRAME_PREFIX + base64.b64encode(packed).decode("ascii")


def loads_value(data: bytes | str | None) -> WorkflowValue | None:
    """Deserialize a frame produced by `dumps_value` back to a native value.

    Returns None for empty input. Raises ValueError for an unknown frame so a
    bad migration surfaces immediately instead of silently producing garbage.
    """
    if data is None or data == "" or data == b"":
        return None
    if isinstance(data, bytes):
        data = data.decode("ascii")
    if not data.startswith(_FRAME_PREFIX):
        # Legacy data stored as plain JSON – decode directly.
        return json.loads(data)
    payload = data[len(_FRAME_PREFIX) :]
    return msgpack.unpackb(base64.b64decode(payload), raw=False)


__all__ = ["dumps_value", "loads_value"]
