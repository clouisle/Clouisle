from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, call, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints.chat_helpers.version_utils import (
    build_message_out_with_versions,
    get_message_versions,
    get_version_count,
)
from app.models.agent import MessageRole, MessageRoundRole, MessageRoundStatus


def _message(**overrides):
    values = {
        "id": uuid4(),
        "conversation_id": uuid4(),
        "role": MessageRole.ASSISTANT,
        "content": "answer",
        "tool_calls": None,
        "tool_call_id": None,
        "tool_name": None,
        "reasoning_content": None,
        "model_used": None,
        "token_usage": None,
        "duration_ms": None,
        "is_manually_stopped": False,
        "rag_context": None,
        "created_at": datetime.now(UTC),
        "round_id": None,
        "round_index": 0,
        "round_role": None,
        "is_round_canonical": False,
        "iteration_index": None,
        "round_status": None,
        "parent_id": None,
        "is_active": True,
        "version_number": 1,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_get_message_versions_uses_root_and_sorts_versions():
    root = _message(version_number=1)
    child = _message(parent_id=root.id, version_number=2, is_active=False)
    newest = _message(parent_id=root.id, version_number=3)
    root_query = SimpleNamespace(all=AsyncMock(return_value=[root]))
    root_query.filter = lambda *a, **k: root_query
    children_query = SimpleNamespace(all=AsyncMock(return_value=[newest, child]))
    children_query.filter = lambda *a, **k: children_query

    with patch(
        "app.api.v1.endpoints.chat_helpers.version_utils.Message.filter",
        side_effect=[root_query, children_query],
    ) as message_filter:
        versions = await get_message_versions(child)

    assert [version.id for version in versions] == [root.id, child.id, newest.id]
    assert versions[1].is_active is False
    assert message_filter.call_args_list == [
        call(id=root.id),
        call(parent_id=root.id),
    ]


@pytest.mark.asyncio
async def test_get_version_count_includes_root_message():
    root = _message()
    query = SimpleNamespace(count=AsyncMock(return_value=2))
    query.filter = lambda *a, **k: query

    with patch(
        "app.api.v1.endpoints.chat_helpers.version_utils.Message.filter",
        return_value=query,
    ) as message_filter:
        count = await get_version_count(root)

    assert count == 3
    message_filter.assert_called_once_with(parent_id=root.id)


@pytest.mark.asyncio
async def test_get_message_versions_propagates_query_error():
    message = _message()
    query = SimpleNamespace(
        all=AsyncMock(side_effect=RuntimeError("database unavailable"))
    )

    with (
        patch(
            "app.api.v1.endpoints.chat_helpers.version_utils.Message.filter",
            return_value=query,
        ),
        pytest.raises(RuntimeError, match="database unavailable"),
    ):
        await get_message_versions(message)


@pytest.mark.asyncio
@pytest.mark.parametrize("include_versions", [False, True])
async def test_build_message_out_optionally_includes_versions(include_versions):
    message = _message(
        round_role=MessageRoundRole.ASSISTANT_FINAL,
        round_status=MessageRoundStatus.COMPLETED,
    )
    versions = [
        SimpleNamespace(
            id=message.id,
            version_number=1,
            is_active=True,
            content=message.content,
            created_at=message.created_at,
        )
    ]

    with (
        patch(
            "app.api.v1.endpoints.chat_helpers.version_utils.get_version_count",
            AsyncMock(return_value=1),
        ),
        patch(
            "app.api.v1.endpoints.chat_helpers.version_utils.get_message_versions",
            AsyncMock(return_value=versions),
        ) as get_versions,
    ):
        result = await build_message_out_with_versions(message, include_versions)

    assert result.role == "assistant"
    assert result.round_role == "assistant_final"
    assert result.round_status == "completed"
    assert result.version_count == 1
    assert (result.versions is not None) is include_versions
    assert get_versions.await_count == int(include_versions)
