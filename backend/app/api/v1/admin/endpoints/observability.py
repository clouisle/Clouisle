"""
Admin observability endpoints.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.deps import PermissionChecker
from app.models.user import User
from app.schemas.response import Response, success
from app.services import admin_observability

router = APIRouter()


def _cache_params(**params: Any) -> dict[str, Any]:
    return {key: value for key, value in params.items() if value is not None}


@router.get("/overview", response_model=Response[dict])
async def get_observability_overview(
    time_range: str = Query("30d", description="Time range: 7d, 30d, 90d, all"),
    current_user: User = Depends(PermissionChecker("admin:dashboard:access")),
) -> Any:
    data = await admin_observability.cached_payload(
        "overview",
        _cache_params(time_range=time_range),
        lambda: admin_observability.get_overview(time_range),
    )
    return success(data=data)


@router.get("/agents", response_model=Response[dict])
async def get_observability_agents(
    time_range: str = Query("30d", description="Time range: 7d, 30d, 90d, all"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("requests"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    current_user: User = Depends(PermissionChecker("admin:dashboard:access")),
) -> Any:
    data = await admin_observability.cached_payload(
        "agents",
        _cache_params(
            time_range=time_range,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        ),
        lambda: admin_observability.get_agents(
            time_range, page, page_size, sort_by, sort_order
        ),
    )
    return success(data=data)


@router.get("/agent/{agent_id}", response_model=Response[dict])
async def get_observability_agent_detail(
    agent_id: UUID,
    time_range: str = Query("30d", description="Time range: 7d, 30d, 90d, all"),
    current_user: User = Depends(PermissionChecker("admin:dashboard:access")),
) -> Any:
    data = await admin_observability.cached_payload(
        "agent-detail",
        _cache_params(agent_id=str(agent_id), time_range=time_range),
        lambda: admin_observability.get_agent_detail(agent_id, time_range),
    )
    return success(data=data)


@router.get("/workflows", response_model=Response[dict])
async def get_observability_workflows(
    time_range: str = Query("30d", description="Time range: 7d, 30d, 90d, all"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("runs"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    current_user: User = Depends(PermissionChecker("admin:dashboard:access")),
) -> Any:
    data = await admin_observability.cached_payload(
        "workflows",
        _cache_params(
            time_range=time_range,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        ),
        lambda: admin_observability.get_workflows(
            time_range, page, page_size, sort_by, sort_order
        ),
    )
    return success(data=data)


@router.get("/workflow/{workflow_id}", response_model=Response[dict])
async def get_observability_workflow_detail(
    workflow_id: UUID,
    time_range: str = Query("30d", description="Time range: 7d, 30d, 90d, all"),
    current_user: User = Depends(PermissionChecker("admin:dashboard:access")),
) -> Any:
    data = await admin_observability.cached_payload(
        "workflow-detail",
        _cache_params(workflow_id=str(workflow_id), time_range=time_range),
        lambda: admin_observability.get_workflow_detail(workflow_id, time_range),
    )
    return success(data=data)


@router.get("/timeouts", response_model=Response[dict])
async def get_observability_timeouts(
    time_range: str = Query("30d", description="Time range: 7d, 30d, 90d, all"),
    source: str = Query("all", pattern="^(all|agent|workflow)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(PermissionChecker("admin:dashboard:access")),
) -> Any:
    data = await admin_observability.cached_payload(
        "timeouts",
        _cache_params(
            time_range=time_range, source=source, page=page, page_size=page_size
        ),
        lambda: admin_observability.get_timeouts(time_range, source, page, page_size),
    )
    return success(data=data)


@router.get("/throughput", response_model=Response[dict])
async def get_observability_throughput(
    time_range: str = Query("30d", description="Time range: 7d, 30d, 90d, all"),
    granularity: str | None = Query(None, description="Granularity: hour, day"),
    current_user: User = Depends(PermissionChecker("admin:dashboard:access")),
) -> Any:
    data = await admin_observability.cached_payload(
        "throughput",
        _cache_params(time_range=time_range, granularity=granularity),
        lambda: admin_observability.get_throughput(time_range, granularity),
    )
    return success(data=data)


@router.get("/tokens", response_model=Response[dict])
async def get_observability_tokens(
    time_range: str = Query("30d", description="Time range: 7d, 30d, 90d, all"),
    current_user: User = Depends(PermissionChecker("admin:dashboard:access")),
) -> Any:
    data = await admin_observability.cached_payload(
        "tokens",
        _cache_params(time_range=time_range),
        lambda: admin_observability.get_tokens(time_range),
    )
    return success(data=data)


@router.get("/system/health", response_model=Response[dict])
async def get_observability_system_health(
    current_user: User = Depends(PermissionChecker("admin:dashboard:access")),
) -> Any:
    data = await admin_observability.cached_payload(
        "system-health",
        {},
        admin_observability.get_system_health,
    )
    return success(data=data)


@router.get("/system/trend", response_model=Response[dict])
async def get_observability_system_trend(
    current_user: User = Depends(PermissionChecker("admin:dashboard:access")),
) -> Any:
    data = await admin_observability.cached_payload(
        "system-trend",
        {},
        admin_observability.get_system_trend,
    )
    return success(data=data)


@router.get("/system/slow-queries", response_model=Response[dict])
async def get_observability_slow_queries(
    threshold_ms: int = Query(1000, ge=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(PermissionChecker("admin:dashboard:access")),
) -> Any:
    data = await admin_observability.cached_payload(
        "system-slow-queries",
        _cache_params(threshold_ms=threshold_ms, page=page, page_size=page_size),
        lambda: admin_observability.get_slow_queries(threshold_ms, page, page_size),
    )
    return success(data=data)


@router.get("/system/workers", response_model=Response[dict])
async def get_observability_workers(
    current_user: User = Depends(PermissionChecker("admin:dashboard:access")),
) -> Any:
    data = await admin_observability.cached_payload(
        "system-workers",
        {},
        admin_observability.get_workers,
    )
    return success(data=data)
