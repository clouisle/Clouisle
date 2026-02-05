"""
Workflow monitoring API endpoints.

Provides endpoints for:
- Workflow execution metrics
- Node performance metrics
- Running workflow status
- Dashboard summary
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.models.user import User
from app.services.workflow import (
    get_metrics_collector,
    get_workflow_cache,
)

router = APIRouter(prefix="/workflows/metrics", tags=["workflow-metrics"])


# Response models

class WorkflowMetricsResponse(BaseModel):
    """Workflow metrics response."""

    workflow_id: str
    total_runs: int
    successful_runs: int
    failed_runs: int
    cancelled_runs: int
    error_rate: float
    avg_duration_ms: float
    min_duration_ms: float
    max_duration_ms: float
    p50_duration_ms: float
    p95_duration_ms: float
    p99_duration_ms: float
    runs_per_minute: float
    avg_nodes_per_run: float
    total_nodes_executed: int
    errors_by_type: dict[str, int]


class NodeMetricsResponse(BaseModel):
    """Node type metrics response."""

    node_type: str
    total_executions: int
    successful_executions: int
    failed_executions: int
    avg_duration_ms: float
    min_duration_ms: float
    max_duration_ms: float
    p50_duration_ms: float
    p95_duration_ms: float
    total_retries: int
    avg_retries: float


class RunningWorkflowResponse(BaseModel):
    """Running workflow response."""

    run_id: str
    workflow_id: str
    start_time: float
    duration_s: float


class DashboardSummaryResponse(BaseModel):
    """Dashboard summary response."""

    total_runs: int
    successful_runs: int
    failed_runs: int
    success_rate: float
    currently_running: int
    running_workflows: list[RunningWorkflowResponse]


class CacheStatsResponse(BaseModel):
    """Cache statistics response."""

    workflow_count: int
    plan_count: int
    node_count: int
    llm_count: int
    tool_count: int
    local_cache_size: int


# Endpoints

@router.get("/dashboard", response_model=DashboardSummaryResponse)
async def get_dashboard_summary(
    current_user: User = Depends(get_current_user),
):
    """
    Get dashboard summary with overall workflow metrics.

    Returns aggregated metrics across all workflows including:
    - Total runs and success/failure counts
    - Success rate
    - Currently running workflows
    """
    metrics = get_metrics_collector()
    summary = await metrics.get_dashboard_summary()

    return DashboardSummaryResponse(
        total_runs=summary.get("total_runs", 0),
        successful_runs=summary.get("successful_runs", 0),
        failed_runs=summary.get("failed_runs", 0),
        success_rate=summary.get("success_rate", 0.0),
        currently_running=summary.get("currently_running", 0),
        running_workflows=[
            RunningWorkflowResponse(**wf)
            for wf in summary.get("running_workflows", [])
        ],
    )


@router.get("/workflows/{workflow_id}", response_model=WorkflowMetricsResponse)
async def get_workflow_metrics(
    workflow_id: UUID,
    time_range_minutes: int = Query(default=60, ge=1, le=1440),
    current_user: User = Depends(get_current_user),
):
    """
    Get detailed metrics for a specific workflow.

    Args:
        workflow_id: Workflow UUID
        time_range_minutes: Time range for metrics (1-1440 minutes)

    Returns:
        Detailed workflow execution metrics
    """
    metrics_collector = get_metrics_collector()
    metrics = await metrics_collector.get_workflow_metrics(
        str(workflow_id),
        time_range_minutes=time_range_minutes,
    )

    return WorkflowMetricsResponse(
        workflow_id=str(workflow_id),
        total_runs=metrics.total_runs,
        successful_runs=metrics.successful_runs,
        failed_runs=metrics.failed_runs,
        cancelled_runs=metrics.cancelled_runs,
        error_rate=metrics.error_rate,
        avg_duration_ms=metrics.avg_duration_ms,
        min_duration_ms=metrics.min_duration_ms if metrics.min_duration_ms != float("inf") else 0,
        max_duration_ms=metrics.max_duration_ms,
        p50_duration_ms=metrics.p50_duration_ms,
        p95_duration_ms=metrics.p95_duration_ms,
        p99_duration_ms=metrics.p99_duration_ms,
        runs_per_minute=metrics.runs_per_minute,
        avg_nodes_per_run=metrics.avg_nodes_per_run,
        total_nodes_executed=metrics.total_nodes_executed,
        errors_by_type=metrics.errors_by_type,
    )


@router.get("/nodes", response_model=dict[str, NodeMetricsResponse])
async def get_all_node_metrics(
    current_user: User = Depends(get_current_user),
):
    """
    Get metrics for all node types.

    Returns metrics for each node type that has been executed,
    including execution counts, durations, and retry statistics.
    """
    metrics_collector = get_metrics_collector()
    all_metrics = await metrics_collector.get_all_node_metrics()

    return {
        node_type: NodeMetricsResponse(
            node_type=node_type,
            total_executions=m.total_executions,
            successful_executions=m.successful_executions,
            failed_executions=m.failed_executions,
            avg_duration_ms=m.avg_duration_ms,
            min_duration_ms=m.min_duration_ms if m.min_duration_ms != float("inf") else 0,
            max_duration_ms=m.max_duration_ms,
            p50_duration_ms=m.p50_duration_ms,
            p95_duration_ms=m.p95_duration_ms,
            total_retries=m.total_retries,
            avg_retries=m.avg_retries,
        )
        for node_type, m in all_metrics.items()
    }


@router.get("/nodes/{node_type}", response_model=NodeMetricsResponse)
async def get_node_type_metrics(
    node_type: str,
    current_user: User = Depends(get_current_user),
):
    """
    Get metrics for a specific node type.

    Args:
        node_type: Node type (e.g., "llm", "code", "http_request")

    Returns:
        Metrics for the specified node type
    """
    metrics_collector = get_metrics_collector()
    metrics = await metrics_collector.get_node_metrics(node_type)

    return NodeMetricsResponse(
        node_type=node_type,
        total_executions=metrics.total_executions,
        successful_executions=metrics.successful_executions,
        failed_executions=metrics.failed_executions,
        avg_duration_ms=metrics.avg_duration_ms,
        min_duration_ms=metrics.min_duration_ms if metrics.min_duration_ms != float("inf") else 0,
        max_duration_ms=metrics.max_duration_ms,
        p50_duration_ms=metrics.p50_duration_ms,
        p95_duration_ms=metrics.p95_duration_ms,
        total_retries=metrics.total_retries,
        avg_retries=metrics.avg_retries,
    )


@router.get("/running", response_model=list[RunningWorkflowResponse])
async def get_running_workflows(
    current_user: User = Depends(get_current_user),
):
    """
    Get list of currently running workflows.

    Returns all workflows that are currently executing,
    including their run IDs, workflow IDs, and duration.
    """
    metrics = get_metrics_collector()
    running = await metrics.get_running_workflows()

    return [
        RunningWorkflowResponse(**wf)
        for wf in running
    ]


@router.get("/cache", response_model=CacheStatsResponse)
async def get_cache_stats(
    current_user: User = Depends(get_current_user),
):
    """
    Get workflow cache statistics.

    Returns counts of cached items by type:
    - Workflow definitions
    - Execution plans
    - Node results
    - LLM responses
    - Tool results
    """
    cache = get_workflow_cache()
    stats = await cache.get_stats()

    return CacheStatsResponse(
        workflow_count=stats.get("workflow_count", 0),
        plan_count=stats.get("plan_count", 0),
        node_count=stats.get("node_count", 0),
        llm_count=stats.get("llm_count", 0),
        tool_count=stats.get("tool_count", 0),
        local_cache_size=stats.get("local_cache_size", 0),
    )


@router.delete("/cache")
async def clear_cache(
    current_user: User = Depends(get_current_user),
):
    """
    Clear all workflow cache entries.

    Requires admin privileges. Clears:
    - Workflow definition cache
    - Execution plan cache
    - Node result cache
    - LLM response cache
    - Tool result cache
    """
    # TODO: Add admin check
    cache = get_workflow_cache()
    count = await cache.clear_all()

    return {"cleared": count, "message": f"Cleared {count} cache entries"}
