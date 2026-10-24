"""Bounded trajectory snapshots for the run execution inspector.

Rows are written at the actual model-call and tool-execution boundaries of the
AgentLoop. Writes follow the existing telemetry convention: best-effort, short
timeout, never failing or materially delaying the run. Only allowlisted
application-level request metadata is stored; transport credentials (base URL,
API keys, headers) are never serialized.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from app.models.observability_payload import ObservabilityTrajectoryEntry

logger = logging.getLogger(__name__)

MAX_ENTRY_BYTES = 256 * 1024
WRITE_TIMEOUT_SECONDS = 0.1
PREVIEW_LIMIT = 200
# Model inference parameters safe to persist. Provider credentials, headers,
# base URLs and adapter configuration are deliberately excluded.
SAFE_MODEL_PARAMS = (
    "temperature",
    "top_p",
    "top_k",
    "max_tokens",
    "max_output_tokens",
    "frequency_penalty",
    "presence_penalty",
    "seed",
    "stop",
    "reasoning_effort",
)


@dataclass(slots=True)
class ModelCallHandle:
    """Correlation handle for one in-flight model invocation."""

    entry_id: UUID
    started_at: datetime
    started_clock: float
    input_recorded: bool
    input_partial: bool
    request_preview: str | None = None


def _encode(value: Any) -> tuple[str | None, int, bool]:
    """Serialize a snapshot, dropping content over the bounded size."""
    text = (
        value
        if isinstance(value, str)
        else json.dumps(value, ensure_ascii=False, default=str)
    )
    raw = text.encode("utf-8")
    if len(raw) > MAX_ENTRY_BYTES:
        return None, len(raw), True
    return text, len(raw), False


def _decode(value: str | None) -> Any:
    if value is None:
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


def _one_line(value: Any, limit: int = PREVIEW_LIMIT) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        try:
            value = json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            value = str(value)
    collapsed = " ".join(value.split())
    if not collapsed:
        return None
    return collapsed[:limit]


def safe_model_options(model_config: Any, **overrides: Any) -> dict[str, Any]:
    """Return allowlisted inference options only.

    ``model_config`` may be an ORM Model, a mapping or None. Only
    ``default_params`` entries from the allowlist are copied, and override
    kwargs are filtered through the same allowlist, so credentials, base URLs
    and adapter config never reach the trajectory store.
    """
    params: dict[str, Any] = {}
    raw = getattr(model_config, "default_params", None)
    if raw is None and isinstance(model_config, dict):
        raw = model_config.get("default_params")
    if isinstance(raw, dict):
        for key in SAFE_MODEL_PARAMS:
            if key in raw:
                params[key] = raw[key]
    for key in SAFE_MODEL_PARAMS:
        if key in overrides and overrides[key] is not None:
            params[key] = overrides[key]
    return params


def _request_preview(messages: list[dict[str, Any]], model: str | None) -> str | None:
    for message in reversed(messages):
        if not isinstance(message, dict):
            continue
        preview = _one_line(message.get("content"))
        if preview:
            return preview
    return _one_line(model)


def serialize_tools(tools: list[Any] | None) -> list[dict[str, Any]]:
    """Return the full application tool definitions (schema included).

    Tool choice is only explainable with descriptions and parameter JSON
    schemas, so names alone are insufficient. Pydantic ``ToolDefinition``
    instances are dumped; plain OpenAI-style dicts are snapshotted as-is.
    """
    serialized: list[dict[str, Any]] = []
    for tool in tools or []:
        if isinstance(tool, dict):
            serialized.append(tool)
            continue
        dump = getattr(tool, "model_dump", None)
        if callable(dump):
            try:
                serialized.append(dump(exclude_none=True))
            except TypeError:
                serialized.append(dump())
            continue
        function = getattr(tool, "function", None)
        serialized.append(
            {
                "type": getattr(tool, "type", "function"),
                "function": {
                    "name": getattr(function, "name", None),
                    "description": getattr(function, "description", None),
                    "parameters": getattr(function, "parameters", None),
                },
            }
        )
    return serialized


async def _write(coroutine: Any) -> None:
    try:
        await asyncio.wait_for(coroutine, timeout=WRITE_TIMEOUT_SECONDS)
    except Exception:
        logger.debug("Trajectory telemetry dropped", exc_info=True)


async def record_model_request(
    *,
    run_id: UUID | str | None,
    conversation_id: UUID | str | None,
    model: str | None,
    provider: str | None,
    model_id: str | None,
    streaming: bool,
    messages: list[dict[str, Any]],
    tools: list[Any] | None,
    options: dict[str, Any],
    limits: dict[str, Any] | None = None,
    fallback: bool = False,
) -> ModelCallHandle | None:
    """Persist the application-normalized request before the provider call."""
    if run_id is None:
        return None
    entry_id = uuid4()
    now = datetime.now(UTC)
    # Snapshot immediately: later loop iterations mutate working history and
    # a tool registry entry can outlive the request.
    request = {
        # Application-level view of the messages/tools/options handed to the
        # model manager. Adapters may add transport-level parameters later;
        # this is not a byte-exact provider request.
        "scope": "application",
        "model": model,
        "model_id": model_id,
        "provider": provider,
        "streaming": streaming,
        "fallback": fallback,
        "messages": messages,
        "tools": serialize_tools(tools),
        "options": options,
        # Configured budget values, not necessarily the effective provider
        # request after adapter/agent overrides.
        "limits": limits or {},
    }
    text, size, truncated = _encode(request)
    preview = _request_preview(messages, model)
    handle = ModelCallHandle(
        entry_id=entry_id,
        started_at=now,
        started_clock=time.monotonic(),
        input_recorded=text is not None,
        input_partial=truncated,
        request_preview=preview,
    )
    await _write(
        ObservabilityTrajectoryEntry.create(
            id=entry_id,
            run_id=UUID(str(run_id)),
            conversation_id=UUID(str(conversation_id)) if conversation_id else None,
            parent_id=None,
            sequence=time.time_ns() // 1000,
            kind="model",
            name=(model or "model")[:200],
            status="running",
            started_at=now,
            model=(model or "")[:200] or None,
            tool_call_ids=[],
            payload_state="unrecorded" if text is None else "partial",
            preview=preview,
            input_text=text,
            output_text=None,
            input_bytes=size,
            output_bytes=0,
            partial=truncated,
        )
    )
    return handle


async def finish_model_call(
    handle: ModelCallHandle | None,
    *,
    status: str,
    content: str | None,
    reasoning: str | None,
    tool_calls: list[Any] | None,
    finish_reason: str | None,
    token_usage: dict[str, int] | None,
    error: str | None = None,
) -> None:
    """Record the actual response (or partial output) for one model entry."""
    if handle is None:
        return
    now = datetime.now(UTC)
    duration_ms = max(0, int((time.monotonic() - handle.started_clock) * 1000))
    serialized_calls: list[dict[str, Any]] = []
    tool_call_ids: list[str] = []
    for call in tool_calls or []:
        call_id = getattr(call, "id", None)
        function = getattr(call, "function", None)
        if not call_id:
            continue
        serialized_calls.append(
            {
                "id": call_id,
                "name": getattr(function, "name", None),
                "arguments": getattr(function, "arguments", None),
            }
        )
        tool_call_ids.append(str(call_id)[:100])
    output: dict[str, Any] = {
        "content": content or "",
        "reasoning": reasoning or "",
        "tool_calls": serialized_calls,
        "finish_reason": finish_reason,
    }
    if error:
        output["error"] = error[:300]
    output_text, output_bytes, output_truncated = _encode(output)
    partial = handle.input_partial or output_truncated or output_text is None
    if handle.input_recorded and output_text is not None and not partial:
        payload_state = "recorded"
    elif handle.input_recorded or output_text is not None:
        payload_state = "partial"
    else:
        payload_state = "unrecorded"
    preview = _one_line(content)
    if not preview and serialized_calls:
        call_names = ", ".join(
            str(call.get("name")) for call in serialized_calls if call.get("name")
        )
        first_arguments = serialized_calls[0].get("arguments")
        preview = _one_line(
            f"{call_names}({first_arguments})"
            if call_names and first_arguments
            else call_names or "tool call"
        )
    # A tool-call turn has no content; keep a useful summary instead of
    # dropping the request preview that was recorded at the boundary.
    preview = preview or _one_line(error) or handle.request_preview
    values: dict[str, Any] = {
        "status": status[:32],
        "finished_at": now,
        "duration_ms": duration_ms,
        "token_usage": token_usage,
        "tool_call_ids": tool_call_ids,
        "output_text": output_text,
        "output_bytes": output_bytes,
        "partial": partial,
        "payload_state": payload_state,
        "preview": preview,
    }
    await _write(
        ObservabilityTrajectoryEntry.filter(id=handle.entry_id).update(**values)
    )


async def record_tool_call(
    *,
    run_id: UUID | str | None,
    conversation_id: UUID | str | None,
    parent_id: UUID | None,
    tool_call_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    status: str,
    started_at: float | None,
    finished_at: float | None,
    duration_ms: int | None,
    kind: str = "tool",
) -> None:
    """Record the tool request and delegate its output to the payload table."""
    if run_id is None or not tool_call_id:
        return
    request = {
        "tool_call_id": tool_call_id[:100],
        "name": tool_name[:100],
        "arguments": arguments,
    }
    text, size, truncated = _encode(request)
    await _write(
        ObservabilityTrajectoryEntry.create(
            id=uuid4(),
            run_id=UUID(str(run_id)),
            conversation_id=UUID(str(conversation_id)) if conversation_id else None,
            parent_id=parent_id,
            sequence=time.time_ns() // 1000,
            kind=kind,
            name=(tool_name or "tool")[:200],
            status=status[:32],
            started_at=(
                datetime.fromtimestamp(started_at, UTC) if started_at else None
            ),
            finished_at=(
                datetime.fromtimestamp(finished_at, UTC) if finished_at else None
            ),
            duration_ms=duration_ms,
            tool_call_ids=[tool_call_id[:100]],
            # The output lives in observability_tool_payloads; run summaries
            # promote this state once that row is present.
            payload_state="partial" if text is not None else "unrecorded",
            preview=_one_line(
                f"{tool_name} {json.dumps(arguments, ensure_ascii=False, default=str)}"
            ),
            input_text=text,
            output_text=None,
            input_bytes=size,
            output_bytes=0,
            partial=truncated,
        )
    )


async def trajectory_entries(run_id: UUID | str, limit: int) -> list[dict[str, Any]]:
    """Load lightweight trajectory summaries for one agent run."""
    rows = await (
        ObservabilityTrajectoryEntry.filter(run_id=UUID(str(run_id)))
        .order_by("sequence", "created_at")
        .limit(limit)
        .values(
            "id",
            "parent_id",
            "kind",
            "name",
            "status",
            "started_at",
            "finished_at",
            "duration_ms",
            "model",
            "token_usage",
            "tool_call_ids",
            "payload_state",
            "preview",
            "partial",
        )
    )
    return [
        {
            "id": str(row["id"]),
            "parent_id": str(row["parent_id"]) if row["parent_id"] else None,
            "kind": row["kind"],
            "name": row["name"],
            "status": row["status"],
            "started_at": row["started_at"].isoformat() if row["started_at"] else None,
            "finished_at": row["finished_at"].isoformat()
            if row["finished_at"]
            else None,
            "duration_ms": row["duration_ms"],
            "model": row["model"],
            "token_usage": row["token_usage"],
            "tool_call_ids": list(row["tool_call_ids"] or []),
            "payload_state": row["payload_state"],
            "preview": row["preview"],
            # Internal summary-only hint used by run_detail to combine request
            # and output completeness; stripped before the API response.
            "_input_recorded": row["payload_state"] != "unrecorded"
            and not row["partial"],
        }
        for row in rows
    ]


async def load_entry(run_id: UUID | str, entry_id: UUID | str) -> Any:
    return await ObservabilityTrajectoryEntry.get_or_none(
        id=UUID(str(entry_id)), run_id=UUID(str(run_id))
    )


def entry_payload(entry: Any) -> tuple[Any, Any, bool, bool]:
    """Return ``(input, output, partial, recorded)`` for a model entry."""
    input_value = _decode(entry.input_text)
    output_value = _decode(entry.output_text)
    recorded = (
        entry.input_text is not None
        and entry.output_text is not None
        and not entry.partial
    )
    partial = entry.partial or not recorded
    return input_value, output_value, partial, recorded
