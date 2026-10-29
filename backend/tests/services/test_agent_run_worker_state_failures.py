"""State and failure behavior for the durable AgentRun worker.

Covers resume/failure paths that the happy-path suites leave untested:

* an approved-tool resume whose persisted tool result disappears,
* a stop race that deletes the run row while the worker is transitioning,
* a deferred park resume whose worker payload cannot be dispatched,
* durable stop-input checks and steer history replay during a live round,
* a resumed round never rewinding ``message_started_at``.

Streaming is replaced by an in-memory fake; persisted run state uses a real
SQLite schema so the assertions describe database state a client can observe.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from tortoise import Tortoise

from app.models.agent import Agent, Conversation
from app.models.agent_run import (
    AgentRun,
    AgentRunInputKind,
    AgentRunMode,
    AgentRunStatus,
)
from app.models.user import Team, TeamMember, User
from app.schemas.tool_approval import (
    ExecutionEntrypoint,
    ExecutionRunKind,
    ToolExecutionStatus,
)
from app.services import agent_run_store
from app.services.agent_loop import AgentLoopContext
from app.services.agent_run_worker import (
    _execute_approved_pending_tool,
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


def _stream():
    return SimpleNamespace(seed_sequence=AsyncMock(), publish=AsyncMock())


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


def _approval_payload(run):
    payload = _round_payload(run)
    payload["resume_tool_approval"] = {
        "execution_id": str(uuid4()),
        "tool_call_id": "call-1",
        "tool_name": "worker_tool",
    }
    return payload


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


# ---------------------------------------------------------------------------
# approved-tool resume: persisted result loss
# ---------------------------------------------------------------------------


def _patch_approved_resume(monkeypatch, run, *, recorded):
    execution = SimpleNamespace(
        run_id=run.id,
        run_kind=ExecutionRunKind.AGENT,
        tool_call_id="call-1",
        status=ToolExecutionStatus.READY,
        parameters_preview={"value": 1},
        entrypoint=ExecutionEntrypoint.AGENT_RUN,
        entrypoint_id="entrypoint-1",
    )
    monkeypatch.setattr(
        "app.services.tool_approvals.get_execution", AsyncMock(return_value=execution)
    )
    monkeypatch.setattr(
        "app.services.agent_run_store.record_resumed_tool_result", recorded
    )
    monkeypatch.setattr(
        "app.models.user.User.get_or_none",
        AsyncMock(return_value=SimpleNamespace(id=run.user_id)),
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.chat_tools.execute_tool_call",
        AsyncMock(return_value={"ok": True}),
    )
    monkeypatch.setattr(
        "app.utils.tool_output.get_tool_execution_payloads",
        lambda _result, _name: ('{"ok": true}', '{"ok": true}'),
    )


@pytest.mark.asyncio
async def test_approved_resume_with_lost_tool_result_is_abandoned(monkeypatch):
    """Losing the persisted tool result must abandon the resume, not replay it."""
    run = SimpleNamespace(id=uuid4(), active_round_id=uuid4(), user_id=uuid4())
    recorded = AsyncMock(return_value=None)
    _patch_approved_resume(monkeypatch, run, recorded=recorded)

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
        conversation=SimpleNamespace(id=uuid4(), user_id=run.user_id),
    )

    assert updated is None


# ---------------------------------------------------------------------------
# stop / missing-row races around the approved resume boundary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stop_that_cannot_transition_a_missing_run_raises_lookup(monkeypatch):
    """A stop whose row vanished is reported as a lost run after cancelling work."""
    from app.services import agent_run_worker as worker

    run = _run(status=AgentRunStatus.STOPPING)
    monkeypatch.setattr(worker.agent_run_store, "get_run", AsyncMock(return_value=run))
    monkeypatch.setattr("app.services.tool_approvals.cancel_execution", AsyncMock())
    monkeypatch.setattr(
        worker, "_transition_active_run", AsyncMock(return_value=(None, False))
    )

    with pytest.raises(LookupError, match="run not found"):
        await run_agent_round(_approval_payload(run))


@pytest.mark.asyncio
async def test_approved_resume_that_loses_its_run_raises_lookup(monkeypatch):
    """A run deleted while its approved tool is being recorded is a lost run."""
    from app.services import agent_run_worker as worker

    run = _run()
    _prepare_round(monkeypatch, run=run)
    monkeypatch.setattr(
        worker.agent_run_store,
        "get_run",
        AsyncMock(side_effect=[run, None]),
    )
    monkeypatch.setattr(
        worker, "_execute_approved_pending_tool", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        worker, "_transition_active_run", AsyncMock(return_value=(None, False))
    )

    with pytest.raises(LookupError, match="run not found"):
        await run_agent_round(_approval_payload(run))


# ---------------------------------------------------------------------------
# approved-tool resume: successful continuation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approved_resume_continues_with_persisted_metrics(monkeypatch):
    """A recorded tool result resumes the round and replays only real metrics."""
    from app.services import agent_run_worker as worker

    metric = {
        "name": "worker_tool",
        "status": "completed",
        "error_category": None,
    }
    expected_tool_result = {"tool_call_id": "call-1", "result": "ok"}
    resumed = {
        "resume_tool_result": dict(expected_tool_result),
        "resume_dependency_metrics": [metric, "not-a-metric"],
    }
    run = _run()
    run, stream, canonical, _context, _user, loop = _prepare_round(monkeypatch, run=run)
    monkeypatch.setattr(
        worker, "_execute_approved_pending_tool", AsyncMock(return_value=resumed)
    )

    output = await run_agent_round(_approval_payload(run))

    assert output == {
        "status": AgentRunStatus.COMPLETED.value,
        "message_id": str(canonical.id),
    }
    assert loop.result.dependency_metrics == [metric]
    tool_results = [
        call
        for call in stream.publish.await_args_list
        if call.args and call.args[0] == "tool_result"
    ]
    assert tool_results
    assert tool_results[0].args[1] == expected_tool_result
    assert tool_results[0].kwargs["message_id"] == canonical.id


# ---------------------------------------------------------------------------
# durable input checks inside a live round
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_durable_stop_input_ends_a_running_turn(monkeypatch):
    """A queued STOP row must be visible to the loop even before status flips."""
    from app.services import agent_run_worker as worker

    async def _observe(context):
        assert await context.stop_requested() is True

    run, _stream, _canonical, _context, _user, _loop = _prepare_round(
        monkeypatch, loop_callback=_observe
    )
    monkeypatch.setattr(
        worker.agent_run_store,
        "has_pending_inputs",
        AsyncMock(side_effect=[False, True]),
    )

    output = await run_agent_round(_round_payload(run))

    assert output["status"] == AgentRunStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_steer_input_extends_an_existing_working_history(monkeypatch):
    """Steering keeps the protocol entries already collected in the turn."""
    from app.services import agent_run_worker as worker

    item = SimpleNamespace(
        kind=AgentRunInputKind.STEER, content="please focus", sequence=4
    )
    prior = {"role": "user", "content": "earlier"}

    async def _steer(context):
        context.working_history_override = [prior]
        consumed = await context.consume_inputs()
        assert consumed == [item]
        await context.input_consumed(item)

    run, _stream, _canonical, context, _user, _loop = _prepare_round(
        monkeypatch, loop_callback=_steer
    )
    monkeypatch.setattr(
        worker.agent_run_store,
        "consume_next_input",
        AsyncMock(side_effect=[item, None]),
    )
    monkeypatch.setattr(
        worker.Message, "create", AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    )
    monkeypatch.setattr(
        "app.models.user.User.get_or_none",
        AsyncMock(return_value=SimpleNamespace(id=run.user_id)),
    )
    monkeypatch.setattr(
        "app.services.audit_log.AuditLogService.snapshot",
        lambda *_args, **_kwargs: {"id": "x"},
    )
    monkeypatch.setattr(
        "app.services.audit_log.AuditLogService.build_changes",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr("app.services.audit_log.AuditLogService.log", AsyncMock())

    output = await run_agent_round(_round_payload(run))

    assert output["status"] == AgentRunStatus.COMPLETED.value
    assert context.working_history_override[0] == prior
    assert len(context.working_history_override) == 2
    appended = context.working_history_override[1]
    assert appended["content"] == "please focus"
    assert appended["round_index"] == 10_000 + item.sequence
    assert appended["is_round_canonical"] is True


@pytest.mark.asyncio
async def test_terminal_run_stops_consuming_queued_inputs(monkeypatch):
    """Once a round is terminal it must not drain inputs meant for a new run."""
    from app.services import agent_run_worker as worker

    item = SimpleNamespace(kind=AgentRunInputKind.STEER, content="too late", sequence=5)

    async def _observe(context):
        run.status = AgentRunStatus.COMPLETED
        assert await context.consume_inputs() == []

    run, _stream, _canonical, _context, _user, _loop = _prepare_round(
        monkeypatch, loop_callback=_observe
    )
    consume = AsyncMock(return_value=item)
    monkeypatch.setattr(worker.agent_run_store, "consume_next_input", consume)

    output = await run_agent_round(_round_payload(run))

    assert output["status"] == AgentRunStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_resumed_round_keeps_the_original_message_started_at(monkeypatch):
    """Resuming must not rewind the timestamp used for observed latency."""
    started = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    run = _run(message_started_at=started)
    run, _stream, _canonical, _context, _user, _loop = _prepare_round(
        monkeypatch, run=run
    )

    output = await run_agent_round(_round_payload(run))

    assert output["status"] == AgentRunStatus.COMPLETED.value
    assert run.message_started_at == started


# ---------------------------------------------------------------------------
# deferred park resume dispatch failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deferred_resume_without_payload_fails_the_queued_run(monkeypatch):
    """A queued resume we cannot dispatch must end FAILED, not stay QUEUED."""
    from app.services import agent_run_worker as worker

    async with _database(monkeypatch):
        user = await _user()
        _team, agent, conversation = await _team_and_agent(user)
        deferred = await AgentRun.create(
            id=uuid4(),
            agent_id=agent.id,
            conversation_id=conversation.id,
            user_id=user.id,
            mode=AgentRunMode.SEND,
            status=AgentRunStatus.QUEUED,
            worker_payload=None,
        )

        run = _run()

        async def _park(current, **interaction):
            current.status = AgentRunStatus.WAITING
            current.pending_tool_call_id = "call-1"
            current.pending_tool_name = "ask_user"
            current.pending_tool_input = {"questions": []}
            current.worker_payload = interaction["worker_payload"]

        async def _pause(context):
            await context.pause_for_user(
                tool_call_id="call-1",
                tool_name="ask_user",
                arguments={"questions": []},
                round_id=context.round_id,
                round_index=3,
                iteration_index=2,
            )
            loop.event_queue.put_nowait(("tool_call", {"id": "call-1"}))

        run, _stream, _canonical, _context, _user_msg, loop = _prepare_round(
            monkeypatch,
            run=run,
            result=_round_result(waiting_for_user=True),
            transition=agent_run_store.transition_run_if_status,
            get_run=AsyncMock(side_effect=[run, run]),
            loop_callback=_pause,
        )
        monkeypatch.setattr(worker.agent_run_store, "park_run_waiting", _park)
        monkeypatch.setattr(
            worker.agent_run_store,
            "queue_agent_run_resume_if_approval_terminal",
            AsyncMock(return_value=deferred),
        )

        output = await run_agent_round(_round_payload(run))

        assert output == {
            "status": AgentRunStatus.QUEUED.value,
            "tool_call_id": "call-1",
        }
        refreshed = await AgentRun.get(id=deferred.id)
        assert refreshed.status == AgentRunStatus.FAILED
        assert refreshed.error_code == "enqueue_failed"
        assert "run resume payload is missing" in refreshed.error_message


# ---------------------------------------------------------------------------
# multi-tool pause: unstarted calls live only as ciphertext in the payload
# ---------------------------------------------------------------------------


def _capture_waiting_park(monkeypatch, worker, parked: dict) -> None:
    """Persist the pause exactly like ``park_run_waiting`` and record it."""

    async def _park(current, **interaction):
        current.status = AgentRunStatus.WAITING
        current.pending_tool_call_id = interaction["tool_call_id"]
        current.pending_tool_name = interaction["tool_name"]
        current.pending_tool_input = interaction["tool_input"]
        current.worker_payload = interaction["worker_payload"]
        parked.update(interaction)

    monkeypatch.setattr(worker.agent_run_store, "park_run_waiting", _park)


def _remaining_calls():
    from app.llm.types import ToolCall

    return [
        ToolCall(
            id="call-2",
            function={"name": "db_query", "arguments": '{"secret":"s3cr3t-arg"}'},
        ),
        ToolCall(
            id="call-3",
            function={
                "name": "http_get",
                "arguments": '{"url":"https://example.test/a"}',
            },
        ),
    ]


@pytest.mark.asyncio
async def test_pause_encrypts_remaining_tool_calls_into_worker_payload(monkeypatch):
    """Only ciphertext of the unstarted calls survives a durable pause."""
    import json
    from types import SimpleNamespace

    from app.core.tool_secrets import decrypt_tool_secret
    from app.llm.types import ToolCall
    from app.services import agent_run_worker as worker

    remaining = _remaining_calls()
    parked: dict = {}

    async def _pause(context):
        await context.pause_for_user(
            tool_call_id="call-1",
            tool_name="ask_user",
            arguments={"questions": []},
            round_id=context.round_id,
            round_index=3,
            iteration_index=2,
            remaining_tool_calls=remaining,
            resume_tool_visible_names=["db_query", "ask_user"],
        )

    run, _stream, _canonical, context, _user, _loop = _prepare_round(
        monkeypatch,
        result=_round_result(waiting_for_user=True),
        loop_callback=_pause,
    )
    context.tool_discovery = SimpleNamespace(
        loaded_names=["db_query"],
    )
    _capture_waiting_park(monkeypatch, worker, parked)

    output = await run_agent_round(_round_payload(run))

    assert output == {
        "status": AgentRunStatus.WAITING.value,
        "tool_call_id": "call-1",
    }
    payload = parked["worker_payload"]
    cipher = payload["pending_tool_calls_cipher"]
    assert cipher.startswith("enc:tool:v1:")
    # The durable payload must not leak call ids or arguments in clear text.
    durable = json.dumps(payload)
    assert "s3cr3t-arg" not in durable
    assert "call-2" not in durable
    assert "call-3" not in durable
    raw_calls = json.loads(decrypt_tool_secret(cipher))
    assert [ToolCall.model_validate(item) for item in raw_calls] == remaining
    assert payload["pending_tool_visible_names"] == ["db_query", "ask_user"]


@pytest.mark.asyncio
@pytest.mark.parametrize("remaining", [[], None], ids=["empty-list", "legacy-omitted"])
async def test_pause_without_remaining_tool_calls_keeps_legacy_payload(
    monkeypatch, remaining
):
    """A single-call pause stores no cipher and forgets any earlier suffix."""
    from app.core.tool_secrets import encrypt_tool_secret
    from app.services import agent_run_worker as worker

    parked: dict = {}

    async def _pause(context):
        kwargs = {
            "tool_call_id": "call-1",
            "tool_name": "ask_user",
            "arguments": {},
            "round_id": context.round_id,
            "round_index": 0,
            "iteration_index": 0,
        }
        if remaining is not None:
            kwargs["remaining_tool_calls"] = remaining
        await context.pause_for_user(**kwargs)

    run, _stream, _canonical, _context, _user, _loop = _prepare_round(
        monkeypatch,
        result=_round_result(waiting_for_user=True),
        loop_callback=_pause,
    )
    _capture_waiting_park(monkeypatch, worker, parked)

    payload = _round_payload(run)
    payload["pending_tool_calls_cipher"] = encrypt_tool_secret("[]")

    output = await run_agent_round(payload)

    assert output == {
        "status": AgentRunStatus.WAITING.value,
        "tool_call_id": "call-1",
    }
    resume_payload = parked["worker_payload"]
    assert "pending_tool_calls_cipher" not in resume_payload
    assert "pending_tool_visible_names" not in resume_payload
    assert resume_payload["first_round_index"] == 1
    assert resume_payload["iteration_offset"] == 0
    assert resume_payload["history_override"] == []
