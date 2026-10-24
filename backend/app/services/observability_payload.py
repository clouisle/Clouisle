"""Record and read exact tool payloads for observability drill-down.

Writes are best-effort and bounded: telemetry must never slow down or fail a
tool call. Large payloads are stored once in this table only; list responses
and run summaries never load them.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any
from uuid import UUID, uuid4

from app.models.observability_payload import ObservabilityToolPayload

logger = logging.getLogger(__name__)

MAX_PAYLOAD_BYTES = 256 * 1024
# One small upsert per tool call; capped so a degraded telemetry DB cannot
# add noticeable latency to tool execution.
WRITE_TIMEOUT_SECONDS = 0.1


def _encode(value: Any) -> tuple[str | None, int]:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    raw = text.encode("utf-8")
    if len(raw) > MAX_PAYLOAD_BYTES:
        return None, len(raw)
    return text, len(raw)


def _continuation_state(payload: Any) -> tuple[bool | None, bool]:
    if not isinstance(payload, dict):
        return None, False
    eof = payload.get("eof")
    return (
        eof if isinstance(eof, bool) else None,
        isinstance(payload.get("next_cursor"), str)
        and bool(payload.get("next_cursor")),
    )


async def record_tool_payload(
    *,
    run_id: UUID | str | None,
    tool_call_id: str,
    tool_name: str,
    display_result: str,
    model_result: str,
    renderer: str | None = None,
    conversation_id: UUID | str | None = None,
    error: str | None = None,
) -> None:
    """Persist one tool payload pair without affecting tool execution."""
    if run_id is None or not tool_call_id:
        return
    try:
        display_text, display_bytes = _encode(display_result)
        model_text, model_bytes = _encode(model_result)
        try:
            payload = json.loads(display_result)
        except (TypeError, ValueError):
            payload = None
        eof, has_cursor = _continuation_state(payload)
        values = {
            "conversation_id": UUID(str(conversation_id)) if conversation_id else None,
            "tool_name": tool_name[:100],
            "display_text": display_text,
            "model_text": model_text,
            "display_bytes": display_bytes,
            "model_bytes": model_bytes,
            "model_sha256": hashlib.sha256(model_result.encode("utf-8")).hexdigest(),
            "renderer": renderer,
            "eof": eof,
            "has_cursor": has_cursor,
            "partial": display_text is None or model_text is None,
            "error": error[:200] if error else None,
        }

        async def persist() -> None:
            updated = await ObservabilityToolPayload.filter(
                run_id=UUID(str(run_id)),
                tool_call_id=tool_call_id[:100],
            ).update(**values)
            if not updated:
                await ObservabilityToolPayload.create(
                    id=uuid4(),
                    run_id=UUID(str(run_id)),
                    tool_call_id=tool_call_id[:100],
                    **values,
                )

        await asyncio.wait_for(persist(), timeout=WRITE_TIMEOUT_SECONDS)
    except Exception:
        logger.debug("Tool payload telemetry dropped", exc_info=True)


async def payload_metadata(run_id: UUID | str) -> dict[str, dict[str, Any]]:
    """Return lightweight per-tool-call metadata keyed by tool_call_id."""
    rows = await ObservabilityToolPayload.filter(run_id=UUID(str(run_id))).values(
        "tool_call_id",
        "model_bytes",
        "display_bytes",
        "model_sha256",
        "renderer",
        "eof",
        "has_cursor",
        "partial",
        "error",
    )
    return {
        str(row["tool_call_id"]): {
            "model_bytes": row["model_bytes"],
            "display_bytes": row["display_bytes"],
            "model_sha256": row["model_sha256"],
            "renderer": row["renderer"],
            "eof": row["eof"],
            "has_cursor": row["has_cursor"],
            "partial": row["partial"],
            **({"error": row["error"]} if row["error"] else {}),
        }
        for row in rows
    }


async def load_tool_payload(
    *,
    run_id: UUID | str,
    tool_call_id: str,
) -> dict[str, Any] | None:
    """Load one exact payload pair for the trace-detail view."""
    row = await ObservabilityToolPayload.get_or_none(
        run_id=UUID(str(run_id)),
        tool_call_id=tool_call_id[:100],
    )
    if row is None:
        return None
    return {
        "tool_call_id": row.tool_call_id,
        "tool_name": row.tool_name,
        "display": row.display_text,
        "model_input": row.model_text,
        "display_bytes": row.display_bytes,
        "model_bytes": row.model_bytes,
        "model_sha256": row.model_sha256,
        "renderer": row.renderer,
        "eof": row.eof,
        "has_cursor": row.has_cursor,
        "partial": row.partial,
        "error": row.error,
        "recorded": row.display_text is not None and row.model_text is not None,
    }
