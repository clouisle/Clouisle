"""Celery tasks for conversation-scoped session memory extraction."""

import logging
from uuid import UUID

from celery import shared_task

from app.services.session_memory import extract_session_memory_for_message

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def extract_session_memory_task(
    self,
    conversation_id: str,
    source_message_id: str,
) -> dict:
    """Extract or refresh session memory after a final assistant reply is persisted."""
    import asyncio

    async def _extract() -> dict:
        return await extract_session_memory_for_message(
            conversation_id=UUID(conversation_id),
            source_message_id=UUID(source_message_id),
        )

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    try:
        return loop.run_until_complete(_extract())
    except Exception as e:
        logger.exception(
            "Session memory extraction task failed for conversation %s message %s: %s",
            conversation_id,
            source_message_id,
            e,
        )
        raise
