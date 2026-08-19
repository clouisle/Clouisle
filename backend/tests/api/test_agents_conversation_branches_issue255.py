from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import agents
from starlette.requests import Request


class Query:
    def __init__(self, value):
        self.value = value
        self.calls = []

    def _chain(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))
        return self

    def prefetch_related(self, *args):
        return self._chain("prefetch_related", *args)

    async def first(self):
        return self.value

    async def update(self, **kwargs):
        return self._chain("update", **kwargs)


@pytest.mark.anyio
async def test_get_conversation_without_messages_skips_version_query(monkeypatch):
    conversation = SimpleNamespace(
        id=uuid4(),
        agent=None,
        title=None,
        variables={},
        message_count=0,
        token_usage=0,
        created_at=None,
        updated_at=None,
    )
    monkeypatch.setattr(
        agents.Conversation, "filter", lambda **_kwargs: Query(conversation)
    )
    monkeypatch.setattr(
        agents, "get_visible_conversation_messages", AsyncMock(return_value=[])
    )
    message_filter = AsyncMock()
    monkeypatch.setattr(agents.Message, "filter", message_filter)
    monkeypatch.setattr(
        agents, "build_message_round_payloads", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        agents.ConversationOut,
        "model_validate",
        lambda _value: SimpleNamespace(model_dump=lambda: {"id": conversation.id}),
    )

    result = await agents.get_conversation(conversation.id, SimpleNamespace())

    assert result["data"]["messages"] == []
    assert result["data"]["agent_name"] is None
    message_filter.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("token_usage", "expected_tokens"),
    [({"prompt": 7}, 7), ({"completion": 5}, 5)],
)
async def test_delete_message_defaults_missing_token_usage_counters(
    monkeypatch, token_usage, expected_tokens
):
    conversation = SimpleNamespace(id=uuid4())
    message = SimpleNamespace(id=uuid4(), token_usage=token_usage, delete=AsyncMock())
    conversation_query = Query(conversation)
    monkeypatch.setattr(
        agents.Conversation, "filter", lambda **_kwargs: conversation_query
    )
    monkeypatch.setattr(agents.Message, "filter", lambda **_kwargs: Query(message))
    monkeypatch.setattr(agents.AuditLogService, "log", AsyncMock())

    request = Request(
        {
            "type": "http",
            "method": "DELETE",
            "path": "/conversations",
            "headers": [],
            "query_string": b"",
        }
    )
    await agents.delete_message(conversation.id, message.id, request, SimpleNamespace())

    update = next(call for call in conversation_query.calls if call[0] == "update")
    assert update[2]["token_usage"].right.value == expected_tokens
    message.delete.assert_awaited_once()
