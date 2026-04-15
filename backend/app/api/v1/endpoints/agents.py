"""
Agent API endpoints.
Provides CRUD operations for agents and conversations.
"""

import logging
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from tortoise.expressions import F, Q
from tortoise.functions import Count

from app.api import deps
from app.models.user import User, Team, TeamMember
from app.models.model import TeamModel, Model
from app.models.knowledge_base import KnowledgeBase
from app.models.agent import (
    Agent,
    AgentKnowledgeBase,
    AgentStatus,
    AgentVisibility,
    Conversation,
    Message,
    RAGMode,
)
from app.schemas.agent import (
    AgentCreate,
    AgentUpdate,
    AgentOut,
    AgentListOut,
    AgentKnowledgeBaseOut,
    ModelInfo,
    KnowledgeBaseInfo,
    TeamInfo,
    CreatorInfo,
    ConversationOut,
    ConversationListOut,
    ConversationUpdate,
    ConversationWithMessages,
    MessageOut,
)
from app.schemas.response import (
    Response,
    PageData,
    ResponseCode,
    BusinessError,
    success,
)
from app.services.audit_log import AuditLogService
from app.services.auto_notification import AutoNotificationService
from app.models.notification import AutoNotificationType
from app.core.i18n import t
from app.api.v1.endpoints.chat import build_message_round_payloads

router = APIRouter()
logger = logging.getLogger(__name__)


# ============ Helper Functions ============


def normalize_agent_visibility(visibility: str) -> str:
    """Normalize legacy public visibility to team."""
    return AgentVisibility.TEAM if visibility == AgentVisibility.PUBLIC else visibility


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


async def check_agent_access(
    agent_id: UUID, user: User, require_write: bool = False
) -> Agent:
    """Check if user has access to the agent."""
    agent = (
        await Agent.filter(id=agent_id)
        .prefetch_related(
            "team", "created_by", "model", "agent_knowledge_bases__knowledge_base"
        )
        .first()
    )
    if not agent:
        raise BusinessError(
            code=ResponseCode.AGENT_NOT_FOUND,
            msg_key="agent_not_found",
            status_code=404,
        )

    if agent.visibility == AgentVisibility.PRIVATE:
        if (
            agent.created_by
            and agent.created_by.id != user.id
            and not user.is_superuser
        ):
            raise BusinessError(
                code=ResponseCode.AGENT_ACCESS_DENIED,
                msg_key="agent_access_denied",
                status_code=403,
            )
        if not agent.created_by and not user.is_superuser:
            await check_team_access(agent.team.id, user, require_admin=require_write)
    else:
        await check_team_access(agent.team.id, user, require_admin=require_write)

    return agent


async def get_model_info(team_model: TeamModel | None) -> ModelInfo | None:
    """Get model info from TeamModel."""
    if not team_model:
        return None
    model = await Model.filter(id=team_model.model_id).first()
    if not model:
        return None
    return ModelInfo(
        id=team_model.id,
        name=model.name,
        provider=model.provider,
        model_id=model.model_id,
    )


async def build_agent_out(agent: Agent) -> dict:
    """Build AgentOut response with all relations."""
    # Get model info
    model_info = None
    if agent.model_id:
        team_model = (
            await TeamModel.filter(id=agent.model_id).prefetch_related("model").first()
        )
        if team_model:
            model_info = ModelInfo(
                id=team_model.id,
                name=team_model.model.name,
                provider=team_model.model.provider,
                model_id=team_model.model.model_id,
            )

    # Get knowledge bases
    kb_associations = await AgentKnowledgeBase.filter(
        agent_id=agent.id
    ).prefetch_related("knowledge_base")
    knowledge_bases = []
    for akb in kb_associations:
        kb = akb.knowledge_base
        knowledge_bases.append(
            AgentKnowledgeBaseOut(
                id=akb.id,
                knowledge_base=KnowledgeBaseInfo(
                    id=kb.id,
                    name=kb.name,
                    description=kb.description,
                    icon=kb.icon,
                    document_count=kb.document_count,
                ),
                retrieval_top_k=akb.retrieval_top_k,
                score_threshold=akb.score_threshold,
                search_mode=akb.search_mode,
            )
        )

    def _sanitize_media_config(config: dict[str, Any] | None) -> dict[str, Any] | None:
        if not config:
            return None

        sanitized = dict(config)
        sanitized.pop("allow_model_override", None)
        return sanitized or None

    # Manually build the dict to avoid QuerySet issues with ForeignKey fields
    agent_data = {
        "id": agent.id,
        "name": agent.name,
        "description": agent.description,
        "icon": agent.icon,
        "avatar_url": agent.avatar_url,
        "team": TeamInfo.model_validate(agent.team).model_dump(),
        "model_id": str(agent.model_id) if agent.model_id else None,
        "model": model_info.model_dump() if model_info else None,
        "system_prompt": agent.system_prompt,
        "max_iterations": agent.max_iterations,
        "tools_config": agent.tools_config or [],
        "enable_vision": agent.enable_vision,
        "enable_file_upload": agent.enable_file_upload,
        "file_upload_config": agent.file_upload_config
        if agent.file_upload_config
        else None,
        "enable_user_input_request": agent.enable_user_input_request,
        "enable_memory": agent.enable_memory,
        "memory_config": agent.memory_config if agent.memory_config else None,
        "context_compression_config": agent.context_compression_config
        if agent.context_compression_config
        else None,
        "enable_image_generation": agent.enable_image_generation,
        "image_generation_config": _sanitize_media_config(
            agent.image_generation_config
        ),
        "enable_video_generation": agent.enable_video_generation,
        "video_generation_config": _sanitize_media_config(
            agent.video_generation_config
        ),
        "rag_mode": agent.rag_mode.value
        if hasattr(agent.rag_mode, "value")
        else agent.rag_mode,
        "variables": agent.variables or [],
        "opening_message": agent.opening_message,
        "suggested_questions": agent.suggested_questions or [],
        "knowledge_bases": [kb.model_dump() for kb in knowledge_bases],
        "embed_config": agent.embed_config or {},
        "status": agent.status.value
        if hasattr(agent.status, "value")
        else agent.status,
        "visibility": normalize_agent_visibility(
            agent.visibility.value
            if hasattr(agent.visibility, "value")
            else agent.visibility
        ),
        "conversation_count": agent.conversation_count,
        "message_count": agent.message_count,
        "created_by": CreatorInfo.model_validate(agent.created_by).model_dump()
        if agent.created_by
        else None,
        "created_at": agent.created_at,
        "updated_at": agent.updated_at,
    }
    return agent_data


async def build_agent_list_out(
    agent: Agent, model_info_map: dict[str, ModelInfo] | None = None
) -> dict:
    """Build AgentListOut response.

    Args:
        agent: Agent instance
        model_info_map: Optional pre-fetched model info mapping (model_id -> ModelInfo)
    """
    model_info = None
    if agent.model_id:
        # Use pre-fetched model info if available (batch query optimization)
        if model_info_map and str(agent.model_id) in model_info_map:
            model_info = model_info_map[str(agent.model_id)]
        else:
            # Fallback to individual query
            team_model = (
                await TeamModel.filter(id=agent.model_id)
                .prefetch_related("model")
                .first()
            )
            if team_model:
                model_info = ModelInfo(
                    id=team_model.id,
                    name=team_model.model.name,
                    provider=team_model.model.provider,
                    model_id=team_model.model.model_id,
                )

    # Manually build the dict to avoid QuerySet issues with ForeignKey fields
    agent_data = {
        "id": agent.id,
        "name": agent.name,
        "description": agent.description,
        "icon": agent.icon,
        "avatar_url": agent.avatar_url,
        "team": TeamInfo.model_validate(agent.team).model_dump(),
        "model": model_info.model_dump() if model_info else None,
        "status": agent.status.value
        if hasattr(agent.status, "value")
        else agent.status,
        "visibility": normalize_agent_visibility(
            agent.visibility.value
            if hasattr(agent.visibility, "value")
            else agent.visibility
        ),
        "conversation_count": agent.conversation_count,
        "message_count": agent.message_count,
        "created_by": CreatorInfo.model_validate(agent.created_by).model_dump()
        if agent.created_by
        else None,
        "created_at": agent.created_at,
        "updated_at": agent.updated_at,
    }
    return agent_data


# ============ Agent CRUD ============


@router.get("", response_model=Response[PageData[AgentListOut]])
async def list_agents(
    team_id: UUID | None = None,
    status: str | None = None,
    visibility: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(deps.PermissionChecker("agent:read")),
) -> Any:
    """
    List agents.
    If team_id is provided, list agents for that team.
    Otherwise, list all agents the user has access to.
    """
    query = Agent.all()

    if team_id:
        await check_team_access(team_id, current_user)
        if not current_user.is_superuser:
            query = query.filter(team_id=team_id).filter(
                Q(visibility__in=[AgentVisibility.TEAM, AgentVisibility.PUBLIC])
                | Q(created_by=current_user, visibility=AgentVisibility.PRIVATE)
            )
        else:
            query = query.filter(team_id=team_id)
    elif not current_user.is_superuser:
        # Get teams user belongs to
        memberships = await TeamMember.filter(user=current_user).values_list(
            "team_id", flat=True
        )
        # Show team agents + own private agents
        query = query.filter(
            Q(
                team_id__in=memberships,
                visibility__in=[AgentVisibility.TEAM, AgentVisibility.PUBLIC],
            )
            | Q(created_by=current_user, visibility=AgentVisibility.PRIVATE)
        )

    if status:
        query = query.filter(status=status)

    if visibility:
        query = query.filter(visibility=visibility)

    if keyword:
        query = query.filter(
            Q(name__icontains=keyword) | Q(description__icontains=keyword)
        )

    total = await query.count()
    skip = (page - 1) * page_size
    agents = (
        await query.prefetch_related("team", "created_by").offset(skip).limit(page_size)
    )

    # Batch fetch all model info to avoid N+1 queries
    model_ids = [a.model_id for a in agents if a.model_id]
    model_info_map: dict[str, ModelInfo] = {}
    if model_ids:
        team_models = await TeamModel.filter(id__in=model_ids).prefetch_related("model")
        for tm in team_models:
            model_info_map[str(tm.id)] = ModelInfo(
                id=tm.id,
                name=tm.model.name,
                provider=tm.model.provider,
                model_id=tm.model.model_id,
            )

    # Build response with pre-fetched model info
    agent_list = []
    for agent in agents:
        agent_data = await build_agent_list_out(agent, model_info_map)
        agent_list.append(agent_data)

    return success(
        data={
            "items": agent_list,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.post("", response_model=Response[AgentOut])
async def create_agent(
    *,
    request: Request,
    agent_in: AgentCreate,
    current_user: User = Depends(deps.PermissionChecker("agent:create")),
) -> Any:
    """Create a new agent."""
    # Check team access
    team = await check_team_access(agent_in.team_id, current_user)

    # Check for duplicate name within the same team
    existing = await Agent.filter(
        team_id=agent_in.team_id,
        name=agent_in.name,
    ).first()
    if existing:
        raise BusinessError(
            code=ResponseCode.DUPLICATE_NAME,
            msg_key="agent_name_exists",
        )

    # Validate model_id if provided
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

    # Validate knowledge bases
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

    # Create agent
    agent = await Agent.create(
        name=agent_in.name,
        description=agent_in.description,
        icon=agent_in.icon,
        avatar_url=agent_in.avatar_url,
        team=team,
        model_id=agent_in.model_id,
        system_prompt=agent_in.system_prompt,
        max_iterations=agent_in.max_iterations,
        tools_config=[t.model_dump() for t in agent_in.tools_config],
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
        variables=[v.model_dump() for v in agent_in.variables],
        opening_message=agent_in.opening_message,
        suggested_questions=agent_in.suggested_questions,
        visibility=normalize_agent_visibility(agent_in.visibility),
        created_by=current_user,
    )

    # Create knowledge base associations
    for kb_config in agent_in.knowledge_base_configs:
        await AgentKnowledgeBase.create(
            agent=agent,
            knowledge_base_id=kb_config.knowledge_base_id,
            retrieval_top_k=kb_config.retrieval_top_k,
            score_threshold=kb_config.score_threshold,
            search_mode=kb_config.search_mode,
        )

    # Reload with relations
    agent = await Agent.get(id=agent.id).prefetch_related("team", "created_by")

    # 记录审计日志
    await AuditLogService.log(
        user=current_user,
        action="create_agent",
        resource_type="agent",
        resource_id=agent.id,
        resource_name=agent.name,
        operation="create",
        status="success",
        request=request,
        metadata={
            "team_id": str(team.id),
            "team_name": team.name,
            "visibility": agent_in.visibility,
            "kb_count": len(agent_in.knowledge_base_configs),
        },
    )

    agent_data = await build_agent_out(agent)
    return success(data=agent_data, msg_key="agent_created")


@router.get("/{agent_id}", response_model=Response[AgentOut])
async def get_agent(
    agent_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("agent:read")),
) -> Any:
    """Get agent by ID."""
    agent = await check_agent_access(agent_id, current_user)
    agent_data = await build_agent_out(agent)
    return success(data=agent_data)


@router.put("/{agent_id}", response_model=Response[AgentOut])
async def update_agent(
    *,
    request: Request,
    agent_id: UUID,
    agent_in: AgentUpdate,
    current_user: User = Depends(deps.PermissionChecker("agent:update")),
) -> Any:
    """Update an agent."""
    agent = await check_agent_access(agent_id, current_user, require_write=True)

    # Check for duplicate name within the same team (exclude self)
    if agent_in.name is not None and agent_in.name != agent.name:
        existing = (
            await Agent.filter(
                team_id=agent.team_id,
                name=agent_in.name,
            )
            .exclude(id=agent_id)
            .first()
        )
        if existing:
            raise BusinessError(
                code=ResponseCode.DUPLICATE_NAME,
                msg_key="agent_name_exists",
            )

    # Track updated fields
    updated_fields = []

    # Update basic fields
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

    # Update model_id
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

    # Update tools config
    if agent_in.tools_config is not None:
        agent.tools_config = [t.model_dump() for t in agent_in.tools_config]
        updated_fields.append("tools_config")

    # Update enable_vision
    if agent_in.enable_vision is not None:
        agent.enable_vision = agent_in.enable_vision
        updated_fields.append("enable_vision")

    # Update enable_file_upload and file_upload_config
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

    # Update enable_user_input_request
    if agent_in.enable_user_input_request is not None:
        agent.enable_user_input_request = agent_in.enable_user_input_request
        updated_fields.append("enable_user_input_request")

    # Update enable_memory and memory_config
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

    # Update rag_mode
    if agent_in.rag_mode is not None:
        agent.rag_mode = RAGMode(agent_in.rag_mode)
        updated_fields.append("rag_mode")

    # Update variables
    if agent_in.variables is not None:
        agent.variables = [v.model_dump() for v in agent_in.variables]
        updated_fields.append("variables")

    # Update embed_config
    if agent_in.embed_config is not None:
        agent.embed_config = agent_in.embed_config
        updated_fields.append("embed_config")

    await agent.save()

    # Update knowledge bases if provided
    if agent_in.knowledge_base_configs is not None:
        # Delete existing associations
        await AgentKnowledgeBase.filter(agent_id=agent.id).delete()

        # Create new associations
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
            await AgentKnowledgeBase.create(
                agent=agent,
                knowledge_base_id=kb_config.knowledge_base_id,
                retrieval_top_k=kb_config.retrieval_top_k,
                score_threshold=kb_config.score_threshold,
                search_mode=kb_config.search_mode,
            )
        updated_fields.append("knowledge_base_configs")

    # Reload with relations
    agent = await Agent.get(id=agent_id).prefetch_related("team", "created_by")

    # 记录审计日志
    await AuditLogService.log(
        user=current_user,
        action="update_agent",
        resource_type="agent",
        resource_id=agent.id,
        resource_name=agent.name,
        operation="update",
        status="success",
        request=request,
        metadata={"fields_updated": updated_fields},
    )

    agent_data = await build_agent_out(agent)
    return success(data=agent_data, msg_key="agent_updated")


@router.delete("/{agent_id}", response_model=Response[dict])
async def delete_agent(
    request: Request,
    agent_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("agent:delete")),
) -> Any:
    """Delete an agent and all its conversations."""
    agent = await check_agent_access(agent_id, current_user, require_write=True)

    # 记录审计日志（在删除前）
    await AuditLogService.log(
        user=current_user,
        action="delete_agent",
        resource_type="agent",
        resource_id=agent.id,
        resource_name=agent.name,
        operation="delete",
        status="success",
        request=request,
        metadata={
            "team_id": str(agent.team_id),
            "visibility": agent.visibility,
        },
    )

    # Delete agent (cascades to conversations, messages, knowledge base associations)
    await agent.delete()

    return success(data={"id": str(agent_id)}, msg_key="agent_deleted")


@router.post("/{agent_id}/publish", response_model=Response[AgentOut])
async def publish_agent(
    request: Request,
    agent_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("agent:publish")),
) -> Any:
    """Publish an agent."""
    agent = await check_agent_access(agent_id, current_user, require_write=True)

    agent.status = AgentStatus.PUBLISHED
    await agent.save()

    # 记录审计日志
    await AuditLogService.log(
        user=current_user,
        action="publish_agent",
        resource_type="agent",
        resource_id=agent.id,
        resource_name=agent.name,
        operation="update",
        status="success",
        request=request,
    )

    # 发送团队通知
    if agent.team_id:
        await AutoNotificationService.send_to_team(
            notification_type=AutoNotificationType.AGENT_PUBLISHED,
            team_id=agent.team_id,
            title=t("notify_agent_published_title"),
            content=t("notify_agent_published_content", agent_name=agent.name),
        )

    agent_data = await build_agent_out(agent)
    return success(data=agent_data, msg_key="agent_published")


@router.post("/{agent_id}/unpublish", response_model=Response[AgentOut])
async def unpublish_agent(
    request: Request,
    agent_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("agent:publish")),
) -> Any:
    """Unpublish an agent."""
    agent = await check_agent_access(agent_id, current_user, require_write=True)

    agent.status = AgentStatus.DRAFT
    await agent.save()

    # 记录审计日志
    await AuditLogService.log(
        user=current_user,
        action="unpublish_agent",
        resource_type="agent",
        resource_id=agent.id,
        resource_name=agent.name,
        operation="update",
        status="success",
        request=request,
    )

    # 发送团队通知
    if agent.team_id:
        await AutoNotificationService.send_to_team(
            notification_type=AutoNotificationType.AGENT_UNPUBLISHED,
            team_id=agent.team_id,
            title=t("notify_agent_unpublished_title"),
            content=t("notify_agent_unpublished_content", agent_name=agent.name),
        )

    agent_data = await build_agent_out(agent)
    return success(data=agent_data, msg_key="agent_unpublished")


@router.post("/{agent_id}/duplicate", response_model=Response[AgentOut])
async def duplicate_agent(
    agent_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("agent:create")),
) -> Any:
    """Duplicate an agent."""
    agent = await check_agent_access(agent_id, current_user)

    # Create a copy
    new_agent = await Agent.create(
        name=f"{agent.name} (Copy)",
        description=agent.description,
        icon=agent.icon,
        avatar_url=agent.avatar_url,
        team_id=agent.team_id,
        model_id=agent.model_id,
        system_prompt=agent.system_prompt,
        max_iterations=agent.max_iterations,
        tools_config=agent.tools_config,
        enable_vision=agent.enable_vision,
        enable_file_upload=agent.enable_file_upload,
        file_upload_config=agent.file_upload_config,
        enable_user_input_request=agent.enable_user_input_request,
        enable_memory=agent.enable_memory,
        memory_config=agent.memory_config,
        context_compression_config=agent.context_compression_config,
        enable_image_generation=agent.enable_image_generation,
        image_generation_config=(
            {
                key: value
                for key, value in (agent.image_generation_config or {}).items()
                if key != "allow_model_override"
            }
        ),
        enable_video_generation=agent.enable_video_generation,
        video_generation_config=(
            {
                key: value
                for key, value in (agent.video_generation_config or {}).items()
                if key != "allow_model_override"
            }
        ),
        rag_mode=agent.rag_mode,
        variables=agent.variables,
        opening_message=agent.opening_message,
        suggested_questions=agent.suggested_questions,
        visibility=AgentVisibility.PRIVATE,  # Copy is always private
        status=AgentStatus.DRAFT,  # Copy is always draft
        created_by=current_user,
    )

    # Copy knowledge base associations
    kb_associations = await AgentKnowledgeBase.filter(agent_id=agent.id)
    for akb in kb_associations:
        await AgentKnowledgeBase.create(
            agent=new_agent,
            knowledge_base_id=akb.knowledge_base_id,
            retrieval_top_k=akb.retrieval_top_k,
            score_threshold=akb.score_threshold,
            search_mode=akb.search_mode,
        )

    # Reload with relations
    new_agent = await Agent.get(id=new_agent.id).prefetch_related("team", "created_by")
    agent_data = await build_agent_out(new_agent)
    return success(data=agent_data, msg_key="agent_duplicated")


@router.get(
    "/{agent_id}/media/video-status",
    response_model=Response[dict[str, Any]],
)
async def get_agent_video_generation_status(
    agent_id: UUID,
    task_id: str,
    current_user: User = Depends(deps.PermissionChecker("agent:read")),
) -> Any:
    """Get video generation status for an agent media task."""
    from app.llm import model_manager
    from app.llm.tools.builtin.media import build_video_tool_result

    agent = await check_agent_access(agent_id, current_user)
    if not agent.enable_video_generation:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg="Video generation is not enabled for this agent",
            status_code=400,
        )

    config = agent.video_generation_config or {}
    resolved_model_ref = config.get("default_model_ref") or None
    response = await model_manager.get_video_status(
        task_id, model_id=resolved_model_ref
    )
    return success(
        data=build_video_tool_result(
            "",
            response,
            model_ref=resolved_model_ref,
            poll_interval_ms=int(config.get("poll_interval_ms", 3000)),
            poll_timeout_s=int(config.get("poll_timeout_s", 120)),
        ),
        msg_key="success",
    )


# ============ Conversations ============


@router.get(
    "/{agent_id}/conversations", response_model=Response[PageData[ConversationListOut]]
)
async def list_agent_conversations(
    agent_id: UUID,
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(deps.PermissionChecker("conversation:read")),
) -> Any:
    """List conversations for an agent (only user's own conversations)."""
    agent = await check_agent_access(agent_id, current_user)

    query = Conversation.filter(agent_id=agent_id, user=current_user)
    total = await query.count()
    skip = (page - 1) * page_size
    conversations = await query.offset(skip).limit(page_size)

    # Add agent info to each conversation
    conv_list = []
    for conv in conversations:
        conv_data = ConversationListOut.model_validate(conv).model_dump()
        conv_data["agent_name"] = agent.name
        conv_data["agent_icon"] = agent.icon
        conv_list.append(conv_data)

    return success(
        data={
            "items": conv_list,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/conversations/my", response_model=Response[PageData[ConversationListOut]])
async def list_my_conversations(
    agent_id: UUID | None = None,
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(deps.PermissionChecker("conversation:read")),
) -> Any:
    """List all conversations for current user."""
    query = Conversation.filter(user=current_user)

    if agent_id:
        query = query.filter(agent_id=agent_id)

    total = await query.count()
    skip = (page - 1) * page_size
    conversations = await query.prefetch_related("agent").offset(skip).limit(page_size)

    conv_list = []
    for conv in conversations:
        conv_data = ConversationListOut.model_validate(conv).model_dump()
        related_agent = conv.agent
        conv_data["agent_name"] = related_agent.name if related_agent else None
        conv_data["agent_icon"] = related_agent.icon if related_agent else None
        conv_list.append(conv_data)

    return success(
        data={
            "items": conv_list,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.get(
    "/conversations/{conversation_id}",
    response_model=Response[ConversationWithMessages],
)
async def get_conversation(
    conversation_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("conversation:read")),
) -> Any:
    """Get conversation with messages."""
    conversation = (
        await Conversation.filter(
            id=conversation_id,
            user=current_user,
        )
        .prefetch_related("agent")
        .first()
    )

    if not conversation:
        raise BusinessError(
            code=ResponseCode.CONVERSATION_NOT_FOUND,
            msg_key="conversation_not_found",
            status_code=404,
        )

    messages = await Message.filter(
        conversation_id=conversation.id,
        is_active=True,
    ).order_by("created_at")

    # Batch calculate version counts to avoid N+1 queries
    # Get all parent_ids we need to count
    root_ids = set()
    for m in messages:
        root_id = m.parent_id if m.parent_id else m.id
        root_ids.add(root_id)

    # Batch query version counts using GROUP BY
    version_counts: dict[str, int] = {}
    if root_ids:
        # Count children for each parent_id
        child_counts = (
            await Message.filter(parent_id__in=list(root_ids))
            .annotate(count=Count("id"))
            .group_by("parent_id")
            .values("parent_id", "count")
        )

        for item in child_counts:
            version_counts[str(item["parent_id"])] = item["count"] + 1  # +1 for root

        # For root messages without children, set count to 1
        for root_id in root_ids:
            if str(root_id) not in version_counts:
                version_counts[str(root_id)] = 1

    # Build message outputs with pre-fetched version counts
    messages_out = await build_message_round_payloads(messages)
    canonical_messages = [m for m in messages if not m.round_id or m.is_round_canonical]
    for msg_data, m in zip(messages_out, canonical_messages, strict=False):
        root_id = m.parent_id if m.parent_id else m.id
        msg_data["version_count"] = version_counts.get(str(root_id), 1)

    # First convert to ConversationOut, then build ConversationWithMessages
    conv_out = ConversationOut.model_validate(conversation)
    conv_data = conv_out.model_dump()
    related_agent = conversation.agent
    conv_data["agent_name"] = related_agent.name if related_agent else None
    conv_data["agent_icon"] = related_agent.icon if related_agent else None
    conv_data["messages"] = messages_out

    return success(data=conv_data)


@router.patch(
    "/conversations/{conversation_id}", response_model=Response[ConversationOut]
)
async def update_conversation(
    *,
    conversation_id: UUID,
    conv_in: ConversationUpdate,
    current_user: User = Depends(deps.PermissionChecker("conversation:read")),
) -> Any:
    """Update conversation (e.g., rename)."""
    conversation = (
        await Conversation.filter(
            id=conversation_id,
            user=current_user,
        )
        .prefetch_related("agent")
        .first()
    )

    if not conversation:
        raise BusinessError(
            code=ResponseCode.CONVERSATION_NOT_FOUND,
            msg_key="conversation_not_found",
            status_code=404,
        )

    if conv_in.title is not None:
        conversation.title = conv_in.title
        await conversation.save()

    conv_data = ConversationOut.model_validate(conversation).model_dump()
    related_agent = conversation.agent
    conv_data["agent_name"] = related_agent.name if related_agent else None
    conv_data["agent_icon"] = related_agent.icon if related_agent else None

    return success(data=conv_data, msg_key="conversation_updated")


@router.delete("/conversations/{conversation_id}", response_model=Response[dict])
async def delete_conversation(
    conversation_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("conversation:delete")),
) -> Any:
    """Delete a conversation."""
    conversation = await Conversation.filter(
        id=conversation_id,
        user=current_user,
    ).first()

    if not conversation:
        raise BusinessError(
            code=ResponseCode.CONVERSATION_NOT_FOUND,
            msg_key="conversation_not_found",
            status_code=404,
        )

    # Update agent stats atomically to prevent race conditions
    await Agent.filter(id=conversation.agent_id).update(
        conversation_count=F("conversation_count") - 1,
        message_count=F("message_count") - conversation.message_count,
    )

    # Delete conversation (cascades to messages)
    await conversation.delete()

    return success(data={"id": str(conversation_id)}, msg_key="conversation_deleted")


@router.delete(
    "/conversations/{conversation_id}/messages/{message_id}",
    response_model=Response[dict],
)
async def delete_message(
    conversation_id: UUID,
    message_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("conversation:delete")),
) -> Any:
    """Delete a message from a conversation."""
    conversation = await Conversation.filter(
        id=conversation_id,
        user=current_user,
    ).first()

    if not conversation:
        raise BusinessError(
            code=ResponseCode.CONVERSATION_NOT_FOUND,
            msg_key="conversation_not_found",
            status_code=404,
        )

    message = await Message.filter(
        id=message_id,
        conversation_id=conversation_id,
    ).first()

    if not message:
        raise BusinessError(
            code=ResponseCode.MESSAGE_NOT_FOUND,
            msg_key="message_not_found",
            status_code=404,
        )

    # Update stats atomically to prevent race conditions
    tokens_to_remove = 0
    if message.token_usage:
        tokens_to_remove = message.token_usage.get(
            "prompt", 0
        ) + message.token_usage.get("completion", 0)

    await Conversation.filter(id=conversation.id).update(
        message_count=F("message_count") - 1,
        token_usage=F("token_usage") - tokens_to_remove,
    )

    # Delete message
    await message.delete()

    return success(data={"id": str(message_id)}, msg_key="message_deleted")
