from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat
from app.models.agent import AgentVisibility
from app.schemas.response import BusinessError, ResponseCode


class Query:
    def __init__(self, result=None):
        self.result = result
        self.delete = AsyncMock(return_value=1)
        self.update = AsyncMock(return_value=1)

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self.result

    async def exists(self):
        return bool(self.result)


@pytest.mark.anyio
async def test_access_and_conversation_helper_residual_arcs(monkeypatch):
    user = SimpleNamespace(id=uuid4(), is_superuser=False)
    team_id = uuid4()
    ownerless = SimpleNamespace(
        id=uuid4(),
        team_id=team_id,
        visibility=AgentVisibility.PRIVATE,
        created_by=None,
    )
    monkeypatch.setattr(chat.Agent, "filter", Mock(return_value=Query(ownerless)))
    monkeypatch.setattr(chat.TeamMember, "filter", Mock(return_value=Query(None)))

    with pytest.raises(BusinessError) as exc_info:
        await chat.check_agent_chat_access(ownerless.id, user)
    assert exc_info.value.code == ResponseCode.AGENT_ACCESS_DENIED

    ownerless.visibility = AgentVisibility.PUBLIC
    with pytest.raises(BusinessError):
        await chat.check_agent_chat_access(ownerless.id, user)

    ownerless.created_by = SimpleNamespace(id=user.id)
    ownerless.visibility = AgentVisibility.PRIVATE
    assert await chat.check_agent_chat_access(ownerless.id, user) is ownerless

    conversation_id = uuid4()
    monkeypatch.setattr(chat.Conversation, "filter", Mock(return_value=Query(None)))
    with pytest.raises(BusinessError) as exc_info:
        await chat.get_or_create_conversation(ownerless, user, conversation_id, {})
    assert exc_info.value.code == ResponseCode.CONVERSATION_NOT_FOUND

    conversation = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(
        chat.Conversation, "create", AsyncMock(return_value=conversation)
    )
    agent_stats = Query()
    team_stats = Query()
    monkeypatch.setattr(chat.Agent, "filter", Mock(return_value=agent_stats))
    monkeypatch.setattr(chat.Team, "filter", Mock(return_value=team_stats))
    ownerless.team = SimpleNamespace(id=team_id)

    assert (
        await chat.get_or_create_conversation(ownerless, user, None, {"name": "Ada"})
        is conversation
    )
    agent_stats.update.assert_awaited_once()
    team_stats.update.assert_awaited_once()


@pytest.mark.anyio
async def test_round_model_stats_and_macro_helpers_cover_empty_boundaries(monkeypatch):
    conversation = SimpleNamespace(id=uuid4())
    last = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(
        chat, "get_last_active_canonical_message", AsyncMock(return_value=last)
    )
    assert await chat.get_next_user_branch_parent_id(conversation) == last.id

    agent_stats = Query()
    team_stats = Query()
    monkeypatch.setattr(chat.Agent, "filter", Mock(return_value=agent_stats))
    monkeypatch.setattr(chat.Team, "filter", Mock(return_value=team_stats))
    agent = SimpleNamespace(id=uuid4(), team=SimpleNamespace(id=uuid4()))
    await chat.update_message_stats(agent, {"prompt": None, "completion": 3})
    assert agent_stats.update.await_args.kwargs["total_tokens"].right.value == 3

    agent.model_id = None
    assert await chat.get_model_identifier(agent) is None
    assert await chat.get_agent_chat_model(agent) is None

    assert chat._first_token_ms(1.0, None) is None


@pytest.mark.anyio
async def test_message_payload_residual_arcs(monkeypatch):
    round_id = uuid4()
    regular = SimpleNamespace(round_id=None, round_role=None, is_round_canonical=True)
    final = SimpleNamespace(
        round_id=round_id,
        round_role=chat.MessageRoundRole.ASSISTANT_FINAL,
        is_round_canonical=True,
    )
    step = SimpleNamespace(round_id=round_id, is_round_canonical=False)
    monkeypatch.setattr(
        chat, "build_round_steps_map", AsyncMock(return_value={round_id: []})
    )
    validated = MagicMock()
    validated.model_dump.side_effect = [{"id": "regular"}, {"id": "final"}]
    monkeypatch.setattr(chat.MessageOut, "model_validate", Mock(return_value=validated))

    assert await chat.build_message_round_payloads([regular, step, final]) == [
        {"id": "regular"},
        {"id": "final", "steps": []},
    ]
