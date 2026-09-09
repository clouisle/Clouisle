"""Branch coverage for agent_run_worker and agent_run_store lifecycle paths.

These tests cover the core durable-run chain branches that integration tests
do not reach: run_agent_round pre-loop validation (missing run / missing
agent / lock busy), _rebuild_context RAG and non-stream tool filtering,
finalizer branches, and the store's transition/park/validation paths.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.agent import MessageRoundStatus, RAGMode
from app.models.agent_run import AgentRunStatus
from app.services import agent_run_store
from app.services.agent_run_worker import (
    _finalize_stopped,
    _tools_definitions,
    _transition_active_run,
    run_agent_round,
)


def _run(status=AgentRunStatus.QUEUED, **values):
    run = SimpleNamespace(
        id=uuid4(),
        agent_id=uuid4(),
        conversation_id=uuid4(),
        user_id=uuid4(),
        mode=SimpleNamespace(value="send"),
        status=status,
        source_message_id=None,
        canonical_message_id=None,
        active_round_id=None,
        started_at=None,
        finished_at=None,
        error_code=None,
        error_message=None,
        celery_task_id=None,
    )
    run.updated_at = None
    run.save = AsyncMock(return_value=None)
    for key, value in values.items():
        setattr(run, key, value)
    return run


class FakeRedis:
    def __init__(self):
        self.data: dict[str, object] = {}

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.data:
            return False
        self.data[key] = value
        return True

    async def get(self, key):
        return self.data.get(key)

    async def expire(self, key, seconds):
        return key in self.data

    async def delete(self, key):
        self.data.pop(key, None)
        return True

    async def rpush(self, key, value):
        if key not in self.data or not isinstance(self.data[key], list):
            self.data[key] = []
        self.data[key].append(value)  # type: ignore[union-attr]
        return len(self.data[key])  # type: ignore[arg-type]

    async def lrange(self, key, start, end):
        values = self.data.get(key) or []
        if end is None or end < 0:
            return values[start:]
        return values[start : end + 1]  # type: ignore[misc]

    async def publish(self, channel, message):
        return 1

    async def pubsub(self):
        return FakePubSub(self)


class FakePubSub:
    def __init__(self, redis: FakeRedis):
        self.redis = redis

    async def subscribe(self, channel):
        pass

    async def unsubscribe(self, channel):
        pass

    async def close(self):
        pass

    async def listen(self):
        yield {"type": "subscribe"}
        while True:
            await asyncio.sleep(0.05)


def _get_redis_fixture(redis: FakeRedis):
    async def _get_redis():
        return redis

    return _get_redis


@pytest.fixture
def fake_redis(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(agent_run_store, "get_redis", _get_redis_fixture(redis))
    return redis


@pytest.fixture
def patched_store(monkeypatch, fake_redis):
    """Mocks every ORM touchpoint of run_agent_round pre-loop validation."""
    from app.services import agent_run_worker as worker

    worker.agent_run_store = agent_run_store

    run = _run(status=AgentRunStatus.QUEUED)
    agent = SimpleNamespace(
        id=uuid4(),
        team_id=uuid4(),
        rag_mode=SimpleNamespace(value="off"),
        max_iterations=5,
    )
    conversation = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        title="title",
        message_count=0,
        token_usage=0,
    )
    user_msg = SimpleNamespace(id=uuid4(), rag_context=[])

    async def _get_run(run_id, **_kwargs):
        if run_id == run.id:
            return run
        return None

    async def _get_or_none(**kwargs):
        if kwargs.get("id") == agent.id:
            return agent
        if kwargs.get("id") == conversation.id:
            return conversation
        if kwargs.get("id") == user_msg.id:
            return user_msg
        return None

    async def _acquire_lock(run_id, conversation_id, **_kwargs):
        return True

    async def _transition(run, status, **_kwargs):
        run.status = status
        return run

    async def _release(run_id, conversation_id):
        pass

    async def _drop(*_args, **_kwargs):
        return 0

    async def _heartbeat(run_id, conversation_id, stop):
        await stop.wait()

    async def _create_placeholder(conversation, user_msg, run):
        return SimpleNamespace(id=uuid4())

    async def _rebuild_context(*_args, **_kwargs):
        raise RuntimeError("never reached")

    async def _claim_queued_run(run_id):
        assert run_id == run.id
        run.status = AgentRunStatus.RUNNING
        return run

    monkeypatch.setattr(worker.agent_run_store, "claim_queued_run", _claim_queued_run)

    monkeypatch.setattr(worker.agent_run_store, "get_run", _get_run)
    monkeypatch.setattr(worker.Agent, "get_or_none", _get_or_none)
    monkeypatch.setattr(worker.Conversation, "get_or_none", _get_or_none)
    monkeypatch.setattr(worker.agent_run_store, "acquire_run_lock", _acquire_lock)
    monkeypatch.setattr(worker.agent_run_store, "transition_run", _transition)
    monkeypatch.setattr(worker.agent_run_store, "release_run_lock", _release)
    monkeypatch.setattr(worker.agent_run_store, "drop_pending_inputs", _drop)
    monkeypatch.setattr(worker.agent_run_store, "heartbeat_run_lock", _heartbeat)
    monkeypatch.setattr(
        worker.agent_run_store, "has_pending_inputs", AsyncMock(return_value=False)
    )

    async def _transition_if_status(run, expected, status, **_kwargs):
        if run.status != expected:
            return None
        run.status = status
        return run

    monkeypatch.setattr(
        worker.agent_run_store, "transition_run_if_status", _transition_if_status
    )
    monkeypatch.setattr(
        worker.agent_run_store, "transition_run_if_status", _transition_if_status
    )
    monkeypatch.setattr(worker, "_create_placeholder", _create_placeholder)
    monkeypatch.setattr(worker, "_rebuild_context", _rebuild_context)

    return SimpleNamespace(
        run=run,
        agent=agent,
        conversation=conversation,
        user_msg=user_msg,
        worker=worker,
    )


@pytest.mark.asyncio
async def test_run_agent_round_missing_run_raises_lookup(monkeypatch, fake_redis):
    from app.services import agent_run_worker as worker

    async def _get_run(run_id, **_kwargs):
        return None

    monkeypatch.setattr(worker.agent_run_store, "get_run", _get_run)
    with pytest.raises(LookupError, match="run not found"):
        await run_agent_round({"run_id": str(uuid4())})


@pytest.mark.asyncio
async def test_run_agent_round_returns_status_when_queue_claim_is_lost(
    monkeypatch, patched_store
):
    from app.services import agent_run_worker as worker

    async def _claim(run_id):
        assert run_id == patched_store.run.id
        patched_store.run.status = AgentRunStatus.RUNNING
        return None

    monkeypatch.setattr(worker.agent_run_store, "claim_queued_run", _claim)

    result = await run_agent_round({"run_id": str(patched_store.run.id)})

    assert result == {"status": AgentRunStatus.RUNNING.value}


@pytest.mark.asyncio
async def test_run_agent_round_does_not_replay_interrupted_run(monkeypatch):
    run = _run(status=AgentRunStatus.INTERRUPTED)

    async def _get_run(run_id, **_kwargs):
        assert run_id == run.id
        return run

    monkeypatch.setattr(agent_run_store, "get_run", _get_run)

    result = await run_agent_round(
        {
            "run_id": str(run.id),
            "agent_id": str(run.agent_id),
            "conversation_id": str(run.conversation_id),
        }
    )

    assert result == {"status": AgentRunStatus.INTERRUPTED.value}


def test_agent_task_crash_does_not_overwrite_stopped_run(monkeypatch):
    from app.services import agent_run_worker
    from app.tasks import agent as agent_task

    async def _raise_round(_payload):
        raise RuntimeError("task crashed")

    run = _run(status=AgentRunStatus.STOPPED)
    monkeypatch.setattr(agent_run_worker, "run_agent_round", _raise_round)
    monkeypatch.setattr(agent_run_store, "get_run", AsyncMock(return_value=run))
    transition = AsyncMock()
    monkeypatch.setattr(agent_run_store, "transition_run_if_status", transition)

    result = agent_task.run_agent_task.run({"run_id": str(run.id)})

    assert result["status"] == AgentRunStatus.STOPPED.value
    transition.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_agent_round_missing_agent_or_conversation_marks_failed(
    monkeypatch, patched_store
):
    from app.services import agent_run_worker as worker

    async def _transition(run, expected_status, status, **_kwargs):
        assert expected_status == AgentRunStatus.RUNNING
        run.status = status
        return run

    transition = AsyncMock(side_effect=_transition)

    async def _get_or_none(**kwargs):
        return None

    monkeypatch.setattr(worker.Agent, "get_or_none", _get_or_none)
    monkeypatch.setattr(worker.Conversation, "get_or_none", _get_or_none)
    monkeypatch.setattr(worker.agent_run_store, "transition_run_if_status", transition)

    payload = {
        "run_id": str(patched_store.run.id),
        "agent_id": str(uuid4()),
        "conversation_id": str(uuid4()),
    }
    result = await run_agent_round(payload)
    assert result == {"status": AgentRunStatus.FAILED.value}
    transition.assert_awaited()
    args = transition.await_args.args
    assert args[1] == AgentRunStatus.RUNNING
    assert args[2] == AgentRunStatus.FAILED
    assert transition.await_args.kwargs["error_code"] == "context_lost"


@pytest.mark.asyncio
async def test_run_agent_round_lock_busy_publishes_error_and_fails(
    monkeypatch, patched_store
):
    from app.services import agent_run_worker as worker

    transition = AsyncMock()
    publishes: list[tuple[str, dict]] = []

    async def _acquire_lock(run_id, conversation_id, **_kwargs):
        return False

    async def _publish(event_type, payload, **_kwargs):
        publishes.append((event_type, payload))

    monkeypatch.setattr(worker.agent_run_store, "acquire_run_lock", _acquire_lock)
    monkeypatch.setattr(worker.agent_run_store, "transition_run", transition)
    monkeypatch.setattr(
        worker,
        "AgentRunStream",
        lambda _id: SimpleNamespace(
            seed_sequence=AsyncMock(),
            publish=_publish,
        ),
    )

    payload = {
        "run_id": str(patched_store.run.id),
        "agent_id": str(patched_store.agent.id),
        "conversation_id": str(patched_store.conversation.id),
    }
    result = await run_agent_round(payload)
    assert result == {"status": AgentRunStatus.FAILED.value}
    transition.assert_not_awaited()
    assert worker.agent_run_store.transition_run_if_status is not None
    error_events = [(t, p) for t, p in publishes if p.get("code") == "lock_busy"]
    assert error_events and error_events[0][0] == "error"
    assert ("run_end", {"status": "failed"}) in publishes


@pytest.mark.asyncio
async def test_tools_definitions_none_and_populated():
    assert _tools_definitions(None) is None
    tools = _tools_definitions(
        [{"function": {"name": "a", "description": "d", "parameters": {}}}]
    )
    assert tools[0].function.name == "a"


@pytest.mark.asyncio
async def test_finalize_stopped_sets_manual_stop_fields(monkeypatch):

    canonical = SimpleNamespace(
        content="",
        reasoning_content=None,
        is_manually_stopped=False,
        round_status=None,
        save=AsyncMock(),
    )
    result = SimpleNamespace(
        full_content="partial",
        full_reasoning="reasoning",
        maximum_tokens_reached=False,
        max_iterations_reached=False,
    )
    stream = SimpleNamespace(publish=AsyncMock())

    await _finalize_stopped(canonical, result, stream)

    assert canonical.content == "partial"
    assert canonical.reasoning_content == "reasoning"
    assert canonical.is_manually_stopped is True
    assert canonical.round_status == MessageRoundStatus.MANUALLY_STOPPED
    canonical.save.assert_awaited_once()
    stream.publish.assert_awaited_once_with("message_end", {"usage": {}})


# ---------------------------------------------------------------------------
# agent_run_store lifecycle branches
# ---------------------------------------------------------------------------


class _Transaction:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *_args):
        return False

    def __call__(self):
        return self


class _LockedRunQuery:
    def __init__(self, run):
        self.run = run

    def using_db(self, _conn):
        return self

    def select_for_update(self):
        return self

    async def first(self):
        return self.run


def _waiting_run():
    run = _run(
        status=AgentRunStatus.WAITING,
        pending_tool_call_id="call-1",
        pending_tool_name="ask_user",
        pending_tool_input={
            "questions": [
                {"id": "target", "question": "Where?", "options": ["cloud", "local"]},
                {"id": "note", "question": "Note?", "required": False},
            ]
        },
        pending_tool_round_id=uuid4(),
        pending_tool_round_index=4,
        pending_tool_iteration_index=2,
        worker_payload={"history_override": [], "exclude_message_ids": []},
    )
    run.active_round_id = run.pending_tool_round_id
    run.canonical_message_id = uuid4()
    return run


@pytest.mark.asyncio
async def test_park_run_waiting_persists_and_rejects_when_not_running(
    monkeypatch, fake_redis
):
    run = _run(status=AgentRunStatus.RUNNING)
    db_running = [True]

    async def _filter_update(**_kwargs):
        return 1 if db_running[0] else 0

    monkeypatch.setattr(
        agent_run_store.AgentRun,
        "filter",
        lambda **_kwargs: SimpleNamespace(update=_filter_update),
    )

    parked = await agent_run_store.park_run_waiting(
        run,
        tool_call_id="call-1",
        tool_name="ask_user",
        tool_input={"questions": []},
        round_id=uuid4(),
        round_index=4,
        iteration_index=2,
        worker_payload={"resume": True},
    )
    assert parked is run
    assert run.status == AgentRunStatus.WAITING
    assert run.pending_tool_call_id == "call-1"

    # The DB row is no longer running -> park raises.
    db_running[0] = False
    with pytest.raises(RuntimeError, match="no longer running"):
        await agent_run_store.park_run_waiting(
            run,
            tool_call_id="call-2",
            tool_name="ask_user",
            tool_input={"questions": []},
            round_id=uuid4(),
            round_index=4,
            iteration_index=2,
        )


@pytest.mark.asyncio
async def test_park_run_waiting_omits_worker_payload_when_none(monkeypatch, fake_redis):
    run = _run(status=AgentRunStatus.RUNNING)
    calls = []

    async def _filter_update(**kwargs):
        calls.append(kwargs)
        return 1

    monkeypatch.setattr(
        agent_run_store.AgentRun,
        "filter",
        lambda **_kwargs: SimpleNamespace(update=_filter_update),
    )

    await agent_run_store.park_run_waiting(
        run,
        tool_call_id="call-1",
        tool_name="ask_user",
        tool_input={},
        round_id=uuid4(),
        round_index=4,
        iteration_index=2,
    )
    assert "worker_payload" not in calls[-1]


@pytest.mark.asyncio
async def test_transition_run_sets_started_finished_and_errors(monkeypatch, fake_redis):
    run = _run(status=AgentRunStatus.QUEUED)

    running = await agent_run_store.transition_run(run, AgentRunStatus.RUNNING)
    assert running.started_at is not None
    assert running.finished_at is None

    failed = await agent_run_store.transition_run(
        run,
        AgentRunStatus.FAILED,
        error_code="boom",
        error_message="bad",
    )
    assert failed.finished_at is not None
    assert failed.error_code == "boom"
    assert failed.error_message == "bad"


@pytest.mark.asyncio
async def test_submit_user_answers_skips_canonical_exclusion_and_round_index(
    monkeypatch, fake_redis
):
    run = _waiting_run()
    message_create = AsyncMock()
    monkeypatch.setattr(agent_run_store, "in_transaction", _Transaction())
    monkeypatch.setattr(
        agent_run_store.AgentRun,
        "filter",
        lambda **_kwargs: _LockedRunQuery(run),
    )
    monkeypatch.setattr(agent_run_store.Message, "create", message_create)

    # canonical_message_id already in exclusions and round_index present
    run.worker_payload["exclude_message_ids"] = [str(run.canonical_message_id)]
    submitted = await agent_run_store.submit_user_answers(
        run.id, tool_call_id="call-1", answers={"target": "cloud"}
    )
    assert submitted is run
    assert run.worker_payload["exclude_message_ids"] == [str(run.canonical_message_id)]
    assert run.worker_payload["first_round_index"] == 5
    assert run.status == AgentRunStatus.QUEUED


@pytest.mark.asyncio
async def test_submit_user_answers_rejects_wrong_tool_name(monkeypatch, fake_redis):
    run = _waiting_run()
    run.pending_tool_name = "generate_image"
    message_create = AsyncMock()
    monkeypatch.setattr(agent_run_store, "in_transaction", _Transaction())
    monkeypatch.setattr(
        agent_run_store.AgentRun,
        "filter",
        lambda **_kwargs: _LockedRunQuery(run),
    )
    monkeypatch.setattr(agent_run_store.Message, "create", message_create)

    submitted = await agent_run_store.submit_user_answers(
        run.id, tool_call_id="call-1", answers={"target": "cloud"}
    )
    assert submitted is None
    message_create.assert_not_awaited()


@pytest.mark.asyncio
async def test_transition_run_if_status_returns_none_when_row_changed(
    monkeypatch, fake_redis
):
    run = _run(status=AgentRunStatus.RUNNING)
    query = SimpleNamespace(update=AsyncMock(return_value=0))
    monkeypatch.setattr(agent_run_store.AgentRun, "filter", lambda **_kwargs: query)

    assert (
        await agent_run_store.transition_run_if_status(
            run, AgentRunStatus.RUNNING, AgentRunStatus.STOPPING
        )
        is None
    )


@pytest.mark.asyncio
async def test_claim_queued_run_handles_missing_and_started_runs(
    monkeypatch, fake_redis
):
    missing = _LockedRunQuery(None)
    fresh = _run(status=AgentRunStatus.QUEUED)
    already_started = _run(status=AgentRunStatus.QUEUED, started_at="already-started")
    queries = iter([missing, _LockedRunQuery(fresh), _LockedRunQuery(already_started)])
    monkeypatch.setattr(agent_run_store, "in_transaction", _Transaction())
    monkeypatch.setattr(
        agent_run_store.AgentRun, "filter", lambda **_kwargs: next(queries)
    )

    assert await agent_run_store.claim_queued_run(uuid4()) is None

    claimed = await agent_run_store.claim_queued_run(uuid4())
    assert claimed is fresh
    assert fresh.status == AgentRunStatus.RUNNING
    assert "started_at" in fresh.save.await_args.kwargs["update_fields"]

    claimed_started = await agent_run_store.claim_queued_run(uuid4())
    assert claimed_started is already_started
    assert already_started.status == AgentRunStatus.RUNNING
    assert already_started.save.await_args.kwargs["update_fields"] == [
        "status",
        "updated_at",
    ]


@pytest.mark.asyncio
async def test_submit_user_answers_without_pending_round_index_omits_first_round(
    monkeypatch, fake_redis
):
    run = _waiting_run()
    run.pending_tool_round_index = None
    run.worker_payload = {}
    message_create = AsyncMock()
    monkeypatch.setattr(agent_run_store, "in_transaction", _Transaction())
    monkeypatch.setattr(
        agent_run_store.AgentRun,
        "filter",
        lambda **_kwargs: _LockedRunQuery(run),
    )
    monkeypatch.setattr(agent_run_store.Message, "create", message_create)

    submitted = await agent_run_store.submit_user_answers(
        run.id, tool_call_id="call-1", answers={"target": "cloud"}
    )

    assert submitted is run
    assert "first_round_index" not in run.worker_payload
    message_create.assert_awaited_once()


@pytest.mark.asyncio
async def test_worker_loss_ignores_lost_transition(monkeypatch, fake_redis):
    from datetime import UTC, datetime, timedelta

    stale_run = _run(status=AgentRunStatus.RUNNING)
    stale_run.started_at = datetime.now(UTC) - timedelta(minutes=10)

    async def all_runs():
        return [stale_run]

    monkeypatch.setattr(
        agent_run_store.AgentRun,
        "filter",
        lambda **_kwargs: SimpleNamespace(all=all_runs),
    )
    monkeypatch.setattr(
        agent_run_store, "transition_run_if_status", AsyncMock(return_value=None)
    )

    assert await agent_run_store.mark_expired_runs_interrupted() == 0


@pytest.mark.asyncio
async def test_transition_active_run_covers_retries_and_missing_rows(monkeypatch):
    current = _run(status=AgentRunStatus.RUNNING)
    transitioned = _run(status=AgentRunStatus.STOPPING)

    result = await _transition_active_run(
        _run(status=AgentRunStatus.COMPLETED),
        AgentRunStatus.STOPPED,
        allowed_statuses=(AgentRunStatus.RUNNING,),
    )
    assert result[1] is False

    monkeypatch.setattr(
        agent_run_store,
        "transition_run_if_status",
        AsyncMock(return_value=transitioned),
    )
    result = await _transition_active_run(
        current,
        AgentRunStatus.STOPPING,
        allowed_statuses=(AgentRunStatus.RUNNING,),
    )
    assert result == (transitioned, True)

    monkeypatch.setattr(
        agent_run_store,
        "transition_run_if_status",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(agent_run_store, "get_run", AsyncMock(return_value=None))
    result = await _transition_active_run(
        _run(status=AgentRunStatus.RUNNING),
        AgentRunStatus.STOPPING,
        allowed_statuses=(AgentRunStatus.RUNNING,),
    )
    assert result == (None, False)

    same_run = _run(status=AgentRunStatus.RUNNING)
    monkeypatch.setattr(agent_run_store, "get_run", AsyncMock(return_value=same_run))
    result = await _transition_active_run(
        same_run,
        AgentRunStatus.STOPPING,
        allowed_statuses=(AgentRunStatus.RUNNING,),
    )
    assert result == (same_run, False)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [AgentRunStatus.WAITING, AgentRunStatus.COMPLETING])
async def test_run_agent_round_returns_nonterminal_status_without_replay(
    monkeypatch, status
):
    run = _run(status=status)
    monkeypatch.setattr(agent_run_store, "get_run", AsyncMock(return_value=run))

    result = await run_agent_round({"run_id": str(run.id)})

    assert result == {"status": status.value}


@pytest.mark.asyncio
async def test_run_agent_round_queue_claim_lost_after_run_disappears(monkeypatch):
    from app.services import agent_run_worker as worker

    run = _run(status=AgentRunStatus.QUEUED)
    monkeypatch.setattr(
        worker.agent_run_store, "get_run", AsyncMock(side_effect=[run, None])
    )
    monkeypatch.setattr(
        worker.agent_run_store, "claim_queued_run", AsyncMock(return_value=None)
    )

    with pytest.raises(LookupError, match="run not found"):
        await run_agent_round({"run_id": str(run.id)})


@pytest.mark.asyncio
async def test_run_agent_round_stop_request_stops_and_publishes(monkeypatch):
    from app.services import agent_run_worker as worker

    for status, pending in (
        (AgentRunStatus.STOPPING, False),
        (AgentRunStatus.RUNNING, True),
    ):
        run = _run(status=status)
        publishes = []

        async def _publish(event_type, payload, **_kwargs):
            publishes.append((event_type, payload))

        async def _transition(run, _expected, new_status, **_kwargs):
            run.status = new_status
            return run

        monkeypatch.setattr(
            worker.agent_run_store, "get_run", AsyncMock(return_value=run)
        )
        monkeypatch.setattr(
            worker.agent_run_store,
            "has_pending_inputs",
            AsyncMock(return_value=pending),
        )
        monkeypatch.setattr(
            worker.agent_run_store, "transition_run_if_status", _transition
        )
        monkeypatch.setattr(
            worker,
            "AgentRunStream",
            lambda _id: SimpleNamespace(seed_sequence=AsyncMock(), publish=_publish),
        )

        result = await run_agent_round({"run_id": str(run.id)})

        assert result == {"status": AgentRunStatus.STOPPED.value}
        assert ("run_end", {"status": "stopped"}) in publishes


@pytest.mark.asyncio
async def test_run_agent_round_stop_request_raises_when_row_disappears(monkeypatch):
    from app.services import agent_run_worker as worker

    run = _run(status=AgentRunStatus.STOPPING)
    monkeypatch.setattr(
        worker.agent_run_store, "get_run", AsyncMock(side_effect=[run, None])
    )
    monkeypatch.setattr(
        worker.agent_run_store, "transition_run_if_status", AsyncMock(return_value=None)
    )

    with pytest.raises(LookupError, match="run not found"):
        await run_agent_round({"run_id": str(run.id)})


@pytest.mark.asyncio
async def test_run_agent_round_stop_request_returns_current_when_transition_lost(
    monkeypatch,
):
    from app.services import agent_run_worker as worker

    run = _run(status=AgentRunStatus.STOPPING)
    monkeypatch.setattr(worker.agent_run_store, "get_run", AsyncMock(return_value=run))
    monkeypatch.setattr(
        worker.agent_run_store, "transition_run_if_status", AsyncMock(return_value=None)
    )

    result = await run_agent_round({"run_id": str(run.id)})

    assert result == {"status": AgentRunStatus.STOPPING.value}


@pytest.mark.asyncio
async def test_run_agent_round_missing_context_row_that_loses_transition(monkeypatch):
    from app.services import agent_run_worker as worker

    run = _run(status=AgentRunStatus.RUNNING)
    monkeypatch.setattr(
        worker.agent_run_store, "get_run", AsyncMock(side_effect=[run, None])
    )
    monkeypatch.setattr(worker.Agent, "get_or_none", AsyncMock(return_value=None))
    monkeypatch.setattr(
        worker.Conversation, "get_or_none", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        worker.agent_run_store, "has_pending_inputs", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(
        worker.agent_run_store, "transition_run_if_status", AsyncMock(return_value=None)
    )

    with pytest.raises(LookupError, match="run not found"):
        await run_agent_round(
            {
                "run_id": str(run.id),
                "agent_id": str(run.agent_id),
                "conversation_id": str(run.conversation_id),
            }
        )


@pytest.mark.asyncio
async def test_run_agent_round_lock_busy_stop_races(monkeypatch):
    from app.services import agent_run_worker as worker

    for transition_result, expected_status in ((None, AgentRunStatus.RUNNING),):
        run = _run(status=AgentRunStatus.RUNNING)
        current = _run(status=AgentRunStatus.RUNNING)
        monkeypatch.setattr(
            worker.agent_run_store,
            "get_run",
            AsyncMock(side_effect=[run, current, current, current]),
        )
        monkeypatch.setattr(worker.Agent, "get_or_none", AsyncMock(return_value=None))
        monkeypatch.setattr(
            worker.Conversation, "get_or_none", AsyncMock(return_value=None)
        )
        monkeypatch.setattr(
            worker.agent_run_store, "acquire_run_lock", AsyncMock(return_value=False)
        )
        monkeypatch.setattr(
            worker.agent_run_store,
            "has_pending_inputs",
            AsyncMock(return_value=True),
        )
        monkeypatch.setattr(
            worker.agent_run_store,
            "transition_run_if_status",
            AsyncMock(return_value=transition_result),
        )

        # The stop-request path returns the still-running row when another
        # worker wins the conditional transition.
        result = await run_agent_round({"run_id": str(run.id)})
        assert result == {"status": expected_status.value}


@pytest.mark.asyncio
async def test_run_agent_round_lock_busy_lost_row_raises(monkeypatch):
    from app.services import agent_run_worker as worker

    run = _run(status=AgentRunStatus.RUNNING)
    current = _run(status=AgentRunStatus.RUNNING)
    monkeypatch.setattr(
        worker.agent_run_store, "get_run", AsyncMock(side_effect=[run, current, None])
    )
    monkeypatch.setattr(worker.Agent, "get_or_none", AsyncMock(return_value=None))
    monkeypatch.setattr(
        worker.Conversation, "get_or_none", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        worker.agent_run_store, "acquire_run_lock", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(
        worker.agent_run_store, "has_pending_inputs", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        worker.agent_run_store, "transition_run_if_status", AsyncMock(return_value=None)
    )

    with pytest.raises(LookupError, match="run not found"):
        await run_agent_round({"run_id": str(run.id)})


@pytest.mark.asyncio
async def test_run_agent_round_lock_busy_returns_unchanged_status(monkeypatch):
    from app.services import agent_run_worker as worker

    run = _run(status=AgentRunStatus.RUNNING)
    current = _run(status=AgentRunStatus.RUNNING)
    monkeypatch.setattr(
        worker.agent_run_store,
        "get_run",
        AsyncMock(side_effect=[run, current, current, current]),
    )
    agent = SimpleNamespace(id=run.agent_id)
    conversation = SimpleNamespace(id=run.conversation_id)

    async def _get_or_none(*, id):
        return agent if id == run.agent_id else conversation

    monkeypatch.setattr(worker.Agent, "get_or_none", _get_or_none)
    monkeypatch.setattr(worker.Conversation, "get_or_none", _get_or_none)
    monkeypatch.setattr(
        worker.agent_run_store, "acquire_run_lock", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(
        worker.agent_run_store, "has_pending_inputs", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(
        worker.agent_run_store, "transition_run_if_status", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        worker,
        "AgentRunStream",
        lambda _id: SimpleNamespace(seed_sequence=AsyncMock(), publish=AsyncMock()),
    )

    result = await run_agent_round(
        {
            "run_id": str(run.id),
            "agent_id": str(run.agent_id),
            "conversation_id": str(run.conversation_id),
        }
    )

    assert result == {"status": AgentRunStatus.RUNNING.value}


def _prepare_full_round(
    monkeypatch,
    *,
    result,
    transition,
    get_run=None,
    rebuild=None,
    rag_mode=None,
    rag_context=None,
):
    from app.services import agent_run_worker as worker

    run = _run(status=AgentRunStatus.RUNNING)
    run.active_round_id = uuid4()
    run.pending_tool_call_id = "call-1"
    run.pending_tool_name = "ask_user"
    run.pending_tool_input = {"questions": []}
    agent = SimpleNamespace(
        id=run.agent_id, rag_mode=rag_mode or SimpleNamespace(value="off")
    )
    conversation = SimpleNamespace(id=run.conversation_id)
    user_message = SimpleNamespace(
        id=uuid4(),
        content="question",
        rag_context=rag_context,
    )
    context = SimpleNamespace(
        model_used="model",
        created_message_count=2,
        working_history_override=None,
    )
    canonical = SimpleNamespace(
        id=uuid4(),
        branch_parent_id=None,
        save=AsyncMock(),
    )
    stream = SimpleNamespace(seed_sequence=AsyncMock(), publish=AsyncMock())

    class Loop:
        def __init__(self):
            self.result = result

        async def run(self):
            if False:
                yield None

    async def _heartbeat(_run_id, _conversation_id, stop):
        await stop.wait()

    async def _rebuild(*_args, **_kwargs):
        if rebuild is not None:
            raise rebuild
        return context, user_message, Loop()

    if get_run is None:
        get_run = AsyncMock(return_value=run)
    monkeypatch.setattr(worker.agent_run_store, "get_run", get_run)
    monkeypatch.setattr(worker.Agent, "get_or_none", AsyncMock(return_value=agent))
    monkeypatch.setattr(
        worker.Conversation, "get_or_none", AsyncMock(return_value=conversation)
    )
    monkeypatch.setattr(worker.Message, "get_or_none", AsyncMock(return_value=None))
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
    monkeypatch.setattr(worker, "_finalize_completed", AsyncMock())
    monkeypatch.setattr(worker, "_finalize_stopped", AsyncMock())
    monkeypatch.setattr(worker.agent_run_store, "transition_run_if_status", transition)
    return run, stream, canonical


def _round_result(**values):
    defaults = {
        "waiting_for_user": False,
        "deadline_exceeded": False,
        "manually_stopped": False,
        "max_iterations_reached": False,
        "full_content": "answer",
        "full_reasoning": None,
    }
    defaults.update(values)
    return SimpleNamespace(**defaults)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("rag_context", "expect_rag_events"),
    [
        (None, False),
        ([], True),
        ([{"document_id": "doc-1", "content": "source"}], True),
    ],
)
async def test_run_agent_round_publishes_rag_progress_when_retrieval_was_attempted(
    monkeypatch, rag_context, expect_rag_events
):
    async def _transition(run, _expected, status, **_kwargs):
        run.status = status
        return run

    run, stream, _ = _prepare_full_round(
        monkeypatch,
        result=_round_result(),
        transition=_transition,
        rag_mode=RAGMode.AUTO,
        rag_context=rag_context,
    )

    await run_agent_round(_round_payload(run))

    event_names = [call.args[0] for call in stream.publish.await_args_list]
    assert ("rag_start" in event_names) is expect_rag_events
    assert ("rag_context" in event_names) is expect_rag_events


@pytest.mark.asyncio
async def test_run_agent_round_waiting_publishes_pending_status(monkeypatch):
    async def _transition(run, _expected, status, **_kwargs):
        run.status = status
        return run

    result = _round_result(waiting_for_user=True)
    run, stream, _ = _prepare_full_round(
        monkeypatch, result=result, transition=_transition
    )

    output = await run_agent_round(_round_payload(run))

    assert output == {"status": AgentRunStatus.WAITING.value, "tool_call_id": "call-1"}
    assert any(
        event.args[0] == "run_status" for event in stream.publish.await_args_list
    )


@pytest.mark.asyncio
async def test_run_agent_round_deadline_stops_and_reports_reason(monkeypatch):
    async def _transition(run, _expected, status, **_kwargs):
        run.status = status
        return run

    result = _round_result(deadline_exceeded=True)
    run, stream, _ = _prepare_full_round(
        monkeypatch, result=result, transition=_transition
    )

    output = await run_agent_round(_round_payload(run))

    assert output == {
        "status": AgentRunStatus.STOPPED.value,
        "reason": "deadline_exceeded",
    }
    assert ("run_end", {"status": "stopped", "reason": "deadline_exceeded"}) in [
        (call.args[0], call.args[1])
        for call in stream.publish.await_args_list
        if len(call.args) >= 2
    ]


@pytest.mark.asyncio
async def test_run_agent_round_manual_stop_returns_canonical_id(monkeypatch):
    async def _transition(run, _expected, status, **_kwargs):
        run.status = status
        return run

    result = _round_result(manually_stopped=True)
    run, _stream, canonical = _prepare_full_round(
        monkeypatch, result=result, transition=_transition
    )

    output = await run_agent_round(_round_payload(run))

    assert output == {
        "status": AgentRunStatus.STOPPED.value,
        "message_id": str(canonical.id),
    }


@pytest.mark.asyncio
async def test_run_agent_round_completion_claim_publishes_end(monkeypatch):
    async def _transition(run, expected, status, **_kwargs):
        if run.status != expected:
            return None
        run.status = status
        return run

    result = _round_result()
    run, stream, canonical = _prepare_full_round(
        monkeypatch, result=result, transition=_transition
    )

    output = await run_agent_round(_round_payload(run))

    assert output == {
        "status": AgentRunStatus.COMPLETED.value,
        "message_id": str(canonical.id),
    }
    assert ("run_end", {"status": "completed", "message_id": str(canonical.id)}) in [
        (call.args[0], call.args[1])
        for call in stream.publish.await_args_list
        if len(call.args) >= 2
    ]


@pytest.mark.asyncio
async def test_run_agent_round_completion_race_stops_winner(monkeypatch):
    stopping = _run(status=AgentRunStatus.STOPPING)
    stopped = _run(status=AgentRunStatus.STOPPED)

    async def _transition(run, _expected, status, **_kwargs):
        if status == AgentRunStatus.COMPLETING:
            return None
        run.status = status
        return stopped

    get_run = AsyncMock(side_effect=[None, stopping])
    result = _round_result()
    run, stream, canonical = _prepare_full_round(
        monkeypatch, result=result, transition=_transition, get_run=get_run
    )
    get_run.side_effect = [run, stopping]

    output = await run_agent_round(_round_payload(run))

    assert output == {
        "status": AgentRunStatus.STOPPED.value,
        "message_id": str(canonical.id),
    }
    assert ("run_end", {"status": "stopped", "message_id": str(canonical.id)}) in [
        (call.args[0], call.args[1])
        for call in stream.publish.await_args_list
        if len(call.args) >= 2
    ]


@pytest.mark.asyncio
async def test_run_agent_round_completion_race_returns_new_terminal_status(monkeypatch):
    current = _run(status=AgentRunStatus.COMPLETED)

    async def _transition(_run, _expected, _status, **_kwargs):
        return None

    get_run = AsyncMock(side_effect=[None, current])
    result = _round_result()
    run, _stream, _ = _prepare_full_round(
        monkeypatch, result=result, transition=_transition, get_run=get_run
    )
    get_run.side_effect = [run, current]

    output = await run_agent_round(_round_payload(run))

    assert output == {"status": AgentRunStatus.COMPLETED.value}


@pytest.mark.asyncio
async def test_run_agent_round_completion_lost_row_fails_without_overwrite(monkeypatch):
    async def _transition(run, _expected, status, **_kwargs):
        if status == AgentRunStatus.COMPLETED:
            return None
        run.status = status
        return run

    get_run = AsyncMock(side_effect=[None, None])
    result = _round_result()
    run, stream, _ = _prepare_full_round(
        monkeypatch, result=result, transition=_transition, get_run=get_run
    )
    get_run.side_effect = [run, None]

    output = await run_agent_round(_round_payload(run))

    assert output["status"] == AgentRunStatus.FAILED.value
    assert output["error"] == "run not found"
    assert any(call.args[0] == "error" for call in stream.publish.await_args_list)


@pytest.mark.asyncio
async def test_run_agent_round_failure_returns_when_failed_transition_is_lost(
    monkeypatch,
):
    async def _transition(_run, _expected, _status, **_kwargs):
        return None

    result = _round_result()
    run, _stream, _ = _prepare_full_round(
        monkeypatch,
        result=result,
        transition=_transition,
        rebuild=RuntimeError("boom"),
    )

    output = await run_agent_round(_round_payload(run))

    assert output == {"status": AgentRunStatus.RUNNING.value, "error": "boom"}


@pytest.mark.asyncio
async def test_run_agent_round_failure_publishes_when_failed_transition_wins(
    monkeypatch,
):
    async def _transition(run, _expected, status, **_kwargs):
        if status == AgentRunStatus.FAILED:
            run.status = status
            return run
        return None

    result = _round_result()
    run, stream, _ = _prepare_full_round(
        monkeypatch,
        result=result,
        transition=_transition,
        rebuild=RuntimeError("boom"),
    )

    output = await run_agent_round(_round_payload(run))

    assert output == {"status": AgentRunStatus.FAILED.value, "error": "boom"}
    assert ("run_end", {"status": "failed", "message_id": ""}) in [
        (call.args[0], call.args[1])
        for call in stream.publish.await_args_list
        if len(call.args) >= 2
    ]


@pytest.mark.asyncio
async def test_run_agent_round_failure_raises_when_run_row_disappears(monkeypatch):
    async def _transition(_run, _expected, _status, **_kwargs):
        return None

    get_run = AsyncMock(side_effect=[None, None])
    result = _round_result()
    run, _stream, _ = _prepare_full_round(
        monkeypatch,
        result=result,
        transition=_transition,
        get_run=get_run,
        rebuild=RuntimeError("boom"),
    )
    get_run.side_effect = [run, None]

    with pytest.raises(LookupError, match="run not found"):
        await run_agent_round(_round_payload(run))


def _round_payload(run):
    return {
        "run_id": str(run.id),
        "agent_id": str(run.agent_id),
        "conversation_id": str(run.conversation_id),
    }


def _prepare_lock_busy_round(
    monkeypatch, worker, run, get_run, pending_inputs, transition
):
    agent = SimpleNamespace(id=run.agent_id)
    conversation = SimpleNamespace(id=run.conversation_id)
    stream = SimpleNamespace(seed_sequence=AsyncMock(), publish=AsyncMock())

    async def _get_or_none(*, id):
        if id == run.agent_id:
            return agent
        if id == run.conversation_id:
            return conversation
        return None

    monkeypatch.setattr(worker.agent_run_store, "get_run", get_run)
    monkeypatch.setattr(worker.Agent, "get_or_none", _get_or_none)
    monkeypatch.setattr(worker.Conversation, "get_or_none", _get_or_none)
    monkeypatch.setattr(
        worker.agent_run_store, "acquire_run_lock", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(
        worker.agent_run_store,
        "has_pending_inputs",
        AsyncMock(side_effect=pending_inputs),
    )
    monkeypatch.setattr(worker.agent_run_store, "transition_run_if_status", transition)
    monkeypatch.setattr(worker, "AgentRunStream", lambda _id: stream)
    return stream


@pytest.mark.asyncio
async def test_run_agent_round_lock_busy_raises_when_current_row_is_missing(
    monkeypatch,
):
    from app.services import agent_run_worker as worker

    run = _run(status=AgentRunStatus.RUNNING)
    _prepare_lock_busy_round(
        monkeypatch,
        worker,
        run,
        AsyncMock(side_effect=[run, None]),
        [False],
        AsyncMock(return_value=None),
    )

    with pytest.raises(LookupError, match="run not found"):
        await run_agent_round(_round_payload(run))


@pytest.mark.asyncio
async def test_run_agent_round_lock_busy_stop_race_handles_all_winners(monkeypatch):
    from app.services import agent_run_worker as worker

    current_running = _run(status=AgentRunStatus.RUNNING)
    current_stopping = _run(status=AgentRunStatus.STOPPING)
    current_stopped = _run(status=AgentRunStatus.STOPPED)
    initial_stopping = _run(status=AgentRunStatus.RUNNING)
    initial_running = _run(status=AgentRunStatus.RUNNING)
    initial_stopped = _run(status=AgentRunStatus.RUNNING)
    initial_transitioned = _run(status=AgentRunStatus.RUNNING)

    async def _stop_transition(run, _expected, status, **_kwargs):
        run.status = status
        return run

    scenarios = (
        (
            initial_stopping,
            AsyncMock(side_effect=[initial_stopping, current_stopping, None]),
            [False],
            AsyncMock(return_value=None),
            "raises",
        ),
        (
            initial_running,
            AsyncMock(
                side_effect=[
                    initial_running,
                    current_running,
                    current_running,
                    current_running,
                    current_running,
                ]
            ),
            [False, True],
            AsyncMock(return_value=None),
            AgentRunStatus.RUNNING.value,
        ),
        (
            initial_stopped,
            AsyncMock(side_effect=[initial_stopped, current_stopped]),
            [False, True],
            AsyncMock(return_value=None),
            AgentRunStatus.STOPPED.value,
        ),
        (
            initial_transitioned,
            AsyncMock(side_effect=[initial_transitioned, current_running]),
            [False, True],
            _stop_transition,
            AgentRunStatus.STOPPED.value,
        ),
    )

    for initial, get_run, pending_inputs, transition, expected in scenarios:
        _prepare_lock_busy_round(
            monkeypatch, worker, initial, get_run, pending_inputs, transition
        )
        if expected == "raises":
            with pytest.raises(LookupError, match="run not found"):
                await run_agent_round(_round_payload(initial))
        else:
            result = await run_agent_round(_round_payload(initial))
            assert result == {"status": expected}


@pytest.mark.asyncio
async def test_run_agent_round_lock_busy_failure_handles_missing_and_current_rows(
    monkeypatch,
):
    from app.services import agent_run_worker as worker

    missing_initial = _run(status=AgentRunStatus.RUNNING)
    _prepare_lock_busy_round(
        monkeypatch,
        worker,
        missing_initial,
        AsyncMock(
            side_effect=[missing_initial, _run(status=AgentRunStatus.RUNNING), None]
        ),
        [False, False],
        AsyncMock(return_value=None),
    )
    with pytest.raises(LookupError, match="run not found"):
        await run_agent_round(_round_payload(missing_initial))

    current_initial = _run(status=AgentRunStatus.RUNNING)
    current = _run(status=AgentRunStatus.RUNNING)
    _prepare_lock_busy_round(
        monkeypatch,
        worker,
        current_initial,
        AsyncMock(side_effect=[current_initial, current, current, current]),
        [False, False],
        AsyncMock(return_value=None),
    )
    result = await run_agent_round(_round_payload(current_initial))
    assert result == {"status": AgentRunStatus.RUNNING.value}


@pytest.mark.asyncio
@pytest.mark.parametrize("result_flag", ["deadline_exceeded", "manually_stopped"])
async def test_run_agent_round_stop_result_returns_when_transition_is_lost(
    monkeypatch, result_flag
):
    async def _transition(_run, _expected, _status, **_kwargs):
        return None

    result = _round_result(**{result_flag: True})
    run, _stream, canonical = _prepare_full_round(
        monkeypatch, result=result, transition=_transition
    )

    output = await run_agent_round(_round_payload(run))

    if result_flag == "deadline_exceeded":
        assert output == {
            "status": AgentRunStatus.RUNNING.value,
            "reason": "deadline_exceeded",
        }
    else:
        assert output == {
            "status": AgentRunStatus.RUNNING.value,
            "message_id": str(canonical.id),
        }


@pytest.mark.asyncio
@pytest.mark.parametrize("result_flag", ["deadline_exceeded", "manually_stopped"])
async def test_run_agent_round_stop_result_fails_when_run_row_disappears(
    monkeypatch, result_flag
):
    async def _transition(run, _expected, status, **_kwargs):
        if status == AgentRunStatus.FAILED:
            run.status = status
            return run
        return None

    get_run = AsyncMock(side_effect=[None, None])
    result = _round_result(**{result_flag: True})
    run, _stream, _ = _prepare_full_round(
        monkeypatch,
        result=result,
        transition=_transition,
        get_run=get_run,
    )
    get_run.side_effect = [run, None]

    output = await run_agent_round(_round_payload(run))

    assert output == {"status": AgentRunStatus.FAILED.value, "error": "run not found"}


@pytest.mark.asyncio
async def test_run_agent_round_completion_claim_raises_when_row_disappears(
    monkeypatch,
):
    async def _transition(run, _expected, status, **_kwargs):
        if status == AgentRunStatus.FAILED:
            run.status = status
            return run
        return None

    get_run = AsyncMock(side_effect=[None, None])
    run, _stream, _ = _prepare_full_round(
        monkeypatch,
        result=_round_result(),
        transition=_transition,
        get_run=get_run,
    )
    get_run.side_effect = [run, None]

    output = await run_agent_round(_round_payload(run))

    assert output == {"status": AgentRunStatus.FAILED.value, "error": "run not found"}


@pytest.mark.asyncio
async def test_run_agent_round_stopping_race_raises_when_stop_claim_disappears(
    monkeypatch,
):
    stopping = _run(status=AgentRunStatus.STOPPING)

    async def _transition(run, _expected, status, **_kwargs):
        if status == AgentRunStatus.FAILED:
            run.status = status
            return run
        return None

    get_run = AsyncMock(side_effect=[None, None, None])
    run, _stream, _ = _prepare_full_round(
        monkeypatch,
        result=_round_result(),
        transition=_transition,
        get_run=get_run,
    )
    get_run.side_effect = [run, stopping, None]

    output = await run_agent_round(_round_payload(run))

    assert output == {"status": AgentRunStatus.FAILED.value, "error": "run not found"}


@pytest.mark.asyncio
async def test_run_agent_round_stopping_race_returns_without_second_claim(
    monkeypatch,
):
    stopping = _run(status=AgentRunStatus.STOPPING)
    stopped = _run(status=AgentRunStatus.STOPPED)

    async def _transition(_run, _expected, _status, **_kwargs):
        return None

    get_run = AsyncMock(side_effect=[None, None, None])
    run, stream, canonical = _prepare_full_round(
        monkeypatch,
        result=_round_result(),
        transition=_transition,
        get_run=get_run,
    )
    get_run.side_effect = [run, stopping, stopped]

    output = await run_agent_round(_round_payload(run))

    assert output == {
        "status": AgentRunStatus.STOPPED.value,
        "message_id": str(canonical.id),
    }
    assert not any(
        call.args[:1] == ("run_end",) and call.args[1].get("status") == "stopped"
        for call in stream.publish.await_args_list
        if len(call.args) >= 2
    )


@pytest.mark.asyncio
async def test_run_agent_round_completion_returns_reloaded_status_without_claim(
    monkeypatch,
):
    completed = _run(status=AgentRunStatus.COMPLETED)

    async def _transition(run, _expected, status, **_kwargs):
        if status == AgentRunStatus.COMPLETING:
            run.status = status
            return run
        return None

    get_run = AsyncMock(side_effect=[None, None])
    run, _stream, canonical = _prepare_full_round(
        monkeypatch,
        result=_round_result(),
        transition=_transition,
        get_run=get_run,
    )
    get_run.side_effect = [run, completed]

    output = await run_agent_round(_round_payload(run))

    assert output == {
        "status": AgentRunStatus.COMPLETED.value,
        "message_id": str(canonical.id),
    }
