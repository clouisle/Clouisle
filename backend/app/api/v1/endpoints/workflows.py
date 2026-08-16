"""
Workflow API endpoints.
Provides CRUD operations for workflows and workflow runs.
"""

import logging
import secrets
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Header, Request
from fastapi.responses import StreamingResponse
from tortoise.expressions import Q
from tortoise.transactions import in_transaction

from app.api import deps
from app.api.team_access import check_team_access
from app.api.workflow_access import check_workflow_access
from app.core.i18n import t
from app.core.timezone import now, to_local, to_utc
from app.models.user import User, TeamMember
from app.models.workflow import (
    Workflow,
    WorkflowRun,
    WorkflowVersion,
    NodeExecution,
    WorkflowPauseRequest,
    PauseRequestStatus,
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
    PauseRequestSubmitRequest,
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
from app.services.audit_log import AuditLogService
from app.services.error_messages import is_safe_user_visible_error
from app.services.workflow.errors import (
    get_public_workflow_error_key,
    translate_public_workflow_error,
)
from app.services.workflow.pause_approvers import (
    remove_pause_pending_notification_for,
    remove_pause_pending_notifications,
    resolve_pause_approver_ids,
    validate_pause_approvers,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ============ Helper Functions ============


def normalize_webhook_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    """Accept both raw webhook inputs and {"inputs": {...}} payloads."""
    nested_inputs = inputs.get("inputs")
    if len(inputs) == 1 and isinstance(nested_inputs, dict):
        return nested_inputs
    return inputs


def get_pause_request_config(
    run: WorkflowRun, pause_request: WorkflowPauseRequest
) -> dict[str, Any] | None:
    """Return the pause-node config pinned when this run first started."""
    snapshot = getattr(run, "context_snapshot", {}) or {}
    definition = snapshot.get("workflow_definition")
    if not isinstance(definition, dict):
        return None
    nodes = definition.get("nodes")
    if not isinstance(nodes, list):
        return None
    node = next(
        (
            item
            for item in nodes
            if isinstance(item, dict) and item.get("id") == pause_request.node_id
        ),
        None,
    )
    if not isinstance(node, dict):
        return None
    data = node.get("data")
    if not isinstance(data, dict):
        return None
    config = data.get("pauseConfig") or data.get("config")
    return config if isinstance(config, dict) else None


def pause_submission_is_valid(
    config: dict[str, Any], mode: str, values: dict[str, Any]
) -> bool:
    """Validate submitted values against the pause node's pinned schema."""
    if mode == "approval":
        return values.get("decision") in {"approved", "rejected"}

    expected_type: dict[str, type[Any] | tuple[type[Any], ...]] = {
        "string": str,
        "text": str,
        "paragraph": str,
        "select": str,
        "file": str,
        "image": str,
        "number": (int, float),
        "boolean": bool,
        "checkbox": bool,
        "array": list,
        "files": list,
        "images": list,
        "object": dict,
    }
    variables = config.get("inputVariables") or []
    if not isinstance(variables, list):
        return False
    for variable in variables:
        if not isinstance(variable, dict):
            return False
        name = variable.get("name")
        if not isinstance(name, str) or not name:
            return False
        value = values.get(name)
        if variable.get("required") and (
            value is None
            or (isinstance(value, str) and not value.strip())
            or (isinstance(value, (list, dict)) and not value)
        ):
            return False
        if value is None:
            continue
        value_type = str(variable.get("type") or "string")
        # Cleared optional number inputs submit ""; treat them as not provided.
        if value_type == "number" and value == "":
            continue
        expected = expected_type.get(value_type)
        if expected is None or not isinstance(value, expected):
            return False
        # bool is an int subclass, but is not a valid number submission.
        if value_type == "number" and isinstance(value, bool):
            return False
    return True


# ============ Global Workflow Runs (must be before /{workflow_id} routes) ============


def sanitize_public_workflow_error(error_message: str | None) -> str | None:
    if not error_message:
        return None

    if get_public_workflow_error_key(error_message):
        return translate_public_workflow_error(error_message)

    if is_safe_user_visible_error(error_message):
        return error_message

    return t("workflow_execution_error")


def sanitize_workflow_run_payload(payload: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(payload)
    sanitized["error_message"] = sanitize_public_workflow_error(
        sanitized.get("error_message")
    )
    return sanitized


def sanitize_node_execution_payload(payload: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(payload)
    sanitized["error_message"] = sanitize_public_workflow_error(
        sanitized.get("error_message")
    )
    return sanitized


@router.get("/runs", response_model=Response[PageData[dict]])
async def list_all_workflow_runs(
    team_id: list[UUID] | None = Query(None),
    workflow_id: list[UUID] | None = Query(None),
    status: list[RunStatus] | None = Query(None),
    trigger_type: list[TriggerType] | None = Query(None),
    user_id: list[UUID] | None = Query(None),
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
        for current_team_id in team_id:
            await check_team_access(current_team_id, current_user)
        workflow_query = workflow_query.filter(team_id__in=team_id)
    elif not current_user.is_superuser:
        # Get teams user belongs to
        memberships = await TeamMember.filter(user=current_user).values_list(
            "team_id", flat=True
        )
        workflow_query = workflow_query.filter(team_id__in=memberships)

    # Apply search filter on workflows (only for non-UUID queries)
    # Note: run-level search below matches run IDs or workflow names; a
    # workflow-level name pre-filter would break run-ID lookups (no
    # workflow name contains a UUID), so it is intentionally omitted.

    accessible_workflows = await workflow_query.all()
    workflow_ids = [w.id for w in accessible_workflows]

    if not workflow_ids:
        return success(
            data={"items": [], "total": 0, "page": page, "page_size": page_size}
        )

    # Build query for runs
    query = WorkflowRun.filter(workflow_id__in=workflow_ids)

    # Apply filters
    if search_text := (search or "").strip():
        query = query.filter(
            Q(id__icontains=search_text) | Q(workflow__name__icontains=search_text)
        )
    if workflow_id:
        query = query.filter(workflow_id__in=workflow_id)
    if status:
        query = query.filter(status__in=status)
    if trigger_type:
        query = query.filter(trigger_type__in=trigger_type)
    if user_id:
        query = query.filter(triggered_by_id__in=user_id)
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
        item = sanitize_workflow_run_payload(
            WorkflowRunListItem.model_validate(run).model_dump()
        )
        related_workflow = run.workflow
        item["workflow_name"] = related_workflow.name if related_workflow else None
        item["workflow_icon"] = related_workflow.icon if related_workflow else None
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
    runs_by_status: dict[str, int] = {}
    for run in runs:
        status_key = run.status.value
        runs_by_status[status_key] = runs_by_status.get(status_key, 0) + 1

    # Runs by workflow (top 10)
    workflow_counts: dict[UUID, int] = {}
    for run in runs:
        if run.workflow_id is None:
            continue
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
            if r.started_at is not None and r.finished_at is not None
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
    own_only: bool = False,
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

    if own_only and not current_user.is_superuser:
        query = query.filter(created_by=current_user)

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
    workflows = (
        await query.prefetch_related("created_by")
        .offset(skip)
        .limit(page_size)
        .order_by("-updated_at")
    )

    workflow_list = []
    for workflow in workflows:
        item = WorkflowListItem.model_validate(workflow).model_dump()
        item["created_by_name"] = (
            workflow.created_by.username if workflow.created_by else None
        )
        workflow_list.append(item)

    return success(
        data={
            "items": workflow_list,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.post("", response_model=Response[WorkflowOut])
async def create_workflow(
    *,
    workflow_in: WorkflowCreate,
    request: Request,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """Create a new workflow."""
    # Check team access
    await deps.check_scoped_permission(
        current_user, "workflow:create", "team", workflow_in.team_id
    )
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

    await AuditLogService.log(
        user=current_user,
        action="create_workflow",
        resource_type="workflow",
        resource_id=workflow.id,
        resource_name=workflow.name,
        operation="create",
        status="success",
        request=request,
        metadata={"team_id": str(workflow_in.team_id)},
        changes={"after": AuditLogService.snapshot(workflow, "workflow")},
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
    completed_durations = [
        r.total_duration_ms for r in runs if r.total_duration_ms is not None
    ]
    avg_duration_ms = (
        sum(completed_durations) / len(completed_durations)
        if completed_durations
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
        completed_durations = [
            r.total_duration_ms for r in runs_in_day if r.total_duration_ms is not None
        ]
        avg_duration = (
            sum(completed_durations) / len(completed_durations)
            if completed_durations
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
    request: Request,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """Update a workflow."""
    workflow = await check_workflow_access(
        workflow_id, current_user, require_write=True
    )
    audit_before = AuditLogService.snapshot(workflow, "workflow")
    await deps.check_scoped_permission(
        current_user, "workflow:update", "team", workflow.team_id
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
        invalid_approvers = await validate_pause_approvers(
            workflow.team_id, workflow_in.definition
        )
        if invalid_approvers:
            raise BusinessError(
                code=ResponseCode.VALIDATION_ERROR,
                msg_key="workflow_pause_invalid_approvers",
                status_code=400,
                users=", ".join(invalid_approvers[:5]),
            )
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
    if workflow_in.embed_config is not None:
        workflow.embed_config = workflow_in.embed_config
    if workflow_in.run_page_config is not None:
        workflow.run_page_config = workflow_in.run_page_config

    await workflow.save()

    await AuditLogService.log(
        user=current_user,
        action="update_workflow",
        resource_type="workflow",
        resource_id=workflow_id,
        resource_name=workflow.name,
        operation="update",
        status="success",
        request=request,
        metadata={"team_id": str(workflow.team_id)},
        changes=AuditLogService.build_changes(
            audit_before, AuditLogService.snapshot(workflow, "workflow")
        ),
    )

    # Reload with relations
    workflow = await Workflow.get(id=workflow_id).prefetch_related("team", "created_by")

    return success(
        data=WorkflowOut.model_validate(workflow).model_dump(),
        msg_key="workflow_updated",
    )


@router.delete("/{workflow_id}", response_model=Response[dict])
async def delete_workflow(
    workflow_id: UUID,
    request: Request,
    current_user: User = Depends(deps.PermissionChecker("workflow:delete")),
) -> Any:
    """Delete a workflow and all its runs."""
    workflow = await check_workflow_access(
        workflow_id, current_user, require_write=True
    )

    workflow_name = workflow.name
    audit_before = AuditLogService.snapshot(workflow, "workflow")

    # Delete workflow (cascades to runs and node executions)
    await workflow.delete()

    await AuditLogService.log(
        user=current_user,
        action="delete_workflow",
        resource_type="workflow",
        resource_id=workflow_id,
        resource_name=workflow_name,
        operation="delete",
        status="success",
        request=request,
        changes={"before": audit_before},
    )

    return success(data={"id": str(workflow_id)}, msg_key="workflow_deleted")


@router.post("/{workflow_id}/publish", response_model=Response[WorkflowOut])
async def publish_workflow(
    workflow_id: UUID,
    request: Request,
    current_user: User = Depends(deps.PermissionChecker("workflow:publish")),
) -> Any:
    """Publish a workflow and save a version snapshot."""
    workflow = await check_workflow_access(
        workflow_id, current_user, require_write=True
    )
    audit_before = AuditLogService.snapshot(workflow, "workflow")

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

    await AuditLogService.log(
        user=current_user,
        action="publish_workflow",
        resource_type="workflow",
        resource_id=workflow_id,
        resource_name=workflow.name,
        operation="update",
        status="success",
        request=request,
        changes=AuditLogService.build_changes(
            audit_before, AuditLogService.snapshot(workflow, "workflow")
        ),
    )

    return success(
        data=WorkflowOut.model_validate(workflow).model_dump(),
        msg_key="workflow_published",
    )


@router.post("/{workflow_id}/unpublish", response_model=Response[WorkflowOut])
async def unpublish_workflow(
    workflow_id: UUID,
    request: Request,
    current_user: User = Depends(deps.PermissionChecker("workflow:publish")),
) -> Any:
    """Unpublish a workflow."""
    workflow = await check_workflow_access(
        workflow_id, current_user, require_write=True
    )
    audit_before = AuditLogService.snapshot(workflow, "workflow")

    workflow.status = WorkflowStatus.DRAFT
    await workflow.save()

    await AuditLogService.log(
        user=current_user,
        action="unpublish_workflow",
        resource_type="workflow",
        resource_id=workflow_id,
        resource_name=workflow.name,
        operation="update",
        status="success",
        request=request,
        changes=AuditLogService.build_changes(
            audit_before, AuditLogService.snapshot(workflow, "workflow")
        ),
    )

    return success(
        data=WorkflowOut.model_validate(workflow).model_dump(),
        msg_key="workflow_unpublished",
    )


@router.post("/{workflow_id}/duplicate", response_model=Response[WorkflowOut])
async def duplicate_workflow(
    workflow_id: UUID,
    request: Request,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """Duplicate a workflow."""
    workflow = await check_workflow_access(
        workflow_id, current_user, require_write=True
    )
    await deps.check_scoped_permission(
        current_user, "workflow:create", "team", workflow.team_id
    )

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

    await AuditLogService.log(
        user=current_user,
        action="duplicate_workflow",
        resource_type="workflow",
        resource_id=new_workflow.id,
        resource_name=new_workflow.name,
        operation="create",
        status="success",
        request=request,
        metadata={
            "source_workflow_id": str(workflow_id),
            "source_workflow_name": workflow.name,
        },
        changes={"after": AuditLogService.snapshot(new_workflow, "workflow")},
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
    request: Request,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """Regenerate webhook token for a workflow."""
    workflow = await check_workflow_access(
        workflow_id, current_user, require_write=True
    )
    audit_before = AuditLogService.snapshot(workflow, "workflow")
    await deps.check_scoped_permission(
        current_user, "workflow:update", "team", workflow.team_id
    )

    workflow.webhook_token = secrets.token_urlsafe(32)
    await workflow.save()

    await AuditLogService.log(
        user=current_user,
        action="regenerate_webhook_token",
        resource_type="workflow",
        resource_id=workflow_id,
        resource_name=workflow.name,
        operation="update",
        status="success",
        request=request,
        changes=AuditLogService.build_changes(
            audit_before, AuditLogService.snapshot(workflow, "workflow")
        ),
    )

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
        normalized_inputs = normalize_webhook_inputs(inputs)

        # Create run record with authenticated user
        run = await WorkflowRun.create(
            workflow_id=matched_workflow.id,
            trigger_type=TriggerType.WEBHOOK,
            triggered_by_id=user.id,  # Record the API key owner as caller
            is_debug=False,
            status=RunStatus.PENDING,
            inputs=normalized_inputs,
        )

        # Submit to Celery for background execution
        run_workflow_task.delay(
            run_id=str(run.id),
            workflow_id=str(matched_workflow.id),
            inputs=normalized_inputs,
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
    request: Request,
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
            base_url=str(request.base_url).rstrip("/"),
        )

        await AuditLogService.log(
            user=current_user,
            action="run_workflow",
            resource_type="workflow_run",
            resource_id=run.id,
            resource_name=workflow.name,
            operation="create",
            status="success",
            request=request,
            metadata={"workflow_id": str(workflow_id), "is_debug": False},
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
    request: Request,
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
            base_url=str(request.base_url).rstrip("/"),
        )

        await AuditLogService.log(
            user=current_user,
            action="debug_workflow",
            resource_type="workflow_run",
            resource_id=run.id,
            resource_name=workflow.name,
            operation="create",
            status="success",
            request=request,
            metadata={"workflow_id": str(workflow_id), "is_debug": True},
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
    if run.workflow_id is None:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="workflow_not_found",
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
        await check_workflow_access(run.workflow_id, current_user)
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
    request: Request,
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
    if run.workflow_id is None:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="workflow_not_found",
            status_code=404,
        )

    await check_workflow_access(run.workflow_id, current_user, require_write=True)

    orchestrator = WorkflowOrchestrator()
    cancelled = await orchestrator.cancel(str(run_id))

    await AuditLogService.log(
        user=current_user,
        action="cancel_workflow_run",
        resource_type="workflow_run",
        resource_id=run_id,
        resource_name=str(run_id),
        operation="update",
        status="success",
        request=request,
        metadata={"workflow_id": str(run.workflow_id), "cancelled": cancelled},
    )

    if cancelled:
        return success(data={"cancelled": True}, msg_key="workflow_run_cancelled")
    else:
        return success(
            data={"cancelled": False}, msg_key="workflow_run_not_cancellable"
        )


@router.post(
    "/{workflow_id}/runs/{run_id}/pause-requests/{pause_request_id}/submit",
    response_model=Response[dict],
)
async def submit_workflow_pause_request(
    workflow_id: UUID,
    run_id: UUID,
    pause_request_id: UUID,
    submission: PauseRequestSubmitRequest,
    request: Request,
    current_user: User = Depends(deps.PermissionChecker("workflow:run")),
) -> Any:
    """
    Submit external variables to a paused workflow and dispatch its resume.

    Approval mode uses this same path with values.decision set to approved or
    rejected, which keeps approval audit data and generic human input unified.
    """
    from app.tasks.workflow import resume_workflow_task

    try:
        workflow = await check_workflow_access(workflow_id, current_user)
    except BusinessError as error:
        # Configured approvers can be team members without private-workflow
        # owner access. Defer that rejection until pause authority is known.
        workflow = await Workflow.filter(id=workflow_id).first()
        if not workflow:
            raise error
        workflow_access_error: BusinessError | None = error
    else:
        workflow_access_error = None
    run = await WorkflowRun.filter(id=run_id, workflow_id=workflow_id).first()
    if not run:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="workflow_run_not_found",
            status_code=404,
        )
    if run.status != RunStatus.WAITING:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="workflow_run_not_waiting",
            status_code=409,
        )

    pause_request = await WorkflowPauseRequest.filter(
        id=pause_request_id,
        run_id=run_id,
        workflow_id=workflow_id,
    ).first()
    if not pause_request:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="workflow_pause_request_not_found",
            status_code=404,
        )
    if pause_request.status == PauseRequestStatus.SUBMITTED:
        # The resume task may have been lost (worker restart, broker hiccup)
        # after the atomic PENDING->SUBMITTED transition. Let the approver
        # re-dispatch it without re-submitting values; the task itself only
        # resumes runs still in WAITING, so repeated dispatches are harmless.
        if run.status != RunStatus.WAITING:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg_key="workflow_pause_request_not_pending",
                status_code=409,
            )
        config = get_pause_request_config(run, pause_request) or {}
        approver_ids = await resolve_pause_approver_ids(workflow, config)
        if not current_user.is_superuser and current_user.id not in approver_ids:
            if workflow_access_error is not None:
                raise workflow_access_error
            raise BusinessError(
                code=ResponseCode.FORBIDDEN,
                msg_key="workflow_pause_not_approver",
                status_code=403,
            )
        resume_workflow_task.delay(str(run.id))
        await remove_pause_pending_notifications(pause_request.id)
        return success(
            data={
                "pause_request_id": str(pause_request.id),
                "status": PauseRequestStatus.SUBMITTED.value,
            },
            msg_key="workflow_pause_submitted",
        )

    if pause_request.status != PauseRequestStatus.PENDING:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="workflow_pause_request_not_pending",
            status_code=409,
        )

    config = get_pause_request_config(run, pause_request) or {}
    if not config or not pause_submission_is_valid(
        config, pause_request.mode, submission.values
    ):
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="workflow_pause_invalid_values",
            status_code=400,
        )

    # Configured approvers (or the owner/admin fallback) are the only
    # submitters; superusers keep the administrative override.
    approver_ids = await resolve_pause_approver_ids(workflow, config)
    if not current_user.is_superuser and current_user.id not in approver_ids:
        if workflow_access_error is not None:
            raise workflow_access_error
        raise BusinessError(
            code=ResponseCode.FORBIDDEN,
            msg_key="workflow_pause_not_approver",
            status_code=403,
        )

    # Require-all approvals (approval mode): every approver submits their own
    # decision, recorded per approver; the request resolves (resumes the run)
    # once all of them approved or any one rejected.
    require_all = pause_request.mode == "approval" and bool(
        config.get("requireAllApprovals")
    )
    if require_all:
        async with in_transaction() as connection:
            locked_run = (
                await WorkflowRun.filter(
                    id=run.id,
                    status=RunStatus.WAITING,
                )
                .using_db(connection)
                .select_for_update()
                .first()
            )
            locked_request = (
                await WorkflowPauseRequest.filter(
                    id=pause_request.id,
                    status=PauseRequestStatus.PENDING,
                )
                .using_db(connection)
                .select_for_update()
                .first()
            )
            if not locked_run or not locked_request:
                raise BusinessError(
                    code=ResponseCode.BAD_REQUEST,
                    msg_key="workflow_pause_request_not_pending",
                    status_code=409,
                )

            approvals = list(locked_request.approvals or [])
            if any(
                str(item.get("approver_id")) == str(current_user.id)
                for item in approvals
            ):
                raise BusinessError(
                    code=ResponseCode.BAD_REQUEST,
                    msg_key="workflow_pause_already_submitted",
                    status_code=409,
                )
            decision = submission.values.get("decision")
            approvals.append(
                {
                    "approver_id": str(current_user.id),
                    "decision": decision,
                    "comment": submission.comment,
                    "submitted_at": now().isoformat(),
                }
            )
            rejected = decision == "rejected"
            all_approved = not rejected and all(
                str(uid) in {str(item.get("approver_id")) for item in approvals}
                for uid in approver_ids
            )
            resolved = rejected or all_approved
            update_values: dict[str, Any] = {"approvals": approvals}
            if resolved:
                update_values.update(
                    status=PauseRequestStatus.SUBMITTED,
                    values=submission.values,
                    comment=submission.comment,
                    submitted_by_id=current_user.id,
                    submitted_at=now(),
                )
            await (
                WorkflowPauseRequest.filter(id=locked_request.id)
                .using_db(connection)
                .update(**update_values)
            )

        await remove_pause_pending_notification_for(pause_request.id, current_user.id)
        await AuditLogService.log(
            user=current_user,
            action="submit_workflow_pause_request",
            resource_type="workflow_pause_request",
            resource_id=pause_request.id,
            resource_name=pause_request.node_name,
            operation="update",
            status="success",
            request=request,
            metadata={
                "workflow_id": str(workflow.id),
                "run_id": str(run.id),
                "node_id": pause_request.node_id,
                "mode": pause_request.mode,
                "decision": decision,
                "require_all": True,
            },
        )
        if not resolved:
            return success(
                data={
                    "pause_request_id": str(pause_request.id),
                    "status": PauseRequestStatus.PENDING.value,
                },
                msg_key="workflow_pause_submitted_partial",
            )

        resume_workflow_task.delay(str(run.id))
        await remove_pause_pending_notifications(pause_request.id)
        return success(
            data={
                "pause_request_id": str(pause_request.id),
                "status": PauseRequestStatus.SUBMITTED.value,
            },
            msg_key="workflow_pause_submitted",
        )

    # Conditional update makes duplicate submissions a conflict: only the
    # first caller transitions PENDING -> SUBMITTED and dispatches resume.
    updated = await WorkflowPauseRequest.filter(
        id=pause_request.id,
        status=PauseRequestStatus.PENDING,
    ).update(
        status=PauseRequestStatus.SUBMITTED,
        values=submission.values,
        comment=submission.comment,
        submitted_by_id=current_user.id,
        submitted_at=now(),
    )
    if updated != 1:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="workflow_pause_request_not_pending",
            status_code=409,
        )

    resume_workflow_task.delay(str(run.id))
    # The approval is handled: drop the one-shot pending notifications so the
    # notification center stops showing an actionable approve/reject state.
    await remove_pause_pending_notifications(pause_request.id)
    await AuditLogService.log(
        user=current_user,
        action="submit_workflow_pause_request",
        resource_type="workflow_pause_request",
        resource_id=pause_request.id,
        resource_name=pause_request.node_name,
        operation="update",
        status="success",
        request=request,
        metadata={
            "workflow_id": str(workflow.id),
            "run_id": str(run.id),
            "node_id": pause_request.node_id,
            "mode": pause_request.mode,
        },
    )
    return success(
        data={
            "pause_request_id": str(pause_request.id),
            "status": PauseRequestStatus.SUBMITTED.value,
        },
        msg_key="workflow_pause_submitted",
    )


@router.get(
    "/{workflow_id}/runs/{run_id}/pause-request",
    response_model=Response[dict],
)
async def get_pending_workflow_pause_request(
    workflow_id: UUID,
    run_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("workflow:run")),
) -> Any:
    """Return the pending external-input request for a waiting run, if any."""
    try:
        workflow = await check_workflow_access(workflow_id, current_user)
    except BusinessError as error:
        workflow = await Workflow.filter(id=workflow_id).first()
        if not workflow:
            raise error
        workflow_access_error: BusinessError | None = error
    else:
        workflow_access_error = None
    run = await WorkflowRun.filter(id=run_id, workflow_id=workflow_id).first()
    if not run:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="workflow_run_not_found",
            status_code=404,
        )

    await run.fetch_related("workflow", "triggered_by")
    workflow_name = run.workflow.name if run.workflow else None
    triggered_by_name = run.triggered_by.username if run.triggered_by else None

    pause_request = (
        await WorkflowPauseRequest.filter(
            run_id=run_id,
            workflow_id=workflow_id,
            status=PauseRequestStatus.PENDING,
        )
        .order_by("-created_at")
        .first()
    )
    if not pause_request:
        return success(data={"pause_request": None})

    config = get_pause_request_config(run, pause_request) or {}
    approver_ids = await resolve_pause_approver_ids(workflow, config)

    # Approvals are bound to a personnel list: users outside it neither see
    # the request nor its contents (the submit endpoint already rejects them).
    # Returning null (the same shape as "no request") avoids leaking that a
    # pending approval exists.
    if not current_user.is_superuser and current_user.id not in approver_ids:
        if workflow_access_error is not None:
            raise workflow_access_error
        return success(data={"pause_request": None})

    approver_users = {
        str(user.id): user for user in await User.filter(id__in=approver_ids)
    }
    approver_names = [
        approver_users[str(uid)].username
        for uid in approver_ids
        if str(uid) in approver_users
    ]
    require_all = pause_request.mode == "approval" and bool(
        config.get("requireAllApprovals")
    )
    approval_records = getattr(pause_request, "approvals", None) or []
    already_submitted = any(
        str(item.get("approver_id")) == str(current_user.id)
        for item in approval_records
    )
    approvals = [
        {
            "approver_id": item.get("approver_id"),
            "username": (
                approver_users.get(str(item.get("approver_id"))).username
                if str(item.get("approver_id")) in approver_users
                else None
            ),
            "decision": item.get("decision"),
            "comment": item.get("comment"),
            "submitted_at": item.get("submitted_at"),
        }
        for item in approval_records
    ]
    raw_variables = config.get("inputVariables", [])
    input_variables = [
        {
            "name": variable.get("name", ""),
            "label": variable.get("label") or variable.get("name", ""),
            "type": variable.get("type", "text"),
            "required": bool(variable.get("required", False)),
            "default": (
                variable.get("defaultValue")
                if variable.get("defaultValue") not in (None, "")
                else None
            ),
            "description": variable.get("description"),
            "options": variable.get("options"),
            "fileConfig": variable.get("fileConfig"),
        }
        for variable in raw_variables
        if isinstance(variable, dict) and isinstance(variable.get("name"), str)
    ]
    return success(
        data={
            "pause_request": {
                "id": str(pause_request.id),
                "node_id": pause_request.node_id,
                "node_name": pause_request.node_name,
                "mode": pause_request.mode,
                "title": config.get("title")
                if isinstance(config.get("title"), str)
                else "",
                "workflow_name": workflow_name,
                "triggered_by_name": triggered_by_name,
                "triggered_at": run.started_at
                if run.started_at is not None
                else run.created_at,
                # An empty resolved description stays empty (never fall back to
                # the raw {{var}} template); only legacy NULL rows fall back to
                # the snapshotted config text.
                "description": (
                    pause_request.description
                    if pause_request.description is not None
                    else (
                        config.get("description")
                        if isinstance(config.get("description"), str)
                        else ""
                    )
                ),
                "input_variables": input_variables,
                "approver_ids": [str(uid) for uid in approver_ids],
                "approver_names": approver_names,
                "require_all": require_all,
                "approvals": approvals,
                "already_submitted": already_submitted,
                "can_submit": (
                    current_user.is_superuser or current_user.id in approver_ids
                )
                and not already_submitted,
            }
        }
    )


# ============ Workflow Runs ============


@router.get(
    "/{workflow_id}/runs/mine",
    response_model=Response[PageData[WorkflowRunListItem]],
)
async def list_my_workflow_runs(
    workflow_id: UUID,
    status: RunStatus | None = None,
    search: str | None = Query(None),
    created_after: datetime | None = Query(None),
    created_before: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(deps.PermissionChecker("workflow:run")),
) -> Any:
    """List the current user's published workflow runs."""
    await check_workflow_access(workflow_id, current_user)

    query = WorkflowRun.filter(
        workflow_id=workflow_id,
        triggered_by_id=current_user.id,
        is_debug=False,
    )
    if status:
        query = query.filter(status=status)
    if search_text := (search or "").strip():
        try:
            query = query.filter(id=UUID(search_text))
        except ValueError:
            query = query.filter(id__isnull=True)
    if created_after:
        query = query.filter(created_at__gte=created_after)
    if created_before:
        query = query.filter(created_at__lte=created_before)

    total = await query.count()
    skip = (page - 1) * page_size
    runs = await query.order_by("-created_at").offset(skip).limit(page_size)

    return success(
        data={
            "items": [
                sanitize_workflow_run_payload(
                    WorkflowRunListItem.model_validate(run).model_dump()
                )
                for run in runs
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.get(
    "/{workflow_id}/runs/mine/{run_id}",
    response_model=Response[WorkflowRunOut],
)
async def get_my_workflow_run(
    workflow_id: UUID,
    run_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("workflow:run")),
) -> Any:
    """Get one of the current user's published workflow runs."""
    await check_workflow_access(workflow_id, current_user)
    run = await WorkflowRun.filter(
        id=run_id,
        workflow_id=workflow_id,
        triggered_by_id=current_user.id,
        is_debug=False,
    ).first()
    if not run:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="workflow_run_not_found",
            status_code=404,
        )

    return success(
        data=sanitize_workflow_run_payload(
            WorkflowRunOut.model_validate(run).model_dump()
        )
    )


@router.get(
    "/{workflow_id}/runs/mine/{run_id}/nodes",
    response_model=Response[list[NodeExecutionOut]],
)
async def list_my_run_node_executions(
    workflow_id: UUID,
    run_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("workflow:run")),
) -> Any:
    """Get node executions for one of the current user's published runs."""
    await check_workflow_access(workflow_id, current_user)
    run_exists = await WorkflowRun.filter(
        id=run_id,
        workflow_id=workflow_id,
        triggered_by_id=current_user.id,
        is_debug=False,
    ).exists()
    if not run_exists:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="workflow_run_not_found",
            status_code=404,
        )

    executions = await NodeExecution.filter(run_id=run_id).order_by("execution_order")
    return success(
        data=[
            sanitize_node_execution_payload(
                NodeExecutionOut.model_validate(execution).model_dump()
            )
            for execution in executions
        ]
    )


@router.get(
    "/{workflow_id}/runs", response_model=Response[PageData[WorkflowRunListItem]]
)
async def list_workflow_runs(
    workflow_id: UUID,
    status: RunStatus | None = None,
    is_debug: bool | None = None,
    search: str | None = Query(None),
    created_after: datetime | None = Query(None),
    created_before: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(deps.PermissionChecker("workflow:read")),
) -> Any:
    """List runs for a workflow."""
    await check_workflow_access(workflow_id, current_user)

    query = WorkflowRun.filter(workflow_id=workflow_id)

    if status:
        query = query.filter(status=status)

    if is_debug is not None:
        query = query.filter(is_debug=is_debug)

    if search_text := (search or "").strip():
        try:
            query = query.filter(id=UUID(search_text))
        except ValueError:
            query = query.filter(id__isnull=True)

    if created_after:
        query = query.filter(created_at__gte=created_after)

    if created_before:
        query = query.filter(created_at__lte=created_before)

    total = await query.count()
    skip = (page - 1) * page_size
    runs = await query.order_by("-created_at").offset(skip).limit(page_size)

    run_list = [WorkflowRunListItem.model_validate(r) for r in runs]

    return success(
        data={
            "items": [sanitize_workflow_run_payload(r.model_dump()) for r in run_list],
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
    if run.workflow_id is None:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="workflow_not_found",
            status_code=404,
        )

    # Check access through workflow
    await check_workflow_access(run.workflow_id, current_user)

    return success(
        data=sanitize_workflow_run_payload(
            WorkflowRunOut.model_validate(run).model_dump()
        )
    )


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
    if run.workflow_id is None:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="workflow_not_found",
            status_code=404,
        )

    # Check access through workflow
    await check_workflow_access(run.workflow_id, current_user)

    executions = await NodeExecution.filter(run_id=run_id).order_by("execution_order")

    return success(
        data=[
            sanitize_node_execution_payload(
                NodeExecutionOut.model_validate(e).model_dump()
            )
            for e in executions
        ]
    )


@router.delete("/runs/{run_id}", response_model=Response[dict])
async def delete_workflow_run(
    run_id: UUID,
    request: Request,
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
    if run.workflow_id is None:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="workflow_not_found",
            status_code=404,
        )

    # Check write access through workflow
    await check_workflow_access(run.workflow_id, current_user, require_write=True)

    workflow_id = run.workflow_id
    audit_before = AuditLogService.snapshot(run, "workflow_run")
    await run.delete()

    await AuditLogService.log(
        user=current_user,
        action="delete_workflow_run",
        resource_type="workflow_run",
        resource_id=run_id,
        resource_name=str(run_id),
        operation="delete",
        status="success",
        request=request,
        changes={"before": audit_before},
        metadata={"workflow_id": str(workflow_id)},
    )

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
    request: Request,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """Manually create a version snapshot of the current workflow state."""
    workflow = await check_workflow_access(
        workflow_id, current_user, require_write=True
    )
    await deps.check_scoped_permission(
        current_user, "workflow:update", "team", workflow.team_id
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

    await AuditLogService.log(
        user=current_user,
        action="create_workflow_version",
        resource_type="workflow_version",
        resource_id=workflow_version.id,
        resource_name=workflow.name,
        operation="create",
        status="success",
        request=request,
        metadata={"workflow_id": str(workflow_id), "version": workflow.version},
        changes={
            "after": AuditLogService.snapshot(workflow_version, "workflow_version")
        },
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
    request: Request,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """Restore a workflow to a specific version."""
    workflow = await check_workflow_access(
        workflow_id, current_user, require_write=True
    )
    audit_before = AuditLogService.snapshot(workflow, "workflow")
    await deps.check_scoped_permission(
        current_user, "workflow:update", "team", workflow.team_id
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
    workflow.trigger_config = workflow_version.trigger_config or {}
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

    await AuditLogService.log(
        user=current_user,
        action="restore_workflow_version",
        resource_type="workflow",
        resource_id=workflow_id,
        resource_name=workflow.name,
        operation="update",
        status="success",
        request=request,
        metadata={"workflow_id": str(workflow_id), "restored_from_version": version},
        changes=AuditLogService.build_changes(
            audit_before, AuditLogService.snapshot(workflow, "workflow")
        ),
    )

    return success(
        data=WorkflowOut.model_validate(workflow).model_dump(),
        msg_key="workflow_version_restored",
    )
