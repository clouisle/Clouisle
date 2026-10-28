"""Branch-margin behavior tests for the tool approval service.

These tests target code paths that the existing approval suites leave
unexercised: strict JSON normalization of scalar parameters, the oversized
preview guard, malformed stored policies, connection-binding mismatch codes,
gate planning rejections, policy-audit fallbacks, decision branches for
replayed/resolved requests, expiry/cancellation dispatch and claim-time
binding drift. Every test drives the real service helpers (and, where a
persisted outcome matters, a real in-memory SQLite database).
"""

from __future__ import annotations

import hashlib
import json
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from tortoise import Tortoise

from app.models.tool import CustomToolType, Tool, ToolType
from app.models.user import Team, TeamMember, User
from app.models.workflow import RunStatus, TriggerType, WorkflowRun
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.tool_approval import (
    ApprovalDecision,
    ApprovalGate,
    ApprovalGateKind,
    ApprovalRequestStatus,
    ApprovalVote,
    ExecutionEntrypoint,
    ExecutionRunKind,
    PolicyEvaluation,
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
        description="margin test",
        type=ToolType.CUSTOM,
        custom_type=CustomToolType.HTTP,
        approval_policy=policy,
    )


def _caller_policy() -> dict:
    return {"default_decision": "require_approval", "gates": [{"kind": "caller"}]}


def _allow_policy() -> dict:
    return {"default_decision": "allow"}


def _team_binding(*, team_id, version: int = 3) -> dict:
    return {
        "connection_id": uuid4(),
        "team_id": team_id,
        "scope": "team",
        "owner_user_id": None,
        "effective_user_id": None,
        "secret_version": version,
        "status": "active",
        "is_active": True,
    }


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
    return await service.ToolApprovalRequest.filter(
        execution_id=execution_id,
        status=ApprovalRequestStatus.PENDING,
    ).first()


def _bulky_policy() -> dict:
    """A valid caller-only policy whose snapshot exceeds the size guard."""
    leaf = {"default_decision": "require_approval"}
    children = {
        f"child-{index}": {
            "default_decision": "require_approval",
            "operation_overrides": {f"grand-{inner}": leaf for inner in range(8)},
        }
        for index in range(200)
    }
    return {"default_decision": "require_approval", "operation_overrides": children}


# ---------------------------------------------------------------------------
# Parameter normalization and preview bounds
# ---------------------------------------------------------------------------


def test_parameter_snapshot_keeps_finite_floats_and_digests_exact_json():
    snapshot = service.build_parameter_snapshot({"ratio": 1.5, "count": 2})

    assert snapshot.preview == {"ratio": 1.5, "count": 2}
    assert snapshot.digest == hashlib.sha256(b'{"count":2,"ratio":1.5}').hexdigest()
    assert snapshot.redacted_paths == ()


def test_redact_parameters_wraps_non_object_roots_under_value():
    assert service.redact_parameters(["a", 1]) == {"value": ["a", 1]}
    assert service.redact_parameters("plain") == {"value": "plain"}


def test_snapshot_preview_is_replaced_by_key_index_when_it_exceeds_the_budget():
    parameters = {f"field-{index:03d}": "x" * 500 for index in range(100)}

    snapshot = service.build_parameter_snapshot(parameters)

    assert set(snapshot.preview) == {"_truncated", "_keys"}
    assert snapshot.preview["_truncated"] is True
    assert snapshot.preview["_keys"] == sorted(parameters)
    # The full parameter digest still binds the real values, not the index.
    assert (
        snapshot.digest
        == hashlib.sha256(
            json.dumps(
                parameters, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
        ).hexdigest()
    )


# ---------------------------------------------------------------------------
# Malformed stored policies and gate planning
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gate_planning_dedupes_caller_stages_and_rejects_bad_audiences():
    caller = ApprovalGate(kind=ApprovalGateKind.CALLER)

    with pytest.raises(BusinessError) as configured:
        await service._plan_gates(
            PolicyEvaluation(
                decision=ApprovalDecision.ALLOW,
                policy_hash="h",
                configuration_error="approval_audience_missing",
            ),
            actor=None,
            team_id=uuid4(),
            interactive=True,
        )
    assert configured.value.code == (
        ResponseCode.TOOL_APPROVAL_POLICY_CONFIGURATION_REQUIRED
    )
    assert configured.value.data == {"reason": "approval_audience_missing"}

    plans = await service._plan_gates(
        PolicyEvaluation(
            decision=ApprovalDecision.REQUIRE_APPROVAL,
            gates=(caller, caller),
            policy_hash="h",
        ),
        actor=None,
        team_id=uuid4(),
        interactive=True,
    )
    assert [(plan.stage_index, plan.stage_key) for plan in plans] == [(0, "caller")]

    with pytest.raises(BusinessError) as unavailable:
        await service._plan_gates(
            PolicyEvaluation(
                decision=ApprovalDecision.REQUIRE_APPROVAL,
                gates=(caller,),
                policy_hash="h",
            ),
            actor=None,
            team_id=uuid4(),
            interactive=False,
        )
    assert unavailable.value.data == {"reason": "approval_audience_unavailable"}

    with pytest.raises(BusinessError) as external:
        await service._plan_gates(
            PolicyEvaluation(
                decision=ApprovalDecision.REQUIRE_APPROVAL,
                gates=(ApprovalGate(kind=ApprovalGateKind.USER, user_ids=(uuid4(),)),),
                policy_hash="h",
            ),
            actor=None,
            team_id=uuid4(),
            interactive=True,
        )
    assert external.value.data == {"reason": "approval_external_audience_unsupported"}

    with pytest.raises(BusinessError) as missing:
        await service._plan_gates(
            PolicyEvaluation(
                decision=ApprovalDecision.REQUIRE_APPROVAL,
                gates=(),
                policy_hash="h",
            ),
            actor=None,
            team_id=uuid4(),
            interactive=True,
        )
    assert missing.value.data == {"reason": "approval_audience_missing"}


@pytest.mark.asyncio
async def test_oversized_policy_snapshot_is_rejected_before_persisting():
    async with _database():
        actor = await _user("bulky-policy-actor")
        team = await _team("bulky-policy-team", actor)
        tool = await _tool(team, _allow_policy())

        with pytest.raises(BusinessError) as oversized:
            await _execution(actor, team, tool, policy=_bulky_policy())

        assert oversized.value.code == (
            ResponseCode.TOOL_APPROVAL_POLICY_CONFIGURATION_REQUIRED
        )
        assert oversized.value.data == {"reason": "approval_policy_snapshot_too_large"}
        assert await service.ToolExecution.all().count() == 0


# ---------------------------------------------------------------------------
# Connection bindings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_binding_mismatch_codes_cover_effective_principal_and_inactive():
    async with _database():
        actor = await _user("binding-code-actor")
        other = await _user("binding-code-other")
        team = await _team("binding-code-team", actor)
        tool = await _tool(team, _allow_policy())
        binding = _team_binding(team_id=team.id)
        execution = await _execution(actor, team, tool, connection_binding=binding)

        matching = service._BindingFacts(
            connection_id=execution.connection_id,
            team_id=team.id,
            scope="team",
            owner_user_id=None,
            effective_user_id=None,
            secret_version=3,
            status="active",
            is_active=True,
        )
        assert service._binding_matches_execution(execution, matching) is None

        drifted = replace(matching, effective_user_id=other.id)
        assert service._binding_matches_execution(execution, drifted) == (
            "effective_user_changed"
        )
        assert (
            service._binding_matches_execution(
                execution, replace(matching, is_active=False)
            )
            == "connection_inactive"
        )


@pytest.mark.asyncio
async def test_none_binding_snapshot_reports_a_missing_connection_id():
    with pytest.raises(service._BindingSnapshotError) as missing:
        service._normalize_binding(None)

    assert str(missing.value) == "connection_id_missing"


def test_stored_api_key_id_ignores_unparseable_explicit_columns():
    stored = uuid4()
    execution = service.ToolExecution(
        api_key_id=str(stored),
        entrypoint=ExecutionEntrypoint.API_KEY,
        entrypoint_id="legacy",
    )
    assert service.stored_api_key_id(execution) == stored

    execution.api_key_id = "not-a-uuid"
    assert service.stored_api_key_id(execution) is None

    execution.api_key_id = None
    execution.entrypoint = ExecutionEntrypoint.CHAT
    assert service.stored_api_key_id(execution) is None


# ---------------------------------------------------------------------------
# Decide/expire/cancel flows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_replayed_idempotency_key_cannot_be_claimed_by_another_approver():
    async with _database():
        actor = await _user("replay-actor")
        other = await _user("replay-other")
        team = await _team("replay-team", actor)
        await TeamMember.create(
            id=uuid4(), team_id=team.id, user_id=other.id, role="member"
        )
        tool = await _tool(team, _caller_policy())
        execution = await _execution(actor, team, tool)
        request = await _pending(execution.id)

        recorded = await service.decide_approval(
            request.id,
            actor,
            decision=ApprovalVote.APPROVE,
            idempotency_key="idem-1",
        )
        assert recorded.decision == ApprovalVote.APPROVE

        with pytest.raises(BusinessError) as stolen:
            await service.decide_approval(
                request.id,
                other,
                decision=ApprovalVote.APPROVE,
                idempotency_key="idem-1",
            )
        assert stolen.value.code == ResponseCode.TOOL_APPROVAL_NOT_AUTHORIZED
        assert len(await service.ToolApprovalDecision.all()) == 1


@pytest.mark.asyncio
async def test_resolved_gate_before_pending_check_reports_already_decided():
    async with _database():
        actor = await _user("resolved-actor")
        team = await _team("resolved-team", actor)
        tool = await _tool(team, _caller_policy())
        execution = await _execution(actor, team, tool)
        request = await _pending(execution.id)
        await service.ToolApprovalRequest.filter(id=request.id).update(
            status=ApprovalRequestStatus.CANCELLED
        )

        with pytest.raises(BusinessError) as resolved:
            await service.decide_approval(
                request.id,
                actor,
                decision=ApprovalVote.APPROVE,
                idempotency_key="idem-resolved",
            )

        assert resolved.value.code == ResponseCode.TOOL_APPROVAL_ALREADY_DECIDED
        assert await service.ToolApprovalDecision.all().count() == 0


@pytest.mark.asyncio
async def test_approval_with_a_remaining_gate_keeps_the_execution_waiting():
    async with _database():
        actor = await _user("remaining-actor")
        team = await _team("remaining-team", actor)
        tool = await _tool(team, _caller_policy())
        execution = await _execution(actor, team, tool)
        first = await _pending(execution.id)
        second = await service.ToolApprovalRequest.create(
            execution_id=execution.id,
            stage_index=1,
            stage_key="caller:secondary",
            gate_kind=ApprovalGateKind.CALLER,
            masked_display={},
            status=ApprovalRequestStatus.PENDING,
            expires_at=execution.expires_at,
        )

        recorded = await service.decide_approval(
            first.id,
            actor,
            decision=ApprovalVote.APPROVE,
            idempotency_key="idem-remaining",
        )

        assert recorded.decision == ApprovalVote.APPROVE
        assert (await service.get_execution(execution.id)).status == (
            ToolExecutionStatus.AWAITING_APPROVAL
        )
        assert (
            await service.ToolApprovalRequest.filter(id=second.id).first()
        ).status == ApprovalRequestStatus.PENDING


@pytest.mark.asyncio
async def test_expiry_and_cancellation_terminalise_pending_work():
    async with _database():
        actor = await _user("terminal-actor")
        team = await _team("terminal-team", actor)
        tool = await _tool(team, _caller_policy())
        now = datetime.now(timezone.utc)

        expiring = await _execution(actor, team, tool, now=now)
        expiring_request = await _pending(expiring.id)
        await service.ToolExecution.filter(id=expiring.id).update(
            expires_at=now - timedelta(seconds=5)
        )

        assert await service.expire_execution(expiring.id, now=now) is True
        expired_row = await service.get_execution(expiring.id)
        assert expired_row.status == ToolExecutionStatus.CANCELLED
        assert expired_row.cancel_reason == ToolExecutionCancelReason.EXPIRED
        assert expired_row.finished_at is not None
        assert (
            await service.ToolApprovalRequest.filter(id=expiring_request.id).first()
        ).status == ApprovalRequestStatus.EXPIRED

        cancellable = await _execution(actor, team, tool, now=now)
        cancellable_request = await _pending(cancellable.id)

        cancelled = await service.cancel_execution(cancellable.id, now=now)

        assert cancelled.status == ToolExecutionStatus.CANCELLED
        assert cancelled.cancel_reason == ToolExecutionCancelReason.CANCELLED
        assert (
            await service.ToolApprovalRequest.filter(id=cancellable_request.id).first()
        ).status == ApprovalRequestStatus.CANCELLED


# ---------------------------------------------------------------------------
# Claim, parameters and stale claims
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claim_detects_binding_hash_drift_and_cancels():
    async with _database():
        actor = await _user("claim-drift-actor")
        team = await _team("claim-drift-team", actor)
        tool = await _tool(team, _allow_policy())
        execution = await _execution(actor, team, tool)
        await service.ToolExecution.filter(id=execution.id).update(
            operation="ticket.reopen"
        )

        with pytest.raises(BusinessError) as drifted:
            await service.claim_execution(
                execution.id,
                claim_token="drift-token",
                tool_definition_version=tool.definition_version,
            )

        assert drifted.value.code == ResponseCode.TOOL_APPROVAL_BINDING_CHANGED
        assert drifted.value.data == {"reason": "binding_changed"}
        row = await service.get_execution(execution.id)
        assert row.status == ToolExecutionStatus.CANCELLED
        assert row.cancel_reason == ToolExecutionCancelReason.BINDING_CHANGED


@pytest.mark.asyncio
async def test_decrypted_non_object_parameters_are_unreadable():
    async with _database():
        actor = await _user("params-actor")
        team = await _team("params-team", actor)
        tool = await _tool(team, _allow_policy())
        execution = await _execution(actor, team, tool)
        claimed = await service.claim_execution(
            execution.id,
            claim_token="params-token",
            tool_definition_version=tool.definition_version,
        )
        assert claimed.status == ToolExecutionStatus.EXECUTING

        from app.core.tool_secrets import encrypt_tool_secret

        await service.ToolExecution.filter(id=execution.id).update(
            parameters_cipher=encrypt_tool_secret("[1, 2]")
        )

        with pytest.raises(BusinessError) as malformed:
            await service.load_execution_parameters(
                execution.id, claim_token="params-token"
            )

        assert malformed.value.code == (
            ResponseCode.TOOL_EXECUTION_PARAMETERS_UNREADABLE
        )


@pytest.mark.asyncio
async def test_stale_workflow_claims_wait_for_a_terminal_run():
    async with _database():
        actor = await _user("stale-workflow-actor")
        team = await _team("stale-workflow-team", actor)
        tool = await _tool(team, _allow_policy())
        now = datetime.now(timezone.utc)
        run = await WorkflowRun.create(
            id=uuid4(), trigger_type=TriggerType.MANUAL, status=RunStatus.RUNNING
        )

        execution = await _execution(
            actor,
            team,
            tool,
            entrypoint=ExecutionEntrypoint.WORKFLOW,
            run_kind=ExecutionRunKind.WORKFLOW,
            run_id=run.id,
            now=now,
        )
        await service.claim_execution(
            execution.id,
            claim_token="workflow-token",
            tool_definition_version=tool.definition_version,
            now=now - timedelta(minutes=10),
        )
        await service.ToolExecution.filter(id=execution.id).update(
            claimed_at=now - timedelta(minutes=10)
        )

        assert (
            await service.mark_stale_executing_outcome_unknown(
                stale_after_seconds=60, now=now
            )
            == 0
        )
        assert (await service.get_execution(execution.id)).status == (
            ToolExecutionStatus.EXECUTING
        )

        await WorkflowRun.filter(id=run.id).update(status=RunStatus.SUCCESS)
        assert (
            await service.mark_stale_executing_outcome_unknown(
                stale_after_seconds=60, now=now
            )
            == 1
        )
        stale_row = await service.get_execution(execution.id)
        assert stale_row.status == ToolExecutionStatus.OUTCOME_UNKNOWN
        assert stale_row.error_code == "claim_expired"


# ---------------------------------------------------------------------------
# Audit payload fallbacks
# ---------------------------------------------------------------------------


def test_policy_audit_payload_and_change_detection_survive_unserialisable_bodies():
    raw = object()
    assert service._policy_audit_payload(raw) is raw
    assert service._policy_audit_payload(["raw"]) == ["raw"]

    assert service.approval_policy_changed(raw, raw) is False
    assert service.approval_policy_changed(raw, object()) is True


def test_request_audience_rejects_legacy_external_gates():
    actor = SimpleNamespace(id=uuid4(), is_active=True)
    execution = SimpleNamespace(actor_user_id=actor.id)
    request = SimpleNamespace(gate_kind=ApprovalGateKind.USER)

    assert (
        service._request_audience_matches(
            request,
            execution,
            actor,
            team_role="owner",
            is_team_member=True,
        )
        is False
    )
