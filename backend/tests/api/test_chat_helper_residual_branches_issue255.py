from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat
from app.models.agent import AgentVisibility, MessageRoundStatus
from app.schemas.response import BusinessError, ResponseCode


class Query:
    def __init__(self, value=None):
        self.value = value
        self.exists = AsyncMock(return_value=bool(value))

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self.value


def user():
    return SimpleNamespace(id=uuid4(), is_superuser=False)


def private_agent():
    return SimpleNamespace(
        id=uuid4(),
        team_id=uuid4(),
        visibility=AgentVisibility.PRIVATE,
        created_by=None,
    )


@pytest.mark.anyio
async def test_private_agent_without_creator_allows_team_member(monkeypatch):
    current_agent = private_agent()
    agent_query = Query(current_agent)
    member_query = Query(True)
    monkeypatch.setattr(chat.Agent, "filter", lambda **_kwargs: agent_query)
    monkeypatch.setattr(chat.TeamMember, "filter", lambda **_kwargs: member_query)

    assert await chat.check_agent_chat_access(current_agent.id, user()) is current_agent
    assert await chat.get_public_agent(current_agent.id, user()) is current_agent
    assert member_query.exists.await_count == 2


@pytest.mark.anyio
async def test_public_agent_reports_missing_agent(monkeypatch):
    monkeypatch.setattr(chat.Agent, "filter", lambda **_kwargs: Query())

    with pytest.raises(BusinessError) as caught:
        await chat.get_public_agent(uuid4(), user())

    assert caught.value.code == ResponseCode.AGENT_NOT_FOUND
    assert caught.value.status_code == 404


@pytest.mark.anyio
async def test_small_async_helpers_cover_remaining_database_boundaries(monkeypatch):
    last_message = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(
        chat, "get_last_active_canonical_message", AsyncMock(return_value=last_message)
    )
    assert (
        await chat.get_next_user_branch_parent_id(SimpleNamespace(id=uuid4()))
        == last_message.id
    )

    monkeypatch.setattr(chat.TeamModel, "filter", lambda **_kwargs: Query())
    assert await chat.get_model_identifier(SimpleNamespace(model_id=uuid4())) is None

    trace_query = Query(True)
    monkeypatch.setattr(chat.Message, "filter", lambda **_kwargs: trace_query)
    trace = SimpleNamespace(round_id=uuid4(), conversation_id=uuid4())
    assert await chat.round_has_persisted_trace(trace) is True
    trace_query.exists.assert_awaited_once()


@pytest.mark.anyio
async def test_build_messages_forwards_to_context_builder(monkeypatch):
    expected = [object()]
    build = AsyncMock(return_value=expected)
    monkeypatch.setattr(chat, "build_model_messages", build)
    current_agent = object()
    conversation = object()

    assert await chat.build_messages(current_agent, conversation, "hello") is expected
    build.assert_awaited_once_with(
        agent=current_agent,
        conversation=conversation,
        user_message="hello",
        file_content=None,
        user_locale=None,
        history_override=None,
        current_images=None,
        model_supports_vision=False,
        current_user_message_id=None,
    )


def test_error_extraction_and_memory_enqueue_disabled_branches(monkeypatch):
    error = Exception("failed - {'error': {'message': ''}}")
    assert chat._extract_llm_error_message(error) == str(error)

    monkeypatch.setattr(
        chat,
        "get_context_compression_config",
        lambda _agent: {
            "session_memory_enabled": True,
            "session_memory_async_extract": False,
        },
    )
    chat.enqueue_session_memory_extraction(
        object(), SimpleNamespace(id=uuid4()), SimpleNamespace(id=uuid4())
    )


@pytest.mark.anyio
async def test_partial_round_error_content_and_persisted_trace_fallbacks(monkeypatch):
    monkeypatch.setattr(chat.time, "time", lambda: 2.0)
    monkeypatch.setattr(chat, "now_utc", lambda: "now")

    content_message = SimpleNamespace(save=AsyncMock())
    assert await chat.persist_partial_round_error(
        content_message,
        content="partial",
        reasoning="",
        model_used=None,
        start_time=1.0,
        fallback_content="ignored",
    )
    assert content_message.content == "partial"

    trace_message = SimpleNamespace(
        conversation_id=uuid4(), round_id=uuid4(), save=AsyncMock()
    )
    monkeypatch.setattr(chat, "round_has_persisted_trace", AsyncMock(return_value=True))
    assert await chat.persist_partial_round_error(
        trace_message,
        content="",
        reasoning="",
        model_used=None,
        start_time=1.0,
    )
    assert trace_message.content == ""
    assert trace_message.round_status == MessageRoundStatus.ERROR
