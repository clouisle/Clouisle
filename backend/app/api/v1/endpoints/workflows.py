"""
Workflow API endpoints.
Provides CRUD operations for workflows and workflow runs.
"""

import logging
import secrets
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Header
from fastapi.responses import StreamingResponse
from tortoise.expressions import Q

from app.api import deps
from app.core.i18n import t
from app.core.timezone import now, to_local, to_utc
from app.models.user import User, Team, TeamMember
from app.models.workflow import (
    Workflow,
    WorkflowRun,
    WorkflowVersion,
    NodeExecution,
    WorkflowStatus,
    WorkflowVisibility,
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

    # Check visibility and team access
    if workflow.visibility == WorkflowVisibility.PRIVATE:
        # Only creator (or superuser) can access private workflows
        # If creator is deleted, fall back to team-level access
        if (
            workflow.created_by
            and workflow.created_by.id != user.id
            and not user.is_superuser
        ):
            raise BusinessError(
                code=ResponseCode.FORBIDDEN,
                msg_key="workflow_access_denied",
                status_code=403,
            )
        elif not workflow.created_by and not user.is_superuser:
            # Creator deleted, check team access
            await check_team_access(workflow.team.id, user, require_admin=require_write)
    else:
        # Team/public visibility - check team membership
        await check_team_access(workflow.team.id, user, require_admin=require_write)

    return workflow


# ============ Global Workflow Runs (must be before /{workflow_id} routes) ============


@router.get("/runs", response_model=Response[PageData[dict]])
async def list_all_workflow_runs(
    team_id: UUID | None = Query(None),
    workflow_id: UUID | None = Query(None),
    status: RunStatus | None = Query(None),
    trigger_type: TriggerType | None = Query(None),
    user_id: UUID | None = Query(None),
    is_debug: bool | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(deps.PermissionChecker("workflow:read")),
) -> Any:
    """
    List all workflow runs across workflows (admin endpoint).

    Supports filtering by:
    - team_id: Filter by team
    - workflow_id: Filter by specific workflow
    - status: Filter by run status
    - trigger_type: Filter by trigger type
    - user_id: Filter by triggered user
    - is_debug: Filter debug runs
    - search: Search workflow names
    """
    # Get workflows user has access to
    workflow_query = Workflow.all()

    if team_id:
        await check_team_access(team_id, current_user)
        workflow_query = workflow_query.filter(team_id=team_id)
    elif not current_user.is_superuser:
        # Get teams user belongs to
        memberships = await TeamMember.filter(user=current_user).values_list(
            "team_id", flat=True
        )
        workflow_query = workflow_query.filter(team_id__in=memberships)

    # Apply search filter on workflows
    if search:
        workflow_query = workflow_query.filter(name__icontains=search)

    accessible_workflows = await workflow_query.all()
    workflow_ids = [w.id for w in accessible_workflows]

    if not workflow_ids:
        return success(
            data={"items": [], "total": 0, "page": page, "page_size": page_size}
        )

    # Build query for runs
    query = WorkflowRun.filter(workflow_id__in=workflow_ids)

    # Apply filters
    if workflow_id:
        query = query.filter(workflow_id=workflow_id)
    if status:
        query = query.filter(status=status)
    if trigger_type:
        query = query.filter(trigger_type=trigger_type)
    if user_id:
        query = query.filter(triggered_by_id=user_id)
    if is_debug is not None:
        query = query.filter(is_debug=is_debug)

    # Get total and paginate
    total = await query.count()
    skip = (page - 1) * page_size
    runs = (
        await query.select_related("workflow", "triggered_by")
        .order_by("-created_at")
        .offset(skip)
        .limit(page_size)
    )

    # Build response with workflow info
    items = []
    for run in runs:
        item = WorkflowRunListItem.model_validate(run).model_dump()
        item["workflow_name"] = run.workflow.name
        item["workflow_icon"] = run.workflow.icon
        item["triggered_by_name"] = (
            run.triggered_by.username if run.triggered_by else None
        )
        items.append(item)

    return success(
        data={"items": items, "total": total, "page": page, "page_size": page_size},
        msg_key="workflow_runs_fetched",
    )


@router.get("/runs/stats", response_model=Response[dict])
async def get_workflow_run_stats(
    team_id: UUID | None = Query(None),
    current_user: User = Depends(deps.PermissionChecker("workflow:read")),
) -> Any:
    """
    Get workflow run statistics.

    Returns:
    - total_runs: Total number of runs
    - runs_by_status: Count by status
    - runs_by_workflow: Top 10 workflows by run count
    - avg_duration_ms: Average execution duration
    """
    # Get workflows user has access to
    workflow_query = Workflow.all()

    if team_id:
        await check_team_access(team_id, current_user)
        workflow_query = workflow_query.filter(team_id=team_id)
    elif not current_user.is_superuser:
        # Get teams user belongs to
        memberships = await TeamMember.filter(user=current_user).values_list(
            "team_id", flat=True
        )
        workflow_query = workflow_query.filter(team_id__in=memberships)

    accessible_workflows = await workflow_query.all()
    workflow_ids = [w.id for w in accessible_workflows]

    if not workflow_ids:
        return success(
            data={
                "total_runs": 0,
                "runs_by_status": {},
                "runs_by_workflow": [],
                "avg_duration_ms": 0,
            },
            msg_key="workflow_run_stats_fetched",
        )

    # Get all runs for accessible workflows
    runs = await WorkflowRun.filter(workflow_id__in=workflow_ids).all()

    # Calculate statistics
    total_runs = len(runs)

    # Runs by status
    runs_by_status = {}
    for run in runs:
        status_key = run.status.value
        runs_by_status[status_key] = runs_by_status.get(status_key, 0) + 1

    # Runs by workflow (top 10)
    workflow_counts = {}
    for run in runs:
        workflow_counts[run.workflow_id] = workflow_counts.get(run.workflow_id, 0) + 1

    # Sort and get top 10
    top_workflows = sorted(workflow_counts.items(), key=lambda x: x[1], reverse=True)[
        :10
    ]

    # Build workflow info
    workflow_map = {w.id: w for w in accessible_workflows}
    runs_by_workflow = []
    for workflow_id, count in top_workflows:
        workflow = workflow_map.get(workflow_id)
        if workflow:
            runs_by_workflow.append(
                {
                    "workflow_id": str(workflow_id),
                    "workflow_name": workflow.name,
                    "workflow_icon": workflow.icon,
                    "count": count,
                }
            )

    # Calculate average duration (only for completed runs)
    completed_runs = [
        r
        for r in runs
        if r.status == RunStatus.SUCCESS and r.started_at and r.finished_at
    ]
    if completed_runs:
        total_duration_ms = sum(
            int((r.finished_at - r.started_at).total_seconds() * 1000)
            for r in completed_runs
        )
        avg_duration_ms = total_duration_ms // len(completed_runs)
    else:
        avg_duration_ms = 0

    return success(
        data={
            "total_runs": total_runs,
            "runs_by_status": runs_by_status,
            "runs_by_workflow": runs_by_workflow,
            "avg_duration_ms": avg_duration_ms,
        },
        msg_key="workflow_run_stats_fetched",
    )


# ============ Workflow CRUD ============


@router.get("", response_model=Response[PageData[WorkflowListItem]])
async def list_workflows(
    team_id: UUID | None = None,
    status: WorkflowStatus | None = None,
    trigger_type: TriggerType | None = None,
    visibility: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(deps.PermissionChecker("workflow:read")),
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
        # Apply visibility filtering for non-superusers
        if not current_user.is_superuser:
            query = query.filter(
                Q(
                    visibility__in=[
                        WorkflowVisibility.TEAM,
                        WorkflowVisibility.PUBLIC,
                    ],
                )
                | Q(
                    created_by=current_user,
                    visibility=WorkflowVisibility.PRIVATE,
                )
            )
    elif not current_user.is_superuser:
        # Get teams user belongs to
        memberships = await TeamMember.filter(user=current_user).values_list(
            "team_id", flat=True
        )
        # Show team/public workflows + own private workflows
        query = query.filter(
            Q(
                team_id__in=memberships,
                visibility__in=[
                    WorkflowVisibility.TEAM,
                    WorkflowVisibility.PUBLIC,
                ],
            )
            | Q(
                created_by=current_user,
                visibility=WorkflowVisibility.PRIVATE,
            )
        )

    if status:
        query = query.filter(status=status)

    if trigger_type:
        query = query.filter(trigger_type=trigger_type)

    if visibility:
        query = query.filter(visibility=visibility)

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


@router.post("", response_model=Response[WorkflowOut])
async def create_workflow(
    *,
    workflow_in: WorkflowCreate,
    current_user: User = Depends(deps.PermissionChecker("workflow:create")),
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
                    "label": t("node_label_start"),
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
        visibility=workflow_in.visibility,
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
    current_user: User = Depends(deps.PermissionChecker("workflow:read")),
) -> Any:
    """Get workflow by ID."""
    workflow = await check_workflow_access(workflow_id, current_user)
    return success(data=WorkflowOut.model_validate(workflow).model_dump())


@router.get("/{workflow_id}/stats", response_model=Response[dict])
async def get_workflow_stats(
    workflow_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("workflow:read")),
) -> Any:
    """
    Get statistics for a specific workflow.

    Returns:
    - total_runs: Total number of runs
    - success_count: Number of successful runs
    - failed_count: Number of failed runs
    - timeout_count: Number of timeout runs
    - avg_duration_ms: Average execution duration
    - last_run_at: Last run timestamp
    """
    await check_workflow_access(workflow_id, current_user)

    # Get all runs for this workflow
    runs = await WorkflowRun.filter(workflow_id=workflow_id).all()

    total_runs = len(runs)

    if total_runs == 0:
        return success(
            data={
                "total_runs": 0,
                "success_count": 0,
                "failed_count": 0,
                "timeout_count": 0,
                "avg_duration_ms": 0,
                "last_run_at": None,
            }
        )

    # Calculate statistics
    success_count = sum(1 for r in runs if r.status == RunStatus.SUCCESS)
    failed_count = sum(1 for r in runs if r.status == RunStatus.FAILED)
    timeout_count = sum(1 for r in runs if r.status == RunStatus.TIMEOUT)

    # Calculate average duration (only for completed runs)
    completed_runs = [r for r in runs if r.total_duration_ms is not None]
    avg_duration_ms = (
        sum(r.total_duration_ms for r in completed_runs) / len(completed_runs)
        if completed_runs
        else 0
    )

    # Get last run timestamp
    last_run = max(runs, key=lambda r: r.created_at)
    last_run_at = last_run.created_at.isoformat() if last_run else None

    return success(
        data={
            "total_runs": total_runs,
            "success_count": success_count,
            "failed_count": failed_count,
            "timeout_count": timeout_count,
            "avg_duration_ms": round(avg_duration_ms, 2),
            "last_run_at": last_run_at,
        }
    )


@router.get("/{workflow_id}/stats/trends", response_model=Response[dict])
async def get_workflow_trends(
    workflow_id: UUID,
    period: str = Query("7d", description="Time period: 7d, 30d"),
    current_user: User = Depends(deps.PermissionChecker("workflow:read")),
) -> Any:
    """
    Get workflow execution trends over time.

    Returns daily statistics for:
    - runs: Number of runs per day
    - success: Number of successful runs per day
    - failed: Number of failed runs per day
    - avgDuration: Average execution duration per day
    """
    await check_workflow_access(workflow_id, current_user)

    now_local = now()

    # Determine time range
    if period == "30d":
        start_time = now_local - timedelta(days=30)
        num_points = 30
    else:  # Default to 7d
        start_time = now_local - timedelta(days=7)
        num_points = 7

    start_time_utc = to_utc(start_time)

    # Get all runs in the period
    runs = await WorkflowRun.filter(
        workflow_id=workflow_id, created_at__gte=start_time_utc
    ).all()

    # Build time series data grouped by day
    data_points = []
    for i in range(num_points):
        point_date = (now_local - timedelta(days=num_points - i - 1)).date()
        point_start = datetime.combine(point_date, datetime.min.time()).replace(
            tzinfo=now_local.tzinfo
        )
        point_end = point_start + timedelta(days=1)

        # Filter runs for this day
        runs_in_day = [
            r for r in runs if point_start <= to_local(r.created_at) < point_end
        ]

        # Count by status
        total_runs = len(runs_in_day)
        success_count = sum(1 for r in runs_in_day if r.status == RunStatus.SUCCESS)
        failed_count = sum(1 for r in runs_in_day if r.status == RunStatus.FAILED)

        # Calculate average duration for completed runs
        completed_runs = [r for r in runs_in_day if r.total_duration_ms is not None]
        avg_duration = (
            sum(r.total_duration_ms for r in completed_runs) / len(completed_runs)
            if completed_runs
            else 0
        )

        # Format label
        label = point_date.strftime("%m/%d")

        data_points.append(
            {
                "date": label,
                "runs": total_runs,
                "success": success_count,
                "failed": failed_count,
                "avgDuration": round(avg_duration, 2),
            }
        )

    return success(
        data={
            "period": period,
            "data": data_points,
        }
    )


@router.put("/{workflow_id}", response_model=Response[WorkflowOut])
async def update_workflow(
    *,
    workflow_id: UUID,
    workflow_in: WorkflowUpdate,
    current_user: User = Depends(deps.PermissionChecker("workflow:update")),
) -> Any:
    """Update a workflow."""
    workflow = await check_workflow_access(
        workflow_id, current_user, require_write=True
    )

    # Check for duplicate name within the same team (exclude self)
    if workflow_in.name is not None and workflow_in.name != workflow.name:
        existing = (
            await Workflow.filter(
                team_id=workflow.team_id,
                name=workflow_in.name,
            )
            .exclude(id=workflow_id)
            .first()
        )
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
    if workflow_in.visibility is not None:
        workflow.visibility = WorkflowVisibility(workflow_in.visibility)

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
    current_user: User = Depends(deps.PermissionChecker("workflow:delete")),
) -> Any:
    """Delete a workflow and all its runs."""
    workflow = await check_workflow_access(
        workflow_id, current_user, require_write=True
    )

    # Delete workflow (cascades to runs and node executions)
    await workflow.delete()

    return success(data={"id": str(workflow_id)}, msg_key="workflow_deleted")


@router.post("/{workflow_id}/publish", response_model=Response[WorkflowOut])
async def publish_workflow(
    workflow_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("workflow:publish")),
) -> Any:
    """Publish a workflow and save a version snapshot."""
    workflow = await check_workflow_access(
        workflow_id, current_user, require_write=True
    )

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
            description=t("workflow_published_version_desc"),
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
    current_user: User = Depends(deps.PermissionChecker("workflow:publish")),
) -> Any:
    """Unpublish a workflow."""
    workflow = await check_workflow_access(
        workflow_id, current_user, require_write=True
    )

    workflow.status = WorkflowStatus.DRAFT
    await workflow.save()

    return success(
        data=WorkflowOut.model_validate(workflow).model_dump(),
        msg_key="workflow_unpublished",
    )


@router.post("/{workflow_id}/duplicate", response_model=Response[WorkflowOut])
async def duplicate_workflow(
    workflow_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("workflow:create")),
) -> Any:
    """Duplicate a workflow."""
    workflow = await check_workflow_access(workflow_id, current_user)

    # Create a copy
    new_workflow = await Workflow.create(
        name=t("workflow_copy_suffix", name=workflow.name),
        description=workflow.description,
        icon=workflow.icon,
        team_id=workflow.team_id,
        definition=workflow.definition,
        variables=workflow.variables,
        status=WorkflowStatus.DRAFT,
        trigger_type=workflow.trigger_type,
        trigger_config=workflow.trigger_config,
        visibility=WorkflowVisibility.PRIVATE,  # Copy is always private
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
    current_user: User = Depends(deps.PermissionChecker("workflow:update")),
) -> Any:
    """Regenerate webhook token for a workflow."""
    workflow = await check_workflow_access(
        workflow_id, current_user, require_write=True
    )

    workflow.webhook_token = secrets.token_urlsafe(32)
    await workflow.save()

    return success(
        data={"webhook_token": workflow.webhook_token},
        msg_key="webhook_token_regenerated",
    )


# ============ Webhook API (Public) ============


@router.post("/webhook/{webhook_token}", response_model=Response[dict])
async def trigger_workflow_webhook(
    webhook_token: str,
    inputs: dict[str, Any],
    authorization: str | None = Header(None),
) -> Any:
    """
    Webhook endpoint to trigger workflow execution.

    Requires API key authentication via Authorization header.
    Format: Authorization: Bearer clou_xxxxx

    Args:
        webhook_token: The workflow's webhook token
        inputs: Input parameters for the workflow
        authorization: API key in Authorization header

    Returns:
        run_id and stream_url for tracking execution
    """
    from app.tasks.workflow import run_workflow_task
    from app.api.deps import _authenticate_api_key

    # Verify API key is provided
    if not authorization:
        raise BusinessError(
            code=ResponseCode.UNAUTHORIZED,
            msg_key="api_key_required",
            status_code=401,
        )

    # Extract API key from Authorization header
    api_key_str = None
    if authorization.startswith("Bearer "):
        api_key_str = authorization[7:]
    else:
        api_key_str = authorization

    # Verify it's an API key (starts with clou_)
    if not api_key_str or not api_key_str.startswith("clou_"):
        raise BusinessError(
            code=ResponseCode.UNAUTHORIZED,
            msg_key="invalid_api_key_format",
            status_code=401,
        )

    # Authenticate API key and get user
    try:
        user, api_key = await _authenticate_api_key(api_key_str)
    except BusinessError:
        raise
    except Exception as e:
        logger.exception(f"API key authentication error: {e}")
        raise BusinessError(
            code=ResponseCode.UNAUTHORIZED,
            msg_key="api_key_authentication_failed",
            status_code=401,
        )

    # Find workflow by webhook token using constant-time comparison
    workflow = (
        await Workflow.filter(webhook_token__isnull=False)
        .prefetch_related("team")
        .all()
    )

    matched_workflow = None
    for wf in workflow:
        if wf.webhook_token and secrets.compare_digest(wf.webhook_token, webhook_token):
            matched_workflow = wf
            break

    if not matched_workflow:
        raise BusinessError(
            code=ResponseCode.FORBIDDEN,
            msg_key="invalid_webhook_token",
            status_code=403,
        )

    # Verify workflow is published
    if matched_workflow.status != WorkflowStatus.PUBLISHED:
        raise BusinessError(
            code=ResponseCode.FORBIDDEN,
            msg_key="workflow_not_published",
            status_code=403,
        )

    # Verify webhook trigger is enabled
    if matched_workflow.trigger_type != TriggerType.WEBHOOK:
        raise BusinessError(
            code=ResponseCode.FORBIDDEN,
            msg_key="webhook_trigger_disabled",
            status_code=403,
        )

    # Verify API key has permission to access this workflow
    if api_key:
        # Get workflows this API key can access
        allowed_workflows = await api_key.workflows.all()
        allowed_workflow_ids = [wf.id for wf in allowed_workflows]

        # If API key has specific workflow restrictions, check permission
        if allowed_workflow_ids and matched_workflow.id not in allowed_workflow_ids:
            raise BusinessError(
                code=ResponseCode.FORBIDDEN,
                msg_key="api_key_no_workflow_access",
                status_code=403,
            )

    try:
        # Create run record with authenticated user
        run = await WorkflowRun.create(
            workflow_id=matched_workflow.id,
            trigger_type=TriggerType.WEBHOOK,
            triggered_by_id=user.id,  # Record the API key owner as caller
            is_debug=False,
            status=RunStatus.PENDING,
            inputs=inputs,
        )

        # Submit to Celery for background execution
        run_workflow_task.delay(
            run_id=str(run.id),
            workflow_id=str(matched_workflow.id),
            inputs=inputs,
            user_id=str(user.id),  # Pass user ID for execution context
            team_id=str(matched_workflow.team_id) if matched_workflow.team_id else None,
        )

        return success(
            data={
                "run_id": str(run.id),
                "status": "pending",
                "stream_url": f"/api/v1/workflows/runs/{run.id}/stream",
            },
            msg_key="workflow_triggered",
        )

    except Exception as e:
        logger.exception(f"Webhook execution error: {e}")
        raise BusinessError(
            code=ResponseCode.INTERNAL_ERROR,
            msg_key="workflow_execution_error",
        )


# ============ Workflow Execution ============


@router.post("/{workflow_id}/run", response_model=Response[dict])
async def run_workflow(
    workflow_id: UUID,
    run_request: WorkflowRunRequest,
    current_user: User = Depends(deps.PermissionChecker("workflow:run")),
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
    current_user: User = Depends(deps.PermissionChecker("workflow:run")),
) -> Any:
    """
    Run a workflow in debug mode (uses current draft, not published version).

    Returns the run ID. Use GET /runs/{run_id}/stream for streaming output.
    """
    from app.tasks.workflow import run_workflow_task

    workflow = await check_workflow_access(
        workflow_id, current_user, require_write=True
    )

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
    current_user: User | None = Depends(deps.get_current_user_optional),
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

    # Check access: allow if webhook trigger (no user) or user has access to workflow
    if run.triggered_by_id is not None:
        # User-triggered run, check access
        if not current_user:
            raise BusinessError(
                code=ResponseCode.UNAUTHORIZED,
                msg_key="unauthorized",
                status_code=401,
            )
        await check_workflow_access(run.workflow.id, current_user)
    # Webhook-triggered runs (triggered_by_id is None) are publicly accessible

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
    current_user: User = Depends(deps.PermissionChecker("workflow:run")),
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
        return success(
            data={"cancelled": False}, msg_key="workflow_run_not_cancellable"
        )


# ============ Workflow Runs ============


@router.get(
    "/{workflow_id}/runs", response_model=Response[PageData[WorkflowRunListItem]]
)
async def list_workflow_runs(
    workflow_id: UUID,
    status: RunStatus | None = None,
    is_debug: bool | None = None,
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(deps.PermissionChecker("workflow:read")),
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
    current_user: User = Depends(deps.PermissionChecker("workflow:read")),
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
    current_user: User = Depends(deps.PermissionChecker("workflow:read")),
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
    current_user: User = Depends(deps.PermissionChecker("workflow:delete")),
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


@router.get(
    "/{workflow_id}/versions",
    response_model=Response[PageData[WorkflowVersionListItem]],
)
async def list_workflow_versions(
    workflow_id: UUID,
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(deps.PermissionChecker("workflow:read")),
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


@router.get(
    "/{workflow_id}/versions/{version}", response_model=Response[WorkflowVersionOut]
)
async def get_workflow_version(
    workflow_id: UUID,
    version: int,
    current_user: User = Depends(deps.PermissionChecker("workflow:read")),
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

    return success(
        data=WorkflowVersionOut.model_validate(workflow_version).model_dump()
    )


@router.post("/{workflow_id}/versions", response_model=Response[WorkflowVersionOut])
async def create_workflow_version(
    workflow_id: UUID,
    version_in: WorkflowVersionCreate,
    current_user: User = Depends(deps.PermissionChecker("workflow:update")),
) -> Any:
    """Manually create a version snapshot of the current workflow state."""
    workflow = await check_workflow_access(
        workflow_id, current_user, require_write=True
    )

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


@router.post(
    "/{workflow_id}/versions/{version}/restore", response_model=Response[WorkflowOut]
)
async def restore_workflow_version(
    workflow_id: UUID,
    version: int,
    restore_in: WorkflowVersionRestore,
    current_user: User = Depends(deps.PermissionChecker("workflow:update")),
) -> Any:
    """Restore a workflow to a specific version."""
    workflow = await check_workflow_access(
        workflow_id, current_user, require_write=True
    )

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
        description=t("workflow_auto_saved_before_restore", version=version),
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
        description=restore_in.description
        or t("workflow_restored_from_version", version=version),
        created_by=current_user,
    )

    # Reload with relations
    workflow = await Workflow.get(id=workflow_id).prefetch_related("team", "created_by")

    return success(
        data=WorkflowOut.model_validate(workflow).model_dump(),
        msg_key="workflow_version_restored",
    )
