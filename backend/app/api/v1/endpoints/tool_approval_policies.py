"""Site/team/entrypoint approval policy administration endpoints.

All authorization is server side and never inferred from the request body:
site rows require ``admin:settings:update`` (or superuser), team rows require
the team owner/admin role plus global ``tool:update``, and entrypoint rows
require the entrypoint's creator or a team owner/admin plus ``tool:update``.
The referenced Agent/Workflow/APIKey is validated inside the team before a row
is written. DTOs never include secrets; ``can_edit`` tells the UI whether to
render controls instead of letting the client guess.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api import deps
from app.models.user import User
from app.schemas.response import Response, success
from app.schemas.tool_approval import ExecutionEntrypoint, PolicySource
from app.schemas.tool_approval_policy import (
    ToolApprovalEntrypointKind,
    ToolApprovalPolicyCreateIn,
    ToolApprovalPolicyEffectiveOut,
    ToolApprovalPolicyLayerOut,
    ToolApprovalPolicyOut,
    ToolApprovalPolicyScope,
    ToolApprovalPolicyUpdateIn,
)
from app.services import tool_approval_policies as policy_service

router = APIRouter()


def _out(view: policy_service.PolicyDefinitionView) -> ToolApprovalPolicyOut:
    row = view.row
    return ToolApprovalPolicyOut(
        id=row.id,
        scope=row.scope,
        team_id=row.team_id,
        entrypoint_kind=row.entrypoint_kind,
        entrypoint_id=row.entrypoint_id,
        tool_id=row.tool_id,
        policy=view.policy,
        policy_hash=row.policy_hash,
        version=row.version,
        can_edit=view.can_edit,
        configuration_error=view.configuration_error,
        created_by_id=row.created_by_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get(
    "",
    response_model=Response[list[ToolApprovalPolicyOut]],
    summary="List configured approval policy layers",
)
async def list_policy_layers(
    team_id: UUID | None = Query(default=None),
    scope: ToolApprovalPolicyScope | None = Query(default=None),
    entrypoint_kind: ToolApprovalEntrypointKind | None = Query(default=None),
    entrypoint_id: UUID | None = Query(default=None),
    tool_id: UUID | None = Query(default=None),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Team listings include read-only site baseline rows.

    Without ``team_id`` only site rows are returned and site-administration
    read permission is required.
    """
    views = await policy_service.list_policy_definitions(
        current_user,
        team_id=team_id,
        scope=scope,
        entrypoint_kind=entrypoint_kind,
        entrypoint_id=entrypoint_id,
        tool_id=tool_id,
    )
    return success(data=[_out(view) for view in views])


@router.get(
    "/effective",
    response_model=Response[ToolApprovalPolicyEffectiveOut],
    summary="Preview the effective policy for one tool operation",
)
async def get_effective_policy(
    team_id: UUID,
    tool_id: UUID,
    operation: str = Query(min_length=1, max_length=200),
    entrypoint: ExecutionEntrypoint | None = Query(
        default=None,
        description=(
            "Runtime entrypoint of the previewed call. Omitted means a direct "
            "tool-test/browse call; pass an interactive agent entrypoint to "
            "preview the tool's own policy."
        ),
    ),
    entrypoint_kind: ToolApprovalEntrypointKind | None = Query(default=None),
    entrypoint_id: UUID | None = Query(default=None),
    entrypoint_interactive: bool = Query(default=True),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Server-composed policy preview; clients must never merge layers."""
    view = await policy_service.get_effective_policy(
        current_user,
        team_id=team_id,
        entrypoint_kind=entrypoint_kind,
        entrypoint_id=entrypoint_id,
        entrypoint=entrypoint,
        tool_id=tool_id,
        operation=operation,
        entrypoint_interactive=entrypoint_interactive,
    )
    evaluation = view.evaluation
    layers = [
        ToolApprovalPolicyLayerOut(
            source=entry.layer.source,
            label=entry.layer.label,
            version=entry.version,
            policy_hash=entry.policy_hash,
            can_edit=can_edit,
        )
        for entry, can_edit in zip(view.layers, view.layer_can_edit)
    ]
    layers.append(
        ToolApprovalPolicyLayerOut(
            source=PolicySource.TOOL,
            label="tool",
            version=None,
            policy_hash=None,
            can_edit=False,
        )
    )
    return success(
        data=ToolApprovalPolicyEffectiveOut(
            operation=operation,
            decision=evaluation.decision,
            gates=evaluation.gates,
            policy_hash=evaluation.policy_hash,
            sources=evaluation.sources,
            configuration_error=evaluation.configuration_error,
            entrypoint_interactive=view.entrypoint_interactive,
            layers=tuple(layers),
            can_edit_team=view.can_edit_team,
        )
    )


@router.post(
    "",
    response_model=Response[ToolApprovalPolicyOut],
    summary="Create one approval policy layer",
)
async def create_policy_layer(
    payload: ToolApprovalPolicyCreateIn,
    current_user: User = Depends(deps.get_current_active_user),
):
    view = await policy_service.create_policy_definition(current_user, payload)
    return success(data=_out(view))


@router.put(
    "/{policy_id}",
    response_model=Response[ToolApprovalPolicyOut],
    summary="Replace one approval policy layer under version control",
)
async def update_policy_layer(
    policy_id: UUID,
    payload: ToolApprovalPolicyUpdateIn,
    current_user: User = Depends(deps.get_current_active_user),
):
    view = await policy_service.update_policy_definition(
        current_user, policy_id, payload
    )
    return success(data=_out(view))


@router.delete(
    "/{policy_id}",
    response_model=Response[None],
    summary="Delete one approval policy layer",
)
async def delete_policy_layer(
    policy_id: UUID,
    current_user: User = Depends(deps.get_current_active_user),
):
    await policy_service.delete_policy_definition(current_user, policy_id)
    return success(data=None)
