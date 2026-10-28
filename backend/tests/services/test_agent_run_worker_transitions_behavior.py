"""Consumer-visible lifecycle behavior for the durable AgentRun worker.

Covers terminal races (stop vs. completion vs. approval resume), cancellation
of approved work that must never execute, failure propagation to the run
stream, and the canonical tool-result/asset replay that the user observes on
resume. Persisted-state assertions use a real SQLite schema; Redis and the
event stream are replaced by small in-memory fakes.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from tortoise import Tortoise

from app.llm.tools.interaction import ToolInteractionRequest
from app.models.agent import (
    Agent,
    Conversation,
    Message,
    MessageRole,
)
from app.models.agent_run import (
    AgentRun,
    AgentRunInputKind,
    AgentRunMode,
    AgentRunStatus,
)
from app.models.tool import CustomToolType, Tool, ToolType
from app.models.user import Team, TeamMember, User
from app.schemas.tool_approval import (
    ExecutionEntrypoint,
    ExecutionRunKind,
    ToolExecutionCancelReason,
    ToolExecutionStatus,
)
from app.services import agent_run_store, tool_approvals
from app.services.agent_loop import AgentLoopContext
from app.services.agent_run_worker import (
    _create_placeholder,
    _execute_approved_pending_tool,
    _marker_int,
    _marker_uuid,
    _transition_active_run,
    run_agent_round,
)

OFF = SimpleNamespace(value="off")


class _Redis:
    async def set(self, key, value, ex=None, nx=False):
        return True

    async def get(self, key):
        return None

    async def delete(self, key):
        return True

    async def expire(self, key, seconds):
        return True

    async def publish(self, channel, message):
        return 1


@asynccontextmanager
async def _database(monkeypatch):
    monkeypatch.setattr(
        agent_run_store, "record_observability_progress", lambda *a, **k: None
    )

    async def _get_redis():
        return _Redis()

    monkeypatch.setattr(agent_run_store, "get_redis", _get_redis)
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        yield
    finally:
        await Tortoise.close_connections()


async def _user() -> User:
    return await User.create(
        id=uuid4(),
        username=f"worker_{uuid4().hex[:8]}",
        email=f"{uuid4().hex}@worker.test",
        hashed_password="x",
    )


async def _team_and_agent(owner: User):
    team = await Team.create(id=uuid4(), name=f"worker_team_{uuid4().hex[:8]}")
    await TeamMember.create(id=uuid4(), team_id=team.id, user_id=owner.id, role="owner")
    agent = await Agent.create(id=uuid4(), team_id=team.id, name="worker-agent")
    conversation = await Conversation.create(
        id=uuid4(), agent_id=agent.id, user_id=owner.id
    )
    return team, agent, conversation


async def _allow_tool(team: Team) -> Tool:
    return await Tool.create(
        id=uuid4(),
        team_id=team.id,
        name=f"worker_tool_{uuid4().hex[:8]}",
        display_name="Worker tool",
        description="worker test",
        type=ToolType.CUSTOM,
        custom_type=CustomToolType.HTTP,
        approval_policy={"default_decision": "allow"},
    )


async def _execution(*, tool, actor, team, run, tool_call_id="call-1"):
    return await tool_approvals.create_execution(
        tool=tool,
        operation="todo.write",
        parameters={"value": 1},
        actor=actor,
        team_id=team.id,
        entrypoint=ExecutionEntrypoint.AGENT_RUN,
        entrypoint_id=str(run.agent_id),
        run_kind=ExecutionRunKind.AGENT,
        run_id=run.id,
        tool_call_id=tool_call_id,
    )


async def _run_row(agent, conversation, user, *, status):
    return await AgentRun.create(
        id=uuid4(),
        agent_id=agent.id,
        conversation_id=conversation.id,
        user_id=user.id,
        mode=AgentRunMode.SEND,
        status=status,
        active_round_id=uuid4(),
    )


def _stream():
    return SimpleNamespace(seed_sequence=AsyncMock(), publish=AsyncMock())


def _approval_payload(run, execution):
    return {
        "run_id": str(run.id),
        "agent_id": str(run.agent_id),
        "conversation_id": str(run.conversation_id),
        "locale": "en",
        "resume_tool_approval": {
            "execution_id": str(execution.id),
            "tool_call_id": "call-1",
            "tool_name": "worker_tool",
        },
    }


# ---------------------------------------------------------------------------
# state transition primitives
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transition_active_run_ignores_disallowed_states(monkeypatch):
    run = SimpleNamespace(id=uuid4(), status=AgentRunStatus.STOPPED)
    transition = AsyncMock()
    monkeypatch.setattr(agent_run_store, "transition_run_if_status", transition)

    current, moved = await _transition_active_run(
        run, AgentRunStatus.STOPPED, allowed_statuses=(AgentRunStatus.RUNNING,)
    )

    assert current is run
    assert moved is False
    transition.assert_not_awaited()


@pytest.mark.asyncio
async def test_transition_active_run_reports_the_race_winner(monkeypatch):
    run = SimpleNamespace(id=uuid4(), status=AgentRunStatus.RUNNING)
    winner = SimpleNamespace(id=run.id, status=AgentRunStatus.COMPLETED)
    monkeypatch.setattr(
        agent_run_store, "transition_run_if_status", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(agent_run_store, "get_run", AsyncMock(return_value=winner))

    current, moved = await _transition_active_run(
        run, AgentRunStatus.STOPPED, allowed_statuses=(AgentRunStatus.RUNNING,)
    )

    assert current is winner
    assert current.status == AgentRunStatus.COMPLETED
    assert moved is False


@pytest.mark.asyncio
async def test_transition_active_run_stops_when_the_row_disappears(monkeypatch):
    run = SimpleNamespace(id=uuid4(), status=AgentRunStatus.RUNNING)
    monkeypatch.setattr(
        agent_run_store, "transition_run_if_status", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(agent_run_store, "get_run", AsyncMock(return_value=None))

    current, moved = await _transition_active_run(
        run, AgentRunStatus.STOPPED, allowed_statuses=(AgentRunStatus.RUNNING,)
    )

    assert current is None
    assert moved is False


def test_approval_resume_marker_validation_rejects_bad_types():
    assert _marker_int(None, "round_index") is None
    assert _marker_int("3", "round_index") == 3
    with pytest.raises(ValueError, match="round_index is invalid"):
        _marker_int(True, "round_index")
    with pytest.raises(ValueError, match="round_index is invalid"):
        _marker_int("not-a-number", "round_index")

    assert _marker_uuid(None) is None
    assert _marker_uuid("") is None
    valid = uuid4()
    assert _marker_uuid(str(valid)) == valid
    with pytest.raises(ValueError, match="round_id is invalid"):
        _marker_uuid("not-a-uuid")


# ---------------------------------------------------------------------------
# approved-tool resume: failure propagation
# ---------------------------------------------------------------------------


def _fake_execution(run, **values):
    defaults = {
        "run_id": run.id,
        "tool_call_id": "call-1",
        "run_kind": ExecutionRunKind.AGENT,
        "status": ToolExecutionStatus.READY,
        "parameters_preview": {"value": 1},
        "entrypoint": ExecutionEntrypoint.AGENT_RUN,
        "entrypoint_id": "entrypoint-1",
    }
    defaults.update(values)
    return SimpleNamespace(**defaults)


def _patch_resume(monkeypatch, execution, *, actor, execute=None, payloads=None):
    monkeypatch.setattr(
        "app.services.tool_approvals.get_execution",
        AsyncMock(return_value=execution),
    )
    recorded = AsyncMock(
        return_value={"resume_tool_result": {"tool_call_id": "call-1"}}
    )
    monkeypatch.setattr(
        "app.services.agent_run_store.record_resumed_tool_result", recorded
    )
    monkeypatch.setattr(
        "app.models.user.User.get_or_none", AsyncMock(return_value=actor)
    )
    if execute is not None:
        monkeypatch.setattr(
            "app.api.v1.endpoints.chat_tools.execute_tool_call", execute
        )
    if payloads is not None:
        monkeypatch.setattr(
            "app.utils.tool_output.get_tool_execution_payloads", payloads
        )
    return recorded


@pytest.mark.asyncio
async def test_resume_without_marker_leaves_payload_untouched():
    payload = {"run_id": str(uuid4())}
    result = await _execute_approved_pending_tool(
        payload,
        run=SimpleNamespace(id=uuid4(), active_round_id=None),
        agent=SimpleNamespace(id=uuid4()),
        conversation=SimpleNamespace(id=uuid4(), user_id=uuid4()),
    )
    assert result is payload


@pytest.mark.asyncio
async def test_resume_with_incomplete_marker_is_rejected():
    with pytest.raises(RuntimeError, match="approval resume marker is invalid"):
        await _execute_approved_pending_tool(
            {"resume_tool_approval": {"execution_id": str(uuid4())}},
            run=SimpleNamespace(id=uuid4(), active_round_id=None),
            agent=SimpleNamespace(id=uuid4()),
            conversation=SimpleNamespace(id=uuid4(), user_id=uuid4()),
        )


@pytest.mark.asyncio
async def test_stale_approved_execution_becomes_a_visible_tool_error(monkeypatch):
    run = SimpleNamespace(id=uuid4(), active_round_id=uuid4())
    execution = _fake_execution(run, run_id=uuid4())
    recorded = _patch_resume(monkeypatch, execution, actor=SimpleNamespace(id=uuid4()))

    updated = await _execute_approved_pending_tool(
        {
            "resume_tool_approval": {
                "execution_id": str(uuid4()),
                "tool_call_id": "call-1",
                "tool_name": "worker_tool",
            }
        },
        run=run,
        agent=SimpleNamespace(id=uuid4()),
        conversation=SimpleNamespace(id=uuid4(), user_id=uuid4()),
    )

    kwargs = recorded.await_args.kwargs
    assert kwargs["is_error"] is True
    assert "approved tool execution is no longer ready" in kwargs["display_result"]
    metric = updated["resume_dependency_metrics"][0]
    assert metric["status"] == "failed"
    assert metric["error_category"] == "RuntimeError"


@pytest.mark.asyncio
async def test_resume_without_run_user_records_tool_error(monkeypatch):
    run = SimpleNamespace(id=uuid4(), active_round_id=uuid4())
    execution = _fake_execution(run)
    recorded = _patch_resume(monkeypatch, execution, actor=None)

    updated = await _execute_approved_pending_tool(
        {
            "resume_tool_approval": {
                "execution_id": str(uuid4()),
                "tool_call_id": "call-1",
                "tool_name": "worker_tool",
            }
        },
        run=run,
        agent=SimpleNamespace(id=uuid4()),
        conversation=SimpleNamespace(id=uuid4(), user_id=uuid4()),
    )

    kwargs = recorded.await_args.kwargs
    assert kwargs["is_error"] is True
    assert "run user is missing" in kwargs["display_result"]
    assert updated["resume_dependency_metrics"][0]["status"] == "failed"


@pytest.mark.asyncio
async def test_resume_that_pauses_again_is_reported_as_a_tool_error(monkeypatch):
    run = SimpleNamespace(id=uuid4(), active_round_id=uuid4())
    execution = _fake_execution(run)
    recorded = _patch_resume(
        monkeypatch,
        execution,
        actor=SimpleNamespace(id=uuid4()),
        execute=AsyncMock(return_value=ToolInteractionRequest("ask_user", {})),
    )

    updated = await _execute_approved_pending_tool(
        {
            "resume_tool_approval": {
                "execution_id": str(uuid4()),
                "tool_call_id": "call-1",
                "tool_name": "worker_tool",
            }
        },
        run=run,
        agent=SimpleNamespace(id=uuid4()),
        conversation=SimpleNamespace(id=uuid4(), user_id=uuid4()),
    )

    kwargs = recorded.await_args.kwargs
    assert kwargs["is_error"] is True
    assert "approved tool execution did not resume" in kwargs["display_result"]
    assert updated["resume_dependency_metrics"][0]["error_category"] == "RuntimeError"


@pytest.mark.asyncio
async def test_successful_resume_marks_the_dependency_metric_completed(monkeypatch):
    run = SimpleNamespace(id=uuid4(), active_round_id=uuid4())
    execution = _fake_execution(run)
    recorded = _patch_resume(
        monkeypatch,
        execution,
        actor=SimpleNamespace(id=uuid4()),
        execute=AsyncMock(return_value={"ok": True}),
        payloads=lambda _result, _name: ('{"ok": true}', '{"ok": true}'),
    )

    updated = await _execute_approved_pending_tool(
        {
            "resume_tool_approval": {
                "execution_id": str(uuid4()),
                "tool_call_id": "call-1",
                "tool_name": "worker_tool",
            }
        },
        run=run,
        agent=SimpleNamespace(id=uuid4()),
        conversation=SimpleNamespace(id=uuid4(), user_id=uuid4()),
    )

    assert recorded.await_args.kwargs["is_error"] is False
    metric = updated["resume_dependency_metrics"][0]
    assert metric["status"] == "completed"
    assert metric["error_category"] is None


@pytest.mark.asyncio
async def test_non_json_tool_output_still_completes_the_resume(monkeypatch):
    run = SimpleNamespace(id=uuid4(), active_round_id=uuid4())
    execution = _fake_execution(run)
    _patch_resume(
        monkeypatch,
        execution,
        actor=SimpleNamespace(id=uuid4()),
        execute=AsyncMock(return_value={"ok": True}),
        payloads=lambda _result, _name: ("plain output", "plain output"),
    )

    updated = await _execute_approved_pending_tool(
        {
            "resume_tool_approval": {
                "execution_id": str(uuid4()),
                "tool_call_id": "call-1",
                "tool_name": "worker_tool",
            }
        },
        run=run,
        agent=SimpleNamespace(id=uuid4()),
        conversation=SimpleNamespace(id=uuid4(), user_id=uuid4()),
    )

    assert updated["resume_dependency_metrics"][0]["status"] == "completed"
    assert updated["resume_dependency_metrics"][0]["error_category"] is None


@pytest.mark.asyncio
async def test_tool_error_result_marks_the_dependency_metric_failed(monkeypatch):
    run = SimpleNamespace(id=uuid4(), active_round_id=uuid4())
    execution = _fake_execution(run)
    _patch_resume(
        monkeypatch,
        execution,
        actor=SimpleNamespace(id=uuid4()),
        execute=AsyncMock(return_value={"error": "denied"}),
        payloads=lambda _result, _name: (
            '{"error": "denied"}',
            '{"error": "denied"}',
        ),
    )

    updated = await _execute_approved_pending_tool(
        {
            "resume_tool_approval": {
                "execution_id": str(uuid4()),
                "tool_call_id": "call-1",
                "tool_name": "worker_tool",
            }
        },
        run=run,
        agent=SimpleNamespace(id=uuid4()),
        conversation=SimpleNamespace(id=uuid4(), user_id=uuid4()),
    )

    metric = updated["resume_dependency_metrics"][0]
    assert metric["status"] == "failed"
    assert metric["error_category"] == "tool_error"


# ---------------------------------------------------------------------------
# stop / cancellation on a real database
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stopping_a_paused_run_cancels_the_approved_execution(monkeypatch):
    """A stop accepted before resume runs must cancel, not execute, the tool."""
    async with _database(monkeypatch):
        user = await _user()
        team, agent, conversation = await _team_and_agent(user)
        tool = await _allow_tool(team)
        run = await _run_row(agent, conversation, user, status=AgentRunStatus.STOPPING)
        execution = await _execution(tool=tool, actor=user, team=team, run=run)
        stream = _stream()
        from app.services import agent_run_worker as worker

        monkeypatch.setattr(worker, "AgentRunStream", lambda _run_id: stream)

        result = await run_agent_round(_approval_payload(run, execution))

        assert result == {"status": AgentRunStatus.STOPPED.value}
        stored = await tool_approvals.get_execution(execution.id)
        assert stored.status == ToolExecutionStatus.CANCELLED
        assert stored.cancel_reason == ToolExecutionCancelReason.RUN_STOPPED
        refreshed = await AgentRun.get(id=run.id)
        assert refreshed.status == AgentRunStatus.STOPPED
        assert (
            "run_end",
            {"status": "stopped"},
        ) in [
            (call.args[0], call.args[1])
            for call in stream.publish.await_args_list
            if len(call.args) >= 2
        ]


@pytest.mark.asyncio
async def test_stop_cancellation_failure_does_not_block_the_stopped_status(
    monkeypatch,
):
    async with _database(monkeypatch):
        user = await _user()
        team, agent, conversation = await _team_and_agent(user)
        tool = await _allow_tool(team)
        run = await _run_row(agent, conversation, user, status=AgentRunStatus.STOPPING)
        execution = await _execution(tool=tool, actor=user, team=team, run=run)
        stream = _stream()
        from app.services import agent_run_worker as worker

        monkeypatch.setattr(worker, "AgentRunStream", lambda _run_id: stream)
        monkeypatch.setattr(
            "app.services.tool_approvals.cancel_execution",
            AsyncMock(side_effect=RuntimeError("approval store unavailable")),
        )

        result = await run_agent_round(_approval_payload(run, execution))

        assert result == {"status": AgentRunStatus.STOPPED.value}
        refreshed = await AgentRun.get(id=run.id)
        assert refreshed.status == AgentRunStatus.STOPPED


@pytest.mark.asyncio
async def test_stop_accepted_during_approval_resume_cancels_execution(monkeypatch):
    async with _database(monkeypatch):
        user = await _user()
        team, agent, conversation = await _team_and_agent(user)
        tool = await _allow_tool(team)
        run = await _run_row(agent, conversation, user, status=AgentRunStatus.RUNNING)
        execution = await _execution(tool=tool, actor=user, team=team, run=run)
        stream = _stream()
        from app.services import agent_run_worker as worker

        monkeypatch.setattr(worker, "AgentRunStream", lambda _run_id: stream)
        monkeypatch.setattr(
            agent_run_store, "has_pending_inputs", AsyncMock(side_effect=[False, True])
        )
        monkeypatch.setattr(
            agent_run_store, "acquire_run_lock", AsyncMock(return_value=True)
        )
        monkeypatch.setattr(agent_run_store, "release_run_lock", AsyncMock())

        async def _heartbeat(_run_id, _conversation_id, stop):
            await stop.wait()

        monkeypatch.setattr(agent_run_store, "heartbeat_run_lock", _heartbeat)

        result = await run_agent_round(_approval_payload(run, execution))

        assert result == {"status": AgentRunStatus.STOPPED.value}
        stored = await tool_approvals.get_execution(execution.id)
        assert stored.status == ToolExecutionStatus.CANCELLED
        assert stored.cancel_reason == ToolExecutionCancelReason.RUN_STOPPED
        refreshed = await AgentRun.get(id=run.id)
        assert refreshed.status == AgentRunStatus.STOPPED
        assert any(
            call.args[0] == "run_end" and call.args[1]["status"] == "stopped"
            for call in stream.publish.await_args_list
            if len(call.args) >= 2
        )


@pytest.mark.asyncio
async def test_resume_losing_its_row_to_a_stop_ends_stopped(monkeypatch):
    async with _database(monkeypatch):
        user = await _user()
        team, agent, conversation = await _team_and_agent(user)
        tool = await _allow_tool(team)
        run = await _run_row(agent, conversation, user, status=AgentRunStatus.RUNNING)
        execution = await _execution(tool=tool, actor=user, team=team, run=run)
        stream = _stream()
        from app.services import agent_run_worker as worker

        async def _record_lost(_payload, **_kwargs):
            await AgentRun.filter(id=run.id).update(status=AgentRunStatus.STOPPING)
            run.status = AgentRunStatus.STOPPING
            return None

        monkeypatch.setattr(worker, "_execute_approved_pending_tool", _record_lost)
        monkeypatch.setattr(worker, "AgentRunStream", lambda _run_id: stream)
        monkeypatch.setattr(
            agent_run_store, "has_pending_inputs", AsyncMock(return_value=False)
        )
        monkeypatch.setattr(
            agent_run_store, "acquire_run_lock", AsyncMock(return_value=True)
        )
        monkeypatch.setattr(agent_run_store, "release_run_lock", AsyncMock())

        async def _heartbeat(_run_id, _conversation_id, stop):
            await stop.wait()

        monkeypatch.setattr(agent_run_store, "heartbeat_run_lock", _heartbeat)

        result = await run_agent_round(_approval_payload(run, execution))

        assert result == {"status": AgentRunStatus.STOPPED.value}
        refreshed = await AgentRun.get(id=run.id)
        assert refreshed.status == AgentRunStatus.STOPPED
        assert any(
            call.args[0] == "run_end" and call.args[1]["status"] == "stopped"
            for call in stream.publish.await_args_list
            if len(call.args) >= 2
        )


@pytest.mark.asyncio
async def test_create_placeholder_anchors_the_canonical_reply(monkeypatch):
    async with _database(monkeypatch):
        user = await _user()
        team, agent, conversation = await _team_and_agent(user)
        round_id = uuid4()
        user_msg = await Message.create(
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content="question",
            round_id=round_id,
        )
        run = SimpleNamespace(id=uuid4(), active_round_id=uuid4())

        placeholder = await _create_placeholder(conversation, user_msg, run)

        stored = await Message.get(id=placeholder.id)
        assert stored.role == MessageRole.ASSISTANT
        assert stored.content == ""
        assert stored.branch_parent_id == user_msg.id
        assert stored.round_id == run.active_round_id
        assert stored.round_index == 0
        assert stored.is_round_canonical is True


# ---------------------------------------------------------------------------
# in-round worker behavior (event/stream/canonical reuse)
# ---------------------------------------------------------------------------


def _run(status=AgentRunStatus.RUNNING, **values):
    run = SimpleNamespace(
        id=uuid4(),
        agent_id=uuid4(),
        conversation_id=uuid4(),
        user_id=uuid4(),
        mode=SimpleNamespace(value="send"),
        status=status,
        source_message_id=None,
        canonical_message_id=None,
        active_round_id=uuid4(),
        started_at=None,
        message_started_at=None,
        first_token_ms=None,
        finished_at=None,
        error_code=None,
        error_message=None,
        pending_tool_call_id=None,
        pending_tool_name=None,
        pending_tool_input=None,
        worker_payload=None,
    )
    run.save = AsyncMock(return_value=None)
    for key, value in values.items():
        setattr(run, key, value)
    return run


def _round_result(**values):
    defaults = {
        "waiting_for_user": False,
        "deadline_exceeded": False,
        "manually_stopped": False,
        "max_iterations_reached": False,
        "full_content": "answer",
        "full_reasoning": None,
        "aggregate_input_tokens": 0,
        "aggregate_output_tokens": 0,
        "aggregate_cache_read_tokens": 0,
        "aggregate_cache_creation_tokens": 0,
        "aggregate_total_input_tokens": 0,
        "duration_ms": 0,
        "first_token_ms": None,
        "dependency_metrics": [],
        "dependency_metrics_truncated": False,
        "created_message_count": 2,
        "final_round_index": 1,
    }
    defaults.update(values)
    return SimpleNamespace(**defaults)


def _round_payload(run):
    return {
        "run_id": str(run.id),
        "agent_id": str(run.agent_id),
        "conversation_id": str(run.conversation_id),
        "locale": "en",
    }


def _prepare_round(
    monkeypatch,
    *,
    run=None,
    result=None,
    loop_callback=None,
    transition=None,
    get_run=None,
    canonical=None,
):
    from app.services import agent_run_worker as worker

    run = run or _run()
    result = result or _round_result()
    agent = SimpleNamespace(id=run.agent_id, rag_mode=OFF)
    conversation = SimpleNamespace(
        id=run.conversation_id,
        user_id=run.user_id,
        title="title",
        message_count=0,
        token_usage=0,
    )
    user_message = SimpleNamespace(
        id=uuid4(), content="question", rag_context=None, round_id=uuid4()
    )
    canonical = canonical or SimpleNamespace(
        id=uuid4(), branch_parent_id=None, save=AsyncMock()
    )
    stream = _stream()
    context = AgentLoopContext(
        agent=agent,
        conversation=conversation,
        user=SimpleNamespace(id=run.user_id),
        model_id="model",
        tokenizer_model_id=None,
        model_provider=None,
        model_context_limit=None,
        model_max_output_tokens=None,
        model_used="model",
        sandbox_session_id=None,
        round_id=run.active_round_id,
        deadline_seconds=120.0,
    )

    class _Loop:
        def __init__(self):
            self.result = result

        async def run(self):
            if loop_callback is not None:
                await loop_callback(context)
            yield "chunk"

    loop = _Loop()

    async def _rebuild(*_args, **kwargs):
        loop.event_queue = kwargs["event_queue"]
        return context, user_message, loop

    if transition is None:

        async def transition(current, expected, status, **_kwargs):
            if current.status != expected:
                return None
            current.status = status
            return current

    async def _heartbeat(_run_id, _conversation_id, stop):
        await stop.wait()

    monkeypatch.setattr(
        worker.agent_run_store, "get_run", get_run or AsyncMock(return_value=run)
    )
    monkeypatch.setattr(worker.Agent, "get_or_none", AsyncMock(return_value=agent))
    monkeypatch.setattr(
        worker.Conversation, "get_or_none", AsyncMock(return_value=conversation)
    )
    monkeypatch.setattr(
        worker.Message, "get_or_none", AsyncMock(return_value=canonical)
    )
    monkeypatch.setattr(
        worker, "_create_placeholder", AsyncMock(return_value=canonical)
    )
    monkeypatch.setattr(worker, "_rebuild_context", _rebuild)
    monkeypatch.setattr(worker, "AgentRunStream", lambda _run_id: stream)
    monkeypatch.setattr(
        worker.agent_run_store, "acquire_run_lock", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(worker.agent_run_store, "release_run_lock", AsyncMock())
    monkeypatch.setattr(worker.agent_run_store, "heartbeat_run_lock", _heartbeat)
    monkeypatch.setattr(
        worker.agent_run_store, "has_pending_inputs", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(
        worker.agent_run_store, "consume_next_input", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(worker.agent_run_store, "drop_pending_inputs", AsyncMock())
    monkeypatch.setattr(worker.agent_run_store, "park_run_waiting", AsyncMock())
    monkeypatch.setattr(
        worker.agent_run_store,
        "queue_agent_run_resume_if_approval_terminal",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(worker, "_finalize_completed", AsyncMock())
    monkeypatch.setattr(worker, "_finalize_stopped", AsyncMock())
    monkeypatch.setattr(
        "app.tasks.memory.schedule_background_memory_extraction", AsyncMock()
    )
    monkeypatch.setattr(worker, "record_dependency_metrics", AsyncMock())
    monkeypatch.setattr(worker.agent_run_store, "transition_run_if_status", transition)
    monkeypatch.setattr(
        worker.agent_run_store, "record_observability_progress", lambda *a, **k: None
    )
    monkeypatch.setattr(
        worker,
        "sandbox_gateway",
        SimpleNamespace(begin_round=AsyncMock(), finish_round=AsyncMock()),
    )
    return run, stream, canonical, context, user_message, loop


@pytest.mark.asyncio
async def test_resume_reuses_canonical_message_and_publishes_tool_result(monkeypatch):
    canonical = SimpleNamespace(id=uuid4(), branch_parent_id=None, save=AsyncMock())
    run = _run(canonical_message_id=canonical.id)
    metric = {"name": "worker_tool", "status": "completed"}
    run, stream, canonical, _context, _user_msg, loop = _prepare_round(
        monkeypatch, run=run, canonical=canonical
    )
    loop.result.dependency_metrics = []
    payload = dict(_round_payload(run))
    payload["resume_tool_result"] = {"tool_call_id": "call-1", "result": "ok"}
    payload["resume_dependency_metrics"] = [metric, "ignored"]

    output = await run_agent_round(payload)

    assert output == {
        "status": AgentRunStatus.COMPLETED.value,
        "message_id": str(canonical.id),
    }
    assert loop.result.dependency_metrics == [metric]
    message_start_calls = [
        call
        for call in stream.publish.await_args_list
        if call.args and call.args[0] == "message_start"
    ]
    assert message_start_calls
    assert message_start_calls[0].kwargs["message_id"] == canonical.id
    tool_result_calls = [
        call
        for call in stream.publish.await_args_list
        if call.args and call.args[0] == "tool_result"
    ]
    assert tool_result_calls
    call = tool_result_calls[0]
    assert call.args[1] == payload["resume_tool_result"]
    assert call.kwargs["round_id"] == run.active_round_id
    assert call.kwargs["message_id"] == canonical.id


@pytest.mark.asyncio
async def test_steer_input_is_persisted_and_visible_as_a_step_message(monkeypatch):
    item = SimpleNamespace(
        kind=AgentRunInputKind.STEER, content="please focus", sequence=3
    )
    step = SimpleNamespace(id=uuid4())

    async def _consume(context):
        await context.input_consumed(item)

    run, stream, _canonical, context, _user_msg, _loop = _prepare_round(
        monkeypatch, loop_callback=_consume
    )
    from app.services import agent_run_worker as worker

    monkeypatch.setattr(worker.Message, "create", AsyncMock(return_value=step))
    monkeypatch.setattr(
        "app.models.user.User.get_or_none",
        AsyncMock(return_value=SimpleNamespace(id=run.user_id)),
    )
    monkeypatch.setattr(
        "app.services.audit_log.AuditLogService.snapshot", lambda *_a, **_k: {"id": "x"}
    )
    monkeypatch.setattr(
        "app.services.audit_log.AuditLogService.build_changes", lambda *_a, **_k: {}
    )
    log = AsyncMock()
    monkeypatch.setattr("app.services.audit_log.AuditLogService.log", log)

    output = await run_agent_round(_round_payload(run))

    assert output["status"] == AgentRunStatus.COMPLETED.value
    assert context.working_history_override[-1] == {
        "role": "user",
        "content": "please focus",
        "round_id": str(run.active_round_id),
        "round_index": 10_003,
        "round_role": "user_input",
        "is_round_canonical": True,
        "round_status": "completed",
    }
    accepted = [
        call.args[1]
        for call in stream.publish.await_args_list
        if call.args and call.args[0] == "input_accepted"
    ]
    assert accepted == [{"kind": "steer", "content": "please focus", "sequence": 3}]


@pytest.mark.asyncio
async def test_steer_input_persist_failure_fails_the_run(monkeypatch):
    item = SimpleNamespace(
        kind=AgentRunInputKind.STEER, content="please focus", sequence=3
    )

    async def _consume(context):
        await context.input_consumed(item)

    run, stream, _canonical, _context, _user, _loop = _prepare_round(
        monkeypatch, loop_callback=_consume
    )
    from app.services import agent_run_worker as worker

    monkeypatch.setattr(
        worker.Message,
        "create",
        AsyncMock(side_effect=RuntimeError("step write failed")),
    )

    output = await run_agent_round(_round_payload(run))

    assert output == {
        "status": AgentRunStatus.FAILED.value,
        "error": "step write failed",
    }
    failed = [
        call.args[1]
        for call in stream.publish.await_args_list
        if call.args and call.args[0] == "error"
    ]
    assert failed == [{"code": "run_failed", "msg": "step write failed"}]


@pytest.mark.asyncio
async def test_stop_requested_short_circuits_once_the_run_is_stopping(monkeypatch):
    from app.services import agent_run_worker as worker

    async def _observe(context):
        run.status = AgentRunStatus.STOPPING
        assert await context.stop_requested() is True
        assert await context.is_disconnected() is True
        run.status = AgentRunStatus.RUNNING

    run, _stream, _canonical, _context, _user, _loop = _prepare_round(
        monkeypatch, loop_callback=_observe
    )

    async def _pending(*_args, **_kwargs):
        assert run.status != AgentRunStatus.STOPPING, (
            "stop short-circuit must not consult the durable input queue"
        )
        return False

    monkeypatch.setattr(worker.agent_run_store, "has_pending_inputs", _pending)
    output = await run_agent_round(_round_payload(run))

    assert output["status"] == AgentRunStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_waiting_run_defers_to_the_decision_scheduler(monkeypatch):
    """A decision that beat the park must not publish a false WAITING status."""
    run = _run()
    completed = SimpleNamespace(id=run.id, status=AgentRunStatus.COMPLETED)
    get_run = AsyncMock(side_effect=[run, completed])
    from app.services import agent_run_worker as worker

    async def _park(current, **interaction):
        current.status = AgentRunStatus.WAITING
        current.pending_tool_call_id = "call-1"
        current.pending_tool_name = "ask_user"
        current.pending_tool_input = {"questions": []}
        current.worker_payload = interaction["worker_payload"]

    async def _pause(context_obj):
        await context_obj.pause_for_user(
            tool_call_id="call-1",
            tool_name="ask_user",
            arguments={"questions": []},
            round_id=context_obj.round_id,
            round_index=3,
            iteration_index=2,
        )
        loop.event_queue.put_nowait(("tool_call", {"id": "call-1"}))

    run, stream, _canonical, context, _user, loop = _prepare_round(
        monkeypatch,
        run=run,
        result=_round_result(waiting_for_user=True),
        get_run=get_run,
        loop_callback=_pause,
    )
    monkeypatch.setattr(worker.agent_run_store, "park_run_waiting", _park)

    output = await run_agent_round(_round_payload(run))

    assert output == {"status": "completed", "tool_call_id": "call-1"}
    assert not any(
        call.args[0] == "run_status" for call in stream.publish.await_args_list
    )


@pytest.mark.asyncio
async def test_deferred_resume_returned_queued_then_dispatch_failure_fails_it(
    monkeypatch,
):
    run = _run()
    deferred = SimpleNamespace(
        id=uuid4(), status=AgentRunStatus.QUEUED, worker_payload={"run_id": "x"}
    )
    get_run = AsyncMock(side_effect=[run, run])
    from app.services import agent_run_worker as worker

    async def _park(current, **interaction):
        current.status = AgentRunStatus.WAITING
        current.pending_tool_call_id = "call-1"
        current.pending_tool_name = "ask_user"
        current.pending_tool_input = {"questions": []}
        current.worker_payload = interaction["worker_payload"]

    async def _transition(current, expected, status, **kwargs):
        if current.status != expected:
            return None
        current.status = status
        return current

    calls: list[str] = []

    async def _release(*_args, **_kwargs):
        calls.append("release")

    async def _dispatch(*_args, **_kwargs):
        calls.append("dispatch")
        raise RuntimeError("celery down")

    async def _pause(context_obj):
        await context_obj.pause_for_user(
            tool_call_id="call-1",
            tool_name="ask_user",
            arguments={"questions": []},
            round_id=context_obj.round_id,
            round_index=3,
            iteration_index=2,
        )
        loop.event_queue.put_nowait(("tool_call", {"id": "call-1"}))

    run, stream, _canonical, context, _user, loop = _prepare_round(
        monkeypatch,
        run=run,
        result=_round_result(waiting_for_user=True),
        get_run=get_run,
        transition=_transition,
        loop_callback=_pause,
    )
    monkeypatch.setattr(worker.agent_run_store, "park_run_waiting", _park)
    monkeypatch.setattr(
        worker.agent_run_store,
        "queue_agent_run_resume_if_approval_terminal",
        AsyncMock(return_value=deferred),
    )
    monkeypatch.setattr(worker.agent_run_store, "release_run_lock", _release)
    monkeypatch.setattr(worker.agent_run_store, "transition_run_if_status", _transition)
    monkeypatch.setattr("app.services.agent_submission.dispatch_run", _dispatch)

    output = await run_agent_round(_round_payload(run))

    assert output == {"status": "queued", "tool_call_id": "call-1"}
    assert deferred.status == AgentRunStatus.FAILED
    assert calls == ["release", "dispatch"]


# ---------------------------------------------------------------------------
# rebuild-context: scoped attachments and provider turn delegation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rebuild_context_passes_only_conversation_scoped_assets(monkeypatch):
    from app.models.agent import RAGMode
    from app.services import agent_run_worker

    agent = SimpleNamespace(
        id=uuid4(),
        team_id=None,
        rag_mode=RAGMode.OFF,
        tools_config=[],
        enable_user_input_request=True,
        enable_memory=False,
        enable_attachments=False,
        enable_image_generation=False,
        enable_video_generation=False,
        streaming_config=None,
    )
    conversation = SimpleNamespace(id=uuid4(), user_id=uuid4())
    user_msg = SimpleNamespace(id=uuid4(), rag_context=None, content="question")
    bound_asset = SimpleNamespace(
        checksum="sum-1", content_type="image/png", display_filename="pic.png"
    )
    orphan_asset = SimpleNamespace(
        checksum="sum-2", content_type="image/jpeg", display_filename="gone.jpg"
    )
    links = [
        SimpleNamespace(asset_id=uuid4(), asset=bound_asset),
        SimpleNamespace(asset_id=uuid4(), asset=orphan_asset),
    ]

    async def _links(*_args, **_kwargs):
        return links

    monkeypatch.setattr(
        "app.models.asset.MessageAsset",
        SimpleNamespace(
            filter=lambda **_kwargs: SimpleNamespace(
                prefetch_related=lambda *_a: SimpleNamespace(
                    order_by=lambda *_a: _links()
                )
            )
        ),
    )
    monkeypatch.setattr(
        "app.models.asset.AssetScopeRef",
        SimpleNamespace(
            get_or_none=AsyncMock(side_effect=[SimpleNamespace(ref="scoped-ref"), None])
        ),
    )
    monkeypatch.setattr(
        "app.services.agent_run_worker.Message.get_or_none",
        AsyncMock(return_value=user_msg),
    )
    monkeypatch.setattr(
        "app.services.sandbox.gateway.sandbox_gateway.create_session",
        AsyncMock(return_value="session-1"),
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.chat.get_agent_tools", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.chat.get_tool_display_names",
        AsyncMock(return_value={}),
    )
    chat_model = SimpleNamespace(
        model_id="db-model",
        tokenizer_model_id=None,
        provider=None,
        context_length=128_000,
        max_output_tokens=None,
        model=SimpleNamespace(),
        input_capabilities=SimpleNamespace(modalities=frozenset()),
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.chat_helpers.resolve_agent_chat_model",
        AsyncMock(return_value=chat_model),
    )
    monkeypatch.setattr(
        "app.services.message_branching.get_visible_conversation_messages",
        AsyncMock(return_value=[]),
    )
    plan = SimpleNamespace(will_summarize=False, compression={"kind": "none"})
    monkeypatch.setattr(
        "app.services.chat_context.build_context_plan",
        AsyncMock(return_value=plan),
    )
    seeded = AsyncMock()
    monkeypatch.setattr(
        agent_run_worker,
        "AgentRunStream",
        lambda _run_id: SimpleNamespace(seed_sequence=seeded),
    )

    loop_context, loaded, _loop = await agent_run_worker._rebuild_context(
        {
            "run_id": str(uuid4()),
            "round_id": str(uuid4()),
            "user_message_id": str(user_msg.id),
            "mode": "non_stream",
            "message": "question",
            "locale": "en",
        },
        agent=agent,
        conversation=conversation,
        event_queue=asyncio.Queue(),
    )

    assert loaded is user_msg
    assert loop_context.current_images == [
        {
            "asset_id": str(links[0].asset_id),
            "checksum": "sum-1",
            "asset_ref": "scoped-ref",
            "mime_type": "image/png",
            "filename": "pic.png",
        }
    ]

    turn = await loop_context.build_turn(messages=[])
    assert turn.plan is plan
    assert turn.will_summarize is False
    assert turn.compression == {"kind": "none"}
