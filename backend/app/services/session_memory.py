"""Conversation-scoped session memory extraction helpers."""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from app.core.timezone import now_utc
from app.core.i18n import t
from app.llm import model_manager
from app.llm.token_counter import count_tokens
from app.llm.types import Message as LLMMessage
from app.llm.types import MessageRole as LLMMessageRole
from app.models.agent import (
    Agent,
    Conversation,
    ConversationSessionMemory,
    ConversationSessionMemoryStatus,
    Message,
    MessageRole,
)
from app.models.model import TeamModel

logger = logging.getLogger(__name__)

EXTRACTION_WINDOW_TURNS = 3
MAX_TRANSCRIPT_CHARS_PER_MESSAGE = 1200
MAX_LIST_ITEMS = 6
MAX_LIST_ITEM_CHARS = 240
MAX_OVERVIEW_CHARS = 600


async def get_ready_session_memory(
    conversation_id: UUID,
) -> ConversationSessionMemory | None:
    """Return the ready snapshot for a conversation, if any."""
    import asyncio

    try:
        return await asyncio.wait_for(
            ConversationSessionMemory.filter(
                conversation_id=conversation_id,
                status=ConversationSessionMemoryStatus.READY,
            ).first(),
            timeout=2.0,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "Session memory query timed out for conversation %s",
            conversation_id,
        )
        return None
    except Exception as e:
        logger.warning(
            "Failed to query session memory for conversation %s: %s",
            conversation_id,
            str(e),
        )
        return None


async def extract_session_memory_for_message(
    conversation_id: UUID | str,
    source_message_id: UUID | str,
) -> dict[str, Any]:
    """Extract and upsert a conversation-scoped session memory snapshot."""
    conversation_uuid = UUID(str(conversation_id))
    source_uuid = UUID(str(source_message_id))

    conversation = await Conversation.filter(id=conversation_uuid).first()
    if not conversation or not conversation.agent_id:
        logger.warning(
            "Skip session memory extraction: conversation %s not found or "
            "agent missing",
            conversation_uuid,
        )
        return {"status": "skipped", "reason": "conversation_not_found"}

    agent = (
        await Agent.filter(id=conversation.agent_id)
        .prefetch_related("team")
        .first()
    )
    if not agent:
        logger.warning(
            "Skip session memory extraction: agent %s not found for conversation %s",
            conversation.agent_id,
            conversation_uuid,
        )
        return {"status": "skipped", "reason": "agent_not_found"}

    from app.services.chat_context import get_context_compression_config

    compression_config = get_context_compression_config(agent)
    if not compression_config.get("session_memory_enabled", True):
        return {"status": "skipped", "reason": "session_memory_disabled"}
    if not compression_config.get("session_memory_async_extract", True):
        return {"status": "skipped", "reason": "async_extract_disabled"}

    source_message = await Message.filter(
        id=source_uuid,
        conversation_id=conversation_uuid,
        is_active=True,
    ).first()
    if not source_message or source_message.role != MessageRole.ASSISTANT:
        logger.warning(
            "Skip session memory extraction: source message %s invalid for "
            "conversation %s",
            source_uuid,
            conversation_uuid,
        )
        return {"status": "skipped", "reason": "invalid_source_message"}

    history = await Message.filter(
        conversation_id=conversation_uuid,
        is_active=True,
        created_at__lte=source_message.created_at,
    ).order_by("created_at")

    turn_blocks = _split_turn_blocks(history)
    min_turns = int(compression_config.get("session_memory_min_turns", 4) or 4)
    if len(turn_blocks) < min_turns:
        return {
            "status": "skipped",
            "reason": "insufficient_turns",
            "turns": len(turn_blocks),
        }

    snapshot = await ConversationSessionMemory.filter(
        conversation_id=conversation_uuid
    ).first()
    if snapshot and snapshot.source_message_id == source_uuid:
        if snapshot.status == ConversationSessionMemoryStatus.READY:
            return {"status": "skipped", "reason": "already_extracted"}

    if snapshot and snapshot.source_message_id:
        existing_source = await Message.filter(
            id=snapshot.source_message_id,
            conversation_id=conversation_uuid,
        ).first()
        if (
            existing_source
            and snapshot.status == ConversationSessionMemoryStatus.READY
            and existing_source.created_at > source_message.created_at
        ):
            return {"status": "skipped", "reason": "outdated_task"}

    if snapshot is None:
        snapshot = await ConversationSessionMemory.create(
            conversation_id=conversation_uuid,
            source_message_id=source_uuid,
            status=ConversationSessionMemoryStatus.PENDING,
        )

    previous_payload = snapshot.snapshot_payload or {}
    previous_summary = snapshot.summary_text or ""
    transcript = _render_transcript(turn_blocks[-EXTRACTION_WINDOW_TURNS:])

    team_model = None
    if agent.model_id:
        team_model = (
            await TeamModel.filter(id=agent.model_id)
            .prefetch_related("model")
            .first()
        )
    model_identifier = _get_model_identifier(team_model)
    tokenizer_model_id = team_model.model.model_id if team_model else "gpt-4"
    tokenizer_provider = team_model.model.provider if team_model else None

    try:
        response = await model_manager.team_chat(
            team_id=str(agent.team_id),
            model_id=model_identifier,
            messages=_build_extraction_messages(
                previous_payload=previous_payload,
                previous_summary=previous_summary,
                transcript=transcript,
            ),  # type: ignore[arg-type]
            response_format={"type": "json_object"},
        )
        payload = _normalize_snapshot_payload(
            _parse_json_object(response.content),
            previous_payload=previous_payload,
        )
        summary_text = _render_summary_text(payload)
        summary_text = _fit_summary_to_budget(
            summary_text,
            max_tokens=int(
                compression_config.get("session_memory_max_tokens", 400) or 400
            ),
            model_id=tokenizer_model_id,
            provider=tokenizer_provider,
        )
        token_estimate = count_tokens(
            summary_text,
            model_id=tokenizer_model_id,
            provider=tokenizer_provider,
        )

        snapshot.source_message_id = source_uuid
        snapshot.status = ConversationSessionMemoryStatus.READY
        snapshot.summary_text = summary_text
        snapshot.snapshot_payload = payload
        snapshot.token_estimate = token_estimate
        snapshot.extractor_model = response.model or model_identifier
        snapshot.failure_count = 0
        snapshot.last_error = None  # type: ignore[assignment]
        snapshot.last_extracted_at = now_utc()
        await snapshot.save()

        logger.info(
            "Session memory extracted for conversation %s from assistant message %s",
            conversation_uuid,
            source_uuid,
        )
        return {
            "status": "success",
            "conversation_id": str(conversation_uuid),
            "source_message_id": str(source_uuid),
            "token_estimate": token_estimate,
        }
    except Exception as e:
        snapshot.source_message_id = source_uuid
        snapshot.failure_count = (snapshot.failure_count or 0) + 1
        snapshot.last_error = str(e)[:2000]
        snapshot.status = (
            ConversationSessionMemoryStatus.STALE
            if snapshot.summary_text
            else ConversationSessionMemoryStatus.FAILED
        )
        await snapshot.save(update_fields=[
            "source_message_id",
            "failure_count",
            "last_error",
            "status",
            "updated_at",
        ])
        logger.exception(
            "Session memory extraction failed for conversation %s message %s",
            conversation_uuid,
            source_uuid,
        )
        return {
            "status": "error",
            "conversation_id": str(conversation_uuid),
            "source_message_id": str(source_uuid),
            "error": t("llm_processing_failed"),
        }


def _get_model_identifier(team_model: TeamModel | None) -> str | None:
    if not team_model or not getattr(team_model, "model", None):
        return None
    return f"{team_model.model.provider}/{team_model.model.model_id}"


def _build_extraction_messages(
    *,
    previous_payload: dict[str, Any],
    previous_summary: str,
    transcript: str,
) -> list[LLMMessage]:
    instruction = (
        "You maintain a conversation-scoped session memory snapshot for "
        "future context compaction. Return JSON only. Merge the existing "
        "snapshot with the recent conversation window. Keep only facts that "
        "help continue this same conversation. Do not include "
        "chain-of-thought, hidden reasoning, or filler.\n\n"
        "Return an object with exactly these keys:\n"
        "overview: string\n"
        "user_preferences: string[]\n"
        "constraints: string[]\n"
        "decisions: string[]\n"
        "open_questions: string[]\n"
        "recent_tools: string[]\n"
        "latest_focus: string[]\n\n"
        "Rules:\n"
        "- Keep overview under 120 words.\n"
        "- Keep each list item short and concrete.\n"
        "- Prefer durable conversation state over transient phrasing.\n"
        "- Do not invent facts that are not in the snapshot or transcript."
    )
    user_prompt = (
        "Existing snapshot payload:\n"
        f"{json.dumps(previous_payload or {}, ensure_ascii=False, indent=2)}\n\n"
        "Existing rendered summary:\n"
        f"{previous_summary or '(none)'}\n\n"
        "Recent conversation window:\n"
        f"{transcript}\n\n"
        "Update the snapshot now."
    )
    return [
        LLMMessage(role=LLMMessageRole.SYSTEM, content=instruction),
        LLMMessage(role=LLMMessageRole.USER, content=user_prompt),
    ]


def _parse_json_object(content: str | None) -> dict[str, Any]:
    if not content:
        return {}
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("Session memory extractor did not return a JSON object")
    return parsed


def _normalize_snapshot_payload(
    payload: dict[str, Any],
    *,
    previous_payload: dict[str, Any],
) -> dict[str, Any]:
    overview = _normalize_text(
        payload.get("overview") or previous_payload.get("overview"),
        max_chars=MAX_OVERVIEW_CHARS,
    )
    return {
        "overview": overview,
        "user_preferences": _normalize_list(
            payload.get("user_preferences"),
            fallback=previous_payload.get("user_preferences"),
        ),
        "constraints": _normalize_list(
            payload.get("constraints"),
            fallback=previous_payload.get("constraints"),
        ),
        "decisions": _normalize_list(
            payload.get("decisions"),
            fallback=previous_payload.get("decisions"),
        ),
        "open_questions": _normalize_list(
            payload.get("open_questions"),
            fallback=previous_payload.get("open_questions"),
        ),
        "recent_tools": _normalize_list(
            payload.get("recent_tools"),
            fallback=previous_payload.get("recent_tools"),
        ),
        "latest_focus": _normalize_list(
            payload.get("latest_focus"),
            fallback=previous_payload.get("latest_focus"),
        ),
    }


def _render_summary_text(payload: dict[str, Any]) -> str:
    lines: list[str] = ["Conversation session memory"]

    overview = payload.get("overview")
    if overview:
        lines.append(f"Overview: {overview}")

    sections = [
        ("User preferences", payload.get("user_preferences") or []),
        ("Constraints", payload.get("constraints") or []),
        ("Decisions", payload.get("decisions") or []),
        ("Open questions", payload.get("open_questions") or []),
        ("Recent tools", payload.get("recent_tools") or []),
        ("Latest focus", payload.get("latest_focus") or []),
    ]
    for title, items in sections:
        if not items:
            continue
        lines.append(f"{title}:")
        lines.extend(f"- {item}" for item in items)

    return "\n".join(lines).strip()


def _fit_summary_to_budget(
    text: str,
    *,
    max_tokens: int,
    model_id: str,
    provider: str | None,
) -> str:
    if not text:
        return ""

    fitted = text[: max(max_tokens * 4, 256)].strip()
    while fitted and count_tokens(
        fitted, model_id=model_id, provider=provider
    ) > max_tokens:
        fitted = fitted[: int(len(fitted) * 0.85)].rstrip()

    return fitted


def _split_turn_blocks(messages: list[Message]) -> list[list[Message]]:
    blocks: list[list[Message]] = []
    current_block: list[Message] = []

    for message in messages:
        if message.role == MessageRole.USER and current_block:
            blocks.append(current_block)
            current_block = [message]
            continue
        current_block.append(message)

    if current_block:
        blocks.append(current_block)

    return blocks


def _render_transcript(blocks: list[list[Message]]) -> str:
    lines: list[str] = []
    for index, block in enumerate(blocks, start=1):
        lines.append(f"## Turn {index}")
        for message in block:
            role = str(message.role).split(".")[-1].upper()
            content = _format_message_content(message)
            if content:
                lines.append(f"{role}: {content}")
            if message.role == MessageRole.ASSISTANT and message.tool_calls:
                tool_names: list[str] = [
                    call["name"]
                    for call in message.tool_calls
                    if isinstance(call, dict) and call.get("name")
                ]
                if tool_names:
                    lines.append(
                        "ASSISTANT_TOOL_CALLS: "
                        + ", ".join(tool_names[:MAX_LIST_ITEMS])
                    )
        lines.append("")
    return "\n".join(lines).strip()


def _format_message_content(message: Message) -> str:
    content = message.content or ""
    if message.role == MessageRole.TOOL:
        from app.services.chat_context import summarize_tool_result_for_llm

        content = summarize_tool_result_for_llm(message.tool_name, content)
    return _truncate_text(content, MAX_TRANSCRIPT_CHARS_PER_MESSAGE)


def _normalize_list(value: Any, *, fallback: Any = None) -> list[str]:
    source = value if isinstance(value, list) and value else fallback
    if not isinstance(source, list):
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for item in source:
        text = _normalize_text(item, max_chars=MAX_LIST_ITEM_CHARS)
        if not text:
            continue
        dedupe_key = text.casefold()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized.append(text)
        if len(normalized) >= MAX_LIST_ITEMS:
            break
    return normalized


def _normalize_text(value: Any, *, max_chars: int) -> str:
    if not isinstance(value, str):
        return ""
    text = " ".join(value.split()).strip()
    if not text:
        return ""
    return _truncate_text(text, max_chars)


def _truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."
