"""
Workflow API endpoints.
Provides CRUD operations for workflows and workflow runs.
"""

import logging
import secrets
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from tortoise.expressions import Q

from app.api import deps
from app.models.user import User, Team, TeamMember
from app.models.workflow import (
    Workflow,
    WorkflowRun,
    NodeExecution,
    WorkflowStatus,
    TriggerType,
    RunStatus,
)
from app.schemas.workflow import (
    WorkflowCreate,
    WorkflowUpdate,
    WorkflowOut,
    WorkflowListItem,
    WorkflowRunOut,
    WorkflowRunListItem,
    NodeExecutionOut,
)
from app.schemas.response import (
    Response,
    PageData,
    ResponseCode,
    BusinessError,
    success,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ============ Helper Functions ============


async def check_team_access(
    team_id: UUID, user: User, require_admin: bool = False
) -> Team:
    """Check if user has access to the team."""
    team = await Team.filter(id=team_id).first()
    if not team:
        raise BusinessError(
            code=ResponseCode.TEAM_NOT_FOUND,
            msg_key="team_not_found",
            status_code=404,
        )

    if user.is_superuser:
        return team

    membership = await TeamMember.filter(team=team, user=user).first()
    if not membership:
        raise BusinessError(
            code=ResponseCode.NOT_TEAM_MEMBER,
            msg_key="not_team_member",
            status_code=403,
        )

    if require_admin and membership.role not in ["owner", "admin"]:
        raise BusinessError(
            code=ResponseCode.TEAM_ADMIN_REQUIRED,
            msg_key="team_admin_required",
            status_code=403,
        )

    return team


async def check_workflow_access(
    workflow_id: UUID, user: User, require_write: bool = False
) -> Workflow:
    """Check if user has access to the workflow."""
    workflow = (
        await Workflow.filter(id=workflow_id)
        .prefetch_related("team", "created_by")
        .first()
    )
    if not workflow:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="workflow_not_found",
            status_code=404,
        )

    # Check team membership
    await check_team_access(workflow.team.id, user, require_admin=require_write)

    return workflow


# ============ Workflow CRUD ============


@router.get("/", response_model=Response[PageData[WorkflowListItem]])
async def list_workflows(
    team_id: UUID | None = None,
    status: WorkflowStatus | None = None,
    trigger_type: TriggerType | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    List workflows.
    If team_id is provided, list workflows for that team.
    Otherwise, list all workflows the user has access to.
    """
    query = Workflow.all()

    if team_id:
        await check_team_access(team_id, current_user)
        query = query.filter(team_id=team_id)
    elif not current_user.is_superuser:
        # Get teams user belongs to
        memberships = await TeamMember.filter(user=current_user).values_list(
            "team_id", flat=True
        )
        query = query.filter(team_id__in=memberships)

    if status:
        query = query.filter(status=status)

    if trigger_type:
        query = query.filter(trigger_type=trigger_type)

    if keyword:
        query = query.filter(
            Q(name__icontains=keyword) | Q(description__icontains=keyword)
        )

    total = await query.count()
    skip = (page - 1) * page_size
    workflows = await query.offset(skip).limit(page_size).order_by("-updated_at")

    workflow_list = [WorkflowListItem.model_validate(w) for w in workflows]

    return success(
        data={
            "items": [w.model_dump() for w in workflow_list],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.post("/", response_model=Response[WorkflowOut])
async def create_workflow(
    *,
    workflow_in: WorkflowCreate,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """Create a new workflow."""
    # Check team access
    team = await check_team_access(workflow_in.team_id, current_user)

    # Create workflow with default definition (start + end nodes)
    default_definition = {
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "position": {"x": 250, "y": 100},
                "data": {"type": "start", "label": "开始", "config": {}},
            },
            {
                "id": "end",
                "type": "end",
                "position": {"x": 250, "y": 400},
                "data": {"type": "end", "label": "结束", "config": {}},
            },
        ],
        "edges": [],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    }

    workflow = await Workflow.create(
        name=workflow_in.name,
        description=workflow_in.description,
        icon=workflow_in.icon,
        team=team,
        definition=default_definition,
        variables=[],
        created_by=current_user,
    )

    # Reload with relations
    workflow = await Workflow.get(id=workflow.id).prefetch_related("team", "created_by")

    return success(
        data=WorkflowOut.model_validate(workflow).model_dump(),
        msg_key="workflow_created",
    )


@router.get("/{workflow_id}", response_model=Response[WorkflowOut])
async def get_workflow(
    workflow_id: UUID,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """Get workflow by ID."""
    workflow = await check_workflow_access(workflow_id, current_user)
    return success(data=WorkflowOut.model_validate(workflow).model_dump())


@router.put("/{workflow_id}", response_model=Response[WorkflowOut])
async def update_workflow(
    *,
    workflow_id: UUID,
    workflow_in: WorkflowUpdate,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """Update a workflow."""
    workflow = await check_workflow_access(workflow_id, current_user, require_write=True)

    # Update fields
    if workflow_in.name is not None:
        workflow.name = workflow_in.name
    if workflow_in.description is not None:
        workflow.description = workflow_in.description
    if workflow_in.icon is not None:
        workflow.icon = workflow_in.icon
    if workflow_in.definition is not None:
        workflow.definition = workflow_in.definition
        workflow.version += 1  # Increment version on definition change
    if workflow_in.variables is not None:
        workflow.variables = workflow_in.variables
    if workflow_in.trigger_type is not None:
        workflow.trigger_type = workflow_in.trigger_type
    if workflow_in.trigger_config is not None:
        workflow.trigger_config = workflow_in.trigger_config

    await workflow.save()

    # Reload with relations
    workflow = await Workflow.get(id=workflow_id).prefetch_related("team", "created_by")

    return success(
        data=WorkflowOut.model_validate(workflow).model_dump(),
        msg_key="workflow_updated",
    )


@router.delete("/{workflow_id}", response_model=Response[dict])
async def delete_workflow(
    workflow_id: UUID,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """Delete a workflow and all its runs."""
    workflow = await check_workflow_access(workflow_id, current_user, require_write=True)

    # Delete workflow (cascades to runs and node executions)
    await workflow.delete()

    return success(data={"id": str(workflow_id)}, msg_key="workflow_deleted")


@router.post("/{workflow_id}/publish", response_model=Response[WorkflowOut])
async def publish_workflow(
    workflow_id: UUID,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """Publish a workflow."""
    workflow = await check_workflow_access(workflow_id, current_user, require_write=True)

    workflow.status = WorkflowStatus.PUBLISHED
    await workflow.save()

    return success(
        data=WorkflowOut.model_validate(workflow).model_dump(),
        msg_key="workflow_published",
    )


@router.post("/{workflow_id}/unpublish", response_model=Response[WorkflowOut])
async def unpublish_workflow(
    workflow_id: UUID,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """Unpublish a workflow."""
    workflow = await check_workflow_access(workflow_id, current_user, require_write=True)

    workflow.status = WorkflowStatus.DRAFT
    await workflow.save()

    return success(
        data=WorkflowOut.model_validate(workflow).model_dump(),
        msg_key="workflow_unpublished",
    )


@router.post("/{workflow_id}/duplicate", response_model=Response[WorkflowOut])
async def duplicate_workflow(
    workflow_id: UUID,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """Duplicate a workflow."""
    workflow = await check_workflow_access(workflow_id, current_user)

    # Create a copy
    new_workflow = await Workflow.create(
        name=f"{workflow.name} (Copy)",
        description=workflow.description,
        icon=workflow.icon,
        team_id=workflow.team_id,
        definition=workflow.definition,
        variables=workflow.variables,
        status=WorkflowStatus.DRAFT,
        trigger_type=workflow.trigger_type,
        trigger_config=workflow.trigger_config,
        created_by=current_user,
    )

    # Reload with relations
    new_workflow = await Workflow.get(id=new_workflow.id).prefetch_related(
        "team", "created_by"
    )

    return success(
        data=WorkflowOut.model_validate(new_workflow).model_dump(),
        msg_key="workflow_duplicated",
    )


@router.post("/{workflow_id}/regenerate-webhook-token", response_model=Response[dict])
async def regenerate_webhook_token(
    workflow_id: UUID,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """Regenerate webhook token for a workflow."""
    workflow = await check_workflow_access(workflow_id, current_user, require_write=True)

    workflow.webhook_token = secrets.token_urlsafe(32)
    await workflow.save()

    return success(
        data={"webhook_token": workflow.webhook_token},
        msg_key="webhook_token_regenerated",
    )


# ============ Workflow Runs ============


@router.get("/{workflow_id}/runs", response_model=Response[PageData[WorkflowRunListItem]])
async def list_workflow_runs(
    workflow_id: UUID,
    status: RunStatus | None = None,
    is_debug: bool | None = None,
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """List runs for a workflow."""
    await check_workflow_access(workflow_id, current_user)

    query = WorkflowRun.filter(workflow_id=workflow_id)

    if status:
        query = query.filter(status=status)

    if is_debug is not None:
        query = query.filter(is_debug=is_debug)

    total = await query.count()
    skip = (page - 1) * page_size
    runs = await query.offset(skip).limit(page_size).order_by("-created_at")

    run_list = [WorkflowRunListItem.model_validate(r) for r in runs]

    return success(
        data={
            "items": [r.model_dump() for r in run_list],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/runs/{run_id}", response_model=Response[WorkflowRunOut])
async def get_workflow_run(
    run_id: UUID,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """Get workflow run details."""
    run = await WorkflowRun.filter(id=run_id).prefetch_related("workflow").first()

    if not run:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="workflow_run_not_found",
            status_code=404,
        )

    # Check access through workflow
    await check_workflow_access(run.workflow.id, current_user)

    return success(data=WorkflowRunOut.model_validate(run).model_dump())


@router.get("/runs/{run_id}/nodes", response_model=Response[list[NodeExecutionOut]])
async def list_run_node_executions(
    run_id: UUID,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """Get all node executions for a run."""
    run = await WorkflowRun.filter(id=run_id).prefetch_related("workflow").first()

    if not run:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="workflow_run_not_found",
            status_code=404,
        )

    # Check access through workflow
    await check_workflow_access(run.workflow.id, current_user)

    executions = await NodeExecution.filter(run_id=run_id).order_by("execution_order")

    return success(
        data=[NodeExecutionOut.model_validate(e).model_dump() for e in executions]
    )


@router.delete("/runs/{run_id}", response_model=Response[dict])
async def delete_workflow_run(
    run_id: UUID,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """Delete a workflow run."""
    run = await WorkflowRun.filter(id=run_id).prefetch_related("workflow").first()

    if not run:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="workflow_run_not_found",
            status_code=404,
        )

    # Check write access through workflow
    await check_workflow_access(run.workflow.id, current_user, require_write=True)

    await run.delete()

    return success(data={"id": str(run_id)}, msg_key="workflow_run_deleted")
