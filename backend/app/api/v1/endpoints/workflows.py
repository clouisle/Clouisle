"""
Workflow API endpoints.
Provides CRUD operations for workflows and workflow runs.
"""

import logging
import secrets
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from tortoise.expressions import Q

from app.api import deps
from app.models.user import User, Team, TeamMember
from app.models.workflow import (
    Workflow,
    WorkflowRun,
    WorkflowVersion,
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
    WorkflowRunRequest,
    WorkflowRunOut,
    WorkflowRunListItem,
    NodeExecutionOut,
    WorkflowVersionOut,
    WorkflowVersionListItem,
    WorkflowVersionCreate,
    WorkflowVersionRestore,
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

    # Check for duplicate name within the same team
    existing = await Workflow.filter(
        team_id=workflow_in.team_id,
        name=workflow_in.name,
    ).first()
    if existing:
        raise BusinessError(
            code=ResponseCode.DUPLICATE_NAME,
            msg_key="workflow_name_exists",
        )

    # Create workflow with default start node (user_input)
    default_definition = {
        "nodes": [
            {
                "id": "user_input-1",
                "type": "user_input",
                "position": {"x": 250, "y": 100},
                "data": {
                    "type": "user_input",
                    "label": "开始",
                    "config": {},
                    "parameters": [
                        {
                            "id": "query",
                            "name": "query",
                            "type": "text",
                            "required": True,
                        }
                    ],
                },
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

    # Check for duplicate name within the same team (exclude self)
    if workflow_in.name is not None and workflow_in.name != workflow.name:
        existing = await Workflow.filter(
            team_id=workflow.team_id,
            name=workflow_in.name,
        ).exclude(id=workflow_id).first()
        if existing:
            raise BusinessError(
                code=ResponseCode.DUPLICATE_NAME,
                msg_key="workflow_name_exists",
            )

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
    """Publish a workflow and save a version snapshot."""
    workflow = await check_workflow_access(workflow_id, current_user, require_write=True)

    # Check if this version already has a snapshot
    existing_version = await WorkflowVersion.filter(
        workflow_id=workflow_id, version=workflow.version
    ).first()

    # Save version snapshot on publish (if not already saved)
    if not existing_version:
        await WorkflowVersion.create(
            workflow_id=workflow_id,
            version=workflow.version,
            definition=workflow.definition,
            variables=workflow.variables,
            trigger_type=workflow.trigger_type,
            trigger_config=workflow.trigger_config,
            description="Published version",
            created_by=current_user,
        )

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


# ============ Workflow Execution ============


@router.post("/{workflow_id}/run", response_model=Response[dict])
async def run_workflow(
    workflow_id: UUID,
    run_request: WorkflowRunRequest,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Run a workflow with the given inputs.

    Returns the run ID. Use GET /runs/{run_id}/stream for streaming output.
    """
    from app.tasks.workflow import run_workflow_task

    workflow = await check_workflow_access(workflow_id, current_user)

    # Check if workflow is published
    if workflow.status != WorkflowStatus.PUBLISHED:
        raise BusinessError(
            code=ResponseCode.FORBIDDEN,
            msg_key="workflow_not_published",
            status_code=403,
        )

    try:
        # Create run record first
        run = await WorkflowRun.create(
            workflow_id=workflow_id,
            trigger_type=workflow.trigger_type,
            triggered_by_id=current_user.id,
            is_debug=False,
            status=RunStatus.PENDING,
            inputs=run_request.inputs,
        )

        # Submit to Celery for background execution
        run_workflow_task.delay(
            run_id=str(run.id),
            workflow_id=str(workflow_id),
            inputs=run_request.inputs,
            user_id=str(current_user.id),
            team_id=str(workflow.team_id) if workflow.team_id else None,
        )

        return success(
            data={
                "run_id": str(run.id),
                "stream_url": f"/api/v1/workflows/runs/{run.id}/stream",
            },
            msg_key="workflow_run_started",
        )

    except Exception as e:
        logger.exception(f"Workflow execution error: {e}")
        raise BusinessError(
            code=ResponseCode.INTERNAL_ERROR,
            msg_key="workflow_execution_error",
        )


@router.post("/{workflow_id}/debug", response_model=Response[dict])
async def debug_workflow(
    workflow_id: UUID,
    run_request: WorkflowRunRequest,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Run a workflow in debug mode (uses current draft, not published version).

    Returns the run ID. Use GET /runs/{run_id}/stream for streaming output.
    """
    from app.tasks.workflow import run_workflow_task

    workflow = await check_workflow_access(workflow_id, current_user, require_write=True)

    try:
        # Create run record first
        run = await WorkflowRun.create(
            workflow_id=workflow_id,
            trigger_type=workflow.trigger_type,
            triggered_by_id=current_user.id,
            is_debug=True,
            status=RunStatus.PENDING,
            inputs=run_request.inputs,
        )

        # Submit to Celery for background execution
        run_workflow_task.delay(
            run_id=str(run.id),
            workflow_id=str(workflow_id),
            inputs=run_request.inputs,
            user_id=str(current_user.id),
            team_id=str(workflow.team_id) if workflow.team_id else None,
            is_debug=True,
        )

        return success(
            data={
                "run_id": str(run.id),
                "stream_url": f"/api/v1/workflows/runs/{run.id}/stream",
            },
            msg_key="workflow_debug_started",
        )

    except Exception as e:
        logger.exception(f"Workflow debug error: {e}")
        raise BusinessError(
            code=ResponseCode.INTERNAL_ERROR,
            msg_key="workflow_execution_error",
        )


@router.get("/runs/{run_id}/stream")
async def stream_workflow_run(
    run_id: UUID,
    from_sequence: int = 0,
    current_user: User = Depends(deps.get_current_active_user),
) -> StreamingResponse:
    """
    Stream workflow execution events via SSE (Server-Sent Events).

    Query params:
    - from_sequence: Resume from this sequence number (for reconnection)

    Event types:
    - workflow_start: Workflow execution started
    - workflow_complete: Workflow completed successfully
    - workflow_error: Workflow failed
    - node_start: Node execution started
    - node_complete: Node completed
    - node_error: Node failed
    - node_skip: Node skipped (branch not taken)
    - token: LLM token stream
    - output: Final output
    """
    from app.services.workflow.stream import stream_to_sse

    # Verify access to the run
    run = await WorkflowRun.filter(id=run_id).prefetch_related("workflow").first()
    if not run:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="workflow_run_not_found",
            status_code=404,
        )

    await check_workflow_access(run.workflow.id, current_user)

    async def event_generator():
        async for event in stream_to_sse(str(run_id), from_sequence):
            yield event

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/runs/{run_id}/cancel", response_model=Response[dict])
async def cancel_workflow_run(
    run_id: UUID,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """Cancel a running workflow."""
    from app.services.workflow import WorkflowOrchestrator

    run = await WorkflowRun.filter(id=run_id).prefetch_related("workflow").first()
    if not run:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="workflow_run_not_found",
            status_code=404,
        )

    await check_workflow_access(run.workflow.id, current_user, require_write=True)

    orchestrator = WorkflowOrchestrator()
    cancelled = await orchestrator.cancel(str(run_id))

    if cancelled:
        return success(data={"cancelled": True}, msg_key="workflow_run_cancelled")
    else:
        return success(data={"cancelled": False}, msg_key="workflow_run_not_cancellable")


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


# ============ Workflow Versions ============


@router.get("/{workflow_id}/versions", response_model=Response[PageData[WorkflowVersionListItem]])
async def list_workflow_versions(
    workflow_id: UUID,
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """List version history for a workflow."""
    await check_workflow_access(workflow_id, current_user)

    query = WorkflowVersion.filter(workflow_id=workflow_id)

    total = await query.count()
    skip = (page - 1) * page_size
    versions = await query.offset(skip).limit(page_size).order_by("-version")

    version_list = [WorkflowVersionListItem.model_validate(v) for v in versions]

    return success(
        data={
            "items": [v.model_dump() for v in version_list],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/{workflow_id}/versions/{version}", response_model=Response[WorkflowVersionOut])
async def get_workflow_version(
    workflow_id: UUID,
    version: int,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """Get a specific version of a workflow."""
    await check_workflow_access(workflow_id, current_user)

    workflow_version = await WorkflowVersion.filter(
        workflow_id=workflow_id, version=version
    ).first()

    if not workflow_version:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="workflow_version_not_found",
            status_code=404,
        )

    return success(data=WorkflowVersionOut.model_validate(workflow_version).model_dump())


@router.post("/{workflow_id}/versions", response_model=Response[WorkflowVersionOut])
async def create_workflow_version(
    workflow_id: UUID,
    version_in: WorkflowVersionCreate,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """Manually create a version snapshot of the current workflow state."""
    workflow = await check_workflow_access(workflow_id, current_user, require_write=True)

    # Create version snapshot
    workflow_version = await WorkflowVersion.create(
        workflow_id=workflow_id,
        version=workflow.version,
        definition=workflow.definition,
        variables=workflow.variables,
        trigger_type=workflow.trigger_type,
        trigger_config=workflow.trigger_config,
        description=version_in.description,
        created_by=current_user,
    )

    return success(
        data=WorkflowVersionOut.model_validate(workflow_version).model_dump(),
        msg_key="workflow_version_created",
    )


@router.post("/{workflow_id}/versions/{version}/restore", response_model=Response[WorkflowOut])
async def restore_workflow_version(
    workflow_id: UUID,
    version: int,
    restore_in: WorkflowVersionRestore,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """Restore a workflow to a specific version."""
    workflow = await check_workflow_access(workflow_id, current_user, require_write=True)

    # Get the version to restore
    workflow_version = await WorkflowVersion.filter(
        workflow_id=workflow_id, version=version
    ).first()

    if not workflow_version:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="workflow_version_not_found",
            status_code=404,
        )

    # Save current state as a new version before restoring
    await WorkflowVersion.create(
        workflow_id=workflow_id,
        version=workflow.version,
        definition=workflow.definition,
        variables=workflow.variables,
        trigger_type=workflow.trigger_type,
        trigger_config=workflow.trigger_config,
        description=f"Auto-saved before restoring to v{version}",
        created_by=current_user,
    )

    # Restore the workflow to the specified version
    workflow.definition = workflow_version.definition
    workflow.variables = workflow_version.variables
    workflow.trigger_type = workflow_version.trigger_type
    workflow.trigger_config = workflow_version.trigger_config
    workflow.version += 1  # Increment version

    await workflow.save()

    # Create a version record for the restored state
    await WorkflowVersion.create(
        workflow_id=workflow_id,
        version=workflow.version,
        definition=workflow.definition,
        variables=workflow.variables,
        trigger_type=workflow.trigger_type,
        trigger_config=workflow.trigger_config,
        description=restore_in.description or f"Restored from v{version}",
        created_by=current_user,
    )

    # Reload with relations
    workflow = await Workflow.get(id=workflow_id).prefetch_related("team", "created_by")

    return success(
        data=WorkflowOut.model_validate(workflow).model_dump(),
        msg_key="workflow_version_restored",
    )
