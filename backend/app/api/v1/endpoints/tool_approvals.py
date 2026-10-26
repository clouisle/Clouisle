"""Unified tool execution approval inbox and execution status endpoints.

Routes intentionally expose only secret-safe projections: execution
parameters are returned as the already-redacted preview, never as ciphertext,
decrypted values or connection credentials. Deciding a request records the
decision and moves the durable execution to ``ready``; it does not perform the
external side effect. The AgentRun/workflow worker claims and executes the
original deferred tool call afterwards.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api import deps
from app.models.tool_approval import ToolApprovalRequest
from app.models.user import User
from app.schemas.response import (
    BusinessError,
    PageData,
    Response,
    ResponseCode,
    success,
)
from app.schemas.tool_approval import (
    ApprovalRequestStatus,
    ExecutionRunKind,
    ToolApprovalDecisionIn,
    ToolApprovalDecisionOut,
    ToolApprovalDecisionResultOut,
    ToolApprovalRequestOut,
    ToolExecutionOut,
    ToolExecutionStatus,
)
from app.services import agent_run_store
from app.services.tool_approvals import (
    decide_approval,
    get_approval_request_for_viewer,
    get_execution,
    get_execution_for_viewer,
    list_executions_for_actor,
    list_pending_approvals_for_user,
)

logger = logging.getLogger(__name__)
router = APIRouter()
execution_router = APIRouter()


@router.get(
    "",
    response_model=Response[PageData[ToolApprovalRequestOut]],
    summary="List pending approval requests for the current approver",
)
async def list_pending_approval_requests(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(deps.get_current_user),
):
    """Only gates whose caller/user/team-role audience includes the caller."""
    requests, total = await list_pending_approvals_for_user(
        current_user, page=page, page_size=page_size
    )
    return success(
        data=PageData(
            items=[ToolApprovalRequestOut.model_validate(item) for item in requests],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get(
    "/{request_id}",
    response_model=Response[ToolApprovalRequestOut],
    summary="Get one approval request visible to the current approver",
)
async def get_approval_request(
    request_id: UUID,
    current_user: User = Depends(deps.get_current_user),
):
    request = await get_approval_request_for_viewer(request_id, current_user)
    return success(data=ToolApprovalRequestOut.model_validate(request))


@router.post(
    "/{request_id}/decision",
    response_model=Response[ToolApprovalDecisionResultOut],
    summary="Approve or reject one approval gate",
)
async def submit_approval_decision(
    request_id: UUID,
    payload: ToolApprovalDecisionIn,
    current_user: User = Depends(deps.get_current_user),
):
    """Decision is idempotent and never edits the bound execution parameters."""
    decision = await decide_approval(
        request_id,
        current_user,
        decision=payload.decision,
        reason=payload.reason,
        idempotency_key=payload.idempotency_key,
    )
    execution = await get_execution(decision.execution_id)
    if execution.run_kind == ExecutionRunKind.AGENT:
        try:
            await agent_run_store.schedule_agent_run_approval_resume(execution)
        except Exception:
            # The decision is already durable; a dispatch failure is recorded
            # by the run itself and must not turn an approved gate into an API
            # error that invites a second decision.
            logger.exception(
                "Failed to schedule approval resume for execution %s",
                execution.id,
            )
    remaining = await ToolApprovalRequest.filter(
        execution_id=execution.id,
        status=ApprovalRequestStatus.PENDING,
    ).count()
    return success(
        data=ToolApprovalDecisionResultOut(
            decision=ToolApprovalDecisionOut.model_validate(decision),
            execution_status=execution.status,
            remaining_approvals=remaining,
        )
    )


@execution_router.get(
    "",
    response_model=Response[PageData[ToolExecutionOut]],
    summary="List tool executions initiated by the current user",
)
async def list_my_executions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: ToolExecutionStatus | None = Query(default=None),
    tool_id: UUID | None = Query(default=None),
    run_kind: ExecutionRunKind | None = Query(default=None),
    run_id: UUID | None = Query(default=None),
    current_user: User = Depends(deps.get_current_user),
):
    """Durable execution references for waiting UIs; secrets are never included."""
    executions, total = await list_executions_for_actor(
        current_user,
        page=page,
        page_size=page_size,
        status=status,
        tool_id=tool_id,
        run_kind=run_kind,
        run_id=run_id,
    )
    return success(
        data=PageData(
            items=[ToolExecutionOut.model_validate(item) for item in executions],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@execution_router.get(
    "/{execution_id}",
    response_model=Response[ToolExecutionOut],
    summary="Get one tool execution visible to the current user",
)
async def get_my_execution(
    execution_id: UUID,
    current_user: User = Depends(deps.get_current_user),
):
    execution = await get_execution_for_viewer(execution_id, current_user)
    return success(data=ToolExecutionOut.model_validate(execution))


@execution_router.post(
    "/{execution_id}/decision",
    response_model=Response[ToolApprovalDecisionResultOut],
    summary="Approve or reject a tool execution directly by execution ID",
)
async def submit_execution_decision(
    execution_id: UUID,
    payload: ToolApprovalDecisionIn,
    current_user: User = Depends(deps.get_current_user),
):
    """Directly decide the pending approval gate for an execution in chat."""
    execution = await get_execution_for_viewer(execution_id, current_user)
    request = await ToolApprovalRequest.filter(
        execution_id=execution.id,
        status=ApprovalRequestStatus.PENDING,
    ).first()
    if not request:
        raise BusinessError(
            code=ResponseCode.TOOL_APPROVAL_REQUEST_NOT_FOUND,
            msg_key="tool_approval_request_not_found",
            status_code=404,
        )
    decision = await decide_approval(
        request.id,
        current_user,
        decision=payload.decision,
        reason=payload.reason,
        idempotency_key=payload.idempotency_key,
    )
    fresh_execution = await get_execution(decision.execution_id)
    if fresh_execution.run_kind == ExecutionRunKind.AGENT:
        try:
            await agent_run_store.schedule_agent_run_approval_resume(fresh_execution)
        except Exception:
            logger.exception(
                "Failed to schedule approval resume for execution %s",
                fresh_execution.id,
            )
    remaining = await ToolApprovalRequest.filter(
        execution_id=fresh_execution.id,
        status=ApprovalRequestStatus.PENDING,
    ).count()
    return success(
        data=ToolApprovalDecisionResultOut(
            decision=ToolApprovalDecisionOut.model_validate(decision),
            execution_status=fresh_execution.status,
            remaining_approvals=remaining,
        )
    )


__all__ = ["execution_router", "router"]
