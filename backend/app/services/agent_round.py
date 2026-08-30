"""Round and message persistence for the shared AgentLoop.

Intermediate assistant-step / tool-result persistence and canonical
finalization are moved out of the four duplicated chat loops into this
service. The loop calls these helpers; each entry path still prepares the
per-path branch/version bookkeeping (placeholder assistant, edited user
version, restored original path) through its own route-level hooks.

Round-structure invariants preserved from the original paths:

- user input is canonical ``round_role=user_input``,
- every model turn with tool calls persists one non-canonical
  ``round_role=assistant_step`` message carrying the ordered tool_calls,
- every executed tool call persists one non-canonical ``round_role=tool_result``
  message keyed by ``tool_call_id`` (including error results),
- the terminal assistant is canonical ``round_role=assistant_final`` with a
  ``round_status``,
- ``round_id`` is shared by the whole round and ``round_index`` is strictly
  increasing in persistence order.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from uuid import UUID

from app.models.agent import (
    Conversation,
    Message,
    MessageRole,
    MessageRoundRole,
    MessageRoundStatus,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


async def persist_assistant_step(
    *,
    conversation: Conversation,
    content: str,
    reasoning_content: str | None,
    tool_calls: list[dict[str, Any]] | None,
    model_used: str | None,
    round_id: UUID,
    round_index: int,
    iteration_index: int,
    branch_parent_id: UUID | None = None,
) -> int:
    """Persist a non-canonical assistant step carrying tool calls.

    Returns the next free round index.
    """
    await Message.create(
        conversation=conversation,
        role=MessageRole.ASSISTANT,
        content=content,
        reasoning_content=reasoning_content,
        tool_calls=tool_calls,
        model_used=model_used,
        branch_parent_id=branch_parent_id,
        round_id=round_id,
        round_index=round_index,
        round_role=MessageRoundRole.ASSISTANT_STEP,
        is_round_canonical=False,
        iteration_index=iteration_index,
    )
    return round_index + 1


async def persist_tool_result(
    *,
    conversation: Conversation,
    content: str,
    tool_call_id: str,
    tool_name: str,
    round_id: UUID,
    round_index: int,
    iteration_index: int,
    branch_parent_id: UUID | None = None,
) -> int:
    """Persist one non-canonical tool result message.

    Every tool call gets exactly one result, including error payloads.
    Returns the next free round index.
    """
    await Message.create(
        conversation=conversation,
        role=MessageRole.TOOL,
        content=content,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        branch_parent_id=branch_parent_id,
        round_id=round_id,
        round_index=round_index,
        round_role=MessageRoundRole.TOOL_RESULT,
        is_round_canonical=False,
        iteration_index=iteration_index,
    )
    return round_index + 1


async def finalize_canonical_assistant(
    *,
    assistant_msg: Message,
    content: str,
    reasoning_content: str | None,
    model_used: str | None,
    duration_ms: int,
    first_token_ms: int | None,
    token_usage: dict[str, Any],
    round_status: MessageRoundStatus,
    is_manually_stopped: bool = False,
) -> Message:
    """Update the canonical assistant with terminal content/status and save.

    The streaming paths pre-create a placeholder canonical assistant; this
    helper applies the terminal fields on it. Returns the same message.
    """
    assistant_msg.content = content
    assistant_msg.reasoning_content = reasoning_content  # type: ignore[assignment]
    assistant_msg.model_used = model_used  # type: ignore[assignment]
    assistant_msg.duration_ms = duration_ms
    assistant_msg.first_token_ms = first_token_ms
    assistant_msg.is_manually_stopped = is_manually_stopped
    assistant_msg.round_status = round_status
    assistant_msg.token_usage = token_usage
    await assistant_msg.save()
    return assistant_msg
