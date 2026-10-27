"""Behavioral SQLite smoke tests for tool execution approvals.

These tests use a real in-memory SQLite Tortoise database (no ORM fakes) to
exercise policy composition, durable approval transitions, claim exclusivity
and binding comparisons end to end.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from tortoise import Tortoise

from app.models.tool import CustomToolType, Tool, ToolType
from app.models.user import Team, TeamMember, User
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.tool_approval import (
    ApprovalDecision,
    ApprovalGate,
    ApprovalGateKind,
    ApprovalVote,
    ExecutionEntrypoint,
    PolicyLayer,
    PolicySource,
    ToolApprovalPolicy,
    ToolExecutionCancelReason,
    ToolExecutionOut,
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
    return {
        "default_decision": "require_approval",
        "gates": [{"kind": "caller"}],
    }


def _allow_policy() -> dict:
    return {"default_decision": "allow"}


def _team_binding(*, version: int = 1, **overrides):
    values = {
        "connection_id": uuid4(),
        "team_id": None,
        "scope": "team",
        "owner_user_id": None,
        "effective_user_id": None,
        "secret_version": version,
        "status": "active",
        "is_active": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_caller_approval_moves_execution_to_ready_without_leaking_secrets():
    async with _database():
        actor = await _user("caller")
        team = await _team("caller-team", actor)
        tool = await _tool(team, _caller_policy())

        execution = await service.create_execution(
            tool=tool,
            operation="todo.delete",
            parameters={"id": 7, "password": "super-secret"},
            actor=actor,
            team_id=team.id,
            entrypoint=ExecutionEntrypoint.CHAT,
            sensitive_fields=["password"],
        )
        assert execution.status == ToolExecutionStatus.AWAITING_APPROVAL
        assert execution.parameters_preview["password"] == "***REDACTED***"
        assert "super-secret" not in str(execution.parameters_preview)
        assert "super-secret" not in str(execution.parameters_cipher)

        dto = ToolExecutionOut.model_validate(execution).model_dump(mode="json")
        assert "parameters_cipher" not in dto
        assert "claim_token" not in dto
        assert dto["parameters_preview"]["password"] == "***REDACTED***"

        pending, total = await service.list_pending_approvals_for_user(actor)
        assert total == 1
        assert pending[0].execution_id == execution.id
        assert pending[0].stage_key == "caller"

        decision = await service.decide_approval(
            pending[0].id,
            actor,
            decision=ApprovalVote.APPROVE,
            idempotency_key="caller-approve-1",
        )
        assert decision.decision == ApprovalVote.APPROVE

        refreshed = await service.get_execution(execution.id)
        assert refreshed.status == ToolExecutionStatus.READY
        assert await service.list_pending_approvals_for_user(actor) == ([], 0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "gate",
    [
        ApprovalGate(kind=ApprovalGateKind.TEAM_ROLE, roles=("admin",)),
        ApprovalGate(kind=ApprovalGateKind.USER, user_ids=(uuid4(),)),
    ],
    ids=["team_role", "user"],
)
async def test_legacy_external_audiences_are_rejected_before_execution(gate):
    async with _database():
        actor = await _user("external-actor")
        team = await _team("external-team", actor)
        tool = await _tool(team, _allow_policy())
        layer = PolicyLayer(
            source=PolicySource.TEAM,
            policy=ToolApprovalPolicy(
                default_decision=ApprovalDecision.REQUIRE_APPROVAL,
                gates=(gate,),
            ),
        )

        with pytest.raises(BusinessError) as config_error:
            await service.create_execution(
                tool=tool,
                operation="ticket.read",
                parameters={"ticket_id": "T-1"},
                actor=actor,
                team_id=team.id,
                entrypoint=ExecutionEntrypoint.CHAT,
                policy_layers=(layer,),
            )

        assert (
            config_error.value.code
            == ResponseCode.TOOL_APPROVAL_POLICY_CONFIGURATION_REQUIRED
        )
        assert await service.ToolExecution.all().count() == 0
        assert await service.ToolApprovalRequest.all().count() == 0
        assert await service.ToolApprovalDecision.all().count() == 0


@pytest.mark.asyncio
async def test_deny_and_exact_operation_overrides_compose_with_mandatory_layers():
    async with _database():
        actor = await _user("override")
        team = await _team("override-team", actor)
        tool = await _tool(
            team,
            {
                "default_decision": "require_approval",
                "gates": [{"kind": "caller"}],
                "operation_overrides": {
                    "read": {"default_decision": "allow"},
                    "delete": {"default_decision": "deny"},
                },
            },
        )

        allowed = await service.create_execution(
            tool=tool,
            operation="read",
            parameters={},
            actor=actor,
            team_id=team.id,
            entrypoint=ExecutionEntrypoint.CHAT,
        )
        assert allowed.status == ToolExecutionStatus.READY

        denied = await service.create_execution(
            tool=tool,
            operation="delete",
            parameters={},
            actor=actor,
            team_id=team.id,
            entrypoint=ExecutionEntrypoint.CHAT,
        )
        assert denied.status == ToolExecutionStatus.CANCELLED
        assert denied.cancel_reason == ToolExecutionCancelReason.POLICY_DENIED

        mandatory = PolicyLayer(
            source=PolicySource.TEAM,
            policy=ToolApprovalPolicy(
                default_decision=ApprovalDecision.REQUIRE_APPROVAL,
                gates=(ApprovalGate(kind=ApprovalGateKind.CALLER),),
            ),
        )
        still_requires_approval = await service.create_execution(
            tool=tool,
            operation="read",
            parameters={},
            actor=actor,
            team_id=team.id,
            entrypoint=ExecutionEntrypoint.CHAT,
            policy_layers=(mandatory,),
        )
        assert still_requires_approval.status == ToolExecutionStatus.AWAITING_APPROVAL
        pending, total = await service.list_pending_approvals_for_user(actor)
        assert total == 1
        assert pending[0].execution_id == still_requires_approval.id


@pytest.mark.asyncio
async def test_claim_rejects_stale_connection_binding_and_never_executes_twice():
    async with _database():
        actor = await _user("claimer")
        team = await _team("claim-team", actor)
        tool = await _tool(team, _allow_policy())
        binding = _team_binding(team_id=team.id)

        execution = await service.create_execution(
            tool=tool,
            operation="mail.send",
            parameters={"to": "a@example.test"},
            actor=actor,
            team_id=team.id,
            entrypoint=ExecutionEntrypoint.API_KEY,
            entrypoint_id="key-1",
            connection_binding=binding,
            connection_account_label="team-mailer",
        )
        assert execution.status == ToolExecutionStatus.READY
        assert execution.connection_scope == "team"

        with pytest.raises(BusinessError) as stale:
            await service.claim_execution(
                execution.id,
                claim_token="claim-stale",
                tool_definition_version=tool.definition_version,
                binding=_team_binding(team_id=team.id, version=2),
            )
        assert stale.value.code == ResponseCode.TOOL_APPROVAL_BINDING_CHANGED

        cancelled = await service.get_execution(execution.id)
        assert cancelled.status == ToolExecutionStatus.CANCELLED
        assert cancelled.cancel_reason == ToolExecutionCancelReason.BINDING_CHANGED

        fresh = await service.create_execution(
            tool=tool,
            operation="mail.send",
            parameters={"to": "a@example.test"},
            actor=actor,
            team_id=team.id,
            entrypoint=ExecutionEntrypoint.API_KEY,
            entrypoint_id="key-1",
            connection_binding=binding,
        )
        claimed = await service.claim_execution(
            fresh.id,
            claim_token="claim-1",
            tool_definition_version=tool.definition_version,
            binding=binding,
        )
        assert claimed.status == ToolExecutionStatus.EXECUTING
        assert claimed.claim_token == "claim-1"

        with pytest.raises(BusinessError) as duplicate:
            await service.claim_execution(
                fresh.id,
                claim_token="claim-2",
                tool_definition_version=tool.definition_version,
                binding=binding,
            )
        assert duplicate.value.code == ResponseCode.TOOL_EXECUTION_CLAIM_CONFLICT
        still_once = await service.get_execution(fresh.id)
        assert still_once.status == ToolExecutionStatus.EXECUTING
        assert still_once.claim_token == "claim-1"


@pytest.mark.asyncio
async def test_decisions_are_idempotent_and_reject_key_reuse_or_resolved_requests():
    async with _database():
        actor = await _user("decider")
        team = await _team("decision-team", actor)
        tool = await _tool(team, _caller_policy())

        execution = await service.create_execution(
            tool=tool,
            operation="file.delete",
            parameters={"path": "/tmp/x"},
            actor=actor,
            team_id=team.id,
            entrypoint=ExecutionEntrypoint.CHAT,
        )
        request = (await service.list_pending_approvals_for_user(actor))[0][0]

        first = await service.decide_approval(
            request.id,
            actor,
            decision=ApprovalVote.APPROVE,
            idempotency_key="decision-key",
        )
        replay = await service.decide_approval(
            request.id,
            actor,
            decision=ApprovalVote.APPROVE,
            idempotency_key="decision-key",
        )
        assert replay.id == first.id
        assert (await service.get_execution(execution.id)).status == (
            ToolExecutionStatus.READY
        )

        with pytest.raises(BusinessError) as key_reuse:
            await service.decide_approval(
                request.id,
                actor,
                decision=ApprovalVote.REJECT,
                idempotency_key="decision-key",
            )
        assert key_reuse.value.code == ResponseCode.TOOL_APPROVAL_IDEMPOTENCY_CONFLICT

        with pytest.raises(BusinessError) as resolved:
            await service.decide_approval(
                request.id,
                actor,
                decision=ApprovalVote.APPROVE,
                idempotency_key="another-key",
            )
        assert resolved.value.code == ResponseCode.TOOL_APPROVAL_ALREADY_DECIDED
        assert (await service.get_execution(execution.id)).status == (
            ToolExecutionStatus.READY
        )


@pytest.mark.asyncio
async def test_user_gate_without_any_current_team_member_fails_closed():
    async with _database():
        owner = await _user("empty-user-owner")
        foreign = await _user("empty-user-foreign")
        team = await _team("empty-user-team", owner)
        tool = await _tool(team, _allow_policy())
        layer = PolicyLayer(
            source=PolicySource.TEAM,
            policy=ToolApprovalPolicy(
                default_decision=ApprovalDecision.REQUIRE_APPROVAL,
                gates=(
                    ApprovalGate(
                        kind=ApprovalGateKind.USER,
                        user_ids=(foreign.id,),
                    ),
                ),
            ),
        )
        with pytest.raises(BusinessError) as config_error:
            await service.create_execution(
                tool=tool,
                operation="ticket.read",
                parameters={},
                actor=owner,
                team_id=team.id,
                entrypoint=ExecutionEntrypoint.CHAT,
                policy_layers=(layer,),
            )
        assert (
            config_error.value.code
            == ResponseCode.TOOL_APPROVAL_POLICY_CONFIGURATION_REQUIRED
        )
        assert await service.ToolExecution.all().count() == 0


@pytest.mark.asyncio
async def test_caller_gate_allows_actor_without_team_membership():
    async with _database():
        other_owner = await _user("caller-gate-owner")
        superuser = await _user("caller-gate-superuser")
        superuser.is_superuser = True
        await superuser.save(update_fields=["is_superuser"])
        team = await _team("caller-gate-team", other_owner)
        tool = await _tool(team, _caller_policy())
        execution = await service.create_execution(
            tool=tool,
            operation="ticket.read",
            parameters={},
            actor=superuser,
            team_id=team.id,
            entrypoint=ExecutionEntrypoint.CHAT,
        )
        inbox, total = await service.list_pending_approvals_for_user(superuser)
        assert total == 1
        await service.decide_approval(
            inbox[0].id,
            superuser,
            decision=ApprovalVote.APPROVE,
            idempotency_key="caller-superuser",
        )
        assert (await service.get_execution(execution.id)).status == (
            ToolExecutionStatus.READY
        )


@pytest.mark.asyncio
async def test_submit_execution_decision_by_execution_id():
    from app.api.v1.endpoints.tool_approvals import submit_execution_decision
    from app.schemas.tool_approval import ToolApprovalDecisionIn

    async with _database():
        actor = await _user("exec-decide-actor")
        team = await _team("exec-team", actor)
        tool = await _tool(
            team,
            {
                "default_decision": "require_approval",
                "gates": [{"kind": "caller"}],
            },
        )
        execution = await service.create_execution(
            tool=tool,
            operation="test_op",
            parameters={},
            actor=actor,
            team_id=tool.team_id,
            entrypoint=ExecutionEntrypoint.CHAT,
            entrypoint_interactive=True,
        )
        assert execution.status == ToolExecutionStatus.AWAITING_APPROVAL

        result = await submit_execution_decision(
            execution_id=execution.id,
            payload=ToolApprovalDecisionIn(
                decision="approve",
                idempotency_key="exec-approve-1",
            ),
            current_user=actor,
        )
        assert result["data"].execution_status == ToolExecutionStatus.READY
        assert result["data"].remaining_approvals == 0
        refreshed = await service.get_execution(execution.id)
        assert refreshed.status == ToolExecutionStatus.READY
