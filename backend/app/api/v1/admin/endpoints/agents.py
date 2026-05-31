"""Admin agent management endpoints."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from tortoise.expressions import Q

from app.api import deps
from app.api.v1.endpoints.agents import build_agent_out, build_agent_list_out
from app.models.agent import Agent, AgentKnowledgeBase, AgentStatus, AgentVisibility
from app.models.model import TeamModel
from app.models.notification import AutoNotificationType
from app.models.user import Team, User
from app.schemas.agent import AgentOut, AgentListOut, ModelInfo
from app.schemas.response import BusinessError, PageData, Response, ResponseCode, success
from app.services.audit_log import AuditLogService
from app.services.auto_notification import AutoNotificationService
from app.core.i18n import t

router = APIRouter()


def _option(value: str, label: str | None = None) -> dict[str, str]:
    return {"value": value, "label": label or value}


async def _get_agent(agent_id: UUID, *, detail: bool = False) -> Agent:
    query = Agent.filter(id=agent_id)
    if detail:
        query = query.prefetch_related(
            "team", "created_by", "agent_knowledge_bases__knowledge_base"
        )
    agent = await query.first()
    if not agent:
        raise BusinessError(
            code=ResponseCode.AGENT_NOT_FOUND,
            msg_key="agent_not_found",
            status_code=404,
        )
    return agent


async def _get_model_info_map(agents: list[Agent]) -> dict[str, ModelInfo]:
    model_ids = [agent.model_id for agent in agents if agent.model_id]
    model_info_map: dict[str, ModelInfo] = {}
    if not model_ids:
        return model_info_map

    team_models = await TeamModel.filter(id__in=model_ids).prefetch_related("model")
    for team_model in team_models:
        model_info_map[str(team_model.id)] = ModelInfo(
            id=team_model.id,
            name=team_model.model.name,
            provider=team_model.model.provider,
            model_id=team_model.model.model_id,
        )
    return model_info_map


@router.get("", response_model=Response[PageData[AgentListOut]])
async def list_agents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    status: list[AgentStatus] | None = Query(None),
    visibility: list[AgentVisibility] | None = Query(None),
    team_id: list[UUID] | None = Query(None),
    creator: list[str] | None = Query(None),
    current_user: User = Depends(deps.PermissionChecker("admin:app:read")),
) -> Any:
    query = Agent.all()

    if search:
        query = query.filter(Q(name__icontains=search) | Q(description__icontains=search))
    if status:
        query = query.filter(status__in=status)
    if visibility:
        query = query.filter(visibility__in=visibility)
    if team_id:
        query = query.filter(team_id__in=team_id)
    if creator:
        query = query.filter(created_by__username__in=creator)

    total = await query.count()
    skip = (page - 1) * page_size
    agents = (
        await query.prefetch_related("team", "created_by")
        .order_by("-updated_at")
        .offset(skip)
        .limit(page_size)
    )
    model_info_map = await _get_model_info_map(agents)
    items = [await build_agent_list_out(agent, model_info_map) for agent in agents]

    return success(data={"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/filters", response_model=Response[dict[str, list[dict[str, str]]]])
async def get_agent_filter_options(
    current_user: User = Depends(deps.PermissionChecker("admin:app:read")),
) -> Any:
    agents = await Agent.all().prefetch_related("created_by")
    teams = await Team.all().order_by("name")
    creator_values = sorted(
        {agent.created_by.username for agent in agents if agent.created_by}
    )
    return success(
        data={
            "statuses": [_option(AgentStatus.DRAFT.value), _option(AgentStatus.PUBLISHED.value)],
            "visibilities": [
                _option(AgentVisibility.PRIVATE.value),
                _option(AgentVisibility.TEAM.value),
            ],
            "teams": [_option(str(team.id), team.name) for team in teams],
            "creators": [_option(value) for value in creator_values],
        }
    )


@router.get("/{agent_id}", response_model=Response[AgentOut])
async def get_agent(
    agent_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("admin:app:read")),
) -> Any:
    agent = await _get_agent(agent_id, detail=True)
    return success(data=await build_agent_out(agent))


@router.post("/{agent_id}/publish", response_model=Response[AgentOut])
async def publish_agent(
    request: Request,
    agent_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("admin:app:publish")),
) -> Any:
    agent = await _get_agent(agent_id, detail=True)
    old_status = agent.status
    agent.status = AgentStatus.PUBLISHED
    await agent.save()

    await AuditLogService.log(
        user=current_user,
        action="admin_publish_agent",
        resource_type="agent",
        resource_id=agent.id,
        resource_name=agent.name,
        operation="update",
        status="success",
        request=request,
        changes={
            "before": {"status": old_status.value},
            "after": {"status": agent.status.value},
        },
        metadata={"team_id": str(agent.team_id), "visibility": agent.visibility.value},
    )
    if agent.team_id:
        await AutoNotificationService.send_to_team(
            notification_type=AutoNotificationType.AGENT_PUBLISHED,
            team_id=UUID(str(agent.team_id)),
            title=t("notify_agent_published_title"),
            content=t("notify_agent_published_content", agent_name=agent.name),
        )

    return success(data=await build_agent_out(agent), msg_key="agent_published")


@router.post("/{agent_id}/unpublish", response_model=Response[AgentOut])
async def unpublish_agent(
    request: Request,
    agent_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("admin:app:publish")),
) -> Any:
    agent = await _get_agent(agent_id, detail=True)
    old_status = agent.status
    agent.status = AgentStatus.DRAFT
    await agent.save()

    await AuditLogService.log(
        user=current_user,
        action="admin_unpublish_agent",
        resource_type="agent",
        resource_id=agent.id,
        resource_name=agent.name,
        operation="update",
        status="success",
        request=request,
        changes={
            "before": {"status": old_status.value},
            "after": {"status": agent.status.value},
        },
        metadata={"team_id": str(agent.team_id), "visibility": agent.visibility.value},
    )
    if agent.team_id:
        await AutoNotificationService.send_to_team(
            notification_type=AutoNotificationType.AGENT_UNPUBLISHED,
            team_id=UUID(str(agent.team_id)),
            title=t("notify_agent_unpublished_title"),
            content=t("notify_agent_unpublished_content", agent_name=agent.name),
        )

    return success(data=await build_agent_out(agent), msg_key="agent_unpublished")


@router.post("/{agent_id}/duplicate", response_model=Response[AgentOut])
async def duplicate_agent(
    request: Request,
    agent_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("admin:app:duplicate")),
) -> Any:
    agent = await _get_agent(agent_id)
    new_agent = await Agent.create(
        name=f"{agent.name} (Copy)",
        description=agent.description,
        icon=agent.icon,
        avatar_url=agent.avatar_url,
        team_id=agent.team_id,
        model_id=agent.model_id,
        system_prompt=agent.system_prompt,
        max_iterations=agent.max_iterations,
        hide_tool_calls=agent.hide_tool_calls,
        tools_config=agent.tools_config,
        enable_vision=agent.enable_vision,
        enable_file_upload=agent.enable_file_upload,
        file_upload_config=agent.file_upload_config,
        enable_user_input_request=agent.enable_user_input_request,
        enable_memory=agent.enable_memory,
        memory_config=agent.memory_config,
        context_compression_config=agent.context_compression_config,
        enable_image_generation=agent.enable_image_generation,
        image_generation_config={
            key: value
            for key, value in (agent.image_generation_config or {}).items()
            if key != "allow_model_override"
        },
        enable_video_generation=agent.enable_video_generation,
        video_generation_config={
            key: value
            for key, value in (agent.video_generation_config or {}).items()
            if key != "allow_model_override"
        },
        rag_mode=agent.rag_mode,
        variables=agent.variables,
        opening_message=agent.opening_message,
        suggested_questions=agent.suggested_questions,
        visibility=AgentVisibility.PRIVATE,
        status=AgentStatus.DRAFT,
        created_by=current_user,
    )

    kb_associations = await AgentKnowledgeBase.filter(agent_id=agent.id)
    for association in kb_associations:
        await AgentKnowledgeBase.create(
            agent=new_agent,
            knowledge_base_id=association.knowledge_base_id,
            retrieval_top_k=association.retrieval_top_k,
            score_threshold=association.score_threshold,
            search_mode=association.search_mode,
        )

    new_agent = await Agent.get(id=new_agent.id).prefetch_related("team", "created_by")
    await AuditLogService.log(
        user=current_user,
        action="admin_duplicate_agent",
        resource_type="agent",
        resource_id=new_agent.id,
        resource_name=new_agent.name,
        operation="create",
        status="success",
        request=request,
        metadata={
            "source_agent_id": str(agent.id),
            "team_id": str(agent.team_id),
            "source_visibility": agent.visibility.value,
            "new_agent_id": str(new_agent.id),
        },
    )
    return success(data=await build_agent_out(new_agent), msg_key="agent_duplicated")


@router.delete("/{agent_id}", response_model=Response[dict])
async def delete_agent(
    request: Request,
    agent_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("admin:app:delete")),
) -> Any:
    agent = await _get_agent(agent_id)
    await AuditLogService.log(
        user=current_user,
        action="admin_delete_agent",
        resource_type="agent",
        resource_id=agent.id,
        resource_name=agent.name,
        operation="delete",
        status="success",
        request=request,
        metadata={"team_id": str(agent.team_id), "visibility": agent.visibility},
    )
    await agent.delete()
    return success(data={"id": str(agent_id)}, msg_key="agent_deleted")
