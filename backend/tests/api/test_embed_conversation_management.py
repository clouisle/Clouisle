"""Boundary tests for embed conversation rename and delete.

Embed history is key-scoped: a conversation is only reachable by the exact
credential that created it, so the mutation routes reuse the same filter as the
read route and answer a plain 404 otherwise.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from starlette.datastructures import Headers
from starlette.requests import Request

from app.api.v1.endpoints import agents as agents_endpoints
from app.api.v1.endpoints import embed
from app.schemas.agent import ConversationUpdate
from app.schemas.response import BusinessError, ResponseCode


class Query:
    def __init__(self, result):
        self.result = result

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self.result


def request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "PATCH",
            "path": "/embed",
            "headers": Headers({}).raw,
            "query_string": b"",
        }
    )


def conversation(*, title: str | None = "Title") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        title=title,
        save=AsyncMock(),
    )


def assert_error(exc_info, code: ResponseCode, status_code: int) -> None:
    assert exc_info.value.code == code
    assert exc_info.value.status_code == status_code


@pytest.mark.anyio
async def test_rename_embed_conversation_updates_owned_row(monkeypatch):
    agent = SimpleNamespace(id=uuid4())
    user, api_key = SimpleNamespace(id=uuid4()), SimpleNamespace(id=uuid4())
    row = conversation(title="Old")
    monkeypatch.setattr(embed, "_get_embed_agent", AsyncMock(return_value=agent))
    lookup = MagicMock(return_value=Query(row))
    monkeypatch.setattr(embed.Conversation, "filter", lookup)

    response = await embed.rename_embed_conversation(
        agent.id,
        row.id,
        ConversationUpdate(title="New title"),
        request(),
        (user, api_key),
    )

    assert response["data"] == {"id": str(row.id), "title": "New title"}
    row.save.assert_awaited_once()
    # The row is looked up inside this agent, this owner and this exact key.
    lookup.assert_called_once_with(
        id=row.id,
        agent_id=agent.id,
        user=user,
        api_key_id=api_key.id,
        api_key_origin_unknown=False,
    )


@pytest.mark.anyio
async def test_rename_embed_conversation_without_title_keeps_current_one(monkeypatch):
    agent = SimpleNamespace(id=uuid4())
    user, api_key = SimpleNamespace(id=uuid4()), SimpleNamespace(id=uuid4())
    row = conversation(title="Kept")
    monkeypatch.setattr(embed, "_get_embed_agent", AsyncMock(return_value=agent))
    monkeypatch.setattr(
        embed.Conversation, "filter", MagicMock(return_value=Query(row))
    )

    response = await embed.rename_embed_conversation(
        agent.id, row.id, ConversationUpdate(), request(), (user, api_key)
    )

    assert response["data"] == {"id": str(row.id), "title": "Kept"}
    row.save.assert_not_awaited()


@pytest.mark.anyio
async def test_rename_embed_conversation_hides_another_keys_row(monkeypatch):
    agent = SimpleNamespace(id=uuid4())
    user, api_key = SimpleNamespace(id=uuid4()), SimpleNamespace(id=uuid4())
    monkeypatch.setattr(embed, "_get_embed_agent", AsyncMock(return_value=agent))
    monkeypatch.setattr(
        embed.Conversation, "filter", MagicMock(return_value=Query(None))
    )

    with pytest.raises(BusinessError) as missing:
        await embed.rename_embed_conversation(
            agent.id,
            uuid4(),
            ConversationUpdate(title="Hijacked"),
            request(),
            (user, api_key),
        )

    assert_error(missing, ResponseCode.CONVERSATION_NOT_FOUND, 404)


@pytest.mark.anyio
async def test_delete_embed_conversation_drops_owned_row(monkeypatch):
    agent = SimpleNamespace(id=uuid4())
    user, api_key = SimpleNamespace(id=uuid4()), SimpleNamespace(id=uuid4())
    row = conversation()
    delete_owned = AsyncMock()
    monkeypatch.setattr(embed, "_get_embed_agent", AsyncMock(return_value=agent))
    monkeypatch.setattr(
        embed.Conversation, "filter", MagicMock(return_value=Query(row))
    )
    monkeypatch.setattr(agents_endpoints, "_delete_owned_conversation", delete_owned)

    response = await embed.delete_embed_conversation(
        agent.id, row.id, request(), (user, api_key)
    )

    assert response["data"] == {"id": str(row.id)}
    delete_owned.assert_awaited_once_with(row)


@pytest.mark.anyio
async def test_delete_embed_conversation_hides_another_keys_row(monkeypatch):
    agent = SimpleNamespace(id=uuid4())
    user, api_key = SimpleNamespace(id=uuid4()), SimpleNamespace(id=uuid4())
    delete_owned = AsyncMock()
    monkeypatch.setattr(embed, "_get_embed_agent", AsyncMock(return_value=agent))
    monkeypatch.setattr(
        embed.Conversation, "filter", MagicMock(return_value=Query(None))
    )
    monkeypatch.setattr(agents_endpoints, "_delete_owned_conversation", delete_owned)

    with pytest.raises(BusinessError) as missing:
        await embed.delete_embed_conversation(
            agent.id, uuid4(), request(), (user, api_key)
        )

    assert_error(missing, ResponseCode.CONVERSATION_NOT_FOUND, 404)
    delete_owned.assert_not_awaited()
