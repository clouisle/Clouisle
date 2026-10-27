"""Behavior tests for tool approval visibility, decisions, expiry and policy.

Each test persists through the real approval service on an in-memory SQLite
Tortoise database; no ORM method is faked. The assertions focus on the
security-relevant outcomes: who may see/decide a gate, what a decision changes
in the database, and how expiry/cancellation reach a terminal state.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from tortoise import Tortoise

from app.models.tool import CustomToolType, Tool, ToolType
from app.models.user import Team, TeamMember, User
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.tool_approval import (
    ApprovalDecision,
    ApprovalRequestStatus,
    ApprovalVote,
    ExecutionEntrypoint,
    ExecutionRunKind,
    PolicyLayer,
    PolicySource,
    ToolApprovalPolicy,
    ToolExecutionCancelReason,
    ToolExecutionStatus,
)
from app.services import tool_approvals as service


@asynccontextmanager
async def _database():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        yield
    finally:
        await Tortoise.close_connections()


async def _user(label: str, *, is_active: bool = True) -> User:
    return await User.create(
        id=uuid4(),
        username=f"{label}_{uuid4().hex[:8]}",
        email=f"{label}_{uuid4().hex[:8]}@approval.test",
        hashed_password="x",
        is_active=is_active,
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


def _team_binding(*, version: int = 1, team_id=None, **overrides):
    values = {
        "connection_id": uuid4(),
        "team_id": team_id,
        "scope": "team",
        "owner_user_id": None,
        "effective_user_id": None,
        "secret_version": version,
        "status": "active",
        "is_active": True,
    }
    values.update(overrides)
    return type("Binding", (), values)()


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


async def _pending(execution_id):
    return await service.ToolApprovalRequest.filter(execution_id=execution_id).first()


def test_policy_normalization_and_evaluation_fail_closed():
    from app.schemas.tool_approval import PolicyEvaluation

    assert service.normalize_tool_approval_policy(None) == (
        service.default_tool_approval_policy()
    )
    assert service.normalize_tool_approval_policy({}) == (
        service.default_tool_approval_policy()
    )
    parsed = service.normalize_tool_approval_policy({"default_decision": "allow"})
    assert parsed.default_decision == ApprovalDecision.ALLOW
    same = service.normalize_tool_approval_policy(parsed)
    assert same is parsed

    with pytest.raises(service.PolicyConfigurationError):
        service.normalize_tool_approval_policy({"default_decision": "maybe"})
    with pytest.raises(service.PolicyConfigurationError):
        service.normalize_tool_approval_policy(["not", "a", "policy"])

    with pytest.raises(service.PolicyConfigurationError):
        service.evaluate_policy([], " ", entrypoint_interactive=True)
    with pytest.raises(service.PolicyConfigurationError):
        service.evaluate_policy([], "x" * 201, entrypoint_interactive=True)
    with pytest.raises(service.PolicyConfigurationError):
        service.evaluate_policy([], "read", entrypoint_interactive=True)

    allow_layer = PolicyLayer(
        source=PolicySource.TOOL,
        policy=ToolApprovalPolicy(default_decision=ApprovalDecision.ALLOW),
    )
    deny_layer = PolicyLayer(
        source=PolicySource.TEAM,
        policy=ToolApprovalPolicy(default_decision=ApprovalDecision.DENY),
    )
    denied = service.evaluate_policy(
        [allow_layer, deny_layer], "read", entrypoint_interactive=True
    )
    assert denied.decision == ApprovalDecision.DENY
    assert denied.gates == ()

    with pytest.raises(service.PolicyConfigurationError):
        service.evaluate_policy(
            [
                allow_layer,
                PolicyLayer(
                    source=PolicySource.TOOL,
                    policy=ToolApprovalPolicy(default_decision=ApprovalDecision.ALLOW),
                ),
            ],
            "read",
            entrypoint_interactive=True,
        )

    caller_layer = PolicyLayer(
        source=PolicySource.TOOL,
        policy=service.default_tool_approval_policy(),
        label="tool default",
    )
    unavailable = service.evaluate_policy(
        [caller_layer], "read", entrypoint_interactive=False
    )
    assert unavailable.configuration_error == "approval_audience_unavailable"
    assert unavailable.sources == ("tool default",)

    fingerprint = service.policy_hash(parsed)
    assert fingerprint == service.policy_hash(
        PolicyEvaluation(
            decision=ApprovalDecision.ALLOW,
            policy_hash=fingerprint,
        )
    )
    with pytest.raises(TypeError):
        service.policy_hash("not-a-policy")


@pytest.mark.asyncio
async def test_execution_visibility_is_actor_effective_principal_or_team_admin():
    async with _database():
        actor = await _user("visibility-actor")
        member = await _user("visibility-member")
        admin = await _user("visibility-admin")
        inactive = await _user("visibility-inactive", is_active=False)
        effective = await _user("visibility-effective")
        outsider = await _user("visibility-outsider")
        team = await _team("visibility-team", actor)
        await _add_member(team, member, "member")
        await _add_member(team, admin, "admin")
        tool = await _tool(team, _allow_policy())

        execution = await _execution(actor, team, tool)
        assert (await service.get_execution(execution.id)).id == execution.id
        with pytest.raises(BusinessError) as missing:
            await service.get_execution(uuid4())
        assert missing.value.code == ResponseCode.TOOL_EXECUTION_NOT_FOUND

        assert await service.can_view_execution(execution, actor) is True
        assert await service.can_view_execution(execution, admin) is True
        assert await service.can_view_execution(execution, member) is False
        assert await service.can_view_execution(execution, inactive) is False
        with pytest.raises(BusinessError) as denied:
            await service.get_execution_for_viewer(execution.id, member)
        assert denied.value.code == ResponseCode.TOOL_EXECUTION_ACCESS_DENIED

        binding = _team_binding(scope="user", owner_user_id=effective.id)
        binding.effective_user_id = effective.id
        bound = await _execution(
            actor,
            team,
            tool,
            connection_binding=binding,
        )
        assert bound.effective_user_id == effective.id
        assert await service.can_view_execution(bound, effective) is True
        assert await service.can_view_execution(bound, outsider) is False

        run_id = uuid4()
        deferred = await _execution(
            actor,
            team,
            tool,
            run_kind=ExecutionRunKind.AGENT,
            run_id=run_id,
            tool_call_id="call-1",
        )
        assert (
            await service.find_execution_by_tool_call(
                run_kind=ExecutionRunKind.AGENT,
                run_id=run_id,
                tool_call_id="call-1",
            )
        ).id == deferred.id
        assert (
            await service.find_execution_by_tool_call(
                run_kind=ExecutionRunKind.AGENT,
                run_id=run_id,
                tool_call_id="call-missing",
            )
            is None
        )

        run_rows = await service.list_run_executions(
            run_kind=ExecutionRunKind.AGENT,
            run_id=run_id,
        )
        assert [row.id for row in run_rows] == [deferred.id]
        filtered_rows = await service.list_run_executions(
            run_kind=ExecutionRunKind.AGENT,
            run_id=run_id,
            tool_call_id="call-1",
        )
        assert [row.id for row in filtered_rows] == [deferred.id]
        assert (
            await service.list_run_executions(
                run_kind=ExecutionRunKind.AGENT,
                run_id=run_id,
                tool_call_id="call-2",
            )
            == []
        )

        page, total = await service.list_executions_for_actor(
            actor, page=0, page_size=0
        )
        assert total == 3
        assert len(page) == 1
        everything, total = await service.list_executions_for_actor(
            actor, page=1, page_size=100
        )
        assert total == 3
        assert len(everything) == 3

        by_status, status_total = await service.list_executions_for_actor(
            actor,
            status=ToolExecutionStatus.READY,
            tool_id=tool.id,
        )
        assert status_total == 3
        assert all(row.status == ToolExecutionStatus.READY for row in by_status)

        by_run, run_total = await service.list_executions_for_actor(
            actor,
            run_kind=ExecutionRunKind.AGENT,
            run_id=run_id,
        )
        assert run_total == 1
        assert by_run[0].id == deferred.id

        with pytest.raises(BusinessError) as bad_run:
            await service.list_executions_for_actor(
                actor, run_kind=ExecutionRunKind.AGENT
            )
        assert bad_run.value.code == ResponseCode.TOOL_APPROVAL_INPUT_INVALID


@pytest.mark.asyncio
async def test_approval_request_view_is_audience_only_and_expiry_aware():
    async with _database():
        actor = await _user("view-actor")
        outsider = await _user("view-outsider")
        superuser = await _user("view-superuser")
        superuser.is_superuser = True
        await superuser.save(update_fields=["is_superuser"])
        team = await _team("view-team", actor)
        tool = await _tool(team, _caller_policy())
        execution = await _execution(actor, team, tool)
        request = await _pending(execution.id)
        assert request is not None

        visible = await service.get_approval_request_for_viewer(request.id, actor)
        assert visible.id == request.id

        for user in (outsider, superuser):
            with pytest.raises(BusinessError) as rejected:
                await service.get_approval_request_for_viewer(request.id, user)
            assert rejected.value.code == ResponseCode.TOOL_APPROVAL_NOT_AUTHORIZED

        actor.is_active = False
        await actor.save(update_fields=["is_active"])
        with pytest.raises(BusinessError) as inactive:
            await service.get_approval_request_for_viewer(request.id, actor)
        assert inactive.value.code == ResponseCode.TOOL_APPROVAL_NOT_AUTHORIZED
        actor.is_active = True
        await actor.save(update_fields=["is_active"])

        expired_at = execution.expires_at + timedelta(seconds=1)
        assert (
            await service.can_view_approval_request(
                request, execution, actor, now=expired_at
            )
            is False
        )

        await service.ToolExecution.filter(id=execution.id).update(
            status=ToolExecutionStatus.SUCCEEDED
        )
        terminal = await service.get_execution(execution.id)
        assert (
            await service.can_view_approval_request(
                request, terminal, actor, now=expired_at
            )
            is True
        )

        with pytest.raises(BusinessError) as missing:
            await service.get_approval_request_for_viewer(uuid4(), actor)
        assert missing.value.code == ResponseCode.TOOL_APPROVAL_REQUEST_NOT_FOUND


@pytest.mark.asyncio
async def test_pending_inbox_filters_expiry_status_and_paginates():
    async with _database():
        actor = await _user("inbox-actor")
        outsider = await _user("inbox-outsider")
        team = await _team("inbox-team", actor)
        tool = await _tool(team, _caller_policy())

        executions = [await _execution(actor, team, tool) for _ in range(3)]
        page, total = await service.list_pending_approvals_for_user(
            actor, page=2, page_size=2
        )
        assert total == 3
        assert len(page) == 1

        clamped, clamped_total = await service.list_pending_approvals_for_user(
            actor, page=0, page_size=0
        )
        assert clamped_total == 3
        assert len(clamped) == 3

        first_request = await _pending(executions[0].id)
        await service.ToolApprovalRequest.filter(id=first_request.id).update(
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)
        )
        _, weekly_total = await service.list_pending_approvals_for_user(actor)
        assert weekly_total == 2

        await service.ToolExecution.filter(id=executions[1].id).update(
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)
        )
        _, unexpired_total = await service.list_pending_approvals_for_user(actor)
        assert unexpired_total == 1

        await service.ToolExecution.filter(id=executions[2].id).update(
            status=ToolExecutionStatus.READY
        )
        assert await service.list_pending_approvals_for_user(actor) == ([], 0)

        _, outsider_total = await service.list_pending_approvals_for_user(outsider)
        assert outsider_total == 0


@pytest.mark.asyncio
async def test_decisions_reject_expiry_and_invalid_payloads():
    async with _database():
        actor = await _user("expiry-actor")
        team = await _team("expiry-team", actor)
        tool = await _tool(team, _caller_policy())
        now = datetime.now(timezone.utc)
        execution = await _execution(
            actor,
            team,
            tool,
            now=now,
            expires_at=now + timedelta(seconds=30),
        )
        request = await _pending(execution.id)

        with pytest.raises(BusinessError) as expired:
            await service.decide_approval(
                request.id,
                actor,
                decision=ApprovalVote.APPROVE,
                idempotency_key="expired-key",
                now=now + timedelta(seconds=31),
            )
        assert expired.value.code == ResponseCode.TOOL_APPROVAL_EXPIRED
        refreshed = await service.get_execution(execution.id)
        assert refreshed.status == ToolExecutionStatus.CANCELLED
        assert refreshed.cancel_reason == ToolExecutionCancelReason.EXPIRED
        refreshed_request = await service.ToolApprovalRequest.get(id=request.id)
        assert refreshed_request.status == ApprovalRequestStatus.EXPIRED
        assert await service.ToolApprovalDecision.all().count() == 0

        with pytest.raises(BusinessError) as already_expired:
            await service.decide_approval(
                request.id,
                actor,
                decision=ApprovalVote.APPROVE,
                idempotency_key="expired-again",
                now=now + timedelta(seconds=32),
            )
        assert already_expired.value.code == ResponseCode.TOOL_APPROVAL_EXPIRED

        late_request_execution = await _execution(actor, team, tool, now=now)
        late_request = await _pending(late_request_execution.id)
        await service.ToolApprovalRequest.filter(id=late_request.id).update(
            expires_at=now - timedelta(seconds=1)
        )
        with pytest.raises(BusinessError) as request_expired:
            await service.decide_approval(
                late_request.id,
                actor,
                decision=ApprovalVote.APPROVE,
                idempotency_key="request-expired",
                now=now,
            )
        assert request_expired.value.code == ResponseCode.TOOL_APPROVAL_EXPIRED

        status_request_execution = await _execution(actor, team, tool, now=now)
        status_request = await _pending(status_request_execution.id)
        await service.ToolApprovalRequest.filter(id=status_request.id).update(
            status=ApprovalRequestStatus.EXPIRED,
            resolved_at=now,
        )
        with pytest.raises(BusinessError):
            await service.decide_approval(
                status_request.id,
                actor,
                decision=ApprovalVote.APPROVE,
                idempotency_key="status-expired",
                now=now,
            )
        assert (
            await service.get_execution(status_request_execution.id)
        ).status == ToolExecutionStatus.CANCELLED

        pending_execution = await _execution(actor, team, tool, now=now)
        pending_request = await _pending(pending_execution.id)
        for kwargs in [
            {
                "decision": "maybe",
                "idempotency_key": "bad-decision",
            },
            {
                "decision": ApprovalVote.APPROVE,
                "idempotency_key": "",
            },
            {
                "decision": ApprovalVote.APPROVE,
                "idempotency_key": "x" * 129,
            },
            {
                "decision": ApprovalVote.APPROVE,
                "idempotency_key": "long-reason",
                "reason": "x" * 2001,
            },
        ]:
            with pytest.raises(BusinessError) as invalid:
                await service.decide_approval(
                    pending_request.id, actor, now=now, **kwargs
                )
            assert invalid.value.code == ResponseCode.TOOL_APPROVAL_INPUT_INVALID

        with pytest.raises(BusinessError) as missing:
            await service.decide_approval(
                uuid4(),
                actor,
                decision=ApprovalVote.APPROVE,
                idempotency_key="missing-request",
                now=now,
            )
        assert missing.value.code == ResponseCode.TOOL_APPROVAL_REQUEST_NOT_FOUND

        actor.is_active = False
        await actor.save(update_fields=["is_active"])
        with pytest.raises(BusinessError) as unauthorized:
            await service.decide_approval(
                pending_request.id,
                actor,
                decision=ApprovalVote.APPROVE,
                idempotency_key="inactive-approver",
                now=now,
            )
        assert unauthorized.value.code == ResponseCode.TOOL_APPROVAL_NOT_AUTHORIZED
        actor.is_active = True
        await actor.save(update_fields=["is_active"])


@pytest.mark.asyncio
async def test_decisions_cover_binding_drift_and_rejection():
    async with _database():
        actor = await _user("decision-flow-actor")
        team = await _team("decision-flow-team", actor)
        tool = await _tool(team, _caller_policy())
        now = datetime.now(timezone.utc)

        drifted = await _execution(actor, team, tool, now=now)
        drifted_request = await _pending(drifted.id)
        await service.ToolExecution.filter(id=drifted.id).update(binding_hash="0" * 64)
        with pytest.raises(BusinessError) as binding:
            await service.decide_approval(
                drifted_request.id,
                actor,
                decision=ApprovalVote.APPROVE,
                idempotency_key="binding-drift",
                now=now,
            )
        assert binding.value.code == ResponseCode.TOOL_APPROVAL_BINDING_CHANGED
        drifted_row = await service.get_execution(drifted.id)
        assert drifted_row.status == ToolExecutionStatus.CANCELLED
        assert drifted_row.cancel_reason == ToolExecutionCancelReason.BINDING_CHANGED
        drifted_gate = await service.ToolApprovalRequest.get(id=drifted_request.id)
        assert drifted_gate.status == ApprovalRequestStatus.CANCELLED
        assert await service.ToolApprovalDecision.all().count() == 0

        rejected = await _execution(actor, team, tool, now=now)
        rejected_request = await _pending(rejected.id)
        decision = await service.decide_approval(
            rejected_request.id,
            actor,
            decision=ApprovalVote.REJECT,
            idempotency_key="reject-key",
            reason="  not allowed \x00here  ",
            now=now,
        )
        assert decision.decision == ApprovalVote.REJECT
        assert decision.reason == "not allowed here"
        rejected_row = await service.get_execution(rejected.id)
        assert rejected_row.status == ToolExecutionStatus.CANCELLED
        assert rejected_row.cancel_reason == ToolExecutionCancelReason.REJECTED
        assert (
            await service.ToolApprovalRequest.get(id=rejected_request.id)
        ).status == ApprovalRequestStatus.REJECTED


@pytest.mark.asyncio
async def test_expiry_and_cancellation_guard_terminal_states():
    async with _database():
        owner = await _user("cancel-owner")
        member = await _user("cancel-member")
        admin = await _user("cancel-admin")
        team = await _team("cancel-team", owner)
        await _add_member(team, member, "member")
        await _add_member(team, admin, "admin")
        tool = await _tool(team, _caller_policy())
        allow_tool = await _tool(team, _allow_policy())
        now = datetime.now(timezone.utc)

        with pytest.raises(BusinessError) as missing:
            await service.expire_execution(uuid4(), now=now)
        assert missing.value.code == ResponseCode.TOOL_EXECUTION_NOT_FOUND

        ready = await _execution(
            owner,
            team,
            allow_tool,
            now=now,
            expires_at=now + timedelta(minutes=5),
        )
        assert await service.expire_execution(ready.id, now=now) is False
        claimed = await service.claim_execution(
            ready.id,
            claim_token="cancel-claim",
            tool_definition_version=allow_tool.definition_version,
            now=now,
        )
        assert claimed.status == ToolExecutionStatus.EXECUTING
        assert (
            await service.expire_execution(ready.id, now=now + timedelta(minutes=6))
            is False
        )

        expiring = await _execution(
            owner,
            team,
            tool,
            now=now,
            expires_at=now + timedelta(seconds=30),
        )
        assert (
            await service.expire_execution(expiring.id, now=now + timedelta(seconds=31))
            is True
        )
        expired_row = await service.get_execution(expiring.id)
        assert expired_row.status == ToolExecutionStatus.CANCELLED
        assert expired_row.cancel_reason == ToolExecutionCancelReason.EXPIRED
        assert (await _pending(expiring.id)).status == ApprovalRequestStatus.EXPIRED

        assert await service.expire_due_executions(limit=0, now=now) == 0
        due_a = await _execution(
            owner, team, tool, now=now, expires_at=now + timedelta(seconds=1)
        )
        due_b = await _execution(
            owner, team, tool, now=now, expires_at=now + timedelta(seconds=2)
        )
        assert (
            await service.expire_due_executions(
                limit=10, now=now + timedelta(seconds=3)
            )
            == 2
        )
        assert (
            await service.get_execution(due_a.id)
        ).status == ToolExecutionStatus.CANCELLED
        assert (
            await service.get_execution(due_b.id)
        ).status == ToolExecutionStatus.CANCELLED

        with pytest.raises(BusinessError) as bad_reason:
            await service.cancel_execution(
                due_a.id, reason=ToolExecutionCancelReason.EXPIRED
            )
        assert bad_reason.value.code == ResponseCode.TOOL_APPROVAL_INPUT_INVALID
        with pytest.raises(BusinessError) as missing_cancel:
            await service.cancel_execution(uuid4())
        assert missing_cancel.value.code == ResponseCode.TOOL_EXECUTION_NOT_FOUND

        cancellable = await _execution(owner, team, allow_tool, now=now)
        with pytest.raises(BusinessError) as unauthorized:
            await service.cancel_execution(cancellable.id, actor_user_id=member.id)
        assert unauthorized.value.code == ResponseCode.TOOL_EXECUTION_ACCESS_DENIED

        cancelled = await service.cancel_execution(
            cancellable.id,
            actor_user_id=admin.id,
            now=now,
        )
        assert cancelled.status == ToolExecutionStatus.CANCELLED
        assert cancelled.cancel_reason == ToolExecutionCancelReason.CANCELLED
        again = await service.cancel_execution(cancellable.id, now=now)
        assert again.status == ToolExecutionStatus.CANCELLED

        executing = await _execution(owner, team, allow_tool, now=now)
        await service.claim_execution(
            executing.id,
            claim_token="executing-claim",
            tool_definition_version=allow_tool.definition_version,
            now=now,
        )
        with pytest.raises(BusinessError) as invalid_state:
            await service.cancel_execution(executing.id, now=now)
        assert invalid_state.value.code == ResponseCode.TOOL_EXECUTION_INVALID_STATE

        run_id = uuid4()
        run_tool = await _tool(team, _allow_policy())
        run_a = await _execution(
            owner,
            team,
            run_tool,
            now=now,
            run_kind=ExecutionRunKind.AGENT,
            run_id=run_id,
        )
        run_b = await _execution(
            owner,
            team,
            run_tool,
            now=now,
            run_kind=ExecutionRunKind.AGENT,
            run_id=run_id,
        )
        unrelated = await _execution(owner, team, allow_tool, now=now)
        with pytest.raises(BusinessError) as run_reason:
            await service.cancel_pending_for_run(
                run_kind=ExecutionRunKind.AGENT,
                run_id=run_id,
                reason=ToolExecutionCancelReason.EXPIRED,
            )
        assert run_reason.value.code == ResponseCode.TOOL_APPROVAL_INPUT_INVALID

        assert (
            await service.cancel_pending_for_run(
                run_kind=ExecutionRunKind.AGENT,
                run_id=run_id,
                limit=1,
            )
            == 1
        )
        assert (
            await service.cancel_pending_for_run(
                run_kind=ExecutionRunKind.AGENT,
                run_id=run_id,
                limit=0,
            )
            == 1
        )
        for row in (run_a, run_b):
            assert (
                await service.get_execution(row.id)
            ).status == ToolExecutionStatus.CANCELLED
        assert (
            await service.get_execution(unrelated.id)
        ).status == ToolExecutionStatus.READY


@pytest.mark.asyncio
async def test_create_execution_validation_and_binding_guards():
    async with _database():
        owner = await _user("create-owner")
        outsider = await _user("create-outsider")
        inactive = await _user("create-inactive", is_active=False)
        other = await _user("create-other")
        team = await _team("create-team", owner)
        other_team = await _team("create-other-team", other)
        tool = await _tool(team, _allow_policy())
        disabled = await _tool(team, _allow_policy())
        disabled.is_enabled = False
        await disabled.save(update_fields=["is_enabled"])
        now = datetime.now(timezone.utc)

        with pytest.raises(BusinessError) as inactive_actor:
            await _execution(inactive, team, tool, now=now)
        assert inactive_actor.value.code == ResponseCode.TOOL_EXECUTION_ACCESS_DENIED

        with pytest.raises(BusinessError) as disabled_tool:
            await _execution(owner, team, disabled, now=now)
        assert disabled_tool.value.code == ResponseCode.TOOL_EXECUTION_ACCESS_DENIED

        with pytest.raises(BusinessError) as not_member:
            await _execution(outsider, team, tool, now=now)
        assert not_member.value.code == ResponseCode.TOOL_EXECUTION_ACCESS_DENIED

        for operation in ("   ", "x" * 201, "bad\x01op"):
            with pytest.raises(BusinessError) as bad_operation:
                await _execution(owner, team, tool, operation=operation, now=now)
            assert bad_operation.value.code == (
                ResponseCode.TOOL_APPROVAL_INPUT_INVALID
            )

        with pytest.raises(BusinessError) as bad_run:
            await _execution(
                owner, team, tool, run_kind=ExecutionRunKind.AGENT, now=now
            )
        assert bad_run.value.code == ResponseCode.TOOL_APPROVAL_INPUT_INVALID
        with pytest.raises(BusinessError) as bad_call:
            await _execution(owner, team, tool, tool_call_id="call-1", now=now)
        assert bad_call.value.code == ResponseCode.TOOL_APPROVAL_INPUT_INVALID

        with pytest.raises(BusinessError) as long_entrypoint:
            await _execution(owner, team, tool, entrypoint_id="x" * 201, now=now)
        assert long_entrypoint.value.code == ResponseCode.TOOL_APPROVAL_INPUT_INVALID
        with pytest.raises(BusinessError) as long_label:
            await _execution(
                owner,
                team,
                tool,
                connection_account_label="x" * 151,
                now=now,
            )
        assert long_label.value.code == ResponseCode.TOOL_APPROVAL_INPUT_INVALID

        with pytest.raises(BusinessError) as non_interactive:
            await _execution(
                owner,
                team,
                tool,
                entrypoint=ExecutionEntrypoint.API_KEY,
                now=now,
            )
        assert non_interactive.value.code == (ResponseCode.TOOL_APPROVAL_INPUT_INVALID)

        with pytest.raises(service.PolicyConfigurationError):
            await _execution(
                owner,
                team,
                tool,
                policy={"default_decision": "maybe"},
                now=now,
            )

        duplicate_layer = PolicyLayer(
            source=PolicySource.TEAM,
            policy=ToolApprovalPolicy(default_decision=ApprovalDecision.ALLOW),
        )
        with pytest.raises(BusinessError) as duplicate_layers:
            await _execution(
                owner,
                team,
                tool,
                policy_layers=(duplicate_layer, duplicate_layer),
                now=now,
            )
        assert duplicate_layers.value.code == (
            ResponseCode.TOOL_APPROVAL_POLICY_CONFIGURATION_REQUIRED
        )

        with pytest.raises(BusinessError) as no_audience:
            await _execution(
                owner,
                team,
                tool,
                policy=_caller_policy(),
                entrypoint=ExecutionEntrypoint.API_KEY,
                entrypoint_id="key-1",
                now=now,
            )
        assert no_audience.value.code == (
            ResponseCode.TOOL_APPROVAL_POLICY_CONFIGURATION_REQUIRED
        )

        with pytest.raises(BusinessError) as bad_version:
            await _execution(owner, team, tool, tool_definition_version=0, now=now)
        assert bad_version.value.code == ResponseCode.TOOL_APPROVAL_INPUT_INVALID

        with pytest.raises(BusinessError) as bad_binding:
            await _execution(
                owner,
                team,
                tool,
                connection_binding=_team_binding(scope="galaxy"),
                now=now,
            )
        assert bad_binding.value.code == ResponseCode.TOOL_APPROVAL_INPUT_INVALID

        with pytest.raises(BusinessError) as foreign_binding:
            await _execution(
                owner,
                team,
                tool,
                connection_binding=_team_binding(team_id=other_team.id),
                now=now,
            )
        assert foreign_binding.value.code == ResponseCode.TOOL_EXECUTION_ACCESS_DENIED

        user_binding = _team_binding(
            scope="user",
            team_id=team.id,
            owner_user_id=other.id,
        )
        user_binding.effective_user_id = other.id
        with pytest.raises(BusinessError) as identity_mismatch:
            await _execution(
                owner,
                team,
                tool,
                connection_binding=user_binding,
                effective_user_id=owner.id,
                now=now,
            )
        assert identity_mismatch.value.code == (
            ResponseCode.TOOL_EXECUTION_ACCESS_DENIED
        )

        with pytest.raises(BusinessError) as no_connection_identity:
            await _execution(owner, team, tool, effective_user_id=other.id, now=now)
        assert no_connection_identity.value.code == (
            ResponseCode.TOOL_EXECUTION_ACCESS_DENIED
        )

        with pytest.raises(BusinessError) as past_expiry:
            await _execution(
                owner, team, tool, expires_at=now - timedelta(seconds=1), now=now
            )
        assert past_expiry.value.code == ResponseCode.TOOL_APPROVAL_INPUT_INVALID
        with pytest.raises(BusinessError) as far_expiry:
            await _execution(
                owner,
                team,
                tool,
                expires_at=now + timedelta(days=31),
                now=now,
            )
        assert far_expiry.value.code == ResponseCode.TOOL_APPROVAL_INPUT_INVALID
