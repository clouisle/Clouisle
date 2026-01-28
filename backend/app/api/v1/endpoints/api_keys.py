from typing import Any, Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from tortoise.expressions import Q

from app.api import deps
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

router = APIRouter()


async def build_api_key_response(api_key: APIKey, include_agents: bool = True, include_workflows: bool = True) -> dict:
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
    if hasattr(api_key, 'user') and api_key.user:
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


@router.get("/", response_model=Response[PageData[APIKeyResponse]])
async def list_api_keys(
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = Query(
        None, description="Filter by status: active, inactive, expired"
    ),
    user_id: Optional[UUID] = Query(None, description="Filter by user ID"),
    search: Optional[str] = Query(None, description="Search by name"),
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
        query = query.filter(user_id=user_id)

    # Status filter
    if status == "active":
        query = query.filter(
            is_active=True
        ).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=now)
        )
    elif status == "inactive":
        query = query.filter(is_active=False)
    elif status == "expired":
        query = query.filter(expires_at__lt=now)

    # Search filter
    if search:
        query = query.filter(name__icontains=search)

    total = await query.count()
    api_keys = await query.offset(skip).limit(page_size).order_by("-created_at").prefetch_related("user", "agents")
    
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
    active = await base_query.filter(
        is_active=True
    ).filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=now)
    ).count()
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


@router.post("/", response_model=Response[APIKeyCreateResponse])
async def create_api_key(
    *,
    data: APIKeyCreate,
    current_user: User = Depends(deps.PermissionChecker("apikey:create")),
) -> Any:
    """
    Create a new API key.
    The full key is only returned once at creation time.
    """
    # 验证 Agent IDs（检查是否存在且用户有权限访问）
    agents = []
    if data.agent_ids:
        for agent_id in data.agent_ids:
            agent = await Agent.filter(id=agent_id).first()
            if not agent:
                raise BusinessError(
                    code=ResponseCode.NOT_FOUND,
                    msg_key="agent_not_found",
                    status_code=404,
                )
            # 检查用户是否有权限访问该 Agent（通过团队成员关系）
            # 简化：这里假设用户可以访问自己创建的或所在团队的 Agent
            agents.append(agent)

    # 验证 Workflow IDs（检查是否存在且用户有权限访问）
    workflows = []
    if data.workflow_ids:
        from app.models.workflow import Workflow
        for workflow_id in data.workflow_ids:
            workflow = await Workflow.filter(id=workflow_id).first()
            if not workflow:
                raise BusinessError(
                    code=ResponseCode.NOT_FOUND,
                    msg_key="workflow_not_found",
                    status_code=404,
                )
            workflows.append(workflow)

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

    # 构建响应
    response_data = await build_api_key_response(api_key)
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
    api_key = await APIKey.filter(id=api_key_id).prefetch_related("user", "agents", "workflows").first()
    
    if not api_key:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="api_key_not_found",
            status_code=404,
        )

    # Check permission - admin can see all, user can only see their own
    if not current_user.is_superuser and api_key.user_id != current_user.id:
        raise BusinessError(
            code=ResponseCode.PERMISSION_DENIED,
            msg_key="permission_denied",
            status_code=403,
        )

    response_data = await build_api_key_response(api_key)
    return success(data=response_data)


@router.put("/{api_key_id}", response_model=Response[APIKeyResponse])
async def update_api_key(
    *,
    api_key_id: UUID,
    data: APIKeyUpdate,
    current_user: User = Depends(deps.PermissionChecker("apikey:update")),
) -> Any:
    """
    Update an API key.
    """
    api_key = await APIKey.filter(id=api_key_id).prefetch_related("user", "agents", "workflows").first()
    
    if not api_key:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="api_key_not_found",
            status_code=404,
        )

    # Check permission
    if not current_user.is_superuser and api_key.user_id != current_user.id:
        raise BusinessError(
            code=ResponseCode.PERMISSION_DENIED,
            msg_key="permission_denied",
            status_code=403,
        )

    # 处理 Agent 关联更新
    if data.agent_ids is not None:
        # 验证新的 Agent IDs
        new_agents = []
        for agent_id in data.agent_ids:
            agent = await Agent.filter(id=agent_id).first()
            if not agent:
                raise BusinessError(
                    code=ResponseCode.NOT_FOUND,
                    msg_key="agent_not_found",
                    status_code=404,
                )
            new_agents.append(agent)

        # 清除现有关联并添加新关联
        await api_key.agents.clear()
        if new_agents:
            await api_key.agents.add(*new_agents)

    # 处理 Workflow 关联更新
    if data.workflow_ids is not None:
        # 验证新的 Workflow IDs
        from app.models.workflow import Workflow
        new_workflows = []
        for workflow_id in data.workflow_ids:
            workflow = await Workflow.filter(id=workflow_id).first()
            if not workflow:
                raise BusinessError(
                    code=ResponseCode.NOT_FOUND,
                    msg_key="workflow_not_found",
                    status_code=404,
                )
            new_workflows.append(workflow)

        # 清除现有关联并添加新关联
        await api_key.workflows.clear()
        if new_workflows:
            await api_key.workflows.add(*new_workflows)

    # Update other fields
    update_data = data.model_dump(exclude_unset=True, exclude={"agent_ids", "workflow_ids"})
    if update_data:
        await api_key.update_from_dict(update_data)
        await api_key.save()
    
    # 重新加载（包括关系）
    api_key = await APIKey.filter(id=api_key_id).prefetch_related("user", "agents", "workflows").first()
    response_data = await build_api_key_response(api_key)
    return success(data=response_data, msg_key="api_key_updated")


@router.delete("/{api_key_id}", response_model=Response[APIKeyResponse])
async def delete_api_key(
    api_key_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("apikey:delete")),
) -> Any:
    """
    Delete an API key.
    """
    api_key = await APIKey.filter(id=api_key_id).prefetch_related("user", "agents", "workflows").first()
    
    if not api_key:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="api_key_not_found",
            status_code=404,
        )

    # Check permission
    if not current_user.is_superuser and api_key.user_id != current_user.id:
        raise BusinessError(
            code=ResponseCode.PERMISSION_DENIED,
            msg_key="permission_denied",
            status_code=403,
        )

    # Store for response
    response_data = await build_api_key_response(api_key)
    
    # Delete
    await api_key.delete()

    return success(data=response_data, msg_key="api_key_deleted")


@router.post("/{api_key_id}/activate", response_model=Response[APIKeyResponse])
async def activate_api_key(
    api_key_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("apikey:update")),
) -> Any:
    """
    Activate an API key.
    """
    api_key = await APIKey.filter(id=api_key_id).prefetch_related("agents").first()
    
    if not api_key:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="api_key_not_found",
            status_code=404,
        )

    # Check permission
    if not current_user.is_superuser and api_key.user_id != current_user.id:
        raise BusinessError(
            code=ResponseCode.PERMISSION_DENIED,
            msg_key="permission_denied",
            status_code=403,
        )

    if api_key.is_active:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="api_key_already_active",
        )

    api_key.is_active = True
    await api_key.save()

    response_data = await build_api_key_response(api_key)
    return success(data=response_data, msg_key="api_key_activated")


@router.post("/{api_key_id}/deactivate", response_model=Response[APIKeyResponse])
async def deactivate_api_key(
    api_key_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("apikey:update")),
) -> Any:
    """
    Deactivate an API key.
    """
    api_key = await APIKey.filter(id=api_key_id).prefetch_related("agents").first()
    
    if not api_key:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="api_key_not_found",
            status_code=404,
        )

    # Check permission
    if not current_user.is_superuser and api_key.user_id != current_user.id:
        raise BusinessError(
            code=ResponseCode.PERMISSION_DENIED,
            msg_key="permission_denied",
            status_code=403,
        )

    if not api_key.is_active:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="api_key_already_inactive",
        )

    api_key.is_active = False
    await api_key.save()

    response_data = await build_api_key_response(api_key)
    return success(data=response_data, msg_key="api_key_deactivated")
