"""Authorized response surface for MCP server-initiated interactions.

Audience rules are stricter than ordinary run/tool visibility: only the
explicit user ids/roles stored on the row may list or answer it. The response
is idempotent, cannot edit the stored request, and never performs or resumes
the external side effect — the worker that owns the live MCP session observes
the row and answers its own in-process JSON-RPC request. If that session is
gone, the caller is told to start a new execution instead of replaying a tool.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api import deps
from app.models.tool_interaction import InteractionKind, InteractionStatus
from app.models.user import User
from app.schemas.response import PageData, Response, success
from app.schemas.tool_interaction import (
    RunInteractionOut,
    RunInteractionResponseIn,
)
from app.services import tool_interactions

logger = logging.getLogger(__name__)
router = APIRouter()


def _out(interaction) -> RunInteractionOut:
    response = None
    if interaction.status == InteractionStatus.RESPONDED:
        response = tool_interactions.load_response_content(interaction)
    return RunInteractionOut.from_record(interaction, response=response)


@router.get(
    "",
    response_model=Response[PageData[RunInteractionOut]],
    summary="List run interactions visible to the current responder",
)
async def list_run_interactions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    kind: InteractionKind | None = Query(default=None),
    status: InteractionStatus = Query(default=InteractionStatus.PENDING),
    run_id: UUID | None = Query(default=None),
    current_user: User = Depends(deps.get_current_user),
):
    """Pending by default; expired rows are swept before the query."""
    rows, total = await tool_interactions.list_interactions_for_user(
        current_user,
        page=page,
        page_size=page_size,
        kind=kind,
        status=status,
        run_id=run_id,
    )
    return success(
        data=PageData(
            items=[_out(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get(
    "/{interaction_id}",
    response_model=Response[RunInteractionOut],
    summary="Get one run interaction visible to the current responder",
)
async def get_run_interaction(
    interaction_id: UUID,
    current_user: User = Depends(deps.get_current_user),
):
    interaction = await tool_interactions.get_interaction_for_user(
        interaction_id, current_user
    )
    return success(data=_out(interaction))


@router.post(
    "/{interaction_id}/response",
    response_model=Response[RunInteractionOut],
    summary="Accept, decline or cancel a pending run interaction",
)
async def respond_to_run_interaction(
    interaction_id: UUID,
    payload: RunInteractionResponseIn,
    current_user: User = Depends(deps.get_current_user),
):
    interaction = await tool_interactions.respond_to_interaction(
        interaction_id,
        current_user,
        action=payload.action,
        content=payload.content,
        idempotency_key=payload.idempotency_key,
    )
    return success(data=_out(interaction))
