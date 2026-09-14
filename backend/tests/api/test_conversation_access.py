from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api import conversation_access
from app.schemas.response import BusinessError, ResponseCode


class Query:
    def __init__(self, value):
        self.value = value

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self.value


@pytest.mark.anyio
async def test_get_authorized_conversation_rejects_missing_conversation(monkeypatch):
    monkeypatch.setattr(
        conversation_access.Conversation,
        "filter",
        lambda **_kwargs: Query(None),
    )

    with pytest.raises(BusinessError) as exc_info:
        await conversation_access.get_authorized_conversation(
            uuid4(), SimpleNamespace()
        )

    assert exc_info.value.code == ResponseCode.NOT_FOUND
    assert exc_info.value.msg_key == "conversation_not_found"


@pytest.mark.anyio
async def test_get_authorized_conversation_allows_owner(monkeypatch):
    user = SimpleNamespace(id=uuid4(), is_superuser=False, roles=[])
    conversation = SimpleNamespace(user_id=user.id, agent=None)
    monkeypatch.setattr(
        conversation_access.Conversation,
        "filter",
        lambda **_kwargs: Query(conversation),
    )

    result = await conversation_access.get_authorized_conversation(uuid4(), user)

    assert result is conversation


@pytest.mark.anyio
async def test_get_authorized_conversation_rejects_non_owner_without_access(
    monkeypatch,
):
    user = SimpleNamespace(id=uuid4(), is_superuser=False, roles=[])
    conversation = SimpleNamespace(
        user_id=uuid4(), agent=SimpleNamespace(team_id=uuid4())
    )
    monkeypatch.setattr(
        conversation_access.Conversation,
        "filter",
        lambda **_kwargs: Query(conversation),
    )
    monkeypatch.setattr(
        conversation_access,
        "has_conversation_team_admin_access",
        AsyncMock(return_value=False),
    )

    with pytest.raises(BusinessError) as exc_info:
        await conversation_access.get_authorized_conversation(uuid4(), user)

    assert exc_info.value.code == ResponseCode.FORBIDDEN
    assert exc_info.value.msg_key == "access_denied"


@pytest.mark.anyio
async def test_get_authorized_conversation_allows_team_admin(monkeypatch):
    user = SimpleNamespace(id=uuid4(), is_superuser=False, roles=[])
    conversation = SimpleNamespace(
        user_id=uuid4(), agent=SimpleNamespace(team_id=uuid4())
    )
    monkeypatch.setattr(
        conversation_access.Conversation,
        "filter",
        lambda **_kwargs: Query(conversation),
    )
    monkeypatch.setattr(
        conversation_access,
        "has_conversation_team_admin_access",
        AsyncMock(return_value=True),
    )

    result = await conversation_access.get_authorized_conversation(uuid4(), user)

    assert result is conversation
