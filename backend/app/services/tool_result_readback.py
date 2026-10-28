"""Authorized, bounded recovery of persisted tool results for the model.

Context compaction may replace a completed tool result with a reference so the
active round fits the model window. Persisted ``Message`` rows stay
authoritative: this module resolves one reference inside the trusted
conversation/run scope and returns the exact model-facing text in pages.

Security invariants:
- the conversation comes from the trusted tool-call context, never from model
  arguments; the actor must own that conversation;
- the row must be a ``role=tool`` result in the requested round and pass the
  existing active-branch check, so side-branch versions are unreadable;
- durable agent runs can only read their own ``active_round_id``;
- no tool is executed and no message is mutated; arguments of the original
  call (which may hold secrets) are never returned.

Reference format: ``tr1:<round_id>:<tool_call_id>``. Both halves already exist
on every persisted result row and on every ``history_override`` entry, so a
compactor can build the reference without loading the row.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from app.models.agent import Conversation, Message, MessageRole
from app.models.agent_run import AgentRun
from app.services.message_branching import is_message_on_active_branch
from app.services.tool_context import current_tool_identity
from app.utils.tool_output import (
    ASSET_VIEW_PERSISTED_KIND,
    ASSET_VIEW_PERSISTED_VERSION,
    KNOWN_OUTPUT_TOOLS,
    persisted_tool_output_parts,
)

logger = logging.getLogger(__name__)

READ_TOOL_RESULT_TOOL = "read_tool_result"

_REF_PREFIX = "tr1"
_REF_SEPARATOR = ":"
_MAX_REF_CHARS = 320
_MAX_TOOL_CALL_ID_CHARS = 200

DEFAULT_WINDOW_CHARS = 4000
MAX_WINDOW_CHARS = 8000

NOT_FOUND_ERROR = "tool_result_not_found"
ACCESS_DENIED_ERROR = "access_denied"
INVALID_REFERENCE_ERROR = "invalid_reference"
INVALID_PAGINATION_ERROR = "invalid_pagination"

_REF_HINT = "tr1:<round_id>:<tool_call_id>"

_DESCRIPTION = (
    "Recover the full persisted output of one earlier tool call when the "
    "conversation shows a compacted tool-result reference. This never re-runs "
    "the tool. Pass `ref` exactly as shown (`tr1:<round_id>:<tool_call_id>`), "
    "or `tool_call_id` for a call in the current round. Read in pages with "
    "offset/limit and continue while has_more is true."
)


def build_read_tool_result_schema() -> dict[str, Any]:
    """OpenAI-format function schema for the readback tool."""
    return {
        "type": "function",
        "function": {
            "name": READ_TOOL_RESULT_TOOL,
            "description": _DESCRIPTION,
            "parameters": {
                "type": "object",
                "properties": {
                    "ref": {
                        "type": "string",
                        "maxLength": _MAX_REF_CHARS,
                        "description": (
                            "Compacted tool-result reference in the form "
                            f"`{_REF_HINT}`."
                        ),
                    },
                    "tool_call_id": {
                        "type": "string",
                        "maxLength": _MAX_TOOL_CALL_ID_CHARS,
                        "description": (
                            "Tool call id from the current active round; only "
                            "use when no reference is shown."
                        ),
                    },
                    "offset": {
                        "type": "integer",
                        "minimum": 0,
                        "default": 0,
                        "description": "0-based character offset into the recovered text.",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_WINDOW_CHARS,
                        "default": DEFAULT_WINDOW_CHARS,
                        "description": (
                            "Maximum number of characters to return "
                            f"(1-{MAX_WINDOW_CHARS})."
                        ),
                    },
                },
            },
        },
    }


def build_definition_descriptor() -> dict[str, Any]:
    """Descriptor consumed by ``get_builtin_definition`` for the Tool row.

    ``get_builtin_definition`` expects the legacy parameter-descriptor list
    for synthetic rows (internal tools materialize with an empty list); the
    model-facing JSON Schema comes from ``build_read_tool_result_schema``.
    """
    function = build_read_tool_result_schema()["function"]
    return {
        "name": function["name"],
        "description": function["description"],
        "parameters": [],
        "definition_version": 1,
    }


def tool_result_ref(round_id: Any, tool_call_id: Any) -> str:
    """Build the canonical reference for a persisted tool result.

    ``round_id`` accepts a ``UUID`` (persisted row) or its string form
    (``history_override``). ``tool_call_id`` accepts the stored string or any
    scalar whose ``str`` form is the stored id.
    """
    if tool_call_id in (None, "") or isinstance(tool_call_id, bool):
        raise ValueError("tool_call_id is required")
    call_id = tool_call_id if isinstance(tool_call_id, str) else str(tool_call_id)
    if len(call_id) > _MAX_TOOL_CALL_ID_CHARS:
        raise ValueError("tool_call_id is invalid")
    return (
        f"{_REF_PREFIX}{_REF_SEPARATOR}{UUID(str(round_id))}{_REF_SEPARATOR}{call_id}"
    )


def parse_tool_result_ref(ref: Any) -> tuple[UUID, str]:
    """Parse ``tr1:<round_id>:<tool_call_id>``; call ids may contain colons."""
    if not isinstance(ref, str):
        raise ValueError("ref must be a string")
    value = ref.strip()
    if not value or len(value) > _MAX_REF_CHARS + 4:
        raise ValueError("ref is invalid")
    if value.lower().startswith("ref="):
        # Models often copy the marker's ``ref=...`` shape verbatim.
        value = value[4:].strip()
    if not value:
        raise ValueError("ref is invalid")
    prefix, separator, remainder = value.partition(_REF_SEPARATOR)
    if prefix != _REF_PREFIX or not separator:
        raise ValueError("ref is invalid")
    round_part, separator, call_id = remainder.partition(_REF_SEPARATOR)
    if not separator:
        raise ValueError("ref is invalid")
    call_id = call_id.strip()
    if not call_id or len(call_id) > _MAX_TOOL_CALL_ID_CHARS:
        raise ValueError("ref is invalid")
    return UUID(round_part), call_id


def model_visible_tool_result(content: Any, tool_name: str | None = None) -> str:
    """Return the text the model originally saw for a persisted result.

    ``tool.result.persisted`` envelopes store the model representation next to
    the display payload, and ``asset.view.persisted`` stores the multimodal
    marker. Both are decoded so recovery matches live context. Plain results of
    *known* tools were rendered for the model at execution time, so they go
    through the same replay summary used when history is rebuilt; unknown
    payloads stay byte-identical (presentation never guesses business fields).
    """
    if not isinstance(content, str):
        return ""
    parts = persisted_tool_output_parts(content)
    if parts is not None:
        return parts[1]
    payload = _json_object(content)
    if (
        payload is not None
        and payload.get("kind") == ASSET_VIEW_PERSISTED_KIND
        and payload.get("version") == ASSET_VIEW_PERSISTED_VERSION
    ):
        marker = payload.get("marker")
        if isinstance(marker, str):
            return marker
    if tool_name in KNOWN_OUTPUT_TOOLS:
        from app.services.chat_context import summarize_tool_result_for_llm

        return summarize_tool_result_for_llm(tool_name, content)
    return content


def _json_object(content: str) -> dict[str, Any] | None:
    if not content or not content.lstrip().startswith("{"):
        return None
    try:
        payload = json.loads(content)
    except (TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _error(code: str, message: str | None = None) -> str:
    payload: dict[str, Any] = {"error": code}
    if message:
        payload["message"] = message
    return json.dumps(payload, ensure_ascii=False)


def _pagination(arguments: dict[str, Any]) -> tuple[int, int] | str:
    raw_offset = arguments.get("offset", 0)
    raw_limit = arguments.get("limit", DEFAULT_WINDOW_CHARS)
    if isinstance(raw_offset, bool) or isinstance(raw_limit, bool):
        return _error(INVALID_PAGINATION_ERROR, "offset and limit must be integers")
    try:
        offset = int(raw_offset)
        limit = int(raw_limit)
    except (TypeError, ValueError):
        return _error(INVALID_PAGINATION_ERROR, "offset and limit must be integers")
    if offset < 0:
        return _error(INVALID_PAGINATION_ERROR, "offset must be >= 0")
    if limit < 1:
        return _error(INVALID_PAGINATION_ERROR, "limit must be >= 1")
    return offset, min(limit, MAX_WINDOW_CHARS)


async def _authorized_conversation(
    conversation_id: Any,
    actor: Any,
    agent: Any,
) -> Conversation | None:
    """Return the conversation only when the actor owns it and the agent matches."""
    actor_id = getattr(actor, "id", None)
    if actor_id is None:
        return None
    try:
        conversation_uuid = UUID(str(conversation_id))
    except (TypeError, ValueError, AttributeError):
        return None
    conversation = await Conversation.get_or_none(id=conversation_uuid)
    if conversation is None:
        return None
    if str(conversation.user_id) != str(actor_id):
        return None
    agent_id = getattr(agent, "id", None)
    if (
        agent_id is not None
        and conversation.agent_id is not None
        and str(conversation.agent_id) != str(agent_id)
    ):
        return None
    return conversation


async def _run_round_scope(
    conversation: Conversation,
    actor: Any,
    agent: Any,
) -> tuple[bool, UUID | None]:
    """Return ``(enforced, active_round_id)`` for the trusted runtime identity.

    No durable run (synchronous chat) means round-enforcement is off but the
    conversation and active-branch checks still apply. A durable workflow run
    has no ``AgentRun``/persisted conversation round, so it is enforced with no
    readable round and therefore denied.
    """
    runtime = current_tool_identity()
    run_id = getattr(runtime, "run_id", None) if runtime is not None else None
    if run_id is None:
        return False, None
    run_kind = getattr(runtime, "run_kind", "agent")
    if str(getattr(run_kind, "value", run_kind)) != "agent":
        return True, None
    try:
        run_uuid = UUID(str(run_id))
    except (TypeError, ValueError, AttributeError):
        return True, None
    run = await AgentRun.get_or_none(id=run_uuid)
    if run is None:
        return True, None
    actor_id = getattr(actor, "id", None)
    agent_id = getattr(agent, "id", None)
    if (
        str(run.conversation_id) != str(conversation.id)
        or actor_id is None
        or str(run.user_id) != str(actor_id)
        or (agent_id is not None and str(run.agent_id) != str(agent_id))
    ):
        return True, None
    return True, run.active_round_id


async def _find_result(
    *,
    conversation: Conversation,
    round_id: UUID,
    tool_call_id: str,
) -> Message | None:
    """Pick the persisted result on the active branch for one round/call pair."""
    candidates = await (
        Message.filter(
            conversation_id=conversation.id,
            role=MessageRole.TOOL,
            round_id=round_id,
            tool_call_id=tool_call_id,
            is_active=True,
        )
        .order_by("-round_index", "-created_at", "-id")
        .limit(10)
    )
    for message in candidates:
        # ``is_active`` is an implementation detail of branch activation; the
        # helper is the maintained definition of the visible branch.
        if await is_message_on_active_branch(conversation.id, message.id):
            return message
    return None


async def read_tool_result(
    arguments: dict[str, Any],
    *,
    agent: Any,
    user: Any,
    conversation_id: Any,
    workflow_run_id: Any = None,
) -> str:
    """Resolve one persisted tool result and return a bounded JSON page."""
    if not isinstance(arguments, dict):
        return _error(INVALID_REFERENCE_ERROR, "arguments must be an object")

    conversation = await _authorized_conversation(conversation_id, user, agent)
    if conversation is None:
        return _error(ACCESS_DENIED_ERROR, "conversation access denied")

    raw_ref = arguments.get("ref")
    raw_call_id = arguments.get("tool_call_id")
    if raw_ref in (None, "") and raw_call_id in (None, ""):
        return _error(
            INVALID_REFERENCE_ERROR,
            f"pass ref ({_REF_HINT}) or tool_call_id",
        )

    round_id: UUID | None = None
    call_id: str | None = None
    if raw_ref not in (None, ""):
        try:
            round_id, call_id = parse_tool_result_ref(raw_ref)
        except (TypeError, ValueError):
            return _error(INVALID_REFERENCE_ERROR, f"ref must be {_REF_HINT}")
        if raw_call_id not in (None, ""):
            supplied = raw_call_id if isinstance(raw_call_id, str) else None
            if supplied is None or supplied.strip() != call_id:
                return _error(
                    INVALID_REFERENCE_ERROR,
                    "ref and tool_call_id disagree",
                )
    else:
        if not isinstance(raw_call_id, str) or not raw_call_id.strip():
            return _error(INVALID_REFERENCE_ERROR, "tool_call_id is invalid")
        call_id = raw_call_id.strip()
        if len(call_id) > _MAX_TOOL_CALL_ID_CHARS:
            return _error(INVALID_REFERENCE_ERROR, "tool_call_id is too long")

    pagination = _pagination(arguments)
    if isinstance(pagination, str):
        return pagination
    offset, limit = pagination

    enforced, run_round = await _run_round_scope(conversation, user, agent)
    if enforced:
        if run_round is None:
            return _error(
                NOT_FOUND_ERROR,
                "no active round is readable for this run",
            )
        if round_id is None:
            round_id = run_round
        elif round_id != run_round:
            return _error(
                NOT_FOUND_ERROR,
                "the referenced result is not on this run's active round",
            )
    elif round_id is None:
        return _error(
            INVALID_REFERENCE_ERROR,
            "tool_call_id needs a durable run; pass the full ref instead",
        )

    message = await _find_result(
        conversation=conversation,
        round_id=round_id,
        tool_call_id=call_id,
    )
    if message is None:
        return _error(
            NOT_FOUND_ERROR,
            "no completed tool result matches this reference on the active branch",
        )

    content = model_visible_tool_result(message.content, message.tool_name)
    total = len(content)
    end = min(offset + limit, total)
    page = content[offset:end] if offset < total else ""
    has_more = end < total
    return json.dumps(
        {
            "ref": tool_result_ref(message.round_id, message.tool_call_id),
            "tool_name": message.tool_name,
            "tool_call_id": message.tool_call_id,
            "total_chars": total,
            "offset": offset,
            "limit": limit,
            "content": page,
            "has_more": has_more,
            "next_offset": end if has_more else None,
        },
        ensure_ascii=False,
    )


async def execute_read_tool_result(
    arguments: dict[str, Any],
    *,
    agent: Any,
    user: Any,
    conversation_id: Any,
    workflow_run_id: Any = None,
) -> str:
    """Tool-call entrypoint; always returns a JSON string, never raises."""
    try:
        return await read_tool_result(
            arguments,
            agent=agent,
            user=user,
            conversation_id=conversation_id,
            workflow_run_id=workflow_run_id,
        )
    except Exception:
        logger.exception("read_tool_result failed")
        return _error("tool_execution_failed")


__all__ = [
    "DEFAULT_WINDOW_CHARS",
    "MAX_WINDOW_CHARS",
    "READ_TOOL_RESULT_TOOL",
    "build_definition_descriptor",
    "build_read_tool_result_schema",
    "execute_read_tool_result",
    "model_visible_tool_result",
    "parse_tool_result_ref",
    "read_tool_result",
    "tool_result_ref",
]
