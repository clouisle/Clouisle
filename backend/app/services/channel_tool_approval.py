"""Caller-only tool confirmation for authenticated IM AgentRun sessions."""

from __future__ import annotations

import json
from uuid import UUID

from app.core.i18n import t
from app.models.agent_run import AgentRunStatus
from app.models.tool_approval import ToolApprovalRequest
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.tool_approval import (
    ApprovalRequestStatus,
    ApprovalVote,
    ExecutionEntrypoint,
    ExecutionRunKind,
    ToolExecutionStatus,
)
from app.services import agent_run_store, tool_approvals


def is_tool_approval(run) -> bool:
    return (
        isinstance(run.pending_tool_input, dict)
        and run.pending_tool_input.get("interaction_kind") == "tool_approval"
    )


def is_ask_user(run) -> bool:
    return (
        run.pending_tool_name == "ask_user"
        and isinstance(run.pending_tool_input, dict)
        and not run.pending_tool_input.get("interaction_kind")
    )


def _invalid() -> BusinessError:
    return BusinessError(
        code=ResponseCode.TOOL_EXECUTION_ACCESS_DENIED,
        msg_key="channel_approval_invalid",
        status_code=403,
    )


async def _execution(run, user, origin, origin_id):
    if (
        run.status != AgentRunStatus.WAITING
        or run.user_id != user.id
        or not getattr(user, "is_active", True)
        or not is_tool_approval(run)
        or not run.pending_tool_call_id
        or origin
        not in {ExecutionEntrypoint.FEISHU_CHANNEL, ExecutionEntrypoint.WECHAT_CHANNEL}
        or not origin_id
    ):
        raise _invalid()
    try:
        execution_id = UUID(str(run.pending_tool_input.get("execution_id")))
    except (TypeError, ValueError):
        raise _invalid() from None
    execution = await tool_approvals.get_execution(execution_id)
    if (
        execution.actor_user_id != user.id
        or execution.run_id != run.id
        or execution.run_kind != ExecutionRunKind.AGENT
        or execution.tool_call_id != run.pending_tool_call_id
        or execution.entrypoint != origin
        or execution.entrypoint_id != str(origin_id)
    ):
        raise _invalid()
    return execution


async def approval_preview(run, user, origin, origin_id) -> tuple[str, str]:
    execution = await _execution(run, user, origin, origin_id)
    if execution.status != ToolExecutionStatus.AWAITING_APPROVAL:
        raise _invalid()
    code = str(execution.id)
    description = run.pending_tool_input.get("tool_description")
    safe_description = (
        description.strip()[:2000] if isinstance(description, str) else ""
    )
    return code, t(
        "channel_approval_prompt",
        operation=execution.operation,
        description=safe_description or "-",
        account=execution.connection_account_label or "-",
        parameters=json.dumps(
            execution.parameters_preview or {}, ensure_ascii=False, default=str
        ),
        code=code,
    )


async def decide_channel_approval(
    run, user, origin, origin_id, token, decision, receipt_id
) -> None:
    execution = await _execution(run, user, origin, origin_id)
    try:
        supplied = UUID(str(token))
        vote = ApprovalVote(decision)
    except (ValueError, TypeError):
        raise _invalid() from None
    if (
        supplied != execution.id
        or execution.status != ToolExecutionStatus.AWAITING_APPROVAL
    ):
        raise _invalid()
    request = await ToolApprovalRequest.filter(
        execution_id=execution.id, status=ApprovalRequestStatus.PENDING
    ).first()
    if request is None:
        raise _invalid()
    await tool_approvals.decide_approval(
        request.id,
        user,
        decision=vote,
        idempotency_key=f"im:{origin.value}:{receipt_id}",
    )
    fresh = await tool_approvals.get_execution(execution.id)
    await agent_run_store.schedule_agent_run_approval_resume(fresh)
