from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.agent import MessageRole
from app.services.chat_context import _build_messages_with_file_content


@pytest.mark.asyncio
async def test_auto_retrieval_injects_recalled_memories_zh_and_en(monkeypatch):
    from app.services.memory import MemoryService

    user_id = uuid4()
    agent = SimpleNamespace(
        id=uuid4(),
        system_prompt="Assistant prompt",
        enable_memory=True,
        tools_config=[],
        team_id=None,
    )
    conv = SimpleNamespace(id=uuid4(), user_id=user_id, variables={})
    user = SimpleNamespace(id=user_id)

    updated_dt = datetime(2026, 9, 8, 10, 0, tzinfo=UTC)
    entity = SimpleNamespace(
        name="Python",
        entity_type="skill",
        description="Daily usage",
        updated_at=updated_dt,
    )

    search = AsyncMock(return_value=[entity])
    monkeypatch.setattr(MemoryService, "search_entities", search)

    # 1. English locale
    messages_en, _, _ = await _build_messages_with_file_content(
        agent=agent,
        conversation=conv,
        user_message="What is my stack?",
        user_locale="en",
        file_content=None,
        history_override=[],
        current_images=None,
        model_supports_vision=False,
        current_user_message_id=None,
        include_current_user_message=True,
        exclude_message_ids=None,
        history_before_message_created_at=None,
        user=user,
    )
    system_content_en = messages_en[0].content
    assert "## Recalled User Memories" in system_content_en
    assert "- [skill] Python: Daily usage (updated: 2026-09-08)" in system_content_en

    # 2. Chinese locale
    messages_zh, _, _ = await _build_messages_with_file_content(
        agent=agent,
        conversation=conv,
        user_message="我常用什么语言？",
        user_locale="zh",
        file_content=None,
        history_override=[],
        current_images=None,
        model_supports_vision=False,
        current_user_message_id=None,
        include_current_user_message=True,
        exclude_message_ids=None,
        history_before_message_created_at=None,
        user=user,
    )
    system_content_zh = messages_zh[0].content
    assert "## 用户记忆与背景信息" in system_content_zh
    assert "- [skill] Python: Daily usage (updated: 2026-09-08)" in system_content_zh


@pytest.mark.asyncio
async def test_auto_retrieval_handles_error_and_empty_gracefully(monkeypatch):
    from app.services.memory import MemoryService

    agent = SimpleNamespace(
        id=uuid4(),
        system_prompt="Base prompt",
        enable_memory=True,
        tools_config=[],
        team_id=None,
    )
    conv = SimpleNamespace(id=uuid4(), user_id=uuid4(), variables={})

    # Search throws exception
    monkeypatch.setattr(
        MemoryService,
        "search_entities",
        AsyncMock(side_effect=RuntimeError("Qdrant offline")),
    )

    messages, _, _ = await _build_messages_with_file_content(
        agent=agent,
        conversation=conv,
        user_message="Hello",
        user_locale="en",
        file_content=None,
        history_override=[],
        current_images=None,
        model_supports_vision=False,
        current_user_message_id=None,
        include_current_user_message=True,
        exclude_message_ids=None,
        history_before_message_created_at=None,
        user=None,
    )
    # Does not crash, system prompt is built normally without error
    assert messages[0].role == MessageRole.SYSTEM
    assert "## Recalled User Memories" not in messages[0].content


@pytest.mark.asyncio
async def test_auto_retrieval_skips_when_memory_disabled(monkeypatch):
    from app.services.memory import MemoryService

    agent = SimpleNamespace(
        id=uuid4(),
        system_prompt="Base prompt",
        enable_memory=False,
        tools_config=[],
        team_id=None,
    )
    conv = SimpleNamespace(id=uuid4(), user_id=uuid4(), variables={})
    search = AsyncMock()
    monkeypatch.setattr(MemoryService, "search_entities", search)

    messages, _, _ = await _build_messages_with_file_content(
        agent=agent,
        conversation=conv,
        user_message="Hello",
        user_locale="en",
        file_content=None,
        history_override=[],
        current_images=None,
        model_supports_vision=False,
        current_user_message_id=None,
        include_current_user_message=True,
        exclude_message_ids=None,
        history_before_message_created_at=None,
        user=None,
    )
    search.assert_not_awaited()
    assert "## Recalled User Memories" not in messages[0].content
