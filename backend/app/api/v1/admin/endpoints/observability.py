"""Admin operational observability API.

Read access intentionally remains aligned with the existing dashboard permission;
alert mutations require the dedicated observability-management permission.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import PermissionChecker
from app.models.user import User
from app.schemas.response import Response, success
from app.services import observability_v2 as service

router = APIRouter()
Period = Literal["15m", "1h", "24h", "7d", "custom"]


class ObservabilityMeta(BaseModel):
    window_start: datetime
    window_end: datetime
    sampled_at: datetime
    period: str
    state: Literal["fresh", "partial", "stale", "unavailable", "no_data"]
    sample_count: int


class RunSummary(BaseModel):
    run_id: str
    source: Literal["agent", "workflow"]
    resource_id: str | None = None
    resource_name: str | None = None
    team_id: str | None = None
    team_name: str | None = None
    status: str
    submitted_at: datetime | None = None
    started_at: datetime | None = None
    message_started_at: datetime | None = None
    worker_bootstrap_ms: int | None = None
    finished_at: datetime | None = None
    queue_duration_ms: int | None = None
    execution_duration_ms: int | None = None
    total_duration_ms: int | None = None
    first_token_ms: int | None = None
    total_tokens: int
    error_category: str | None = None
    error_code: str | None = None
    trace_available: bool
    trace_complete: bool


class TraceSpan(BaseModel):
    span_id: str
    parent_span_id: str | None = None
    kind: str
    name: str
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    attempt: int | None = None
    model: str | None = None
    tool: str | None = None
    error_category: str | None = None
    token_usage: dict[str, int] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunPage(BaseModel):
    items: list[RunSummary]
    next_cursor: str | None
    meta: ObservabilityMeta


class TraceInfo(BaseModel):
    complete: bool
    expired: bool
    truncated: bool = False
    recorded_count: int


class RunDetail(BaseModel):
    run: RunSummary
    spans: list[TraceSpan]
    trace: TraceInfo
    meta: ObservabilityMeta


class DependencyRow(BaseModel):
    name: str
    requests: int
    completed: int
    failed: int
    success_rate: float | None
    p50_ms: int | None
    p95_ms: int | None
    first_token_p95_ms: int | None
    tokens: int | None
    sample_count: int


class ModelDependencyRow(DependencyRow):
    id: str
    provider: str | None
    provider_display_name: str | None


class WorkerRow(BaseModel):
    worker_id: str
    status: str
    queues: list[str]
    last_heartbeat: datetime | None
    active_tasks: int
    reserved_tasks: int
    scheduled_tasks: int


class QueueTrendRow(BaseModel):
    bucket: str
    pending: int


class QueueRow(BaseModel):
    name: str
    consumers: int
    pending: int | None
    oldest_wait_ms: int | None
    observed_at: datetime | None
    state: Literal["healthy", "warning", "unavailable", "unknown"]
    trend: list[QueueTrendRow]


class SummaryMetrics(BaseModel):
    submitted: int
    completed: int
    failed: int
    success_rate: float | None
    p50_ms: int | None
    p95_ms: int | None
    tokens: int


class AgentSummaryMetrics(SummaryMetrics):
    first_token_p95_ms: int | None


class TrendRow(BaseModel):
    bucket: str
    submitted: int
    completed: int
    failed: int
    tokens: int
    p95_ms: int | None
    first_token_p95_ms: int | None


class ObservabilityIssue(BaseModel):
    kind: str
    severity: Literal["critical", "warning", "info"]
    title: str
    detail: str
    affected_count: int
    href: str


class SummaryPayload(BaseModel):
    meta: ObservabilityMeta
    agents: AgentSummaryMetrics
    workflows: SummaryMetrics
    trend: list[TrendRow]
    issues: list[ObservabilityIssue]


class DependenciesPayload(BaseModel):
    meta: ObservabilityMeta
    models: list[ModelDependencyRow]
    tools: list[DependencyRow]
    retrieval: list[DependencyRow]


class QueuePayload(BaseModel):
    meta: ObservabilityMeta
    workers: list[WorkerRow]
    queues: list[QueueRow]


class InstanceRow(BaseModel):
    instance_id: str
    name: str
    role: Literal["api"]
    cpu_percent: float | None
    memory_percent: float | None
    metric_scope: Literal["host"]
    observed_at: datetime | None
    state: Literal["healthy", "warning", "unavailable", "stale", "offline"]


class DependencyHealth(BaseModel):
    name: str
    status: Literal["healthy", "degraded", "unhealthy", "unknown"]
    observed_at: datetime | None
    latency_ms: int | None
    detail: str | None


class SlowQuery(BaseModel):
    query_id: str
    query: str
    calls: int
    mean_ms: float | None
    max_ms: float | None
    total_ms: float | None


class SlowQueries(BaseModel):
    available: bool
    reset_at: datetime | None
    items: list[SlowQuery]


class InfrastructurePayload(BaseModel):
    meta: ObservabilityMeta
    instances: list[InstanceRow]
    dependencies: list[DependencyHealth]
    slow_queries: SlowQueries


class AlertRule(BaseModel):
    id: str
    name: str
    threshold: float
    enabled: bool
    evaluation_window_seconds: int
    recovery_window_seconds: int
    updated_at: datetime


class AlertEvent(BaseModel):
    id: str
    rule_id: str
    kind: str
    severity: Literal["critical", "warning", "info"]
    title: str
    detail: str
    affected_count: int
    status: Literal["active", "resolved"]
    opened_at: datetime
    resolved_at: datetime | None = None
    acknowledged_at: datetime | None = None
    silenced_until: datetime | None = None


class AlertPage(BaseModel):
    items: list[AlertEvent]
    next_cursor: str | None
    meta: ObservabilityMeta


class RuleUpdate(BaseModel):
    threshold: float | None = Field(None, ge=0, le=1)
    enabled: bool | None = None
    evaluation_window_seconds: int | None = Field(None, ge=60, le=604800)
    recovery_window_seconds: int | None = Field(None, ge=60, le=604800)


READ = "admin:dashboard:access"
MANAGE = "admin:observability:manage"


@router.get("/summary", response_model=Response[SummaryPayload])
async def get_summary(
    period: Period = "1h",
    team_id: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    current_user: User = Depends(PermissionChecker(READ)),
) -> Any:
    try:
        data = await service.summary(period, team_id, start_time, end_time)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return success(data=data)


@router.get("/runs", response_model=Response[RunPage])
async def get_runs(
    period: Period = "1h",
    team_id: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    source: Literal["all", "agent", "workflow"] = "all",
    status: str | None = None,
    error_category: str | None = None,
    run_id: str | None = None,
    cursor: str | None = None,
    limit: int = Query(25, ge=1, le=50),
    current_user: User = Depends(PermissionChecker(READ)),
) -> Any:
    try:
        data = await service.list_runs(
            period=period,
            start_time=start_time,
            end_time=end_time,
            team_id=team_id,
            source=source,
            status=status,
            error_category=error_category,
            run_id=run_id,
            cursor=cursor,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return success(data=data)


@router.get("/runs/{source}/{run_id}", response_model=Response[RunDetail])
async def get_run(
    source: Literal["agent", "workflow"],
    run_id: UUID,
    current_user: User = Depends(PermissionChecker(READ)),
) -> Any:
    # Permission dependency resolves before service loads any trace content.
    data = await service.run_detail(source, run_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return success(data=data)


@router.get("/dependencies", response_model=Response[DependenciesPayload])
async def get_dependencies(
    period: Period = "1h",
    team_id: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    current_user: User = Depends(PermissionChecker(READ)),
) -> Any:
    try:
        data = await service.dependencies(period, team_id, start_time, end_time)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return success(data=data)


@router.get("/queues", response_model=Response[QueuePayload])
async def get_queues(current_user: User = Depends(PermissionChecker(READ))) -> Any:
    return success(data=await service.queues())


@router.get("/infrastructure", response_model=Response[InfrastructurePayload])
async def get_infrastructure(
    current_user: User = Depends(PermissionChecker(READ)),
) -> Any:
    return success(data=await service.infrastructure())


@router.get("/alerts", response_model=Response[AlertPage])
async def get_alerts(
    status: Literal["active", "resolved", "all"] = "active",
    cursor: str | None = None,
    limit: int = Query(25, ge=1, le=50),
    current_user: User = Depends(PermissionChecker(READ)),
) -> Any:
    try:
        return success(data=await service.list_alerts(status, cursor, limit))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/alerts/{alert_id}/acknowledge", response_model=Response[AlertEvent])
async def acknowledge_alert(
    alert_id: UUID, current_user: User = Depends(PermissionChecker(MANAGE))
) -> Any:
    event = await service.acknowledge_alert(alert_id, str(current_user.id))
    if event is None:
        raise HTTPException(status_code=404, detail="Active alert not found")
    return success(data=event)


@router.post("/alerts/{alert_id}/silence", response_model=Response[AlertEvent])
async def silence_alert(
    alert_id: UUID,
    duration_seconds: int = Query(..., ge=60, le=604800),
    current_user: User = Depends(PermissionChecker(MANAGE)),
) -> Any:
    event = await service.silence_alert(alert_id, duration_seconds)
    if event is None:
        raise HTTPException(status_code=404, detail="Active alert not found")
    return success(data=event)


@router.get("/alerts/rules", response_model=Response[list[AlertRule]])
async def get_alert_rules(current_user: User = Depends(PermissionChecker(READ))) -> Any:
    return success(data=await service.alert_rules())


@router.put("/alerts/rules/{rule_id}", response_model=Response[AlertRule])
async def put_alert_rule(
    rule_id: str,
    body: RuleUpdate,
    current_user: User = Depends(PermissionChecker(MANAGE)),
) -> Any:
    data = await service.update_rule(
        rule_id, body.model_dump(exclude_unset=True, exclude_none=True)
    )
    if data is None:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    return success(data=data)
