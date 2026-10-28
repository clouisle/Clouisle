"""Audit coverage for tool approval decisions and approval-policy updates.

Decisions are driven through the real HTTP handlers/service against an
in-memory database so identity binding, idempotent replay and failure auditing
are observed exactly as production runs them. Audit rows are inspected for
secret-safe metadata only: caller parameters and reviewer reasons must never
appear.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from tortoise import Tortoise

from app.api.v1.admin.endpoints import tools as admin_tools
from app.api.v1.endpoints.tool_approvals import (
    submit_approval_decision,
    submit_execution_decision,
)
from app.models.agent import Agent, Conversation
from app.models.agent_run import AgentRun, AgentRunMode, AgentRunStatus
from app.models.api_key import APIKey
from app.models.audit_log import AuditLog
from app.models.tool import CustomToolType, Tool, ToolType
from app.models.user import Team, TeamMember, User
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.tool import ToolUpdateInput
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
from app.services.audit_log import AuditLogService
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
        email=f"{label}_{uuid4().hex[:8]}@audit.test",
        hashed_password="x",
    )


async def _team(name: str, owner: User) -> Team:
    team = await Team.create(id=uuid4(), name=f"{name}_{uuid4().hex[:8]}")
    await TeamMember.create(id=uuid4(), team_id=team.id, user_id=owner.id, role="owner")
    return team


async def _tool(team: Team, *, approval_policy: dict | None = None) -> Tool:
    return await Tool.create(
        id=uuid4(),
        team_id=team.id,
        name=f"tool_{uuid4().hex[:8]}",
        display_name="Audited tool",
        description="approval audit test",
        type=ToolType.CUSTOM,
        custom_type=CustomToolType.HTTP,
        approval_policy=approval_policy
        or {"default_decision": "require_approval", "gates": [{"kind": "caller"}]},
    )


def _caller_policy() -> dict:
    return {"default_decision": "require_approval", "gates": [{"kind": "caller"}]}


async def _execution(
    actor: User,
    team: Team,
    tool: Tool,
    *,
    parameters: dict | None = None,
    **kwargs,
) -> service.ToolExecution:
    return await service.create_execution(
        tool=tool,
        operation="ticket.close",
        parameters=parameters or {"ticket": "T-1"},
        actor=actor,
        team_id=team.id,
        entrypoint=kwargs.pop("entrypoint", ExecutionEntrypoint.CHAT),
        **kwargs,
    )


async def _pending_request(execution_id):
    return await service.ToolApprovalRequest.filter(
        execution_id=execution_id,
        status=ApprovalRequestStatus.PENDING,
    ).first()


def _decision(vote: ApprovalVote = ApprovalVote.APPROVE, *, key: str, reason=None):
    return ToolApprovalDecisionIn(
        decision=vote,
        reason=reason,
        idempotency_key=key,
    )


async def _logs(action: str) -> list[AuditLog]:
    return await AuditLog.filter(action=action).order_by("created_at")


def _assert_no_payload_leak(log: AuditLog, *needles: str) -> None:
    inspected = repr((log.metadata, log.changes, log.error_message))
    for needle in needles:
        assert needle not in inspected


@pytest.mark.asyncio
async def test_approve_decision_audits_actor_outcome_and_safe_metadata():
    async with _database():
        actor = await _user("approver")
        team = await _team("audit-team", actor)
        tool = await _tool(team)
        execution = await _execution(
            actor,
            team,
            tool,
            parameters={"ticket": "T-1", "password": "PARAM-SECRET-123"},
        )
        request = await _pending_request(execution.id)

        await submit_approval_decision(
            request_id=request.id,
            payload=_decision(
                key="audit-approve-1",
                reason="REASON-SECRET-456 reviewed manually",
            ),
            auth_result=actor,
        )

        logs = await _logs("approve_tool_execution")
        assert len(logs) == 1
        log = logs[0]
        assert log.user_id == actor.id
        assert log.username == actor.username
        assert log.auth_method == "jwt"
        assert log.api_key_id is None
        assert log.resource_type == "tool_execution"
        assert log.resource_id == execution.id
        assert log.resource_name == "ticket.close"
        assert log.operation == "approve"
        assert log.status == "success"
        assert log.error_message is None
        assert log.changes is None
        assert log.metadata == {
            "execution_id": str(execution.id),
            "approval_request_id": str(request.id),
            "team_id": str(team.id),
            "tool_id": str(tool.id),
            "operation": "ticket.close",
            "entrypoint": "chat",
            "decision": "approve",
            "outcome": "ready",
            "execution_status": "ready",
        }
        _assert_no_payload_leak(log, "PARAM-SECRET-123", "REASON-SECRET-456")


@pytest.mark.asyncio
async def test_reject_decision_audits_rejection_and_cancelled_execution():
    async with _database():
        actor = await _user("rejecter")
        team = await _team("reject-team", actor)
        tool = await _tool(team)
        execution = await _execution(actor, team, tool)
        request = await _pending_request(execution.id)

        await submit_approval_decision(
            request_id=request.id,
            payload=_decision(ApprovalVote.REJECT, key="audit-reject-1"),
            auth_result=actor,
        )

        fresh = await service.get_execution(execution.id)
        assert fresh.status == ToolExecutionStatus.CANCELLED
        assert fresh.cancel_reason.value == "rejected"
        logs = await _logs("reject_tool_execution")
        assert len(logs) == 1
        log = logs[0]
        assert log.operation == "reject"
        assert log.status == "success"
        assert log.metadata["decision"] == "reject"
        assert log.metadata["outcome"] == "rejected"
        assert log.metadata["execution_status"] == "cancelled"


@pytest.mark.asyncio
async def test_api_key_decision_audits_credential_id_but_never_key_material(
    monkeypatch,
):
    async with _database():
        owner = await _user("key-owner")
        team = await _team("key-team", owner)
        agent = await Agent.create(
            id=uuid4(), team_id=team.id, name=f"agent_{uuid4().hex[:8]}"
        )
        key = await APIKey.create(
            id=uuid4(),
            name="audit-key",
            key_prefix="clou_audit",
            key_hash="HASHED-KEY-MATERIAL",
            user_id=owner.id,
            is_active=True,
        )
        await key.agents.add(agent)
        tool = await _tool(team)
        conversation = await Conversation.create(
            id=uuid4(), agent_id=agent.id, user_id=owner.id
        )
        run = await AgentRun.create(
            id=uuid4(),
            agent_id=agent.id,
            conversation_id=conversation.id,
            user_id=owner.id,
            mode=AgentRunMode.SEND,
            api_key_id=key.id,
            status=AgentRunStatus.WAITING,
            pending_tool_call_id="call-1",
            pending_tool_name="ticket_close",
            worker_payload={},
        )
        with tool_identity_scope(
            RuntimeToolIdentity(
                run_id=run.id,
                tool_call_id="call-1",
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
                run_kind=ExecutionRunKind.AGENT,
                run_id=run.id,
                tool_call_id="call-1",
                entrypoint_interactive=False,
            )

        async def _no_resume(*_args, **_kwargs):
            return None

        monkeypatch.setattr(
            agent_run_store, "schedule_agent_run_approval_resume", _no_resume
        )

        await submit_execution_decision(
            execution_id=execution.id,
            payload=_decision(key="audit-api-key-1"),
            auth_result=(owner, key),
        )

        logs = await _logs("approve_tool_execution")
        assert len(logs) == 1
        log = logs[0]
        assert log.user_id == owner.id
        assert log.auth_method == "api_key"
        assert log.api_key_id == key.id
        assert log.metadata["run_kind"] == "agent"
        assert log.metadata["run_id"] == str(run.id)
        assert log.metadata["entrypoint"] == "api_key"
        _assert_no_payload_leak(log, "HASHED-KEY-MATERIAL", "clou_audit")


@pytest.mark.asyncio
async def test_idempotent_replay_does_not_duplicate_audit_or_decision():
    async with _database():
        actor = await _user("replayer")
        team = await _team("replay-team", actor)
        tool = await _tool(team)
        execution = await _execution(actor, team, tool)
        request = await _pending_request(execution.id)
        payload = _decision(key="audit-replay-1")

        await submit_approval_decision(
            request_id=request.id, payload=payload, auth_result=actor
        )
        await submit_approval_decision(
            request_id=request.id, payload=payload, auth_result=actor
        )

        assert (
            await service.ToolApprovalDecision.filter(request_id=request.id).count()
            == 1
        )
        assert (
            await AuditLog.filter(
                action="approve_tool_execution", resource_id=execution.id
            ).count()
            == 1
        )


@pytest.mark.asyncio
async def test_denied_decision_is_audited_as_failure_without_user_input():
    async with _database():
        actor = await _user("owner")
        outsider = await _user("outsider")
        team = await _team("deny-team", actor)
        tool = await _tool(team)
        execution = await _execution(actor, team, tool)
        request = await _pending_request(execution.id)

        with pytest.raises(BusinessError) as exc_info:
            await submit_approval_decision(
                request_id=request.id,
                payload=_decision(key="audit-denied-1", reason="REASON-SECRET-789"),
                auth_result=outsider,
            )
        assert exc_info.value.code == ResponseCode.TOOL_APPROVAL_NOT_AUTHORIZED

        log = await AuditLog.get(action="approve_tool_execution")
        assert log.user_id == outsider.id
        assert log.status == "failed"
        assert log.error_message == "tool_approval_not_authorized"
        assert log.metadata["execution_id"] == str(execution.id)
        assert log.metadata["decision"] == "approve"
        assert log.metadata["execution_status"] == "awaiting_approval"
        _assert_no_payload_leak(log, "REASON-SECRET-789")
        assert (
            await service.get_execution(execution.id)
        ).status == ToolExecutionStatus.AWAITING_APPROVAL


@pytest.mark.asyncio
async def test_expired_decision_is_audited_as_failed_outcome():
    async with _database():
        actor = await _user("expired-actor")
        team = await _team("expired-team", actor)
        tool = await _tool(team)
        execution = await _execution(actor, team, tool)
        request = await _pending_request(execution.id)
        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        execution.expires_at = past
        await execution.save(update_fields=["expires_at", "updated_at"])
        request.expires_at = past
        await request.save(update_fields=["expires_at", "updated_at"])

        with pytest.raises(BusinessError) as exc_info:
            await submit_approval_decision(
                request_id=request.id,
                payload=_decision(key="audit-expired-1"),
                auth_result=actor,
            )
        assert exc_info.value.code == ResponseCode.TOOL_APPROVAL_EXPIRED

        log = await AuditLog.get(action="approve_tool_execution")
        assert log.status == "failed"
        assert log.error_message == "tool_approval_expired"
        assert log.metadata["outcome"] == "expired"
        assert log.metadata["execution_status"] == "cancelled"


@pytest.mark.asyncio
async def test_audit_delivery_failure_never_blocks_durable_decision(monkeypatch):
    async with _database():
        actor = await _user("audit-down")
        team = await _team("audit-down-team", actor)
        tool = await _tool(team)
        execution = await _execution(actor, team, tool)
        request = await _pending_request(execution.id)

        async def _explode(**_kwargs):
            raise RuntimeError("audit store unavailable")

        monkeypatch.setattr(AuditLogService, "log", _explode)

        result = await submit_approval_decision(
            request_id=request.id,
            payload=_decision(key="audit-down-1"),
            auth_result=actor,
        )

        assert result["data"].execution_status == ToolExecutionStatus.READY
        assert (
            await service.get_execution(execution.id)
        ).status == ToolExecutionStatus.READY
        assert await AuditLog.all().count() == 0


@pytest.mark.asyncio
async def test_admin_policy_update_audits_once_and_skips_unchanged_policy():
    async with _database():
        actor = await _user("admin-editor")
        team = await _team("policy-team", actor)
        tool = await _tool(team, approval_policy={"default_decision": "allow"})
        new_policy = _caller_policy()

        await admin_tools.update_tool(
            tool.id,
            ToolUpdateInput(approval_policy=new_policy),
            current_user=actor,
        )

        logs = await _logs("update_tool_approval_policy")
        assert len(logs) == 1
        log = logs[0]
        assert log.user_id == actor.id
        assert log.auth_method == "jwt"
        assert log.resource_type == "tool"
        assert log.resource_id == tool.id
        assert log.resource_name == tool.name
        assert log.operation == "update"
        assert log.status == "success"
        assert log.metadata["team_id"] == str(team.id)
        assert log.metadata["definition_version"] == 2
        assert log.changes["before"]["approval_policy"]["default_decision"] == "allow"
        assert (
            log.changes["after"]["approval_policy"]["default_decision"]
            == "require_approval"
        )
        assert await AuditLog.filter(action="update_tool").count() == 0

        # Re-submitting the semantically identical policy is not a change.
        await admin_tools.update_tool(
            tool.id,
            ToolUpdateInput(approval_policy=new_policy),
            current_user=actor,
        )
        assert len(await _logs("update_tool_approval_policy")) == 1
