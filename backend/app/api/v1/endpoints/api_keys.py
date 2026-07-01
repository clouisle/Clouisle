from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from tortoise.expressions import Q

from app.api import deps
from app.api.workflow_access import check_workflow_access
from app.api.v1.endpoints.agents import check_agent_access
from app.core.timezone import now_utc
from app.models.user import User
from app.models.api_key import APIKey
from app.models.agent import Agent
from app.schemas.api_key import (
    APIKeyCreate,
    APIKeyUpdate,
    APIKeyResponse,
    APIKeyCreateResponse,
    APIKeyStats,
    APIKeyAgentInfo,
)
from app.schemas.response import (
    Response,
    PageData,
    ResponseCode,
    BusinessError,
    success,
)
from app.services.audit_log import AuditLogService

router = APIRouter()


async def build_api_key_response(
    api_key: APIKey, include_agents: bool = True, include_workflows: bool = True
) -> dict:
    """构建 API Key 响应数据"""
    response_data = {
        "id": api_key.id,
        "name": api_key.name,
        "key_prefix": api_key.key_prefix,
        "user_id": api_key.user_id,
        "scopes": api_key.scopes,
        "rate_limit": api_key.rate_limit,
        "is_active": api_key.is_active,
        "expires_at": api_key.expires_at,
        "last_used_at": api_key.last_used_at,
        "created_at": api_key.created_at,
        "updated_at": api_key.updated_at,
        "agents": [],
        "workflows": [],
    }

    # 添加用户信息（如果已预加载）
    if hasattr(api_key, "user") and api_key.user:
        response_data["user"] = {
            "id": api_key.user.id,
            "username": api_key.user.username,
        }

    # 添加关联的 Agent 信息
    if include_agents:
        agents = await api_key.agents.all()
        response_data["agents"] = [
            APIKeyAgentInfo(id=agent.id, name=agent.name, icon=agent.icon)
            for agent in agents
        ]

    # 添加关联的 Workflow 信息
    if include_workflows:
        from app.schemas.api_key import APIKeyWorkflowInfo

        workflows = await api_key.workflows.all()
        response_data["workflows"] = [
            APIKeyWorkflowInfo(id=workflow.id, name=workflow.name, icon=workflow.icon)
            for workflow in workflows
        ]

    return response_data


async def ensure_api_key_owner(api_key: APIKey, current_user: User) -> None:
    if current_user.is_superuser or api_key.user_id == current_user.id:
        return
    raise BusinessError(
        code=ResponseCode.PERMISSION_DENIED,
        msg_key="permission_denied",
        status_code=403,
    )


async def get_api_key_or_404(api_key_id: UUID) -> APIKey:
    api_key = (
        await APIKey.filter(id=api_key_id)
        .prefetch_related("user", "agents", "workflows")
        .first()
    )
    if not api_key:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="api_key_not_found",
            status_code=404,
        )
    return api_key


async def collect_allowed_agents(
    agent_ids: list[UUID] | None, user: User
) -> list[Agent]:
    agents = []
    for agent_id in agent_ids or []:
        agent = await check_agent_access(agent_id, user)
        agents.append(agent)
    return agents


async def collect_allowed_workflows(
    workflow_ids: list[UUID] | None, user: User
) -> list[Any]:
    workflows = []
    for workflow_id in workflow_ids or []:
        workflow = await check_workflow_access(workflow_id, user)
        workflows.append(workflow)
    return workflows


@router.get("", response_model=Response[PageData[APIKeyResponse]])
async def list_api_keys(
    page: int = 1,
    page_size: int = 20,
    status: Optional[list[str]] = Query(
        None, description="Filter by status: active, inactive, expired"
    ),
    user_id: Optional[list[UUID]] = Query(None, description="Filter by user ID"),
    search: Optional[str] = Query(None, description="Search by name or key prefix"),
    current_user: User = Depends(deps.PermissionChecker("apikey:read")),
) -> Any:
    """
    List all API keys with optional filters.
    Admin can see all keys, regular users can only see their own.
    """
    skip = (page - 1) * page_size
    now = now_utc()

    # Build query - admin sees all, regular user sees only their own
    if current_user.is_superuser:
        query = APIKey.all()
    else:
        query = APIKey.filter(user_id=current_user.id)

    # User filter (only for admin)
    if user_id and current_user.is_superuser:
        query = query.filter(user_id__in=user_id)

    # Status filter
    if status:
        status_conditions = Q()
        if "active" in status:
            status_conditions |= Q(is_active=True) & (
                Q(expires_at__isnull=True) | Q(expires_at__gt=now)
            )
        if "inactive" in status:
            status_conditions |= Q(is_active=False)
        if "expired" in status:
            status_conditions |= Q(expires_at__lt=now)
        if status_conditions:
            query = query.filter(status_conditions)

    # Search filter
    if search:
        query = query.filter(
            Q(name__icontains=search) | Q(key_prefix__icontains=search)
        )

    total = await query.count()
    api_keys = (
        await query.offset(skip)
        .limit(page_size)
        .order_by("-created_at")
        .prefetch_related("user", "agents")
    )

    # 构建响应数据
    items = []
    for api_key in api_keys:
        item = await build_api_key_response(api_key)
        items.append(item)

    return success(
        data={
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/stats", response_model=Response[APIKeyStats])
async def get_api_key_stats(
    current_user: User = Depends(deps.PermissionChecker("apikey:read")),
) -> Any:
    """
    Get API key statistics.
    """
    now = now_utc()

    # Admin sees all, regular user sees only their own
    if current_user.is_superuser:
        base_query = APIKey.all()
    else:
        base_query = APIKey.filter(user_id=current_user.id)

    total = await base_query.count()
    active = (
        await base_query.filter(is_active=True)
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        .count()
    )
    inactive = await base_query.filter(is_active=False).count()
    expired = await base_query.filter(expires_at__lt=now).count()

    return success(
        data={
            "total": total,
            "active": active,
            "inactive": inactive,
            "expired": expired,
        }
    )


@router.post("", response_model=Response[APIKeyCreateResponse])
async def create_api_key(
    *,
    request: Request,
    data: APIKeyCreate,
    current_user: User = Depends(deps.PermissionChecker("apikey:create")),
) -> Any:
    """
    Create a new API key.
    The full key is only returned once at creation time.
    """
    agents = await collect_allowed_agents(data.agent_ids, current_user)

    # 验证 Workflow IDs（检查是否存在且用户有权限访问）
    workflows = await collect_allowed_workflows(data.workflow_ids, current_user)

    # Generate API key
    full_key, key_prefix, key_hash = APIKey.generate_key()

    # Create API key record
    api_key = await APIKey.create(
        name=data.name,
        key_prefix=key_prefix,
        key_hash=key_hash,
        user_id=current_user.id,
        scopes=data.scopes,
        rate_limit=data.rate_limit,
        expires_at=data.expires_at,
    )

    # 关联 Agents
    if agents:
        await api_key.agents.add(*agents)

    # 关联 Workflows
    if workflows:
        await api_key.workflows.add(*workflows)

    # 记录审计日志
    await AuditLogService.log(
        user=current_user,
        action="create_api_key",
        resource_type="api_key",
        resource_id=api_key.id,
        resource_name=api_key.name,
        operation="create",
        status="success",
        request=request,
        metadata={
            "key_prefix": key_prefix,
            "scopes": data.scopes,
            "agent_count": len(agents),
            "workflow_count": len(workflows),
        },
    )

    # 重新查询以获取关联数据
    reloaded_api_key = (
        await APIKey.filter(id=api_key.id)
        .prefetch_related("user", "agents", "workflows")
        .first()
    )
    if reloaded_api_key is None:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="api_key_not_found",
            status_code=404,
        )

    # 构建响应
    response_data = await build_api_key_response(reloaded_api_key)
    response_data["key"] = full_key  # Only returned once

    return success(data=response_data, msg_key="api_key_created")


@router.get("/{api_key_id}", response_model=Response[APIKeyResponse])
async def get_api_key(
    api_key_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("apikey:read")),
) -> Any:
    """
    Get a specific API key by ID.
    """
    api_key = await get_api_key_or_404(api_key_id)
    await ensure_api_key_owner(api_key, current_user)

    response_data = await build_api_key_response(api_key)
    return success(data=response_data)


@router.put("/{api_key_id}", response_model=Response[APIKeyResponse])
async def update_api_key(
    *,
    request: Request,
    api_key_id: UUID,
    data: APIKeyUpdate,
    current_user: User = Depends(deps.PermissionChecker("apikey:update")),
) -> Any:
    """
    Update an API key.
    """
    api_key = await get_api_key_or_404(api_key_id)
    await ensure_api_key_owner(api_key, current_user)

    new_agents = (
        await collect_allowed_agents(data.agent_ids, current_user)
        if data.agent_ids is not None
        else None
    )
    new_workflows = (
        await collect_allowed_workflows(data.workflow_ids, current_user)
        if data.workflow_ids is not None
        else None
    )

    # 处理 Agent 关联更新
    if new_agents is not None:
        # 清除现有关联并添加新关联
        await api_key.agents.clear()
        if new_agents:
            await api_key.agents.add(*new_agents)

    # 处理 Workflow 关联更新
    if new_workflows is not None:
        # 清除现有关联并添加新关联
        await api_key.workflows.clear()
        if new_workflows:
            await api_key.workflows.add(*new_workflows)

    # Update other fields
    update_data = data.model_dump(
        exclude_unset=True, exclude={"agent_ids", "workflow_ids"}
    )
    if update_data:
        await api_key.update_from_dict(update_data)
        await api_key.save()

    # 重新加载（包括关系）
    reloaded_api_key = (
        await APIKey.filter(id=api_key_id)
        .prefetch_related("user", "agents", "workflows")
        .first()
    )
    if reloaded_api_key is None:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="api_key_not_found",
            status_code=404,
        )

    # 记录审计日志
    await AuditLogService.log(
        user=current_user,
        action="update_api_key",
        resource_type="api_key",
        resource_id=reloaded_api_key.id,
        resource_name=reloaded_api_key.name,
        operation="update",
        status="success",
        request=request,
        metadata={"fields_updated": list(data.model_dump(exclude_unset=True).keys())},
    )

    response_data = await build_api_key_response(reloaded_api_key)
    return success(data=response_data, msg_key="api_key_updated")


@router.delete("/{api_key_id}", response_model=Response[APIKeyResponse])
async def delete_api_key(
    request: Request,
    api_key_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("apikey:delete")),
) -> Any:
    """
    Delete an API key.
    """
    api_key = await get_api_key_or_404(api_key_id)
    await ensure_api_key_owner(api_key, current_user)

    # Store for response
    response_data = await build_api_key_response(api_key)

    # 记录审计日志（在删除前）
    await AuditLogService.log(
        user=current_user,
        action="delete_api_key",
        resource_type="api_key",
        resource_id=api_key.id,
        resource_name=api_key.name,
        operation="delete",
        status="success",
        request=request,
        metadata={"key_prefix": api_key.key_prefix},
    )

    # Delete
    await api_key.delete()

    return success(data=response_data, msg_key="api_key_deleted")


@router.post("/{api_key_id}/activate", response_model=Response[APIKeyResponse])
async def activate_api_key(
    request: Request,
    api_key_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("apikey:update")),
) -> Any:
    """
    Activate an API key.
    """
    api_key = await get_api_key_or_404(api_key_id)
    await ensure_api_key_owner(api_key, current_user)

    if api_key.is_active:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="api_key_already_active",
        )

    api_key.is_active = True
    await api_key.save()

    # 记录审计日志
    await AuditLogService.log(
        user=current_user,
        action="activate_api_key",
        resource_type="api_key",
        resource_id=api_key.id,
        resource_name=api_key.name,
        operation="update",
        status="success",
        request=request,
    )

    response_data = await build_api_key_response(api_key)
    return success(data=response_data, msg_key="api_key_activated")


@router.post("/{api_key_id}/deactivate", response_model=Response[APIKeyResponse])
async def deactivate_api_key(
    request: Request,
    api_key_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("apikey:update")),
) -> Any:
    """
    Deactivate an API key.
    """
    api_key = await get_api_key_or_404(api_key_id)
    await ensure_api_key_owner(api_key, current_user)

    if not api_key.is_active:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="api_key_already_inactive",
        )

    api_key.is_active = False
    await api_key.save()

    # 记录审计日志
    await AuditLogService.log(
        user=current_user,
        action="deactivate_api_key",
        resource_type="api_key",
        resource_id=api_key.id,
        resource_name=api_key.name,
        operation="update",
        status="success",
        request=request,
    )

    response_data = await build_api_key_response(api_key)
    return success(data=response_data, msg_key="api_key_deactivated")
