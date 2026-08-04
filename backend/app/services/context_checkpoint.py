"""Active-branch model-generated context checkpoint helpers."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Sequence
from uuid import UUID

from app.core.timezone import now_utc
from app.llm import model_manager
from app.llm.token_counter import count_tokens
from app.llm.types import Message as LLMMessage
from app.llm.types import MessageRole as LLMMessageRole
from app.models.agent import (
    Agent,
    Conversation,
    ConversationContextCheckpoint,
    ConversationContextCheckpointStatus,
    Message as ConversationMessage,
    MessageRole as ConversationMessageRole,
)
from app.services.message_branching import is_message_on_active_branch

logger = logging.getLogger(__name__)

CHECKPOINT_SUMMARY_PREFIX = "Context checkpoint summary:"
CHECKPOINT_MAX_MESSAGE_CHARS = 1800
CHECKPOINT_MAX_TRANSCRIPT_CHARS = 48_000
CHECKPOINT_MAX_LIST_ITEMS = 8
CHECKPOINT_MAX_LIST_ITEM_CHARS = 320
CHECKPOINT_MAX_OVERVIEW_CHARS = 800

_SUMMARY_FIELDS = (
    "conversation_goal",
    "established_facts",
    "user_requirements",
    "constraints",
    "decisions",
    "completed_work",
    "pending_work",
    "tool_state",
    "important_artifacts",
    "open_questions",
    "latest_user_intent",
)


@dataclass(slots=True)
class CheckpointCandidate:
    """A contiguous old-history prefix and the raw tail kept after it."""

    covered_messages: list[ConversationMessage]
    retained_messages: list[ConversationMessage]
    covered_turns: int
    retained_turns: int

    @property
    def source_message_id(self) -> UUID | None:
        if not self.covered_messages:
            return None
        return self.covered_messages[-1].id


@dataclass(slots=True)
class ContextCheckpointResult:
    """Outcome of a checkpoint generation attempt."""

    checkpoint: ConversationContextCheckpoint | None = None
    created: bool = False
    covered_turns: int = 0
    retained_turns: int = 0
    error: str | None = None


def _role_value(message: ConversationMessage) -> str:
    role = getattr(message, "role", "")
    return role.value if hasattr(role, "value") else str(role)


def _message_has_media(message: ConversationMessage) -> bool:
    return bool(getattr(message, "images", None) or getattr(message, "file_urls", None))


def _message_has_tool_state(message: ConversationMessage) -> bool:
    role = _role_value(message)
    return role in {
        ConversationMessageRole.ASSISTANT.value,
        ConversationMessageRole.TOOL.value,
    } and bool(
        getattr(message, "tool_calls", None) or getattr(message, "tool_call_id", None)
    )


def _split_turn_blocks(
    messages: Sequence[ConversationMessage],
) -> list[list[ConversationMessage]]:
    blocks: list[list[ConversationMessage]] = []
    current: list[ConversationMessage] = []
    for message in messages:
        if _role_value(message) == ConversationMessageRole.USER.value:
            if current:
                blocks.append(current)
            current = [message]
        elif current:
            current.append(message)
        else:
            current = [message]
    if current:
        blocks.append(current)
    return blocks


def select_checkpoint_candidate(
    messages: Sequence[ConversationMessage],
    *,
    recent_raw_turns: int,
    recent_tool_turns: int,
    min_new_turns: int,
) -> CheckpointCandidate | None:
    """Select a contiguous prefix while retaining recent/protected turn blocks."""
    blocks = _split_turn_blocks(messages)
    if not blocks:
        return None

    keep_indexes: set[int] = set(
        range(max(len(blocks) - max(recent_raw_turns, 1), 0), len(blocks))
    )
    for index, block in enumerate(blocks):
        if any(_message_has_media(message) for message in block):
            keep_indexes.add(index)

    if recent_tool_turns > 0:
        kept_tool_turns = 0
        for index in range(len(blocks) - 1, -1, -1):
            if index not in keep_indexes and any(
                _message_has_tool_state(message) for message in blocks[index]
            ):
                keep_indexes.add(index)
                kept_tool_turns += 1
                if kept_tool_turns >= recent_tool_turns:
                    break

    # A checkpoint can only cover a prefix. Keeping the earliest protected block
    # makes the cut safe for media and tool-turn continuity.
    cut_index = min(keep_indexes) if keep_indexes else len(blocks)
    covered_blocks = blocks[:cut_index]
    retained_blocks = blocks[cut_index:]
    if len(covered_blocks) < max(min_new_turns, 1):
        return None

    return CheckpointCandidate(
        covered_messages=[message for block in covered_blocks for message in block],
        retained_messages=[message for block in retained_blocks for message in block],
        covered_turns=len(covered_blocks),
        retained_turns=len(retained_blocks),
    )


def _truncate(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 3].rstrip() + "..."


def _message_text(message: ConversationMessage) -> str:
    content = getattr(message, "content", "") or ""
    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False, default=str)
    lines = [_truncate(content, CHECKPOINT_MAX_MESSAGE_CHARS)]
    tool_calls = getattr(message, "tool_calls", None) or []
    if tool_calls:
        names: list[str] = []
        for tool_call in tool_calls:
            if isinstance(tool_call, dict):
                function = tool_call.get("function") or {}
                names.append(
                    str(function.get("name") or tool_call.get("name") or "tool")
                )
            else:
                function = getattr(tool_call, "function", None)
                names.append(str(getattr(function, "name", None) or "tool"))
        lines.append(f"TOOL_CALLS: {', '.join(names)}")
    tool_call_id = getattr(message, "tool_call_id", None)
    if tool_call_id:
        lines.append(f"TOOL_CALL_ID: {tool_call_id}")
    return "\n".join(part for part in lines if part)


def render_checkpoint_transcript(
    messages: Sequence[ConversationMessage],
    *,
    max_chars: int = CHECKPOINT_MAX_TRANSCRIPT_CHARS,
) -> str:
    """Render a bounded, non-reasoning transcript for the summarizer."""
    lines = [
        f"{_role_value(message).upper()}: {_message_text(message)}"
        for message in messages
    ]
    transcript = "\n\n".join(lines)
    if len(transcript) <= max_chars:
        return transcript
    half = max((max_chars - 80) // 2, 1)
    return (
        transcript[:half]
        + "\n...[middle transcript omitted for budget]...\n"
        + transcript[-half:]
    )


def _normalize_text(value: Any, *, max_chars: int) -> str:
    if not isinstance(value, str):
        return ""
    return _truncate(" ".join(value.split()), max_chars)


def _normalize_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        text = _normalize_text(item, max_chars=CHECKPOINT_MAX_LIST_ITEM_CHARS)
        if text and text not in normalized:
            normalized.append(text)
        if len(normalized) >= CHECKPOINT_MAX_LIST_ITEMS:
            break
    return normalized


def _parse_json_object(content: str | None) -> dict[str, Any]:
    if not content:
        return {}
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.startswith("json"):
            text = text[4:].strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("Context checkpoint summarizer did not return an object")
    return parsed


def normalize_checkpoint_payload(
    payload: dict[str, Any],
    *,
    previous_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    previous_payload = previous_payload or {}
    normalized: dict[str, Any] = {}
    for field in _SUMMARY_FIELDS:
        value = payload.get(field)
        if field in {"conversation_goal", "latest_user_intent"}:
            normalized[field] = _normalize_text(
                value or previous_payload.get(field),
                max_chars=CHECKPOINT_MAX_OVERVIEW_CHARS,
            )
        else:
            normalized[field] = _normalize_list(
                value if value is not None else previous_payload.get(field)
            )
    return normalized


def render_checkpoint_summary(payload: dict[str, Any]) -> str:
    lines = [CHECKPOINT_SUMMARY_PREFIX]
    labels = {
        "conversation_goal": "Conversation goal",
        "established_facts": "Established facts",
        "user_requirements": "User requirements",
        "constraints": "Constraints",
        "decisions": "Decisions",
        "completed_work": "Completed work",
        "pending_work": "Pending work",
        "tool_state": "Tool state",
        "important_artifacts": "Important artifacts",
        "open_questions": "Open questions",
        "latest_user_intent": "Latest user intent",
    }
    for field in _SUMMARY_FIELDS:
        value = payload.get(field)
        if not value:
            continue
        lines.append(f"{labels[field]}:")
        if isinstance(value, list):
            lines.extend(f"- {item}" for item in value)
        else:
            lines.append(str(value))
    return "\n".join(lines).strip()


def fit_checkpoint_summary(
    text: str,
    *,
    max_tokens: int,
    model_id: str,
    provider: str | None,
) -> str:
    if not text:
        return ""
    fitted = text[: max(max_tokens * 4, 256)].strip()
    while (
        fitted
        and count_tokens(fitted, model_id=model_id, provider=provider) > max_tokens
    ):
        fitted = fitted[: int(len(fitted) * 0.85)].rstrip()
    return fitted


def _build_summary_messages(
    *,
    previous_payload: dict[str, Any],
    previous_summary: str,
    transcript: str,
) -> list[LLMMessage]:
    instruction = (
        "You maintain a durable context checkpoint for continuing the same "
        "conversation. Return JSON only. Merge the previous checkpoint with "
        "the new transcript. Preserve facts needed for future answers, exact "
        "identifiers, constraints, decisions, unfinished work, important "
        "artifacts, and meaningful tool outcomes. Do not include chain-of-thought, "
        "hidden reasoning, or filler. Never invent facts.\n\n"
        "Return exactly these keys:\n"
        "conversation_goal: string\n"
        "established_facts: string[]\n"
        "user_requirements: string[]\n"
        "constraints: string[]\n"
        "decisions: string[]\n"
        "completed_work: string[]\n"
        "pending_work: string[]\n"
        "tool_state: string[]\n"
        "important_artifacts: string[]\n"
        "open_questions: string[]\n"
        "latest_user_intent: string\n"
        "Keep every list item short and concrete."
    )
    user_prompt = (
        "Previous checkpoint payload:\n"
        f"{json.dumps(previous_payload or {}, ensure_ascii=False, indent=2)}\n\n"
        "Previous rendered checkpoint:\n"
        f"{previous_summary or '(none)'}\n\n"
        "New conversation transcript covered by this checkpoint:\n"
        f"{transcript}\n\n"
        "Update the checkpoint now."
    )
    return [
        LLMMessage(role=LLMMessageRole.SYSTEM, content=instruction),
        LLMMessage(role=LLMMessageRole.USER, content=user_prompt),
    ]


async def get_ready_context_checkpoint(
    conversation_id: UUID,
) -> ConversationContextCheckpoint | None:
    """Return a ready checkpoint without treating query failures as fatal."""
    try:
        return await asyncio.wait_for(
            ConversationContextCheckpoint.filter(
                conversation_id=conversation_id,
                status=ConversationContextCheckpointStatus.READY,
            ).first(),
            timeout=2.0,
        )
    except asyncio.TimeoutError:
        logger.warning("Context checkpoint query timed out for %s", conversation_id)
    except Exception as exc:
        logger.warning(
            "Failed to query context checkpoint for %s: %s", conversation_id, exc
        )
    return None


async def get_valid_context_checkpoint(
    conversation_id: UUID,
    *,
    before_created_at=None,
) -> ConversationContextCheckpoint | None:
    """Return a checkpoint only when its watermark remains on the active branch."""
    checkpoint = await get_ready_context_checkpoint(conversation_id)
    if (
        not checkpoint
        or not checkpoint.summary_text
        or not checkpoint.covered_through_message_id
    ):
        return None
    try:
        is_active = await is_message_on_active_branch(
            conversation_id,
            checkpoint.covered_through_message_id,
            before_created_at=before_created_at,
        )
    except Exception as exc:
        logger.warning(
            "Failed to validate context checkpoint %s: %s", checkpoint.id, exc
        )
        return None
    if is_active:
        return checkpoint
    checkpoint.status = ConversationContextCheckpointStatus.STALE
    await checkpoint.save(update_fields=["status", "updated_at"])
    return None


def _message_position(message: ConversationMessage) -> tuple[Any, str]:
    return (getattr(message, "created_at", None), str(message.id))


async def _existing_checkpoint_is_newer(
    checkpoint: ConversationContextCheckpoint,
    source_message: ConversationMessage,
) -> bool:
    if not checkpoint.covered_through_message_id:
        return False
    existing_source = await ConversationMessage.filter(
        id=checkpoint.covered_through_message_id,
        conversation_id=checkpoint.conversation_id,
    ).first()
    return bool(
        existing_source
        and _message_position(existing_source) >= _message_position(source_message)
    )


async def _record_generation_failure(
    *,
    conversation: Conversation,
    source_message_id: UUID,
    error: Exception,
) -> None:
    checkpoint = await ConversationContextCheckpoint.filter(
        conversation_id=conversation.id
    ).first()
    if checkpoint is None:
        try:
            checkpoint = await ConversationContextCheckpoint.create(
                conversation_id=conversation.id,
                covered_through_message_id=source_message_id,
                status=ConversationContextCheckpointStatus.FAILED,
            )
        except Exception:
            logger.exception(
                "Could not persist failed context checkpoint for %s", conversation.id
            )
            return
    checkpoint.failure_count = (checkpoint.failure_count or 0) + 1
    checkpoint.last_error = str(error)[:2000]
    if not checkpoint.summary_text:
        checkpoint.status = ConversationContextCheckpointStatus.FAILED
    await checkpoint.save(
        update_fields=[
            "covered_through_message_id",
            "failure_count",
            "last_error",
            "status",
            "updated_at",
        ]
    )


async def create_context_checkpoint(
    *,
    agent: Agent,
    conversation: Conversation,
    messages: Sequence[ConversationMessage],
    previous_checkpoint: ConversationContextCheckpoint | None,
    model_id: str,
    tokenizer_model_id: str | None = None,
    provider: str | None,
    summary_max_tokens: int,
    recent_raw_turns: int,
    recent_tool_turns: int,
    min_new_turns: int,
    input_budget: int,
) -> ContextCheckpointResult:
    """Generate and persist a checkpoint for a contiguous old-history prefix."""
    candidate = select_checkpoint_candidate(
        messages,
        recent_raw_turns=recent_raw_turns,
        recent_tool_turns=recent_tool_turns,
        min_new_turns=min_new_turns,
    )
    if not candidate or not candidate.source_message_id:
        return ContextCheckpointResult()
    if not getattr(agent, "team_id", None):
        return ContextCheckpointResult(error="agent_team_missing")

    source_message = candidate.covered_messages[-1]
    if previous_checkpoint and await _existing_checkpoint_is_newer(
        previous_checkpoint, source_message
    ):
        return ContextCheckpointResult(checkpoint=previous_checkpoint)

    max_transcript_chars = min(
        CHECKPOINT_MAX_TRANSCRIPT_CHARS,
        max(input_budget * 2, 4_000),
    )
    transcript = render_checkpoint_transcript(
        candidate.covered_messages,
        max_chars=max_transcript_chars,
    )
    covered_tokens = count_tokens(
        transcript, model_id=tokenizer_model_id, provider=provider
    )
    if covered_tokens <= 0:
        return ContextCheckpointResult()

    previous_payload = (
        previous_checkpoint.summary_payload if previous_checkpoint else {}
    )
    previous_summary = previous_checkpoint.summary_text if previous_checkpoint else ""

    try:
        response = await model_manager.team_chat(
            team_id=str(agent.team_id),
            model_id=model_id,
            messages=_build_summary_messages(
                previous_payload=previous_payload or {},
                previous_summary=previous_summary,
                transcript=transcript,
            ),
            response_format={"type": "json_object"},
        )
        payload = normalize_checkpoint_payload(
            _parse_json_object(response.content),
            previous_payload=previous_payload,
        )
        summary_text = fit_checkpoint_summary(
            render_checkpoint_summary(payload),
            max_tokens=summary_max_tokens,
            model_id=tokenizer_model_id,
            provider=provider,
        )
        summary_tokens = count_tokens(
            summary_text,
            model_id=tokenizer_model_id,
            provider=provider,
        )
        if not summary_text or summary_tokens >= covered_tokens:
            return ContextCheckpointResult()

        checkpoint, _ = await ConversationContextCheckpoint.get_or_create(
            conversation_id=conversation.id,
            defaults={"status": ConversationContextCheckpointStatus.PENDING},
        )
        if await _existing_checkpoint_is_newer(checkpoint, source_message):
            return ContextCheckpointResult(checkpoint=checkpoint)

        checkpoint.covered_through_message_id = source_message.id
        checkpoint.status = ConversationContextCheckpointStatus.READY
        checkpoint.summary_text = summary_text
        checkpoint.summary_payload = payload
        checkpoint.token_estimate = summary_tokens
        checkpoint.summarizer_model = response.model or model_id
        checkpoint.failure_count = 0
        checkpoint.last_error = None  # type: ignore[assignment]
        checkpoint.last_summarized_at = now_utc()
        await checkpoint.save()
        return ContextCheckpointResult(
            checkpoint=checkpoint,
            created=True,
            covered_turns=candidate.covered_turns,
            retained_turns=candidate.retained_turns,
        )
    except Exception as exc:
        try:
            await _record_generation_failure(
                conversation=conversation,
                source_message_id=source_message.id,
                error=exc,
            )
        except Exception:
            logger.warning(
                "Could not record context checkpoint failure for conversation %s",
                conversation.id,
                exc_info=True,
            )
        logger.exception(
            "Context checkpoint generation failed for conversation %s", conversation.id
        )
        return ContextCheckpointResult(error=str(exc))
