from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.v1.endpoints.chat import (
    check_agent_chat_access,
    get_or_create_conversation,
)
from app.models.agent import AgentVisibility
from app.schemas.response import BusinessError


class _FirstQuery:
    def __init__(self, value):
        self.value = value

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self.value


class _ExistsQuery:
    def __init__(self, value):
        self.value = value

    async def exists(self):
        return self.value


class _AgentModel:
    agent = None

    @classmethod
    def filter(cls, **_kwargs):
        return _FirstQuery(cls.agent)


class _TeamMemberModel:
    is_member = False

    @classmethod
    def filter(cls, **_kwargs):
        return _ExistsQuery(cls.is_member)


class _ConversationModel:
    conversation = None
    created_with = None

    @classmethod
    def filter(cls, **_kwargs):
        return _FirstQuery(cls.conversation)

    @classmethod
    async def create(cls, **kwargs):
        cls.created_with = kwargs
        return SimpleNamespace(id=uuid4(), **kwargs)


class _CounterQuery:
    def __init__(self):
        self.update_calls = []

    async def update(self, **kwargs):
        self.update_calls.append(kwargs)


class _CounterModel:
    query = _CounterQuery()

    @classmethod
    def filter(cls, **_kwargs):
        return cls.query


@pytest.fixture(autouse=True)
def _patch_chat_models(monkeypatch):
    _AgentModel.agent = None
    _TeamMemberModel.is_member = False
    _ConversationModel.conversation = None
    _ConversationModel.created_with = None
    _CounterModel.query = _CounterQuery()
    monkeypatch.setattr("app.api.v1.endpoints.chat.Agent", _AgentModel)
    monkeypatch.setattr("app.api.v1.endpoints.chat.TeamMember", _TeamMemberModel)
    monkeypatch.setattr("app.api.v1.endpoints.chat.Conversation", _ConversationModel)


@pytest.mark.anyio
async def test_chat_endpoint_rejects_missing_agent():
    with pytest.raises(BusinessError) as error:
        await check_agent_chat_access(
            uuid4(), SimpleNamespace(id=uuid4(), is_superuser=False)
        )

    assert error.value.status_code == 404
    assert error.value.msg_key == "agent_not_found"


@pytest.mark.anyio
async def test_chat_endpoint_rejects_unrelated_private_agent_user():
    _AgentModel.agent = SimpleNamespace(
        visibility=AgentVisibility.PRIVATE,
        created_by=SimpleNamespace(id=uuid4()),
        team_id=uuid4(),
    )

    with pytest.raises(BusinessError) as error:
        await check_agent_chat_access(
            uuid4(), SimpleNamespace(id=uuid4(), is_superuser=False)
        )

    assert error.value.status_code == 403
    assert error.value.msg_key == "agent_access_denied"


@pytest.mark.anyio
async def test_chat_endpoint_requires_membership_for_team_agent():
    _AgentModel.agent = SimpleNamespace(
        visibility=AgentVisibility.TEAM,
        created_by=None,
        team_id=uuid4(),
    )

    with pytest.raises(BusinessError) as error:
        await check_agent_chat_access(
            uuid4(), SimpleNamespace(id=uuid4(), is_superuser=False)
        )

    assert error.value.status_code == 403
    assert error.value.msg_key == "agent_access_denied"


@pytest.mark.anyio
async def test_chat_endpoint_allows_team_member():
    agent = SimpleNamespace(
        visibility=AgentVisibility.TEAM,
        created_by=None,
        team_id=uuid4(),
    )
    _AgentModel.agent = agent
    _TeamMemberModel.is_member = True

    assert (
        await check_agent_chat_access(
            uuid4(), SimpleNamespace(id=uuid4(), is_superuser=False)
        )
        is agent
    )


@pytest.mark.anyio
async def test_chat_endpoint_rejects_missing_or_unowned_conversation():
    agent = SimpleNamespace(id=uuid4())
    user = SimpleNamespace(id=uuid4())

    with pytest.raises(BusinessError) as error:
        await get_or_create_conversation(agent, user, uuid4(), {})

    assert error.value.status_code == 404
    assert error.value.msg_key == "conversation_not_found"


@pytest.mark.anyio
async def test_chat_endpoint_uses_existing_conversation_for_owner():
    agent = SimpleNamespace(id=uuid4())
    user = SimpleNamespace(id=uuid4())
    conversation = SimpleNamespace(id=uuid4())
    _ConversationModel.conversation = conversation

    assert (
        await get_or_create_conversation(agent, user, conversation.id, {})
        is conversation
    )


@pytest.mark.anyio
async def test_chat_endpoint_creates_conversation_with_request_variables(monkeypatch):
    agent = SimpleNamespace(id=uuid4(), team=SimpleNamespace(id=uuid4()))
    user = SimpleNamespace(id=uuid4())
    monkeypatch.setattr("app.api.v1.endpoints.chat.Agent", _CounterModel)
    monkeypatch.setattr("app.api.v1.endpoints.chat.Team", _CounterModel)

    conversation = await get_or_create_conversation(agent, user, None, {"locale": "en"})

    assert conversation.agent is agent
    assert conversation.user is user
    assert _ConversationModel.created_with["variables"] == {"locale": "en"}
    assert len(_CounterModel.query.update_calls) == 2
