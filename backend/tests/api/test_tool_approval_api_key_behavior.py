"""Behavior tests for API-key-bound tool approvals.

The tests drive the real HTTP handlers and the real approval service against an
in-memory database, so they observe identity persistence, key isolation,
idempotent replay and the durable AgentRun resume exactly as the routes do.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from tortoise import Tortoise

from app.api.v1.endpoints.tool_approvals import (
    get_approval_request,
    get_my_execution,
    list_my_executions,
    list_pending_approval_requests,
    submit_approval_decision,
    submit_execution_decision,
)
from app.models.agent import Agent, Conversation
from app.models.agent_run import AgentRun, AgentRunMode, AgentRunStatus
from app.models.api_key import APIKey
from app.models.tool import CustomToolType, Tool, ToolType
from app.models.user import Team, TeamMember, User
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.tool_approval import (
    ApprovalRequestStatus,
    ApprovalVote,
    ExecutionEntrypoint,
    ExecutionRunKind,
    ToolApprovalDecisionIn,
    ToolExecutionStatus,
)
from app.services import tool_approvals as service
from app.services.tool_context import RuntimeToolIdentity, tool_identity_scope


@asynccontextmanager
async def _database():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        yield
    finally:
        await Tortoise.close_connections()


async def _user(label: str) -> User:
    return await User.create(
        id=uuid4(),
        username=f"{label}_{uuid4().hex[:8]}",
        email=f"{label}_{uuid4().hex[:8]}@approval.test",
        hashed_password="x",
    )


async def _team(name: str, owner: User) -> Team:
    team = await Team.create(id=uuid4(), name=f"{name}_{uuid4().hex[:8]}")
    await TeamMember.create(id=uuid4(), team_id=team.id, user_id=owner.id, role="owner")
    return team


async def _agent(team: Team, label: str) -> Agent:
    return await Agent.create(
        id=uuid4(), team_id=team.id, name=f"{label}_{uuid4().hex[:8]}"
    )


async def _api_key(owner: User, *, agents: list[Agent] | None = None) -> APIKey:
    key = await APIKey.create(
        id=uuid4(),
        name=f"key_{uuid4().hex[:6]}",
        key_prefix=f"clou_{uuid4().hex[:6]}"[:12],
        key_hash="x",
        user_id=owner.id,
        is_active=True,
    )
    if agents:
        await key.agents.add(*agents)
    return key


async def _run(
    owner: User,
    agent: Agent,
    *,
    status: AgentRunStatus = AgentRunStatus.WAITING,
    tool_call_id: str = "call-1",
    tool_name: str = "ticket_close",
    api_key_id=None,
) -> AgentRun:
    conversation = await Conversation.create(
        id=uuid4(), agent_id=agent.id, user_id=owner.id
    )
    return await AgentRun.create(
        id=uuid4(),
        agent_id=agent.id,
        conversation_id=conversation.id,
        user_id=owner.id,
        mode=AgentRunMode.SEND,
        api_key_id=api_key_id,
        status=status,
        pending_tool_call_id=tool_call_id,
        pending_tool_name=tool_name,
        worker_payload={},
    )


async def _tool(team: Team) -> Tool:
    return await Tool.create(
        id=uuid4(),
        team_id=team.id,
        name=f"tool_{uuid4().hex[:8]}",
        display_name="Approval tool",
        description="api key approval test",
        type=ToolType.CUSTOM,
        custom_type=CustomToolType.HTTP,
        approval_policy={
            "default_decision": "require_approval",
            "gates": [{"kind": "caller"}],
        },
    )


async def _api_key_execution(
    *,
    owner: User,
    team: Team,
    tool: Tool,
    run: AgentRun,
    key: APIKey,
    tool_call_id: str = "call-1",
    run_kind: ExecutionRunKind = ExecutionRunKind.AGENT,
):
    with tool_identity_scope(
        RuntimeToolIdentity(
            run_id=run.id if run_kind == ExecutionRunKind.AGENT else uuid4(),
            tool_call_id=tool_call_id,
            entrypoint=ExecutionEntrypoint.API_KEY.value,
            entrypoint_id=str(key.id),
            api_key_id=key.id,
            interactive=False,
        )
    ):
        execution = await service.create_execution(
            tool=tool,
            operation="ticket.close",
            parameters={"ticket": "T-1"},
            actor=owner,
            team_id=team.id,
            entrypoint=ExecutionEntrypoint.API_KEY,
            entrypoint_id=str(key.id),
            run_kind=run_kind,
            run_id=run.id,
            tool_call_id=tool_call_id,
            entrypoint_interactive=False,
        )
    return execution


async def _pending_request(execution_id):
    return await service.ToolApprovalRequest.filter(
        execution_id=execution_id,
        status=ApprovalRequestStatus.PENDING,
    ).first()


def _decision(vote: str = "approve", *, key: str = "idem-1") -> ToolApprovalDecisionIn:
    return ToolApprovalDecisionIn(
        decision=ApprovalVote(vote),
        reason="reviewed",
        idempotency_key=key,
    )


async def _no_dispatch(*_args, **_kwargs) -> None:
    return None


@pytest.fixture(autouse=True)
def _stub_agent_dispatch(monkeypatch):
    """Never publish to a broker from an approval test; capture dispatch only."""
    monkeypatch.setattr("app.services.agent_submission.dispatch_run", _no_dispatch)


def _assert_business_error(exc_info, *, code: int, status_code: int):
    assert exc_info.value.code == code
    assert exc_info.value.status_code == status_code


@pytest.mark.asyncio
async def test_api_key_run_execution_is_bound_and_decision_resumes_run(monkeypatch):
    """API-key caller gates park, the same key decides and the run resumes."""
    async with _database():
        owner = await _user("key-owner")
        team = await _team("key-team", owner)
        agent = await _agent(team, "key-agent")
        key = await _api_key(owner, agents=[agent])
        tool = await _tool(team)
        run = await _run(owner, agent, tool_name="ticket_close", api_key_id=key.id)
        execution = await _api_key_execution(
            owner=owner, team=team, tool=tool, run=run, key=key
        )

        assert execution.api_key_id == key.id
        assert execution.status == ToolExecutionStatus.AWAITING_APPROVAL
        request = await _pending_request(execution.id)
        assert request is not None and request.gate_kind.value == "caller"

        listing = await list_pending_approval_requests(
            page=1, page_size=20, auth_result=(owner, key)
        )
        assert [item.id for item in listing["data"].items] == [request.id]

        detail = await get_approval_request(
            request_id=request.id, auth_result=(owner, key)
        )
        assert detail["data"].id == request.id

        dispatched: list[tuple[dict, object]] = []

        async def _capture(payload, current_run):
            dispatched.append((payload, current_run))

        monkeypatch.setattr("app.services.agent_submission.dispatch_run", _capture)

        result = await submit_execution_decision(
            execution_id=execution.id,
            payload=_decision(),
            auth_result=(owner, key),
        )
        assert result["data"].execution_status == ToolExecutionStatus.READY
        assert result["data"].remaining_approvals == 0
        assert result["data"].decision.decision == ApprovalVote.APPROVE

        fresh_execution = await service.get_execution(execution.id)
        assert fresh_execution.status == ToolExecutionStatus.READY
        fresh_run = await AgentRun.get(id=run.id)
        assert fresh_run.status == AgentRunStatus.QUEUED
        assert fresh_run.pending_tool_call_id is None
        assert fresh_run.worker_payload["resume_tool_approval"]["execution_id"] == str(
            execution.id
        )
        assert dispatched and dispatched[0][1].id == run.id


@pytest.mark.asyncio
async def test_different_key_of_same_owner_cannot_read_or_decide():
    async with _database():
        owner = await _user("same-owner")
        team = await _team("same-owner-team", owner)
        agent = await _agent(team, "shared-agent")
        key_a = await _api_key(owner, agents=[agent])
        key_b = await _api_key(owner, agents=[agent])
        tool = await _tool(team)
        run = await _run(owner, agent)
        execution = await _api_key_execution(
            owner=owner, team=team, tool=tool, run=run, key=key_a
        )
        request = await _pending_request(execution.id)

        with pytest.raises(BusinessError) as detail_error:
            await get_my_execution(
                execution_id=execution.id, auth_result=(owner, key_b)
            )
        _assert_business_error(
            detail_error,
            code=ResponseCode.TOOL_EXECUTION_ACCESS_DENIED,
            status_code=403,
        )

        with pytest.raises(BusinessError) as request_error:
            await get_approval_request(
                request_id=request.id, auth_result=(owner, key_b)
            )
        _assert_business_error(
            request_error,
            code=ResponseCode.TOOL_APPROVAL_NOT_AUTHORIZED,
            status_code=403,
        )

        with pytest.raises(BusinessError) as decide_error:
            await submit_approval_decision(
                request_id=request.id,
                payload=_decision(),
                auth_result=(owner, key_b),
            )
        _assert_business_error(
            decide_error,
            code=ResponseCode.TOOL_APPROVAL_NOT_AUTHORIZED,
            status_code=403,
        )

        assert (
            await service.ToolApprovalDecision.filter(execution_id=execution.id).count()
            == 0
        )
        assert (
            await service.get_execution(execution.id)
        ).status == ToolExecutionStatus.AWAITING_APPROVAL

        listing = await list_pending_approval_requests(
            page=1, page_size=20, auth_result=(owner, key_b)
        )
        assert listing["data"].total == 0


@pytest.mark.asyncio
async def test_inactive_key_is_rejected_before_any_decision():
    async with _database():
        owner = await _user("inactive-key")
        team = await _team("inactive-team", owner)
        agent = await _agent(team, "inactive-agent")
        key = await _api_key(owner, agents=[agent])
        tool = await _tool(team)
        run = await _run(owner, agent)
        execution = await _api_key_execution(
            owner=owner, team=team, tool=tool, run=run, key=key
        )
        request = await _pending_request(execution.id)
        await APIKey.filter(id=key.id).update(is_active=False)
        key.is_active = False

        with pytest.raises(BusinessError) as view_error:
            await get_my_execution(execution_id=execution.id, auth_result=(owner, key))
        _assert_business_error(
            view_error, code=ResponseCode.TOOL_EXECUTION_ACCESS_DENIED, status_code=403
        )

        with pytest.raises(BusinessError) as decide_error:
            await submit_approval_decision(
                request_id=request.id,
                payload=_decision(),
                auth_result=(owner, key),
            )
        _assert_business_error(
            decide_error,
            code=ResponseCode.TOOL_APPROVAL_NOT_AUTHORIZED,
            status_code=403,
        )
        inbox = await list_pending_approval_requests(
            page=1, page_size=20, auth_result=(owner, key)
        )
        assert inbox["data"].total == 0
        executions = await list_my_executions(
            page=1,
            page_size=20,
            status=None,
            tool_id=None,
            run_kind=None,
            run_id=None,
            auth_result=(owner, key),
        )
        assert executions["data"].total == 0
        assert (
            await service.ToolApprovalDecision.filter(execution_id=execution.id).count()
            == 0
        )


@pytest.mark.asyncio
async def test_key_agent_scope_is_rechecked_at_decision_time():
    async with _database():
        owner = await _user("scope-owner")
        team = await _team("scope-team", owner)
        agent = await _agent(team, "scope-agent")
        other_agent = await _agent(team, "other-agent")
        key = await _api_key(owner, agents=[other_agent])
        tool = await _tool(team)
        run = await _run(owner, agent)
        execution = await _api_key_execution(
            owner=owner, team=team, tool=tool, run=run, key=key
        )
        request = await _pending_request(execution.id)

        with pytest.raises(BusinessError) as decide_error:
            await submit_approval_decision(
                request_id=request.id,
                payload=_decision(),
                auth_result=(owner, key),
            )
        _assert_business_error(
            decide_error,
            code=ResponseCode.TOOL_APPROVAL_NOT_AUTHORIZED,
            status_code=403,
        )
        assert (
            await service.get_execution(execution.id)
        ).status == ToolExecutionStatus.AWAITING_APPROVAL


@pytest.mark.asyncio
async def test_legacy_execution_binding_uses_entrypoint_id_and_stays_decidable():
    """Rows created before the column existed keep their key binding."""
    async with _database():
        owner = await _user("legacy-owner")
        team = await _team("legacy-team", owner)
        agent = await _agent(team, "legacy-agent")
        key = await _api_key(owner, agents=[agent])
        other_key = await _api_key(owner, agents=[agent])
        tool = await _tool(team)
        run = await _run(owner, agent)
        execution = await _api_key_execution(
            owner=owner, team=team, tool=tool, run=run, key=key
        )
        await service.ToolExecution.filter(id=execution.id).update(api_key_id=None)
        execution = await service.get_execution(execution.id)
        assert execution.api_key_id is None
        request = await _pending_request(execution.id)

        with pytest.raises(BusinessError):
            await get_my_execution(
                execution_id=execution.id, auth_result=(owner, other_key)
            )

        view = await get_my_execution(
            execution_id=execution.id, auth_result=(owner, key)
        )
        assert view["data"].id == execution.id

        decided = await submit_approval_decision(
            request_id=request.id,
            payload=_decision(),
            auth_result=(owner, key),
        )
        assert decided["data"].execution_status == ToolExecutionStatus.READY


@pytest.mark.asyncio
async def test_run_reads_are_bound_to_the_submitting_key():
    """Reconnect/read endpoints must not accept another key of the owner."""
    from app.api.v1.endpoints import chat as chat_endpoints

    async with _database():
        owner = await _user("run-read-owner")
        team = await _team("run-read-team", owner)
        agent = await _agent(team, "run-read-agent")
        key = await _api_key(owner, agents=[agent])
        other_key = await _api_key(owner, agents=[agent])
        run = await _run(owner, agent, status=AgentRunStatus.RUNNING, api_key_id=key.id)

        loaded = await chat_endpoints._load_owned_run(
            agent.id, run.id, owner, api_key=key
        )
        assert loaded.id == run.id
        assert (
            await chat_endpoints._load_owned_run(agent.id, run.id, owner)
        ).id == run.id

        with pytest.raises(BusinessError) as foreign_error:
            await chat_endpoints._load_owned_run(
                agent.id, run.id, owner, api_key=other_key
            )
        _assert_business_error(
            foreign_error, code=ResponseCode.NOT_FOUND, status_code=404
        )

        legacy = await _run(owner, agent, status=AgentRunStatus.RUNNING)
        legacy.worker_payload = {
            "tool_entrypoint": "api_key",
            "tool_entrypoint_id": str(key.id),
        }
        await legacy.save(update_fields=["worker_payload"])
        assert (
            await chat_endpoints._load_owned_run(
                agent.id, legacy.id, owner, api_key=key
            )
        ).id == legacy.id
        with pytest.raises(BusinessError):
            await chat_endpoints._load_owned_run(
                agent.id, legacy.id, owner, api_key=other_key
            )

        payload_bound = await _run(owner, agent, status=AgentRunStatus.RUNNING)
        payload_bound.worker_payload = {"api_key_id": str(key.id)}
        await payload_bound.save(update_fields=["worker_payload"])
        assert (
            await chat_endpoints._load_owned_run(
                agent.id, payload_bound.id, owner, api_key=key
            )
        ).id == payload_bound.id
        with pytest.raises(BusinessError):
            await chat_endpoints._load_owned_run(
                agent.id, payload_bound.id, owner, api_key=other_key
            )

        # A run persisted before API-key binding keeps owner-scoped access.
        plain = await _run(owner, agent, status=AgentRunStatus.RUNNING)
        assert (
            await chat_endpoints._load_owned_run(agent.id, plain.id, owner, api_key=key)
        ).id == plain.id


@pytest.mark.asyncio
async def test_lists_hide_executions_whose_run_binding_mismatches():
    """List/inbox apply the same run owner/key constraints as the detail view."""
    async with _database():
        owner = await _user("mismatch-owner")
        outsider = await _user("mismatch-outsider")
        team = await _team("mismatch-team", owner)
        agent = await _agent(team, "mismatch-agent")
        key_a = await _api_key(owner, agents=[agent])
        key_b = await _api_key(owner, agents=[agent])
        tool = await _tool(team)

        good_run = await _run(owner, agent, api_key_id=key_a.id)
        good = await _api_key_execution(
            owner=owner, team=team, tool=tool, run=good_run, key=key_a
        )
        good_run_2 = await _run(
            owner, agent, tool_call_id="call-4", api_key_id=key_a.id
        )
        good_2 = await _api_key_execution(
            owner=owner,
            team=team,
            tool=tool,
            run=good_run_2,
            key=key_a,
            tool_call_id="call-4",
        )

        other_key_run = await _run(
            owner, agent, tool_call_id="call-2", api_key_id=key_b.id
        )
        wrong_key = await _api_key_execution(
            owner=owner,
            team=team,
            tool=tool,
            run=other_key_run,
            key=key_a,
            tool_call_id="call-2",
        )

        foreign_run = await _run(outsider, agent, tool_call_id="call-3")
        wrong_owner = await _api_key_execution(
            owner=owner,
            team=team,
            tool=tool,
            run=foreign_run,
            key=key_a,
            tool_call_id="call-3",
        )

        listing = await list_my_executions(
            page=1,
            page_size=10,
            status=None,
            tool_id=None,
            run_kind=None,
            run_id=None,
            auth_result=(owner, key_a),
        )
        assert listing["data"].total == 2
        assert {item.id for item in listing["data"].items} == {good.id, good_2.id}

        first_page = await list_my_executions(
            page=1,
            page_size=1,
            status=None,
            tool_id=None,
            run_kind=None,
            run_id=None,
            auth_result=(owner, key_a),
        )
        second_page = await list_my_executions(
            page=2,
            page_size=1,
            status=None,
            tool_id=None,
            run_kind=None,
            run_id=None,
            auth_result=(owner, key_a),
        )
        assert first_page["data"].total == 2
        assert second_page["data"].total == 2
        assert len(first_page["data"].items) == 1
        assert len(second_page["data"].items) == 1
        assert {
            first_page["data"].items[0].id,
            second_page["data"].items[0].id,
        } == {good.id, good_2.id}

        inbox = await list_pending_approval_requests(
            page=1, page_size=20, auth_result=(owner, key_a)
        )
        assert inbox["data"].total == 2
        assert {item.execution_id for item in inbox["data"].items} == {
            good.id,
            good_2.id,
        }

        for hidden in (wrong_key, wrong_owner):
            with pytest.raises(BusinessError) as detail_error:
                await get_my_execution(
                    execution_id=hidden.id, auth_result=(owner, key_a)
                )
            _assert_business_error(
                detail_error,
                code=ResponseCode.TOOL_EXECUTION_ACCESS_DENIED,
                status_code=403,
            )
            hidden_request = await _pending_request(hidden.id)
            with pytest.raises(BusinessError) as decide_error:
                await submit_approval_decision(
                    request_id=hidden_request.id,
                    payload=_decision(key=f"hidden-{hidden.id}"),
                    auth_result=(owner, key_a),
                )
            _assert_business_error(
                decide_error,
                code=ResponseCode.TOOL_APPROVAL_NOT_AUTHORIZED,
                status_code=403,
            )


@pytest.mark.asyncio
async def test_revoked_key_lists_are_empty_even_with_stale_instance():
    """Liveness is re-read from the key row, not trusted from the instance."""
    async with _database():
        owner = await _user("stale-key-owner")
        team = await _team("stale-key-team", owner)
        agent = await _agent(team, "stale-key-agent")
        key = await _api_key(owner, agents=[agent])
        tool = await _tool(team)
        run = await _run(owner, agent)
        execution = await _api_key_execution(
            owner=owner, team=team, tool=tool, run=run, key=key
        )
        await _pending_request(execution.id)

        await APIKey.filter(id=key.id).update(is_active=False)
        assert key.is_active is True  # stale in-memory credential

        listing = await list_my_executions(
            page=1,
            page_size=20,
            status=None,
            tool_id=None,
            run_kind=None,
            run_id=None,
            auth_result=(owner, key),
        )
        assert listing["data"].total == 0
        inbox = await list_pending_approval_requests(
            page=1, page_size=20, auth_result=(owner, key)
        )
        assert inbox["data"].total == 0
        with pytest.raises(BusinessError):
            await get_my_execution(execution_id=execution.id, auth_result=(owner, key))


@pytest.mark.asyncio
async def test_legacy_run_with_matching_payload_is_hidden_from_lists():
    """Legacy runs are list fail-closed even when the payload names the key."""
    async with _database():
        owner = await _user("legacy-list-owner")
        team = await _team("legacy-list-team", owner)
        agent = await _agent(team, "legacy-list-agent")
        key = await _api_key(owner, agents=[agent])
        tool = await _tool(team)
        run = await _run(owner, agent)
        run.worker_payload = {
            "api_key_id": str(key.id),
            "tool_entrypoint": "api_key",
            "tool_entrypoint_id": str(key.id),
        }
        await run.save(update_fields=["worker_payload"])
        execution = await _api_key_execution(
            owner=owner, team=team, tool=tool, run=run, key=key
        )
        request = await _pending_request(execution.id)

        listing = await list_my_executions(
            page=1,
            page_size=20,
            status=None,
            tool_id=None,
            run_kind=None,
            run_id=None,
            auth_result=(owner, key),
        )
        assert listing["data"].total == 0
        inbox = await list_pending_approval_requests(
            page=1, page_size=20, auth_result=(owner, key)
        )
        assert inbox["data"].total == 0

        # Detail/decision by explicit id still validate the legacy evidence.
        view = await get_my_execution(
            execution_id=execution.id, auth_result=(owner, key)
        )
        assert view["data"].id == execution.id
        decided = await submit_approval_decision(
            request_id=request.id,
            payload=_decision(key="legacy-list-decide"),
            auth_result=(owner, key),
        )
        assert decided["data"].execution_status == ToolExecutionStatus.READY


@pytest.mark.asyncio
async def test_legacy_run_with_conflicting_payload_is_hidden_and_denied():
    """A legacy run naming another key never leaks and is never decidable."""
    async with _database():
        owner = await _user("legacy-conflict-owner")
        team = await _team("legacy-conflict-team", owner)
        agent = await _agent(team, "legacy-conflict-agent")
        key = await _api_key(owner, agents=[agent])
        other_key = await _api_key(owner, agents=[agent])
        tool = await _tool(team)
        run = await _run(owner, agent)
        run.worker_payload = {"api_key_id": str(other_key.id)}
        await run.save(update_fields=["worker_payload"])
        execution = await _api_key_execution(
            owner=owner, team=team, tool=tool, run=run, key=key
        )
        request = await _pending_request(execution.id)

        listing = await list_my_executions(
            page=1,
            page_size=20,
            status=None,
            tool_id=None,
            run_kind=None,
            run_id=None,
            auth_result=(owner, key),
        )
        assert listing["data"].total == 0
        inbox = await list_pending_approval_requests(
            page=1, page_size=20, auth_result=(owner, key)
        )
        assert inbox["data"].total == 0

        with pytest.raises(BusinessError) as detail_error:
            await get_my_execution(execution_id=execution.id, auth_result=(owner, key))
        _assert_business_error(
            detail_error,
            code=ResponseCode.TOOL_EXECUTION_ACCESS_DENIED,
            status_code=403,
        )
        with pytest.raises(BusinessError) as decide_error:
            await submit_approval_decision(
                request_id=request.id,
                payload=_decision(key="legacy-conflict-decide"),
                auth_result=(owner, key),
            )
        _assert_business_error(
            decide_error,
            code=ResponseCode.TOOL_APPROVAL_NOT_AUTHORIZED,
            status_code=403,
        )
        assert (
            await service.get_execution(execution.id)
        ).status == ToolExecutionStatus.AWAITING_APPROVAL


@pytest.mark.asyncio
async def test_unbound_api_key_entrypoint_cannot_wait_for_approval():
    """Only an authenticated key identity may park a non-interactive call."""
    async with _database():
        owner = await _user("unbound-owner")
        team = await _team("unbound-team", owner)
        tool = await _tool(team)
        run_id = uuid4()

        with pytest.raises(BusinessError) as unbound:
            await service.create_execution(
                tool=tool,
                operation="ticket.close",
                parameters={"ticket": "T-9"},
                actor=owner,
                team_id=team.id,
                entrypoint=ExecutionEntrypoint.API_KEY,
                entrypoint_id="not-a-key",
                run_kind=ExecutionRunKind.AGENT,
                run_id=run_id,
                tool_call_id="call-1",
                entrypoint_interactive=False,
            )
        assert unbound.value.code == (
            ResponseCode.TOOL_APPROVAL_POLICY_CONFIGURATION_REQUIRED
        )
        assert await service.ToolExecution.all().count() == 0

        key = await _api_key(owner, agents=[])

        with tool_identity_scope(
            RuntimeToolIdentity(
                run_id=run_id,
                tool_call_id="call-2",
                entrypoint=ExecutionEntrypoint.API_KEY.value,
                entrypoint_id="opaque",
                api_key_id=key.id,
                interactive=False,
            )
        ):
            execution = await service.create_execution(
                tool=tool,
                operation="ticket.close",
                parameters={"ticket": "T-10"},
                actor=owner,
                team_id=team.id,
                entrypoint=ExecutionEntrypoint.API_KEY,
                entrypoint_id="opaque",
                run_kind=ExecutionRunKind.AGENT,
                run_id=run_id,
                tool_call_id="call-2",
                entrypoint_interactive=False,
            )
        assert execution.api_key_id == key.id
        assert execution.status == ToolExecutionStatus.AWAITING_APPROVAL


@pytest.mark.asyncio
async def test_execution_and_run_key_binding_must_agree():
    """An execution cannot be approved under a key other than its run's."""
    async with _database():
        owner = await _user("agree-owner")
        team = await _team("agree-team", owner)
        agent = await _agent(team, "agree-agent")
        key_a = await _api_key(owner, agents=[agent])
        key_b = await _api_key(owner, agents=[agent])
        tool = await _tool(team)
        run = await _run(owner, agent, api_key_id=key_b.id)
        execution = await _api_key_execution(
            owner=owner, team=team, tool=tool, run=run, key=key_a
        )
        request = await _pending_request(execution.id)

        assert execution.api_key_id == key_a.id
        assert not await service.execution_owned_by_api_key(execution, key_a)
        with pytest.raises(BusinessError) as decide_error:
            await submit_approval_decision(
                request_id=request.id,
                payload=_decision(),
                auth_result=(owner, key_a),
            )
        _assert_business_error(
            decide_error,
            code=ResponseCode.TOOL_APPROVAL_NOT_AUTHORIZED,
            status_code=403,
        )


@pytest.mark.asyncio
async def test_key_without_agent_links_keeps_legacy_all_agents_scope():
    """A key with no linked Agents keeps the existing all-Agents contract."""
    async with _database():
        owner = await _user("global-key-owner")
        team = await _team("global-key-team", owner)
        agent = await _agent(team, "global-agent")
        key = await _api_key(owner)
        tool = await _tool(team)
        run = await _run(owner, agent)
        execution = await _api_key_execution(
            owner=owner, team=team, tool=tool, run=run, key=key
        )
        request = await _pending_request(execution.id)

        assert await service.execution_owned_by_api_key(execution, key)
        decided = await submit_approval_decision(
            request_id=request.id,
            payload=_decision(),
            auth_result=(owner, key),
        )
        assert decided["data"].execution_status == ToolExecutionStatus.READY


@pytest.mark.asyncio
async def test_workflow_origin_execution_is_not_decidable_by_api_key():
    async with _database():
        owner = await _user("workflow-owner")
        team = await _team("workflow-team", owner)
        agent = await _agent(team, "workflow-agent")
        key = await _api_key(owner, agents=[agent])
        tool = await _tool(team)
        run = await _run(owner, agent)
        execution = await _api_key_execution(
            owner=owner,
            team=team,
            tool=tool,
            run=run,
            key=key,
            run_kind=ExecutionRunKind.WORKFLOW,
        )
        request = await _pending_request(execution.id)

        with pytest.raises(BusinessError) as decide_error:
            await submit_approval_decision(
                request_id=request.id,
                payload=_decision(),
                auth_result=(owner, key),
            )
        _assert_business_error(
            decide_error,
            code=ResponseCode.TOOL_APPROVAL_NOT_AUTHORIZED,
            status_code=403,
        )
        assert (
            await service.get_execution(execution.id)
        ).status == ToolExecutionStatus.AWAITING_APPROVAL


@pytest.mark.asyncio
async def test_jwt_owner_keeps_existing_access_and_outsiders_do_not():
    async with _database():
        owner = await _user("jwt-owner")
        outsider = await _user("jwt-outsider")
        team = await _team("jwt-team", owner)
        agent = await _agent(team, "jwt-agent")
        key = await _api_key(owner, agents=[agent])
        tool = await _tool(team)
        run = await _run(owner, agent)
        execution = await _api_key_execution(
            owner=owner, team=team, tool=tool, run=run, key=key
        )
        request = await _pending_request(execution.id)

        view = await get_my_execution(execution_id=execution.id, auth_result=owner)
        assert view["data"].id == execution.id
        listing = await list_pending_approval_requests(
            page=1, page_size=20, auth_result=owner
        )
        assert listing["data"].total == 1

        with pytest.raises(BusinessError) as outsider_error:
            await get_my_execution(execution_id=execution.id, auth_result=outsider)
        _assert_business_error(
            outsider_error,
            code=ResponseCode.TOOL_EXECUTION_ACCESS_DENIED,
            status_code=403,
        )
        with pytest.raises(BusinessError):
            await submit_approval_decision(
                request_id=request.id,
                payload=_decision(),
                auth_result=outsider,
            )

        decided = await submit_approval_decision(
            request_id=request.id,
            payload=_decision(key="jwt-decision"),
            auth_result=owner,
        )
        assert decided["data"].decision.decision == ApprovalVote.APPROVE


@pytest.mark.asyncio
async def test_idempotent_replay_is_key_bound_and_conflicts_are_reported():
    async with _database():
        owner = await _user("idem-owner")
        team = await _team("idem-team", owner)
        agent = await _agent(team, "idem-agent")
        key = await _api_key(owner, agents=[agent])
        other_key = await _api_key(owner, agents=[agent])
        tool = await _tool(team)
        run = await _run(owner, agent)
        execution = await _api_key_execution(
            owner=owner, team=team, tool=tool, run=run, key=key
        )
        request = await _pending_request(execution.id)

        first = await submit_approval_decision(
            request_id=request.id,
            payload=_decision(key="replay-1"),
            auth_result=(owner, key),
        )
        replay = await submit_approval_decision(
            request_id=request.id,
            payload=_decision(key="replay-1"),
            auth_result=(owner, key),
        )
        assert replay["data"].decision.id == first["data"].decision.id

        with pytest.raises(BusinessError) as other_key_replay:
            await submit_approval_decision(
                request_id=request.id,
                payload=_decision(key="replay-1"),
                auth_result=(owner, other_key),
            )
        _assert_business_error(
            other_key_replay,
            code=ResponseCode.TOOL_APPROVAL_NOT_AUTHORIZED,
            status_code=403,
        )

        with pytest.raises(BusinessError) as conflict:
            await submit_approval_decision(
                request_id=request.id,
                payload=_decision("reject", key="replay-1"),
                auth_result=(owner, key),
            )
        _assert_business_error(
            conflict,
            code=ResponseCode.TOOL_APPROVAL_IDEMPOTENCY_CONFLICT,
            status_code=409,
        )

        with pytest.raises(BusinessError) as decided:
            await submit_approval_decision(
                request_id=request.id,
                payload=_decision(key="replay-2"),
                auth_result=(owner, key),
            )
        _assert_business_error(
            decided,
            code=ResponseCode.TOOL_APPROVAL_ALREADY_DECIDED,
            status_code=409,
        )
        assert (
            await service.ToolApprovalDecision.filter(execution_id=execution.id).count()
            == 1
        )


@pytest.mark.asyncio
async def test_execution_listing_is_scoped_to_the_authenticated_key():
    async with _database():
        owner = await _user("list-owner")
        team = await _team("list-team", owner)
        agent = await _agent(team, "list-agent")
        key = await _api_key(owner, agents=[agent])
        other_key = await _api_key(owner, agents=[agent])
        tool = await _tool(team)
        run = await _run(owner, agent, api_key_id=key.id)
        key_execution = await _api_key_execution(
            owner=owner, team=team, tool=tool, run=run, key=key
        )
        chat_execution = await service.create_execution(
            tool=tool,
            operation="ticket.close",
            parameters={"ticket": "T-2"},
            actor=owner,
            team_id=team.id,
            entrypoint=ExecutionEntrypoint.CHAT,
        )

        scoped = await list_my_executions(
            page=1,
            page_size=20,
            status=None,
            tool_id=None,
            run_kind=ExecutionRunKind.AGENT,
            run_id=key_execution.run_id,
            auth_result=(owner, key),
        )
        assert [item.id for item in scoped["data"].items] == [key_execution.id]

        other = await list_my_executions(
            page=1,
            page_size=20,
            status=None,
            tool_id=None,
            run_kind=None,
            run_id=None,
            auth_result=(owner, other_key),
        )
        assert other["data"].total == 0

        jwt_listing = await list_my_executions(
            page=1,
            page_size=20,
            status=None,
            tool_id=None,
            run_kind=None,
            run_id=None,
            auth_result=owner,
        )
        assert {item.id for item in jwt_listing["data"].items} == {
            key_execution.id,
            chat_execution.id,
        }


@pytest.mark.asyncio
async def test_api_key_entrypoint_identity_falls_back_to_entrypoint_id():
    """A payload created before the explicit field still binds the key."""
    async with _database():
        owner = await _user("fallback-owner")
        team = await _team("fallback-team", owner)
        agent = await _agent(team, "fallback-agent")
        key = await _api_key(owner, agents=[agent])
        tool = await _tool(team)
        run = await _run(owner, agent)

        execution = await service.create_execution(
            tool=tool,
            operation="ticket.close",
            parameters={"ticket": "T-3"},
            actor=owner,
            team_id=team.id,
            entrypoint=ExecutionEntrypoint.API_KEY,
            entrypoint_id=str(key.id),
            run_kind=ExecutionRunKind.AGENT,
            run_id=run.id,
            tool_call_id="call-1",
            entrypoint_interactive=False,
        )

        assert execution.api_key_id == key.id
        assert execution.status == ToolExecutionStatus.AWAITING_APPROVAL

        chat_execution = await service.create_execution(
            tool=tool,
            operation="ticket.close",
            parameters={"ticket": "T-4"},
            actor=owner,
            team_id=team.id,
            entrypoint=ExecutionEntrypoint.CHAT,
            entrypoint_id=None,
        )
        assert chat_execution.api_key_id is None


@pytest.mark.asyncio
async def test_expired_key_cannot_view_or_decide_an_unexpired_execution():
    """Liveness is authoritative even when the request reaches the service."""
    from datetime import datetime, timedelta, timezone

    async with _database():
        owner = await _user("expired-key")
        team = await _team("expired-team", owner)
        agent = await _agent(team, "expired-agent")
        key = await _api_key(owner, agents=[agent])
        tool = await _tool(team)
        run = await _run(owner, agent)
        execution = await _api_key_execution(
            owner=owner, team=team, tool=tool, run=run, key=key
        )
        request = await _pending_request(execution.id)
        assert request is not None

        await APIKey.filter(id=key.id).update(
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)
        )
        assert key.is_active is True  # the in-memory row still looks usable

        with pytest.raises(BusinessError) as view_error:
            await get_my_execution(execution_id=execution.id, auth_result=(owner, key))
        _assert_business_error(
            view_error, code=ResponseCode.TOOL_EXECUTION_ACCESS_DENIED, status_code=403
        )

        with pytest.raises(BusinessError) as decide_error:
            await submit_approval_decision(
                request_id=request.id,
                payload=_decision(key="expired-1"),
                auth_result=(owner, key),
            )
        _assert_business_error(
            decide_error,
            code=ResponseCode.TOOL_APPROVAL_NOT_AUTHORIZED,
            status_code=403,
        )

        assert (
            await service.ToolApprovalDecision.filter(execution_id=execution.id).count()
            == 0
        )
        executions = await list_my_executions(
            page=1,
            page_size=20,
            status=None,
            tool_id=None,
            run_kind=None,
            run_id=None,
            auth_result=(owner, key),
        )
        assert executions["data"].total == 0
        inbox = await list_pending_approval_requests(
            page=1, page_size=20, auth_result=(owner, key)
        )
        assert inbox["data"].total == 0


@pytest.mark.asyncio
async def test_revoked_key_cannot_replay_its_own_decision():
    """Deactivation closes replay too, not only new decisions."""
    async with _database():
        owner = await _user("revoke-replay")
        team = await _team("revoke-replay-team", owner)
        agent = await _agent(team, "revoke-replay-agent")
        key = await _api_key(owner, agents=[agent])
        tool = await _tool(team)
        run = await _run(owner, agent)
        execution = await _api_key_execution(
            owner=owner, team=team, tool=tool, run=run, key=key
        )
        request = await _pending_request(execution.id)

        first = await submit_approval_decision(
            request_id=request.id,
            payload=_decision(key="revoke-replay-1"),
            auth_result=(owner, key),
        )
        assert first["data"].execution_status == ToolExecutionStatus.READY

        await APIKey.filter(id=key.id).update(is_active=False)

        with pytest.raises(BusinessError) as replay_error:
            await submit_approval_decision(
                request_id=request.id,
                payload=_decision(key="revoke-replay-1"),
                auth_result=(owner, key),
            )
        _assert_business_error(
            replay_error,
            code=ResponseCode.TOOL_APPROVAL_NOT_AUTHORIZED,
            status_code=403,
        )
        assert (
            await service.ToolApprovalDecision.filter(execution_id=execution.id).count()
            == 1
        )
        assert (
            await service.get_execution(execution.id)
        ).status == ToolExecutionStatus.READY


@pytest.mark.asyncio
async def test_decided_api_key_run_recovers_worker_with_the_original_key(monkeypatch):
    """decision -> queued marker -> worker restart keeps the API-key identity."""
    from app.api.v1.endpoints import chat_tools
    from app.services.agent_run_worker import _execute_approved_pending_tool
    from app.services.sandbox.gateway import sandbox_gateway
    from app.services.tool_context import current_tool_identity

    async with _database():
        owner = await _user("resume-key")
        team = await _team("resume-key-team", owner)
        agent = await _agent(team, "resume-key-agent")
        key = await _api_key(owner, agents=[agent])
        tool = await _tool(team)
        run = await _run(owner, agent, api_key_id=key.id, tool_name="ticket_close")
        execution = await _api_key_execution(
            owner=owner, team=team, tool=tool, run=run, key=key
        )

        decided = await submit_execution_decision(
            execution_id=execution.id,
            payload=_decision(key="resume-key-1"),
            auth_result=(owner, key),
        )
        assert decided["data"].execution_status == ToolExecutionStatus.READY

        queued = await AgentRun.get(id=run.id)
        assert queued.status == AgentRunStatus.QUEUED
        assert queued.worker_payload["resume_tool_approval"]["execution_id"] == str(
            execution.id
        )
        conversation = await Conversation.get(id=queued.conversation_id)

        async def _session(**_kwargs):
            return "session-1"

        monkeypatch.setattr(sandbox_gateway, "create_session", _session)
        observed = []

        async def fake_execute_call(tool_name, arguments, **kwargs):
            identity = current_tool_identity()
            assert identity is not None
            observed.append(identity)
            return {"ticket": "closed"}

        monkeypatch.setattr(chat_tools, "execute_tool_call", fake_execute_call)

        # Simulate a worker restart: a fresh process claims the queued run.
        queued.status = AgentRunStatus.RUNNING
        await queued.save(update_fields=["status"])
        payload = await _execute_approved_pending_tool(
            dict(queued.worker_payload or {}),
            run=queued,
            agent=agent,
            conversation=conversation,
        )

        assert payload is not None
        assert len(observed) == 1
        identity = observed[0]
        assert identity.api_key_id == key.id
        assert identity.entrypoint == ExecutionEntrypoint.API_KEY.value
        assert identity.entrypoint_id == str(key.id)
        assert identity.run_id == run.id
        assert identity.run_kind == ExecutionRunKind.AGENT.value
        assert identity.interactive is False
        result = payload["resume_tool_result"]
        assert result["is_error"] is False
        assert "closed" in result["result"]
        fresh_run = await AgentRun.get(id=run.id)
        assert fresh_run.api_key_id == key.id


@pytest.mark.asyncio
async def test_api_key_rejection_cancels_and_resumes_with_a_tool_error():
    """Reject is terminal for the key's own call and never executes the tool."""
    async with _database():
        owner = await _user("reject-key")
        team = await _team("reject-key-team", owner)
        agent = await _agent(team, "reject-key-agent")
        key = await _api_key(owner, agents=[agent])
        tool = await _tool(team)
        run = await _run(owner, agent, api_key_id=key.id)
        execution = await _api_key_execution(
            owner=owner, team=team, tool=tool, run=run, key=key
        )

        result = await submit_execution_decision(
            execution_id=execution.id,
            payload=_decision("reject", key="reject-key-1"),
            auth_result=(owner, key),
        )

        assert result["data"].execution_status == ToolExecutionStatus.CANCELLED
        fresh_execution = await service.get_execution(execution.id)
        assert fresh_execution.cancel_reason == (
            service.ToolExecutionCancelReason.REJECTED
        )
        fresh_run = await AgentRun.get(id=run.id)
        assert fresh_run.status == AgentRunStatus.QUEUED
        assert "resume_tool_approval" not in fresh_run.worker_payload
        resume = fresh_run.worker_payload["resume_tool_result"]
        assert resume["is_error"] is True
        assert "rejected" in resume["result"].lower()
        assert fresh_run.api_key_id == key.id
