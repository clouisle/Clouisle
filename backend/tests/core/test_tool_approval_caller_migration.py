"""Caller-only approval cutover against real ORM rows.

The migration must cancel unstarted executions that depend on retired
user/team-role audiences without touching historical evidence, policies or
already-started work.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from tortoise.context import TortoiseContext

from app.core.tool_approval_caller_migration import (
    LEGACY_EXTERNAL_GATE_KINDS,
    UNSTARTED_EXECUTION_STATUSES,
    cancel_unstarted_legacy_approvals,
    migrate_caller_only_tool_confirmation,
    policy_has_external_gate,
)
from app.models.tool import CustomToolType, Tool, ToolType
from app.models.tool_approval import (
    ToolApprovalDecision,
    ToolApprovalRequest,
    ToolExecution,
)
from app.models.user import Team, User
from app.schemas.tool_approval import (
    ApprovalGateKind,
    ApprovalRequestStatus,
    ApprovalVote,
    ExecutionEntrypoint,
    ToolExecutionCancelReason,
    ToolExecutionStatus,
)


def _digest(char: str) -> str:
    return char * 64


@pytest.fixture
def run_orm():
    with asyncio.Runner() as runner:

        def run(scenario, *, generate: bool = True):
            async def wrapped():
                async with TortoiseContext() as context:
                    await context.init(
                        db_url="sqlite://:memory:", modules={"models": ["app.models"]}
                    )
                    if generate:
                        await context.generate_schemas()
                    await scenario()

            runner.run(wrapped())

        yield run


async def _fixtures():
    owner = await User.create(
        username=f"owner_{uuid4().hex[:8]}",
        email=f"owner_{uuid4().hex[:8]}@caller.test",
        hashed_password="x",
    )
    team = await Team.create(name=f"caller_{uuid4().hex[:8]}", owner=owner)
    tool = await Tool.create(
        id=uuid4(),
        team=team,
        name=f"tool_{uuid4().hex[:8]}",
        display_name="Caller migration tool",
        description="migration test",
        type=ToolType.CUSTOM,
        custom_type=CustomToolType.HTTP,
        approval_policy={
            "default_decision": "require_approval",
            "gates": [{"kind": "caller"}],
        },
    )
    return owner, team, tool


async def _execution(team, tool, actor, status=ToolExecutionStatus.AWAITING_APPROVAL):
    return await ToolExecution.create(
        actor_user=actor,
        effective_user=actor,
        team=team,
        tool=tool,
        tool_definition_version=1,
        operation="ticket.close",
        entrypoint=ExecutionEntrypoint.CHAT,
        parameters_cipher="gAAAAA-ciphertext",
        parameters_digest=_digest("a"),
        policy_hash=_digest("b"),
        binding_hash=_digest("c"),
        status=status,
    )


async def _request(
    execution,
    kind: ApprovalGateKind,
    *,
    status: ApprovalRequestStatus = ApprovalRequestStatus.PENDING,
    stage_index: int = 0,
):
    resolved_at = (
        None if status == ApprovalRequestStatus.PENDING else datetime.now(timezone.utc)
    )
    return await ToolApprovalRequest.create(
        execution=execution,
        stage_index=stage_index,
        stage_key=f"{kind.value}:{stage_index}",
        gate_kind=kind,
        approver_user_ids=[str(uuid4())] if kind == ApprovalGateKind.USER else [],
        approver_roles=["admin"] if kind == ApprovalGateKind.TEAM_ROLE else [],
        allow_self_approval=False,
        status=status,
        resolved_at=resolved_at,
    )


def test_cancels_awaiting_execution_and_every_pending_gate(run_orm):
    async def scenario():
        actor, team, tool = await _fixtures()
        execution = await _execution(team, tool, actor)
        pending_team_role = await _request(
            execution, ApprovalGateKind.TEAM_ROLE, stage_index=1
        )
        pending_caller = await _request(
            execution, ApprovalGateKind.CALLER, stage_index=0
        )
        approved_user = await _request(
            execution,
            ApprovalGateKind.USER,
            status=ApprovalRequestStatus.APPROVED,
            stage_index=2,
        )
        decision = await ToolApprovalDecision.create(
            request=approved_user,
            execution=execution,
            decision=ApprovalVote.APPROVE,
            decided_by=actor,
            idempotency_key=f"legacy-{uuid4()}",
            request_hash=_digest("e"),
            binding_hash=_digest("c"),
        )

        summary = await migrate_caller_only_tool_confirmation()

        assert summary["executions_cancelled"] == 1
        assert summary["requests_cancelled"] == 2
        await execution.refresh_from_db()
        assert execution.status == ToolExecutionStatus.CANCELLED
        assert execution.cancel_reason == ToolExecutionCancelReason.CANCELLED
        assert execution.finished_at is not None
        assert execution.claim_token is None

        for request in (pending_team_role, pending_caller):
            await request.refresh_from_db()
            assert request.status == ApprovalRequestStatus.CANCELLED
            assert request.resolved_at is not None

        await approved_user.refresh_from_db()
        assert approved_user.status == ApprovalRequestStatus.APPROVED
        assert approved_user.resolved_at is not None
        assert await ToolApprovalDecision.filter(id=decision.id).exists()

        await tool.refresh_from_db()
        assert tool.approval_policy["gates"] == [{"kind": "caller"}]

    run_orm(scenario)


def test_cancels_ready_execution_with_approved_external_gate(run_orm):
    async def scenario():
        actor, team, tool = await _fixtures()
        execution = await _execution(
            team, tool, actor, status=ToolExecutionStatus.READY
        )
        await _request(
            execution,
            ApprovalGateKind.TEAM_ROLE,
            status=ApprovalRequestStatus.APPROVED,
        )
        pending_caller = await _request(
            execution, ApprovalGateKind.CALLER, stage_index=1
        )

        summary = await cancel_unstarted_legacy_approvals()

        assert summary == {"executions_cancelled": 1, "requests_cancelled": 1}
        await execution.refresh_from_db()
        assert execution.status == ToolExecutionStatus.CANCELLED
        assert execution.cancel_reason == ToolExecutionCancelReason.CANCELLED
        await pending_caller.refresh_from_db()
        assert pending_caller.status == ApprovalRequestStatus.CANCELLED

    run_orm(scenario)


@pytest.mark.parametrize("status", UNSTARTED_EXECUTION_STATUSES)
def test_rejected_external_gate_still_cancels_unstarted_execution(run_orm, status):
    async def scenario():
        actor, team, tool = await _fixtures()
        execution = await _execution(team, tool, actor, status=status)
        await _request(
            execution,
            ApprovalGateKind.USER,
            status=ApprovalRequestStatus.REJECTED,
        )

        summary = await cancel_unstarted_legacy_approvals()

        assert summary["executions_cancelled"] == 1
        assert summary["requests_cancelled"] == 0
        await execution.refresh_from_db()
        assert execution.status == ToolExecutionStatus.CANCELLED

    run_orm(scenario)


def test_preserves_caller_only_unstarted_executions(run_orm):
    async def scenario():
        actor, team, tool = await _fixtures()
        awaiting = await _execution(team, tool, actor)
        await _request(awaiting, ApprovalGateKind.CALLER)
        ready = await _execution(team, tool, actor, status=ToolExecutionStatus.READY)
        await _request(
            ready, ApprovalGateKind.CALLER, status=ApprovalRequestStatus.APPROVED
        )

        summary = await cancel_unstarted_legacy_approvals()

        assert summary == {"executions_cancelled": 0, "requests_cancelled": 0}
        await awaiting.refresh_from_db()
        await ready.refresh_from_db()
        assert awaiting.status == ToolExecutionStatus.AWAITING_APPROVAL
        assert ready.status == ToolExecutionStatus.READY

    run_orm(scenario)


def test_never_cancels_executing_or_terminal_rows(run_orm):
    async def scenario():
        actor, team, tool = await _fixtures()
        executing = await _execution(
            team, tool, actor, status=ToolExecutionStatus.EXECUTING
        )
        await _request(executing, ApprovalGateKind.TEAM_ROLE)
        succeeded = await _execution(
            team, tool, actor, status=ToolExecutionStatus.SUCCEEDED
        )
        await _request(
            succeeded,
            ApprovalGateKind.USER,
            status=ApprovalRequestStatus.APPROVED,
        )

        summary = await cancel_unstarted_legacy_approvals()

        assert summary == {"executions_cancelled": 0, "requests_cancelled": 0}
        await executing.refresh_from_db()
        await succeeded.refresh_from_db()
        assert executing.status == ToolExecutionStatus.EXECUTING
        assert executing.cancel_reason is None
        assert succeeded.status == ToolExecutionStatus.SUCCEEDED

    run_orm(scenario)


def test_rerun_is_idempotent_and_keeps_original_resolution_times(run_orm):
    async def scenario():
        actor, team, tool = await _fixtures()
        execution = await _execution(team, tool, actor)
        request = await _request(execution, ApprovalGateKind.TEAM_ROLE)

        first = await migrate_caller_only_tool_confirmation()
        await execution.refresh_from_db()
        await request.refresh_from_db()
        execution_updated_at = execution.updated_at
        request_updated_at = request.updated_at

        second = await migrate_caller_only_tool_confirmation()

        assert first["executions_cancelled"] == 1
        assert first["requests_cancelled"] == 1
        assert second["executions_cancelled"] == 0
        assert second["requests_cancelled"] == 0
        await execution.refresh_from_db()
        await request.refresh_from_db()
        assert execution.updated_at == execution_updated_at
        assert request.updated_at == request_updated_at

    run_orm(scenario)


def test_missing_tables_are_a_noop(run_orm):
    async def scenario():
        summary = await migrate_caller_only_tool_confirmation()

        assert summary == {
            "executions_cancelled": 0,
            "requests_cancelled": 0,
            "tools_with_legacy_gates": 0,
        }

    run_orm(scenario, generate=False)


def test_scan_reports_nested_external_gates_without_rewriting_policies(run_orm):
    async def scenario():
        actor, team, tool = await _fixtures()
        nested_policy = {
            "default_decision": "require_approval",
            "gates": [{"kind": "caller"}],
            "operation_overrides": {
                "mail.send": {
                    "default_decision": "require_approval",
                    "gates": [{"kind": "team_role", "roles": ["admin"]}],
                    "operation_overrides": {
                        "mail.bulk_send": {
                            "default_decision": "require_approval",
                            "gates": [{"kind": "user", "user_ids": [str(actor.id)]}],
                        }
                    },
                }
            },
        }
        await Tool.filter(id=tool.id).update(approval_policy=nested_policy)
        caller_only = await Tool.create(
            id=uuid4(),
            team=team,
            name=f"caller_{uuid4().hex[:8]}",
            display_name="Caller only",
            description="caller only",
            type=ToolType.CUSTOM,
            custom_type=CustomToolType.HTTP,
            approval_policy={
                "default_decision": "require_approval",
                "gates": [{"kind": "caller"}],
            },
        )
        summary = await migrate_caller_only_tool_confirmation()

        assert summary["tools_with_legacy_gates"] == 1
        await tool.refresh_from_db()
        await caller_only.refresh_from_db()
        assert tool.approval_policy == nested_policy
        assert caller_only.approval_policy["gates"] == [{"kind": "caller"}]

    run_orm(scenario)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ({"gates": [{"kind": "caller"}]}, False),
        ({"gates": [{"kind": "user", "user_ids": ["x"]}]}, True),
        ({"gates": [{"kind": "team_role", "roles": ["owner"]}]}, True),
        (
            {
                "default_decision": "require_approval",
                "operation_overrides": {
                    "op": {
                        "default_decision": "require_approval",
                        "gates": [{"kind": "team_role", "roles": ["member"]}],
                    }
                },
            },
            True,
        ),
        (json.dumps({"gates": [{"kind": "user", "user_ids": ["x"]}]}), True),
        ("not-json", False),
        (None, False),
        ({}, False),
    ],
)
def test_policy_has_external_gate(raw, expected):
    assert policy_has_external_gate(raw) is expected


def test_legacy_gate_kind_constant_covers_retired_audiences():
    assert set(LEGACY_EXTERNAL_GATE_KINDS) == {"user", "team_role"}
