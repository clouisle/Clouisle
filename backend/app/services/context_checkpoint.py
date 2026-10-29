"""Durable active-round semantic compaction checkpoint.

The model view of one durable AgentRun's active round can outgrow the provider
input budget. Completed tool exchanges in the *model view* are then condensed;
persisted messages remain authoritative and readable via ``read_tool_result``.

A checkpoint is advisory and scoped to the current run:

* stored in ``AgentRun.worker_payload["active_round_checkpoint"]`` — no table,
  no startup DDL, no message/summary-watermark writes;
* merged read-modify-write under ``SELECT ... FOR UPDATE`` and skipped when the
  run's ``active_round_id`` moved (restart/branch switch);
* a real LLM summary of exactly the covered complete tool groups, bound to the
  covered call ids and their content hashes. If summarization fails, nothing
  semantic is stored or claimed: the view falls back to explicit readback
  markers.

``mode="semantic"`` carries ``summary_text``; ``mode="readback_only"`` is an
honest fallback with no content assertions. Both carry per-result outcome
(``succeeded`` / ``failed`` / unconfirmed), the ref, and the content hash used
to reject stale or concurrent versions.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from app.core.timezone import now_utc

logger = logging.getLogger(__name__)

CHECKPOINT_KEY = "active_round_checkpoint"
CHECKPOINT_VERSION = 3
MAX_ENTRIES = 512
MAX_REF_CHARS = 320
MAX_TOOL_NAME_CHARS = 200
MAX_TOOL_CALL_ID_CHARS = 200
MAX_SUMMARY_CHARS = 8000

STATUS_VALUES = frozenset({"succeeded", "failed", "unconfirmed"})
_MODES = frozenset({"semantic", "readback_only"})
_MULTIMODAL_VIEW_KINDS = frozenset({"asset.view.persisted", "asset.view"})


@dataclass(frozen=True, slots=True)
class ToolResultSource:
    tool_call_id: str
    tool_name: str | None
    content: str
    round_id: UUID | str


@dataclass(slots=True)
class LoadedCheckpoint:
    """Persisted checkpoint data; empty entries mean "run exists, no summary"."""

    run_id: UUID
    round_id: str
    entries: dict[str, dict[str, Any]]
    summary_text: str | None = None
    mode: str = "readback_only"
    #: Hash of the *entire* summary source (user instruction, assistant calls
    #: and arguments, tool results) so a changed goal or call arguments cannot
    #: reuse an older summary.
    source_sha256: str | None = None
    invalid_entries: int = 0
    persisted: dict[str, Any] | None = None

    def covers(self, tool_call_ids: list[str]) -> bool:
        return bool(self.entries) and set(self.entries) == set(tool_call_ids)


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def _json_object(content: str) -> dict[str, Any] | None:
    text = content.strip()
    if not text or text[0] != "{":
        return None
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def infer_tool_result_status(
    content: Any,
) -> Literal["succeeded", "failed", "unconfirmed"]:
    """Report only what the stored result states; never assume success."""
    if not isinstance(content, str):
        return "unconfirmed"
    payload = _json_object(content)
    if payload is None:
        return "unconfirmed"
    if payload.get("success") is False:
        return "failed"
    error = payload.get("error")
    if isinstance(error, str) and error.strip():
        return "failed"
    if payload.get("success") is True:
        return "succeeded"
    return "unconfirmed"


def _is_multimodal_view(tool_name: str | None, content: Any) -> bool:
    if tool_name == "view_asset":
        return True
    if not isinstance(content, str):
        return False
    payload = _json_object(content)
    return payload is not None and payload.get("kind") in _MULTIMODAL_VIEW_KINDS


def result_reference(
    *,
    role: Any,
    tool_call_id: Any,
    round_id: Any,
    tool_name: str | None = None,
    content: Any = None,
) -> str | None:
    """Readable ref via the committed ``tool_result_ref``, or ``None``.

    ``None`` means readback cannot restore this result (multimodal view or
    incomplete round/call pair), so its content must stay in the view.
    """
    from app.services.tool_result_readback import tool_result_ref

    if getattr(role, "value", role) != "tool":
        return None
    if not isinstance(tool_call_id, str) or not tool_call_id.strip():
        return None
    if round_id in (None, ""):
        return None
    if _is_multimodal_view(tool_name, content):
        return None
    try:
        return tool_result_ref(round_id, tool_call_id)
    except (TypeError, ValueError, AttributeError):
        return None


def omission_marker(ref: str) -> str:
    return (
        "[Earlier tool result omitted from context. Use read_tool_result "
        f"with ref={ref} to read it. Do not assume its contents.]"
    )


def semantic_marker(summary_text: str, entries: list[dict[str, Any]]) -> str:
    """Checkpoint message carrying the LLM summary and exact refs/outcomes."""
    lines = [
        "[Active-round semantic checkpoint: a model-generated summary of the "
        "completed tool exchanges below. It may omit detail; the stored "
        "originals are authoritative and readable with read_tool_result.]",
        summary_text.strip(),
        "Covered tool results:",
    ]
    for entry in entries:
        lines.append(
            f"- {entry.get('tool_name') or 'tool'} call={entry['tool_call_id']} "
            f"outcome={entry.get('status')} ref={entry.get('ref')}"
        )
    return "\n".join(lines)


def content_version_hash(content: Any) -> str | None:
    if not isinstance(content, str):
        return None
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def build_entry(source: ToolResultSource) -> dict[str, Any] | None:
    """Build one covered-entry descriptor, or ``None`` if not addressable."""
    if not source.content.strip():
        return None
    ref = result_reference(
        role="tool",
        tool_call_id=source.tool_call_id,
        round_id=source.round_id,
        tool_name=source.tool_name,
        content=source.content,
    )
    if ref is None:
        return None
    return {
        "tool_call_id": source.tool_call_id,
        "tool_name": (source.tool_name or "")[:MAX_TOOL_NAME_CHARS] or None,
        "status": infer_tool_result_status(source.content),
        "ref": ref,
        "source_chars": len(source.content),
        "content_sha256": content_version_hash(source.content),
    }


def valid_entry(
    entry: Any,
    *,
    round_id: UUID | str,
    expected_tool_call_id: str | None = None,
) -> bool:
    from app.services.tool_result_readback import parse_tool_result_ref

    if not isinstance(entry, dict):
        return False
    call_id = entry.get("tool_call_id")
    if (
        not isinstance(call_id, str)
        or not call_id.strip()
        or len(call_id) > MAX_TOOL_CALL_ID_CHARS
    ):
        return False
    if expected_tool_call_id is not None and call_id != expected_tool_call_id:
        return False
    tool_name = entry.get("tool_name")
    if tool_name is not None and (
        not isinstance(tool_name, str) or len(tool_name) > MAX_TOOL_NAME_CHARS
    ):
        return False
    if entry.get("status") not in STATUS_VALUES:
        return False
    ref = entry.get("ref")
    if not isinstance(ref, str) or len(ref) > MAX_REF_CHARS:
        return False
    try:
        ref_round, ref_call = parse_tool_result_ref(ref)
        expected_round = UUID(str(round_id))
    except (TypeError, ValueError, AttributeError):
        return False
    if ref_round != expected_round or ref_call != call_id:
        return False
    content_hash = entry.get("content_sha256")
    return (
        isinstance(content_hash, str)
        and len(content_hash) == 64
        and all(char in "0123456789abcdef" for char in content_hash)
    )


def _iso(value: datetime | None = None) -> str:
    return (value or now_utc()).isoformat()


def build_payload(
    *,
    round_id: UUID | str,
    entries: list[dict[str, Any]],
    summary_text: str | None,
    mode: str,
    source_sha256: str | None = None,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the persisted payload; keeps only the newest bounded entries."""
    entries = list(entries)[-MAX_ENTRIES:]
    if not _is_sha256(source_sha256):
        source_sha256 = None
    if mode not in _MODES or (
        mode == "semantic" and (not summary_text or source_sha256 is None)
    ):
        mode = "readback_only"
        summary_text = None
        source_sha256 = None
    created_at = None
    if isinstance(previous, dict) and isinstance(previous.get("created_at"), str):
        created_at = previous["created_at"]
    return {
        "version": CHECKPOINT_VERSION,
        "round_id": str(round_id),
        "mode": mode,
        "summary_text": summary_text,
        "source_sha256": source_sha256,
        "entries": entries,
        "created_at": created_at or _iso(),
        "updated_at": _iso(),
    }


def _payload_matches(left: Any, right: Any) -> bool:
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    keys = {
        "version",
        "round_id",
        "mode",
        "summary_text",
        "source_sha256",
        "entries",
    }
    return {key: left.get(key) for key in keys} == {key: right.get(key) for key in keys}


async def _find_run(conversation_id: UUID, round_id: UUID):
    from app.models.agent_run import AgentRun

    return (
        await AgentRun.filter(
            conversation_id=conversation_id,
            active_round_id=round_id,
        )
        .order_by("-updated_at")
        .only("id", "worker_payload", "active_round_id")
        .first()
    )


async def active_branch_version_hashes(
    *,
    conversation_id: UUID,
    round_id: UUID,
    tool_call_ids: list[str],
) -> dict[str, str | None]:
    """Hash the current active-branch result generation per call id."""
    from app.models.agent import Message, MessageRole
    from app.services.chat_context import summarize_tool_result_for_llm
    from app.services.tool_result_readback import model_visible_tool_result
    from app.utils.tool_output import (
        ASSET_VIEW_PERSISTED_KIND,
        ASSET_VIEW_PERSISTED_VERSION,
    )

    wanted = [call_id for call_id in dict.fromkeys(tool_call_ids) if call_id]
    if not wanted:
        return {}
    rows = await (
        Message.filter(
            conversation_id=conversation_id,
            round_id=round_id,
            role=MessageRole.TOOL,
            tool_call_id__in=wanted,
            is_active=True,
        )
        .order_by("-round_index", "-created_at", "-id")
        .only("tool_call_id", "tool_name", "content")
    )
    versions: dict[str, str | None] = {call_id: None for call_id in wanted}
    for row in rows:
        call_id = getattr(row, "tool_call_id", None)
        if call_id in versions and versions[call_id] is None:
            content = getattr(row, "content", None)
            tool_name = getattr(row, "tool_name", None)
            payload = None
            if isinstance(content, str) and content.lstrip().startswith("{"):
                try:
                    payload = json.loads(content)
                except (TypeError, ValueError):
                    pass
            is_asset_view_envelope = (
                isinstance(payload, dict)
                and payload.get("kind") == ASSET_VIEW_PERSISTED_KIND
                and payload.get("version") == ASSET_VIEW_PERSISTED_VERSION
                and isinstance(payload.get("marker"), str)
            )
            if is_asset_view_envelope:
                model_content = model_visible_tool_result(content, tool_name)
            else:
                model_content = summarize_tool_result_for_llm(
                    tool_name, content if isinstance(content, str) else ""
                )
            versions[call_id] = content_version_hash(model_content)
    return versions


async def load_round_checkpoint(
    *,
    conversation_id: UUID,
    round_id: UUID,
) -> LoadedCheckpoint | None:
    """Load a checkpoint; ``None`` only when no durable run owns this round."""
    run = await _find_run(conversation_id, round_id)
    if run is None:
        return None
    raw = getattr(run, "worker_payload", None)
    stored = raw.get(CHECKPOINT_KEY) if isinstance(raw, dict) else None
    if (
        not isinstance(stored, dict)
        or str(stored.get("round_id")) != str(round_id)
        or stored.get("version") != CHECKPOINT_VERSION
    ):
        return LoadedCheckpoint(run_id=run.id, round_id=str(round_id), entries={})
    entries: dict[str, dict[str, Any]] = {}
    invalid = 0
    raw_entries = stored.get("entries")
    for entry in (raw_entries if isinstance(raw_entries, list) else [])[-MAX_ENTRIES:]:
        if valid_entry(entry, round_id=round_id):
            entries[entry["tool_call_id"]] = dict(entry)
        else:
            invalid += 1
    summary_text = stored.get("summary_text")
    source_sha256 = stored.get("source_sha256")
    mode = stored.get("mode")
    if not _is_sha256(source_sha256):
        source_sha256 = None
    if (
        mode != "semantic"
        or not isinstance(summary_text, str)
        or not summary_text.strip()
        or len(summary_text) > MAX_SUMMARY_CHARS
        or source_sha256 is None
    ):
        mode, summary_text = "readback_only", None
    return LoadedCheckpoint(
        run_id=run.id,
        round_id=str(round_id),
        entries=entries,
        summary_text=summary_text,
        mode=mode,
        source_sha256=source_sha256,
        invalid_entries=invalid,
        persisted=stored,
    )


async def save_round_checkpoint(
    *,
    conversation_id: UUID,
    round_id: UUID,
    entries: list[dict[str, Any]],
    summary_text: str | None,
    mode: str,
    source_sha256: str | None = None,
    previous: dict[str, Any] | None = None,
) -> str:
    """Merge the checkpoint into the owning run payload under a row lock."""
    from tortoise.transactions import in_transaction

    from app.models.agent_run import AgentRun

    payload = build_payload(
        round_id=round_id,
        entries=entries,
        summary_text=summary_text,
        mode=mode,
        source_sha256=source_sha256,
        previous=previous,
    )
    async with in_transaction() as conn:
        run = (
            await AgentRun.filter(conversation_id=conversation_id)
            .filter(active_round_id=round_id)
            .using_db(conn)
            .select_for_update()
            .order_by("-updated_at")
            .first()
        )
        if run is None or str(getattr(run, "active_round_id", None)) != str(round_id):
            return "no_run"
        raw = getattr(run, "worker_payload", None)
        worker_payload = dict(raw) if isinstance(raw, dict) else {}
        if _payload_matches(worker_payload.get(CHECKPOINT_KEY), payload):
            return "unchanged"
        worker_payload[CHECKPOINT_KEY] = payload
        run.worker_payload = worker_payload
        run.updated_at = now_utc()
        await run.save(using_db=conn, update_fields=["worker_payload", "updated_at"])
        return "updated"


__all__ = [
    "CHECKPOINT_KEY",
    "MAX_SUMMARY_CHARS",
    "LoadedCheckpoint",
    "ToolResultSource",
    "active_branch_version_hashes",
    "build_entry",
    "infer_tool_result_status",
    "load_round_checkpoint",
    "omission_marker",
    "result_reference",
    "save_round_checkpoint",
    "semantic_marker",
    "valid_entry",
]
