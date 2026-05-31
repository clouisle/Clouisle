"""Admin agent management endpoints."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from tortoise.expressions import Q

from app.api import deps
from app.api.v1.endpoints.agents import (
    build_agent_out,
    build_agent_list_out,
    normalize_agent_visibility,
)
from app.models.agent import (
    Agent,
    AgentKnowledgeBase,
    AgentStatus,
    AgentVisibility,
    RAGMode,
)
from app.models.knowledge_base import KnowledgeBase
from app.models.model import TeamModel
from app.models.notification import AutoNotificationType
from app.models.user import Team, User
from app.schemas.agent import (
    AgentCreate,
    AgentOut,
    AgentUpdate,
    AgentListOut,
    ModelInfo,
)
from app.schemas.response import (
    BusinessError,
    PageData,
    Response,
    ResponseCode,
    success,
)
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
        query = query.filter(
            Q(name__icontains=search) | Q(description__icontains=search)
        )
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

    return success(
        data={"items": items, "total": total, "page": page, "page_size": page_size}
    )


@router.get("/filters", response_model=Response[dict[str, list[dict[str, str]]]])
async def get_agent_filter_options(
    current_user: User = Depends(deps.PermissionChecker("admin:app:read")),
) -> Any:
    teams = await Team.all().order_by("name")
    creator_values = (
        await Agent.filter(created_by__isnull=False)
        .distinct()
        .values_list("created_by__username", flat=True)
    )
    creator_values = sorted(creator_values)
    return success(
        data={
            "statuses": [
                _option(AgentStatus.DRAFT.value),
                _option(AgentStatus.PUBLISHED.value),
            ],
            "visibilities": [
                _option(AgentVisibility.PRIVATE.value),
                _option(AgentVisibility.TEAM.value),
            ],
            "teams": [_option(str(team.id), team.name) for team in teams],
            "creators": [_option(value) for value in creator_values],
        }
    )


@router.post("", response_model=Response[AgentOut])
async def create_agent(
    request: Request,
    agent_in: AgentCreate,
    current_user: User = Depends(deps.PermissionChecker("admin:app:create")),
) -> Any:
    team = await Team.filter(id=agent_in.team_id).first()
    if not team:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="team_not_found",
            status_code=404,
        )

    existing = await Agent.filter(team_id=agent_in.team_id, name=agent_in.name).first()
    if existing:
        raise BusinessError(
            code=ResponseCode.DUPLICATE_NAME,
            msg_key="agent_name_exists",
        )

    if agent_in.model_id:
        team_model = await TeamModel.filter(
            id=agent_in.model_id,
            team_id=agent_in.team_id,
            is_enabled=True,
        ).first()
        if not team_model:
            raise BusinessError(
                code=ResponseCode.MODEL_NOT_AUTHORIZED,
                msg_key="model_not_authorized",
            )

    for kb_config in agent_in.knowledge_base_configs:
        kb = await KnowledgeBase.filter(
            id=kb_config.knowledge_base_id,
            team_id=agent_in.team_id,
        ).first()
        if not kb:
            raise BusinessError(
                code=ResponseCode.KB_NOT_FOUND,
                msg_key="kb_not_found",
                status_code=404,
            )

    from app.services.skill import SkillService

    await SkillService.validate_agent_skill_configs(
        None,
        [tool.model_dump() for tool in agent_in.tools_config],
        agent_in.team_id,
    )

    agent = await Agent.create(
        name=agent_in.name,
        description=agent_in.description,
        icon=agent_in.icon,
        avatar_url=agent_in.avatar_url,
        team=team,
        model_id=agent_in.model_id,
        system_prompt=agent_in.system_prompt,
        max_iterations=agent_in.max_iterations,
        hide_tool_calls=agent_in.hide_tool_calls,
        tools_config=[tool.model_dump() for tool in agent_in.tools_config],
        enable_vision=agent_in.enable_vision,
        enable_file_upload=agent_in.enable_file_upload,
        file_upload_config=agent_in.file_upload_config.model_dump()
        if agent_in.file_upload_config
        else {},
        enable_user_input_request=agent_in.enable_user_input_request,
        enable_memory=agent_in.enable_memory,
        memory_config=agent_in.memory_config.model_dump()
        if agent_in.memory_config
        else {},
        context_compression_config=agent_in.context_compression_config.model_dump()
        if agent_in.context_compression_config
        else {},
        enable_image_generation=agent_in.enable_image_generation,
        image_generation_config=agent_in.image_generation_config.model_dump()
        if agent_in.image_generation_config
        else {},
        enable_video_generation=agent_in.enable_video_generation,
        video_generation_config=agent_in.video_generation_config.model_dump()
        if agent_in.video_generation_config
        else {},
        rag_mode=agent_in.rag_mode,
        variables=[variable.model_dump() for variable in agent_in.variables],
        opening_message=agent_in.opening_message,
        suggested_questions=agent_in.suggested_questions,
        visibility=normalize_agent_visibility(agent_in.visibility),
        created_by=current_user,
    )

    for kb_config in agent_in.knowledge_base_configs:
        await AgentKnowledgeBase.create(
            agent=agent,
            knowledge_base_id=kb_config.knowledge_base_id,
            retrieval_top_k=kb_config.retrieval_top_k,
            score_threshold=kb_config.score_threshold,
            search_mode=kb_config.search_mode,
        )

    agent = await Agent.get(id=agent.id).prefetch_related("team", "created_by")
    await AuditLogService.log(
        user=current_user,
        action="admin_create_agent",
        resource_type="agent",
        resource_id=agent.id,
        resource_name=agent.name,
        operation="create",
        status="success",
        request=request,
        metadata={
            "team_id": str(team.id),
            "team_name": team.name,
            "visibility": normalize_agent_visibility(agent_in.visibility),
            "kb_count": len(agent_in.knowledge_base_configs),
        },
    )
    return success(data=await build_agent_out(agent), msg_key="agent_created")


@router.get("/{agent_id}", response_model=Response[AgentOut])
async def get_agent(
    agent_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("admin:app:read")),
) -> Any:
    agent = await _get_agent(agent_id, detail=True)
    return success(data=await build_agent_out(agent))


@router.put("/{agent_id}", response_model=Response[AgentOut])
async def update_agent(
    request: Request,
    agent_id: UUID,
    agent_in: AgentUpdate,
    current_user: User = Depends(deps.PermissionChecker("admin:app:update")),
) -> Any:
    agent = await _get_agent(agent_id, detail=True)

    if agent_in.name is not None and agent_in.name != agent.name:
        existing = (
            await Agent.filter(team_id=agent.team_id, name=agent_in.name)
            .exclude(id=agent_id)
            .first()
        )
        if existing:
            raise BusinessError(
                code=ResponseCode.DUPLICATE_NAME,
                msg_key="agent_name_exists",
            )

    updated_fields = []

    if agent_in.name is not None:
        agent.name = agent_in.name
        updated_fields.append("name")
    if agent_in.description is not None:
        agent.description = agent_in.description
        updated_fields.append("description")
    if agent_in.icon is not None:
        agent.icon = agent_in.icon
        updated_fields.append("icon")
    if agent_in.avatar_url is not None:
        agent.avatar_url = agent_in.avatar_url
        updated_fields.append("avatar_url")
    if agent_in.system_prompt is not None:
        agent.system_prompt = agent_in.system_prompt
        updated_fields.append("system_prompt")
    if agent_in.max_iterations is not None:
        agent.max_iterations = agent_in.max_iterations
        updated_fields.append("max_iterations")
    if agent_in.hide_tool_calls is not None:
        agent.hide_tool_calls = agent_in.hide_tool_calls
        updated_fields.append("hide_tool_calls")
    if agent_in.opening_message is not None:
        agent.opening_message = agent_in.opening_message
        updated_fields.append("opening_message")
    if agent_in.suggested_questions is not None:
        agent.suggested_questions = agent_in.suggested_questions
        updated_fields.append("suggested_questions")
    if agent_in.visibility is not None:
        agent.visibility = AgentVisibility(
            normalize_agent_visibility(agent_in.visibility)
        )
        updated_fields.append("visibility")

    if agent_in.model_id is not None:
        team_model = await TeamModel.filter(
            id=agent_in.model_id,
            team_id=agent.team_id,
            is_enabled=True,
        ).first()
        if not team_model:
            raise BusinessError(
                code=ResponseCode.MODEL_NOT_AUTHORIZED,
                msg_key="model_not_authorized",
            )
        agent.model_id = agent_in.model_id
        updated_fields.append("model_id")

    if agent_in.tools_config is not None:
        from app.services.skill import SkillService

        tools_config = [tool.model_dump() for tool in agent_in.tools_config]
        await SkillService.validate_agent_skill_configs(
            agent, tools_config, agent.team_id
        )
        agent.tools_config = tools_config
        updated_fields.append("tools_config")

    if agent_in.enable_vision is not None:
        agent.enable_vision = agent_in.enable_vision
        updated_fields.append("enable_vision")
    if agent_in.enable_file_upload is not None:
        agent.enable_file_upload = agent_in.enable_file_upload
        updated_fields.append("enable_file_upload")
    if agent_in.file_upload_config is not None:
        file_upload_config = (
            agent_in.file_upload_config.model_dump()
            if hasattr(agent_in.file_upload_config, "model_dump")
            else agent_in.file_upload_config
        )
        agent.file_upload_config = cast(dict[str, Any], file_upload_config)
        updated_fields.append("file_upload_config")
    if agent_in.enable_user_input_request is not None:
        agent.enable_user_input_request = agent_in.enable_user_input_request
        updated_fields.append("enable_user_input_request")
    if agent_in.enable_memory is not None:
        agent.enable_memory = agent_in.enable_memory
        updated_fields.append("enable_memory")
    if agent_in.memory_config is not None:
        agent.memory_config = agent_in.memory_config.model_dump()
        updated_fields.append("memory_config")
    if agent_in.context_compression_config is not None:
        agent.context_compression_config = (
            agent_in.context_compression_config.model_dump()
        )
        updated_fields.append("context_compression_config")
    if agent_in.enable_image_generation is not None:
        agent.enable_image_generation = agent_in.enable_image_generation
        updated_fields.append("enable_image_generation")
    if agent_in.image_generation_config is not None:
        agent.image_generation_config = agent_in.image_generation_config.model_dump()
        updated_fields.append("image_generation_config")
    if agent_in.enable_video_generation is not None:
        agent.enable_video_generation = agent_in.enable_video_generation
        updated_fields.append("enable_video_generation")
    if agent_in.video_generation_config is not None:
        agent.video_generation_config = agent_in.video_generation_config.model_dump()
        updated_fields.append("video_generation_config")
    if agent_in.rag_mode is not None:
        agent.rag_mode = RAGMode(agent_in.rag_mode)
        updated_fields.append("rag_mode")
    if agent_in.variables is not None:
        agent.variables = [variable.model_dump() for variable in agent_in.variables]
        updated_fields.append("variables")
    if agent_in.embed_config is not None:
        agent.embed_config = agent_in.embed_config
        updated_fields.append("embed_config")

    await agent.save()

    if agent_in.knowledge_base_configs is not None:
        for kb_config in agent_in.knowledge_base_configs:
            kb = await KnowledgeBase.filter(
                id=kb_config.knowledge_base_id,
                team_id=agent.team_id,
            ).first()
            if not kb:
                raise BusinessError(
                    code=ResponseCode.KB_NOT_FOUND,
                    msg_key="kb_not_found",
                    status_code=404,
                )

        await AgentKnowledgeBase.filter(agent_id=agent.id).delete()
        for kb_config in agent_in.knowledge_base_configs:
            await AgentKnowledgeBase.create(
                agent=agent,
                knowledge_base_id=kb_config.knowledge_base_id,
                retrieval_top_k=kb_config.retrieval_top_k,
                score_threshold=kb_config.score_threshold,
                search_mode=kb_config.search_mode,
            )
        updated_fields.append("knowledge_base_configs")

    agent = await Agent.get(id=agent_id).prefetch_related("team", "created_by")
    await AuditLogService.log(
        user=current_user,
        action="admin_update_agent",
        resource_type="agent",
        resource_id=agent.id,
        resource_name=agent.name,
        operation="update",
        status="success",
        request=request,
        metadata={
            "fields_updated": updated_fields,
            "team_id": str(agent.team_id),
            "visibility": agent.visibility.value,
        },
    )
    return success(data=await build_agent_out(agent), msg_key="agent_updated")


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
