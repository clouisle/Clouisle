from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat
from app.models.agent import AgentVisibility, MessageRole, RAGMode
from app.schemas.agent import ChatRequest
from app.schemas.response import ResponseCode


class Query:
    def __init__(self, *, first=None, exists=False):
        self._first = first
        self._exists = exists
        self.update = AsyncMock(return_value=1)

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self._first

    async def exists(self):
        return self._exists


def user(*, active=True, superuser=False):
    return SimpleNamespace(
        id=uuid4(), is_active=active, is_superuser=superuser, locale="en"
    )


def agent(*, visibility=AgentVisibility.TEAM, created_by=None):
    team_id = uuid4()
    return SimpleNamespace(
        id=uuid4(),
        team_id=team_id,
        team=SimpleNamespace(id=team_id),
        created_by=created_by,
        visibility=visibility,
        rag_mode=RAGMode.OFF,
        max_iterations=1,
        enable_vision=False,
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("current_agent", "current_user", "is_member", "msg_key", "status_code"),
    [
        (None, user(), False, "agent_not_found", 404),
        (
            agent(
                visibility=AgentVisibility.PRIVATE,
                created_by=SimpleNamespace(id=uuid4()),
            ),
            user(),
            False,
            "agent_access_denied",
            403,
        ),
        (
            agent(visibility=AgentVisibility.PRIVATE),
            user(),
            False,
            "agent_access_denied",
            403,
        ),
        (agent(), user(), False, "agent_access_denied", 403),
    ],
)
async def test_chat_access_rejects_missing_and_out_of_scope_agents(
    monkeypatch, current_agent, current_user, is_member, msg_key, status_code
):
    monkeypatch.setattr(
        chat.Agent, "filter", lambda **_kwargs: Query(first=current_agent)
    )
    monkeypatch.setattr(
        chat.TeamMember, "filter", lambda **_kwargs: Query(exists=is_member)
    )

    with pytest.raises(chat.BusinessError) as error:
        await chat.check_agent_chat_access(uuid4(), current_user)

    assert error.value.msg_key == msg_key
    assert error.value.status_code == status_code


@pytest.mark.anyio
@pytest.mark.parametrize("access", ["member", "superuser", "owner"])
async def test_chat_access_accepts_members_superusers_and_private_owner(
    monkeypatch, access
):
    current_user = user(superuser=access == "superuser")
    current_agent = agent(
        visibility=AgentVisibility.PRIVATE
        if access == "owner"
        else AgentVisibility.TEAM,
        created_by=SimpleNamespace(id=current_user.id) if access == "owner" else None,
    )
    is_member = access == "member"
    monkeypatch.setattr(
        chat.Agent, "filter", lambda **_kwargs: Query(first=current_agent)
    )
    monkeypatch.setattr(
        chat.TeamMember, "filter", lambda **_kwargs: Query(exists=is_member)
    )

    assert (
        await chat.check_agent_chat_access(current_agent.id, current_user)
        is current_agent
    )


@pytest.mark.anyio
async def test_public_agent_requires_authentication():
    with pytest.raises(chat.BusinessError) as error:
        await chat.get_public_agent(uuid4(), None)

    assert error.value.code == ResponseCode.UNAUTHORIZED
    assert error.value.status_code == 401


@pytest.mark.anyio
async def test_public_agent_info_returns_minimal_projection(monkeypatch):
    creator = SimpleNamespace(
        id=uuid4(), username="owner", avatar_url="https://img.test/owner.png"
    )
    current_agent = agent(created_by=creator)
    current_agent.name = "Assistant"
    current_agent.description = "Helpful"
    current_agent.icon = "bot"
    current_agent.avatar_url = None
    current_agent.opening_message = "Hello"
    current_agent.suggested_questions = None
    current_agent.variables = None
    current_agent.enable_file_upload = True
    current_agent.file_upload_config = {"max_files": 2}
    current_agent.hide_tool_calls = False
    monkeypatch.setattr(chat, "get_public_agent", AsyncMock(return_value=current_agent))

    result = await chat.get_public_agent_info(current_agent.id, user())

    assert result["data"].name == "Assistant"
    assert result["data"].suggested_questions == []
    assert result["data"].variables == []
    assert result["data"].created_by.username == "owner"
    assert not hasattr(result["data"], "system_prompt")


@pytest.mark.anyio
async def test_conversation_lookup_enforces_agent_and_user_scope(monkeypatch):
    current_agent = agent()
    current_user = user()
    conversation_id = uuid4()
    conversation_filter = MagicMock(return_value=Query(first=None))
    monkeypatch.setattr(chat.Conversation, "filter", conversation_filter)

    with pytest.raises(chat.BusinessError) as error:
        await chat.get_or_create_conversation(
            current_agent, current_user, conversation_id, {}
        )

    assert error.value.msg_key == "conversation_not_found"
    conversation_filter.assert_called_once_with(
        id=conversation_id, agent_id=current_agent.id, user=current_user
    )


@pytest.mark.anyio
async def test_conversation_create_updates_agent_and_team_counts(monkeypatch):
    current_agent = agent()
    current_user = user()
    created = SimpleNamespace(id=uuid4())
    create = AsyncMock(return_value=created)
    agent_query = Query()
    team_query = Query()
    monkeypatch.setattr(chat.Conversation, "create", create)
    monkeypatch.setattr(chat.Agent, "filter", lambda **_kwargs: agent_query)
    monkeypatch.setattr(chat.Team, "filter", lambda **_kwargs: team_query)

    result = await chat.get_or_create_conversation(
        current_agent, current_user, None, {"topic": "coverage"}
    )

    assert result is created
    create.assert_awaited_once_with(
        agent=current_agent, user=current_user, variables={"topic": "coverage"}
    )
    agent_query.update.assert_awaited_once()
    team_query.update.assert_awaited_once()


@pytest.mark.anyio
@pytest.mark.parametrize("endpoint", [chat.chat, chat.chat_stream])
async def test_chat_endpoints_reject_inactive_user_before_api_key_check(
    monkeypatch, endpoint
):
    api_access = AsyncMock()
    monkeypatch.setattr(chat.deps, "check_api_key_agent_access", api_access)
    args = [uuid4(), ChatRequest(message="hello")]
    if endpoint is chat.chat_stream:
        args.append(SimpleNamespace())
    args.append((user(active=False), SimpleNamespace()))

    with pytest.raises(chat.BusinessError) as error:
        await endpoint(*args)

    assert error.value.code == ResponseCode.INACTIVE_USER
    assert error.value.status_code == 401
    api_access.assert_not_awaited()


@pytest.mark.anyio
async def test_stream_setup_failure_returns_error_without_provider_call(monkeypatch):
    current_user = user()
    current_agent = agent()
    conversation = SimpleNamespace(id=uuid4())
    provider = MagicMock()
    monkeypatch.setattr(chat.deps, "check_api_key_agent_access", AsyncMock())
    monkeypatch.setattr(
        chat, "check_agent_chat_access", AsyncMock(return_value=current_agent)
    )
    monkeypatch.setattr(
        chat, "get_or_create_conversation", AsyncMock(return_value=conversation)
    )
    monkeypatch.setattr(
        chat,
        "get_streaming_config",
        lambda _agent: {
            "global_timeout": 10,
            "heartbeat_interval": 1,
            "tool_timeouts": {},
            "idle_timeout": 3,
        },
    )
    monkeypatch.setattr(
        "app.services.sandbox.gateway.sandbox_gateway.create_session",
        AsyncMock(return_value="session"),
    )
    monkeypatch.setattr(
        chat.Message,
        "create",
        AsyncMock(side_effect=RuntimeError("message setup unavailable")),
    )
    monkeypatch.setattr("app.llm.model_manager.team_chat_stream", provider)
    monkeypatch.setattr(chat, "t", lambda key, **_kwargs: key)

    response = await chat.chat_stream(
        current_agent.id,
        ChatRequest(message="hello"),
        SimpleNamespace(),
        (current_user, None),
    )
    events = [event async for event in response.body_iterator]

    assert events == [
        f'event: error\ndata: {{"code": {ResponseCode.UNKNOWN_ERROR}, "msg": "unknown_error"}}\n\n'
    ]
    provider.assert_not_called()


@pytest.mark.anyio
async def test_nonstream_attachment_failure_stops_before_context_and_provider(
    monkeypatch,
):
    current_user = user()
    current_agent = agent()
    conversation = SimpleNamespace(id=uuid4())
    user_message = SimpleNamespace(id=uuid4(), role=MessageRole.USER, file_urls=None)
    context = AsyncMock()
    provider = AsyncMock()
    monkeypatch.setattr(chat.deps, "check_api_key_agent_access", AsyncMock())
    monkeypatch.setattr(
        chat, "check_agent_chat_access", AsyncMock(return_value=current_agent)
    )
    monkeypatch.setattr(
        chat, "get_or_create_conversation", AsyncMock(return_value=conversation)
    )
    monkeypatch.setattr(
        chat, "get_next_user_branch_parent_id", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(chat.Message, "create", AsyncMock(return_value=user_message))
    monkeypatch.setattr(chat, "update_message_stats", AsyncMock())
    monkeypatch.setattr(chat, "get_agent_chat_model", AsyncMock(return_value=None))
    monkeypatch.setattr(
        chat, "get_streaming_config", lambda _agent: {"tool_timeouts": {}}
    )
    monkeypatch.setattr(
        "app.services.sandbox.gateway.sandbox_gateway.create_session",
        AsyncMock(return_value="session"),
    )
    monkeypatch.setattr(
        chat,
        "build_file_content_for_context",
        AsyncMock(
            side_effect=chat.BusinessError(
                code=ResponseCode.FORBIDDEN,
                msg_key="file_access_denied",
                status_code=403,
            )
        ),
    )
    monkeypatch.setattr(chat, "prepare_model_context", context)
    monkeypatch.setattr("app.llm.model_manager.team_chat", provider)

    with pytest.raises(chat.BusinessError) as error:
        await chat.chat(
            current_agent.id,
            ChatRequest(message="read attachment"),
            (current_user, None),
        )

    assert error.value.msg_key == "file_access_denied"
    assert user_message.role == MessageRole.USER
    context.assert_not_awaited()
    provider.assert_not_awaited()
