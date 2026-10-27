"""Behavior tests for the tool approval and execution HTTP handlers.

Handlers are invoked directly against a real in-memory database so the tests
observe the same service calls, persisted decisions and dispatch side effects
the routes perform (including the best-effort resume dispatch contract).
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
from app.services import agent_run_store
from app.services import tool_approvals as service


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


async def _add_member(team: Team, user: User, role: str) -> None:
    await TeamMember.create(id=uuid4(), team_id=team.id, user_id=user.id, role=role)


async def _tool(team: Team, policy: dict) -> Tool:
    return await Tool.create(
        id=uuid4(),
        team_id=team.id,
        name=f"tool_{uuid4().hex[:8]}",
        display_name="Approval tool",
        description="behavior test",
        type=ToolType.CUSTOM,
        custom_type=CustomToolType.HTTP,
        approval_policy=policy,
    )


def _caller_policy() -> dict:
    return {"default_decision": "require_approval", "gates": [{"kind": "caller"}]}


def _allow_policy() -> dict:
    return {"default_decision": "allow"}


async def _execution(actor: User, team: Team, tool: Tool, **kwargs):
    params = {
        "tool": tool,
        "operation": "ticket.close",
        "parameters": {"ticket": "T-1"},
        "actor": actor,
        "team_id": team.id,
        "entrypoint": ExecutionEntrypoint.CHAT,
    }
    params.update(kwargs)
    return await service.create_execution(**params)


async def _pending_request(execution_id):
    return await service.ToolApprovalRequest.filter(
        execution_id=execution_id,
        status=ApprovalRequestStatus.PENDING,
    ).first()


@pytest.mark.asyncio
async def test_approval_inbox_and_detail_endpoints_are_viewer_scoped():
    async with _database():
        actor = await _user("api-inbox-actor")
        outsider = await _user("api-inbox-outsider")
        team = await _team("api-inbox-team", actor)
        tool = await _tool(team, _caller_policy())
        execution = await _execution(actor, team, tool)
        request = await _pending_request(execution.id)

        listing = await list_pending_approval_requests(
            page=1, page_size=20, current_user=actor
        )
        page = listing["data"]
        assert page.total == 1
        assert page.page == 1
        assert page.page_size == 20
        assert [item.id for item in page.items] == [request.id]
        assert page.items[0].execution_id == execution.id

        detail = await get_approval_request(request_id=request.id, current_user=actor)
        assert detail["data"].id == request.id
        assert detail["data"].stage_key == "caller"

        outsider_page = await list_pending_approval_requests(
            page=1, page_size=20, current_user=outsider
        )
        assert outsider_page["data"].total == 0

        with pytest.raises(BusinessError) as hidden:
            await get_approval_request(request_id=request.id, current_user=outsider)
        assert hidden.value.code == ResponseCode.TOOL_APPROVAL_NOT_AUTHORIZED


@pytest.mark.asyncio
async def test_submit_decision_reports_remaining_gates_and_dispatch_failures(
    monkeypatch,
):
    async with _database():
        actor = await _user("api-decide-actor")
        team = await _team("api-decide-team", actor)
        tool = await _tool(team, _caller_policy())

        scheduled: list[str] = []

        async def record(execution):
            scheduled.append(str(execution.id))
            return None

        monkeypatch.setattr(
            agent_run_store, "schedule_agent_run_approval_resume", record
        )

        agent_execution = await _execution(
            actor,
            team,
            tool,
            run_kind=ExecutionRunKind.AGENT,
            run_id=uuid4(),
        )
        agent_request = await _pending_request(agent_execution.id)
        result = await submit_approval_decision(
            request_id=agent_request.id,
            payload=ToolApprovalDecisionIn(
                decision=ApprovalVote.APPROVE,
                idempotency_key="api-agent-approve",
            ),
            current_user=actor,
        )
        assert result["data"].execution_status == ToolExecutionStatus.READY
        assert result["data"].remaining_approvals == 0
        assert result["data"].decision.decision == ApprovalVote.APPROVE
        assert scheduled.count(str(agent_execution.id)) >= 1
        assert set(scheduled) == {str(agent_execution.id)}
        assert (
            await service.get_execution(agent_execution.id)
        ).status == ToolExecutionStatus.READY

        async def explode(_execution):
            raise RuntimeError("broker down")

        monkeypatch.setattr(
            agent_run_store, "schedule_agent_run_approval_resume", explode
        )
        failure_execution = await _execution(
            actor,
            team,
            tool,
            run_kind=ExecutionRunKind.AGENT,
            run_id=uuid4(),
        )
        failure_request = await _pending_request(failure_execution.id)
        failure_result = await submit_approval_decision(
            request_id=failure_request.id,
            payload=ToolApprovalDecisionIn(
                decision=ApprovalVote.APPROVE,
                idempotency_key="api-agent-dispatch-failure",
            ),
            current_user=actor,
        )
        assert failure_result["data"].execution_status == ToolExecutionStatus.READY
        assert (
            await service.get_execution(failure_execution.id)
        ).status == ToolExecutionStatus.READY


@pytest.mark.asyncio
async def test_execution_listing_and_detail_endpoints_are_actor_scoped():
    async with _database():
        actor = await _user("api-list-actor")
        teammate = await _user("api-list-teammate")
        admin = await _user("api-list-admin")
        team = await _team("api-list-team", actor)
        await _add_member(team, teammate, "member")
        await _add_member(team, admin, "admin")
        tool = await _tool(team, _allow_policy())

        mine = await _execution(actor, team, tool)
        run_id = uuid4()
        deferred = await _execution(
            actor,
            team,
            tool,
            run_kind=ExecutionRunKind.AGENT,
            run_id=run_id,
        )
        theirs = await _execution(teammate, team, tool)

        listing = await list_my_executions(
            page=1,
            page_size=20,
            status=None,
            tool_id=None,
            run_kind=None,
            run_id=None,
            current_user=actor,
        )
        assert listing["data"].total == 2
        assert {item.id for item in listing["data"].items} == {mine.id, deferred.id}

        filtered = await list_my_executions(
            page=1,
            page_size=20,
            status=ToolExecutionStatus.READY,
            tool_id=tool.id,
            run_kind=ExecutionRunKind.AGENT,
            run_id=run_id,
            current_user=actor,
        )
        assert filtered["data"].total == 1
        assert filtered["data"].items[0].id == deferred.id

        with pytest.raises(BusinessError) as bad_run:
            await list_my_executions(
                page=1,
                page_size=20,
                status=None,
                tool_id=None,
                run_kind=ExecutionRunKind.AGENT,
                run_id=None,
                current_user=actor,
            )
        assert bad_run.value.code == ResponseCode.TOOL_APPROVAL_INPUT_INVALID

        detail = await get_my_execution(execution_id=mine.id, current_user=actor)
        assert detail["data"].id == mine.id

        own = await get_my_execution(execution_id=theirs.id, current_user=teammate)
        assert own["data"].id == theirs.id

        admin_view = await get_my_execution(execution_id=theirs.id, current_user=admin)
        assert admin_view["data"].id == theirs.id

        actor_view = await get_my_execution(execution_id=theirs.id, current_user=actor)
        assert actor_view["data"].id == theirs.id

        outsider = await _user("api-list-outsider")
        with pytest.raises(BusinessError) as denied:
            await get_my_execution(execution_id=theirs.id, current_user=outsider)
        assert denied.value.code == ResponseCode.TOOL_EXECUTION_ACCESS_DENIED

        with pytest.raises(BusinessError) as missing:
            await get_my_execution(execution_id=uuid4(), current_user=actor)
        assert missing.value.code == ResponseCode.TOOL_EXECUTION_NOT_FOUND


@pytest.mark.asyncio
async def test_execution_decision_endpoint_decides_pending_gate(
    monkeypatch,
):
    async with _database():
        actor = await _user("api-exec-actor")
        outsider = await _user("api-exec-outsider")
        team = await _team("api-exec-team", actor)
        tool = await _tool(team, _caller_policy())

        awaiting = await _execution(actor, team, tool)
        result = await submit_execution_decision(
            execution_id=awaiting.id,
            payload=ToolApprovalDecisionIn(
                decision=ApprovalVote.APPROVE,
                idempotency_key="api-exec-approve",
            ),
            current_user=actor,
        )
        assert result["data"].execution_status == ToolExecutionStatus.READY
        assert result["data"].remaining_approvals == 0
        refreshed = await service.get_execution(awaiting.id)
        assert refreshed.status == ToolExecutionStatus.READY

        with pytest.raises(BusinessError) as no_pending:
            await submit_execution_decision(
                execution_id=awaiting.id,
                payload=ToolApprovalDecisionIn(
                    decision=ApprovalVote.APPROVE,
                    idempotency_key="api-exec-approve-again",
                ),
                current_user=actor,
            )
        assert no_pending.value.code == (ResponseCode.TOOL_APPROVAL_REQUEST_NOT_FOUND)

        with pytest.raises(BusinessError) as not_visible:
            await submit_execution_decision(
                execution_id=awaiting.id,
                payload=ToolApprovalDecisionIn(
                    decision=ApprovalVote.APPROVE,
                    idempotency_key="api-exec-outsider",
                ),
                current_user=outsider,
            )
        assert not_visible.value.code == ResponseCode.TOOL_EXECUTION_ACCESS_DENIED

        allow_tool = await _tool(team, _allow_policy())
        already_ready = await _execution(actor, team, allow_tool)
        with pytest.raises(BusinessError) as allow_no_gate:
            await submit_execution_decision(
                execution_id=already_ready.id,
                payload=ToolApprovalDecisionIn(
                    decision=ApprovalVote.APPROVE,
                    idempotency_key="api-exec-ready",
                ),
                current_user=actor,
            )
        assert allow_no_gate.value.code == (
            ResponseCode.TOOL_APPROVAL_REQUEST_NOT_FOUND
        )

        async def explode(_execution):
            raise RuntimeError("dispatch unavailable")

        monkeypatch.setattr(
            agent_run_store, "schedule_agent_run_approval_resume", explode
        )
        agent_execution = await _execution(
            actor,
            team,
            tool,
            run_kind=ExecutionRunKind.AGENT,
            run_id=uuid4(),
        )
        agent_result = await submit_execution_decision(
            execution_id=agent_execution.id,
            payload=ToolApprovalDecisionIn(
                decision=ApprovalVote.REJECT,
                reason="not in this run",
                idempotency_key="api-exec-reject",
            ),
            current_user=actor,
        )
        assert agent_result["data"].execution_status == (ToolExecutionStatus.CANCELLED)
        assert agent_result["data"].decision.decision == ApprovalVote.REJECT
        rejected = await service.get_execution(agent_execution.id)
        assert rejected.status == ToolExecutionStatus.CANCELLED
