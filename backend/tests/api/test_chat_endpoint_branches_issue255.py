from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat
from app.models.agent import (
    AgentVisibility,
    MessageRole,
    MessageRoundRole,
    MessageRoundStatus,
)
from app.models.agent_run import AgentRunStatus
from app.schemas.response import BusinessError
from app.schemas.agent import RunAnswerCreate


def _query_with_first(value):
    query = MagicMock()
    query.prefetch_related.return_value.first = AsyncMock(return_value=value)
    return query


def test_extracts_provider_error_and_preserves_malformed_payload():
    provider_error = Exception(
        "request failed - {'error': {'message': 'provider unavailable'}}"
    )
    malformed_error = Exception("request failed - not-a-payload")

    assert chat._extract_llm_error_message(provider_error) == "provider unavailable"
    assert chat._extract_llm_error_message(malformed_error) == str(malformed_error)


def test_formats_empty_and_nonempty_llm_errors(monkeypatch):
    translate = MagicMock(side_effect=lambda key, **kwargs: (key, kwargs))
    monkeypatch.setattr(chat, "t", translate)

    assert chat._format_llm_error_message(Exception()) == ("model_call_failed", {})
    assert chat._format_llm_error_message(Exception("bad request")) == (
        "model_service_request_failed",
        {"message": "bad request"},
    )


@pytest.mark.asyncio
async def test_get_public_agent_requires_user_and_rejects_private_noncreator(
    monkeypatch,
):
    with pytest.raises(BusinessError):
        await chat.get_public_agent(uuid4())

    user = SimpleNamespace(id=uuid4(), is_superuser=False)
    agent = SimpleNamespace(
        visibility=AgentVisibility.PRIVATE,
        created_by=SimpleNamespace(id=uuid4()),
        team_id=uuid4(),
    )
    monkeypatch.setattr(
        chat.Agent, "filter", MagicMock(return_value=_query_with_first(agent))
    )

    with pytest.raises(BusinessError):
        await chat.get_public_agent(uuid4(), user)


@pytest.mark.asyncio
async def test_get_public_agent_allows_team_member_for_ownerless_private_agent(
    monkeypatch,
):
    user = SimpleNamespace(id=uuid4(), is_superuser=False)
    agent = SimpleNamespace(
        visibility=AgentVisibility.PRIVATE,
        created_by=None,
        team_id=uuid4(),
    )
    monkeypatch.setattr(
        chat.Agent, "filter", MagicMock(return_value=_query_with_first(agent))
    )
    member_query = MagicMock()
    member_query.exists = AsyncMock(return_value=True)
    monkeypatch.setattr(chat.TeamMember, "filter", MagicMock(return_value=member_query))

    assert await chat.get_public_agent(uuid4(), user) is agent


@pytest.mark.asyncio
async def test_build_round_steps_map_groups_only_steps_with_round_ids(monkeypatch):
    round_id = uuid4()
    canonical = SimpleNamespace(
        round_id=round_id,
        is_round_canonical=True,
        conversation_id=uuid4(),
    )
    step = SimpleNamespace(
        id=uuid4(),
        role=MessageRole.TOOL,
        content="result",
        tool_calls=None,
        tool_call_id="call-1",
        tool_name="search",
        reasoning_content=None,
        model_used=None,
        token_usage=None,
        duration_ms=4,
        is_manually_stopped=False,
        rag_context=None,
        created_at=None,
        round_id=round_id,
        round_index=1,
        round_role=MessageRoundRole.TOOL_RESULT,
        is_round_canonical=False,
        iteration_index=1,
        round_status=None,
    )
    orphan = SimpleNamespace(**{**vars(step), "round_id": None})
    query = MagicMock()
    query.order_by.return_value.all = AsyncMock(return_value=[step, orphan])
    monkeypatch.setattr(chat.Message, "filter", MagicMock(return_value=query))

    grouped = await chat.build_round_steps_map([canonical])

    assert grouped[round_id] == [
        {
            "id": step.id,
            "role": "tool",
            "content": "result",
            "tool_calls": None,
            "tool_call_id": "call-1",
            "tool_name": "search",
            "reasoning_content": None,
            "model_used": None,
            "token_usage": None,
            "duration_ms": 4,
            "is_manually_stopped": False,
            "rag_context": None,
            "created_at": None,
            "round_id": round_id,
            "round_index": 1,
            "round_role": "tool_result",
            "is_round_canonical": False,
            "iteration_index": 1,
            "round_status": None,
        }
    ]


@pytest.mark.asyncio
async def test_build_round_steps_map_skips_query_without_canonical_rounds(monkeypatch):
    message_filter = MagicMock()
    monkeypatch.setattr(chat.Message, "filter", message_filter)

    assert await chat.build_round_steps_map([]) == {}
    message_filter.assert_not_called()


@pytest.mark.asyncio
async def test_build_message_round_payloads_skips_steps_and_attaches_them(monkeypatch):
    round_id = uuid4()
    user_message = SimpleNamespace(
        round_id=round_id,
        round_role=MessageRoundRole.USER_INPUT,
        is_round_canonical=True,
    )
    step_message = SimpleNamespace(round_id=round_id, is_round_canonical=False)
    final_message = SimpleNamespace(
        round_id=round_id,
        round_role=MessageRoundRole.ASSISTANT_FINAL,
        is_round_canonical=True,
    )
    monkeypatch.setattr(
        chat,
        "build_round_steps_map",
        AsyncMock(return_value={round_id: [{"content": "tool result"}]}),
    )
    validated = MagicMock()
    validated.model_dump.side_effect = [{"role": "user"}, {"role": "assistant"}]
    monkeypatch.setattr(
        chat.MessageOut, "model_validate", MagicMock(return_value=validated)
    )

    payloads = await chat.build_message_round_payloads(
        [user_message, step_message, final_message]
    )

    assert payloads == [
        {"role": "user"},
        {"role": "assistant", "steps": [{"content": "tool result"}]},
    ]


@pytest.mark.asyncio
async def test_persist_partial_round_error_uses_fallback_and_saves(monkeypatch):
    message = SimpleNamespace(
        conversation_id=uuid4(),
        round_id=uuid4(),
        save=AsyncMock(),
    )
    monkeypatch.setattr(
        chat, "round_has_persisted_trace", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(chat, "now_utc", MagicMock(return_value="now"))
    monkeypatch.setattr(chat.time, "time", MagicMock(return_value=12.0))

    persisted = await chat.persist_partial_round_error(
        message,
        content="",
        reasoning="reasoning",
        model_used="model",
        start_time=10.0,
        first_token_time=10.5,
        fallback_content="request failed",
    )

    assert persisted is True
    assert message.content == "request failed"
    assert message.reasoning_content == "reasoning"
    assert message.duration_ms == 2000
    assert message.first_token_ms == 500
    assert message.round_status == MessageRoundStatus.ERROR
    message.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_persist_partial_round_error_skips_empty_untraced_round(monkeypatch):
    message = SimpleNamespace(round_id=uuid4())
    monkeypatch.setattr(
        chat, "round_has_persisted_trace", AsyncMock(return_value=False)
    )

    assert not await chat.persist_partial_round_error(
        message,
        content="",
        reasoning="",
        model_used=None,
        start_time=0,
    )


@pytest.mark.asyncio
async def test_post_run_answer_forwards_explicit_skip(monkeypatch):
    agent_id = uuid4()
    run_id = uuid4()
    original = SimpleNamespace(status=AgentRunStatus.WAITING)
    resumed = SimpleNamespace(worker_payload={})
    submit = AsyncMock(return_value=resumed)
    current_user = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(
        chat, "_split_run_auth", MagicMock(return_value=(current_user, None))
    )
    monkeypatch.setattr(chat.deps, "check_api_key_agent_access", AsyncMock())
    monkeypatch.setattr(chat, "_load_owned_run", AsyncMock(return_value=original))
    from app.services import agent_run_store
    from app.tasks.agent import run_agent_task

    monkeypatch.setattr(agent_run_store, "submit_user_answers", submit)
    monkeypatch.setattr(
        run_agent_task,
        "apply_async",
        MagicMock(return_value=SimpleNamespace(id=None)),
    )
    monkeypatch.setattr(
        chat, "_run_to_out", MagicMock(return_value={"id": str(run_id)})
    )
    monkeypatch.setattr(chat, "success", lambda *, data: {"data": data})

    result = await chat.post_run_answer(
        agent_id,
        run_id,
        RunAnswerCreate(tool_call_id="call-1", answers={}, skipped=True),
        auth_result=(current_user, None),
    )

    submit.assert_awaited_once_with(
        run_id,
        tool_call_id="call-1",
        answers={},
        skipped=True,
    )
    assert result == {"data": {"id": str(run_id)}}


@pytest.mark.asyncio
async def test_load_owned_run_allows_superuser_to_access_any_conversation(monkeypatch):
    agent_id = uuid4()
    run_id = uuid4()
    conv_id = uuid4()
    run = SimpleNamespace(id=run_id, agent_id=agent_id, conversation_id=conv_id)
    conv = SimpleNamespace(id=conv_id)

    from app.models.agent_run import AgentRun
    from app.models.agent import Conversation as _Conv

    monkeypatch.setattr(AgentRun, "get_or_none", AsyncMock(return_value=run))
    monkeypatch.setattr(_Conv, "get_or_none", AsyncMock(return_value=conv))

    superuser = SimpleNamespace(id=uuid4(), is_superuser=True)
    loaded = await chat._load_owned_run(agent_id, run_id, superuser)

    assert loaded is run
    _Conv.get_or_none.assert_awaited_once_with(id=conv_id)
