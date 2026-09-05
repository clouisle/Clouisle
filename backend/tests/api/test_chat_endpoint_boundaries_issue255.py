from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat as chat_module
from app.llm.types import (
    ChatStreamChunk,
    ChatStreamDelta,
    FinishReason,
    FunctionCall,
    ToolCall,
)
from app.models.agent import AgentVisibility, MessageRole, MessageRoundStatus
from app.schemas.agent import (
    ChatRequest,
    EditMessageRequest,
    RegenerateRequest,
    SwitchVersionRequest,
)
from app.schemas.response import BusinessError, ResponseCode


def _fake_chat_resolution():
    """Return a SimpleNamespace mimicking ChatModelResolution for tests."""
    return SimpleNamespace(
        model=SimpleNamespace(id=uuid4()),
        team_model=SimpleNamespace(),
        model_id=str(uuid4()),
        tokenizer_model_id="stub-model",
        provider="stub",
        context_length=8192,
        max_output_tokens=1024,
        supports_vision=False,
    )


class Query:
    def __init__(self, result=None):
        self.result = result

    def prefetch_related(self, *args):
        return self

    def order_by(self, *args):
        return self

    def using_db(self, *args):
        return self

    def select_for_update(self):
        return self

    async def first(self):
        return self.result

    async def exists(self):
        return bool(self.result)

    async def count(self):
        return self.result

    async def all(self):
        return self.result

    async def update(self, **kwargs):
        return 1

    async def delete(self):
        return 1


def user(*, superuser=False, active=True):
    return SimpleNamespace(
        id=uuid4(), is_superuser=superuser, is_active=active, locale="en"
    )


def agent(**overrides):
    values = {
        "id": uuid4(),
        "team_id": uuid4(),
        "team": SimpleNamespace(id=uuid4()),
        "visibility": AgentVisibility.TEAM,
        "created_by": None,
        "name": "Helper",
        "description": None,
        "icon": None,
        "avatar_url": None,
        "opening_message": None,
        "suggested_questions": None,
        "powered_by_text": None,
        "variables": None,
        "enable_attachments": False,
        "attachment_config": None,
        "hide_tool_calls": False,
        "hide_message_actions": False,
        "hide_reasoning": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def message(**overrides):
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
        "first_token_ms": None,
        "is_manually_stopped": False,
        "rag_context": None,
        "created_at": datetime.now(timezone.utc),
        "round_id": None,
        "round_index": 0,
        "round_role": None,
        "is_round_canonical": True,
        "iteration_index": None,
        "round_status": None,
        "parent_id": None,
        "branch_parent_id": None,
        "is_active": True,
        "version_number": 1,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def assert_business_error(error, code, status):
    assert error.value.code == code
    assert error.value.status_code == status


def test_dependency_light_helpers_cover_payload_activity_and_error_formatting(
    monkeypatch,
):
    preview = chat_module._message_content_audit_preview("x" * 501)
    assert preview == {
        "content_preview": "x" * 500,
        "content_length": 501,
        "truncated": True,
    }

    quiet = ChatStreamChunk(id="1", model="m", delta=ChatStreamDelta())
    active = ChatStreamChunk(
        id="2", model="m", delta=ChatStreamDelta(stream_activity=True)
    )
    tool_call = ToolCall(
        id="tool-1",
        function=FunctionCall(name="edit", arguments="{}"),
    )
    tool_start = ChatStreamChunk(
        id="tool-start",
        model="m",
        delta=ChatStreamDelta(tool_call_starts=[tool_call]),
    )
    finished = ChatStreamChunk(
        id="3",
        model="m",
        delta=ChatStreamDelta(),
        finish_reason=FinishReason.STOP,
    )
    assert chat_module._is_model_stream_activity(quiet) is False
    assert chat_module._is_model_stream_activity(active) is True
    assert chat_module._is_model_stream_activity(tool_start) is True
    tool_events = chat_module._build_tool_call_start_sse_events(
        [tool_call], {"edit": "Edit file"}
    )
    assert len(tool_events) == 1
    assert '"tool_call_id": "tool-1"' in tool_events[0]
    assert '"tool_display_name": "Edit file"' in tool_events[0]
    assert '"arguments": {}' in tool_events[0]
    assert chat_module._is_model_stream_activity(finished) is True

    provider_error = Exception(
        "request failed - {'error': {'message': 'provider rejected input'}}"
    )
    assert chat_module._extract_llm_error_message(provider_error) == (
        "provider rejected input"
    )
    malformed = Exception("request failed - not-a-dict")
    assert chat_module._extract_llm_error_message(malformed) == str(malformed)

    monkeypatch.setattr(chat_module, "t", lambda key, **kw: (key, kw))
    assert chat_module._format_llm_error_message(provider_error) == (
        "model_service_request_failed",
        {"message": "provider rejected input"},
    )


def test_round_helpers_cover_optional_history_and_terminal_precedence():
    round_id = uuid4()
    history = []
    chat_module.append_round_history_entry(
        history,
        role="tool",
        content="done",
        round_id=round_id,
        round_index=2,
        round_role="tool_result",
        is_round_canonical=False,
        iteration_index=1,
        round_status="completed",
        reasoning_content="why",
        tool_calls=[{"id": "call"}],
        tool_call_id="call",
        tool_name="lookup",
    )
    assert history == [
        {
            "role": "tool",
            "content": "done",
            "round_id": str(round_id),
            "round_index": 2,
            "round_role": "tool_result",
            "is_round_canonical": False,
            "iteration_index": 1,
            "round_status": "completed",
            "reasoning_content": "why",
            "tool_calls": [{"id": "call"}],
            "tool_call_id": "call",
            "tool_name": "lookup",
        }
    ]
    assert (
        chat_module.get_round_terminal_status(
            completed=True,
            manually_stopped=True,
            max_iterations_reached=True,
            errored=True,
        )
        == MessageRoundStatus.MANUALLY_STOPPED
    )
    assert (
        chat_module.get_round_terminal_status(
            completed=True, max_iterations_reached=True, errored=True
        )
        == MessageRoundStatus.MAX_ITERATIONS_REACHED
    )
    assert (
        chat_module.get_round_terminal_status(completed=True, errored=True)
        == MessageRoundStatus.ERROR
    )
    assert chat_module.get_round_terminal_status(completed=True) == (
        MessageRoundStatus.COMPLETED
    )
    assert chat_module.get_round_terminal_status(completed=False) == (
        MessageRoundStatus.ERROR
    )
    assert chat_module._first_token_ms(10.0, None) is None
    assert chat_module._first_token_ms(10.0, 10.125) == 125


@pytest.mark.anyio
async def test_access_boundaries_reject_missing_agent_and_nonmembers(monkeypatch):
    monkeypatch.setattr(chat_module.Agent, "filter", lambda **kwargs: Query(None))
    with pytest.raises(BusinessError) as missing:
        await chat_module.check_agent_chat_access(uuid4(), user())
    assert_business_error(missing, ResponseCode.AGENT_NOT_FOUND, 404)

    private = agent(
        visibility=AgentVisibility.PRIVATE, created_by=SimpleNamespace(id=uuid4())
    )
    monkeypatch.setattr(chat_module.Agent, "filter", lambda **kwargs: Query(private))
    with pytest.raises(BusinessError) as denied_private:
        await chat_module.check_agent_chat_access(private.id, user())
    assert_business_error(denied_private, ResponseCode.AGENT_ACCESS_DENIED, 403)

    team_agent = agent()
    monkeypatch.setattr(chat_module.Agent, "filter", lambda **kwargs: Query(team_agent))
    monkeypatch.setattr(chat_module.TeamMember, "filter", lambda **kwargs: Query(False))
    with pytest.raises(BusinessError) as denied_team:
        await chat_module.get_public_agent(team_agent.id, user())
    assert_business_error(denied_team, ResponseCode.AGENT_ACCESS_DENIED, 403)


@pytest.mark.anyio
async def test_access_boundaries_allow_creator_member_and_superuser(monkeypatch):
    creator = user()
    private = agent(
        visibility=AgentVisibility.PRIVATE,
        created_by=SimpleNamespace(id=creator.id),
    )
    monkeypatch.setattr(chat_module.Agent, "filter", lambda **kwargs: Query(private))
    assert await chat_module.check_agent_chat_access(private.id, creator) is private

    team_agent = agent()
    monkeypatch.setattr(chat_module.Agent, "filter", lambda **kwargs: Query(team_agent))
    monkeypatch.setattr(chat_module.TeamMember, "filter", lambda **kwargs: Query(True))
    assert await chat_module.get_public_agent(team_agent.id, user()) is team_agent

    monkeypatch.setattr(
        chat_module.TeamMember, "filter", MagicMock(side_effect=AssertionError)
    )
    assert (
        await chat_module.get_public_agent(team_agent.id, user(superuser=True))
        is team_agent
    )


@pytest.mark.anyio
async def test_public_agent_requires_authentication():
    with pytest.raises(BusinessError) as unauthorized:
        await chat_module.get_public_agent(uuid4(), None)
    assert_business_error(unauthorized, ResponseCode.UNAUTHORIZED, 401)


@pytest.mark.anyio
async def test_get_or_create_conversation_covers_lookup_create_and_stats(monkeypatch):
    current_user = user()
    current_agent = agent()
    existing = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(
        chat_module.Conversation, "filter", lambda **kwargs: Query(existing)
    )
    assert (
        await chat_module.get_or_create_conversation(
            current_agent, current_user, existing.id, {}
        )
        is existing
    )

    created = SimpleNamespace(id=uuid4())
    create = AsyncMock(return_value=created)
    agent_filter = MagicMock(return_value=Query())
    team_filter = MagicMock(return_value=Query())
    monkeypatch.setattr(chat_module.Conversation, "create", create)
    monkeypatch.setattr(chat_module.Agent, "filter", agent_filter)
    monkeypatch.setattr(chat_module.Team, "filter", team_filter)
    assert (
        await chat_module.get_or_create_conversation(
            current_agent, current_user, None, {"topic": "tests"}
        )
        is created
    )
    create.assert_awaited_once_with(
        agent=current_agent, user=current_user, variables={"topic": "tests"}
    )
    agent_filter.assert_called_once_with(id=current_agent.id)
    team_filter.assert_called_once_with(id=current_agent.team.id)


@pytest.mark.anyio
async def test_get_or_create_conversation_rejects_unowned_id(monkeypatch):
    monkeypatch.setattr(
        chat_module.Conversation, "filter", lambda **kwargs: Query(None)
    )
    with pytest.raises(BusinessError) as missing:
        await chat_module.get_or_create_conversation(agent(), user(), uuid4(), {})
    assert_business_error(missing, ResponseCode.CONVERSATION_NOT_FOUND, 404)


@pytest.mark.anyio
async def test_persist_partial_round_error_covers_no_progress_and_saved_fallback(
    monkeypatch,
):
    assert (
        await chat_module.persist_partial_round_error(
            None, content="", reasoning="", model_used=None, start_time=1
        )
        is False
    )

    empty = message(round_id=None)
    assert (
        await chat_module.persist_partial_round_error(
            empty, content="", reasoning="", model_used=None, start_time=1
        )
        is False
    )

    saved = message(round_id=uuid4())
    saved.save = AsyncMock()
    monkeypatch.setattr(chat_module, "now_utc", lambda: "now")
    monkeypatch.setattr(chat_module.time, "time", lambda: 3.25)
    assert (
        await chat_module.persist_partial_round_error(
            saved,
            content="",
            reasoning="trace",
            model_used="provider/model",
            start_time=2.0,
            first_token_time=2.125,
            fallback_content="failed",
        )
        is True
    )
    assert saved.content == "failed"
    assert saved.reasoning_content == "trace"
    assert saved.model_used == "provider/model"
    assert saved.duration_ms == 1250
    assert saved.first_token_ms == 125
    assert saved.round_status == MessageRoundStatus.ERROR
    assert saved.created_at == "now"
    saved.save.assert_awaited_once()


@pytest.mark.anyio
async def test_public_info_endpoint_returns_minimal_creator_payload(monkeypatch):
    creator_id = uuid4()
    current_agent = agent(
        created_by=SimpleNamespace(
            id=creator_id, username="owner", avatar_url="/avatar.png"
        ),
        suggested_questions=["How?"],
        variables=[{"name": "topic"}],
    )
    monkeypatch.setattr(
        chat_module, "get_public_agent", AsyncMock(return_value=current_agent)
    )
    result = await chat_module.get_public_agent_info(current_agent.id, user())
    assert result["code"] == ResponseCode.SUCCESS
    assert result["data"].id == current_agent.id
    assert result["data"].created_by.id == creator_id
    assert result["data"].suggested_questions == ["How?"]


@pytest.mark.anyio
async def test_message_version_endpoint_covers_missing_forbidden_and_happy(monkeypatch):
    current_user = user()
    message_id = uuid4()
    monkeypatch.setattr(chat_module.Message, "filter", lambda **kwargs: Query(None))
    with pytest.raises(BusinessError) as missing:
        await chat_module.get_message_version_list(uuid4(), message_id, current_user)
    assert_business_error(missing, ResponseCode.NOT_FOUND, 404)

    current_message = message(id=message_id)
    monkeypatch.setattr(
        chat_module.Message, "filter", lambda **kwargs: Query(current_message)
    )
    monkeypatch.setattr(
        chat_module.Conversation, "filter", lambda **kwargs: Query(None)
    )
    with pytest.raises(BusinessError) as forbidden:
        await chat_module.get_message_version_list(uuid4(), message_id, current_user)
    assert_business_error(forbidden, ResponseCode.FORBIDDEN, 403)

    monkeypatch.setattr(
        chat_module.Conversation, "filter", lambda **kwargs: Query(SimpleNamespace())
    )
    versions = [SimpleNamespace(id=uuid4())]
    monkeypatch.setattr(
        chat_module, "get_message_versions", AsyncMock(return_value=versions)
    )
    result = await chat_module.get_message_version_list(
        uuid4(), message_id, current_user
    )
    assert result["data"] == versions


@pytest.mark.anyio
async def test_switch_version_rejects_other_group_and_activates_valid_branch(
    monkeypatch,
):
    current = message()
    other = message(parent_id=uuid4())
    conversation = SimpleNamespace(id=current.conversation_id)
    results = iter([current, other])
    monkeypatch.setattr(
        chat_module.Message, "filter", lambda **kwargs: Query(next(results))
    )
    monkeypatch.setattr(
        chat_module.Conversation, "filter", lambda **kwargs: Query(conversation)
    )
    with pytest.raises(BusinessError) as wrong_group:
        await chat_module.switch_message_version(
            uuid4(), current.id, SwitchVersionRequest(version_id=other.id), user()
        )
    assert_business_error(wrong_group, ResponseCode.BAD_REQUEST, 400)

    target = message(parent_id=current.id, version_number=2)
    # switch_message_version resolves the version-group ROOT message when the
    # target is not the root, so the Message.filter mock needs a third result.
    results = iter([current, target, current])
    monkeypatch.setattr(
        chat_module.Message, "filter", lambda **kwargs: Query(next(results))
    )
    prefix = [message()]
    descendants = [target, message(branch_parent_id=target.id)]
    monkeypatch.setattr(
        chat_module, "get_prefix_path_before", AsyncMock(return_value=prefix)
    )
    monkeypatch.setattr(
        chat_module, "find_descendant_branch_from", AsyncMock(return_value=descendants)
    )
    activate = AsyncMock()
    monkeypatch.setattr(chat_module, "activate_conversation_branch", activate)
    output = SimpleNamespace(id=target.id)
    monkeypatch.setattr(
        chat_module,
        "build_message_out_with_versions",
        AsyncMock(return_value=output),
    )
    result = await chat_module.switch_message_version(
        uuid4(), current.id, SwitchVersionRequest(version_id=target.id), user()
    )
    assert result["data"] is output
    activate.assert_awaited_once_with(current.conversation_id, [*prefix, *descendants])


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("case", "code", "msg_key", "status"),
    [
        ("missing", ResponseCode.NOT_FOUND, "message_not_found", 404),
        ("wrong_role", ResponseCode.BAD_REQUEST, "can_only_edit_user_message", 400),
        ("empty", ResponseCode.BAD_REQUEST, "message_content_required", 400),
        ("forbidden", ResponseCode.FORBIDDEN, "access_denied", 403),
        ("missing_agent", ResponseCode.NOT_FOUND, "agent_not_found", 404),
    ],
)
async def test_edit_user_message_stream_rejects_invalid_preflight(
    monkeypatch, case, code, msg_key, status
):
    current_user = user()
    current_agent = agent()
    current_message = message(role=MessageRole.USER, content="original")
    requested_content = "updated"
    conversation = SimpleNamespace(agent_id=current_agent.id)

    if case == "missing":
        current_message = None
    elif case == "wrong_role":
        current_message = message(role=MessageRole.ASSISTANT)
    elif case == "empty":
        requested_content = "   "
    elif case == "forbidden":
        conversation = None
    elif case == "missing_agent":
        current_agent = None

    monkeypatch.setattr(
        chat_module.Message, "filter", lambda **kwargs: Query(current_message)
    )
    monkeypatch.setattr(
        chat_module.Conversation, "filter", lambda **kwargs: Query(conversation)
    )
    monkeypatch.setattr(
        chat_module.Agent, "filter", lambda **kwargs: Query(current_agent)
    )

    with pytest.raises(BusinessError) as error:
        await chat_module.edit_user_message_stream(
            uuid4(),
            uuid4(),
            EditMessageRequest(content=requested_content),
            SimpleNamespace(),
            current_user,
        )

    assert_business_error(error, code, status)
    assert error.value.msg_key == msg_key


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("case", "code", "msg_key", "status"),
    [
        ("missing", ResponseCode.NOT_FOUND, "message_not_found", 404),
        (
            "wrong_role",
            ResponseCode.BAD_REQUEST,
            "can_only_regenerate_assistant",
            400,
        ),
        ("forbidden", ResponseCode.FORBIDDEN, "access_denied", 403),
        ("missing_agent", ResponseCode.NOT_FOUND, "agent_not_found", 404),
        ("no_user_message", ResponseCode.BAD_REQUEST, "no_user_message_found", 400),
    ],
)
async def test_regenerate_message_rejects_invalid_preflight(
    monkeypatch, case, code, msg_key, status
):
    current_user = user()
    current_agent = agent()
    current_message = message(role=MessageRole.ASSISTANT)
    conversation = SimpleNamespace(agent_id=current_agent.id)

    if case == "missing":
        current_message = None
    elif case == "wrong_role":
        current_message = message(role=MessageRole.USER)
    elif case == "forbidden":
        conversation = None
    elif case == "missing_agent":
        current_agent = None

    monkeypatch.setattr(
        chat_module.Message, "filter", lambda **kwargs: Query(current_message)
    )
    monkeypatch.setattr(
        chat_module.Conversation, "filter", lambda **kwargs: Query(conversation)
    )
    monkeypatch.setattr(
        chat_module.Agent, "filter", lambda **kwargs: Query(current_agent)
    )
    monkeypatch.setattr(
        chat_module, "get_prefix_path_before", AsyncMock(return_value=[])
    )

    with pytest.raises(BusinessError) as error:
        await chat_module.regenerate_message(
            uuid4(),
            uuid4(),
            RegenerateRequest(),
            SimpleNamespace(),
            current_user,
        )

    assert_business_error(error, code, status)
    assert error.value.msg_key == msg_key


@pytest.mark.anyio
async def test_chat_endpoints_reject_inactive_user_before_access_checks(monkeypatch):
    access = AsyncMock()
    monkeypatch.setattr(chat_module.deps, "check_api_key_agent_access", access)
    inactive = user(active=False)
    chat_in = ChatRequest(message="hello")

    with pytest.raises(BusinessError) as nonstream:
        await chat_module.chat(uuid4(), chat_in, (inactive, None))
    assert_business_error(nonstream, ResponseCode.INACTIVE_USER, 401)

    with pytest.raises(BusinessError) as stream:
        await chat_module.chat_stream(
            uuid4(), chat_in, SimpleNamespace(), (inactive, None)
        )
    assert_business_error(stream, ResponseCode.INACTIVE_USER, 401)
    access.assert_not_awaited()
