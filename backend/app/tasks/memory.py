"""Celery tasks and helpers for background memory extraction (Slow Track)."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any
from uuid import UUID

from celery import shared_task

from app.core.redis import get_redis
from app.core.timezone import now as tz_now
from app.models.agent import Agent, Conversation, MessageRole
from app.models.model import Model, ModelType
from app.models.site_setting import SiteSetting
from app.services.memory import MemoryService
from app.services.message_branching import (
    get_visible_conversation_messages,
    get_visible_conversation_messages_after,
)

logger = logging.getLogger(__name__)


def _get_event_loop() -> asyncio.AbstractEventLoop:
    try:
        loop = asyncio.get_event_loop_policy().get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop
    except Exception:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


def _run_async(coro: Any) -> Any:
    loop = _get_event_loop()
    if loop.is_running():  # pragma: no cover
        return asyncio.run_coroutine_threadsafe(coro, loop).result()
    return loop.run_until_complete(coro)


async def resolve_extraction_model(agent_id: UUID | str | None = None) -> str | None:
    """Resolve model ID for memory extraction using Level 1-3 fallback chain.

    Level 1: System setting memory_extraction_model_id if configured & enabled.
    Level 2: Model configured on the conversation's Agent.
    Level 3: System default chat model (is_default=True).
    Fallback: First available enabled chat model.
    """
    # Level 1: SiteSetting explicitly configured
    configured_model = await SiteSetting.get_value("memory_extraction_model_id", "")
    if configured_model and str(configured_model).strip():
        model_key = str(configured_model).strip()
        model = await Model.filter(id=model_key, is_enabled=True).first() or (
            await Model.filter(model_id=model_key, is_enabled=True).first()
        )
        if model:
            return str(model.id)
        logger.warning(
            "Configured memory extraction model '%s' not found or disabled. Falling back.",
            model_key,
        )

    # Level 2: Agent's assigned model
    if agent_id:
        try:
            agent = await Agent.get_or_none(id=UUID(str(agent_id)))
            if agent and agent.model_id:
                agent_model = await Model.filter(
                    id=agent.model_id, is_enabled=True
                ).first() or (
                    await Model.filter(model_id=agent.model_id, is_enabled=True).first()
                )
                if agent_model:
                    return str(agent_model.id)
        except Exception as e:
            logger.debug("Failed to lookup agent model for memory extraction: %s", e)

    # Level 3: System default chat model
    default_model = await Model.filter(
        model_type=ModelType.CHAT, is_enabled=True, is_default=True
    ).first()
    if default_model:
        return str(default_model.id)

    # Final fallback: any enabled chat model
    first_chat = (
        await Model.filter(model_type=ModelType.CHAT, is_enabled=True)
        .order_by("sort_order")
        .first()
    )
    if first_chat:
        return str(first_chat.id)

    return None


def _parse_extraction_json(raw_text: str) -> dict[str, Any]:
    """Extract and parse JSON payload from LLM output."""
    if not raw_text or not raw_text.strip():
        return {"entities": [], "relations": []}

    cleaned = raw_text.strip()
    # Strip markdown code blocks if present
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
    if match:
        cleaned = match.group(1).strip()

    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            entities = data.get("entities")
            relations = data.get("relations")
            return {
                "entities": entities if isinstance(entities, list) else [],
                "relations": relations if isinstance(relations, list) else [],
            }
    except Exception as e:
        logger.warning(
            "Failed to parse memory extraction JSON: %s. Raw: %s", e, raw_text[:200]
        )

    return {"entities": [], "relations": []}


async def _extract_memories_for_conversation(
    conversation_id_str: str,
    agent_id_str: str,
    user_id_str: str,
    scheduled_ts: float | None = None,
) -> dict[str, Any]:
    """Execute background memory extraction on incremental conversation turns."""
    redis = await get_redis()
    debounce_key = f"memory:extraction:scheduled:{conversation_id_str}"

    # Check debounce freshness
    if scheduled_ts is not None:
        latest_ts = await redis.get(debounce_key)
        if latest_ts:
            try:
                if float(latest_ts) > scheduled_ts:
                    logger.info(
                        "Extraction task for conversation %s debounced by newer turn",
                        conversation_id_str,
                    )
                    return {"status": "debounced"}
            except (ValueError, TypeError):
                pass

    # Check global toggle
    is_enabled = await SiteSetting.get_value("memory_async_extraction_enabled", False)
    if not is_enabled:
        return {"status": "skipped", "reason": "disabled"}

    # Acquire conversation extraction lock to prevent parallel extractions
    lock_key = f"memory:extraction:lock:{conversation_id_str}"
    acquired = await redis.set(lock_key, "1", nx=True, ex=120)
    if not acquired:
        return {"status": "locked"}

    try:
        conv_id = UUID(conversation_id_str)
        ag_id = UUID(agent_id_str)
        u_id = UUID(user_id_str)

        conversation = await Conversation.get_or_none(id=conv_id)
        if not conversation:
            return {"status": "error", "error": "conversation_not_found"}

        agent = await Agent.get_or_none(id=ag_id)
        if not agent or not getattr(agent, "enable_memory", False):
            return {"status": "skipped", "reason": "agent_memory_disabled"}

        # Fetch incremental messages
        watermark = getattr(conversation, "memory_extracted_watermark_id", None)
        if watermark:
            messages = await get_visible_conversation_messages_after(
                conv_id, after_message_id=watermark
            )
            if messages is None:
                messages = await get_visible_conversation_messages(conv_id)
        else:
            messages = await get_visible_conversation_messages(conv_id)

        if not messages:
            return {"status": "skipped", "reason": "no_messages"}

        dialogue = [
            m
            for m in messages
            if m.role in (MessageRole.USER, MessageRole.ASSISTANT)
            and isinstance(m.content, str)
            and m.content.strip()
        ]
        if not dialogue:
            return {"status": "skipped", "reason": "no_dialogue"}

        # Resolve extraction model
        model_id = await resolve_extraction_model(agent.id)
        if not model_id:
            logger.warning(
                "No extraction model available for background memory extraction"
            )
            return {"status": "skipped", "reason": "no_model_available"}

        # Format transcript
        current_time = tz_now().strftime("%Y-%m-%d %H:%M (%A)")
        transcript_lines = [
            f"{m.role.value.capitalize()}: {m.content}" for m in dialogue
        ]
        transcript_text = "\n\n".join(transcript_lines)

        system_instruction = (
            "You are a memory extraction specialist.\n"
            "Analyze the following conversation transcript and extract persistent, important knowledge about the user.\n\n"
            "Extract:\n"
            "- User preferences, habits, tools, coding style\n"
            "- User skills, expertise, programming languages\n"
            "- Projects, work, architecture, goals\n"
            "- Facts, concepts, organizations, locations associated with the user\n\n"
            f"Temporal Grounding:\n"
            f"- Current base time is {current_time}.\n"
            "- Convert all relative time expressions (e.g., 'yesterday', 'last month', 'recently', 'next year') into absolute dates or year-months.\n"
            "- Do not store words like 'yesterday' or 'recently' in descriptions.\n\n"
            "Output valid JSON adhering strictly to this schema with NO markdown wrappers:\n"
            '{\n  "entities": [\n    {"name": "...", "entity_type": "person|preference|skill|project|goal|fact|concept|organization|location|custom", "description": "...", "properties": {}}\n  ],\n  "relations": [\n    {"source_entity_name": "...", "target_entity_name": "...", "relation_type": "prefers|works_on|knows|uses|works_at|located_in|has_goal|related_to|part_of", "description": "..."}\n  ]\n}\n'
            'If no persistent user facts or preferences are shared, return {"entities": [], "relations": []}.'
        )

        from app.llm import model_manager

        response = await model_manager.chat(
            model_id=model_id,
            messages=[
                {"role": "system", "content": system_instruction},
                {
                    "role": "user",
                    "content": f"Conversation transcript:\n\n{transcript_text}\n\nExtract now:",
                },
            ],
            temperature=0.1,
        )

        extracted = _parse_extraction_json(response.content or "")
        entities_created = 0
        relations_created = 0

        for ent in extracted.get("entities", []):
            name = (ent.get("name") or "").strip()
            if not name:
                continue
            etype = ent.get("entity_type") or "fact"
            desc = ent.get("description")
            props = (
                ent.get("properties")
                if isinstance(ent.get("properties"), dict)
                else None
            )
            try:
                res = await MemoryService.handle_create_entity(
                    user_id=u_id,
                    name=name,
                    entity_type=etype,
                    description=desc,
                    properties=props,
                )
                if res.get("success"):
                    entities_created += 1
            except Exception as e:
                logger.warning("Failed to persist background entity '%s': %s", name, e)

        for rel in extracted.get("relations", []):
            src = (rel.get("source_entity_name") or "").strip()
            tgt = (rel.get("target_entity_name") or "").strip()
            rtype = rel.get("relation_type") or "related_to"
            rdesc = rel.get("description")
            if not src or not tgt:
                continue
            try:
                res = await MemoryService.handle_create_relation(
                    user_id=u_id,
                    source_entity_name=src,
                    target_entity_name=tgt,
                    relation_type=rtype,
                    description=rdesc,
                )
                if res.get("success"):
                    relations_created += 1
            except Exception as e:
                logger.warning(
                    "Failed to persist background relation '%s -> %s': %s", src, tgt, e
                )

        # Advance watermark to the last message processed
        new_watermark = messages[-1].id
        await Conversation.filter(id=conv_id).update(
            memory_extracted_watermark_id=new_watermark
        )
        await redis.delete(debounce_key)

        return {
            "status": "completed",
            "entities_created": entities_created,
            "relations_created": relations_created,
            "watermark_id": str(new_watermark),
        }
    finally:
        await redis.delete(lock_key)


@shared_task(
    name="app.tasks.memory.extract_conversation_memories_task", bind=True, max_retries=0
)
def extract_conversation_memories_task(
    self,
    conversation_id: str,
    agent_id: str,
    user_id: str,
    scheduled_ts: float | None = None,
) -> dict[str, Any]:
    """Celery task entry point for background conversation memory extraction."""
    return _run_async(
        _extract_memories_for_conversation(
            conversation_id_str=conversation_id,
            agent_id_str=agent_id,
            user_id_str=user_id,
            scheduled_ts=scheduled_ts,
        )
    )


async def schedule_background_memory_extraction(
    conversation_id: UUID,
    agent_id: UUID,
    user_id: UUID,
) -> bool:
    """Schedule debounced background memory extraction if enabled.

    Uses a hybrid trigger:
    - If unextracted user turns >= memory_extraction_max_pending_turns: triggers immediately.
    - Otherwise: schedules countdown based on memory_extraction_cooldown_seconds (default 180s)
      and sets a timestamp in Redis for debouncing.
    """
    is_enabled = await SiteSetting.get_value("memory_async_extraction_enabled", False)
    if not is_enabled:
        return False

    agent = await Agent.get_or_none(id=agent_id)
    if not agent or not getattr(agent, "enable_memory", False):
        return False

    conversation = await Conversation.get_or_none(id=conversation_id)
    if not conversation:
        return False

    watermark_id = getattr(conversation, "memory_extracted_watermark_id", None)
    if watermark_id:
        pending = await get_visible_conversation_messages_after(
            conversation_id, after_message_id=watermark_id
        )
        if pending is None:
            pending = await get_visible_conversation_messages(conversation_id)
    else:
        pending = await get_visible_conversation_messages(conversation_id)

    pending_user_turns = sum(1 for m in (pending or []) if m.role == MessageRole.USER)
    if pending_user_turns == 0:
        return False

    max_turns = int(
        await SiteSetting.get_value("memory_extraction_max_pending_turns", 6)
    )
    cooldown_seconds = int(
        await SiteSetting.get_value("memory_extraction_cooldown_seconds", 180)
    )

    redis = await get_redis()
    debounce_key = f"memory:extraction:scheduled:{conversation_id}"

    # If pending turns exceed max_turns, trigger immediately
    if pending_user_turns >= max_turns:
        await redis.delete(debounce_key)
        extract_conversation_memories_task.apply_async(
            args=[str(conversation_id), str(agent_id), str(user_id), None],
            countdown=0,
        )
        return True

    # Otherwise schedule debounced countdown
    now_ts = time.time()
    await redis.set(debounce_key, str(now_ts), ex=cooldown_seconds + 300)
    extract_conversation_memories_task.apply_async(
        args=[str(conversation_id), str(agent_id), str(user_id), now_ts],
        countdown=cooldown_seconds,
    )
    return True
