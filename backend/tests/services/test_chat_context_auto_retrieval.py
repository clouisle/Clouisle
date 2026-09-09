"""Test memory auto-retrieval is disabled in favor of agentic tool calls."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.chat_context import (
    _build_messages_with_file_content,
)


@pytest.mark.asyncio
async def test_auto_retrieval_is_disabled_with_enable_memory_true(monkeypatch):
    """Verify automatic memory retrieval is disabled even when enable_memory=True."""
    from app.services.memory import MemoryService

    user_id = uuid4()
    agent = SimpleNamespace(
        id=uuid4(),
        enable_memory=True,
        enable_user_input_request=False,
        system_prompt="Base prompt",
    )
    conv = SimpleNamespace(id=uuid4(), user_id=user_id, variables={})
    user = SimpleNamespace(id=user_id)

    # Mock MemoryService to verify it's not called
    search = AsyncMock(return_value=[])
    monkeypatch.setattr(MemoryService, "search_entities", search)

    # Mock conversation history to avoid DB dependency
    get_messages = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "app.services.chat_context.get_visible_conversation_messages", get_messages
    )

    messages, _, _ = await _build_messages_with_file_content(
        agent=agent,
        conversation=conv,
        user_message="Test query",
        file_content=None,
        user_locale="en",
        history_override=None,
        current_images=None,
        model_supports_vision=False,
        current_user_message_id=None,
        include_current_user_message=False,
        exclude_message_ids=None,
        history_before_message_created_at=None,
        tool_timeouts=None,
        user=user,
        protected_round_id=None,
        context_summary_text=None,
        history_after_message_id=None,
    )

    # Verify MemoryService.search_entities was NOT called
    search.assert_not_awaited()

    # Verify system prompt does not contain auto-injected memories
    system_content = messages[0].content
    assert "## Recalled User Memories" not in system_content
    assert "## 用户记忆与背景信息" not in system_content
