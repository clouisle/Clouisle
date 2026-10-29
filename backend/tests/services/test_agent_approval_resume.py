"""Durable AgentRun resume for tool approvals on real SQLite.

Covers the store transition (waiting -> queued marker / tool error), the
worker's approved original-call execution (real result, never the approval
itself), and the no-resume rules for stopped runs.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from tortoise import Tortoise

from app.models.agent import Agent, Conversation, Message
from app.models.observability_payload import ObservabilityTrajectoryEntry
from app.models.agent_run import AgentRun, AgentRunMode, AgentRunStatus
from app.models.tool import CustomToolType, Tool, ToolType
from app.models.user import Team, TeamMember, User
from app.schemas.tool_approval import (
    ApprovalVote,
    ExecutionEntrypoint,
    ExecutionRunKind,
    ToolExecutionCancelReason,
    ToolExecutionStatus,
)
from app.services import agent_run_store, tool_approvals
from app.services.agent_run_worker import _execute_approved_pending_tool


class _Redis:
    async def set(self, key, value, ex=None, nx=False):
        return True

    async def get(self, key):
        return None

    async def delete(self, key):
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
        username=f"resume_{uuid4().hex[:8]}",
        email=f"{uuid4().hex}@resume.test",
        hashed_password="x",
    )


async def _team_and_agent(owner: User):
    team = await Team.create(id=uuid4(), name=f"resume_team_{uuid4().hex[:8]}")
    await TeamMember.create(id=uuid4(), team_id=team.id, user_id=owner.id, role="owner")
    agent = await Agent.create(id=uuid4(), team_id=team.id, name="resume-agent")
    conversation = await Conversation.create(
        id=uuid4(), agent_id=agent.id, user_id=owner.id
    )
    return team, agent, conversation


async def _allow_tool(team: Team) -> Tool:
    return await Tool.create(
        id=uuid4(),
        team_id=team.id,
        name=f"resume_tool_{uuid4().hex[:8]}",
        display_name="Resume tool",
        description="resume test",
        type=ToolType.CUSTOM,
        custom_type=CustomToolType.HTTP,
        approval_policy={"default_decision": "allow"},
    )


async def _execution(
    *,
    tool: Tool,
    actor: User,
    team: Team,
    run: AgentRun | None = None,
    policy=None,
    entrypoint: ExecutionEntrypoint = ExecutionEntrypoint.AGENT_RUN,
    entrypoint_id: str | None = None,
):
    return await tool_approvals.create_execution(
        tool=tool,
        operation="todo.write",
        parameters={"value": 1},
        actor=actor,
        team_id=team.id,
        entrypoint=entrypoint,
        entrypoint_id=entrypoint_id
        if entrypoint_id is not None
        else (str(run.agent_id) if run else None),
        run_kind=ExecutionRunKind.AGENT if run else None,
        run_id=run.id if run else None,
        tool_call_id="call-1" if run else None,
        policy=policy,
    )


async def _waiting_run(
    agent: Agent,
    conversation: Conversation,
    user: User,
    *,
    status: AgentRunStatus = AgentRunStatus.WAITING,
    round_id=None,
    payload: dict | None = None,
) -> AgentRun:
    round_id = round_id or uuid4()
    return await AgentRun.create(
        id=uuid4(),
        agent_id=agent.id,
        conversation_id=conversation.id,
        user_id=user.id,
        mode=AgentRunMode.SEND,
        status=status,
        active_round_id=round_id,
        pending_tool_call_id="call-1" if status == AgentRunStatus.WAITING else None,
        pending_tool_name="custom_resume_tool",
        pending_tool_input={"interaction_kind": "tool_approval"},
        pending_tool_round_id=round_id,
        pending_tool_round_index=5 if status == AgentRunStatus.WAITING else None,
        pending_tool_iteration_index=2 if status == AgentRunStatus.WAITING else None,
        worker_payload=payload
        or {
            "history_override": [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "name": "custom_resume_tool",
                            "arguments": {"interaction_kind": "tool_approval"},
                        }
                    ],
                    "round_id": str(round_id),
                    "round_index": 4,
                    "round_role": "assistant_step",
                    "is_round_canonical": False,
                    "iteration_index": 2,
                }
            ],
            "pending_tool_display_name": "Resume tool",
            "created_message_count": 3,
        },
    )


@pytest.mark.asyncio
async def test_ready_approval_queues_marker_then_worker_result_replaces_it(monkeypatch):
    async with _database(monkeypatch):
        user = await _user()
        team, agent, conversation = await _team_and_agent(user)
        tool = await _allow_tool(team)
        run = await _waiting_run(agent, conversation, user)
        execution = await _execution(tool=tool, actor=user, team=team, run=run)
        assert execution.status == ToolExecutionStatus.READY

        queued = await agent_run_store.queue_agent_run_approval_resume(execution)
        assert queued is not None
        assert queued.status == AgentRunStatus.QUEUED
        assert queued.pending_tool_call_id is None
        marker = queued.worker_payload["resume_tool_approval"]
        assert marker["execution_id"] == str(execution.id)
        assert marker["tool_call_id"] == "call-1"
        assert marker["tool_name"] == "custom_resume_tool"
        assert "resume_tool_result" not in queued.worker_payload

        # The worker claims the queued run before it records the real result.
        queued.status = AgentRunStatus.RUNNING
        await queued.save(update_fields=["status"])
        payload = await agent_run_store.record_resumed_tool_result(
            queued.id,
            tool_call_id="call-1",
            tool_name="custom_resume_tool",
            tool_display_name="Resume tool",
            display_result='{"ok": true}',
            llm_result='{"ok": true}',
            is_error=False,
            round_id=run.pending_tool_round_id,
            round_index=5,
            iteration_index=2,
        )
        assert payload is not None
        assert "resume_tool_approval" not in payload
        assert payload["resume_tool_result"]["is_error"] is False
        assert payload["resume_tool_result"]["result"] == '{"ok": true}'
        history = payload["history_override"]
        assert history[-1]["role"] == "tool"
        assert history[-1]["tool_call_id"] == "call-1"
        assert history[-1]["content"] == '{"ok": true}'
        assert (
            await Message.filter(
                conversation_id=conversation.id,
                tool_call_id="call-1",
                tool_name="custom_resume_tool",
            ).count()
            == 1
        )

        # A second approval notification cannot queue the run again.
        assert await agent_run_store.queue_agent_run_approval_resume(execution) is None


@pytest.mark.asyncio
async def test_schedule_dispatches_queued_resume_exactly_once(monkeypatch):
    async with _database(monkeypatch):
        user = await _user()
        team, agent, conversation = await _team_and_agent(user)
        tool = await _allow_tool(team)
        run = await _waiting_run(agent, conversation, user)
        execution = await _execution(tool=tool, actor=user, team=team, run=run)

        dispatched = []

        async def fake_dispatch(payload, queued_run):
            dispatched.append((payload, queued_run.id))

        from app.services import agent_submission

        monkeypatch.setattr(agent_submission, "dispatch_run", fake_dispatch)
        scheduled = await agent_run_store.schedule_agent_run_approval_resume(execution)
        assert scheduled is not None
        assert scheduled.status == AgentRunStatus.QUEUED
        assert len(dispatched) == 1
        assert dispatched[0][1] == run.id
        assert dispatched[0][0]["resume_tool_approval"]["execution_id"] == str(
            execution.id
        )

        assert (
            await agent_run_store.schedule_agent_run_approval_resume(execution) is None
        )
        assert len(dispatched) == 1


@pytest.mark.asyncio
async def test_expiry_resumes_agent_run_with_tool_error(monkeypatch):
    async with _database(monkeypatch):
        user = await _user()
        team, agent, conversation = await _team_and_agent(user)
        tool = await Tool.create(
            id=uuid4(),
            team_id=team.id,
            name=f"expire_tool_{uuid4().hex[:8]}",
            display_name="Expire tool",
            description="resume test",
            type=ToolType.CUSTOM,
            custom_type=CustomToolType.HTTP,
            approval_policy={
                "default_decision": "require_approval",
                "gates": [{"kind": "caller"}],
            },
        )
        run = await _waiting_run(agent, conversation, user)
        from datetime import datetime, timedelta, timezone

        execution = await _execution(
            tool=tool,
            actor=user,
            team=team,
            run=run,
            policy={
                "default_decision": "require_approval",
                "gates": [{"kind": "caller"}],
            },
        )
        # Move the approval deadline into the past without waiting.
        execution.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await execution.save(update_fields=["expires_at"])

        dispatched = []

        async def fake_dispatch(payload, queued_run):
            dispatched.append(queued_run.id)

        from app.services import agent_submission

        monkeypatch.setattr(agent_submission, "dispatch_run", fake_dispatch)
        assert await tool_approvals.expire_execution(execution.id) is True
        assert dispatched == [run.id]
        queued = await AgentRun.get(id=run.id)
        assert queued.status == AgentRunStatus.QUEUED
        assert (
            "expired" in queued.worker_payload["resume_tool_result"]["result"].lower()
        )
        assert "resume_tool_approval" not in queued.worker_payload


@pytest.mark.asyncio
async def test_park_run_waiting_merges_checkpoint_with_real_database(monkeypatch):
    async with _database(monkeypatch):
        user = await _user()
        _team, _agent, conversation = await _team_and_agent(user)
        round_id = uuid4()
        checkpoint = {"mode": "semantic", "summary_text": "keep me"}
        run = await _waiting_run(
            _agent,
            conversation,
            user,
            status=AgentRunStatus.RUNNING,
            round_id=round_id,
            payload={
                "history_override": [{"role": "user", "content": "fresh"}],
                "active_round_checkpoint": checkpoint,
            },
        )
        # The worker's in-memory instance predates the checkpoint and carries a
        # stale copy in its resume payload.
        run.worker_payload = {}
        await agent_run_store.park_run_waiting(
            run,
            tool_call_id="call-1",
            tool_name="custom_resume_tool",
            tool_input={"interaction_kind": "tool_approval"},
            round_id=round_id,
            round_index=6,
            iteration_index=3,
            worker_payload={
                "history_override": [{"role": "user", "content": "stale"}],
                "resume": True,
                "active_round_checkpoint": {
                    "mode": "readback_only",
                    "summary_text": None,
                },
            },
        )
        fresh = await AgentRun.get(id=run.id)
        assert fresh.status == AgentRunStatus.WAITING
        # The locked row value wins for the checkpoint; resume fields win for
        # everything the caller actually supplies.
        assert fresh.worker_payload["active_round_checkpoint"] == checkpoint
        assert fresh.worker_payload["resume"] is True
        assert fresh.worker_payload["history_override"] == [
            {"role": "user", "content": "stale"}
        ]


@pytest.mark.asyncio
async def test_compression_events_survive_approval_pause_and_remain_visible(
    monkeypatch,
):
    import asyncio
    from types import SimpleNamespace
    from app.api.v1.endpoints.chat import build_message_round_payloads
    from app.models.agent import MessageRole, MessageRoundRole
    from app.services.agent_run_worker import MicroBatchingCollector

    async with _database(monkeypatch):
        user = await _user()
        _, agent, conversation = await _team_and_agent(user)
        round_id = uuid4()
        message = await Message.create(
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content="done",
            round_id=round_id,
            round_role=MessageRoundRole.ASSISTANT_FINAL,
            is_round_canonical=True,
        )
        run = await _waiting_run(
            agent, conversation, user, status=AgentRunStatus.RUNNING, round_id=round_id
        )
        run.canonical_message_id = message.id
        await run.save(update_fields=["canonical_message_id"])
        events = asyncio.Queue()
        published = []

        async def publish(event_type, payload, **kwargs):
            published.append((event_type, payload, kwargs))

        collector = MicroBatchingCollector(
            event_queue=events,
            stream=SimpleNamespace(publish=publish),
            run=run,
            canonical_message_id=message.id,
        )
        task = asyncio.create_task(collector.run_loop())
        await events.put(
            (
                "compression_end",
                {"stage": "micro", "before_tokens": 900, "after_tokens": 500},
            )
        )
        await events.put(None)
        await task
        await agent_run_store.park_run_waiting(
            run,
            tool_call_id="call",
            tool_name="tool",
            tool_input={},
            round_id=round_id,
            round_index=1,
            iteration_index=1,
            worker_payload={"compression_events": []},
        )
        payloads = await build_message_round_payloads([message])
        assert payloads[0]["compression_events"][0]["payload"]["before_tokens"] == 900
        assert published[0][0] == "compression_end"


@pytest.mark.asyncio
async def test_post_park_recheck_closes_decision_before_waiting_race(monkeypatch):
    async with _database(monkeypatch):
        user = await _user()
        team, agent, conversation = await _team_and_agent(user)
        tool = await _allow_tool(team)
        run = await _waiting_run(
            agent, conversation, user, status=AgentRunStatus.RUNNING
        )
        execution = await _execution(tool=tool, actor=user, team=team, run=run)
        assert execution.status == ToolExecutionStatus.READY

        # Decision happens while the run is still RUNNING: the scheduler sees
        # no WAITING row and cannot queue yet.
        assert (
            await agent_run_store.schedule_agent_run_approval_resume(execution) is None
        )
        assert (await AgentRun.get(id=run.id)).status == AgentRunStatus.RUNNING

        # The worker then parks the pending call. The post-park recheck must
        # find the already-ready execution and queue the resume itself.
        await agent_run_store.park_run_waiting(
            run,
            tool_call_id="call-1",
            tool_name="custom_resume_tool",
            tool_input={"interaction_kind": "tool_approval"},
            round_id=run.active_round_id,
            round_index=5,
            iteration_index=2,
        )
        queued = await agent_run_store.queue_agent_run_resume_if_approval_terminal(
            run.id
        )
        assert queued is not None
        assert queued.status == AgentRunStatus.QUEUED
        assert queued.pending_tool_call_id is None
        assert queued.worker_payload["resume_tool_approval"]["execution_id"] == str(
            execution.id
        )


@pytest.mark.asyncio
async def test_rejection_resumes_with_tool_error_and_no_side_effect(monkeypatch):
    async with _database(monkeypatch):
        user = await _user()
        team, agent, conversation = await _team_and_agent(user)
        tool = await Tool.create(
            id=uuid4(),
            team_id=team.id,
            name=f"reject_tool_{uuid4().hex[:8]}",
            display_name="Reject tool",
            description="resume test",
            type=ToolType.CUSTOM,
            custom_type=CustomToolType.HTTP,
            approval_policy={
                "default_decision": "require_approval",
                "gates": [{"kind": "caller"}],
            },
        )
        run = await _waiting_run(agent, conversation, user)
        execution = await _execution(
            tool=tool,
            actor=user,
            team=team,
            run=run,
            policy={
                "default_decision": "require_approval",
                "gates": [{"kind": "caller"}],
            },
        )
        assert execution.status == ToolExecutionStatus.AWAITING_APPROVAL
        request = (await tool_approvals.list_pending_approvals_for_user(user))[0][0]

        dispatched = []

        async def fake_dispatch(payload, queued_run):
            dispatched.append(queued_run.id)

        from app.services import agent_submission

        monkeypatch.setattr(agent_submission, "dispatch_run", fake_dispatch)
        await tool_approvals.decide_approval(
            request.id,
            user,
            decision=ApprovalVote.REJECT,
            idempotency_key="reject-1",
        )

        rejected = await tool_approvals.get_execution(execution.id)
        assert rejected.status == ToolExecutionStatus.CANCELLED
        assert dispatched == [run.id]
        queued = await AgentRun.get(id=run.id)
        assert queued.status == AgentRunStatus.QUEUED
        assert "resume_tool_approval" not in queued.worker_payload
        result = queued.worker_payload["resume_tool_result"]
        assert result["is_error"] is True
        assert "rejected" in result["result"].lower()
        assert (
            queued.worker_payload["history_override"][-1]["content"] == result["result"]
        )
        assert (
            await Message.filter(
                conversation_id=conversation.id, tool_call_id="call-1"
            ).count()
            == 1
        )


@pytest.mark.asyncio
async def test_stopped_run_and_run_stopped_cancel_reason_never_resume(monkeypatch):
    async with _database(monkeypatch):
        user = await _user()
        team, agent, conversation = await _team_and_agent(user)
        tool = await _allow_tool(team)

        stopped_run = await _waiting_run(
            agent, conversation, user, status=AgentRunStatus.STOPPED
        )
        ready_execution = await _execution(
            tool=tool, actor=user, team=team, run=stopped_run
        )
        assert (
            await agent_run_store.queue_agent_run_approval_resume(ready_execution)
            is None
        )
        assert (await AgentRun.get(id=stopped_run.id)).status == AgentRunStatus.STOPPED

        waiting_run = await _waiting_run(agent, conversation, user)
        cancel_execution = await _execution(
            tool=tool, actor=user, team=team, run=waiting_run
        )
        await tool_approvals.cancel_execution(
            cancel_execution.id, reason=ToolExecutionCancelReason.RUN_STOPPED
        )
        stopped_execution = await tool_approvals.get_execution(cancel_execution.id)
        assert stopped_execution.cancel_reason == ToolExecutionCancelReason.RUN_STOPPED
        assert (
            await agent_run_store.queue_agent_run_approval_resume(stopped_execution)
            is None
        )
        waiting = await AgentRun.get(id=waiting_run.id)
        assert waiting.status == AgentRunStatus.WAITING
        assert waiting.pending_tool_call_id == "call-1"


@pytest.mark.asyncio
async def test_worker_executes_approved_original_call_and_records_real_result(
    monkeypatch,
):
    async with _database(monkeypatch):
        user = await _user()
        team, agent, conversation = await _team_and_agent(user)
        tool = await _allow_tool(team)
        run = await _waiting_run(agent, conversation, user)
        execution = await _execution(tool=tool, actor=user, team=team, run=run)
        queued = await agent_run_store.queue_agent_run_approval_resume(execution)
        assert queued is not None
        queued.status = AgentRunStatus.RUNNING
        await queued.save(update_fields=["status"])

        calls = []

        async def fake_stored_tool(agent_arg, name, arguments, user_arg):
            calls.append((agent_arg.id, name, arguments, user_arg.id))
            return {"ok": True, "value": 7}

        from app.services import agent_tool_execution

        monkeypatch.setattr(
            agent_tool_execution, "execute_agent_stored_tool", fake_stored_tool
        )
        payload = await _execute_approved_pending_tool(
            dict(queued.worker_payload or {}),
            run=queued,
            agent=agent,
            conversation=conversation,
        )
        assert payload is not None
        assert calls == [(agent.id, "custom_resume_tool", {}, user.id)]
        assert payload["resume_tool_result"]["is_error"] is False
        assert '"ok":true' in payload["resume_tool_result"]["result"].replace(" ", "")
        assert payload["history_override"][-1]["role"] == "tool"
        assert "resume_tool_approval" not in payload
        metric = payload["resume_dependency_metrics"][0]
        assert metric["status"] == "completed"
        assert metric["tool_call_id"] == "call-1"
        assert metric["error_category"] is None
        trajectory = await ObservabilityTrajectoryEntry.filter(run_id=run.id).first()
        assert trajectory is not None
        assert trajectory.kind == "tool"
        assert "call-1" in list(trajectory.tool_call_ids or [])
        assert (
            await Message.filter(
                conversation_id=conversation.id,
                tool_call_id="call-1",
                tool_name="custom_resume_tool",
            ).count()
            == 1
        )


@pytest.mark.asyncio
async def test_stale_claim_of_terminal_run_becomes_outcome_unknown_only(monkeypatch):
    async with _database(monkeypatch):
        user = await _user()
        team, agent, conversation = await _team_and_agent(user)
        tool = await _allow_tool(team)
        run = await _waiting_run(agent, conversation, user)
        execution = await _execution(tool=tool, actor=user, team=team, run=run)
        await tool_approvals.claim_execution(
            execution.id,
            claim_token="stale-claim",
            tool_definition_version=tool.definition_version,
        )
        run.status = AgentRunStatus.INTERRUPTED
        await run.save(update_fields=["status"])
        from datetime import datetime, timedelta, timezone

        claimed_at = datetime.now(timezone.utc) - timedelta(hours=1)
        await tool_approvals.ToolExecution.filter(id=execution.id).update(
            claimed_at=claimed_at, started_at=claimed_at
        )

        marked = await tool_approvals.mark_stale_executing_outcome_unknown(
            stale_after_seconds=60
        )
        assert marked == 1
        stale = await tool_approvals.get_execution(execution.id)
        assert stale.status == ToolExecutionStatus.OUTCOME_UNKNOWN
        assert stale.error_code == "claim_expired"
        assert (
            await tool_approvals.mark_stale_executing_outcome_unknown(
                stale_after_seconds=60
            )
            == 0
        )


@pytest.mark.asyncio
async def test_stale_claim_on_active_run_is_not_touched(monkeypatch):
    async with _database(monkeypatch):
        user = await _user()
        team, agent, conversation = await _team_and_agent(user)
        tool = await _allow_tool(team)
        run = await _waiting_run(
            agent, conversation, user, status=AgentRunStatus.RUNNING
        )
        execution = await _execution(tool=tool, actor=user, team=team, run=run)
        await tool_approvals.claim_execution(
            execution.id,
            claim_token="active-claim",
            tool_definition_version=tool.definition_version,
        )
        from datetime import datetime, timedelta, timezone

        claimed_at = datetime.now(timezone.utc) - timedelta(hours=1)
        await tool_approvals.ToolExecution.filter(id=execution.id).update(
            claimed_at=claimed_at, started_at=claimed_at
        )
        assert (
            await tool_approvals.mark_stale_executing_outcome_unknown(
                stale_after_seconds=60
            )
            == 0
        )
        assert (
            await tool_approvals.get_execution(execution.id)
        ).status == ToolExecutionStatus.EXECUTING


@pytest.mark.asyncio
async def test_worker_routes_builtin_resume_through_execute_tool_call(monkeypatch):
    async with _database(monkeypatch):
        user = await _user()
        team, agent, conversation = await _team_and_agent(user)
        builtin = await Tool.create(
            id=uuid4(),
            team_id=team.id,
            name=f"builtin_{uuid4().hex[:8]}",
            display_name="Builtin tool",
            description="builtin resume test",
            type=ToolType.BUILTIN,
            approval_policy={"default_decision": "allow"},
        )
        run = await _waiting_run(agent, conversation, user)
        execution = await _execution(tool=builtin, actor=user, team=team, run=run)
        queued = await agent_run_store.queue_agent_run_approval_resume(execution)
        assert queued is not None
        queued.status = AgentRunStatus.RUNNING
        await queued.save(update_fields=["status"])

        calls = []

        async def fake_execute_call(tool_name, arguments, **kwargs):
            calls.append((tool_name, arguments, kwargs))
            return {"output": "builtin result"}

        from app.api.v1.endpoints import chat_tools

        monkeypatch.setattr(chat_tools, "execute_tool_call", fake_execute_call)
        payload = await _execute_approved_pending_tool(
            dict(queued.worker_payload or {}),
            run=queued,
            agent=agent,
            conversation=conversation,
        )
        assert payload is not None
        assert len(calls) == 1
        tool_name, arguments, kwargs = calls[0]
        assert tool_name == "custom_resume_tool"
        assert arguments == {}
        assert kwargs["agent"].id == agent.id
        assert kwargs["user"].id == user.id
        assert kwargs["conversation_id"] == conversation.id
        assert payload["resume_tool_result"]["is_error"] is False
        assert "builtin result" in payload["resume_tool_result"]["result"]


@pytest.mark.asyncio
async def test_approved_resume_reuses_noninteractive_stored_origin(monkeypatch):
    async with _database(monkeypatch):
        user = await _user()
        team, agent, conversation = await _team_and_agent(user)
        tool = await _allow_tool(team)
        run = await _waiting_run(agent, conversation, user)
        execution = await _execution(
            tool=tool,
            actor=user,
            team=team,
            run=run,
            entrypoint=ExecutionEntrypoint.API_KEY,
            entrypoint_id="key-stable-1",
        )
        queued = await agent_run_store.queue_agent_run_approval_resume(execution)
        assert queued is not None
        queued.status = AgentRunStatus.RUNNING
        await queued.save(update_fields=["status"])

        observed = []

        async def fake_execute_call(tool_name, arguments, **kwargs):
            from app.services.tool_context import current_tool_identity

            identity = current_tool_identity()
            assert identity is not None
            observed.append(
                (identity.entrypoint, identity.entrypoint_id, identity.interactive)
            )
            return {"ok": True}

        from app.api.v1.endpoints import chat_tools

        monkeypatch.setattr(chat_tools, "execute_tool_call", fake_execute_call)
        payload = await _execute_approved_pending_tool(
            dict(queued.worker_payload or {}),
            run=queued,
            agent=agent,
            conversation=conversation,
        )
        assert payload is not None
        assert observed == [("api_key", "key-stable-1", False)]


@pytest.mark.asyncio
async def test_worker_original_call_failure_records_tool_error_and_continues(
    monkeypatch,
):
    async with _database(monkeypatch):
        user = await _user()
        team, agent, conversation = await _team_and_agent(user)
        tool = await _allow_tool(team)
        run = await _waiting_run(agent, conversation, user)
        execution = await _execution(tool=tool, actor=user, team=team, run=run)
        queued = await agent_run_store.queue_agent_run_approval_resume(execution)
        assert queued is not None
        queued.status = AgentRunStatus.RUNNING
        await queued.save(update_fields=["status"])

        async def failing_stored_tool(*args, **kwargs):
            raise RuntimeError("external side effect failed")

        from app.services import agent_tool_execution

        monkeypatch.setattr(
            agent_tool_execution, "execute_agent_stored_tool", failing_stored_tool
        )
        payload = await _execute_approved_pending_tool(
            dict(queued.worker_payload or {}),
            run=queued,
            agent=agent,
            conversation=conversation,
        )
        assert payload is not None
        assert payload["resume_tool_result"]["is_error"] is True
        assert "external side effect failed" in payload["resume_tool_result"]["result"]
        assert payload["history_override"][-1]["round_role"] == "tool_result"
        metric = payload["resume_dependency_metrics"][0]
        assert metric["status"] == "failed"
        assert metric["error_category"] == "RuntimeError"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "origin", [ExecutionEntrypoint.FEISHU_CHANNEL, ExecutionEntrypoint.WECHAT_CHANNEL]
)
@pytest.mark.parametrize("decision", ["approve", "reject"])
async def test_channel_decision_is_bound_to_run_actor_origin_and_execution(
    monkeypatch, origin, decision
):
    from app.schemas.response import BusinessError
    from app.services.channel_tool_approval import (
        approval_preview,
        decide_channel_approval,
    )
    from app.services import agent_submission

    async with _database(monkeypatch):
        user = await _user()
        other = await _user()
        team, agent, conversation = await _team_and_agent(user)
        tool = await _allow_tool(team)
        run = await _waiting_run(agent, conversation, user)
        origin_id = str(uuid4())
        execution = await _execution(
            tool=tool,
            actor=user,
            team=team,
            run=run,
            entrypoint=origin,
            entrypoint_id=origin_id,
            policy={
                "default_decision": "require_approval",
                "gates": [{"kind": "caller"}],
            },
        )
        run.pending_tool_input = {
            "interaction_kind": "tool_approval",
            "execution_id": str(execution.id),
            "tool_description": "Changes a task",
        }
        await run.save(update_fields=["pending_tool_input"])
        token, text = await approval_preview(run, user, origin, origin_id)
        assert token == str(execution.id)
        assert "Changes a task" in text and token in text
        with pytest.raises(BusinessError):
            await approval_preview(run, other, origin, origin_id)
        with pytest.raises(BusinessError):
            await approval_preview(run, user, origin, str(uuid4()))
        with pytest.raises(BusinessError):
            await decide_channel_approval(
                run, user, origin, origin_id, str(uuid4()), decision, uuid4()
            )
        dispatched = []

        async def dispatch(payload, queued):
            dispatched.append(queued.id)

        monkeypatch.setattr(agent_submission, "dispatch_run", dispatch)
        await decide_channel_approval(
            run, user, origin, origin_id, token, decision, uuid4()
        )
        current = await AgentRun.get(id=run.id)
        assert current.status == AgentRunStatus.QUEUED
        assert dispatched == [run.id]
        assert (await tool_approvals.get_execution(execution.id)).status == (
            ToolExecutionStatus.READY
            if decision == "approve"
            else ToolExecutionStatus.CANCELLED
        )
        with pytest.raises(BusinessError):
            await decide_channel_approval(
                current, user, origin, origin_id, token, decision, uuid4()
            )
